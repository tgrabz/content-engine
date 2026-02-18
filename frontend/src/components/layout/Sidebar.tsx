import { NavLink } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import {
  LayoutDashboard,
  FolderOpen,
  Download,
  Film,
  Scissors,
  Layers,
  Send,
  Settings,
  ChevronDown,
} from 'lucide-react'
import { fetchProfiles } from '../../api/profiles'
import { useAppStore } from '../../stores/appStore'

const links = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/niches', label: 'Niches', icon: FolderOpen },
  { to: '/scraper', label: 'Scraper', icon: Download },
  { to: '/videos', label: 'Videos', icon: Film },
  { to: '/editor', label: 'Editor', icon: Scissors },
  { to: '/templates', label: 'Templates', icon: Layers },
  { to: '/posts', label: 'Post', icon: Send },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export default function Sidebar() {
  const { data: profiles = [] } = useQuery({ queryKey: ['profiles'], queryFn: fetchProfiles })
  const { activeProfileId, setActiveProfile } = useAppStore()
  const activeProfile = profiles.find(p => p.id === activeProfileId)

  return (
    <aside className="w-56 bg-zinc-900 border-r border-zinc-800 flex flex-col h-screen sticky top-0">
      <div className="px-5 py-5 border-b border-zinc-800">
        <h1 className="text-lg font-bold text-white tracking-tight">Content Engine</h1>
        <p className="text-xs text-zinc-500 mt-0.5">Instagram Automation</p>
      </div>

      {/* Profile selector */}
      <div className="px-3 py-3 border-b border-zinc-800">
        <label className="text-[10px] text-zinc-600 uppercase tracking-wider px-1">Profile</label>
        <div className="relative mt-1">
          <select
            value={activeProfileId ?? ''}
            onChange={e => setActiveProfile(e.target.value ? Number(e.target.value) : null)}
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-white appearance-none cursor-pointer pr-8"
          >
            <option value="">All profiles</option>
            {profiles.map(p => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
        </div>
      </div>

      <nav className="flex-1 py-3 px-3 space-y-0.5 overflow-auto">
        {links.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-violet-600/20 text-violet-400 font-medium'
                  : 'text-zinc-400 hover:text-white hover:bg-zinc-800'
              }`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="px-5 py-4 border-t border-zinc-800 text-xs text-zinc-600">
        {activeProfile ? activeProfile.name : 'No profile'} &middot; v0.1.0
      </div>
    </aside>
  )
}
