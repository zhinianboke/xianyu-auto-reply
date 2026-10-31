/** 管理、申请和费用配置共用的广告类型字典查询，失败明确反馈并提供重试。 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { getAdvertisementTypes, type AdvertisementTypeOption } from '@/api/advertisements'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

export function useAdvertisementTypes() {
  const { addToast } = useUIStore()
  const [adTypeOptions, setAdTypeOptions] = useState<AdvertisementTypeOption[]>([])
  const [typesLoading, setTypesLoading] = useState(true)
  const [typesError, setTypesError] = useState('')
  const sequence = useRef(0)
  const reloadTypes = useCallback(() => {
    const requestSequence = ++sequence.current
    setTypesLoading(true)
    setTypesError('')
    const fail = (message: string) => {
      if (requestSequence !== sequence.current) return
      setTypesError(message)
      addToast({ type: 'error', message })
    }
    return getAdvertisementTypes().then((response) => {
      if (requestSequence !== sequence.current) return
      if (!response.success || !Array.isArray(response.data) || !response.data.length) {
        fail(response.message || '广告类型加载失败，请重新加载')
        return
      }
      setAdTypeOptions(response.data)
    }, (error: unknown) => fail(getApiErrorMessage(error, '广告类型加载失败')))
      .finally(() => { if (requestSequence === sequence.current) setTypesLoading(false) })
  }, [addToast])
  useEffect(() => {
    void reloadTypes()
    return () => { sequence.current += 1 }
  }, [reloadTypes])
  return { adTypeOptions, typesLoading, typesError, reloadTypes }
}
