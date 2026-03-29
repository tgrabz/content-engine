import api from './client'

export interface Template {
  id: number
  profile_id: number | null
  name: string
  image_path: string
  video_box: string   // JSON: [x1, y1, x2, y2] normalized 0-1
  caption_box: string  // JSON: [x1, y1, x2, y2] normalized 0-1
  overlays_json: string
  text_config: string
  created_at: string
  updated_at: string
}

export const fetchTemplates = (profileId?: number) => {
  const qs = profileId ? `?profile_id=${profileId}` : ''
  return api.get<Template[]>(`/templates${qs}`).then(r => r.data)
}

export const fetchTemplate = (id: number) =>
  api.get<Template>(`/templates/${id}`).then(r => r.data)

export const createTemplate = (form: FormData) =>
  api.post<Template>('/templates', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data)

export const updateTemplate = (id: number, data: Partial<Template>) =>
  api.patch<Template>(`/templates/${id}`, data).then(r => r.data)

export const deleteTemplate = (id: number) =>
  api.delete(`/templates/${id}`)

export const generateTemplate = (form: FormData) =>
  api.post<Template>('/templates/generate', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data)

export const templateImageUrl = (id: number) => `/api/templates/${id}/image`
