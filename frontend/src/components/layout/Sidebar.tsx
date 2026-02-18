import { NavLink } from 'react-router-dom'
import {
  LayoutDashboard,
  FolderOpen,
  Download,
  Film,
  Scissors,
  Layers,
  Send,
} from 'lucide-react'

const links = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/niches', label: 'Niches', icon: FolderOpen },
  { to: '/scraper', label: 'Scraper', icon: Download },
  { to: '/videos', label: 'Videos', icon: Film },
  { to: '/editor', label: 'Editor', icon: Scissors },
  { to: '/templates', label: 'Templates', icon: Layers },
  { to: '/posts', label: 'Post', icon: Send },
]

export default function Sidebar() {
  return (
    <aside className="w-56 bg-zinc-900 border-r border-zinc-800 flex flex-col h-screen sticky top-0">
      <div className="px-5 py-5 border-b border-zinc-800">
        <h1 className="text-lg font-bold text-white tracking-tight">Content Engine</h1>
        <p className="text-xs text-zinc-500 mt-0.5">Instagram Automation</p>
      </div>
      <nav className="flex-1 py-3 px-3 space-y-0.5">
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
        v0.1.0
      </div>
    </aside>
  )
}
