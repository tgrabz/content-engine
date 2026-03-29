import { useEffect, useState, useCallback } from 'react'
import { CheckCircle, XCircle, Info, X } from 'lucide-react'

type ToastType = 'success' | 'error' | 'info'

interface ToastMessage {
  id: number
  type: ToastType
  text: string
}

let _addToast: ((type: ToastType, text: string) => void) | null = null

/** Imperative toast API — call from anywhere. */
export const toast = {
  success: (text: string) => _addToast?.('success', text),
  error: (text: string) => _addToast?.('error', text),
  info: (text: string) => _addToast?.('info', text),
}

const ICONS = {
  success: <CheckCircle size={15} className="text-green-400 flex-shrink-0" />,
  error: <XCircle size={15} className="text-red-400 flex-shrink-0" />,
  info: <Info size={15} className="text-blue-400 flex-shrink-0" />,
}

const BORDER_COLORS = {
  success: 'border-green-500/30',
  error: 'border-red-500/30',
  info: 'border-blue-500/30',
}

export default function ToastContainer() {
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  const addToast = useCallback((type: ToastType, text: string) => {
    const id = Date.now() + Math.random()
    setToasts(prev => [...prev, { id, type, text }])
  }, [])

  const removeToast = useCallback((id: number) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  useEffect(() => {
    _addToast = addToast
    return () => { _addToast = null }
  }, [addToast])

  // Auto-dismiss after 4 seconds
  useEffect(() => {
    if (toasts.length === 0) return
    const timer = setTimeout(() => {
      setToasts(prev => prev.slice(1))
    }, 4000)
    return () => clearTimeout(timer)
  }, [toasts])

  if (toasts.length === 0) return null

  return (
    <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 max-w-sm">
      {toasts.map(t => (
        <div
          key={t.id}
          className={`flex items-start gap-2.5 px-4 py-3 bg-zinc-900 border ${BORDER_COLORS[t.type]} rounded-xl shadow-xl animate-in slide-in-from-right-5`}
        >
          {ICONS[t.type]}
          <p className="text-sm text-zinc-200 flex-1">{t.text}</p>
          <button onClick={() => removeToast(t.id)} className="text-zinc-500 hover:text-white">
            <X size={13} />
          </button>
        </div>
      ))}
    </div>
  )
}
