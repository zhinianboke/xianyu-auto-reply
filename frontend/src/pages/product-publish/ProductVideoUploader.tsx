/**
 * 商品视频上传控件。
 * 与图片区域共用媒体卡片，负责上传、预览和移除视频。
 */
import { useState } from 'react'
import { Loader2, Trash2, Upload } from 'lucide-react'
import type { MaterialVideo } from '@/api/productPublish'

interface ProductVideoUploaderProps {
  videos: MaterialVideo[]
  onUploadVideo: (file: File) => Promise<MaterialVideo | null>
  onChange: (videos: MaterialVideo[]) => void
}

export function ProductVideoUploader({ videos, onUploadVideo, onChange }: ProductVideoUploaderProps) {
  const [uploading, setUploading] = useState(false)

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || videos.length >= 3) return
    setUploading(true)
    try {
      const video = await onUploadVideo(file)
      if (video) onChange([...videos, video])
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="mt-4 border-t border-slate-100 pt-4 dark:border-slate-700">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium text-slate-700 dark:text-slate-200">宝贝视频</span>
        <span className="text-xs text-slate-400">{videos.length}/3，单个最大100MB</span>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {videos.map((video, index) => (
          <div key={`${video.url}-${index}`} className="group relative h-20 w-28 overflow-hidden rounded-lg border border-slate-200 bg-slate-100 dark:border-slate-600 dark:bg-slate-800">
            <video src={video.url} className="h-full w-full object-cover" preload="metadata" />
            <button type="button" title="移除视频" className="absolute right-1 top-1 rounded bg-black/60 p-1 text-white opacity-0 transition-opacity group-hover:opacity-100 hover:bg-red-500" onClick={() => onChange(videos.filter((_, itemIndex) => itemIndex !== index))}>
              <Trash2 className="h-3.5 w-3.5" />
            </button>
            <span className="absolute inset-x-0 bottom-0 truncate bg-black/55 px-1 py-0.5 text-[10px] text-white">{video.name || '视频'}</span>
          </div>
        ))}
        {videos.length < 3 && (
          <label className="flex h-20 w-28 cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-300 text-slate-400 transition-colors hover:border-blue-400 hover:text-blue-500 dark:border-slate-600">
            {uploading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Upload className="h-5 w-5" />}
            <span className="mt-1 text-xs">{uploading ? '上传中' : '添加视频'}</span>
            <input type="file" accept="video/*" className="hidden" onChange={handleUpload} disabled={uploading} />
          </label>
        )}
      </div>
    </div>
  )
}

export default ProductVideoUploader
