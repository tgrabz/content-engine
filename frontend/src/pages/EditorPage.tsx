import { useState, useEffect, useRef } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchVideos, thumbnailUrl } from '../api/videos'
import { fetchTemplates, templateImageUrl } from '../api/templates'
import { fetchProfiles, updateProfile } from '../api/profiles'
import {
  getOrCreateSession, updateSession, autoCrop, captionPlace,
  startRender, renderStatus, renderDownloadUrl, exportToProfile,
  generateCaption, describeCaption,
} from '../api/editor'
import { useEditorStore } from '../stores/editorStore'
import { useAppStore } from '../stores/appStore'
import EditorCanvas from '../components/editor/EditorCanvas'
import { Save, Check, Film, Layers, Type, Sliders, Crop, Wand2, Loader2, Play, Download, CheckCircle, Volume2, VolumeX, Star, ArrowLeft, Sparkles, MessageSquare, Eye, X } from 'lucide-react'

function parseBox(json: string): [number, number, number, number] {
  try {
    const arr = JSON.parse(json)
    if (Array.isArray(arr) && arr.length === 4) return arr as [number, number, number, number]
  } catch { /* fallback */ }
  return [0, 0, 1, 1]
}

export default function EditorPage() {
  const [searchParams] = useSearchParams()
  const initialVideoId = searchParams.get('video') ? Number(searchParams.get('video')) : null
  const activeProfileId = useAppStore(s => s.activeProfileId)

  const store = useEditorStore()
  const {
    videoId, templateId, sessionId, frameTimestamp,
    cropBox, captionBox: storeCaptionBox, captionText, captionColor, postCaption, isDirty,
    setVideo, setTemplate, setSessionId, setFrameTimestamp,
    setCaptionText, setCaptionColor, setPostCaption, loadSession, markClean,
  } = store

  // Sync video selection with URL — set from param, or clear when navigating to /editor
  useEffect(() => {
    if (initialVideoId) {
      if (!videoId) setVideo(initialVideoId)
    } else {
      if (videoId) setVideo(null)
    }
  }, [initialVideoId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Canvas sizing
  const containerRef = useRef<HTMLDivElement>(null)
  const [canvasSize, setCanvasSize] = useState({ w: 0, h: 0 })

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const update = () => {
      const cw = el.clientWidth
      // Use viewport height minus header/padding for max canvas height
      const maxH = window.innerHeight - 120
      if (cw === 0 || maxH <= 0) return
      // Fit 9:16 within available space
      const wFromH = Math.floor(maxH * (9 / 16))
      if (wFromH <= cw) {
        setCanvasSize({ w: wFromH, h: maxH })
      } else {
        const hFromW = Math.floor(cw * (16 / 9))
        setCanvasSize({ w: cw, h: hFromW })
      }
    }
    const ro = new ResizeObserver(update)
    ro.observe(el)
    update()
    window.addEventListener('resize', update)
    return () => { ro.disconnect(); window.removeEventListener('resize', update) }
  }, [videoId])

  // Data queries
  const { data: videos = [] } = useQuery({
    queryKey: ['videos', { status: 'downloaded', limit: 100 }],
    queryFn: () => fetchVideos({ limit: 100 }),
  })
  const { data: profilesRaw } = useQuery({
    queryKey: ['profiles'],
    queryFn: () => fetchProfiles(),
  })
  const profiles = Array.isArray(profilesRaw) ? profilesRaw : []
  const { data: templates = [] } = useQuery({
    queryKey: ['templates', activeProfileId],
    queryFn: () => fetchTemplates(activeProfileId ?? undefined),
  })

  const activeProfile = profiles.find(p => p.id === activeProfileId)
  const selectedVideo = videos.find(v => v.id === videoId)
  const selectedTemplate = templates.find(t => t.id === templateId)

  // Load/create edit session when video + profile are set
  useEffect(() => {
    if (!videoId || !activeProfileId) return
    getOrCreateSession(videoId, activeProfileId).then(session => {
      setSessionId(session.id)
      loadSession(session)
      // Auto-select profile's default template for new sessions (no template set yet)
      if (!session.template_id && activeProfile?.default_template_id) {
        setTemplate(activeProfile.default_template_id)
      }
    })
  }, [videoId, activeProfileId]) // eslint-disable-line react-hooks/exhaustive-deps

  // Save mutation
  const saveMut = useMutation({
    mutationFn: () => {
      if (!sessionId) throw new Error('No session')
      return updateSession(sessionId, {
        template_id: templateId,
        crop_box: JSON.stringify(cropBox),
        caption_text: captionText,
        caption_color: captionColor,
        caption_box: storeCaptionBox ? JSON.stringify(storeCaptionBox) : '',
        post_caption: postCaption,
      })
    },
    onSuccess: () => markClean(),
  })

  // Auto-crop mutation
  const cropMut = useMutation({
    mutationFn: () => {
      if (!videoId) throw new Error('No video')
      return autoCrop(videoId)
    },
    onSuccess: (data) => {
      store.setCropBox(data.crop_box)
    },
  })

  // AI caption generation mutations
  const [showDescribe, setShowDescribe] = useState(false)
  const [describeInput, setDescribeInput] = useState('')

  const aiCaptionMut = useMutation({
    mutationFn: () => {
      if (!videoId || !activeProfileId) throw new Error('No video or profile')
      return generateCaption(videoId, activeProfileId)
    },
    onSuccess: (data) => {
      setCaptionText(data.overlay)
      setPostCaption(data.caption)
    },
  })

  const describeMut = useMutation({
    mutationFn: (description: string) => describeCaption(description),
    onSuccess: (data) => {
      setPostCaption(data.caption)
      setShowDescribe(false)
      setDescribeInput('')
    },
  })

  // Auto-run smart placement when template or crop changes
  useEffect(() => {
    if (!videoId || !templateId) return
    captionPlace(videoId, templateId, videoBox, cropBox).then((data) => {
      store.setCaptionBox(data.caption_box as [number, number, number, number])
      store.setCaptionColor(data.caption_color)
    }).catch(() => { /* ignore - user can still click Smart Placement manually */ })
  }, [videoId, templateId, cropBox]) // eslint-disable-line react-hooks/exhaustive-deps

  // ──── Render state ────
  const [renderQuality, setRenderQuality] = useState('Native 1920')
  const [includeAudio, setIncludeAudio] = useState(true)
  const [renderJobId, setRenderJobId] = useState<string | null>(null)
  const [renderProgress, setRenderProgress] = useState(0)
  const [renderState, setRenderState] = useState<'idle' | 'rendering' | 'complete' | 'failed'>('idle')
  const [renderError, setRenderError] = useState<string | null>(null)
  const [showPreview, setShowPreview] = useState(false)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const handleRender = async () => {
    if (!sessionId) return
    // Save first if dirty
    if (isDirty) {
      await updateSession(sessionId, {
        template_id: templateId,
        crop_box: JSON.stringify(cropBox),
        caption_text: captionText,
        caption_color: captionColor,
        caption_box: storeCaptionBox ? JSON.stringify(storeCaptionBox) : '',
        post_caption: postCaption,
      })
      markClean()
    }
    setRenderState('rendering')
    setRenderProgress(0)
    setRenderError(null)
    try {
      const { job_id } = await startRender(sessionId, renderQuality, includeAudio)
      setRenderJobId(job_id)
      // Start polling
      if (pollRef.current) clearInterval(pollRef.current)
      pollRef.current = setInterval(async () => {
        try {
          const status = await renderStatus(job_id)
          setRenderProgress(status.progress)
          if (status.status === 'complete') {
            setRenderState('complete')
            if (pollRef.current) clearInterval(pollRef.current)
          } else if (status.status === 'failed') {
            setRenderState('failed')
            setRenderError(status.error || 'Render failed')
            if (pollRef.current) clearInterval(pollRef.current)
          }
        } catch {
          // Keep polling
        }
      }, 1000)
    } catch (e: unknown) {
      setRenderState('failed')
      setRenderError(e instanceof Error ? e.message : 'Failed to start render')
    }
  }

  // Cleanup poll on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const handleExport = async () => {
    if (!sessionId) return
    try {
      await exportToProfile(sessionId)
    } catch { /* handled in UI */ }
  }

  // Template geometry
  const videoBox = selectedTemplate ? parseBox(selectedTemplate.video_box) : [0.06, 0.18, 0.94, 0.94] as [number, number, number, number]
  const templateCaptionBox = selectedTemplate ? parseBox(selectedTemplate.caption_box) : [0.06, 0.08, 0.94, 0.16] as [number, number, number, number]
  // Prefer store's captionBox (from Smart Placement) over template default
  const captionBox = storeCaptionBox ?? templateCaptionBox

  const queryClient = useQueryClient()

  const handleSetDefaultTemplate = async (tplId: number | null) => {
    if (!activeProfileId) return
    await updateProfile(activeProfileId, { default_template_id: tplId })
    queryClient.invalidateQueries({ queryKey: ['profiles'] })
  }

  const [saved, setSaved] = useState(false)
  const handleSave = () => {
    saveMut.mutate(undefined, {
      onSuccess: () => {
        setSaved(true)
        setTimeout(() => setSaved(false), 2000)
      },
    })
  }

  // ─── Video grid (no video selected) ───
  if (!videoId) {
    return (
      <div className="h-screen overflow-auto p-8">
        <div className="max-w-6xl space-y-5">
          <div>
            <h2 className="text-2xl font-bold text-white mb-1">Editor</h2>
            <p className="text-zinc-400 text-sm">
              {videos.length} video{videos.length !== 1 ? 's' : ''} — select one to edit
            </p>
          </div>

          {!activeProfileId && (
            <div className="px-3 py-2 bg-amber-500/10 border border-amber-500/30 rounded-lg">
              <p className="text-amber-300 text-xs">Select a profile in the sidebar to enable edit sessions.</p>
            </div>
          )}

          {videos.length === 0 ? (
            <div className="text-center py-20 text-zinc-600">
              <Film size={40} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">No videos found.</p>
              <p className="text-xs mt-1">Scrape some reels to populate your library.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
              {videos.map(v => (
                <button
                  key={v.id}
                  onClick={() => setVideo(v.id)}
                  className="group text-left rounded-xl overflow-hidden border border-zinc-800 hover:border-zinc-700 transition-all"
                >
                  <div className="relative aspect-[9/16] bg-zinc-800">
                    <img
                      src={thumbnailUrl(v.id)}
                      alt=""
                      loading="lazy"
                      className="w-full h-full object-cover"
                      onError={e => (e.currentTarget.style.display = 'none')}
                    />
                    {v.duration_sec !== null && (
                      <span className="absolute bottom-1.5 right-1.5 bg-black/70 text-white text-[10px] px-1.5 py-0.5 rounded-md font-mono">
                        {Math.floor(v.duration_sec / 60)}:{Math.floor(v.duration_sec % 60).toString().padStart(2, '0')}
                      </span>
                    )}
                  </div>
                  <div className="px-2 py-1.5 bg-zinc-900">
                    <p className="text-white text-xs font-medium truncate">@{v.source_account}</p>
                    <p className="text-zinc-600 text-[10px] truncate">{v.shortcode}</p>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    )
  }

  // ─── Editor view (video selected) ───
  return (
    <div className="h-screen overflow-auto p-6">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <button
          onClick={() => setVideo(null)}
          className="flex items-center gap-1.5 text-sm text-zinc-400 hover:text-white transition-colors"
        >
          <ArrowLeft size={14} /> Videos
        </button>
        <div className="flex items-center gap-3">
          <span className="text-xs text-white font-medium">@{selectedVideo?.source_account}</span>
          <span className="text-[10px] text-zinc-500 font-mono">{selectedVideo?.shortcode}</span>
        </div>
        <button
          onClick={handleSave}
          disabled={!isDirty || !sessionId}
          className={`flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-medium transition-all ${
            saved
              ? 'bg-green-600/20 text-green-400'
              : isDirty
                ? 'bg-violet-600 hover:bg-violet-500 text-white'
                : 'bg-zinc-800 text-zinc-500'
          }`}
        >
          {saved ? <><Check size={12} /> Saved</> : <><Save size={12} /> Save</>}
        </button>
      </div>

      {/* Canvas + Controls side by side */}
      <div className="flex gap-6">
        {/* Canvas */}
        <div ref={containerRef} className="flex-1 flex justify-center min-w-0">
          {canvasSize.w > 0 && canvasSize.h > 0 && (
            <EditorCanvas
              width={canvasSize.w}
              height={canvasSize.h}
              videoId={videoId}
              templateId={templateId}
              frameTimestamp={frameTimestamp}
              videoBox={videoBox}
              cropBox={cropBox}
              captionBox={captionBox}
              captionText={captionText}
              captionColor={captionColor}
            />
          )}
        </div>

        {/* Controls */}
        <div className="w-64 shrink-0 space-y-3">
          {/* Template Selector */}
          <section>
            <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1.5 flex items-center gap-1.5">
              <Layers size={11} /> Template
            </h3>
            {templates.length > 0 ? (
              <div className="grid grid-cols-4 gap-1.5">
                <button
                  onClick={() => setTemplate(null)}
                  className={`aspect-[9/16] rounded-lg border flex items-center justify-center transition-all ${
                    !templateId
                      ? 'border-violet-500 bg-violet-500/10'
                      : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                  }`}
                >
                  <span className="text-[9px] text-zinc-500">None</span>
                </button>
                {templates.map(t => {
                  const isDefault = activeProfile?.default_template_id === t.id
                  return (
                    <button
                      key={t.id}
                      onClick={() => setTemplate(t.id)}
                      className={`relative aspect-[9/16] rounded-lg border overflow-hidden transition-all ${
                        t.id === templateId
                          ? 'border-violet-500 ring-1 ring-violet-500/30'
                          : 'border-zinc-700 hover:border-zinc-600'
                      }`}
                    >
                      <img
                        src={templateImageUrl(t.id)}
                        alt={t.name}
                        className="w-full h-full object-cover"
                        onError={e => (e.currentTarget.style.display = 'none')}
                      />
                      {isDefault && (
                        <div className="absolute top-0.5 right-0.5">
                          <Star size={10} className="text-amber-400 fill-amber-400" />
                        </div>
                      )}
                    </button>
                  )
                })}
              </div>
            ) : (
              <p className="text-zinc-600 text-xs">No templates yet.</p>
            )}
            {selectedTemplate && (
              <div className="flex items-center justify-between mt-1">
                <p className="text-zinc-400 text-xs">{selectedTemplate.name}</p>
                {activeProfileId && (
                  <button
                    onClick={() => handleSetDefaultTemplate(
                      activeProfile?.default_template_id === templateId ? null : templateId
                    )}
                    className="flex items-center gap-1 text-[10px] text-zinc-500 hover:text-amber-400 transition-colors"
                  >
                    <Star
                      size={10}
                      className={activeProfile?.default_template_id === templateId ? 'text-amber-400 fill-amber-400' : ''}
                    />
                    {activeProfile?.default_template_id === templateId ? 'Default' : 'Set default'}
                  </button>
                )}
              </div>
            )}
          </section>

          {/* Frame Timestamp */}
          <section>
            <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1 flex items-center gap-1.5">
              <Sliders size={11} /> Video Frame
            </h3>
            <input
              type="range"
              min={0}
              max={selectedVideo?.duration_sec ?? 30}
              step={0.5}
              value={frameTimestamp}
              onChange={e => setFrameTimestamp(Number(e.target.value))}
              className="w-full accent-violet-500"
            />
            <p className="text-zinc-500 text-[10px]">{frameTimestamp.toFixed(1)}s</p>
          </section>

          {/* Auto-Crop */}
          <section>
            <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1.5 flex items-center gap-1.5">
              <Crop size={11} /> Crop
            </h3>
            <button
              onClick={() => cropMut.mutate()}
              disabled={cropMut.isPending}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-xs text-zinc-300 transition-colors disabled:opacity-50"
            >
              {cropMut.isPending ? (
                <><Loader2 size={12} className="animate-spin" /> Analyzing...</>
              ) : (
                <><Wand2 size={12} /> Auto-Crop</>
              )}
            </button>
            <div className="mt-1.5 grid grid-cols-4 gap-1">
              {(['x1', 'y1', 'x2', 'y2'] as const).map((label, i) => (
                <div key={label} className="text-center">
                  <p className="text-[9px] text-zinc-600 uppercase">{label}</p>
                  <p className="text-[10px] text-zinc-400 font-mono">{cropBox[i].toFixed(2)}</p>
                </div>
              ))}
            </div>
            {cropMut.isError && (
              <p className="text-red-400 text-[10px] mt-1">Auto-crop failed.</p>
            )}
          </section>

          {/* AI Caption Generate */}
          {videoId && activeProfileId && (
            <section>
              <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1.5 flex items-center gap-1.5">
                <Sparkles size={11} /> AI Captions
              </h3>
              <div className="flex gap-1.5 mb-1.5">
                <button
                  onClick={() => aiCaptionMut.mutate()}
                  disabled={aiCaptionMut.isPending}
                  className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-[10px] text-zinc-300 transition-colors disabled:opacity-50"
                >
                  {aiCaptionMut.isPending ? (
                    <><Loader2 size={11} className="animate-spin" /> Watching...</>
                  ) : (
                    <><Wand2 size={11} /> Auto (Watch)</>
                  )}
                </button>
                <button
                  onClick={() => setShowDescribe(!showDescribe)}
                  className={`flex-1 flex items-center justify-center gap-1 px-2 py-1.5 border rounded-lg text-[10px] transition-colors ${
                    showDescribe
                      ? 'bg-violet-500/10 border-violet-500/50 text-violet-300'
                      : 'bg-zinc-800 hover:bg-zinc-700 border-zinc-700 text-zinc-300'
                  }`}
                >
                  <Type size={11} /> Describe
                </button>
              </div>
              {showDescribe && (
                <div className="space-y-1.5">
                  <textarea
                    value={describeInput}
                    onChange={e => setDescribeInput(e.target.value)}
                    placeholder="Describe what happens..."
                    rows={2}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-xs resize-none"
                  />
                  <button
                    onClick={() => describeMut.mutate(describeInput)}
                    disabled={!describeInput.trim() || describeMut.isPending}
                    className="w-full flex items-center justify-center gap-1 px-2 py-1.5 bg-violet-600 hover:bg-violet-500 text-white rounded-lg text-[10px] font-medium transition-colors disabled:opacity-50"
                  >
                    {describeMut.isPending ? (
                      <><Loader2 size={11} className="animate-spin" /> Generating...</>
                    ) : (
                      'Generate Post Caption'
                    )}
                  </button>
                </div>
              )}
              {(aiCaptionMut.isError || describeMut.isError) && (
                <p className="text-red-400 text-[10px] mt-1">Caption generation failed.</p>
              )}
            </section>
          )}

          {/* Overlay Text (rendered inside the video) */}
          <section>
            <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1.5 flex items-center gap-1.5">
              <Type size={11} /> Overlay Text
            </h3>
            <textarea
              value={captionText}
              onChange={e => setCaptionText(e.target.value)}
              placeholder="Text rendered on the video..."
              rows={2}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-xs resize-none"
            />
            <div className="flex items-center gap-2 mt-1.5">
              <label className="text-[10px] text-zinc-600">Color</label>
              <input
                type="color"
                value={captionColor}
                onChange={e => setCaptionColor(e.target.value)}
                className="w-5 h-5 rounded border border-zinc-700 cursor-pointer bg-transparent"
              />
              <span className="text-[10px] text-zinc-500 font-mono">{captionColor}</span>
            </div>
          </section>

          {/* Post Caption (Instagram caption) */}
          <section>
            <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1.5 flex items-center gap-1.5">
              <MessageSquare size={11} /> Post Caption
            </h3>
            <textarea
              value={postCaption}
              onChange={e => setPostCaption(e.target.value)}
              placeholder="Instagram caption for the post..."
              rows={3}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-xs resize-none"
            />
          </section>

          {/* Render */}
          {sessionId && (
            <section>
              <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1.5 flex items-center gap-1.5">
                <Play size={11} /> Render
              </h3>

              <div className="flex gap-1 mb-2">
                {['Native 1920', 'Medium 1280p', 'Fast 960p'].map(q => (
                  <button
                    key={q}
                    onClick={() => setRenderQuality(q)}
                    className={`flex-1 px-1 py-1 rounded-md text-[10px] font-medium transition-all ${
                      renderQuality === q
                        ? 'bg-violet-600 text-white'
                        : 'bg-zinc-800 text-zinc-400 hover:bg-zinc-700'
                    }`}
                  >
                    {q.split(' ')[0]}
                  </button>
                ))}
              </div>

              <div className="flex gap-1.5 mb-2">
                <button
                  onClick={() => setIncludeAudio(!includeAudio)}
                  className={`flex-1 flex items-center justify-center gap-1.5 px-2 py-1.5 rounded-lg border text-xs transition-all ${
                    includeAudio
                      ? 'border-violet-500/50 bg-violet-500/10 text-violet-300'
                      : 'border-zinc-700 bg-zinc-800 text-zinc-400'
                  }`}
                >
                  {includeAudio ? <Volume2 size={11} /> : <VolumeX size={11} />}
                  {includeAudio ? 'Audio' : 'Muted'}
                </button>
                <button
                  onClick={handleRender}
                  disabled={renderState === 'rendering'}
                  className={`flex-[2] flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                    renderState === 'rendering'
                      ? 'bg-violet-600/50 text-violet-300 cursor-wait'
                      : 'bg-violet-600 hover:bg-violet-500 text-white'
                  }`}
                >
                  {renderState === 'rendering' ? (
                    <><Loader2 size={12} className="animate-spin" /> {renderProgress}%</>
                  ) : (
                    <><Play size={12} /> Render</>
                  )}
                </button>
              </div>

              {renderState === 'rendering' && (
                <div className="w-full h-1 bg-zinc-800 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-violet-500 transition-all duration-500 rounded-full"
                    style={{ width: `${renderProgress}%` }}
                  />
                </div>
              )}

              {renderState === 'failed' && renderError && (
                <p className="text-red-400 text-[10px] mt-1">{renderError}</p>
              )}

              {renderState === 'complete' && renderJobId && (
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5 text-green-400 text-xs">
                    <CheckCircle size={12} /> Complete
                  </div>
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => setShowPreview(true)}
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-violet-600/20 hover:bg-violet-600/30 border border-violet-500/40 rounded-lg text-[10px] text-violet-300 transition-colors"
                    >
                      <Eye size={11} /> Preview
                    </button>
                    <a
                      href={renderDownloadUrl(renderJobId)}
                      download
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-[10px] text-zinc-300 transition-colors"
                    >
                      <Download size={11} /> Download
                    </a>
                    <button
                      onClick={handleExport}
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-green-600/20 hover:bg-green-600/30 border border-green-600/40 rounded-lg text-[10px] text-green-400 transition-colors"
                    >
                      <Check size={11} /> Ready
                    </button>
                  </div>
                </div>
              )}
            </section>
          )}
        </div>
      </div>

      {/* Video Preview Modal */}
      {showPreview && renderJobId && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm"
          onClick={() => setShowPreview(false)}
        >
          <div
            className="relative max-h-[90vh] max-w-[50vh] w-full"
            onClick={e => e.stopPropagation()}
          >
            <button
              onClick={() => setShowPreview(false)}
              className="absolute -top-10 right-0 text-zinc-400 hover:text-white transition-colors"
            >
              <X size={20} />
            </button>
            <video
              src={renderDownloadUrl(renderJobId)}
              controls
              autoPlay
              className="w-full h-full rounded-xl shadow-2xl"
              style={{ maxHeight: '90vh' }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
