import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchProfiles, createProfile, deleteProfile, type Profile } from '../api/profiles'
import { fetchCredentials, createCredential, deleteCredential, type Credential } from '../api/credentials'
import { fetchNiches } from '../api/niches'
import { Plus, Trash2, User, KeyRound } from 'lucide-react'

export default function SettingsPage() {
  const qc = useQueryClient()
  const { data: profiles = [] } = useQuery({ queryKey: ['profiles'], queryFn: fetchProfiles })
  const { data: credentials = [] } = useQuery({ queryKey: ['credentials'], queryFn: fetchCredentials })
  const { data: niches = [] } = useQuery({ queryKey: ['niches'], queryFn: fetchNiches })

  // New profile form
  const [pName, setPName] = useState('')
  const [pNiche, setPNiche] = useState<number | ''>('')
  const createProf = useMutation({
    mutationFn: () => createProfile({ name: pName.trim(), niche_id: pNiche || undefined, export_dir: pName.trim().toLowerCase().replace(/\s+/g, '-') }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['profiles'] }); setPName(''); setPNiche('') },
  })
  const deleteProf = useMutation({
    mutationFn: (id: number) => deleteProfile(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profiles'] }),
  })

  // New credential form
  const [cUser, setCUser] = useState('')
  const [cPass, setCPass] = useState('')
  const createCred = useMutation({
    mutationFn: () => createCredential(cUser.trim(), cPass),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['credentials'] }); setCUser(''); setCPass('') },
  })
  const deleteCred = useMutation({
    mutationFn: (id: number) => deleteCredential(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['credentials'] }),
  })

  return (
    <div className="p-8 max-w-2xl space-y-10">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">Settings</h2>
        <p className="text-zinc-400 text-sm">Manage profiles and Instagram login credentials.</p>
      </div>

      {/* Profiles */}
      <section>
        <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-3 flex items-center gap-2">
          <User size={14} /> Profiles
        </h3>
        <div className="space-y-2 mb-4">
          {profiles.map(p => (
            <div key={p.id} className="flex items-center justify-between bg-zinc-800/50 border border-zinc-700 rounded-lg px-4 py-2.5">
              <div>
                <span className="text-white text-sm font-medium">{p.name}</span>
                {p.niche_id && (
                  <span className="text-zinc-500 text-xs ml-2">
                    niche: {niches.find(n => n.id === p.niche_id)?.name || p.niche_id}
                  </span>
                )}
              </div>
              <button onClick={() => deleteProf.mutate(p.id)} className="text-zinc-600 hover:text-red-400"><Trash2 size={15} /></button>
            </div>
          ))}
          {profiles.length === 0 && <p className="text-zinc-600 text-sm">No profiles yet.</p>}
        </div>
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <label className="text-xs text-zinc-500">Name</label>
            <input value={pName} onChange={e => setPName(e.target.value)} placeholder="e.g. Teachyouvids" className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-white text-sm mt-1" />
          </div>
          <div className="w-40">
            <label className="text-xs text-zinc-500">Niche</label>
            <select value={pNiche} onChange={e => setPNiche(e.target.value ? Number(e.target.value) : '')} className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-white text-sm mt-1">
              <option value="">None</option>
              {niches.map(n => <option key={n.id} value={n.id}>{n.name}</option>)}
            </select>
          </div>
          <button onClick={() => createProf.mutate()} disabled={!pName.trim()} className="px-3 py-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white rounded-lg text-sm">
            <Plus size={16} />
          </button>
        </div>
      </section>

      {/* Credentials */}
      <section>
        <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-3 flex items-center gap-2">
          <KeyRound size={14} /> Instagram Login Credentials
        </h3>
        <p className="text-xs text-zinc-600 mb-3">Used by the scraper to log into Instagram. Passwords are encrypted at rest.</p>
        <div className="space-y-2 mb-4">
          {credentials.map(c => (
            <div key={c.id} className="flex items-center justify-between bg-zinc-800/50 border border-zinc-700 rounded-lg px-4 py-2.5">
              <span className="text-white text-sm font-mono">@{c.username}</span>
              <button onClick={() => deleteCred.mutate(c.id)} className="text-zinc-600 hover:text-red-400"><Trash2 size={15} /></button>
            </div>
          ))}
          {credentials.length === 0 && <p className="text-zinc-600 text-sm">No credentials saved.</p>}
        </div>
        <div className="flex gap-2 items-end">
          <div className="flex-1">
            <label className="text-xs text-zinc-500">Username</label>
            <input value={cUser} onChange={e => setCUser(e.target.value)} placeholder="instagram_username" className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-white text-sm mt-1 font-mono" />
          </div>
          <div className="flex-1">
            <label className="text-xs text-zinc-500">Password</label>
            <input type="password" value={cPass} onChange={e => setCPass(e.target.value)} placeholder="password" className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-1.5 text-white text-sm mt-1" />
          </div>
          <button onClick={() => createCred.mutate()} disabled={!cUser.trim() || !cPass} className="px-3 py-1.5 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white rounded-lg text-sm">
            <Plus size={16} />
          </button>
        </div>
      </section>
    </div>
  )
}
