import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Activity, Calendar, MessageSquare, RefreshCw, Shield, ShoppingCart, Users, Package, Clock, DollarSign, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react'
import { getAccountStats } from '@/api/accounts'
import { type AdminStats, type TodayStats, getAdminStats, getTodayStats } from '@/api/admin'
import { getPublicAds, type Advertisement } from '@/api/advertisements'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { OrderAmountChart } from '@/components/common/OrderAmountChart'

interface DashboardStats {
  totalAccounts: number
  totalKeywords: number
  activeAccounts: number
  totalOrders: number
  todayReplyCount: number
  yesterdayReplyCount: number
  accountLimit: number | null
  usedAccountCount: number
  remainingAccountCount: number | null
}

interface AdsData {
  carousel: Advertisement[]
  text: Advertisement[]
}

export function Dashboard() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated, user } = useAuthStore()
  const [statsLoading, setStatsLoading] = useState(true)
  const [adminStatsLoading, setAdminStatsLoading] = useState(true)
  const [adsLoading, setAdsLoading] = useState(true)
  const [stats, setStats] = useState<DashboardStats>({
    totalAccounts: 0,
    totalKeywords: 0,
    activeAccounts: 0,
    totalOrders: 0,
    todayReplyCount: 0,
    yesterdayReplyCount: 0,
    accountLimit: null,
    usedAccountCount: 0,
    remainingAccountCount: null,
  })
  const [adminStats, setAdminStats] = useState<AdminStats | null>(null)
  const [todayStats, setTodayStats] = useState<TodayStats | null>(null)
  const [adsData, setAdsData] = useState<AdsData>({ carousel: [], text: [] })
  const [carouselIndex, setCarouselIndex] = useState(0)
  const [expandedTextAds, setExpandedTextAds] = useState<Set<number>>(new Set())

  /** 加载基础统计数据 */
  const loadStats = async () => {
    try {
      setStatsLoading(true)
      
      // 调用后端统计接口，一次性获取所有统计数据
      const statsData = await getAccountStats()
      
      setStats({
        totalAccounts: statsData.total_accounts,
        totalKeywords: statsData.total_keywords,
        activeAccounts: statsData.active_accounts,
        totalOrders: statsData.total_orders,
        todayReplyCount: statsData.today_reply_count,
        yesterdayReplyCount: statsData.yesterday_reply_count,
        accountLimit: statsData.account_limit ?? user?.account_limit ?? null,
        usedAccountCount: statsData.used_account_count,
        remainingAccountCount: statsData.remaining_account_count ?? null,
      })
    } catch (error) {
      addToast({ type: 'error', message: '加载统计数据失败' })
    } finally {
      setStatsLoading(false)
    }
  }

  /** 加载管理员统计数据 */
  const loadAdminStats = async () => {
    if (!user?.is_admin) {
      setAdminStatsLoading(false)
      return
    }
    try {
      setAdminStatsLoading(true)
      const [adminResult, todayResult] = await Promise.all([
        getAdminStats(),
        getTodayStats(),
      ])
      if (adminResult.success && adminResult.data) {
        setAdminStats(adminResult.data)
      }
      if (todayResult.success && todayResult.data) {
        setTodayStats(todayResult.data)
      }
    } catch {
      // ignore
    } finally {
      setAdminStatsLoading(false)
    }
  }

  /** 加载广告数据 */
  const loadAds = async () => {
    try {
      setAdsLoading(true)
      const adsResult = await getPublicAds()
      if (adsResult.success && adsResult.data) {
        setAdsData(adsResult.data)
      }
    } catch {
      // ignore
    } finally {
      setAdsLoading(false)
    }
  }

  /** 加载所有数据（异步独立加载） */
  const loadDashboard = () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    
    // 异步独立加载各个模块，不互相等待
    loadStats()
    loadAdminStats()
    loadAds()
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadDashboard()
  }, [_hasHydrated, isAuthenticated, token])

  // 轮播广告自动切换
  useEffect(() => {
    if (adsData.carousel.length <= 1) return
    const timer = setInterval(() => {
      setCarouselIndex((prev) => (prev + 1) % adsData.carousel.length)
    }, 4000)
    return () => clearInterval(timer)
  }, [adsData.carousel.length])

  /** 切换文字广告展开/折叠 */
  const toggleTextAd = (id: number) => {
    setExpandedTextAds((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(id)) {
        newSet.delete(id)
      } else {
        newSet.add(id)
      }
      return newSet
    })
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
    {
      icon: Calendar,
      label: '今日回复',
      value: stats.todayReplyCount,
      color: 'success',
    },
    {
      icon: Clock,
      label: '昨日回复',
      value: stats.yesterdayReplyCount,
      color: 'info',
    },
    {
      icon: Shield,
      label: '可添加账号数',
      value: stats.accountLimit,
      color: 'primary',
    },
    {
      icon: Package,
      label: '已用账号数',
      value: stats.usedAccountCount,
      color: 'warning',
    },
    {
      icon: Clock,
      label: '剩余额度',
      value: stats.remainingAccountCount,
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
        <button onClick={loadDashboard} className="btn-ios-secondary">
          <RefreshCw className="w-4 h-4" />
          <span className="hidden sm:inline">刷新数据</span>
          <span className="sm:hidden">刷新</span>
        </button>
      </div>

      {/* Stats cards */}
      <div className="flex flex-nowrap gap-2 sm:gap-3 overflow-x-auto pb-1 scrollbar-visible">
        {statsLoading ? (
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

      {/* 广告模块 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.2, duration: 0.3 }}
        className="grid grid-cols-1 lg:grid-cols-2 gap-4"
      >
        {/* 左侧：轮播广告 */}
        <div className="vben-card">
          <div className="vben-card-header">
            <h2 className="vben-card-title">推荐广告</h2>
          </div>
          <div className="vben-card-body p-0">
            <div className="relative h-48 sm:h-56 overflow-hidden rounded-b-lg bg-slate-100 dark:bg-slate-800">
              {adsLoading ? (
                <div className="w-full h-full flex items-center justify-center">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
                </div>
              ) : adsData.carousel.length > 0 ? (
                <AnimatePresence mode="wait">
                  <motion.a
                    key={carouselIndex}
                    href={adsData.carousel[carouselIndex]?.link || '#'}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="absolute inset-0 block cursor-pointer bg-slate-100 dark:bg-slate-800"
                    initial={{ y: '100%', opacity: 0 }}
                    animate={{ y: 0, opacity: 1 }}
                    exit={{ y: '-100%', opacity: 0 }}
                    transition={{ duration: 0.5, ease: 'easeInOut' }}
                  >
                    {adsData.carousel[carouselIndex]?.image_url ? (
                      <img
                        src={adsData.carousel[carouselIndex].image_url!}
                        alt={adsData.carousel[carouselIndex].title}
                        className="w-full h-full object-contain"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-blue-500 to-purple-600">
                        <span className="text-white text-xl font-bold">
                          {adsData.carousel[carouselIndex]?.title}
                        </span>
                      </div>
                    )}
                    {/* 底部标题和正文 */}
                    <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-3">
                      <h3 className="text-white font-medium text-sm truncate">
                        {adsData.carousel[carouselIndex]?.title}
                      </h3>
                      {adsData.carousel[carouselIndex]?.content && (
                        <p className="text-white/80 text-xs mt-1 line-clamp-2">
                          {adsData.carousel[carouselIndex].content}
                        </p>
                      )}
                    </div>
                  </motion.a>
                </AnimatePresence>
              ) : (
                <div className="w-full h-full flex items-center justify-center text-slate-400">
                  <span>暂无轮播广告</span>
                </div>
              )}
              {/* 轮播指示器 */}
              {adsData.carousel.length > 1 && (
                <div className="absolute bottom-12 left-0 right-0 flex justify-center gap-1.5">
                  {adsData.carousel.map((_, idx) => (
                    <button
                      key={idx}
                      onClick={() => setCarouselIndex(idx)}
                      className={`w-2 h-2 rounded-full transition-colors ${
                        idx === carouselIndex ? 'bg-white' : 'bg-white/40'
                      }`}
                    />
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* 右侧：文字广告 */}
        <div className="vben-card">
          <div className="vben-card-header">
            <h2 className="vben-card-title">文字广告</h2>
          </div>
          <div className="vben-card-body">
            <div className="space-y-2 max-h-48 sm:max-h-56 overflow-y-auto">
              {adsLoading ? (
                <div className="h-32 flex items-center justify-center">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
                </div>
              ) : adsData.text.length > 0 ? (
                adsData.text.map((ad) => (
                  <div
                    key={ad.id}
                    className="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden"
                  >
                    <div className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-800">
                      <a
                        href={ad.link || '#'}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline truncate flex items-center gap-1"
                      >
                        {ad.title}
                        <ExternalLink className="w-3 h-3 flex-shrink-0" />
                      </a>
                      <button
                        onClick={() => toggleTextAd(ad.id)}
                        className="ml-2 p-1 hover:bg-slate-200 dark:hover:bg-slate-700 rounded transition-colors"
                      >
                        {expandedTextAds.has(ad.id) ? (
                          <ChevronUp className="w-4 h-4 text-slate-500" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-slate-500" />
                        )}
                      </button>
                    </div>
                    <AnimatePresence>
                      {expandedTextAds.has(ad.id) && ad.content && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: 'auto', opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.2 }}
                          className="overflow-hidden"
                        >
                          <p className="p-3 text-sm text-slate-600 dark:text-slate-400 border-t border-slate-200 dark:border-slate-700">
                            {ad.content}
                          </p>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                ))
              ) : (
                <div className="h-32 flex items-center justify-center text-slate-400 border border-dashed border-slate-300 dark:border-slate-600 rounded-lg">
                  <span>广告位招租</span>
                </div>
              )}
            </div>
          </div>
        </div>
      </motion.div>

      {/* Admin Stats - 管理员专属 */}
      {user?.is_admin && (
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
            {adminStatsLoading ? (
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
                  <p className="text-2xl font-bold text-emerald-600">{adminStats.online_cookies ?? 0}</p>
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
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.35, duration: 0.3 }}
      >
        <OrderAmountChart />
      </motion.div>

      {/* Today Stats - 今日统计（管理员专属） */}
      {user?.is_admin && (
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
            {adminStatsLoading ? (
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
