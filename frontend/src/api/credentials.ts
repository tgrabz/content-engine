import api from './client'

export interface Credential {
  id: number
  username: string
  created_at: string
}

export const fetchCredentials = () => api.get<Credential[]>('/credentials').then(r => r.data)

export const createCredential = (username: string, password: string) =>
  api.post<Credential>('/credentials', { username, password }).then(r => r.data)

export const deleteCredential = (id: number) => api.delete(`/credentials/${id}`)
