import { useState, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { fetchProfiles, createProfile, deleteProfile, checkUsernames, type UsernameCheckResult } from '../api/profiles'
import { fetchCredentials, createCredential, deleteCredential } from '../api/credentials'
import { fetchNiches } from '../api/niches'
import {
  getOAuthUrl,
  handleOAuthCallback,
  saveOAuthTokens,
  getProfileToken,
  deleteProfileToken,
  type OAuthToken,
} from '../api/auth'
import { Plus, Trash2, User, KeyRound, Instagram, Unlink, Loader2, Check, Search, CheckCircle, XCircle } from 'lucide-react'

export default function SettingsPage() {
  const qc = useQueryClient()
  const { data: profilesRaw } = useQuery({ queryKey: ['profiles'], queryFn: fetchProfiles })
  const profiles = Array.isArray(profilesRaw) ? profilesRaw : []
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

  // OAuth connect state
  const [connectingProfileId, setConnectingProfileId] = useState<number | null>(null)
  const [oauthLoading, setOauthLoading] = useState(false)
  const [oauthError, setOauthError] = useState<string | null>(null)

  // Fetch token status for all profiles
  const { data: profileTokens = {} } = useQuery({
    queryKey: ['profile-tokens', profiles.map(p => p.id).join(',')],
    queryFn: async () => {
      const tokens: Record<number, OAuthToken | null> = {}
      await Promise.all(
        profiles.map(async (p) => {
          try {
            tokens[p.id] = await getProfileToken(p.id)
          } catch {
            tokens[p.id] = null
          }
        })
      )
      return tokens
    },
    enabled: profiles.length > 0,
  })

  // Listen for OAuth popup callback
  const handleMessage = useCallback(async (event: MessageEvent) => {
    if (event.origin !== window.location.origin) return
    if (event.data?.type !== 'oauth-callback') return

    if (event.data.error) {
      setOauthError(event.data.error_description || 'Authorization was denied.')
      setOauthLoading(false)
      return
    }

    const { code, state } = event.data
    if (!code || !state || !connectingProfileId) return

    try {
      setOauthLoading(true)
      setOauthError(null)

      // Exchange code for tokens and get user info
      const result = await handleOAuthCallback(code, state)

      // Save tokens + auto-generate template from IG name/pfp
      await saveOAuthTokens({
        profile_id: connectingProfileId,
        ig_user_id: result.ig_user_id,
        username: result.username,
        access_token: result.access_token,
        name: result.name,
        profile_picture_url: result.profile_picture_url,
      })

      qc.invalidateQueries({ queryKey: ['profile-tokens'] })
      qc.invalidateQueries({ queryKey: ['profiles'] })
      qc.invalidateQueries({ queryKey: ['templates'] })
      setConnectingProfileId(null)
      setOauthError(null)
    } catch (err: any) {
      setOauthError(err?.response?.data?.detail || err?.message || 'OAuth flow failed.')
    } finally {
      setOauthLoading(false)
    }
  }, [connectingProfileId, qc])

  useEffect(() => {
    window.addEventListener('message', handleMessage)
    return () => window.removeEventListener('message', handleMessage)
  }, [handleMessage])

  async function startConnect(profileId: number) {
    setConnectingProfileId(profileId)
    setOauthError(null)

    try {
      setOauthLoading(true)
      const { auth_url } = await getOAuthUrl()

      // Open popup
      const w = 600, h = 700
      const left = window.screenX + (window.outerWidth - w) / 2
      const top = window.screenY + (window.outerHeight - h) / 2
      const popup = window.open(
        auth_url,
        'instagram-oauth',
        `width=${w},height=${h},left=${left},top=${top},toolbar=no,menubar=no`
      )

      if (!popup) {
        setOauthError('Popup was blocked. Please allow popups for this site.')
        setOauthLoading(false)
        return
      }

      // Poll for popup close (user cancelled)
      const interval = setInterval(() => {
        if (popup.closed) {
          clearInterval(interval)
          setTimeout(() => {
            setOauthLoading(false)
            setConnectingProfileId(prev => {
              if (prev === profileId) return null
              return prev
            })
          }, 1500)
        }
      }, 500)
    } catch (err: any) {
      setOauthError(err?.response?.data?.detail || err?.message || 'Failed to start OAuth flow.')
      setOauthLoading(false)
    }
  }

  // Username checker
  const [usernameInput, setUsernameInput] = useState('')
  const [usernameResults, setUsernameResults] = useState<UsernameCheckResult[]>([])
  const [checkingUsernames, setCheckingUsernames] = useState(false)

  async function handleCheckUsernames() {
    const names = usernameInput.split(/[\n,]+/).map(s => s.trim()).filter(Boolean)
    if (!names.length) return
    setCheckingUsernames(true)
    try {
      const results = await checkUsernames(names)
      setUsernameResults(results)
    } catch {
      setUsernameResults([])
    } finally {
      setCheckingUsernames(false)
    }
  }

  const disconnectToken = useMutation({
    mutationFn: (profileId: number) => deleteProfileToken(profileId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['profile-tokens'] }),
  })

  return (
    <div className="p-8 max-w-2xl space-y-10">
      <div>
        <h2 className="text-2xl font-bold text-white mb-1">Settings</h2>
        <p className="text-zinc-400 text-sm">Manage profiles, Instagram connections, and login credentials.</p>
      </div>

      {/* Profiles */}
      <section>
        <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-3 flex items-center gap-2">
          <User size={14} /> Profiles
        </h3>
        <div className="space-y-2 mb-4">
          {profiles.map(p => {
            const token = profileTokens[p.id]
            const isConnecting = connectingProfileId === p.id
            return (
              <div key={p.id} className="bg-zinc-800/50 border border-zinc-700 rounded-lg px-4 py-3">
                <div className="flex items-center justify-between">
                  <div>
                    <span className="text-white text-sm font-medium">{p.name}</span>
                    {p.niche_id && (
                      <span className="text-zinc-500 text-xs ml-2">
                        niche: {niches.find(n => n.id === p.niche_id)?.name || p.niche_id}
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {token ? (
                      <>
                        <span className="text-xs text-green-400 flex items-center gap-1">
                          <Check size={12} /> Connected
                        </span>
                        <button
                          onClick={() => disconnectToken.mutate(p.id)}
                          className="text-zinc-600 hover:text-orange-400 transition-colors"
                          title="Disconnect Instagram"
                        >
                          <Unlink size={15} />
                        </button>
                      </>
                    ) : (
                      <button
                        onClick={() => startConnect(p.id)}
                        disabled={oauthLoading}
                        className="flex items-center gap-1.5 px-2.5 py-1 bg-gradient-to-r from-purple-600 to-pink-600 hover:from-purple-500 hover:to-pink-500 disabled:opacity-50 text-white rounded-md text-xs font-medium transition-all"
                      >
                        {isConnecting && oauthLoading ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <Instagram size={12} />
                        )}
                        Connect
                      </button>
                    )}
                    <button onClick={() => deleteProf.mutate(p.id)} className="text-zinc-600 hover:text-red-400 transition-colors">
                      <Trash2 size={15} />
                    </button>
                  </div>
                </div>

                {/* Error display */}
                {isConnecting && oauthError && (
                  <div className="mt-2 pt-2 border-t border-zinc-700">
                    <p className="text-xs text-red-400">{oauthError}</p>
                    <button
                      onClick={() => { setOauthError(null); setConnectingProfileId(null) }}
                      className="mt-1 text-xs text-zinc-500 hover:text-zinc-300"
                    >
                      Dismiss
                    </button>
                  </div>
                )}
              </div>
            )
          })}
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

      {/* Username Checker */}
      <section>
        <h3 className="text-sm font-semibold text-zinc-300 uppercase tracking-wider mb-3 flex items-center gap-2">
          <Search size={14} /> Username Availability Checker
        </h3>
        <p className="text-xs text-zinc-600 mb-3">Check if Instagram usernames are available. Enter one per line or comma-separated.</p>
        <div className="flex gap-2 items-end mb-3">
          <div className="flex-1">
            <textarea
              value={usernameInput}
              onChange={e => setUsernameInput(e.target.value)}
              placeholder={"teachyouscience\nlearnwithme\ndailyknowledge"}
              rows={3}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm font-mono resize-none"
            />
          </div>
          <button
            onClick={handleCheckUsernames}
            disabled={checkingUsernames || !usernameInput.trim()}
            className="px-4 py-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white rounded-lg text-sm font-medium flex items-center gap-1.5 self-start mt-1"
          >
            {checkingUsernames ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
            Check
          </button>
        </div>
        {usernameResults.length > 0 && (
          <div className="space-y-1.5">
            {usernameResults.map(r => (
              <div key={r.username} className={`flex items-center gap-2 px-3 py-2 rounded-lg border ${
                r.available
                  ? 'border-green-500/30 bg-green-500/5'
                  : 'border-zinc-700 bg-zinc-800/50'
              }`}>
                {r.available ? (
                  <CheckCircle size={14} className="text-green-400 flex-shrink-0" />
                ) : (
                  <XCircle size={14} className="text-zinc-500 flex-shrink-0" />
                )}
                <span className={`text-sm font-mono ${r.available ? 'text-green-400' : 'text-zinc-500'}`}>
                  @{r.username}
                </span>
                <span className={`text-xs ml-auto ${r.available ? 'text-green-400' : 'text-zinc-600'}`}>
                  {r.error ? r.error : r.available ? 'Available' : 'Taken'}
                </span>
              </div>
            ))}
          </div>
        )}
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
