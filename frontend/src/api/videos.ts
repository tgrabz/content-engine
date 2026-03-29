import api from './client'

export interface Video {
  id: number
  platform: string
  niche_id: number
  source_account: string
  shortcode: string
  source_url: string
  local_path: string | null
  file_bytes: number
  views: number | null
  caption: string
  duration_sec: number | null
  width: number | null
  height: number | null
  status: string
  exported_path: string | null
  ig_post_id: string | null
  scraped_at: string
  updated_at: string
}

export interface VideoFilters {
  niche_id?: number
  status?: string
  source_account?: string
  search?: string
  sort?: string
  limit?: number
  offset?: number
}

export const fetchVideos = (filters: VideoFilters = {}) => {
  const params = new URLSearchParams()
  if (filters.niche_id) params.set('niche_id', String(filters.niche_id))
  if (filters.status) params.set('status', filters.status)
  if (filters.source_account) params.set('source_account', filters.source_account)
  if (filters.search) params.set('search', filters.search)
  if (filters.sort) params.set('sort', filters.sort)
  if (filters.limit) params.set('limit', String(filters.limit))
  if (filters.offset) params.set('offset', String(filters.offset))
  const qs = params.toString()
  return api.get<Video[]>(`/videos${qs ? `?${qs}` : ''}`).then(r => r.data)
}

export const fetchVideo = (id: number) =>
  api.get<Video>(`/videos/${id}`).then(r => r.data)

export const updateVideo = (id: number, data: { status?: string; caption?: string }) =>
  api.patch<Video>(`/videos/${id}`, data).then(r => r.data)

export const deleteVideo = (id: number) =>
  api.delete(`/videos/${id}`)

export const fetchSourceAccounts = (nicheId?: number) => {
  const qs = nicheId ? `?niche_id=${nicheId}` : ''
  return api.get<string[]>(`/videos/accounts${qs}`).then(r => r.data)
}

export interface ProfileVideo extends Video {
  session_id: number | null
  profile_status: string | null
  profile_exported_path: string | null
}

export const fetchVideosForProfile = (profileId: number) =>
  api.get<ProfileVideo[]>(`/videos/for-profile/${profileId}`).then(r => r.data)

export const thumbnailUrl = (videoId: number) => `/api/videos/${videoId}/thumbnail`
export const editedThumbnailUrl = (videoId: number) => `/api/videos/${videoId}/thumbnail?edited=true`
export const profileThumbnailUrl = (videoId: number, profileId: number) =>
  `/api/videos/${videoId}/thumbnail?edited=true&profile_id=${profileId}`
export const streamUrl = (videoId: number) => `/api/videos/${videoId}/stream`
export const editedStreamUrl = (videoId: number) => `/api/videos/${videoId}/stream?edited=true`
export const profileStreamUrl = (videoId: number, profileId: number) =>
  `/api/videos/${videoId}/stream?edited=true&profile_id=${profileId}`
