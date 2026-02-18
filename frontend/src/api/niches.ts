import api from './client'

export interface NicheAccount {
  id: number
  username: string
  platform: string
}

export interface Niche {
  id: number
  name: string
  accounts: NicheAccount[]
  created_at: string
  updated_at: string
}

export const fetchNiches = () => api.get<Niche[]>('/niches').then(r => r.data)

export const createNiche = (name: string, accounts: string[]) =>
  api.post<Niche>('/niches', { name, accounts }).then(r => r.data)

export const updateNiche = (id: number, data: { name?: string; accounts?: string[] }) =>
  api.put<Niche>(`/niches/${id}`, data).then(r => r.data)

export const deleteNiche = (id: number) => api.delete(`/niches/${id}`)
