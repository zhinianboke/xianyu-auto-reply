/**
 * 商品监控总览页
 *
 * 功能：
 * 1. 展示商品监控任务总数、启用/停用数
 * 2. 展示今日任务执行成功/失败/部分成功数
 * 3. 展示今日采集数、今日私信成功/失败数、今日下单数（均按商品ID去重）
 * 4. 展示累计采集/私信/下单数等汇总指标
 * 说明：数据按当前用户隔离，管理员可查看全量统计。
 */
import { useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import {
  Activity,
  AlertCircle,
  CheckCircle2,
  CopyX,
  ListChecks,
  MessageSquare,
  MessageSquareX,
  Package,
  PackageSearch,
  PauseCircle,
  PlusCircle,
  RefreshCw,
  ShoppingCart,
  XCircle,
} from 'lucide-react'
import {
  getListingMonitorOverview,
  type ListingMonitorOverview,
} from '@/api/listingMonitor'
import { PageLoading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'

type CardColor = 'primary' | 'success' | 'warning' | 'info' | 'danger' | 'purple'

interface OverviewCard {
  icon: typeof Activity
  label: string
  value: number
  color: CardColor
  hint?: string
}

// 卡片图标底色样式
const colorClasses: Record<CardColor, string> = {
  primary: 'bg-blue-100 text-blue-600 dark:bg-blue-900/30 dark:text-blue-400',
  success: 'bg-green-100 text-green-600 dark:bg-green-900/30 dark:text-green-400',
  warning: 'bg-amber-100 text-amber-600 dark:bg-amber-900/30 dark:text-amber-400',
  info: 'bg-cyan-100 text-cyan-600 dark:bg-cyan-900/30 dark:text-cyan-400',
  danger: 'bg-red-100 text-red-600 dark:bg-red-900/30 dark:text-red-400',
  purple: 'bg-purple-100 text-purple-600 dark:bg-purple-900/30 dark:text-purple-400',
}

export function MonitorOverview() {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [data, setData] = useState<ListingMonitorOverview | null>(null)

  const loadOverview = async (silent = false) => {
    if (silent) setRefreshing(true)
    else setLoading(true)
    const result = await getListingMonitorOverview()
    if (result.success && result.data) {
      setData(result.data)
    } else {
      addToast({ type: 'error', message: result.message || '加载监控总览失败' })
    }
    setLoading(false)
    setRefreshing(false)
  }

  useEffect(() => {
    loadOverview()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (loading) {
    return <PageLoading />
  }

  const taskCards: OverviewCard[] = [
    { icon: ListChecks, label: '任务总数', value: data?.total_tasks ?? 0, color: 'primary' },
    { icon: CheckCircle2, label: '启用任务数', value: data?.enabled_tasks ?? 0, color: 'success' },
    { icon: PauseCircle, label: '停用任务数', value: data?.disabled_tasks ?? 0, color: 'warning' },
    { icon: Activity, label: '今日执行次数', value: data?.today_run_total ?? 0, color: 'info' },
    { icon: CheckCircle2, label: '今日任务成功数', value: data?.today_run_success ?? 0, color: 'success' },
    { icon: AlertCircle, label: '今日任务部分成功数', value: data?.today_run_partial ?? 0, color: 'warning' },
    { icon: XCircle, label: '今日任务失败数', value: data?.today_run_failed ?? 0, color: 'danger' },
  ]

  const todayCards: OverviewCard[] = [
    { icon: PackageSearch, label: '今日采集数', value: data?.today_collected ?? 0, color: 'primary', hint: '按商品ID去重' },
    { icon: PlusCircle, label: '今日新增商品数', value: data?.today_new ?? 0, color: 'info', hint: '按商品ID去重' },
    { icon: MessageSquare, label: '今日私信成功', value: data?.today_dm ?? 0, color: 'success', hint: '按商品ID去重' },
    { icon: MessageSquareX, label: '今日私信失败', value: data?.today_dm_failed ?? 0, color: 'danger', hint: '按创建时间统计，按商品ID去重' },
    { icon: ShoppingCart, label: '今日下单数', value: data?.today_ordered ?? 0, color: 'purple', hint: '按商品ID去重' },
    { icon: XCircle, label: '今日下单失败数', value: data?.today_order_failed ?? 0, color: 'danger', hint: '按创建时间统计，按商品ID去重' },
    { icon: CopyX, label: '今日重复跳过数', value: data?.today_order_duplicate ?? 0, color: 'warning', hint: '按创建时间统计，按商品ID去重' },
  ]

  const totalCards: OverviewCard[] = [
    { icon: Package, label: '累计采集商品数', value: data?.total_items ?? 0, color: 'primary', hint: '按商品ID去重' },
    { icon: MessageSquare, label: '累计私信数', value: data?.total_dm ?? 0, color: 'success', hint: '按商品ID去重' },
    { icon: ShoppingCart, label: '累计下单成功数', value: data?.total_ordered ?? 0, color: 'purple', hint: '按商品ID去重' },
  ]

  const renderCards = (cards: OverviewCard[]) => (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-6 gap-3 sm:gap-4">
      {cards.map((card, index) => {
        const Icon = card.icon
        return (
          <motion.div
            key={card.label}
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: index * 0.05, duration: 0.3 }}
            className="flex items-center gap-3 p-3 sm:p-4 rounded-xl border border-slate-100 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-sm"
          >
            <div className={`w-11 h-11 flex items-center justify-center rounded-full shrink-0 ${colorClasses[card.color]}`}>
              <Icon className="w-5 h-5" />
            </div>
            <div className="min-w-0">
              <p className="text-xl font-bold text-slate-800 dark:text-slate-100 truncate">{card.value}</p>
              <p className="text-xs text-slate-500 dark:text-slate-400 truncate" title={card.label}>{card.label}</p>
              {card.hint && (
                <p className="text-[11px] text-slate-400 dark:text-slate-500 truncate">{card.hint}</p>
              )}
            </div>
          </motion.div>
        )
      })}
    </div>
  )

  return (
    <div className="space-y-4">
      {/* 页头 */}
      <div className="page-header flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="page-title">监控总览</h1>
          <p className="page-description">商品监控任务与今日采集、私信、下单概览（按商品ID去重）</p>
        </div>
        <button onClick={() => loadOverview(true)} className="btn-ios-secondary" disabled={refreshing}>
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
          <span className="hidden sm:inline">刷新数据</span>
          <span className="sm:hidden">刷新</span>
        </button>
      </div>

      {/* 任务概览 */}
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">任务概览</h2>
        </div>
        <div className="vben-card-body">{renderCards(taskCards)}</div>
      </div>

      {/* 今日统计 */}
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">今日统计</h2>
        </div>
        <div className="vben-card-body">{renderCards(todayCards)}</div>
      </div>

      {/* 累计统计 */}
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">累计统计</h2>
        </div>
        <div className="vben-card-body">{renderCards(totalCards)}</div>
      </div>
    </div>
  )
}

export default MonitorOverview
