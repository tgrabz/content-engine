import api from './client'

export interface Network {
  id: number
  name: string
  slug: string
  ig_app_id: string | null
  ig_redirect_uri: string | null
  public_url: string | null
  api_key: string | null
  created_at: string
  updated_at: string
}

export interface NetworkMember {
  id: number
  user_id: number
  network_id: number
  role: string
  email: string
  display_name: string | null
}

export const fetchNetworks = () =>
  api.get<Network[]>('/networks').then(r => r.data)

export const createNetwork = (data: {
  name: string
  ig_app_id?: string
  ig_app_secret?: string
  ig_redirect_uri?: string
  public_url?: string
}) => api.post<Network>('/networks', data).then(r => r.data)

export const updateNetwork = (id: number, data: {
  name?: string
  ig_app_id?: string
  ig_app_secret?: string
  ig_redirect_uri?: string
  public_url?: string
}) => api.put<Network>(`/networks/${id}`, data).then(r => r.data)

export const deleteNetwork = (id: number) =>
  api.delete(`/networks/${id}`)

export const fetchMembers = (networkId: number) =>
  api.get<NetworkMember[]>(`/networks/${networkId}/members`).then(r => r.data)

export const addMember = (networkId: number, userId: number) =>
  api.post<NetworkMember>(`/networks/${networkId}/members`, null, { params: { user_id: userId } }).then(r => r.data)

export const removeMember = (networkId: number, userId: number) =>
  api.delete(`/networks/${networkId}/members/${userId}`)

export const rotateApiKey = (networkId: number) =>
  api.post<Network>(`/networks/${networkId}/rotate-api-key`).then(r => r.data)
