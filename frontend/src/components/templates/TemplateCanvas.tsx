import { useEffect, useRef, useCallback } from 'react'
import { Canvas, FabricImage, Rect } from 'fabric'

interface TemplateCanvasProps {
  width: number
  height: number
  imageUrl: string | null
  videoBox: [number, number, number, number]
  captionBox: [number, number, number, number]
  onVideoBoxChange: (box: [number, number, number, number]) => void
  onCaptionBoxChange: (box: [number, number, number, number]) => void
}

const OBJ_IMAGE = '__template_image__'
const OBJ_VIDEO_BOX = '__video_box__'
const OBJ_CAPTION_BOX = '__caption_box__'

function clamp01(v: number) {
  return Math.max(0, Math.min(1, v))
}

export default function TemplateCanvas({
  width,
  height,
  imageUrl,
  videoBox,
  captionBox,
  onVideoBoxChange,
  onCaptionBoxChange,
}: TemplateCanvasProps) {
  const canvasElRef = useRef<HTMLCanvasElement>(null)
  const fabricRef = useRef<Canvas | null>(null)
  const suppressSync = useRef(false)

  useEffect(() => {
    if (!canvasElRef.current || width <= 0 || height <= 0) return
    const fc = new Canvas(canvasElRef.current, {
      width,
      height,
      backgroundColor: '#18181b',
      selection: false,
    })
    fabricRef.current = fc
    return () => {
      fc.dispose()
      fabricRef.current = null
    }
  }, [width, height])

  const findObj = useCallback((name: string) => {
    const fc = fabricRef.current
    if (!fc) return null
    return fc.getObjects().find((o) => (o as any).name === name) ?? null
  }, [])

  const removeObj = useCallback((name: string) => {
    const fc = fabricRef.current
    if (!fc) return
    const obj = findObj(name)
    if (obj) fc.remove(obj)
  }, [findObj])

  // Load template image as background
  useEffect(() => {
    const fc = fabricRef.current
    if (!fc) return
    removeObj(OBJ_IMAGE)
    if (!imageUrl) {
      fc.requestRenderAll()
      return
    }
    FabricImage.fromURL(imageUrl, { crossOrigin: 'anonymous' }).then((img) => {
      removeObj(OBJ_IMAGE)
      ;(img as any).name = OBJ_IMAGE
      img.set({
        left: 0,
        top: 0,
        scaleX: width / (img.width || 1),
        scaleY: height / (img.height || 1),
        selectable: false,
        evented: false,
        hoverCursor: 'default',
      })
      fc.add(img)
      fc.sendObjectToBack(img)
      fc.requestRenderAll()
    })
  }, [imageUrl, width, height, removeObj])

  // Helper to create a draggable/resizable guide rect
  const makeGuideRect = useCallback(
    (
      name: string,
      box: [number, number, number, number],
      color: string,
      onChange: (box: [number, number, number, number]) => void,
    ) => {
      const fc = fabricRef.current
      if (!fc) return

      removeObj(name)

      const [x1, y1, x2, y2] = box
      const left = x1 * width
      const top = y1 * height
      const w = (x2 - x1) * width
      const h = (y2 - y1) * height

      const rect = new Rect({
        left,
        top,
        width: w,
        height: h,
        fill: color + '18',
        stroke: color,
        strokeWidth: 2,
        strokeDashArray: [6, 3],
        selectable: true,
        hasControls: true,
        hasBorders: true,
        lockRotation: true,
        cornerColor: color,
        cornerStyle: 'circle',
        cornerSize: 8,
        transparentCorners: false,
        borderColor: color,
        minScaleLimit: 0.01,
      })
      ;(rect as any).name = name
      fc.add(rect)

      const syncBox = () => {
        if (suppressSync.current) return
        const l = rect.left ?? 0
        const t = rect.top ?? 0
        const rw = (rect.width ?? 1) * (rect.scaleX ?? 1)
        const rh = (rect.height ?? 1) * (rect.scaleY ?? 1)
        onChange([
          clamp01(l / width),
          clamp01(t / height),
          clamp01((l + rw) / width),
          clamp01((t + rh) / height),
        ])
      }

      rect.on('modified', syncBox)
      rect.on('moved', syncBox)
      rect.on('scaled', syncBox)

      return rect
    },
    [width, height, removeObj],
  )

  // Create/update video box guide
  useEffect(() => {
    const fc = fabricRef.current
    if (!fc) return
    suppressSync.current = true
    const rect = makeGuideRect(OBJ_VIDEO_BOX, videoBox, '#7c3aed', onVideoBoxChange)
    suppressSync.current = false
    // Bring caption box to front if exists
    const cap = findObj(OBJ_CAPTION_BOX)
    if (cap) fc.bringObjectToFront(cap)
    fc.requestRenderAll()
    return () => {
      if (rect) {
        rect.off('modified')
        rect.off('moved')
        rect.off('scaled')
      }
    }
  }, [videoBox, width, height, makeGuideRect, onVideoBoxChange, findObj])

  // Create/update caption box guide
  useEffect(() => {
    const fc = fabricRef.current
    if (!fc) return
    suppressSync.current = true
    makeGuideRect(OBJ_CAPTION_BOX, captionBox, '#f59e0b', onCaptionBoxChange)
    suppressSync.current = false
    // Ensure caption is on top
    const cap = findObj(OBJ_CAPTION_BOX)
    if (cap) fc.bringObjectToFront(cap)
    fc.requestRenderAll()
  }, [captionBox, width, height, makeGuideRect, onCaptionBoxChange, findObj])

  return (
    <div
      style={{ width, height }}
      className="relative rounded-lg overflow-hidden shadow-2xl border border-zinc-800"
    >
      <canvas ref={canvasElRef} />
      {/* Legend */}
      <div className="absolute bottom-2 left-2 flex gap-3">
        <div className="flex items-center gap-1.5 bg-black/60 rounded px-2 py-1">
          <div className="w-2.5 h-2.5 rounded-sm bg-violet-500/60 border border-violet-500" />
          <span className="text-[9px] text-zinc-300">Video</span>
        </div>
        <div className="flex items-center gap-1.5 bg-black/60 rounded px-2 py-1">
          <div className="w-2.5 h-2.5 rounded-sm bg-amber-500/60 border border-amber-500" />
          <span className="text-[9px] text-zinc-300">Caption</span>
        </div>
      </div>
    </div>
  )
}
