import { useEffect } from 'react'
import { motion } from 'framer-motion'
import { Activity, Calendar, MessageSquare, RefreshCw, Shield, ShoppingCart, Users, Package, Clock, DollarSign } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { OrderAmountChart } from '@/components/common/OrderAmountChart'
import { PublicAdvertisements } from '@/components/common/PublicAdvertisements'
import { usePublicAdvertisements } from '@/components/common/usePublicAdvertisements'
import { useDashboardStats } from './useDashboardStats'

export function Dashboard() {
  const { isAuthenticated, token, _hasHydrated, user } = useAuthStore()
  if (!_hasHydrated || !isAuthenticated || !token || user?.user_id == null) return null

  // 按用户和权限隔离上次成功的数据。相同用户刷新时仍可保留这些结果。
  return <DashboardContent key={`${user.user_id}:${user.is_admin}`} userId={user.user_id} token={token} isAdmin={user.is_admin} />
}

function DashboardContent({ userId, token, isAdmin }: { userId: number; token: string; isAdmin: boolean }) {
  const { stats, adminStats, todayStats, trend, loading, blocked, checking, refresh } = useDashboardStats(userId, token, isAdmin)
  const advertisements = usePublicAdvertisements()
  const { loadAds } = advertisements
  useEffect(() => { void loadAds() }, [loadAds])

  const refreshDashboard = () => {
    refresh()
    void loadAds()
  }

  const statCards = [
    {
      icon: Users,
      label: '总账号数',
      value: stats?.total_accounts,
      color: 'primary',
    },
    {
      icon: MessageSquare,
      label: '总关键词数',
      value: stats?.total_keywords,
      color: 'success',
    },
    {
      icon: Activity,
      label: '启用账号数',
      value: stats?.active_accounts,
      color: 'warning',
    },
    {
      icon: ShoppingCart,
      label: '总订单数',
      value: stats?.total_orders,
      color: 'info',
    },
    {
      icon: Calendar,
      label: '今日回复',
      value: stats?.today_reply_count,
      color: 'success',
    },
    {
      icon: Clock,
      label: '昨日回复',
      value: stats?.yesterday_reply_count,
      color: 'info',
    },
    {
      icon: Shield,
      label: '可添加账号数',
      value: stats?.account_limit,
      color: 'primary',
    },
    {
      icon: Package,
      label: '已用账号数',
      value: stats?.used_account_count,
      color: 'warning',
    },
    {
      icon: Clock,
      label: '剩余额度',
      value: stats?.remaining_account_count,
      color: 'success',
    },
  ]

  const colorClasses = {
    primary: 'stat-icon-primary',
    success: 'stat-icon-success',
    warning: 'stat-icon-warning',
    info: 'stat-icon-info',
  }

  /** 骨架屏组件 */
  const SkeletonCard = () => (
    <div className="stat-card min-w-[132px] sm:min-w-[148px] flex-1 animate-pulse">
      <div className="w-12 h-12 bg-slate-200 dark:bg-slate-700 rounded-full" />
      <div className="flex-1">
        <div className="h-8 bg-slate-200 dark:bg-slate-700 rounded w-16 mb-2" />
        <div className="h-4 bg-slate-200 dark:bg-slate-700 rounded w-24" />
      </div>
    </div>
  )

  return (
    <div className="space-y-3 sm:space-y-4">
      {/* Page header */}
      <div className="page-header flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="page-title">仪表盘</h1>
          <p className="page-description">系统概览和统计信息</p>
        </div>
        <button onClick={refreshDashboard} disabled={checking} className="btn-ios-secondary">
          <RefreshCw className="w-4 h-4" />
          <span className="hidden sm:inline">刷新数据</span>
          <span className="sm:hidden">刷新</span>
        </button>
      </div>

      {/* Stats cards */}
      <div className="flex flex-nowrap gap-2 sm:gap-3 overflow-x-auto pb-1 scrollbar-visible">
        {loading.account ? (
          // 骨架屏
          Array.from({ length: statCards.length }).map((_, index) => (
            <SkeletonCard key={index} />
          ))
        ) : (
          statCards.map((card, index) => {
            const Icon = card.icon
            return (
              <motion.div
                key={card.label}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1, duration: 0.3 }}
                className="stat-card min-w-[132px] sm:min-w-[148px] flex-1"
              >
                <div className={colorClasses[card.color as keyof typeof colorClasses]}>
                  <Icon className="w-6 h-6" />
                </div>
                <div className="min-w-0">
                  <p className="stat-value truncate whitespace-nowrap">{card.value ?? '-'}</p>
                  <p className="stat-label truncate whitespace-nowrap">{card.label}</p>
                </div>
              </motion.div>
            )
          })
        )}
      </div>

      <PublicAdvertisements placement="dashboard" {...advertisements} />

      {/* Admin Stats - 管理员专属 */}
      {isAdmin && !blocked && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3, duration: 0.3 }}
          className="vben-card"
        >
          <div className="vben-card-header">
            <h2 className="vben-card-title flex items-center gap-2">
              <Shield className="w-4 h-4" />
              全局统计（管理员）
            </h2>
          </div>
          <div className="vben-card-body">
            {loading.admin ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
              </div>
            ) : adminStats ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 xl:grid-cols-5 gap-4">
                <div className="text-center p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                  <p className="text-2xl font-bold text-blue-600">{adminStats.total_users}</p>
                  <p className="text-sm text-slate-500">总用户数</p>
                </div>
                <div className="text-center p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                  <p className="text-2xl font-bold text-green-600">{adminStats.total_cookies}</p>
                  <p className="text-sm text-slate-500">总账号数</p>
                </div>
                <div className="text-center p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                  <p className="text-2xl font-bold text-amber-600">{adminStats.active_cookies}</p>
                  <p className="text-sm text-slate-500">活跃账号</p>
                </div>
                <div className="text-center p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                  <p className="text-2xl font-bold text-emerald-600">{adminStats.online_cookies ?? '-'}</p>
                  <p className="text-sm text-slate-500">在线账号</p>
                </div>
                <div className="text-center p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                  <p className="text-2xl font-bold text-teal-600">{adminStats.password_configured}</p>
                  <p className="text-sm text-slate-500">已配置密码</p>
                </div>
                <div className="text-center p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                  <p className="text-2xl font-bold text-purple-600">{adminStats.total_cards}</p>
                  <p className="text-sm text-slate-500">总卡券数</p>
                </div>
                <div className="text-center p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                  <p className="text-2xl font-bold text-cyan-600">{adminStats.total_keywords}</p>
                  <p className="text-sm text-slate-500">总关键词</p>
                </div>
                <div className="text-center p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                  <p className="text-2xl font-bold text-rose-600">{adminStats.total_orders}</p>
                  <p className="text-sm text-slate-500">总订单数</p>
                </div>
                <div className="text-center p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                  <p className="text-2xl font-bold text-indigo-600">{adminStats.today_reply_count}</p>
                  <p className="text-sm text-slate-500">今日回复</p>
                </div>
                <div className="text-center p-3 bg-slate-50 dark:bg-slate-800 rounded-lg">
                  <p className="text-2xl font-bold text-sky-600">{adminStats.yesterday_reply_count}</p>
                  <p className="text-sm text-slate-500">昨日回复</p>
                </div>
              </div>
            ) : null}
          </div>
        </motion.div>
      )}

      {/* 订单金额趋势折线图（所有用户可见） */}
      {!blocked && <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35, duration: 0.3 }}
      >
        <OrderAmountChart data={trend} loading={loading.trend} onRefresh={() => refresh(true)} />
      </motion.div>}

      {/* Today Stats - 今日统计（管理员专属） */}
      {isAdmin && !blocked && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.4, duration: 0.3 }}
          className="vben-card"
        >
          <div className="vben-card-header">
            <h2 className="vben-card-title flex items-center gap-2">
              <Calendar className="w-4 h-4" />
              今日统计（管理员）
            </h2>
          </div>
          <div className="vben-card-body">
            {loading.today ? (
              <div className="flex items-center justify-center py-8">
                <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
              </div>
            ) : todayStats ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-4">
                <div className="text-center p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-100 dark:border-blue-800">
                  <div className="flex items-center justify-center mb-2">
                    <Users className="w-5 h-5 text-blue-500" />
                  </div>
                  <p className="text-2xl font-bold text-blue-600">{todayStats.today_users}</p>
                  <p className="text-sm text-slate-500">今日新增用户</p>
                </div>
                <div className="text-center p-3 bg-green-50 dark:bg-green-900/20 rounded-lg border border-green-100 dark:border-green-800">
                  <div className="flex items-center justify-center mb-2">
                    <Activity className="w-5 h-5 text-green-500" />
                  </div>
                  <p className="text-2xl font-bold text-green-600">{todayStats.today_accounts}</p>
                  <p className="text-sm text-slate-500">今日新增账号</p>
                </div>
                <div className="text-center p-3 bg-purple-50 dark:bg-purple-900/20 rounded-lg border border-purple-100 dark:border-purple-800">
                  <div className="flex items-center justify-center mb-2">
                    <ShoppingCart className="w-5 h-5 text-purple-500" />
                  </div>
                  <p className="text-2xl font-bold text-purple-600">{todayStats.today_orders}</p>
                  <p className="text-sm text-slate-500">今日订单</p>
                </div>
                <div className="text-center p-3 bg-cyan-50 dark:bg-cyan-900/20 rounded-lg border border-cyan-100 dark:border-cyan-800">
                  <div className="flex items-center justify-center mb-2">
                    <DollarSign className="w-5 h-5 text-cyan-500" />
                  </div>
                  <p className="text-2xl font-bold text-cyan-600">{todayStats.today_agent_orders ?? 0}</p>
                  <p className="text-sm text-slate-500">今日代销订单</p>
                </div>
                <div className="text-center p-3 bg-rose-50 dark:bg-rose-900/20 rounded-lg border border-rose-100 dark:border-rose-800">
                  <div className="flex items-center justify-center mb-2">
                    <span className="text-rose-500 text-xl font-bold">￥</span>
                  </div>
                  <p className="text-2xl font-bold text-rose-600">¥{todayStats.today_amount?.toFixed(2) || '0.00'}</p>
                  <p className="text-sm text-slate-500">今日订单金额</p>
                </div>
                <div className="text-center p-3 bg-emerald-50 dark:bg-emerald-900/20 rounded-lg border border-emerald-100 dark:border-emerald-800">
                  <div className="flex items-center justify-center mb-2">
                    <Package className="w-5 h-5 text-emerald-500" />
                  </div>
                  <p className="text-2xl font-bold text-emerald-600">{todayStats.today_shipped}</p>
                  <p className="text-sm text-slate-500">今日已发货</p>
                </div>
                <div className="text-center p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-100 dark:border-amber-800">
                  <div className="flex items-center justify-center mb-2">
                    <Clock className="w-5 h-5 text-amber-500" />
                  </div>
                  <p className="text-2xl font-bold text-amber-600">{todayStats.today_pending}</p>
                  <p className="text-sm text-slate-500">今日待处理</p>
                </div>
              </div>
            ) : null}
          </div>
        </motion.div>
      )}
    </div>
  )
}
