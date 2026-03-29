import { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchNiches, type Niche } from '../api/niches'
import { fetchCredentials, createCredential, deleteCredential, type Credential } from '../api/credentials'
import { startScrape, connectScraperWs, type ScrapeConfig } from '../api/scraper'
import { Download, Play, Loader2, CheckCircle2, XCircle, Monitor, MonitorOff, Plus, Trash2 } from 'lucide-react'

interface LogEntry {
  id: number
  message: string
  type: 'log' | 'error' | 'result'
}

interface ScrapeResult {
  video_id: number
  account: string
  shortcode: string
  views: number | null
  file_bytes: number
}

export default function ScraperPage() {
  const queryClient = useQueryClient()
  const { data: niches = [] } = useQuery({ queryKey: ['niches'], queryFn: fetchNiches })
  const { data: credentials = [] } = useQuery({ queryKey: ['credentials'], queryFn: fetchCredentials })

  // Config state
  const [nicheId, setNicheId] = useState<number | ''>('')
  const [credentialId, setCredentialId] = useState<number | ''>('')
  const [selectedAccounts, setSelectedAccounts] = useState<string[]>([])
  const [maxReels, setMaxReels] = useState(10)
  const [minViews, setMinViews] = useState(10000)
  const [maxScrolls, setMaxScrolls] = useState(15)
  const [earlyStopDupes, setEarlyStopDupes] = useState(5)
  const [headless, setHeadless] = useState(true)

  // Add credential form
  const [showAddCred, setShowAddCred] = useState(false)
  const [newCredUser, setNewCredUser] = useState('')
  const [newCredPass, setNewCredPass] = useState('')
  const [addingCred, setAddingCred] = useState(false)

  // Job state
  const [isRunning, setIsRunning] = useState(false)
  const [isDone, setIsDone] = useState(false)
  const [hasError, setHasError] = useState(false)
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [results, setResults] = useState<ScrapeResult[]>([])
  const logIdRef = useRef(0)
  const logEndRef = useRef<HTMLDivElement>(null)
  const wsRef = useRef<WebSocket | null>(null)

  const selectedNiche = niches.find(n => n.id === nicheId)
  const nicheAccounts = selectedNiche?.accounts.filter(a => a.platform === 'instagram') ?? []

  // Auto-scroll log
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  // Auto-select all accounts when niche changes
  useEffect(() => {
    setSelectedAccounts(nicheAccounts.map(a => a.username))
  }, [nicheId]) // eslint-disable-line react-hooks/exhaustive-deps

  const addLog = useCallback((message: string, type: LogEntry['type'] = 'log') => {
    setLogs(prev => [...prev, { id: ++logIdRef.current, message, type }])
  }, [])

  const startMutation = useMutation({
    mutationFn: (config: ScrapeConfig) => startScrape(config),
    onSuccess: (job) => {
      setIsRunning(true)
      setIsDone(false)
      setHasError(false)
      addLog(`Job #${job.id} started`)

      const ws = connectScraperWs(job.id, {
        onLog: (msg) => addLog(msg),
        onResult: (data) => {
          setResults(prev => [...prev, data as unknown as ScrapeResult])
          addLog(`Downloaded: ${(data as Record<string, string>).shortcode}`, 'result')
        },
        onDone: (total) => {
          addLog(`Done! ${total} reels downloaded.`)
          setIsDone(true)
          setIsRunning(false)
        },
        onError: (msg) => {
          addLog(`Error: ${msg}`, 'error')
          setHasError(true)
          setIsRunning(false)
        },
        onComplete: () => {
          setIsRunning(false)
        },
      })
      wsRef.current = ws
    },
    onError: (err) => {
      addLog(`Failed to start: ${err}`, 'error')
      setHasError(true)
    },
  })

  const handleStart = () => {
    if (!nicheId || !credentialId) return
    setLogs([])
    setResults([])
    startMutation.mutate({
      niche_id: nicheId as number,
      credential_id: credentialId as number,
      target_accounts: selectedAccounts,
      max_reels: maxReels,
      min_views: minViews,
      max_scrolls: maxScrolls,
      scroll_pause_min: 1.5,
      scroll_pause_max: 3.0,
      headless,
      early_stop_dupes: earlyStopDupes,
      unknown_views_pass: true,
      fallback_to_likes: false,
    })
  }

  const toggleAccount = (username: string) => {
    setSelectedAccounts(prev =>
      prev.includes(username) ? prev.filter(u => u !== username) : [...prev, username]
    )
  }

  const formatBytes = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  }

  const formatViews = (views: number | null) => {
    if (views === null) return '---'
    if (views >= 1_000_000) return `${(views / 1_000_000).toFixed(1)}M`
    if (views >= 1_000) return `${(views / 1_000).toFixed(1)}K`
    return views.toLocaleString()
  }

  return (
    <div className="p-8 max-w-4xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">Scraper</h2>
        <p className="text-zinc-400 text-sm">Download Instagram Reels from target accounts.</p>
      </div>

      {/* Config Panel */}
      <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
        <div>
          <label className="text-xs text-zinc-500 block mb-1">Niche</label>
          <select
            value={nicheId}
            onChange={e => setNicheId(e.target.value ? Number(e.target.value) : '')}
            className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm"
          >
            <option value="">Select niche...</option>
            {niches.map(n => (
              <option key={n.id} value={n.id}>{n.name}</option>
            ))}
          </select>
        </div>

        {/* Scraper Accounts */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs text-zinc-500 uppercase tracking-wider font-semibold">Scraper Account</label>
            <button
              onClick={() => setShowAddCred(!showAddCred)}
              className="flex items-center gap-1 px-2 py-0.5 text-[10px] font-medium text-violet-400 bg-violet-500/10 hover:bg-violet-500/20 rounded-md transition-colors"
            >
              <Plus size={10} /> Add Account
            </button>
          </div>

          {showAddCred && (
            <div className="flex gap-2 mb-3">
              <input
                type="text"
                value={newCredUser}
                onChange={e => setNewCredUser(e.target.value)}
                placeholder="Instagram username"
                className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm focus:border-violet-500 focus:outline-none"
              />
              <input
                type="password"
                value={newCredPass}
                onChange={e => setNewCredPass(e.target.value)}
                placeholder="Password"
                className="flex-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm focus:border-violet-500 focus:outline-none"
              />
              <button
                onClick={async () => {
                  if (!newCredUser.trim() || !newCredPass.trim()) return
                  setAddingCred(true)
                  try {
                    const cred = await createCredential(newCredUser.trim(), newCredPass.trim())
                    queryClient.invalidateQueries({ queryKey: ['credentials'] })
                    setCredentialId(cred.id)
                    setNewCredUser('')
                    setNewCredPass('')
                    setShowAddCred(false)
                  } catch (e: any) {
                    alert(e?.response?.data?.detail || 'Failed to save credential')
                  } finally {
                    setAddingCred(false)
                  }
                }}
                disabled={addingCred || !newCredUser.trim() || !newCredPass.trim()}
                className="px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 text-white rounded-lg text-sm font-medium transition-colors"
              >
                {addingCred ? <Loader2 size={14} className="animate-spin" /> : 'Save'}
              </button>
            </div>
          )}

          {credentials.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {credentials.map(c => (
                <div key={c.id} className="flex items-center gap-1">
                  <button
                    onClick={() => setCredentialId(c.id)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                      credentialId === c.id
                        ? 'bg-violet-600/30 text-violet-300 border border-violet-500/50'
                        : 'bg-zinc-800 text-zinc-400 border border-zinc-700 hover:text-zinc-300'
                    }`}
                  >
                    @{c.username}
                  </button>
                  <button
                    onClick={async () => {
                      if (credentialId === c.id) setCredentialId('')
                      await deleteCredential(c.id)
                      queryClient.invalidateQueries({ queryKey: ['credentials'] })
                    }}
                    className="p-1 text-zinc-600 hover:text-red-400 transition-colors"
                    title="Remove"
                  >
                    <Trash2 size={10} />
                  </button>
                </div>
              ))}
            </div>
          ) : !showAddCred ? (
            <p className="text-xs text-zinc-600">No scraper accounts saved. Add one to get started.</p>
          ) : null}
        </div>

        {/* Target Accounts */}
        {nicheAccounts.length > 0 && (
          <div>
            <label className="text-xs text-zinc-500 block mb-2">
              Target Accounts ({selectedAccounts.length}/{nicheAccounts.length})
            </label>
            <div className="flex flex-wrap gap-2">
              {nicheAccounts.map(a => (
                <button
                  key={a.id}
                  onClick={() => toggleAccount(a.username)}
                  className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
                    selectedAccounts.includes(a.username)
                      ? 'bg-violet-600/30 text-violet-300 border border-violet-500/50'
                      : 'bg-zinc-800 text-zinc-500 border border-zinc-700 hover:text-zinc-300'
                  }`}
                >
                  @{a.username}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Numeric Controls */}
        <div className="grid grid-cols-4 gap-4">
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Max Reels</label>
            <input
              type="number"
              min={1}
              max={1000}
              value={maxReels}
              onChange={e => setMaxReels(Number(e.target.value))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Min Views</label>
            <input
              type="number"
              min={0}
              step={1000}
              value={minViews}
              onChange={e => setMinViews(Number(e.target.value))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Max Scrolls</label>
            <input
              type="number"
              min={1}
              max={500}
              value={maxScrolls}
              onChange={e => setMaxScrolls(Number(e.target.value))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm"
            />
          </div>
          <div>
            <label className="text-xs text-zinc-500 block mb-1">Dupe Stop</label>
            <input
              type="number"
              min={0}
              max={50}
              value={earlyStopDupes}
              onChange={e => setEarlyStopDupes(Number(e.target.value))}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm"
            />
            <p className="text-[9px] text-zinc-600 mt-0.5">0 = off</p>
          </div>
        </div>

        {/* Toggles + Start */}
        <div className="flex items-center justify-between pt-2">
          <button
            onClick={() => setHeadless(!headless)}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
              headless
                ? 'bg-zinc-800 text-zinc-400 border border-zinc-700'
                : 'bg-amber-600/20 text-amber-300 border border-amber-500/50'
            }`}
          >
            {headless ? <MonitorOff size={14} /> : <Monitor size={14} />}
            {headless ? 'Headless' : 'Visible Browser'}
          </button>

          <button
            onClick={handleStart}
            disabled={!nicheId || !credentialId || selectedAccounts.length === 0 || isRunning}
            className="flex items-center gap-2 px-5 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
          >
            {isRunning ? (
              <><Loader2 size={16} className="animate-spin" /> Scraping...</>
            ) : (
              <><Play size={16} /> Start Scrape</>
            )}
          </button>
        </div>
      </div>

      {/* Live Log */}
      {logs.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            {isRunning ? (
              <Loader2 size={14} className="animate-spin text-violet-400" />
            ) : isDone ? (
              <CheckCircle2 size={14} className="text-green-400" />
            ) : hasError ? (
              <XCircle size={14} className="text-red-400" />
            ) : (
              <Download size={14} className="text-zinc-400" />
            )}
            <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider">
              {isRunning ? 'Running' : isDone ? 'Complete' : hasError ? 'Failed' : 'Log'}
            </h3>
          </div>

          <div className="bg-zinc-950 border border-zinc-800 rounded-xl p-4 h-72 overflow-auto font-mono text-xs leading-relaxed">
            {logs.map(entry => (
              <div
                key={entry.id}
                className={
                  entry.type === 'error' ? 'text-red-400' :
                  entry.type === 'result' ? 'text-green-400' :
                  'text-zinc-400'
                }
              >
                <span className="text-zinc-600 select-none">&gt; </span>
                {entry.message}
              </div>
            ))}
            <div ref={logEndRef} />
          </div>
        </div>
      )}

      {/* Results Table */}
      {results.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-2">
            <Download size={14} />
            Results ({results.length} reels)
          </h3>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-zinc-800 text-zinc-500 text-xs uppercase tracking-wider">
                  <th className="text-left px-4 py-2.5">Account</th>
                  <th className="text-left px-4 py-2.5">Shortcode</th>
                  <th className="text-right px-4 py-2.5">Views</th>
                  <th className="text-right px-4 py-2.5">Size</th>
                </tr>
              </thead>
              <tbody>
                {results.map((r, i) => (
                  <tr key={i} className="border-b border-zinc-800/50 hover:bg-zinc-800/30">
                    <td className="px-4 py-2 text-white">@{r.account}</td>
                    <td className="px-4 py-2 text-zinc-400 font-mono">{r.shortcode}</td>
                    <td className="px-4 py-2 text-right text-zinc-300">{formatViews(r.views)}</td>
                    <td className="px-4 py-2 text-right text-zinc-500">{formatBytes(r.file_bytes)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Empty state */}
      {niches.length === 0 && (
        <div className="text-center py-12 text-zinc-600">
          <p className="text-sm">No niches configured yet.</p>
          <p className="text-xs mt-1">Go to the Niches page to add target accounts.</p>
        </div>
      )}
    </div>
  )
}
