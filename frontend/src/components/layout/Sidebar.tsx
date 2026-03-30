import { NavLink, useNavigate } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
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
  Zap,
  LogOut,
  Globe,
} from 'lucide-react'
import { fetchProfiles } from '../../api/profiles'
import { useAppStore } from '../../stores/appStore'

const mainLinks = [
  { to: '/', label: 'Workspace', icon: Zap },
]

const setupLinks = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/niches', label: 'Niches', icon: FolderOpen },
  { to: '/scraper', label: 'Scraper', icon: Download },
  { to: '/templates', label: 'Templates', icon: Layers },
  { to: '/videos', label: 'Videos', icon: Film },
  { to: '/editor', label: 'Editor', icon: Scissors },
  { to: '/posts', label: 'Posts', icon: Send },
  { to: '/settings', label: 'Settings', icon: Settings },
  { to: '/network-settings', label: 'Networks', icon: Globe },
]

export default function Sidebar() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const { data: profilesRaw } = useQuery({ queryKey: ['profiles'], queryFn: fetchProfiles })
  const profiles = Array.isArray(profilesRaw) ? profilesRaw : []
  const {
    activeProfileId, setActiveProfile,
    activeNetworkId, setActiveNetwork,
    user, networks, logout,
  } = useAppStore()
  const handleLogout = () => {
    logout()
    navigate('/login')
  }

  return (
    <aside className="w-56 bg-zinc-900 border-r border-zinc-800 flex flex-col h-screen sticky top-0">
      <div className="px-5 py-5 border-b border-zinc-800">
        <h1 className="text-lg font-bold text-white tracking-tight">Content Engine</h1>
        <p className="text-xs text-zinc-500 mt-0.5">Instagram Automation</p>
      </div>

      {/* Network selector */}
      {networks.length > 0 && (
        <div className="px-3 py-3 border-b border-zinc-800">
          <label className="text-[10px] text-zinc-600 uppercase tracking-wider px-1 flex items-center gap-1">
            <Globe size={10} />
            Network
          </label>
          <div className="relative mt-1">
            <select
              value={activeNetworkId ?? ''}
              onChange={e => {
                setActiveNetwork(e.target.value ? Number(e.target.value) : null)
                queryClient.clear()
              }}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-white appearance-none cursor-pointer pr-8"
            >
              {networks.map(n => (
                <option key={n.id} value={n.id}>{n.name}</option>
              ))}
            </select>
            <ChevronDown size={14} className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-500 pointer-events-none" />
          </div>
        </div>
      )}

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

      <nav className="flex-1 py-3 px-3 overflow-auto">
        {mainLinks.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-violet-600/20 text-violet-400'
                  : 'text-zinc-300 hover:text-white hover:bg-zinc-800'
              }`
            }
          >
            <Icon size={18} />
            {label}
          </NavLink>
        ))}
        <div className="my-3 border-t border-zinc-800" />
        <p className="px-3 mb-1 text-[9px] text-zinc-600 uppercase tracking-wider">Setup</p>
        <div className="space-y-0.5">
          {setupLinks.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              className={({ isActive }) =>
                `flex items-center gap-3 px-3 py-1.5 rounded-lg text-sm transition-colors ${
                  isActive
                    ? 'bg-violet-600/20 text-violet-400 font-medium'
                    : 'text-zinc-400 hover:text-white hover:bg-zinc-800'
                }`
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </div>
      </nav>

      {/* User info + logout */}
      <div className="px-3 py-3 border-t border-zinc-800">
        <div className="flex items-center justify-between">
          <div className="min-w-0">
            <p className="text-xs text-white truncate">{user?.display_name || user?.email}</p>
            <p className="text-[10px] text-zinc-500">{user?.role}</p>
          </div>
          <button
            onClick={handleLogout}
            className="p-1.5 text-zinc-500 hover:text-white rounded transition-colors"
            title="Sign out"
          >
            <LogOut size={14} />
          </button>
        </div>
      </div>
    </aside>
  )
}
