import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchPosts, createPost, updatePost, deletePost, publishPost, type Post } from '../api/posts'
import { fetchVideos, thumbnailUrl, profileThumbnailUrl, profileStreamUrl, type Video } from '../api/videos'
import { getOAuthUrl, getProfileToken, deleteProfileToken } from '../api/auth'
import { generateCaption, describeCaption } from '../api/editor'
import { useAppStore } from '../stores/appStore'
import {
  Send, Plus, Trash2, ExternalLink, Loader2, CheckCircle,
  Upload, Link2, Unlink, ChevronRight, Clock, XCircle, Wand2, PenLine,
} from 'lucide-react'

const STATUS_COLORS: Record<string, { bg: string; text: string; icon: React.ReactNode }> = {
  queued: { bg: 'bg-zinc-700/30', text: 'text-zinc-300', icon: <Clock size={11} /> },
  uploading: { bg: 'bg-blue-500/20', text: 'text-blue-400', icon: <Upload size={11} /> },
  processing: { bg: 'bg-amber-500/20', text: 'text-amber-400', icon: <Loader2 size={11} className="animate-spin" /> },
  published: { bg: 'bg-green-500/20', text: 'text-green-400', icon: <CheckCircle size={11} /> },
  failed: { bg: 'bg-red-500/20', text: 'text-red-400', icon: <XCircle size={11} /> },
}

function StatusBadge({ status }: { status: string }) {
  const s = STATUS_COLORS[status] || STATUS_COLORS.queued
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${s.bg} ${s.text}`}>
      {s.icon} {status}
    </span>
  )
}

export default function PostsPage() {
  const queryClient = useQueryClient()
  const activeProfileId = useAppStore(s => s.activeProfileId)

  // Posts data
  const { data: posts = [] } = useQuery({
    queryKey: ['posts', { profile_id: activeProfileId }],
    queryFn: () => fetchPosts(activeProfileId ? { profile_id: activeProfileId } : undefined),
  })

  // Videos available for posting (status: ready or exported)
  const { data: videos = [] } = useQuery({
    queryKey: ['videos', { limit: 200 }],
    queryFn: () => fetchVideos({ limit: 200 }),
  })
  const readyVideos = videos.filter(v =>
    v.status === 'ready' || v.exported_path
  )

  // OAuth token for active profile
  const { data: oauthToken, refetch: refetchToken } = useQuery({
    queryKey: ['oauth-token', activeProfileId],
    queryFn: () => activeProfileId ? getProfileToken(activeProfileId) : Promise.resolve(null),
    enabled: !!activeProfileId,
  })

  // Add to queue state
  const [showAddPanel, setShowAddPanel] = useState(false)
  const [selectedVideoId, setSelectedVideoId] = useState<number | null>(null)
  const [caption, setCaption] = useState('')
  const [shareToFeed, setShareToFeed] = useState(true)

  // Selected post for detail
  const [selectedPostId, setSelectedPostId] = useState<number | null>(null)
  const selectedPost = posts.find(p => p.id === selectedPostId)

  // Mutations
  const addMut = useMutation({
    mutationFn: () => {
      if (!selectedVideoId || !activeProfileId) throw new Error('Select video and profile')
      return createPost({
        video_id: selectedVideoId,
        profile_id: activeProfileId,
        caption,
        share_to_feed: shareToFeed,
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['posts'] })
      queryClient.invalidateQueries({ queryKey: ['videos'] })
      setShowAddPanel(false)
      setSelectedVideoId(null)
      setCaption('')
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => deletePost(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['posts'] })
      queryClient.invalidateQueries({ queryKey: ['videos'] })
      if (selectedPostId === deleteMut.variables) setSelectedPostId(null)
    },
  })

  const publishMut = useMutation({
    mutationFn: (id: number) => publishPost(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['posts'] })
      queryClient.invalidateQueries({ queryKey: ['videos'] })
    },
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { caption?: string } }) =>
      updatePost(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['posts'] }),
  })

  // AI caption mutations
  const [describeText, setDescribeText] = useState('')
  const [showDescribeInput, setShowDescribeInput] = useState(false)

  const autoCaptionMut = useMutation({
    mutationFn: (postId: number) => {
      const post = posts.find(p => p.id === postId)
      if (!post) throw new Error('Post not found')
      return generateCaption(post.video_id, post.profile_id)
    },
    onSuccess: (data, postId) => {
      updateMut.mutate({ id: postId, data: { caption: data.caption } })
    },
  })

  const describeCaptionMut = useMutation({
    mutationFn: (description: string) => describeCaption(description),
    onSuccess: (data) => {
      if (selectedPostId) {
        updateMut.mutate({ id: selectedPostId, data: { caption: data.caption } })
      }
      setShowDescribeInput(false)
      setDescribeText('')
    },
  })

  const disconnectMut = useMutation({
    mutationFn: () => {
      if (!activeProfileId) throw new Error('No profile')
      return deleteProfileToken(activeProfileId)
    },
    onSuccess: () => refetchToken(),
  })

  const handleConnect = async () => {
    try {
      const { auth_url } = await getOAuthUrl()
      window.open(auth_url, '_blank', 'width=600,height=700')
    } catch {
      alert('Failed to generate OAuth URL. Check App ID/Secret in .env')
    }
  }

  // Find video info for a post
  const videoForPost = (post: Post) => videos.find(v => v.id === post.video_id)

  const queuedPosts = posts.filter(p => p.status === 'queued')
  const activePosts = posts.filter(p => ['uploading', 'processing'].includes(p.status))
  const completedPosts = posts.filter(p => ['published', 'failed'].includes(p.status))

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Main content */}
      <div className="flex-1 overflow-auto">
        <div className="p-8 max-w-4xl">
          {/* Header */}
          <div className="flex items-center justify-between mb-6">
            <div>
              <h2 className="text-2xl font-bold text-white">Post Scheduler</h2>
              <p className="text-zinc-500 text-sm mt-1">Queue and publish reels to Instagram</p>
            </div>
            <div className="flex items-center gap-2">
              {activeProfileId && (
                <button
                  onClick={() => setShowAddPanel(true)}
                  className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  <Plus size={16} /> Add to Queue
                </button>
              )}
            </div>
          </div>

          {/* No profile warning */}
          {!activeProfileId && (
            <div className="px-4 py-3 bg-amber-500/10 border border-amber-500/30 rounded-lg mb-6">
              <p className="text-amber-300 text-sm">Select a profile in the sidebar to manage your post queue.</p>
            </div>
          )}

          {/* OAuth Status */}
          {activeProfileId && (
            <div className="mb-6 p-4 bg-zinc-900 border border-zinc-800 rounded-xl">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-2.5 h-2.5 rounded-full ${oauthToken ? 'bg-green-500' : 'bg-zinc-600'}`} />
                  <div>
                    <p className="text-sm text-white font-medium">
                      {oauthToken ? 'Instagram Connected' : 'Instagram Not Connected'}
                    </p>
                    {oauthToken?.ig_user_id && (
                      <p className="text-xs text-zinc-500">IG User: {oauthToken.ig_user_id}</p>
                    )}
                  </div>
                </div>
                {oauthToken ? (
                  <button
                    onClick={() => disconnectMut.mutate()}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-xs text-zinc-300 transition-colors"
                  >
                    <Unlink size={12} /> Disconnect
                  </button>
                ) : (
                  <button
                    onClick={handleConnect}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-xs font-medium transition-colors"
                  >
                    <Link2 size={12} /> Connect with Facebook
                  </button>
                )}
              </div>
            </div>
          )}

          {/* Queue */}
          {queuedPosts.length > 0 && (
            <section className="mb-8">
              <h3 className="text-xs text-zinc-500 uppercase tracking-wider font-semibold mb-3">
                Queue ({queuedPosts.length})
              </h3>
              <div className="space-y-2">
                {queuedPosts.map(post => (
                  <PostRow
                    key={post.id}
                    post={post}
                    video={videoForPost(post)}
                    selected={selectedPostId === post.id}
                    onSelect={() => setSelectedPostId(post.id)}
                    onPublish={() => publishMut.mutate(post.id)}
                    onDelete={() => deleteMut.mutate(post.id)}
                    publishing={publishMut.isPending && publishMut.variables === post.id}
                    canPublish={!!oauthToken}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Active */}
          {activePosts.length > 0 && (
            <section className="mb-8">
              <h3 className="text-xs text-zinc-500 uppercase tracking-wider font-semibold mb-3">
                In Progress ({activePosts.length})
              </h3>
              <div className="space-y-2">
                {activePosts.map(post => (
                  <PostRow
                    key={post.id}
                    post={post}
                    video={videoForPost(post)}
                    selected={selectedPostId === post.id}
                    onSelect={() => setSelectedPostId(post.id)}
                  />
                ))}
              </div>
            </section>
          )}

          {/* History */}
          {completedPosts.length > 0 && (
            <section className="mb-8">
              <h3 className="text-xs text-zinc-500 uppercase tracking-wider font-semibold mb-3">
                History ({completedPosts.length})
              </h3>
              <div className="space-y-2">
                {completedPosts.map(post => (
                  <PostRow
                    key={post.id}
                    post={post}
                    video={videoForPost(post)}
                    selected={selectedPostId === post.id}
                    onSelect={() => setSelectedPostId(post.id)}
                    onDelete={() => deleteMut.mutate(post.id)}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Empty state */}
          {posts.length === 0 && activeProfileId && (
            <div className="text-center py-20">
              <Send size={48} className="mx-auto mb-4 text-zinc-700" />
              <p className="text-zinc-500 text-sm">No posts in queue. Add a video to get started.</p>
            </div>
          )}
        </div>
      </div>

      {/* Right sidebar: Add panel or detail panel */}
      {showAddPanel && activeProfileId && (
        <div className="w-80 border-l border-zinc-800 bg-zinc-900 flex flex-col h-full overflow-auto">
          <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
            <h3 className="text-sm font-bold text-white">Add to Queue</h3>
            <button onClick={() => setShowAddPanel(false)} className="text-zinc-500 hover:text-white">
              <XCircle size={16} />
            </button>
          </div>
          <div className="p-4 space-y-4">
            {/* Video selector */}
            <section>
              <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
                Select Video
              </label>
              <div className="mt-2 max-h-60 overflow-auto space-y-1.5">
                {readyVideos.length === 0 ? (
                  <p className="text-zinc-600 text-xs py-4 text-center">No ready videos. Edit and render a video first.</p>
                ) : (
                  readyVideos.map(v => (
                    <button
                      key={v.id}
                      onClick={() => setSelectedVideoId(v.id)}
                      className={`w-full flex items-center gap-2.5 p-2 rounded-lg border transition-all ${
                        selectedVideoId === v.id
                          ? 'border-violet-500 bg-violet-500/10'
                          : 'border-zinc-700 bg-zinc-800 hover:border-zinc-600'
                      }`}
                    >
                      <div className="w-8 h-14 rounded bg-zinc-700 overflow-hidden flex-shrink-0">
                        <img
                          src={activeProfileId ? profileThumbnailUrl(v.id, activeProfileId) : thumbnailUrl(v.id)}
                          alt=""
                          className="w-full h-full object-cover"
                          onError={e => (e.currentTarget.style.display = 'none')}
                        />
                      </div>
                      <div className="text-left min-w-0">
                        <p className="text-xs text-zinc-300 truncate">@{v.source_account}</p>
                        <p className="text-[10px] text-zinc-600 truncate">{v.shortcode}</p>
                      </div>
                    </button>
                  ))
                )}
              </div>
            </section>

            {/* Caption */}
            <section>
              <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
                Caption
              </label>
              <textarea
                value={caption}
                onChange={e => setCaption(e.target.value)}
                placeholder="Write your Instagram caption..."
                rows={4}
                className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-xs resize-none"
              />
              {/* AI Caption for Add panel */}
              {selectedVideoId && activeProfileId && (
                <div className="mt-2 flex gap-1.5">
                  <button
                    onClick={() => {
                      generateCaption(selectedVideoId, activeProfileId!).then(data => {
                        setCaption(data.caption)
                      })
                    }}
                    className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-[10px] text-zinc-300 transition-colors"
                  >
                    <Wand2 size={10} /> Auto (AI Watch)
                  </button>
                  <button
                    onClick={() => setShowDescribeInput(!showDescribeInput)}
                    className={`flex-1 flex items-center justify-center gap-1 px-2 py-1.5 border rounded-lg text-[10px] transition-colors ${
                      showDescribeInput
                        ? 'bg-violet-500/10 border-violet-500/50 text-violet-300'
                        : 'bg-zinc-800 hover:bg-zinc-700 border-zinc-700 text-zinc-300'
                    }`}
                  >
                    <PenLine size={10} /> Describe
                  </button>
                </div>
              )}
            </section>

            {/* Share to feed toggle */}
            <label className="flex items-center gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={shareToFeed}
                onChange={e => setShareToFeed(e.target.checked)}
                className="rounded border-zinc-600 bg-zinc-800 text-violet-500 focus:ring-violet-500"
              />
              <span className="text-xs text-zinc-300">Share to feed</span>
            </label>

            {/* Error */}
            {addMut.isError && (
              <p className="text-red-400 text-xs">Failed to add to queue.</p>
            )}

            {/* Add button */}
            <button
              onClick={() => addMut.mutate()}
              disabled={!selectedVideoId || addMut.isPending}
              className="w-full flex items-center justify-center gap-1.5 px-3 py-2.5 bg-violet-600 hover:bg-violet-500 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
            >
              {addMut.isPending ? (
                <><Loader2 size={13} className="animate-spin" /> Adding...</>
              ) : (
                <><Plus size={13} /> Add to Queue</>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Detail panel */}
      {selectedPost && !showAddPanel && (
        <div className="w-80 border-l border-zinc-800 bg-zinc-900 flex flex-col h-full overflow-auto">
          <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
            <h3 className="text-sm font-bold text-white">Post Details</h3>
            <button onClick={() => setSelectedPostId(null)} className="text-zinc-500 hover:text-white">
              <XCircle size={16} />
            </button>
          </div>
          <div className="p-4 space-y-4">
            {/* Thumbnail — prefer edited version */}
            <div className="aspect-[9/16] bg-zinc-800 rounded-lg overflow-hidden">
              {(() => {
                const _v = videoForPost(selectedPost)
                return (
                  <img
                    src={profileThumbnailUrl(selectedPost.video_id, selectedPost.profile_id)}
                    alt=""
                    className="w-full h-full object-cover"
                    onError={e => (e.currentTarget.style.display = 'none')}
                  />
                )
              })()}
            </div>

            <StatusBadge status={selectedPost.status} />

            {/* Caption (editable for queued) */}
            {selectedPost.status === 'queued' ? (
              <div>
                <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">Caption</label>
                <textarea
                  key={`${selectedPost.id}-${selectedPost.caption}`}
                  defaultValue={selectedPost.caption}
                  onBlur={e => {
                    if (e.target.value !== selectedPost.caption) {
                      updateMut.mutate({ id: selectedPost.id, data: { caption: e.target.value } })
                    }
                  }}
                  rows={5}
                  className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-xs resize-none"
                />

                {/* AI Caption buttons */}
                <div className="mt-2 space-y-1.5">
                  <div className="flex gap-1.5">
                    <button
                      onClick={() => autoCaptionMut.mutate(selectedPost.id)}
                      disabled={autoCaptionMut.isPending}
                      className="flex-1 flex items-center justify-center gap-1 px-2 py-1.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-[10px] text-zinc-300 transition-colors disabled:opacity-50"
                    >
                      {autoCaptionMut.isPending ? (
                        <><Loader2 size={10} className="animate-spin" /> Watching...</>
                      ) : (
                        <><Wand2 size={10} /> Auto (AI Watch)</>
                      )}
                    </button>
                    <button
                      onClick={() => setShowDescribeInput(!showDescribeInput)}
                      className={`flex-1 flex items-center justify-center gap-1 px-2 py-1.5 border rounded-lg text-[10px] transition-colors ${
                        showDescribeInput
                          ? 'bg-violet-500/10 border-violet-500/50 text-violet-300'
                          : 'bg-zinc-800 hover:bg-zinc-700 border-zinc-700 text-zinc-300'
                      }`}
                    >
                      <PenLine size={10} /> Describe
                    </button>
                  </div>

                  {showDescribeInput && (
                    <div className="space-y-1.5">
                      <textarea
                        value={describeText}
                        onChange={e => setDescribeText(e.target.value)}
                        placeholder="Describe what happens in the video..."
                        rows={2}
                        className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-xs resize-none"
                      />
                      <button
                        onClick={() => describeCaptionMut.mutate(describeText)}
                        disabled={!describeText.trim() || describeCaptionMut.isPending}
                        className="w-full flex items-center justify-center gap-1 px-2 py-1.5 bg-violet-600 hover:bg-violet-500 text-white rounded-lg text-[10px] font-medium transition-colors disabled:opacity-50"
                      >
                        {describeCaptionMut.isPending ? (
                          <><Loader2 size={10} className="animate-spin" /> Generating...</>
                        ) : (
                          <><Wand2 size={10} /> Generate Caption</>
                        )}
                      </button>
                    </div>
                  )}

                  {(autoCaptionMut.isError || describeCaptionMut.isError) && (
                    <p className="text-red-400 text-[10px]">Caption generation failed.</p>
                  )}
                </div>
              </div>
            ) : selectedPost.caption ? (
              <div>
                <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">Caption</label>
                <p className="text-xs text-zinc-300 mt-1 whitespace-pre-wrap">{selectedPost.caption}</p>
              </div>
            ) : null}

            {/* Permalink */}
            {selectedPost.ig_permalink && (
              <a
                href={selectedPost.ig_permalink}
                target="_blank"
                rel="noopener noreferrer"
                className="flex items-center gap-1.5 text-xs text-violet-400 hover:text-violet-300"
              >
                <ExternalLink size={12} /> View on Instagram
              </a>
            )}

            {/* Error */}
            {selectedPost.error_message && (
              <div className="px-3 py-2 bg-red-500/10 border border-red-500/30 rounded-lg">
                <p className="text-red-400 text-xs">{selectedPost.error_message}</p>
              </div>
            )}

            {/* Info */}
            <div className="space-y-1.5 text-xs">
              <div className="flex justify-between">
                <span className="text-zinc-500">Created</span>
                <span className="text-zinc-300">{new Date(selectedPost.created_at).toLocaleDateString()}</span>
              </div>
              {selectedPost.published_at && (
                <div className="flex justify-between">
                  <span className="text-zinc-500">Published</span>
                  <span className="text-zinc-300">{new Date(selectedPost.published_at).toLocaleDateString()}</span>
                </div>
              )}
              {selectedPost.ig_media_id && (
                <div className="flex justify-between">
                  <span className="text-zinc-500">Media ID</span>
                  <span className="text-zinc-300 font-mono text-[10px]">{selectedPost.ig_media_id}</span>
                </div>
              )}
            </div>

            {/* Actions */}
            <div className="flex gap-2 pt-2">
              {(selectedPost.status === 'queued' || selectedPost.status === 'failed') && oauthToken && (
                <button
                  onClick={() => publishMut.mutate(selectedPost.id)}
                  disabled={publishMut.isPending}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-green-600 hover:bg-green-500 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
                >
                  {publishMut.isPending && publishMut.variables === selectedPost.id ? (
                    <><Loader2 size={12} className="animate-spin" /> Publishing...</>
                  ) : (
                    <><Send size={12} /> Publish</>
                  )}
                </button>
              )}
              {selectedPost.status !== 'uploading' && selectedPost.status !== 'processing' && (
                <button
                  onClick={() => { deleteMut.mutate(selectedPost.id); setSelectedPostId(null) }}
                  className="flex items-center justify-center gap-1.5 px-3 py-2 bg-zinc-800 hover:bg-red-600/20 border border-zinc-700 hover:border-red-600/40 rounded-lg text-xs text-zinc-400 hover:text-red-400 transition-colors"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ──── Post Row Component ────

interface PostRowProps {
  post: Post
  video?: Video
  selected: boolean
  onSelect: () => void
  onPublish?: () => void
  onDelete?: () => void
  publishing?: boolean
  canPublish?: boolean
}

function PostRow({
  post, video, selected, onSelect, onPublish, onDelete, publishing, canPublish,
}: PostRowProps) {
  return (
    <div
      onClick={onSelect}
      className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
        selected
          ? 'border-violet-500 bg-violet-500/5'
          : 'border-zinc-800 bg-zinc-900 hover:border-zinc-700'
      }`}
    >
      {/* Thumbnail — prefer edited version */}
      <div className="w-10 h-[70px] rounded-lg bg-zinc-800 overflow-hidden flex-shrink-0">
        <img
          src={profileThumbnailUrl(post.video_id, post.profile_id)}
          alt=""
          className="w-full h-full object-cover"
          onError={e => (e.currentTarget.style.display = 'none')}
        />
      </div>

      {/* Info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm text-white font-medium truncate">
            {video ? `@${video.source_account}` : `Video #${post.video_id}`}
          </p>
          <StatusBadge status={post.status} />
        </div>
        <p className="text-xs text-zinc-500 mt-0.5 truncate">
          {post.caption || 'No caption'}
        </p>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-1.5 flex-shrink-0">
        {onPublish && canPublish && (post.status === 'queued' || post.status === 'failed') && (
          <button
            onClick={e => { e.stopPropagation(); onPublish() }}
            disabled={publishing}
            className="p-1.5 bg-green-600/20 hover:bg-green-600/40 rounded-lg transition-colors"
            title="Publish"
          >
            {publishing ? (
              <Loader2 size={13} className="text-green-400 animate-spin" />
            ) : (
              <Send size={13} className="text-green-400" />
            )}
          </button>
        )}
        {onDelete && post.status !== 'uploading' && post.status !== 'processing' && (
          <button
            onClick={e => { e.stopPropagation(); onDelete() }}
            className="p-1.5 hover:bg-red-600/20 rounded-lg transition-colors"
            title="Remove"
          >
            <Trash2 size={13} className="text-zinc-500 hover:text-red-400" />
          </button>
        )}
        <ChevronRight size={14} className="text-zinc-600" />
      </div>
    </div>
  )
}
