/** 同表任务加载与操作：保留后端分页、身份与卸载保护，操作完成后刷新当前页。 */
import { useEffect, useRef, useState } from 'react'
import { getScheduledTaskPage, triggerScheduledTask, updateScheduledTask } from '@/api/scheduledTasks'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { useSecurityPage } from './useSecurityPage'

const NO_FILTERS = {}
export function useScheduledTasks() {
  const state = useSecurityPage(getScheduledTaskPage, NO_FILTERS)
  const { isCurrentSession, load, page, pageSize, filters } = state
  const { addToast } = useUIStore()
  const [operation, setOperation] = useState<{ code: string; kind: 'trigger' | 'update' } | null>(null)
  const pending = useRef(false)
  const generation = useRef(0)
  const query = useRef({ page, pageSize, filters })
  query.current = { page, pageSize, filters }
  useEffect(() => {
    pending.current = false
    setOperation(null)
    return () => { generation.current += 1 }
  }, [isCurrentSession])
  const refresh = () => {
    const current = query.current
    load(current.page, current.pageSize, current.filters)
  }
  const perform = (code: string, kind: 'trigger' | 'update', request: () => Promise<{ success: boolean; message: string }>,
    onSuccess?: () => void) => {
    if (state.loading || pending.current || !isCurrentSession()) return
    pending.current = true
    setOperation({ code, kind })
    const id = ++generation.current
    void request().then((response) => {
      if (id !== generation.current || !isCurrentSession()) return
      addToast({ type: response.success ? 'success' : 'error', message: response.message || '定时任务未返回处理结果' })
      if (response.success) onSuccess?.()
      refresh()
    }).catch((reason: unknown) => {
      if (id !== generation.current || !isCurrentSession()) return
      addToast({ type: 'error', message: getApiErrorMessage(reason, '定时任务操作失败') })
      refresh()
    }).finally(() => {
      if (id === generation.current && isCurrentSession()) { pending.current = false; setOperation(null) }
    })
  }
  return { ...state, operation, busy: state.loading || Boolean(operation), refresh,
    run: (code: string) => perform(code, 'trigger', () => triggerScheduledTask(code)),
    update: (code: string, params: { enabled?: boolean; interval_seconds?: number }, onSuccess?: () => void) =>
      perform(code, 'update', () => updateScheduledTask(code, params), onSuccess) }
}
