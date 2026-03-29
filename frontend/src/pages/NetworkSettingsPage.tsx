import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, Key, Copy, Users, Globe, Eye, EyeOff } from 'lucide-react'
import { fetchNetworks, createNetwork, updateNetwork, deleteNetwork, rotateApiKey, type Network } from '../api/networks'
import { useAppStore } from '../stores/appStore'

export default function NetworkSettingsPage() {
  const queryClient = useQueryClient()
  const { user, setNetworks } = useAppStore()
  const isOwner = user?.role === 'owner'

  const { data: networks = [] } = useQuery({
    queryKey: ['networks'],
    queryFn: fetchNetworks,
  })

  const [showCreate, setShowCreate] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)

  const refreshNetworks = () => {
    queryClient.invalidateQueries({ queryKey: ['networks'] })
    fetchNetworks().then(nets => {
      setNetworks(nets.map(n => ({ id: n.id, name: n.name, slug: n.slug })))
    })
  }

  return (
    <div className="p-6 max-w-4xl">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-bold text-white">Networks</h1>
          <p className="text-sm text-zinc-500 mt-1">Each network is an isolated set of Instagram accounts with its own API credentials</p>
        </div>
        {isOwner && (
          <button
            onClick={() => setShowCreate(true)}
            className="flex items-center gap-2 bg-violet-600 hover:bg-violet-500 text-white rounded-lg px-4 py-2 text-sm"
          >
            <Plus size={16} /> New Network
          </button>
        )}
      </div>

      {showCreate && (
        <CreateNetworkForm
          onDone={() => { setShowCreate(false); refreshNetworks() }}
          onCancel={() => setShowCreate(false)}
        />
      )}

      <div className="space-y-4">
        {networks.map(network => (
          <NetworkCard
            key={network.id}
            network={network}
            isOwner={isOwner}
            isEditing={editingId === network.id}
            onEdit={() => setEditingId(editingId === network.id ? null : network.id)}
            onRefresh={refreshNetworks}
          />
        ))}
      </div>
    </div>
  )
}

function CreateNetworkForm({ onDone, onCancel }: { onDone: () => void; onCancel: () => void }) {
  const [name, setName] = useState('')
  const [igAppId, setIgAppId] = useState('')
  const [igAppSecret, setIgAppSecret] = useState('')
  const [redirectUri, setRedirectUri] = useState('https://localhost:5173/auth/callback')
  const [publicUrl, setPublicUrl] = useState('')
  const [error, setError] = useState('')

  const mutation = useMutation({
    mutationFn: () => createNetwork({
      name,
      ig_app_id: igAppId,
      ig_app_secret: igAppSecret,
      ig_redirect_uri: redirectUri,
      public_url: publicUrl,
    }),
    onSuccess: onDone,
    onError: (err: any) => setError(err.response?.data?.detail || 'Failed'),
  })

  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-5 mb-6">
      <h3 className="text-sm font-medium text-white mb-4">Create Network</h3>
      <div className="grid grid-cols-2 gap-4">
        <Field label="Network Name" value={name} onChange={setName} placeholder="My Network" />
        <Field label="IG App ID" value={igAppId} onChange={setIgAppId} placeholder="From Meta Developer Portal" />
        <Field label="IG App Secret" value={igAppSecret} onChange={setIgAppSecret} placeholder="From Meta Developer Portal" type="password" />
        <Field label="OAuth Redirect URI" value={redirectUri} onChange={setRedirectUri} />
        <Field label="Public URL" value={publicUrl} onChange={setPublicUrl} placeholder="https://your-ngrok-url.app" className="col-span-2" />
      </div>
      {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
      <div className="flex gap-2 mt-4">
        <button onClick={() => mutation.mutate()} disabled={!name || mutation.isPending} className="bg-violet-600 hover:bg-violet-500 text-white rounded-lg px-4 py-1.5 text-sm disabled:opacity-50">
          {mutation.isPending ? 'Creating...' : 'Create'}
        </button>
        <button onClick={onCancel} className="text-zinc-400 hover:text-white text-sm px-4 py-1.5">Cancel</button>
      </div>
    </div>
  )
}

function NetworkCard({ network, isOwner, isEditing, onEdit, onRefresh }: {
  network: Network
  isOwner: boolean
  isEditing: boolean
  onEdit: () => void
  onRefresh: () => void
}) {
  const [showApiKey, setShowApiKey] = useState(false)
  const [copied, setCopied] = useState(false)

  const deleteMut = useMutation({
    mutationFn: () => deleteNetwork(network.id),
    onSuccess: onRefresh,
  })

  const rotateMut = useMutation({
    mutationFn: () => rotateApiKey(network.id),
    onSuccess: onRefresh,
  })

  const copyApiKey = () => {
    if (network.api_key) {
      navigator.clipboard.writeText(network.api_key)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Globe size={18} className="text-violet-400" />
          <div>
            <h3 className="text-sm font-medium text-white">{network.name}</h3>
            <p className="text-xs text-zinc-500">{network.slug} &middot; App ID: {network.ig_app_id || 'Not set'}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isOwner && (
            <>
              <button onClick={onEdit} className="text-xs text-zinc-400 hover:text-white px-2 py-1 rounded">
                {isEditing ? 'Close' : 'Edit'}
              </button>
              <button
                onClick={() => { if (confirm('Delete this network and all its data?')) deleteMut.mutate() }}
                className="text-zinc-500 hover:text-red-400 p-1"
              >
                <Trash2 size={14} />
              </button>
            </>
          )}
        </div>
      </div>

      {/* API Key section */}
      <div className="mt-4 pt-3 border-t border-zinc-800">
        <div className="flex items-center gap-2">
          <Key size={12} className="text-zinc-500" />
          <span className="text-xs text-zinc-500">API Key (for local app):</span>
          <code className="text-xs text-zinc-300 font-mono">
            {showApiKey ? network.api_key : '••••••••••••••••'}
          </code>
          <button onClick={() => setShowApiKey(!showApiKey)} className="text-zinc-500 hover:text-white">
            {showApiKey ? <EyeOff size={12} /> : <Eye size={12} />}
          </button>
          <button onClick={copyApiKey} className="text-zinc-500 hover:text-white">
            <Copy size={12} />
          </button>
          {copied && <span className="text-xs text-green-400">Copied!</span>}
          {isOwner && (
            <button onClick={() => rotateMut.mutate()} className="text-xs text-zinc-500 hover:text-yellow-400 ml-2">
              Rotate
            </button>
          )}
        </div>
      </div>

      {isEditing && (
        <EditNetworkForm network={network} onDone={() => { onEdit(); onRefresh() }} />
      )}
    </div>
  )
}

function EditNetworkForm({ network, onDone }: { network: Network; onDone: () => void }) {
  const [name, setName] = useState(network.name)
  const [igAppId, setIgAppId] = useState(network.ig_app_id || '')
  const [igAppSecret, setIgAppSecret] = useState('')
  const [redirectUri, setRedirectUri] = useState(network.ig_redirect_uri || '')
  const [publicUrl, setPublicUrl] = useState(network.public_url || '')
  const [error, setError] = useState('')

  const mutation = useMutation({
    mutationFn: () => updateNetwork(network.id, {
      name,
      ig_app_id: igAppId,
      ...(igAppSecret ? { ig_app_secret: igAppSecret } : {}),
      ig_redirect_uri: redirectUri,
      public_url: publicUrl,
    }),
    onSuccess: onDone,
    onError: (err: any) => setError(err.response?.data?.detail || 'Failed'),
  })

  return (
    <div className="mt-4 pt-4 border-t border-zinc-800">
      <div className="grid grid-cols-2 gap-3">
        <Field label="Name" value={name} onChange={setName} />
        <Field label="IG App ID" value={igAppId} onChange={setIgAppId} />
        <Field label="IG App Secret" value={igAppSecret} onChange={setIgAppSecret} placeholder="Leave blank to keep current" type="password" />
        <Field label="Redirect URI" value={redirectUri} onChange={setRedirectUri} />
        <Field label="Public URL" value={publicUrl} onChange={setPublicUrl} className="col-span-2" />
      </div>
      {error && <p className="text-red-400 text-xs mt-2">{error}</p>}
      <button onClick={() => mutation.mutate()} disabled={mutation.isPending} className="mt-3 bg-violet-600 hover:bg-violet-500 text-white rounded-lg px-4 py-1.5 text-sm disabled:opacity-50">
        {mutation.isPending ? 'Saving...' : 'Save'}
      </button>
    </div>
  )
}

function Field({ label, value, onChange, placeholder, type, className }: {
  label: string; value: string; onChange: (v: string) => void
  placeholder?: string; type?: string; className?: string
}) {
  return (
    <div className={className}>
      <label className="block text-xs text-zinc-400 mb-1">{label}</label>
      <input
        type={type || 'text'}
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-sm text-white focus:outline-none focus:border-violet-500"
      />
    </div>
  )
}
