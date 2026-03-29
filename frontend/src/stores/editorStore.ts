import { create } from 'zustand'

interface EditorState {
  videoId: number | null
  templateId: number | null
  sessionId: number | null
  frameTimestamp: number
  cropBox: [number, number, number, number]
  captionBox: [number, number, number, number] | null  // null = use template default
  paddingPct: number
  offsetX: number
  offsetY: number
  captionText: string
  captionColor: string
  postCaption: string
  isDirty: boolean

  setVideo: (id: number | null) => void
  setTemplate: (id: number | null) => void
  setSessionId: (id: number | null) => void
  setFrameTimestamp: (t: number) => void
  setCropBox: (box: [number, number, number, number]) => void
  setCaptionBox: (box: [number, number, number, number] | null) => void
  setPaddingPct: (pct: number) => void
  setOffsetX: (x: number) => void
  setOffsetY: (y: number) => void
  setCaptionText: (text: string) => void
  setCaptionColor: (color: string) => void
  setPostCaption: (text: string) => void
  markDirty: () => void
  markClean: () => void
  loadSession: (data: {
    template_id: number | null
    crop_box: string
    caption_box: string
    padding_pct: number
    offset_x: number
    offset_y: number
    caption_text: string
    caption_color: string
    post_caption: string
  }) => void
  reset: () => void
}

const DEFAULT_CROP: [number, number, number, number] = [0, 0, 1, 1]

function parseBoxOrNull(json: string): [number, number, number, number] | null {
  try {
    const arr = JSON.parse(json)
    if (Array.isArray(arr) && arr.length === 4) return arr as [number, number, number, number]
  } catch { /* ignore */ }
  return null
}

export const useEditorStore = create<EditorState>()((set) => ({
  videoId: null,
  templateId: null,
  sessionId: null,
  frameTimestamp: 1.0,
  cropBox: DEFAULT_CROP,
  captionBox: null,
  paddingPct: 6.0,
  offsetX: 0,
  offsetY: 0,
  captionText: '',
  captionColor: '#000000',
  postCaption: '',
  isDirty: false,

  setVideo: (id) => set({ videoId: id, isDirty: false }),
  setTemplate: (id) => set({ templateId: id, captionBox: null, isDirty: true }),
  setSessionId: (id) => set({ sessionId: id }),
  setFrameTimestamp: (t) => set({ frameTimestamp: t }),
  setCropBox: (box) => set({ cropBox: box, isDirty: true }),
  setCaptionBox: (box) => set({ captionBox: box, isDirty: true }),
  setPaddingPct: (pct) => set({ paddingPct: pct, isDirty: true }),
  setOffsetX: (x) => set({ offsetX: x, isDirty: true }),
  setOffsetY: (y) => set({ offsetY: y, isDirty: true }),
  setCaptionText: (text) => set({ captionText: text, isDirty: true }),
  setCaptionColor: (color) => set({ captionColor: color, isDirty: true }),
  setPostCaption: (text) => set({ postCaption: text, isDirty: true }),
  markDirty: () => set({ isDirty: true }),
  markClean: () => set({ isDirty: false }),

  loadSession: (data) => {
    let cropBox = DEFAULT_CROP
    try {
      const parsed = JSON.parse(data.crop_box)
      if (Array.isArray(parsed) && parsed.length === 4) cropBox = parsed as [number, number, number, number]
    } catch { /* use default */ }
    set({
      templateId: data.template_id,
      cropBox,
      captionBox: parseBoxOrNull(data.caption_box),
      paddingPct: data.padding_pct,
      offsetX: data.offset_x,
      offsetY: data.offset_y,
      captionText: data.caption_text,
      captionColor: data.caption_color,
      postCaption: data.post_caption || '',
      isDirty: false,
    })
  },

  reset: () =>
    set({
      videoId: null,
      templateId: null,
      sessionId: null,
      frameTimestamp: 1.0,
      cropBox: DEFAULT_CROP,
      captionBox: null,
      paddingPct: 6.0,
      offsetX: 0,
      offsetY: 0,
      captionText: '',
      captionColor: '#000000',
      postCaption: '',
      isDirty: false,
    }),
}))
