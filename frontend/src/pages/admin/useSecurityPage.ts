/** 安全管理公共分页加载：保留真实数据、已应用筛选、加载遮罩及中文失败反馈。 */
import { useCallback, useEffect, useRef, useState } from 'react'
import type { ApiResponse } from '@/types'
import type { SecurityPage } from '@/api/securityManagement'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { getApiErrorMessage } from '@/utils/apiError'

export function useSecurityPage<T, F>(fetcher: (page: number, size: number, filters: F) => Promise<ApiResponse<SecurityPage<T>>>, initialFilters: F) {
  const [snapshot, setSnapshot] = useState<{ data: SecurityPage<T>; userId: number | undefined } | null>(null)
  const [filters, setFilters] = useState(initialFilters)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const generation = useRef(0)
  const pending = useRef(false)
  const mounted = useRef(false)
  const appliedQuery = useRef({ page: 1, size: 20, filters: initialFilters })
  const { addToast } = useUIStore()
  const { user, _hasHydrated, isAuthenticated, token } = useAuthStore()
  const userId = user?.user_id
  const canLoad = _hasHydrated && isAuthenticated && Boolean(token) && Boolean(user?.is_admin)
  const previousIdentity = useRef({ userId, canLoad, initialFilters })
  const isCurrentSession = useCallback(() => {
    const current = useAuthStore.getState()
    return mounted.current && canLoad && current._hasHydrated && current.isAuthenticated
      && Boolean(current.token) && current.user?.user_id === userId && Boolean(current.user?.is_admin)
  }, [canLoad, userId])
  const load = useCallback((page: number, size: number, applied: F) => {
    if (!isCurrentSession() || pending.current) return
    pending.current = true
    // 点击查询即应用条件；失败后的刷新、翻页仍使用本次条件和每页条数。
    appliedQuery.current = { page, size, filters: applied }
    setFilters(applied)
    setLoading(true)
    const id = ++generation.current
    void fetcher(page, size, applied).then((response) => {
      if (id !== generation.current || !isCurrentSession()) return
      if (!response.success) {
        setError(response.message || '安全管理查询失败')
        addToast({ type: 'error', message: response.message || '安全管理查询失败' })
        return
      }
      const result = response.data
      if (!result || !Array.isArray(result.items) || !Number.isInteger(result.total) || !result.dictionaries) {
        setError('安全管理响应不完整，请重新加载')
        addToast({ type: 'error', message: '安全管理响应不完整，请重新加载' })
        return
      }
      setError('')
      setSnapshot({ data: result, userId })
      appliedQuery.current = { page: result.page, size: result.page_size, filters: applied }
    }).catch((reason: unknown) => {
      if (id !== generation.current || !isCurrentSession()) return
      const message = getApiErrorMessage(reason, '安全管理查询失败')
      setError(message)
      addToast({ type: 'error', message })
    }).finally(() => {
      if (id === generation.current && isCurrentSession()) { pending.current = false; setLoading(false) }
    })
  }, [addToast, fetcher, isCurrentSession, userId])
  useEffect(() => {
    mounted.current = true
    const previous = previousIdentity.current
    if (previous.userId !== userId || previous.canLoad !== canLoad || previous.initialFilters !== initialFilters) {
      appliedQuery.current = { page: 1, size: 20, filters: initialFilters }
    }
    previousIdentity.current = { userId, canLoad, initialFilters }
    setSnapshot(null)
    setFilters(appliedQuery.current.filters)
    setError('')
    setLoading(false)
    load(appliedQuery.current.page, appliedQuery.current.size, appliedQuery.current.filters)
    return () => { mounted.current = false; generation.current += 1; pending.current = false }
  }, [load, initialFilters, userId, canLoad])
  const data = canLoad && snapshot && snapshot.userId === userId ? snapshot.data : null
  return { data, filters, loading, error, load, isCurrentSession,
    page: appliedQuery.current.page, pageSize: appliedQuery.current.size }
}
