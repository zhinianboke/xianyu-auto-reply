import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Users, MessageSquare, Activity, ShoppingCart, RefreshCw } from 'lucide-react'
import { getAccountDetails } from '@/api/accounts'
import { getKeywords } from '@/api/keywords'
import { getOrders } from '@/api/orders'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import type { AccountDetail } from '@/types'

interface DashboardStats {
  totalAccounts: number
  totalKeywords: number
  activeAccounts: number
  totalOrders: number
}


export function Dashboard() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState<DashboardStats>({
    totalAccounts: 0,
    totalKeywords: 0,
    activeAccounts: 0,
    totalOrders: 0,
  })
  const [accounts, setAccounts] = useState<AccountDetail[]>([])

  const loadDashboard = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)

      // 获取账号详情
      const accountsData = await getAccountDetails()

      // 为每个账号获取关键词数量
      const accountsWithKeywords = await Promise.all(
        accountsData.map(async (account) => {
          try {
            const keywords = await getKeywords(account.id)
            return {
              ...account,
              keywordCount: keywords.length,
            }
          } catch {
            return { ...account, keywordCount: 0 }
          }
        })
      )

      // 计算统计数据
      let totalKeywords = 0
      let activeAccounts = 0

      accountsWithKeywords.forEach((account) => {
        const isEnabled = account.enabled !== false
        if (isEnabled) {
          activeAccounts++
          totalKeywords += account.keywordCount || 0
        }
      })

      // 获取订单数量
      let ordersCount = 0
      try {
        const ordersResult = await getOrders()
        if (ordersResult.success) {
          ordersCount = ordersResult.data?.length || 0
        }
      } catch {
        // ignore
      }


      setStats({
        totalAccounts: accountsWithKeywords.length,
        totalKeywords,
        activeAccounts,
        totalOrders: ordersCount,
      })

      setAccounts(accountsWithKeywords)
    } catch {
      addToast({ type: 'error', message: '加载仪表盘数据失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadDashboard()
  }, [_hasHydrated, isAuthenticated, token])

  if (loading) {
    return <PageLoading />
  }

  const statCards = [
    {
      icon: Users,
      label: '总账号数',
      value: stats.totalAccounts,
      color: 'primary',
    },
    {
      icon: MessageSquare,
      label: '总关键词数',
      value: stats.totalKeywords,
      color: 'success',
    },
    {
      icon: Activity,
      label: '启用账号数',
      value: stats.activeAccounts,
      color: 'warning',
    },
    {
      icon: ShoppingCart,
      label: '总订单数',
      value: stats.totalOrders,
      color: 'info',
    },
  ]

  const colorClasses = {
    primary: 'stat-icon-primary',
    success: 'stat-icon-success',
    warning: 'stat-icon-warning',
    info: 'stat-icon-info',
  }

  return (
    <div className="space-y-3 sm:space-y-4">
      {/* Page header */}
      <div className="page-header flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="page-title">仪表盘</h1>
          <p className="page-description">系统概览和统计信息</p>
        </div>
        <button onClick={loadDashboard} className="btn-ios-secondary">
          <RefreshCw className="w-4 h-4" />
          <span className="hidden sm:inline">刷新数据</span>
          <span className="sm:hidden">刷新</span>
        </button>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-2 sm:grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-4">
        {statCards.map((card, index) => {
          const Icon = card.icon
          return (
            <motion.div 
              key={card.label} 
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1, duration: 0.3 }}
              className="stat-card"
            >
              <div className={colorClasses[card.color as keyof typeof colorClasses]}>
                <Icon className="w-6 h-6" />
              </div>
              <div>
                <p className="stat-value">{card.value}</p>
                <p className="stat-label">{card.label}</p>
              </div>
            </motion.div>
          )
        })}
      </div>

      {/* Accounts table */}
      <motion.div 
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.4, duration: 0.3 }}
        className="vben-card"
      >
        <div className="vben-card-header">
          <h2 className="vben-card-title">账号详情</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="table-ios">
            <thead>
              <tr>
                <th>账号ID</th>
                <th>关键词数量</th>
                <th>状态</th>
                <th>最后更新</th>
              </tr>
            </thead>
            <tbody>
              {accounts.length === 0 ? (
                <tr>
                  <td colSpan={4}>
                    <div className="empty-state py-8">
                      <Users className="empty-state-icon" />
                      <p className="text-gray-500">暂无账号数据</p>
                    </div>
                  </td>
                </tr>
              ) : (
                accounts.map((account) => {
                  const isEnabled = account.enabled !== false
                  const keywordCount = account.keywordCount || 0

                  return (
                    <tr key={account.id}>
                      <td className="font-medium text-blue-600 dark:text-blue-400">{account.id}</td>
                      <td>{keywordCount}</td>
                      <td>
                        <span className={`inline-flex items-center gap-1.5 ${!isEnabled ? 'text-gray-400' : keywordCount > 0 ? 'text-green-600' : 'text-gray-500'}`}>
                          <span className={`status-dot ${!isEnabled ? 'status-dot-danger' : keywordCount > 0 ? 'status-dot-success' : 'bg-gray-300'}`} />
                          {!isEnabled ? '已禁用' : keywordCount > 0 ? '活跃' : '无关键词'}
                        </span>
                      </td>
                      <td className="text-gray-500">
                        {account.updated_at
                          ? new Date(account.updated_at).toLocaleString()
                          : '-'}
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </motion.div>
    </div>
  )
}
