import axios from 'axios'
import { useAppStore } from '../stores/appStore'

const api = axios.create({
  baseURL: '/api',
  headers: { 'Content-Type': 'application/json' },
})

// Inject JWT and network_id into every request
api.interceptors.request.use((config) => {
  const { token, activeNetworkId } = useAppStore.getState()
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  if (activeNetworkId) {
    config.params = { ...config.params, network_id: activeNetworkId }
  }
  return config
})

// Redirect to login on 401
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const { logout } = useAppStore.getState()
      logout()
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)

export default api
