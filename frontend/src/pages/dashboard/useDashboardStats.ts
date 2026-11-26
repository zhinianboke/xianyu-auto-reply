/** 仪表盘统计加载与权限复核，按登录会话隔离各区块的请求和结果。 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { getAccountStats, getOrderAmountTrend, type AccountStats, type OrderTrendItem } from '@/api/accounts'
import { getAdminStats, getTodayStats, type AdminStats, type TodayStats } from '@/api/admin'
import { verifyToken } from '@/api/auth'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage, isApiForbidden } from '@/utils/apiError'

type Section = 'account' | 'admin' | 'today' | 'trend'
type Loading = Record<Section, boolean>
const IDLE: Loading = { account: false, admin: false, today: false, trend: false }

/** 加载基础、管理员、今日及趋势统计。明确拒绝时清理旧数据并核验权限。 */
export function useDashboardStats(userId: number, token: string, isAdmin: boolean) {
  const addToast = useUIStore(state => state.addToast)
  const [stats, setStats] = useState<AccountStats | null>(null)
  const [adminStats, setAdminStats] = useState<AdminStats | null>(null)
  const [todayStats, setTodayStats] = useState<TodayStats | null>(null)
  const [trend, setTrend] = useState<OrderTrendItem[] | null>(null)
  const [loading, setLoading] = useState<Loading>({ account: true, admin: isAdmin, today: isAdmin, trend: true })
  const [blocked, setBlocked] = useState(false)
  const [checking, setChecking] = useState(false)
  const lifecycle = useRef({ mounted: false, generation: 0, blocked: false, checking: false })
  const latest = useRef<Record<Section, number>>({ account: 0, admin: 0, today: 0, trend: 0 })

  const refresh = useCallback((trendOnly = false) => {
    const state = lifecycle.current
    const isCurrent = (generation: number) => {
      const auth = useAuthStore.getState()
      return state.mounted && state.generation === generation && auth.isAuthenticated
        && auth.token === token && auth.user?.user_id === userId && auth.user.is_admin === isAdmin
    }

    async function recheckAccess(showInactiveMessage = false) {
      if (state.checking) return
      const generation = state.generation
      state.checking = true
      setChecking(true)
      try {
        const result = await verifyToken()
        if (!isCurrent(generation)) return
        if (result?.authenticated === false) {
          if (showInactiveMessage) {
            addToast({ type: 'error', message: '账号不可用或登录已失效，请重新登录' })
          }
          return
        }
        if (result?.authenticated !== true || result.user_id !== userId || typeof result.is_admin !== 'boolean') {
          throw new Error('暂时无法核验当前账号的权限，请刷新重试')
        }
        if (result.is_admin !== isAdmin) {
          // 更新当前用户的真实权限，父组件按权限重建数据区。
          useAuthStore.getState().updateUser({ is_admin: result.is_admin })
          return
        }
        state.blocked = false
        setBlocked(false)
        load(false, false)
      } catch (error) {
        if (isCurrent(generation)) {
          addToast({ type: 'error', message: getApiErrorMessage(error, '暂时无法核验权限，请刷新重试') })
        }
      } finally {
        if (isCurrent(generation)) {
          state.checking = false
          setChecking(false)
        }
      }
    }

    function load(onlyTrend: boolean, recheckOnDenial: boolean) {
      const generation = state.generation
      async function loadSection<T>(section: Section, request: () => Promise<T>, apply: (data: T) => void, fallback: string) {
        const attempt = ++latest.current[section]
        const isLatest = () => isCurrent(generation) && latest.current[section] === attempt
        setLoading(value => ({ ...value, [section]: true }))
        try {
          const result = await request()
          if (isLatest()) apply(result)
        } catch (error) {
          if (!isCurrent(generation)) return
          if (isApiForbidden(error)) {
            // 本会话的拒绝使尚未完成的请求失效，权限以拒绝之后发起的核验为准。
            state.generation += 1
            state.blocked = true
            setStats(null)
            setAdminStats(null)
            setTodayStats(null)
            setTrend(null)
            setLoading(IDLE)
            setBlocked(true)
            addToast({ type: 'error', message: '当前权限无法查看这些统计，请确认账号状态后刷新' })
            if (recheckOnDenial) void recheckAccess()
          } else if (isLatest()) {
            addToast({ type: 'error', message: getApiErrorMessage(error, fallback) })
          }
        } finally {
          if (isLatest()) setLoading(value => ({ ...value, [section]: false }))
        }
      }
      if (!onlyTrend) {
        void loadSection('account', getAccountStats, setStats, '加载统计数据失败')
        if (isAdmin) {
          void loadSection('admin', getAdminStats, result => {
            setAdminStats(result)
            if (result.online_cookies == null) {
              addToast({ type: 'error', message: result.online_cookies_message || '在线账号数量暂不可用' })
            }
          }, '加载管理员统计失败')
          void loadSection('today', getTodayStats, setTodayStats, '加载今日统计失败')
        }
      }
      void loadSection('trend', getOrderAmountTrend, setTrend, '加载订单金额趋势失败')
    }

    if (!isCurrent(state.generation)) return
    if (state.blocked) {
      void recheckAccess(true)
    } else {
      load(trendOnly, true)
    }
  }, [userId, token, isAdmin, addToast])

  useEffect(() => {
    const state = lifecycle.current
    state.mounted = true
    state.blocked = false
    state.checking = false
    setBlocked(false)
    setChecking(false)
    refresh()
    return () => {
      state.mounted = false
      state.generation += 1
    }
  }, [refresh])

  return { stats, adminStats, todayStats, trend, loading, blocked, checking, refresh }
}
