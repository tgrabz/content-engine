import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface AuthUser {
  id: number
  email: string
  display_name: string | null
  role: string
}

export interface NetworkBrief {
  id: number
  name: string
  slug: string
}

interface AppState {
  activeProfileId: number | null
  activeNetworkId: number | null
  token: string | null
  user: AuthUser | null
  networks: NetworkBrief[]
  setActiveProfile: (id: number | null) => void
  setActiveNetwork: (id: number | null) => void
  setAuth: (token: string, user: AuthUser, networks: NetworkBrief[]) => void
  setNetworks: (networks: NetworkBrief[]) => void
  logout: () => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      activeProfileId: null,
      activeNetworkId: null,
      token: null,
      user: null,
      networks: [],
      setActiveProfile: (id) => set({ activeProfileId: id }),
      setActiveNetwork: (id) => set({ activeNetworkId: id, activeProfileId: null }),
      setAuth: (token, user, networks) => set({
        token,
        user,
        networks,
        // Auto-select first network if none selected
        activeNetworkId: networks.length > 0 ? networks[0].id : null,
      }),
      setNetworks: (networks) => set({ networks }),
      logout: () => set({
        token: null,
        user: null,
        networks: [],
        activeNetworkId: null,
        activeProfileId: null,
      }),
    }),
    { name: 'content-engine-app' }
  )
)
