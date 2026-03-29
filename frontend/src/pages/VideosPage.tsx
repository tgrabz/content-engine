import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  fetchVideos, deleteVideo, updateVideo, thumbnailUrl, editedThumbnailUrl,
  streamUrl, editedStreamUrl, fetchSourceAccounts, type Video, type VideoFilters,
} from '../api/videos'
import { createPost } from '../api/posts'
import { fetchNiches } from '../api/niches'
import { fetchProfiles } from '../api/profiles'
import { useAppStore } from '../stores/appStore'
import {
  Film, Search, Trash2, X, ExternalLink, Clock, Eye, HardDrive,
  ChevronDown, Scissors, ListPlus,
} from 'lucide-react'

const STATUS_COLORS: Record<string, string> = {
  downloaded: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  editing: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  ready: 'bg-green-500/20 text-green-300 border-green-500/30',
  queued: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  posting: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  posted: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30',
}

const ALL_STATUSES = ['downloaded', 'editing', 'ready', 'queued', 'posting', 'posted']

function formatViews(views: number | null) {
  if (views === null) return '---'
  if (views >= 1_000_000) return `${(views / 1_000_000).toFixed(1)}M`
  if (views >= 1_000) return `${(views / 1_000).toFixed(1)}K`
  return views.toLocaleString()
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function formatDuration(sec: number | null) {
  if (sec === null) return '--:--'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${s.toString().padStart(2, '0')}`
}

function timeAgo(dateStr: string) {
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export default function VideosPage() {
  const qc = useQueryClient()
  const navigate = useNavigate()
  const { data: niches = [] } = useQuery({ queryKey: ['niches'], queryFn: fetchNiches })
  const { data: profilesRaw } = useQuery({ queryKey: ['profiles'], queryFn: fetchProfiles })
  const profiles = Array.isArray(profilesRaw) ? profilesRaw : []

  const activeProfileId = useAppStore(s => s.activeProfileId)
  const activeProfile = profiles.find(p => p.id === activeProfileId)

  // Filters — default sort by status priority so "ready" videos appear first
  const [filters, setFilters] = useState<VideoFilters>(() => ({
    limit: 50,
    sort: 'status_priority',
    niche_id: activeProfile?.niche_id ?? undefined,
  }))
  const [searchInput, setSearchInput] = useState('')

  // When active profile changes, update niche filter
  useEffect(() => {
    setFilters(f => ({
      ...f,
      niche_id: activeProfile?.niche_id ?? undefined,
      offset: 0,
    }))
  }, [activeProfile?.niche_id])

  const { data: accounts = [] } = useQuery({
    queryKey: ['video-accounts', filters.niche_id],
    queryFn: () => fetchSourceAccounts(filters.niche_id),
  })
  const { data: videos = [], isLoading } = useQuery({
    queryKey: ['videos', filters],
    queryFn: () => fetchVideos(filters),
  })

  // Selected video for detail panel
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const selected = videos.find(v => v.id === selectedId) ?? null

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteVideo(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['videos'] })
      setSelectedId(null)
    },
  })
  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { status?: string; caption?: string } }) =>
      updateVideo(id, data),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['videos'] }),
  })
  const queueMut = useMutation({
    mutationFn: (videoId: number) => {
      if (!activeProfileId) throw new Error('Select a profile first')
      return createPost({ video_id: videoId, profile_id: activeProfileId })
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['videos'] })
      qc.invalidateQueries({ queryKey: ['posts'] })
    },
  })

  const handleSearch = () => {
    setFilters(f => ({ ...f, search: searchInput || undefined, offset: 0 }))
  }

  return (
    <div className="flex h-screen">
      {/* Main content area */}
      <div className="flex-1 overflow-auto p-8">
        <div className="max-w-6xl space-y-5">
          {/* Header */}
          <div>
            <h2 className="text-2xl font-bold text-white mb-1">Video Library</h2>
            <p className="text-zinc-400 text-sm">
              {videos.length} video{videos.length !== 1 ? 's' : ''}
              {filters.niche_id || filters.status || filters.source_account
                ? ' (filtered)'
                : ''}
            </p>
          </div>

          {/* Profile context banner */}
          {activeProfile ? (
            <div className="flex items-center gap-2 px-3 py-2 bg-violet-500/10 border border-violet-500/20 rounded-lg">
              <span className="text-violet-300 text-xs font-medium">
                Showing videos for: {activeProfile.name}
              </span>
              {activeProfile.niche_id && (
                <span className="text-violet-400/60 text-xs">
                  ({niches.find(n => n.id === activeProfile.niche_id)?.name})
                </span>
              )}
            </div>
          ) : (
            <div className="px-3 py-2 bg-amber-500/10 border border-amber-500/30 rounded-lg">
              <p className="text-amber-300 text-xs">Select a profile in the sidebar to filter videos by niche.</p>
            </div>
          )}

          {/* Filters Bar */}
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative">
              <select
                value={filters.niche_id ?? ''}
                onChange={e => setFilters(f => ({
                  ...f,
                  niche_id: e.target.value ? Number(e.target.value) : undefined,
                  source_account: undefined,
                  offset: 0,
                }))}
                className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-white appearance-none pr-8 cursor-pointer"
              >
                <option value="">All Niches</option>
                {niches.map(n => (
                  <option key={n.id} value={n.id}>{n.name}</option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
            </div>

            <div className="relative">
              <select
                value={filters.status ?? ''}
                onChange={e => setFilters(f => ({ ...f, status: e.target.value || undefined, offset: 0 }))}
                className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-white appearance-none pr-8 cursor-pointer"
              >
                <option value="">All Statuses</option>
                {ALL_STATUSES.map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
            </div>

            {accounts.length > 0 && (
              <div className="relative">
                <select
                  value={filters.source_account ?? ''}
                  onChange={e => setFilters(f => ({ ...f, source_account: e.target.value || undefined, offset: 0 }))}
                  className="bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-white appearance-none pr-8 cursor-pointer"
                >
                  <option value="">All Accounts</option>
                  {accounts.map(a => (
                    <option key={a} value={a}>@{a}</option>
                  ))}
                </select>
                <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
              </div>
            )}

            <div className="flex-1 min-w-[200px]">
              <div className="relative">
                <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" />
                <input
                  value={searchInput}
                  onChange={e => setSearchInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && handleSearch()}
                  placeholder="Search shortcode, account, caption..."
                  className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-9 pr-3 py-1.5 text-sm text-white"
                />
              </div>
            </div>

            {(filters.niche_id || filters.status || filters.source_account || filters.search) && (
              <button
                onClick={() => {
                  setFilters({
                    limit: 50,
                    sort: 'status_priority',
                    niche_id: activeProfile?.niche_id ?? undefined,
                  })
                  setSearchInput('')
                }}
                className="text-xs text-zinc-500 hover:text-white"
              >
                Clear filters
              </button>
            )}
          </div>

          {/* Video Grid */}
          {isLoading ? (
            <div className="text-center py-20 text-zinc-600 text-sm">Loading videos...</div>
          ) : videos.length === 0 ? (
            <div className="text-center py-20 text-zinc-600">
              <Film size={40} className="mx-auto mb-3 opacity-30" />
              <p className="text-sm">No videos found.</p>
              <p className="text-xs mt-1">Scrape some reels to populate your library.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
              {videos.map(v => (
                <VideoCard
                  key={v.id}
                  video={v}
                  isSelected={v.id === selectedId}
                  onClick={() => setSelectedId(v.id === selectedId ? null : v.id)}
                />
              ))}
            </div>
          )}

          {/* Load more */}
          {videos.length >= (filters.limit ?? 50) && (
            <div className="text-center pt-2">
              <button
                onClick={() => setFilters(f => ({ ...f, limit: (f.limit ?? 50) + 50 }))}
                className="text-xs text-violet-400 hover:text-violet-300"
              >
                Load more...
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Detail Panel (slide-in from right) */}
      {selected && (
        <div className="w-96 border-l border-zinc-800 bg-zinc-900 flex flex-col h-screen overflow-auto">
          {/* Video Player — prefer edited version */}
          <div className="relative bg-black aspect-[9/16] max-h-[50vh] flex-shrink-0">
            <video
              key={`${selected.id}-${selected.exported_path ?? 'orig'}`}
              src={selected.exported_path ? editedStreamUrl(selected.id) : streamUrl(selected.id)}
              controls
              className="w-full h-full object-contain"
              preload="metadata"
            />
            <button
              onClick={() => setSelectedId(null)}
              className="absolute top-2 right-2 p-1 bg-black/60 rounded-full text-white hover:bg-black/80"
            >
              <X size={16} />
            </button>
          </div>

          {/* Details */}
          <div className="p-4 space-y-4 flex-1">
            <div className="flex items-center justify-between">
              <span className="text-white font-medium text-sm">@{selected.source_account}</span>
              <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full border ${STATUS_COLORS[selected.status] ?? 'bg-zinc-700 text-zinc-300 border-zinc-600'}`}>
                {selected.status}
              </span>
            </div>

            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="bg-zinc-800/50 rounded-lg py-2">
                <Eye size={12} className="mx-auto text-zinc-500 mb-1" />
                <p className="text-white text-sm font-medium">{formatViews(selected.views)}</p>
                <p className="text-zinc-600 text-[10px]">views</p>
              </div>
              <div className="bg-zinc-800/50 rounded-lg py-2">
                <Clock size={12} className="mx-auto text-zinc-500 mb-1" />
                <p className="text-white text-sm font-medium">{formatDuration(selected.duration_sec)}</p>
                <p className="text-zinc-600 text-[10px]">duration</p>
              </div>
              <div className="bg-zinc-800/50 rounded-lg py-2">
                <HardDrive size={12} className="mx-auto text-zinc-500 mb-1" />
                <p className="text-white text-sm font-medium">{formatBytes(selected.file_bytes)}</p>
                <p className="text-zinc-600 text-[10px]">size</p>
              </div>
            </div>

            {selected.caption && (
              <div>
                <label className="text-[10px] text-zinc-600 uppercase tracking-wider">Caption</label>
                <p className="text-zinc-400 text-xs mt-1 leading-relaxed">{selected.caption}</p>
              </div>
            )}

            <div>
              <label className="text-[10px] text-zinc-600 uppercase tracking-wider">Details</label>
              <div className="mt-1 space-y-1 text-xs">
                <div className="flex justify-between">
                  <span className="text-zinc-500">Shortcode</span>
                  <span className="text-zinc-300 font-mono">{selected.shortcode}</span>
                </div>
                {selected.width && selected.height && (
                  <div className="flex justify-between">
                    <span className="text-zinc-500">Resolution</span>
                    <span className="text-zinc-300">{selected.width}x{selected.height}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-zinc-500">Scraped</span>
                  <span className="text-zinc-300">{timeAgo(selected.scraped_at)}</span>
                </div>
              </div>
            </div>

            {/* Status changer */}
            <div>
              <label className="text-[10px] text-zinc-600 uppercase tracking-wider">Change Status</label>
              <div className="flex flex-wrap gap-1.5 mt-1.5">
                {ALL_STATUSES.map(s => (
                  <button
                    key={s}
                    onClick={() => updateMut.mutate({ id: selected.id, data: { status: s } })}
                    disabled={selected.status === s}
                    className={`text-[10px] px-2 py-0.5 rounded-full border transition-colors ${
                      selected.status === s
                        ? STATUS_COLORS[s]
                        : 'bg-zinc-800 text-zinc-500 border-zinc-700 hover:text-zinc-300'
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            {/* Quick actions */}
            <div className="space-y-2 pt-2">
              <div className="flex gap-2">
                {(selected.status === 'downloaded' || selected.status === 'editing') && (
                  <button
                    onClick={() => navigate(`/editor?video=${selected.id}`)}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 bg-violet-600 hover:bg-violet-500 text-white rounded-lg text-xs font-medium"
                  >
                    <Scissors size={12} /> Edit
                  </button>
                )}
                {selected.status === 'ready' && activeProfileId && (
                  <button
                    onClick={() => queueMut.mutate(selected.id)}
                    disabled={queueMut.isPending}
                    className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 bg-green-600 hover:bg-green-500 text-white rounded-lg text-xs font-medium disabled:opacity-50"
                  >
                    <ListPlus size={12} /> Add to Queue
                  </button>
                )}
              </div>
              <div className="flex gap-2">
                <a
                  href={selected.source_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 text-zinc-300 rounded-lg text-xs"
                >
                  <ExternalLink size={12} /> View on IG
                </a>
                <button
                  onClick={() => deleteMut.mutate(selected.id)}
                  className="flex items-center justify-center gap-1.5 px-3 py-1.5 bg-red-500/10 hover:bg-red-500/20 text-red-400 rounded-lg text-xs border border-red-500/20"
                >
                  <Trash2 size={12} /> Delete
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function VideoCard({ video, isSelected, onClick }: {
  video: Video
  isSelected: boolean
  onClick: () => void
}) {
  const [thumbError, setThumbError] = useState(false)

  return (
    <button
      onClick={onClick}
      className={`group text-left rounded-xl overflow-hidden border transition-all ${
        isSelected
          ? 'border-violet-500 ring-1 ring-violet-500/30'
          : 'border-zinc-800 hover:border-zinc-700'
      }`}
    >
      {/* Thumbnail — prefer edited version */}
      <div className="relative aspect-[9/16] bg-zinc-800">
        {!thumbError ? (
          <img
            src={video.exported_path ? editedThumbnailUrl(video.id) : thumbnailUrl(video.id)}
            alt=""
            loading="lazy"
            onError={() => setThumbError(true)}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center">
            <Film size={24} className="text-zinc-700" />
          </div>
        )}

        {/* Views badge */}
        {video.views !== null && (
          <span className="absolute top-1.5 left-1.5 bg-black/70 text-white text-[10px] px-1.5 py-0.5 rounded-md font-medium">
            {formatViews(video.views)}
          </span>
        )}

        {/* Duration badge */}
        {video.duration_sec !== null && (
          <span className="absolute bottom-1.5 right-1.5 bg-black/70 text-white text-[10px] px-1.5 py-0.5 rounded-md font-mono">
            {formatDuration(video.duration_sec)}
          </span>
        )}

        {/* Edited indicator */}
        {video.exported_path && (
          <span className="absolute bottom-1.5 left-1.5 bg-green-500/80 text-white text-[8px] px-1 py-0.5 rounded-md font-bold uppercase">
            Edited
          </span>
        )}

        {/* Status badge */}
        <span className={`absolute top-1.5 right-1.5 text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded-md border ${STATUS_COLORS[video.status] ?? 'bg-zinc-700 text-zinc-300 border-zinc-600'}`}>
          {video.status}
        </span>
      </div>

      {/* Info */}
      <div className="px-2 py-1.5 bg-zinc-900">
        <p className="text-white text-xs font-medium truncate">@{video.source_account}</p>
        <p className="text-zinc-600 text-[10px] truncate">{video.shortcode}</p>
      </div>
    </button>
  )
}
