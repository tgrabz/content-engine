import api from './client'
import type { AuthUser, NetworkBrief } from '../stores/appStore'

// ── User Auth ──

export interface AuthResponse {
  access_token: string
  user: AuthUser
  networks: NetworkBrief[]
}

export const checkAuthStatus = () =>
  api.get<{ has_users: boolean }>('/auth/status').then(r => r.data)

export const register = (email: string, password: string, display_name?: string) =>
  api.post<AuthResponse>('/auth/register', { email, password, display_name }).then(r => r.data)

export const login = (email: string, password: string) =>
  api.post<AuthResponse>('/auth/login', { email, password }).then(r => r.data)

export const getMe = () =>
  api.get<AuthResponse>('/auth/me').then(r => r.data)

// ── Instagram OAuth ──

export interface OAuthUrl {
  auth_url: string
  state: string
}

export interface OAuthCallbackResponse {
  access_token: string
  ig_user_id: string
  username: string
  name: string | null
  profile_picture_url: string | null
}

export interface OAuthToken {
  id: number
  profile_id: number
  ig_user_id: string | null
  saved_at: string
}

export const getOAuthUrl = () =>
  api.get<OAuthUrl>('/auth/oauth/url').then(r => r.data)

export const handleOAuthCallback = (code: string, state: string) =>
  api.post<OAuthCallbackResponse>('/auth/oauth/callback', { code, state }).then(r => r.data)

export const saveOAuthTokens = (data: {
  profile_id: number
  ig_user_id: string
  username: string
  access_token: string
  name?: string | null
  profile_picture_url?: string | null
}) => api.post<OAuthToken>('/auth/oauth/save', data).then(r => r.data)

export const getProfileToken = (profileId: number) =>
  api.get<OAuthToken | null>(`/auth/oauth/token/${profileId}`).then(r => r.data)

export const deleteProfileToken = (profileId: number) =>
  api.delete(`/auth/oauth/token/${profileId}`)
