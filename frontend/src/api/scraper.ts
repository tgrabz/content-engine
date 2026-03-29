import api from './client'

export interface ScrapeConfig {
  niche_id: number
  credential_id: number
  target_accounts: string[]
  max_reels: number
  min_views: number
  max_scrolls: number
  scroll_pause_min: number
  scroll_pause_max: number
  headless: boolean
  early_stop_dupes: number
  unknown_views_pass: boolean
  fallback_to_likes: boolean
}

export interface ScrapeJob {
  id: number
  niche_id: number
  login_credential_id: number
  status: string
  target_accounts: string
  config_json: string
  results_json: string | null
  error_message: string | null
  created_at: string
  started_at: string | null
  completed_at: string | null
}

export const startScrape = (config: ScrapeConfig) =>
  api.post<ScrapeJob>('/scraper/start', config).then(r => r.data)

export const fetchJobs = (limit = 20) =>
  api.get<ScrapeJob[]>(`/scraper/jobs?limit=${limit}`).then(r => r.data)

export const fetchJob = (id: number) =>
  api.get<ScrapeJob>(`/scraper/jobs/${id}`).then(r => r.data)

export function connectScraperWs(jobId: number, handlers: {
  onLog: (msg: string) => void
  onResult: (data: Record<string, unknown>) => void
  onDone: (total: number, results: Record<string, unknown>[]) => void
  onError: (msg: string) => void
  onComplete: () => void
}) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const ws = new WebSocket(`${proto}//${window.location.host}/ws/scraper/${jobId}`)

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data)
    switch (msg.type) {
      case 'log':
        handlers.onLog(msg.message)
        break
      case 'result':
        handlers.onResult(msg.data)
        break
      case 'done':
        handlers.onDone(msg.total, msg.results)
        break
      case 'error':
        handlers.onError(msg.message)
        break
      case 'complete':
        handlers.onComplete()
        break
      case 'heartbeat':
        break
    }
  }

  ws.onerror = () => handlers.onError('WebSocket connection error')
  ws.onclose = () => handlers.onComplete()

  return ws
}
