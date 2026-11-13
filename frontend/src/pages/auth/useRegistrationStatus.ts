/** 登录和注册页面共用注册状态加载，区分开放、关闭、加载及读取失败。 */
import { useEffect, useState } from 'react'
import axios from 'axios'
import { getRegistrationStatus } from '@/api/auth'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

export function useRegistrationStatus() {
  const [enabled, setEnabled] = useState<boolean | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)
  const addToast = useUIStore((state) => state.addToast)

  useEffect(() => {
    let active = true
    setEnabled(null)
    setError(null)
    getRegistrationStatus().then(
      (result) => { if (active) setEnabled(result.enabled) },
      (reason: unknown) => {
        if (!active) return
        const fallback = '读取注册状态失败，请检查网络后重试'
        const message = axios.isAxiosError(reason) && !reason.response
          ? fallback
          : getApiErrorMessage(reason, fallback)
        setError(message)
        addToast({ type: 'error', message })
      },
    )
    return () => { active = false }
  }, [attempt, addToast])

  return { enabled, error, reload: () => setAttempt((current) => current + 1) }
}
