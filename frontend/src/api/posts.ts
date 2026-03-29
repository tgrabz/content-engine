import api from './client'

export interface Post {
  id: number
  video_id: number
  profile_id: number
  caption: string
  share_to_feed: boolean
  thumb_offset_ms: number
  upload_strategy: string
  status: 'scheduled' | 'queued' | 'uploading' | 'processing' | 'published' | 'failed'
  ig_container_id: string | null
  ig_media_id: string | null
  ig_permalink: string | null
  error_message: string | null
  position: number
  scheduled_for: string | null
  created_at: string
  published_at: string | null
}

export interface PostFilters {
  profile_id?: number
  status?: string
}

export const fetchPosts = (filters?: PostFilters) => {
  const params = new URLSearchParams()
  if (filters?.profile_id) params.set('profile_id', String(filters.profile_id))
  if (filters?.status) params.set('status', filters.status)
  const qs = params.toString()
  return api.get<Post[]>(`/posts${qs ? `?${qs}` : ''}`).then(r => r.data)
}

export const createPost = (data: {
  video_id: number
  profile_id: number
  caption?: string
  share_to_feed?: boolean
  thumb_offset_ms?: number
  auto_schedule?: boolean
}) => api.post<Post>('/posts', data).then(r => r.data)

export const updatePost = (id: number, data: {
  caption?: string
  share_to_feed?: boolean
  thumb_offset_ms?: number
  position?: number
}) => api.patch<Post>(`/posts/${id}`, data).then(r => r.data)

export const deletePost = (id: number) =>
  api.delete(`/posts/${id}`)

export const publishPost = (id: number) =>
  api.post<Post>(`/posts/${id}/publish`).then(r => r.data)
