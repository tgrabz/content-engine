import { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchVideosForProfile, thumbnailUrl, profileThumbnailUrl, profileStreamUrl,
  streamUrl, type ProfileVideo,
} from '../api/videos'
import { fetchTemplates, templateImageUrl, type Template } from '../api/templates'
import { fetchProfiles, updateProfile, type Profile } from '../api/profiles'
import { fetchNiches, type Niche } from '../api/niches'
import {
  getOrCreateSession, updateSession, startRender, renderStatus,
  exportToProfile, autoEdit, batchRenderStatus, generateCaption,
  type AutoEditItem, type BatchStatusItem,
} from '../api/editor'
import { createPost, fetchPosts, publishPost, deletePost, type Post } from '../api/posts'
import { useAppStore } from '../stores/appStore'
import {
  Film, Loader2, CheckCircle, Star, Send, Sparkles,
  Zap, Plus, Trash2, AlertCircle, X, Play, Type,
  Clock, Calendar, Shield,
} from 'lucide-react'

export default function WorkspacePage() {
  const activeProfileId = useAppStore(s => s.activeProfileId)
  const queryClient = useQueryClient()

  // ─── Data ───
  const { data: profilesRaw } = useQuery({ queryKey: ['profiles'], queryFn: fetchProfiles })
  const profiles = Array.isArray(profilesRaw) ? profilesRaw : []
  const activeProfile = profiles.find(p => p.id === activeProfileId)

  const { data: niches = [] } = useQuery({ queryKey: ['niches'], queryFn: fetchNiches })

  const { data: videos = [], isLoading: videosLoading } = useQuery({
    queryKey: ['profile-videos', activeProfileId],
    queryFn: () => fetchVideosForProfile(activeProfileId!),
    enabled: !!activeProfileId && !!activeProfile?.niche_id,
  })

  const { data: templates = [] } = useQuery({
    queryKey: ['templates', activeProfileId],
    queryFn: () => fetchTemplates(activeProfileId ?? undefined),
  })

  const { data: posts = [] } = useQuery({
    queryKey: ['posts', activeProfileId],
    queryFn: () => fetchPosts({ profile_id: activeProfileId! }),
    enabled: !!activeProfileId,
  })

  // ─── Selected video ───
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const selectedVideo = videos.find(v => v.id === selectedId)

  // ─── Profile config ───
  const handleSetNiche = async (nicheId: number | null) => {
    if (!activeProfileId) return
    setSelectedId(null)
    await updateProfile(activeProfileId, { niche_id: nicheId })
    queryClient.invalidateQueries({ queryKey: ['profiles'] })
    queryClient.invalidateQueries({ queryKey: ['profile-videos'] })
  }

  const handleSetDefaultTemplate = async (tplId: number | null) => {
    if (!activeProfileId) return
    await updateProfile(activeProfileId, { default_template_id: tplId })
    queryClient.invalidateQueries({ queryKey: ['profiles'] })
  }

  // ─── Per-video auto-edit ───
  const [processingIds, setProcessingIds] = useState<Set<number>>(new Set())
  const [activeJobMap, setActiveJobMap] = useState<Map<number, string>>(new Map())
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const singleAutoEditMut = useMutation({
    mutationFn: (videoId: number) => autoEdit(activeProfileId!, [videoId]),
    onSuccess: (items, videoId) => {
      if (items.length > 0) {
        setProcessingIds(prev => new Set(prev).add(videoId))
        setActiveJobMap(prev => new Map(prev).set(videoId, items[0].job_id))
      }
      queryClient.invalidateQueries({ queryKey: ['profile-videos'] })
    },
  })

  // Poll active auto-edit jobs
  useEffect(() => {
    if (activeJobMap.size === 0) {
      if (pollRef.current) clearInterval(pollRef.current)
      return
    }
    pollRef.current = setInterval(async () => {
      const jobIds = Array.from(activeJobMap.values())
      try {
        const statuses = await batchRenderStatus(jobIds)
        const done = new Set<string>()
        for (const s of statuses) {
          if (s.status === 'complete' || s.status === 'failed') done.add(s.job_id)
        }
        if (done.size > 0) {
          setActiveJobMap(prev => {
            const next = new Map(prev)
            for (const [vid, jid] of prev) { if (done.has(jid)) next.delete(vid) }
            return next
          })
          setProcessingIds(prev => {
            const next = new Set(prev)
            for (const [vid, jid] of activeJobMap) { if (done.has(jid)) next.delete(vid) }
            return next
          })
          queryClient.invalidateQueries({ queryKey: ['profile-videos'] })
        }
      } catch { /* keep polling */ }
    }, 2000)
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [activeJobMap]) // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Caption + render for edited videos ───
  const [captionText, setCaptionText] = useState('')
  const [renderJobId, setRenderJobId] = useState<string | null>(null)
  const [renderState, setRenderState] = useState<'idle' | 'rendering' | 'complete' | 'failed'>('idle')
  const [renderProgress, setRenderProgress] = useState(0)
  const renderPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const [aiGenerating, setAiGenerating] = useState(false)
  const [aiCaption, setAiCaption] = useState<{ overlay: string; caption: string } | null>(null)

  // Reset caption state when selecting a new video
  useEffect(() => {
    setCaptionText('')
    setRenderState('idle')
    setRenderJobId(null)
    setRenderProgress(0)
    setAiGenerating(false)
    setAiCaption(null)
    if (renderPollRef.current) clearInterval(renderPollRef.current)
  }, [selectedId])

  const handleRenderAndReady = async () => {
    if (!selectedId || !activeProfileId || !selectedVideo) return

    // Get or create session, save caption, then render
    const session = await getOrCreateSession(selectedId, activeProfileId)
    await updateSession(session.id, {
      caption_text: captionText,
    })

    setRenderState('rendering')
    setRenderProgress(0)

    try {
      const { job_id } = await startRender(session.id, 'Native 1920', true)
      setRenderJobId(job_id)

      if (renderPollRef.current) clearInterval(renderPollRef.current)
      renderPollRef.current = setInterval(async () => {
        try {
          const s = await renderStatus(job_id)
          setRenderProgress(s.progress)
          if (s.status === 'complete') {
            if (renderPollRef.current) clearInterval(renderPollRef.current)
            // Mark as ready
            await exportToProfile(session.id)
            setRenderState('complete')
            queryClient.invalidateQueries({ queryKey: ['profile-videos'] })
          } else if (s.status === 'failed') {
            if (renderPollRef.current) clearInterval(renderPollRef.current)
            setRenderState('failed')
          }
        } catch { /* keep polling */ }
      }, 1000)
    } catch {
      setRenderState('failed')
    }
  }

  useEffect(() => () => { if (renderPollRef.current) clearInterval(renderPollRef.current) }, [])

  // ─── Skip caption — mark ready without re-render ───
  const handleMarkReady = async () => {
    if (!selectedId || !activeProfileId) return
    const session = await getOrCreateSession(selectedId, activeProfileId)
    await exportToProfile(session.id)
    queryClient.invalidateQueries({ queryKey: ['profile-videos'] })
  }

  // ─── AI caption generation ───
  const handleAiGenerate = async () => {
    if (!selectedId || !activeProfileId) return
    setAiGenerating(true)
    try {
      const result = await generateCaption(selectedId, activeProfileId)
      setAiCaption(result)
      setCaptionText(result.overlay)
    } catch (e: any) {
      alert(e?.response?.data?.detail || 'AI caption generation failed')
    } finally {
      setAiGenerating(false)
    }
  }

  // ─── Post queue ───
  const [postCaption, setPostCaption] = useState('')

  const addToQueueMut = useMutation({
    mutationFn: () => {
      if (!selectedId || !activeProfileId) throw new Error('Missing')
      return createPost({ video_id: selectedId, profile_id: activeProfileId, caption: postCaption })
    },
    onSuccess: () => {
      setPostCaption('')
      queryClient.invalidateQueries({ queryKey: ['posts'] })
      queryClient.invalidateQueries({ queryKey: ['profile-videos'] })
    },
  })

  const publishMut = useMutation({
    mutationFn: publishPost,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['posts'] })
      queryClient.invalidateQueries({ queryKey: ['profile-videos'] })
    },
  })

  const deletePostMut = useMutation({
    mutationFn: deletePost,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['posts'] })
      queryClient.invalidateQueries({ queryKey: ['profile-videos'] })
    },
  })

  // ─── Post polling ───
  const scheduledPosts = posts.filter(p => p.status === 'scheduled')
  const activePosts = posts.filter(p => ['queued', 'uploading', 'processing', 'failed'].includes(p.status))
  const allQueuePosts = [...scheduledPosts, ...activePosts]
  const hasActivePosts = posts.some(p => p.status === 'uploading' || p.status === 'processing')
  const postPollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (postPollRef.current) clearInterval(postPollRef.current)
    if (hasActivePosts) {
      postPollRef.current = setInterval(() => {
        queryClient.invalidateQueries({ queryKey: ['posts'] })
        queryClient.invalidateQueries({ queryKey: ['profile-videos'] })
      }, 5000)
    }
    return () => { if (postPollRef.current) clearInterval(postPollRef.current) }
  }, [hasActivePosts]) // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Schedule config ───
  const [showScheduleConfig, setShowScheduleConfig] = useState(false)
  const [scheduleInput, setScheduleInput] = useState('')
  const [dailyLimitInput, setDailyLimitInput] = useState(3)
  const [warmupEnabled, setWarmupEnabled] = useState(false)

  useEffect(() => {
    if (activeProfile) {
      try {
        const times = activeProfile.schedule_times ? JSON.parse(activeProfile.schedule_times) : []
        setScheduleInput(times.join(', '))
      } catch { setScheduleInput('') }
      setDailyLimitInput(activeProfile.daily_post_limit)
      setWarmupEnabled(!!activeProfile.warmup_started_at)
    }
  }, [activeProfile?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Video groups ───
  const readyVideos = videos.filter(v => v.profile_status === 'ready')
  const editedVideos = videos.filter(v => v.profile_status === 'edited')
  const renderingVideos = videos.filter(v =>
    v.profile_status === 'rendering' || processingIds.has(v.id)
  )
  const uneditedVideos = videos.filter(v =>
    !v.profile_status && !processingIds.has(v.id)
  )

  // ─── Guards ───
  if (!activeProfileId || !activeProfile) {
    return (
      <div className="flex items-center justify-center h-screen text-zinc-500">
        <div className="text-center">
          <Film size={48} className="mx-auto mb-4 opacity-30" />
          <p className="text-lg font-medium text-zinc-400">Select a profile</p>
          <p className="text-sm mt-1">Choose a profile from the sidebar to start</p>
        </div>
      </div>
    )
  }

  const needsSetup = !activeProfile.niche_id || !activeProfile.default_template_id

  const handleSaveSchedule = async () => {
    if (!activeProfileId) return
    const times = scheduleInput
      .split(',')
      .map(s => s.trim())
      .filter(s => /^\d{1,2}:\d{2}$/.test(s))
    await updateProfile(activeProfileId, {
      schedule_times: times.length > 0 ? times : null,
      daily_post_limit: dailyLimitInput,
      warmup_started_at: warmupEnabled && !activeProfile?.warmup_started_at
        ? new Date().toISOString()
        : warmupEnabled
          ? activeProfile?.warmup_started_at
          : null,
    } as any)
    queryClient.invalidateQueries({ queryKey: ['profiles'] })
    setShowScheduleConfig(false)
  }

  // Determine detail panel mode
  const isProcessing = selectedVideo && (selectedVideo.profile_status === 'rendering' || processingIds.has(selectedVideo.id))
  const isEdited = selectedVideo?.profile_status === 'edited'
  const isReady = selectedVideo?.profile_status === 'ready'
  const isUnedited = selectedVideo && !selectedVideo.profile_status && !processingIds.has(selectedVideo.id)

  return (
    <div className="flex h-screen overflow-hidden">
      {/* ─── Main feed ─── */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        {/* Top bar */}
        <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between shrink-0">
          <div>
            <h1 className="text-lg font-bold text-white">{activeProfile.name}</h1>
            <div className="flex items-center gap-1.5 text-xs text-zinc-500">
              <select
                value={activeProfile.niche_id ?? ''}
                onChange={e => handleSetNiche(e.target.value ? Number(e.target.value) : null)}
                className="bg-transparent text-zinc-400 hover:text-white text-xs cursor-pointer focus:outline-none appearance-none pr-4 border-none"
                style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' width=\'10\' height=\'6\' fill=\'%2371717a\'%3E%3Cpath d=\'M0 0l5 6 5-6z\'/%3E%3C/svg%3E")', backgroundRepeat: 'no-repeat', backgroundPosition: 'right center' }}
              >
                <option value="">No niche</option>
                {niches.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
              </select>
              <span>·</span>
              <span>{videos.length} videos</span>
              {readyVideos.length > 0 && <span className="text-green-400">· {readyVideos.length} ready</span>}
              {editedVideos.length > 0 && <span className="text-blue-400">· {editedVideos.length} edited</span>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {scheduledPosts.length > 0 && (
              <span className="text-[10px] text-violet-400 bg-violet-500/10 px-2 py-1 rounded-full flex items-center gap-1">
                <Clock size={10} /> {scheduledPosts.length} scheduled
              </span>
            )}
            {activePosts.length > 0 && (
              <span className="text-[10px] text-amber-400 bg-amber-500/10 px-2 py-1 rounded-full">
                {activePosts.length} queued
              </span>
            )}
            <button
              onClick={() => setShowScheduleConfig(!showScheduleConfig)}
              className={`text-[10px] px-2 py-1 rounded-full transition-colors flex items-center gap-1 ${
                activeProfile.schedule_times
                  ? 'text-green-400 bg-green-500/10 hover:bg-green-500/20'
                  : 'text-zinc-500 bg-zinc-800 hover:bg-zinc-700'
              }`}
            >
              <Calendar size={10} /> {activeProfile.schedule_times ? 'Schedule On' : 'No Schedule'}
            </button>
          </div>
        </div>

        {/* Setup banner */}
        {needsSetup && (
          <div className="mx-6 mt-4 px-4 py-3 bg-amber-500/10 border border-amber-500/30 rounded-lg">
            <p className="text-amber-300 text-sm font-medium mb-2">Setup needed</p>
            <div className="flex gap-4">
              {!activeProfile.niche_id && (
                <div className="flex-1">
                  <label className="text-[10px] text-amber-300/70 uppercase tracking-wider">Niche</label>
                  <select
                    value=""
                    onChange={e => handleSetNiche(Number(e.target.value))}
                    className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-white"
                  >
                    <option value="">Select niche...</option>
                    {niches.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
                  </select>
                </div>
              )}
              {!activeProfile.default_template_id && (
                <div className="flex-1">
                  <label className="text-[10px] text-amber-300/70 uppercase tracking-wider">Default Template</label>
                  <div className="flex gap-1.5 mt-1">
                    {templates.map(t => (
                      <button
                        key={t.id}
                        onClick={() => handleSetDefaultTemplate(t.id)}
                        className="w-12 aspect-[9/16] rounded border border-zinc-700 hover:border-amber-500 overflow-hidden transition-all"
                      >
                        <img src={templateImageUrl(t.id)} alt={t.name} className="w-full h-full object-cover" />
                      </button>
                    ))}
                    {templates.length === 0 && <p className="text-zinc-500 text-xs">Create templates first</p>}
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Schedule config panel */}
        {showScheduleConfig && (
          <div className="mx-6 mt-4 px-4 py-3 bg-zinc-800/50 border border-zinc-700 rounded-lg space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-medium text-white flex items-center gap-1.5">
                <Calendar size={14} /> Posting Schedule
              </h3>
              <button onClick={() => setShowScheduleConfig(false)} className="p-1 rounded hover:bg-zinc-700 text-zinc-500">
                <X size={14} />
              </button>
            </div>

            <div>
              <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1 block">
                Post Times (UTC, comma-separated)
              </label>
              <input
                type="text"
                value={scheduleInput}
                onChange={e => setScheduleInput(e.target.value)}
                placeholder="9:00, 14:00, 19:00"
                className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-white focus:border-violet-500 focus:outline-none"
              />
              <p className="text-[10px] text-zinc-600 mt-0.5">e.g. 9:00, 14:00, 19:00</p>
            </div>

            <div className="flex gap-4">
              <div className="flex-1">
                <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1 block">
                  Daily Limit
                </label>
                <input
                  type="number"
                  min={1}
                  max={10}
                  value={dailyLimitInput}
                  onChange={e => setDailyLimitInput(Number(e.target.value))}
                  className="w-full bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-white focus:border-violet-500 focus:outline-none"
                />
              </div>
              <div className="flex-1">
                <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1 block">
                  Warmup Mode
                </label>
                <button
                  onClick={() => setWarmupEnabled(!warmupEnabled)}
                  className={`w-full flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                    warmupEnabled
                      ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                      : 'bg-zinc-900 text-zinc-500 border border-zinc-700 hover:border-zinc-600'
                  }`}
                >
                  <Shield size={12} /> {warmupEnabled ? 'On' : 'Off'}
                </button>
                {warmupEnabled && (
                  <p className="text-[10px] text-amber-400/60 mt-0.5">Wk1: 1/day, Wk2: 2/day, then full</p>
                )}
              </div>
            </div>

            <button
              onClick={handleSaveSchedule}
              className="w-full px-4 py-2 bg-violet-600 hover:bg-violet-500 rounded-lg text-sm font-medium text-white transition-all"
            >
              Save Schedule
            </button>
          </div>
        )}

        {/* Video feed */}
        <div className="flex-1 overflow-auto px-6 py-4">
          {videosLoading && (
            <div className="flex justify-center py-12">
              <Loader2 size={24} className="animate-spin text-zinc-600" />
            </div>
          )}

          {!activeProfile.niche_id && !videosLoading && (
            <div className="text-center py-12 text-zinc-600">
              <Film size={40} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">Assign a niche to see videos</p>
            </div>
          )}

          {readyVideos.length > 0 && (
            <FeedSection label="Ready to Post" count={readyVideos.length} color="green">
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                {readyVideos.map(v => (
                  <VideoCard key={v.id} video={v} profileId={activeProfileId} selected={v.id === selectedId}
                    isProcessing={false} onClick={() => setSelectedId(v.id === selectedId ? null : v.id)} />
                ))}
              </div>
            </FeedSection>
          )}

          {editedVideos.length > 0 && (
            <FeedSection label="Edited — Add Caption" count={editedVideos.length} color="blue">
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                {editedVideos.map(v => (
                  <VideoCard key={v.id} video={v} profileId={activeProfileId} selected={v.id === selectedId}
                    isProcessing={false} onClick={() => setSelectedId(v.id === selectedId ? null : v.id)}
                    badge="Edited" badgeColor="blue" />
                ))}
              </div>
            </FeedSection>
          )}

          {renderingVideos.length > 0 && (
            <FeedSection label="Processing" count={renderingVideos.length} color="violet">
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                {renderingVideos.map(v => (
                  <VideoCard key={v.id} video={v} profileId={activeProfileId} selected={v.id === selectedId}
                    isProcessing={true} onClick={() => setSelectedId(v.id === selectedId ? null : v.id)} />
                ))}
              </div>
            </FeedSection>
          )}

          {uneditedVideos.length > 0 && (
            <FeedSection label="Unedited" count={uneditedVideos.length} color="zinc">
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 gap-3">
                {uneditedVideos.map(v => (
                  <VideoCard key={v.id} video={v} profileId={activeProfileId} selected={v.id === selectedId}
                    isProcessing={processingIds.has(v.id)}
                    onClick={() => setSelectedId(v.id === selectedId ? null : v.id)}
                    onAutoEdit={activeProfile.default_template_id
                      ? () => singleAutoEditMut.mutate(v.id)
                      : undefined
                    } />
                ))}
              </div>
            </FeedSection>
          )}
        </div>
      </div>

      {/* ─── Detail panel ─── */}
      {selectedVideo && (
        <div className="w-80 border-l border-zinc-800 bg-zinc-900 flex flex-col h-full shrink-0">
          {/* Header */}
          <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between shrink-0">
            <div className="min-w-0">
              <p className="text-sm font-medium text-white truncate">@{selectedVideo.source_account}</p>
              <p className="text-[10px] text-zinc-500">{selectedVideo.shortcode}</p>
            </div>
            <button onClick={() => setSelectedId(null)}
              className="p-1 rounded hover:bg-zinc-800 text-zinc-500 transition-colors shrink-0">
              <X size={16} />
            </button>
          </div>

          <div className="flex-1 overflow-auto">
            {/* Video preview */}
            <div className="p-4">
              <video
                key={`${selectedVideo.id}-${selectedVideo.profile_status}-${selectedVideo.profile_exported_path || ''}`}
                src={`${selectedVideo.profile_exported_path
                  ? profileStreamUrl(selectedVideo.id, activeProfileId)
                  : streamUrl(selectedVideo.id)}${selectedVideo.profile_exported_path ? '&' : '?'}_s=${selectedVideo.profile_status || 'raw'}`}
                poster={`${selectedVideo.profile_exported_path
                  ? profileThumbnailUrl(selectedVideo.id, activeProfileId)
                  : thumbnailUrl(selectedVideo.id)}${selectedVideo.profile_exported_path ? '&' : '?'}_s=${selectedVideo.profile_status || 'raw'}`}
                controls
                className="w-full rounded-lg border border-zinc-700"
                style={{ aspectRatio: '9/16' }}
              />
            </div>

            <div className="px-4 pb-4 space-y-3">
              {/* ── UNEDITED ── */}
              {isUnedited && (
                <>
                  <span className="inline-flex items-center gap-1.5 text-xs text-zinc-400 bg-zinc-800 px-2.5 py-1 rounded-full">
                    Unedited
                  </span>
                  <button
                    onClick={() => singleAutoEditMut.mutate(selectedVideo.id)}
                    disabled={!activeProfile.default_template_id || singleAutoEditMut.isPending}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-violet-600 hover:bg-violet-500 disabled:bg-zinc-800 disabled:text-zinc-500 rounded-lg text-sm font-medium text-white transition-all"
                  >
                    {singleAutoEditMut.isPending
                      ? <><Loader2 size={14} className="animate-spin" /> Starting...</>
                      : <><Zap size={14} /> Auto Edit</>}
                  </button>
                  {!activeProfile.default_template_id && (
                    <p className="text-amber-400/70 text-[10px] text-center">Set a default template first</p>
                  )}
                </>
              )}

              {/* ── PROCESSING ── */}
              {isProcessing && (
                <>
                  <span className="inline-flex items-center gap-1.5 text-xs text-violet-400 bg-violet-500/10 px-2.5 py-1 rounded-full">
                    <Loader2 size={12} className="animate-spin" /> Processing
                  </span>
                  <div className="text-center py-3">
                    <p className="text-xs text-zinc-400">Auto-editing in progress...</p>
                    <p className="text-[10px] text-zinc-600 mt-1">Cropping onto template and rendering</p>
                  </div>
                </>
              )}

              {/* ── EDITED — add caption + mark ready ── */}
              {isEdited && (
                <>
                  <span className="inline-flex items-center gap-1.5 text-xs text-blue-400 bg-blue-500/10 px-2.5 py-1 rounded-full">
                    <Type size={12} /> Edited — Add Caption
                  </span>

                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
                        Caption Overlay
                      </label>
                      <button
                        onClick={handleAiGenerate}
                        disabled={aiGenerating}
                        className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium text-violet-400 bg-violet-500/10 hover:bg-violet-500/20 disabled:opacity-50 rounded-md transition-colors"
                      >
                        {aiGenerating
                          ? <><Loader2 size={10} className="animate-spin" /> Generating...</>
                          : <><Sparkles size={10} /> Generate with AI</>}
                      </button>
                    </div>
                    <textarea
                      value={captionText}
                      onChange={e => setCaptionText(e.target.value)}
                      placeholder="Text to burn into the video..."
                      rows={3}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm resize-none focus:border-violet-500 focus:outline-none transition-colors"
                    />
                    <p className="text-[10px] text-zinc-600 mt-1">This text appears on the video itself</p>
                  </div>

                  {/* Render with caption + mark ready */}
                  {captionText.trim() ? (
                    <button
                      onClick={handleRenderAndReady}
                      disabled={renderState === 'rendering'}
                      className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-green-600 hover:bg-green-500 disabled:bg-green-600/50 rounded-lg text-sm font-medium text-white transition-all"
                    >
                      {renderState === 'rendering'
                        ? <><Loader2 size={14} className="animate-spin" /> Rendering {renderProgress}%</>
                        : <><Play size={14} /> Render & Mark Ready</>}
                    </button>
                  ) : (
                    <button
                      onClick={handleMarkReady}
                      className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-green-600 hover:bg-green-500 rounded-lg text-sm font-medium text-white transition-all"
                    >
                      <CheckCircle size={14} /> Mark Ready (No Caption)
                    </button>
                  )}

                  {renderState === 'rendering' && (
                    <div className="w-full h-1.5 bg-zinc-800 rounded-full overflow-hidden">
                      <div className="h-full bg-green-500 transition-all duration-500 rounded-full"
                        style={{ width: `${renderProgress}%` }} />
                    </div>
                  )}
                  {renderState === 'failed' && (
                    <p className="text-red-400 text-xs">Render failed. Try again.</p>
                  )}
                </>
              )}

              {/* ── READY — post it ── */}
              {isReady && (
                <>
                  <span className="inline-flex items-center gap-1.5 text-xs text-green-400 bg-green-500/10 px-2.5 py-1 rounded-full">
                    <CheckCircle size={12} /> Ready to Post
                  </span>

                  <div>
                    <div className="flex items-center justify-between mb-1.5">
                      <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
                        Instagram Caption
                      </label>
                      <button
                        onClick={async () => {
                          if (aiCaption?.caption) {
                            setPostCaption(aiCaption.caption)
                          } else if (selectedId && activeProfileId) {
                            setAiGenerating(true)
                            try {
                              const result = await generateCaption(selectedId, activeProfileId)
                              setAiCaption(result)
                              setPostCaption(result.caption)
                            } catch (e: any) {
                              alert(e?.response?.data?.detail || 'AI caption generation failed')
                            } finally {
                              setAiGenerating(false)
                            }
                          }
                        }}
                        disabled={aiGenerating}
                        className="flex items-center gap-1 px-2 py-1 text-[10px] font-medium text-violet-400 bg-violet-500/10 hover:bg-violet-500/20 disabled:opacity-50 rounded-md transition-colors"
                      >
                        {aiGenerating
                          ? <><Loader2 size={10} className="animate-spin" /> Generating...</>
                          : <><Sparkles size={10} /> {aiCaption?.caption ? 'Use AI Caption' : 'Generate with AI'}</>}
                      </button>
                    </div>
                    <textarea
                      value={postCaption}
                      onChange={e => setPostCaption(e.target.value)}
                      placeholder="Write your Instagram caption..."
                      rows={5}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm resize-none focus:border-violet-500 focus:outline-none transition-colors"
                    />
                  </div>

                  <button
                    onClick={() => addToQueueMut.mutate()}
                    disabled={addToQueueMut.isPending}
                    className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-violet-600 hover:bg-violet-500 rounded-lg text-sm font-medium text-white transition-all disabled:opacity-50"
                  >
                    {addToQueueMut.isPending
                      ? <><Loader2 size={14} className="animate-spin" /> Adding...</>
                      : <><Plus size={14} /> Add to Queue</>}
                  </button>
                </>
              )}

              {/* Video info */}
              <div className="pt-3 border-t border-zinc-800 space-y-1">
                {selectedVideo.duration_sec && (
                  <div className="flex justify-between text-xs">
                    <span className="text-zinc-500">Duration</span>
                    <span className="text-zinc-300">{selectedVideo.duration_sec.toFixed(1)}s</span>
                  </div>
                )}
                {selectedVideo.width && selectedVideo.height && (
                  <div className="flex justify-between text-xs">
                    <span className="text-zinc-500">Resolution</span>
                    <span className="text-zinc-300">{selectedVideo.width}x{selectedVideo.height}</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Post queue */}
          {allQueuePosts.length > 0 && (
            <div className="border-t border-zinc-800 shrink-0">
              <div className="px-4 py-2 flex items-center justify-between">
                <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold flex items-center gap-1.5">
                  <Send size={11} /> Queue
                </h3>
                <span className="text-[10px] text-zinc-600">{allQueuePosts.length}</span>
              </div>
              <div className="max-h-48 overflow-auto px-2 pb-2 space-y-1">
                {allQueuePosts.map(post => (
                  <div key={post.id} className="flex items-center gap-2 px-2 py-1.5 bg-zinc-800 rounded-lg">
                    <div className="w-7 h-7 rounded overflow-hidden bg-zinc-700 shrink-0">
                      <img src={`${profileThumbnailUrl(post.video_id, activeProfileId)}&_s=queued`}
                        alt="" className="w-full h-full object-cover"
                        onError={e => (e.currentTarget.style.display = 'none')} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className="text-[10px] text-zinc-300 truncate">{post.caption || '(no caption)'}</p>
                      {post.status === 'scheduled' && post.scheduled_for && (
                        <p className="text-[9px] text-violet-400 flex items-center gap-0.5">
                          <Clock size={8} />
                          {new Date(post.scheduled_for).toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' })}
                          {' '}
                          {new Date(post.scheduled_for).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}
                        </p>
                      )}
                      {post.status === 'uploading' && (
                        <p className="text-[9px] text-amber-400 flex items-center gap-0.5"><Loader2 size={8} className="animate-spin" /> Uploading</p>
                      )}
                      {post.status === 'processing' && (
                        <p className="text-[9px] text-amber-400 flex items-center gap-0.5"><Loader2 size={8} className="animate-spin" /> Processing</p>
                      )}
                    </div>
                    {post.status === 'failed' && <AlertCircle size={10} className="text-red-400 shrink-0" title={post.error_message || 'Failed'} />}
                    {(post.status === 'queued' || post.status === 'scheduled' || post.status === 'failed') && (
                      <button onClick={() => publishMut.mutate(post.id)} disabled={publishMut.isPending}
                        className="p-1 rounded hover:bg-green-600/20 text-green-400 transition-colors disabled:opacity-50 shrink-0"
                        title={post.status === 'scheduled' ? 'Publish Now' : 'Publish'}>
                        <Send size={11} />
                      </button>
                    )}
                    {!['uploading', 'processing'].includes(post.status) && (
                      <button onClick={() => deletePostMut.mutate(post.id)}
                        className="p-1 rounded hover:bg-red-600/20 text-zinc-500 hover:text-red-400 transition-colors shrink-0" title="Remove">
                        <Trash2 size={11} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}


// ─── Sub-components ───

function FeedSection({ label, count, color, children }: {
  label: string; count: number; color: string; children: React.ReactNode
}) {
  const colors: Record<string, { label: string; badge: string }> = {
    green: { label: 'text-green-400', badge: 'bg-green-500/10 text-green-400' },
    blue: { label: 'text-blue-400', badge: 'bg-blue-500/10 text-blue-400' },
    violet: { label: 'text-violet-400', badge: 'bg-violet-500/10 text-violet-400' },
    zinc: { label: 'text-zinc-500', badge: 'bg-zinc-800 text-zinc-500' },
  }
  const c = colors[color] || colors.zinc
  return (
    <div className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <h2 className={`text-xs uppercase tracking-wider font-semibold ${c.label}`}>{label}</h2>
        <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${c.badge}`}>{count}</span>
      </div>
      {children}
    </div>
  )
}

function VideoCard({ video, profileId, selected, isProcessing, onClick, onAutoEdit, badge, badgeColor }: {
  video: ProfileVideo; profileId: number; selected: boolean; isProcessing: boolean
  onClick: () => void; onAutoEdit?: () => void; badge?: string; badgeColor?: string
}) {
  const badgeStyles: Record<string, string> = {
    green: 'bg-green-600/90',
    blue: 'bg-blue-600/90',
  }
  return (
    <div
      className={`group rounded-lg overflow-hidden border transition-all cursor-pointer ${
        selected ? 'border-violet-500 ring-1 ring-violet-500/30' : 'border-zinc-800 hover:border-zinc-600'
      }`}
      onClick={onClick}
    >
      <div className="relative aspect-[9/16] bg-zinc-800">
        <img
          src={`${video.profile_exported_path ? profileThumbnailUrl(video.id, profileId) : thumbnailUrl(video.id)}${video.profile_exported_path ? '&' : '?'}_s=${video.profile_status || 'raw'}`}
          alt="" loading="lazy" className="w-full h-full object-cover"
          onError={e => (e.currentTarget.style.display = 'none')}
        />
        {isProcessing && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/60">
            <Loader2 size={18} className="animate-spin text-violet-400" />
          </div>
        )}
        {video.profile_status === 'ready' && !isProcessing && (
          <div className="absolute top-1.5 left-1.5">
            <span className="flex items-center gap-0.5 text-[9px] bg-green-600/90 text-white px-1.5 py-0.5 rounded-full font-medium">
              <CheckCircle size={8} /> Ready
            </span>
          </div>
        )}
        {badge && !isProcessing && (
          <div className="absolute top-1.5 left-1.5">
            <span className={`text-[9px] text-white px-1.5 py-0.5 rounded-full font-medium ${badgeStyles[badgeColor || 'blue'] || badgeStyles.blue}`}>
              {badge}
            </span>
          </div>
        )}
        {onAutoEdit && !isProcessing && !video.profile_status && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/0 group-hover:bg-black/50 transition-all">
            <button
              onClick={e => { e.stopPropagation(); onAutoEdit() }}
              className="opacity-0 group-hover:opacity-100 flex items-center gap-1.5 px-3 py-2 bg-violet-600 hover:bg-violet-500 rounded-lg text-xs font-medium text-white transition-all"
            >
              <Zap size={12} /> Auto Edit
            </button>
          </div>
        )}
      </div>
      <div className="px-2 py-1 bg-zinc-900">
        <p className="text-[10px] text-zinc-400 truncate">@{video.source_account}</p>
      </div>
    </div>
  )
}
