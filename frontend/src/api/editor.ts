import api from './client'

export interface EditSession {
  id: number
  video_id: number
  profile_id: number
  template_id: number | null
  scene_json: string
  crop_box: string
  padding_pct: number
  offset_x: number
  offset_y: number
  caption_text: string
  caption_color: string
  caption_box: string
  caption_placement: string
  post_caption: string
  render_quality: string
  include_audio: boolean
  exported_path: string | null
  profile_status: string | null
  created_at: string
  updated_at: string
}

export interface EditSessionUpdateData {
  template_id?: number | null
  scene_json?: string
  crop_box?: string
  padding_pct?: number
  offset_x?: number
  offset_y?: number
  caption_text?: string
  caption_color?: string
  caption_box?: string
  caption_placement?: string
  post_caption?: string
  render_quality?: string
  include_audio?: boolean
}

export const getOrCreateSession = (videoId: number, profileId: number) =>
  api.get<EditSession>(`/editor/session?video_id=${videoId}&profile_id=${profileId}`).then(r => r.data)

export const updateSession = (sessionId: number, data: EditSessionUpdateData) =>
  api.patch<EditSession>(`/editor/session/${sessionId}`, data).then(r => r.data)

export const frameUrl = (videoId: number, t = 1.0) =>
  `/api/editor/frame/${videoId}?t=${t}`

// Composite preview — server-side render-identical preview
export function previewUrl(params: {
  videoId: number
  t: number
  templateId: number | null
  cropBox: [number, number, number, number]
  videoBox: [number, number, number, number]
  captionText: string
  captionColor: string
  captionBox: [number, number, number, number]
}): string {
  const p = new URLSearchParams()
  p.set('video_id', String(params.videoId))
  p.set('t', String(params.t))
  if (params.templateId) p.set('template_id', String(params.templateId))
  p.set('crop_box', JSON.stringify(params.cropBox))
  p.set('video_box', JSON.stringify(params.videoBox))
  p.set('caption_text', params.captionText)
  p.set('caption_color', params.captionColor)
  p.set('caption_box', JSON.stringify(params.captionBox))
  return `/api/editor/preview?${p.toString()}`
}

// Auto-crop
export interface AutoCropResult {
  crop_box: [number, number, number, number]
}

export const autoCrop = (videoId: number, numSamples = 16) =>
  api.post<AutoCropResult>('/editor/auto-crop', { video_id: videoId, num_samples: numSamples }).then(r => r.data)

// Caption placement
export interface CaptionPlaceResult {
  caption_box: [number, number, number, number]
  caption_color: string
}

export const captionPlace = (videoId: number, templateId: number | null, videoBox: [number, number, number, number], cropBox?: [number, number, number, number]) =>
  api.post<CaptionPlaceResult>('/editor/caption-place', {
    video_id: videoId,
    template_id: templateId,
    video_box: videoBox,
    crop_box: cropBox,
  }).then(r => r.data)

// Render pipeline
export interface RenderStartResult {
  job_id: string
}

export interface RenderStatusResult {
  status: 'pending' | 'rendering' | 'complete' | 'failed'
  progress: number
  error: string | null
}

export const startRender = (sessionId: number, quality: string, includeAudio: boolean) =>
  api.post<RenderStartResult>('/editor/render', {
    session_id: sessionId,
    quality,
    include_audio: includeAudio,
  }).then(r => r.data)

export const renderStatus = (jobId: string) =>
  api.get<RenderStatusResult>(`/editor/render/${jobId}`).then(r => r.data)

export const renderDownloadUrl = (jobId: string) =>
  `/api/editor/render/${jobId}/download`

export const exportToProfile = (sessionId: number) =>
  api.post<{ status: string; exported_path: string }>(`/editor/export/${sessionId}`).then(r => r.data)

// Auto-edit pipeline
export interface AutoEditItem {
  video_id: number
  session_id: number
  job_id: string
  status: string
}

export const autoEdit = (profileId: number, videoIds?: number[]) =>
  api.post<AutoEditItem[]>('/editor/auto-edit', {
    profile_id: profileId,
    video_ids: videoIds,
  }).then(r => r.data)

// AI caption generation
export interface GenerateCaptionResult {
  overlay: string
  caption: string
  cached: boolean  // true if video was already analyzed (no vision cost)
}

export const generateCaption = (videoId: number, profileId: number) =>
  api.post<GenerateCaptionResult>('/editor/generate-caption', {
    video_id: videoId,
    profile_id: profileId,
  }).then(r => r.data)

// Caption from description (no video analysis)
export const describeCaption = (description: string) =>
  api.post<{ caption: string }>('/editor/describe-caption', { description }).then(r => r.data)

// Batch render status
export interface BatchStatusItem {
  job_id: string
  status: string
  progress: number
  error: string | null
}

export const batchRenderStatus = (jobIds: string[]) =>
  api.post<BatchStatusItem[]>('/editor/render/batch-status', { job_ids: jobIds }).then(r => r.data)
