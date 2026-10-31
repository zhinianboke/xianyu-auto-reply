/** 广告编辑共用图片上传，使用统一请求客户端及中文错误反馈。 */
import { useRef, useState, type ChangeEvent } from 'react'
import { post } from '@/utils/request'
import { getApiErrorMessage } from '@/utils/apiError'
import { useUIStore } from '@/store/uiStore'
import type { ApiResponse } from '@/types'

export function useAdvertisementImage(token: string | null, onChange: (url: string) => void) {
  const { addToast } = useUIStore()
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const handleUploadImage = (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.target
    const file = input.files?.[0]
    if (!file) return
    input.value = ''
    if (!file.type.startsWith('image/')) {
      addToast({ type: 'warning', message: '请选择图片文件' })
      return
    }
    if (!token) {
      addToast({ type: 'error', message: '登录已失效，请重新登录' })
      return
    }
    setUploading(true)
    const data = new FormData()
    data.append('image', file)
    void post<ApiResponse & { data?: { image_url: string } }>('/api/v1/upload/upload-image', data, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((response) => {
      if (response.success && response.data?.image_url) {
        onChange(response.data.image_url)
        addToast({ type: 'success', message: '图片上传成功' })
      } else addToast({ type: 'error', message: response.message || '上传失败' })
    }, (error: unknown) => addToast({ type: 'error', message: getApiErrorMessage(error, '上传失败') }))
      .finally(() => setUploading(false))
  }
  return { uploading, fileInputRef, handleUploadImage }
}
