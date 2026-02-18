import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface AppState {
  activeProfileId: number | null
  setActiveProfile: (id: number | null) => void
}

export const useAppStore = create<AppState>()(
  persist(
    (set) => ({
      activeProfileId: null,
      setActiveProfile: (id) => set({ activeProfileId: id }),
    }),
    { name: 'content-engine-app' }
  )
)
