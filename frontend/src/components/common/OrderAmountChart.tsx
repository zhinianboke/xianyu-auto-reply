/**
 * 订单趋势折线图组件
 *
 * 功能：
 * 1. 展示近30天每日订单金额与订单笔数双线走势
 * 2. 支持金额/笔数切换视图
 * 3. 汇总：累计金额、累计订单、峰值金额、峰值笔数
 * 4. 普通用户显示自己账号的订单汇总，管理员显示全局汇总
 * 5. 支持暗黑模式 + 自适应手机端
 */
import { useEffect, useState } from 'react'
import {
  ResponsiveContainer,
  ComposedChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'
import { TrendingUp, RefreshCw, ShoppingCart } from 'lucide-react'
import { getOrderAmountTrend, type OrderTrendItem } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'

type ViewMode = 'amount' | 'count'

/** 自定义Tooltip组件 */
function ChartTooltip({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ value: number; dataKey: string; payload: OrderTrendItem }>
  label?: string
}) {
  if (!active || !payload || !payload.length) return null
  const item = payload[0]?.payload
  if (!item) return null
  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-lg shadow-lg px-3 py-2 text-sm">
      <p className="text-slate-500 dark:text-slate-400 mb-1">{label}</p>
      <div className="flex flex-col gap-0.5">
        <p className="font-semibold text-blue-600 dark:text-blue-400">
          ¥{(item.amount || 0).toFixed(2)}
        </p>
        <p className="text-slate-500 dark:text-slate-400 text-xs">
          {item.count} 笔订单
        </p>
      </div>
    </div>
  )
}

export function OrderAmountChart() {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<OrderTrendItem[]>([])
  const [viewMode, setViewMode] = useState<ViewMode>('amount')

  /** 加载趋势数据 */
  const loadTrend = async () => {
    try {
      setLoading(true)
      const result = await getOrderAmountTrend()
      setData(result)
    } catch {
      addToast({ type: 'error', message: '加载订单趋势失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadTrend()
  }, [])

  // 计算汇总数据
  const totalAmount = data.reduce((s, d) => s + d.amount, 0)
  const totalCount = data.reduce((s, d) => s + d.count, 0)
  const maxAmount = Math.max(...data.map(d => d.amount), 0)
  const maxCount = Math.max(...data.map(d => d.count), 0)

  return (
    <div className="vben-card">
      <div className="vben-card-header flex items-center justify-between">
        <h2 className="vben-card-title flex items-center gap-2">
          <TrendingUp className="w-4 h-4" />
          近30天订单趋势
        </h2>
        <div className="flex items-center gap-2">
          {/* 视图切换 */}
          <div className="flex items-center bg-slate-100 dark:bg-slate-700 rounded-lg p-0.5">
            <button
              onClick={() => setViewMode('amount')}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                viewMode === 'amount'
                  ? 'bg-white dark:bg-slate-600 text-blue-600 dark:text-blue-400 font-medium shadow-sm'
                  : 'text-slate-500 dark:text-slate-400'
              }`}
            >
              金额
            </button>
            <button
              onClick={() => setViewMode('count')}
              className={`px-2.5 py-1 text-xs rounded-md transition-colors ${
                viewMode === 'count'
                  ? 'bg-white dark:bg-slate-600 text-emerald-600 dark:text-emerald-400 font-medium shadow-sm'
                  : 'text-slate-500 dark:text-slate-400'
              }`}
            >
              订单数
            </button>
          </div>
          <button
            onClick={loadTrend}
            className="p-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            title="刷新"
          >
            <RefreshCw className={`w-4 h-4 text-slate-400 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>
      <div className="vben-card-body">
        {/* 汇总指标 */}
        <div className="flex items-center justify-between gap-2 mb-3">
          <div className="flex items-center gap-4 text-xs text-slate-500 dark:text-slate-400">
            {viewMode === 'amount' ? (
              <>
                <span>累计金额 <b className="text-blue-600 dark:text-blue-400 ml-0.5">¥{totalAmount.toFixed(2)}</b></span>
                <span className="hidden sm:inline">峰值 <b className="text-rose-600 dark:text-rose-400 ml-0.5">¥{maxAmount.toFixed(2)}</b></span>
              </>
            ) : (
              <>
                <span>累计订单 <b className="text-emerald-600 dark:text-emerald-400 ml-0.5">{totalCount}笔</b></span>
                <span className="hidden sm:inline">峰值 <b className="text-rose-600 dark:text-rose-400 ml-0.5">{maxCount}笔</b></span>
              </>
            )}
          </div>
          <div className="flex items-center gap-1 text-xs text-slate-400">
            <ShoppingCart className="w-3 h-3" />
            <span>{totalCount}笔 · ¥{totalAmount.toFixed(2)}</span>
          </div>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-56 sm:h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
          </div>
        ) : (
          <div className="h-56 sm:h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={data} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="amountGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.02} />
                  </linearGradient>
                  <linearGradient id="countGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#10b981" stopOpacity={0.25} />
                    <stop offset="100%" stopColor="#10b981" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid
                  strokeDasharray="3 3"
                  stroke="currentColor"
                  className="text-slate-200 dark:text-slate-700"
                  vertical={false}
                />
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 11 }}
                  stroke="currentColor"
                  className="text-slate-400 dark:text-slate-500"
                  tickLine={false}
                  axisLine={false}
                  interval={4}
                />
                <YAxis
                  tick={{ fontSize: 11 }}
                  stroke="currentColor"
                  className="text-slate-400 dark:text-slate-500"
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={(v: number) => v >= 1000 ? `${(v / 1000).toFixed(1)}k` : String(v)}
                />
                <Tooltip content={<ChartTooltip />} />

                {viewMode === 'amount' ? (
                  <Area
                    type="monotone"
                    dataKey="amount"
                    stroke="#3b82f6"
                    strokeWidth={2.5}
                    fill="url(#amountGradient)"
                    dot={false}
                    activeDot={{ r: 5, fill: '#3b82f6', stroke: '#fff', strokeWidth: 2 }}
                  />
                ) : (
                  <Area
                    type="monotone"
                    dataKey="count"
                    stroke="#10b981"
                    strokeWidth={2.5}
                    fill="url(#countGradient)"
                    dot={false}
                    activeDot={{ r: 5, fill: '#10b981', stroke: '#fff', strokeWidth: 2 }}
                  />
                )}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  )
}
