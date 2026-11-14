/**
 * 通知事件类型数据字典 Hook。
 *
 * 功能：
 * 1. 统一从后端数据字典加载通知类型及中文名称
 * 2. 向通知渠道页和消息通知页提供同一份选项、加载状态和错误信息
 */
import { useCallback, useEffect, useState } from 'react'
import { getMessageNotificationOptions } from '@/api/notifications'
import type { NotificationTypeOption } from '@/api/notifications'
import { getApiErrorMessage } from '@/utils/request'

export function useNotificationTypeOptions(enabled: boolean) {
  const [options, setOptions] = useState<NotificationTypeOption[]>([])
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    if (!enabled) {
      setLoading(false)
      return
    }
    setLoading(true)
    setError('')
    try {
      const result = await getMessageNotificationOptions()
      if (!result.success) {
        setOptions([])
        setError(result.message || '加载通知类型失败')
        return
      }
      const values = result.data?.notify_types || []
      if (!['chat', 'delivery', 'account'].every((type) => values.some((item) => item.value === type && item.label))) {
        setOptions([])
        setError('通知类型数据字典不完整，请联系管理员检查数据库初始化')
        return
      }
      setOptions(values)
    } catch (reason) {
      setOptions([])
      setError(getApiErrorMessage(reason, '加载通知类型失败'))
    } finally {
      setLoading(false)
    }
  }, [enabled])

  useEffect(() => {
    void load()
  }, [load])

  return { options, loading, error, reload: load }
}
