import { useState } from 'react'
import { Monitor, Apple, Copy, Check, Terminal } from 'lucide-react'

export default function DownloadPage() {
  const [copied, setCopied] = useState<string | null>(null)

  const macCommand = `curl -fsSL https://raw.githubusercontent.com/tgrabz/content-engine/main/install-mac.sh | bash`
  const winCommand = `irm https://raw.githubusercontent.com/tgrabz/content-engine/main/install-windows.ps1 | iex`

  function copy(text: string, id: string) {
    navigator.clipboard.writeText(text)
    setCopied(id)
    setTimeout(() => setCopied(null), 2000)
  }

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center px-4">
      <div className="w-full max-w-2xl">
        <div className="text-center mb-10">
          <h1 className="text-3xl font-bold text-white">Content Engine</h1>
          <p className="text-zinc-400 text-sm mt-2">Install the desktop app to get started</p>
        </div>

        <div className="grid gap-6 md:grid-cols-2">
          {/* Mac */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-zinc-800 flex items-center justify-center">
                <Apple size={20} className="text-white" />
              </div>
              <div>
                <h2 className="text-white font-semibold">macOS</h2>
                <p className="text-zinc-500 text-xs">Intel & Apple Silicon</p>
              </div>
            </div>
            <p className="text-zinc-400 text-xs mb-4">Open Terminal and paste:</p>
            <div className="relative">
              <pre className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-xs text-green-400 font-mono overflow-x-auto whitespace-pre-wrap break-all">
                {macCommand}
              </pre>
              <button
                onClick={() => copy(macCommand, 'mac')}
                className="absolute top-2 right-2 p-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-colors"
              >
                {copied === 'mac' ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
              </button>
            </div>
          </div>

          {/* Windows */}
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="w-10 h-10 rounded-lg bg-zinc-800 flex items-center justify-center">
                <Monitor size={20} className="text-white" />
              </div>
              <div>
                <h2 className="text-white font-semibold">Windows</h2>
                <p className="text-zinc-500 text-xs">Windows 10 / 11</p>
              </div>
            </div>
            <p className="text-zinc-400 text-xs mb-4">Open PowerShell as Admin and paste:</p>
            <div className="relative">
              <pre className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-xs text-blue-400 font-mono overflow-x-auto whitespace-pre-wrap break-all">
                {winCommand}
              </pre>
              <button
                onClick={() => copy(winCommand, 'win')}
                className="absolute top-2 right-2 p-1.5 rounded-md bg-zinc-800 hover:bg-zinc-700 text-zinc-400 hover:text-white transition-colors"
              >
                {copied === 'win' ? <Check size={14} className="text-green-400" /> : <Copy size={14} />}
              </button>
            </div>
          </div>
        </div>

        <div className="mt-8 bg-zinc-900/50 border border-zinc-800 rounded-xl p-6">
          <h3 className="text-white font-semibold text-sm mb-3 flex items-center gap-2">
            <Terminal size={14} /> After Install
          </h3>
          <ul className="space-y-2 text-zinc-400 text-sm">
            <li>1. Double-click <code className="text-zinc-300 bg-zinc-800 px-1.5 py-0.5 rounded text-xs">start.command</code> (Mac) or <code className="text-zinc-300 bg-zinc-800 px-1.5 py-0.5 rounded text-xs">Start Content Engine.bat</code> (Windows)</li>
            <li>2. Browser opens to <code className="text-zinc-300 bg-zinc-800 px-1.5 py-0.5 rounded text-xs">localhost:5173</code> automatically</li>
            <li>3. Log in with your account or create one</li>
            <li>4. To update, run <code className="text-zinc-300 bg-zinc-800 px-1.5 py-0.5 rounded text-xs">update.command</code> / <code className="text-zinc-300 bg-zinc-800 px-1.5 py-0.5 rounded text-xs">Update Content Engine.bat</code></li>
          </ul>
        </div>

        <p className="text-center text-zinc-600 text-xs mt-6">
          Already have an account? <a href="/login" className="text-violet-400 hover:text-violet-300">Sign in online</a>
        </p>
      </div>
    </div>
  )
}
