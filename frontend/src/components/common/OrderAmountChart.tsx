/**
 * 订单金额趋势折线图组件
 *
 * 功能：
 * 1. 展示近30天每日订单金额趋势
 * 2. 普通用户显示自己账号的订单汇总，管理员显示全局汇总
 * 3. 支持暗黑模式
 * 4. 自适应手机端
 */
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'
import { TrendingUp, RefreshCw } from 'lucide-react'
import type { OrderTrendItem } from '@/api/accounts'

/** 自定义Tooltip组件 */
function ChartTooltip({ active, payload, label }: {
  active?: boolean
  payload?: Array<{ value: number; dataKey: string; payload: OrderTrendItem }>
  label?: string
}) {
  if (!active || !payload || !payload.length) return null
  const amount = payload.find(p => p.dataKey === 'amount')?.value ?? 0
  const count = payload[0]?.payload?.count ?? 0
  return (
    <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-600 rounded-lg shadow-lg px-3 py-2 text-sm">
      <p className="text-slate-500 dark:text-slate-400 mb-1">{label}</p>
      <p className="font-semibold text-blue-600 dark:text-blue-400">
        ¥{amount.toFixed(2)}
      </p>
      <p className="text-slate-500 dark:text-slate-400 text-xs">
        {count} 笔订单
      </p>
    </div>
  )
}

/** 展示仪表盘已授权的趋势结果和独立加载状态。 */
export function OrderAmountChart({ data, loading, onRefresh }: {
  data: OrderTrendItem[] | null
  loading: boolean
  onRefresh: () => void
}) {
  const totalAmount = data ? `¥${data.reduce((sum, day) => sum + day.amount, 0).toFixed(2)}` : '-'
  const totalCount = data ? `${data.reduce((sum, day) => sum + day.count, 0)}笔` : '-'
  const maxAmount = data ? `¥${Math.max(...data.map(day => day.amount), 0).toFixed(2)}` : '-'

  return (
    <div className="vben-card">
      <div className="vben-card-header flex items-center justify-between">
        <h2 className="vben-card-title flex items-center gap-2">
          <TrendingUp className="w-4 h-4" />
          近30天订单金额趋势
        </h2>
        <div className="flex items-center gap-3">
          {/* 汇总指标 */}
          <div className="hidden sm:flex items-center gap-4 text-sm">
            <div className="text-slate-500 dark:text-slate-400">
              累计金额
              <span className="ml-1 font-semibold text-blue-600 dark:text-blue-400">
                {totalAmount}
              </span>
            </div>
            <div className="text-slate-500 dark:text-slate-400">
              累计订单
              <span className="ml-1 font-semibold text-emerald-600 dark:text-emerald-400">
                {totalCount}
              </span>
            </div>
            <div className="text-slate-500 dark:text-slate-400">
              峰值金额
              <span className="ml-1 font-semibold text-rose-600 dark:text-rose-400">
                {maxAmount}
              </span>
            </div>
          </div>
          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            title="刷新"
          >
            <RefreshCw className={`w-4 h-4 text-slate-400 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>
      <div className="vben-card-body">
        {/* 手机端汇总指标 */}
        <div className="sm:hidden flex items-center justify-between mb-3 text-xs text-slate-500 dark:text-slate-400">
          <span>累计 <b className="text-blue-600 dark:text-blue-400">{totalAmount}</b></span>
          <span>订单 <b className="text-emerald-600 dark:text-emerald-400">{totalCount}</b></span>
          <span>峰值 <b className="text-rose-600 dark:text-rose-400">{maxAmount}</b></span>
        </div>

        {loading ? (
          <div className="flex items-center justify-center h-56 sm:h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500" />
          </div>
        ) : data ? (
          <div className="h-56 sm:h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data} margin={{ top: 8, right: 8, left: -10, bottom: 0 }}>
                <defs>
                  <linearGradient id="amountGradient" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#3b82f6" stopOpacity={0.3} />
                    <stop offset="100%" stopColor="#3b82f6" stopOpacity={0.02} />
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
                <Area
                  type="monotone"
                  dataKey="amount"
                  stroke="#3b82f6"
                  strokeWidth={2.5}
                  fill="url(#amountGradient)"
                  dot={false}
                  activeDot={{ r: 5, fill: '#3b82f6', stroke: '#fff', strokeWidth: 2 }}
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <div className="flex items-center justify-center h-56 sm:h-64 text-sm text-slate-500 dark:text-slate-400">
            订单金额趋势暂不可用
          </div>
        )}
      </div>
    </div>
  )
}
