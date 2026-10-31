/** 首页与仪表盘共用的公开广告加载逻辑，保留真实错误并忽略过期响应。 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { getPublicAds, type AdvertisementPlacement, type PublicAdsResponse } from '@/api/advertisements'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

/** 随机排列实际广告数据，不修改接口返回的数组。 */
function shuffle<T>(items: T[]): T[] {
  const shuffled = [...items]
  for (let index = shuffled.length - 1; index > 0; index -= 1) {
    const randomIndex = Math.floor(Math.random() * (index + 1))
    ;[shuffled[index], shuffled[randomIndex]] = [shuffled[randomIndex], shuffled[index]]
  }
  return shuffled
}

/** 返回公开广告、加载状态、错误提示及重新加载方法；请求不依赖登录状态。 */
export function usePublicAdvertisements(placement: AdvertisementPlacement = 'dashboard') {
  const { addToast } = useUIStore()
  const [adsData, setAdsData] = useState<PublicAdsResponse>({ carousel: [], text: [] })
  const [adsLoading, setAdsLoading] = useState(true)
  const [adsError, setAdsError] = useState('')
  const loadSequence = useRef(0)

  const loadAds = useCallback(() => {
    const sequence = ++loadSequence.current
    setAdsLoading(true)
    setAdsError('')

    const showError = (message: string) => {
      if (sequence !== loadSequence.current) return
      setAdsError(message)
      addToast({ type: 'error', message })
    }

    return getPublicAds(placement).then((result) => {
      if (sequence !== loadSequence.current) return
      if (!result.success) {
        showError(result.message || '广告加载失败，请重新加载')
        return
      }
      if (!result.data || !Array.isArray(result.data.carousel) || !Array.isArray(result.data.text)) {
        showError('广告数据格式异常，请重新加载')
        return
      }
      setAdsData({ carousel: shuffle(result.data.carousel), text: shuffle(result.data.text) })
    }, (error: unknown) => {
      showError(getApiErrorMessage(error, '广告加载失败，请重新加载'))
    }).finally(() => {
      if (sequence === loadSequence.current) setAdsLoading(false)
    })
  }, [addToast, placement])

  useEffect(() => () => { loadSequence.current += 1 }, [])

  return { adsData, adsLoading, adsError, loadAds }
}
