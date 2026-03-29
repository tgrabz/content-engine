import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

export default function OAuthCallbackPage() {
  const [params] = useSearchParams()
  const [status, setStatus] = useState<'sending' | 'done' | 'error'>('sending')

  useEffect(() => {
    const code = params.get('code')
    const state = params.get('state')
    const error = params.get('error')

    if (error) {
      setStatus('error')
      // Notify opener about the error
      if (window.opener) {
        window.opener.postMessage({ type: 'oauth-callback', error }, window.location.origin)
      }
      setTimeout(() => window.close(), 2000)
      return
    }

    if (!code || !state) {
      setStatus('error')
      return
    }

    // Send code and state back to the opener window
    if (window.opener) {
      window.opener.postMessage(
        { type: 'oauth-callback', code, state },
        window.location.origin,
      )
      setStatus('done')
      setTimeout(() => window.close(), 500)
    } else {
      // Opened directly (not as popup) — can't relay back
      setStatus('error')
    }
  }, [params])

  return (
    <div className="flex items-center justify-center h-screen bg-zinc-950 text-white">
      {status === 'sending' && <p className="text-sm text-zinc-400">Connecting to Instagram...</p>}
      {status === 'done' && <p className="text-sm text-green-400">Connected! This window will close.</p>}
      {status === 'error' && (
        <div className="text-center space-y-2">
          <p className="text-sm text-red-400">
            {params.get('error_description') || 'OAuth authorization failed.'}
          </p>
          <p className="text-xs text-zinc-600">You can close this window.</p>
        </div>
      )}
    </div>
  )
}
