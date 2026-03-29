import { useState, useEffect, useRef } from 'react'
import { previewUrl } from '../../api/editor'
import { Loader2 } from 'lucide-react'

interface EditorCanvasProps {
  width: number
  height: number
  videoId: number | null
  templateId: number | null
  frameTimestamp: number
  videoBox: [number, number, number, number]
  cropBox: [number, number, number, number]
  captionBox: [number, number, number, number]
  captionText: string
  captionColor: string
}

export default function EditorCanvas({
  width,
  height,
  videoId,
  templateId,
  frameTimestamp,
  videoBox,
  cropBox,
  captionBox,
  captionText,
  captionColor,
}: EditorCanvasProps) {
  const [src, setSrc] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout>>(undefined)

  // Build preview URL with debounce
  useEffect(() => {
    if (!videoId) {
      setSrc(null)
      setLoading(false)
      return
    }

    clearTimeout(debounceRef.current)
    debounceRef.current = setTimeout(() => {
      const url = previewUrl({
        videoId,
        t: frameTimestamp,
        templateId,
        cropBox,
        videoBox,
        captionText,
        captionColor,
        captionBox,
      })
      // Only show spinner if the URL actually changed
      if (url !== src) {
        setLoading(true)
      }
      setSrc(url)
    }, 300)

    return () => clearTimeout(debounceRef.current)
  }, [videoId, templateId, frameTimestamp, videoBox, cropBox, captionBox, captionText, captionColor]) // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div
      style={{ width, height }}
      className="relative bg-black rounded-lg overflow-hidden shadow-2xl"
    >
      {src && (
        <img
          src={src}
          alt="Preview"
          className="w-full h-full object-contain"
          onLoad={() => setLoading(false)}
          onError={() => setLoading(false)}
        />
      )}
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/30">
          <Loader2 size={24} className="animate-spin text-violet-400" />
        </div>
      )}
    </div>
  )
}
