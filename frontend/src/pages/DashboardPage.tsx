import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Film, CheckCircle, Clock, Download, Send, AlertTriangle } from 'lucide-react'
import api from '../api/client'

interface DashboardStats {
  total_videos: number
  video_counts: Record<string, number>
  post_counts: Record<string, number>
  recent_videos: {
    id: number
    source_account: string
    shortcode: string
    status: string
    scraped_at: string | null
  }[]
}

const fetchStats = () => api.get<DashboardStats>('/stats').then(r => r.data)

const STATUS_COLORS: Record<string, string> = {
  downloaded: 'text-zinc-400',
  editing: 'text-blue-400',
  ready: 'text-amber-400',
  queued: 'text-violet-400',
  posting: 'text-orange-400',
  posted: 'text-green-400',
}

export default function DashboardPage() {
  const { data: stats, isLoading } = useQuery({
    queryKey: ['stats'],
    queryFn: fetchStats,
    refetchInterval: 30_000,
  })

  const vc = stats?.video_counts ?? {}
  const pc = stats?.post_counts ?? {}

  const cards = [
    { label: 'Total Videos', value: stats?.total_videos ?? 0, icon: Film, color: 'text-white' },
    { label: 'Downloaded', value: vc.downloaded ?? 0, icon: Download, color: 'text-zinc-400' },
    { label: 'Ready', value: vc.ready ?? 0, icon: CheckCircle, color: 'text-amber-400' },
    { label: 'Queued', value: (pc.queued ?? 0), icon: Clock, color: 'text-violet-400' },
    { label: 'Published', value: (pc.published ?? 0) + (vc.posted ?? 0), icon: Send, color: 'text-green-400' },
    { label: 'Failed', value: pc.failed ?? 0, icon: AlertTriangle, color: 'text-red-400' },
  ]

  return (
    <div className="p-8 max-w-5xl">
      <h2 className="text-2xl font-bold text-white mb-2">Dashboard</h2>
      <p className="text-zinc-400 text-sm">Overview of your content pipeline.</p>

      {/* Stat cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 mt-6">
        {cards.map(c => (
          <div key={c.label} className="bg-zinc-800/50 border border-zinc-700 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <c.icon size={14} className={c.color} />
              <p className="text-[10px] text-zinc-500 uppercase tracking-wider">{c.label}</p>
            </div>
            <p className={`text-2xl font-bold ${c.color}`}>
              {isLoading ? '...' : c.value}
            </p>
          </div>
        ))}
      </div>

      {/* Quick actions */}
      <div className="mt-8">
        <h3 className="text-xs text-zinc-500 uppercase tracking-wider font-semibold mb-3">Quick Actions</h3>
        <div className="flex gap-3">
          <Link
            to="/scraper"
            className="flex items-center gap-2 px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-xl text-sm text-white transition-colors"
          >
            <Download size={16} className="text-violet-400" /> Scrape Reels
          </Link>
          <Link
            to="/editor"
            className="flex items-center gap-2 px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-xl text-sm text-white transition-colors"
          >
            <Film size={16} className="text-violet-400" /> Edit Videos
          </Link>
          <Link
            to="/posts"
            className="flex items-center gap-2 px-4 py-2.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-xl text-sm text-white transition-colors"
          >
            <Send size={16} className="text-violet-400" /> Post Queue
          </Link>
        </div>
      </div>

      {/* Recent activity */}
      <div className="mt-8">
        <h3 className="text-xs text-zinc-500 uppercase tracking-wider font-semibold mb-3">Recent Videos</h3>
        {stats?.recent_videos.length ? (
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-zinc-500 text-xs">
                  <th className="text-left px-4 py-2.5 font-medium">Account</th>
                  <th className="text-left px-4 py-2.5 font-medium">Shortcode</th>
                  <th className="text-left px-4 py-2.5 font-medium">Status</th>
                  <th className="text-left px-4 py-2.5 font-medium">Scraped</th>
                </tr>
              </thead>
              <tbody>
                {stats.recent_videos.map(v => (
                  <tr key={v.id} className="border-b border-zinc-800/50 last:border-0">
                    <td className="px-4 py-2.5 text-zinc-300">@{v.source_account}</td>
                    <td className="px-4 py-2.5 text-zinc-500 font-mono text-xs">{v.shortcode}</td>
                    <td className="px-4 py-2.5">
                      <span className={`text-xs font-medium ${STATUS_COLORS[v.status] ?? 'text-zinc-400'}`}>
                        {v.status}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-zinc-500 text-xs">
                      {v.scraped_at ? new Date(v.scraped_at).toLocaleDateString() : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-zinc-600 text-sm">No videos yet. Start by scraping some reels.</p>
        )}
      </div>
    </div>
  )
}
