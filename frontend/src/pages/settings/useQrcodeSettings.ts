/** 系统设置二维码读取与上传逻辑。 */
import { useCallback, useState } from 'react'
import { getQrcodeUrl, uploadQrcode } from '@/api/settings'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import type { QrcodeType, QrcodeUploading, QrcodeUrls } from './settingsTypes'

const QRCODE_TYPES: QrcodeType[] = ['wechat', 'qq', 'wechat_official', 'telegram', 'reward']
const QRCODE_LABELS: Record<QrcodeType, string> = {
  wechat: '微信群二维码',
  qq: 'QQ群二维码',
  wechat_official: '微信公众号二维码',
  telegram: 'TG二维码',
  reward: '赞赏码',
}

const emptyUrls = (): QrcodeUrls => ({
  wechat: '',
  qq: '',
  wechat_official: '',
  telegram: '',
  reward: '',
})

const emptyUploading = (): QrcodeUploading => ({
  wechat: false,
  qq: false,
  wechat_official: false,
  telegram: false,
  reward: false,
})

export function useQrcodeSettings() {
  const { addToast } = useUIStore()
  const [urls, setUrls] = useState<QrcodeUrls>(emptyUrls)
  const [uploading, setUploading] = useState<QrcodeUploading>(emptyUploading)

  const loadQrcodes = useCallback(async () => {
    const results = await Promise.allSettled(QRCODE_TYPES.map(async (type) => ({
      type,
      result: await getQrcodeUrl(type),
    })))
    const loadedUrls: Partial<QrcodeUrls> = {}
    const failureMessages: string[] = []
    results.forEach((item) => {
      if (item.status === 'rejected') {
        failureMessages.push(getApiErrorMessage(item.reason, '二维码加载失败'))
        return
      }
      const { type, result } = item.value
      if (result.success && result.data?.image_url) loadedUrls[type] = result.data.image_url
      else if (result.message === '二维码未配置') loadedUrls[type] = ''
      else if (!result.success) failureMessages.push(result.message || `${QRCODE_LABELS[type]}加载失败`)
    })
    setUrls((current) => ({ ...current, ...loadedUrls }))
    if (failureMessages.length) {
      addToast({ type: 'error', message: Array.from(new Set(failureMessages)).join('；') })
    }
  }, [addToast])

  const upload = useCallback(async (type: QrcodeType, file: File) => {
    setUploading((current) => ({ ...current, [type]: true }))
    try {
      const result = await uploadQrcode(type, file)
      if (result.success && result.data?.image_url) {
        setUrls((current) => ({ ...current, [type]: `${result.data?.image_url}?t=${Date.now()}` }))
        addToast({ type: 'success', message: `${QRCODE_LABELS[type]}上传成功` })
      } else {
        addToast({ type: 'error', message: result.message || '上传失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '上传失败') })
    } finally {
      setUploading((current) => ({ ...current, [type]: false }))
    }
  }, [addToast])

  return { urls, uploading, loadQrcodes, upload }
}
