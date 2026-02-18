export default function DashboardPage() {
  return (
    <div className="p-8">
      <h2 className="text-2xl font-bold text-white mb-2">Dashboard</h2>
      <p className="text-zinc-400">Overview of your content pipeline.</p>
      <div className="grid grid-cols-3 gap-4 mt-6">
        <div className="bg-zinc-800/50 border border-zinc-700 rounded-xl p-5">
          <p className="text-xs text-zinc-500 uppercase tracking-wider">Videos</p>
          <p className="text-3xl font-bold text-white mt-1">—</p>
        </div>
        <div className="bg-zinc-800/50 border border-zinc-700 rounded-xl p-5">
          <p className="text-xs text-zinc-500 uppercase tracking-wider">Ready to Post</p>
          <p className="text-3xl font-bold text-white mt-1">—</p>
        </div>
        <div className="bg-zinc-800/50 border border-zinc-700 rounded-xl p-5">
          <p className="text-xs text-zinc-500 uppercase tracking-wider">Posted</p>
          <p className="text-3xl font-bold text-white mt-1">—</p>
        </div>
      </div>
    </div>
  )
}
