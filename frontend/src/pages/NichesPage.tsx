import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchNiches, createNiche, deleteNiche, updateNiche, type Niche } from '../api/niches'
import { Plus, Trash2, X } from 'lucide-react'

export default function NichesPage() {
  const qc = useQueryClient()
  const { data: niches = [], isLoading } = useQuery({ queryKey: ['niches'], queryFn: fetchNiches })
  const [selected, setSelected] = useState<Niche | null>(null)
  const [showNew, setShowNew] = useState(false)
  const [newName, setNewName] = useState('')
  const [newAccounts, setNewAccounts] = useState('')

  const createMut = useMutation({
    mutationFn: () => createNiche(newName.trim(), newAccounts.split('\n').map(s => s.trim()).filter(Boolean)),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['niches'] }); setShowNew(false); setNewName(''); setNewAccounts('') },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteNiche(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['niches'] }); setSelected(null) },
  })

  const [editAccounts, setEditAccounts] = useState('')
  const saveMut = useMutation({
    mutationFn: () => updateNiche(selected!.id, { accounts: editAccounts.split('\n').map(s => s.trim()).filter(Boolean) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['niches'] }),
  })

  return (
    <div className="flex h-full">
      {/* Left: list */}
      <div className="w-72 border-r border-zinc-800 p-4 space-y-2">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-bold text-white">Niches</h2>
          <button onClick={() => setShowNew(true)} className="p-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white">
            <Plus size={16} />
          </button>
        </div>
        {isLoading && <p className="text-zinc-500 text-sm">Loading...</p>}
        {niches.map(n => (
          <button
            key={n.id}
            onClick={() => { setSelected(n); setEditAccounts(n.accounts.map(a => a.username).join('\n')) }}
            className={`w-full text-left px-3 py-2 rounded-lg text-sm transition ${
              selected?.id === n.id ? 'bg-violet-600/20 text-violet-400' : 'text-zinc-300 hover:bg-zinc-800'
            }`}
          >
            {n.name}
            <span className="text-zinc-600 ml-2">{n.accounts.length} accts</span>
          </button>
        ))}
      </div>

      {/* Right: detail */}
      <div className="flex-1 p-6">
        {showNew ? (
          <div className="max-w-md space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">New Niche</h3>
              <button onClick={() => setShowNew(false)} className="text-zinc-500 hover:text-white"><X size={18} /></button>
            </div>
            <input value={newName} onChange={e => setNewName(e.target.value)} placeholder="Niche name" className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm" />
            <textarea value={newAccounts} onChange={e => setNewAccounts(e.target.value)} placeholder="Instagram accounts (one per line)" rows={6} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm" />
            <button onClick={() => createMut.mutate()} disabled={!newName.trim()} className="px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium">
              Create Niche
            </button>
          </div>
        ) : selected ? (
          <div className="max-w-md space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-semibold text-white">{selected.name}</h3>
              <button onClick={() => deleteMut.mutate(selected.id)} className="text-red-500 hover:text-red-400"><Trash2 size={18} /></button>
            </div>
            <label className="block text-xs text-zinc-500 uppercase">Target Accounts</label>
            <textarea value={editAccounts} onChange={e => setEditAccounts(e.target.value)} rows={8} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm font-mono" />
            <button onClick={() => saveMut.mutate()} className="px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white rounded-lg text-sm font-medium">
              Save Accounts
            </button>
          </div>
        ) : (
          <p className="text-zinc-500 mt-20 text-center">Select a niche or create a new one</p>
        )}
      </div>
    </div>
  )
}
