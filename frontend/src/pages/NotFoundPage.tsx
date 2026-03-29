import { Link } from 'react-router-dom'
import { Home } from 'lucide-react'

export default function NotFoundPage() {
  return (
    <div className="flex flex-col items-center justify-center h-screen gap-4">
      <p className="text-6xl font-bold text-zinc-700">404</p>
      <p className="text-zinc-400 text-sm">Page not found.</p>
      <Link
        to="/"
        className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white rounded-lg text-sm font-medium transition-colors"
      >
        <Home size={14} /> Back to Dashboard
      </Link>
    </div>
  )
}
