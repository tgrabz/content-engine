import { useState, useRef, useEffect, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  fetchTemplates, createTemplate, generateTemplate, updateTemplate, deleteTemplate,
  templateImageUrl,
} from '../api/templates'
import { useAppStore } from '../stores/appStore'
import TemplateCanvas from '../components/templates/TemplateCanvas'
import {
  Trash2, Edit3, X, Upload, Save, Loader2, Layers, ArrowLeft, Wand2, BadgeCheck,
} from 'lucide-react'

type Box = [number, number, number, number]

const DEFAULT_VIDEO_BOX: Box = [0.06, 0.18, 0.94, 0.94]
const DEFAULT_CAPTION_BOX: Box = [0.06, 0.08, 0.94, 0.16]

function parseBox(json: string): Box {
  try {
    const arr = JSON.parse(json)
    if (Array.isArray(arr) && arr.length === 4) return arr as Box
  } catch { /* fallback */ }
  return DEFAULT_VIDEO_BOX
}

export default function TemplatesPage() {
  const queryClient = useQueryClient()
  const activeProfileId = useAppStore(s => s.activeProfileId)
  const { data: templates = [] } = useQuery({
    queryKey: ['templates', activeProfileId],
    queryFn: () => fetchTemplates(activeProfileId ?? undefined),
  })

  // Builder state
  const [mode, setMode] = useState<'list' | 'create' | 'edit' | 'generate'>('list')
  const [editId, setEditId] = useState<number | null>(null)
  const [name, setName] = useState('')
  const [imageFile, setImageFile] = useState<File | null>(null)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const [videoBox, setVideoBox] = useState<Box>(DEFAULT_VIDEO_BOX)
  const [captionBox, setCaptionBox] = useState<Box>(DEFAULT_CAPTION_BOX)
  const fileRef = useRef<HTMLInputElement>(null)

  // Generate-specific state
  const [genDisplayName, setGenDisplayName] = useState('')
  const [genHandle, setGenHandle] = useState('')
  const [genVerified, setGenVerified] = useState(true)
  const [genPfpFile, setGenPfpFile] = useState<File | null>(null)
  const [genPfpPreview, setGenPfpPreview] = useState<string | null>(null)
  const genPfpRef = useRef<HTMLInputElement>(null)

  // Canvas sizing
  const containerRef = useRef<HTMLDivElement>(null)
  const [canvasSize, setCanvasSize] = useState({ w: 0, h: 0 })

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => {
      const h = el.clientHeight
      const w = Math.floor(h * (9 / 16))
      setCanvasSize({ w, h })
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [mode])

  // When editing, load template data
  useEffect(() => {
    if (mode === 'edit' && editId) {
      const tmpl = templates.find(t => t.id === editId)
      if (tmpl) {
        setName(tmpl.name)
        setVideoBox(parseBox(tmpl.video_box))
        setCaptionBox(parseBox(tmpl.caption_box))
        setImagePreview(templateImageUrl(tmpl.id))
        setImageFile(null)
      }
    }
  }, [mode, editId, templates])

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImageFile(file)
    const url = URL.createObjectURL(file)
    setImagePreview(url)
  }

  const resetBuilder = () => {
    setMode('list')
    setEditId(null)
    setName('')
    setImageFile(null)
    setImagePreview(null)
    setVideoBox(DEFAULT_VIDEO_BOX)
    setCaptionBox(DEFAULT_CAPTION_BOX)
    setGenDisplayName('')
    setGenHandle('')
    setGenVerified(true)
    setGenPfpFile(null)
    setGenPfpPreview(null)
  }

  // Create mutation
  const createMut = useMutation({
    mutationFn: async () => {
      if (!imageFile || !name.trim()) throw new Error('Name and image required')
      const form = new FormData()
      form.append('name', name.trim())
      form.append('image', imageFile)
      form.append('video_box', JSON.stringify(videoBox))
      form.append('caption_box', JSON.stringify(captionBox))
      if (activeProfileId) form.append('profile_id', String(activeProfileId))
      return createTemplate(form)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['templates'] })
      resetBuilder()
    },
  })

  // Update mutation
  const updateMut = useMutation({
    mutationFn: async () => {
      if (!editId || !name.trim()) throw new Error('Name required')
      return updateTemplate(editId, {
        name: name.trim(),
        video_box: JSON.stringify(videoBox),
        caption_box: JSON.stringify(captionBox),
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['templates'] })
      resetBuilder()
    },
  })

  // Delete mutation
  const deleteMut = useMutation({
    mutationFn: (id: number) => deleteTemplate(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['templates'] }),
  })

  // Generate mutation
  const generateMut = useMutation({
    mutationFn: async () => {
      if (!genPfpFile || !genDisplayName.trim() || !genHandle.trim()) {
        throw new Error('Display name, handle, and profile picture required')
      }
      const form = new FormData()
      form.append('name', name.trim() || genDisplayName.trim())
      form.append('display_name', genDisplayName.trim())
      form.append('handle', genHandle.trim())
      form.append('verified', String(genVerified))
      form.append('pfp', genPfpFile)
      if (activeProfileId) form.append('profile_id', String(activeProfileId))
      return generateTemplate(form)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['templates'] })
      resetBuilder()
    },
  })

  const handleVideoBoxChange = useCallback((box: Box) => setVideoBox(box), [])
  const handleCaptionBoxChange = useCallback((box: Box) => setCaptionBox(box), [])

  // ──── List Mode ────
  if (mode === 'list') {
    return (
      <div className="p-8 max-w-5xl">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold text-white">Templates</h2>
            <p className="text-zinc-500 text-sm mt-1">Frame overlays with video &amp; caption placement guides</p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => { resetBuilder(); setMode('generate') }}
              className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white rounded-lg text-sm font-medium transition-colors"
            >
              <Wand2 size={16} /> Generate
            </button>
            <button
              onClick={() => { resetBuilder(); setMode('create') }}
              className="flex items-center gap-2 px-4 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 text-zinc-300 rounded-lg text-sm font-medium transition-colors"
            >
              <Upload size={16} /> Upload
            </button>
          </div>
        </div>

        {templates.length === 0 ? (
          <div className="text-center py-20">
            <Layers size={48} className="mx-auto mb-4 text-zinc-700" />
            <p className="text-zinc-500 text-sm">No templates yet. Create one to get started.</p>
          </div>
        ) : (
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
            {templates.map(t => (
              <div
                key={t.id}
                className="group rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden hover:border-zinc-700 transition-colors"
              >
                <div className="relative aspect-[9/16] bg-zinc-800">
                  <img
                    src={templateImageUrl(t.id)}
                    alt={t.name}
                    className="w-full h-full object-cover"
                    onError={e => (e.currentTarget.style.display = 'none')}
                  />
                  {/* Overlay actions */}
                  <div className="absolute inset-0 bg-black/0 group-hover:bg-black/50 transition-colors flex items-center justify-center gap-2 opacity-0 group-hover:opacity-100">
                    <button
                      onClick={() => { setEditId(t.id); setMode('edit') }}
                      className="p-2 bg-zinc-800/90 hover:bg-zinc-700 rounded-lg transition-colors"
                      title="Edit"
                    >
                      <Edit3 size={14} className="text-white" />
                    </button>
                    <button
                      onClick={() => {
                        if (confirm(`Delete "${t.name}"?`)) deleteMut.mutate(t.id)
                      }}
                      className="p-2 bg-zinc-800/90 hover:bg-red-600 rounded-lg transition-colors"
                      title="Delete"
                    >
                      <Trash2 size={14} className="text-white" />
                    </button>
                  </div>
                </div>
                <div className="px-3 py-2">
                  <p className="text-sm text-white font-medium truncate">{t.name}</p>
                  <p className="text-[10px] text-zinc-500 mt-0.5">
                    {t.profile_id ? `Profile #${t.profile_id}` : 'Global'}
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    )
  }

  // ──── Generate Mode ────
  if (mode === 'generate') {
    return (
      <div className="flex items-center justify-center h-screen bg-zinc-950 p-8">
        <div className="w-full max-w-md bg-zinc-900 border border-zinc-800 rounded-2xl overflow-hidden">
          <div className="px-5 py-4 border-b border-zinc-800 flex items-center justify-between">
            <button
              onClick={resetBuilder}
              className="flex items-center gap-1.5 text-zinc-400 hover:text-white text-xs transition-colors"
            >
              <ArrowLeft size={14} /> Back
            </button>
            <h2 className="text-sm font-bold text-white">Generate Template</h2>
          </div>
          <div className="p-5 space-y-4">
            {/* Template Name */}
            <div>
              <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
                Template Name
              </label>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="e.g. TeachYouZone Main"
                className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm"
              />
            </div>

            {/* Display Name */}
            <div>
              <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
                Display Name
              </label>
              <input
                type="text"
                value={genDisplayName}
                onChange={e => setGenDisplayName(e.target.value)}
                placeholder="TeachYouZone"
                className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm"
              />
            </div>

            {/* Handle */}
            <div>
              <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
                Handle
              </label>
              <input
                type="text"
                value={genHandle}
                onChange={e => setGenHandle(e.target.value)}
                placeholder="@teachyouzone"
                className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm"
              />
            </div>

            {/* Profile Picture Upload */}
            <div>
              <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
                Profile Picture
              </label>
              <input
                ref={genPfpRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={e => {
                  const f = e.target.files?.[0]
                  if (!f) return
                  setGenPfpFile(f)
                  setGenPfpPreview(URL.createObjectURL(f))
                }}
                className="hidden"
              />
              <div className="flex items-center gap-3 mt-1">
                {genPfpPreview ? (
                  <img src={genPfpPreview} alt="" className="w-12 h-12 rounded-full object-cover border border-zinc-700" />
                ) : (
                  <div className="w-12 h-12 rounded-full bg-zinc-800 border border-zinc-700 flex items-center justify-center">
                    <Upload size={14} className="text-zinc-600" />
                  </div>
                )}
                <button
                  onClick={() => genPfpRef.current?.click()}
                  className="flex-1 flex items-center justify-center gap-2 px-3 py-2.5 bg-zinc-800 hover:bg-zinc-700 border border-dashed border-zinc-600 rounded-lg text-xs text-zinc-300 transition-colors"
                >
                  <Upload size={14} />
                  {genPfpFile ? genPfpFile.name : 'Choose image'}
                </button>
              </div>
            </div>

            {/* Verified Toggle */}
            <div className="flex items-center justify-between">
              <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold flex items-center gap-1.5">
                <BadgeCheck size={12} /> Verified Badge
              </label>
              <button
                onClick={() => setGenVerified(!genVerified)}
                className={`relative w-10 h-5 rounded-full transition-colors ${
                  genVerified ? 'bg-violet-600' : 'bg-zinc-700'
                }`}
              >
                <div className={`absolute top-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                  genVerified ? 'left-[22px]' : 'left-0.5'
                }`} />
              </button>
            </div>

            {/* Error */}
            {generateMut.isError && (
              <p className="text-red-400 text-xs">Failed to generate template.</p>
            )}

            {/* Actions */}
            <div className="flex gap-2 pt-2">
              <button
                onClick={resetBuilder}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-xs text-zinc-300 transition-colors"
              >
                <X size={13} /> Cancel
              </button>
              <button
                onClick={() => generateMut.mutate()}
                disabled={generateMut.isPending || !genDisplayName.trim() || !genHandle.trim() || !genPfpFile}
                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 bg-violet-600 hover:bg-violet-500 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
              >
                {generateMut.isPending ? (
                  <><Loader2 size={13} className="animate-spin" /> Generating...</>
                ) : (
                  <><Wand2 size={13} /> Generate</>
                )}
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ──── Create/Edit Mode ────
  const isEditing = mode === 'edit'
  const isSaving = createMut.isPending || updateMut.isPending

  return (
    <div className="flex h-screen overflow-hidden">
      {/* Center: Canvas */}
      <div className="flex-1 flex items-center justify-center bg-zinc-950 p-6">
        <div ref={containerRef} className="h-full max-h-full" style={{ aspectRatio: '9/16' }}>
          {canvasSize.w > 0 && canvasSize.h > 0 && imagePreview ? (
            <TemplateCanvas
              width={canvasSize.w}
              height={canvasSize.h}
              imageUrl={imagePreview}
              videoBox={videoBox}
              captionBox={captionBox}
              onVideoBoxChange={handleVideoBoxChange}
              onCaptionBoxChange={handleCaptionBoxChange}
            />
          ) : (
            <div className="h-full flex items-center justify-center text-zinc-600 border-2 border-dashed border-zinc-800 rounded-xl">
              <div className="text-center">
                <Upload size={40} className="mx-auto mb-3 opacity-30" />
                <p className="text-sm">Upload a template image to start</p>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Right: Controls */}
      <div className="w-80 border-l border-zinc-800 bg-zinc-900 flex flex-col h-full overflow-auto">
        {/* Header */}
        <div className="px-4 py-3 border-b border-zinc-800 flex items-center justify-between">
          <button
            onClick={resetBuilder}
            className="flex items-center gap-1.5 text-zinc-400 hover:text-white text-xs transition-colors"
          >
            <ArrowLeft size={14} /> Back
          </button>
          <h2 className="text-sm font-bold text-white">
            {isEditing ? 'Edit Template' : 'New Template'}
          </h2>
        </div>

        <div className="p-4 space-y-5">
          {/* Name */}
          <section>
            <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="My Template"
              className="w-full mt-1 bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-white text-sm"
            />
          </section>

          {/* Image Upload */}
          {!isEditing && (
            <section>
              <label className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold">
                Template Image
              </label>
              <input
                ref={fileRef}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                onChange={handleFileChange}
                className="hidden"
              />
              <button
                onClick={() => fileRef.current?.click()}
                className="w-full mt-1 flex items-center justify-center gap-2 px-3 py-3 bg-zinc-800 hover:bg-zinc-700 border border-dashed border-zinc-600 rounded-lg text-xs text-zinc-300 transition-colors"
              >
                <Upload size={14} />
                {imageFile ? imageFile.name : 'Choose PNG / JPG'}
              </button>
            </section>
          )}

          {/* Video Box */}
          <section>
            <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1.5 flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-sm bg-violet-500" />
              Video Box
            </h3>
            <p className="text-[10px] text-zinc-600 mb-2">
              Drag &amp; resize the purple rectangle on the canvas
            </p>
            <div className="grid grid-cols-4 gap-1.5">
              {(['x1', 'y1', 'x2', 'y2'] as const).map((label, i) => (
                <div key={label}>
                  <label className="text-[9px] text-zinc-600 uppercase block text-center">{label}</label>
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={videoBox[i].toFixed(2)}
                    onChange={e => {
                      const next = [...videoBox] as Box
                      next[i] = Math.max(0, Math.min(1, Number(e.target.value)))
                      setVideoBox(next)
                    }}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded px-1.5 py-1 text-[10px] text-zinc-300 text-center font-mono"
                  />
                </div>
              ))}
            </div>
          </section>

          {/* Caption Box */}
          <section>
            <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-1.5 flex items-center gap-1.5">
              <div className="w-2 h-2 rounded-sm bg-amber-500" />
              Caption Box
            </h3>
            <p className="text-[10px] text-zinc-600 mb-2">
              Drag &amp; resize the amber rectangle on the canvas
            </p>
            <div className="grid grid-cols-4 gap-1.5">
              {(['x1', 'y1', 'x2', 'y2'] as const).map((label, i) => (
                <div key={label}>
                  <label className="text-[9px] text-zinc-600 uppercase block text-center">{label}</label>
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step={0.01}
                    value={captionBox[i].toFixed(2)}
                    onChange={e => {
                      const next = [...captionBox] as Box
                      next[i] = Math.max(0, Math.min(1, Number(e.target.value)))
                      setCaptionBox(next)
                    }}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded px-1.5 py-1 text-[10px] text-zinc-300 text-center font-mono"
                  />
                </div>
              ))}
            </div>
          </section>

          {/* Preset Layouts */}
          <section>
            <h3 className="text-[10px] text-zinc-500 uppercase tracking-wider font-semibold mb-2">
              Presets
            </h3>
            <div className="grid grid-cols-2 gap-1.5">
              <button
                onClick={() => {
                  setVideoBox([0.06, 0.18, 0.94, 0.94])
                  setCaptionBox([0.06, 0.06, 0.94, 0.16])
                }}
                className="px-2 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-[10px] text-zinc-300 transition-colors"
              >
                Standard
              </button>
              <button
                onClick={() => {
                  setVideoBox([0.06, 0.28, 0.94, 0.94])
                  setCaptionBox([0.06, 0.06, 0.94, 0.26])
                }}
                className="px-2 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-[10px] text-zinc-300 transition-colors"
              >
                Large Caption
              </button>
              <button
                onClick={() => {
                  setVideoBox([0.04, 0.04, 0.96, 0.82])
                  setCaptionBox([0.06, 0.84, 0.94, 0.96])
                }}
                className="px-2 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-[10px] text-zinc-300 transition-colors"
              >
                Caption Below
              </button>
              <button
                onClick={() => {
                  setVideoBox([0.0, 0.0, 1.0, 1.0])
                  setCaptionBox([0.06, 0.04, 0.94, 0.12])
                }}
                className="px-2 py-2 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-[10px] text-zinc-300 transition-colors"
              >
                Fullscreen
              </button>
            </div>
          </section>

          {/* Error */}
          {(createMut.isError || updateMut.isError) && (
            <p className="text-red-400 text-xs">
              {isEditing ? 'Failed to update template.' : 'Failed to create template.'}
            </p>
          )}

          {/* Save / Cancel */}
          <div className="flex gap-2 pt-2">
            <button
              onClick={resetBuilder}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-lg text-xs text-zinc-300 transition-colors"
            >
              <X size={13} /> Cancel
            </button>
            <button
              onClick={() => isEditing ? updateMut.mutate() : createMut.mutate()}
              disabled={isSaving || !name.trim() || (!isEditing && !imageFile)}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 bg-violet-600 hover:bg-violet-500 text-white rounded-lg text-xs font-medium transition-colors disabled:opacity-50"
            >
              {isSaving ? (
                <><Loader2 size={13} className="animate-spin" /> Saving...</>
              ) : (
                <><Save size={13} /> {isEditing ? 'Update' : 'Create'}</>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
