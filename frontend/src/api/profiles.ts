import api from './client'

export interface Profile {
  id: number
  name: string
  niche_id: number | null
  export_dir: string
  default_template_id: number | null
  created_at: string
  updated_at: string
}

export const fetchProfiles = () => api.get<Profile[]>('/profiles').then(r => r.data)

export const createProfile = (data: { name: string; niche_id?: number; export_dir?: string }) =>
  api.post<Profile>('/profiles', data).then(r => r.data)

export const updateProfile = (id: number, data: Partial<Profile>) =>
  api.put<Profile>(`/profiles/${id}`, data).then(r => r.data)

export const deleteProfile = (id: number) => api.delete(`/profiles/${id}`)
