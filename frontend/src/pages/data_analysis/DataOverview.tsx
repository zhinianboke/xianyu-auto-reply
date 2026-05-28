/**
 * 数据总览页面
 *
 * 展示卖家数据概览，包括核心指标卡片和趋势图表
 * 支持多账号切换、时间范围选择和自定义日期范围
 */
import { useEffect, useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import {
  BarChart3,
  Eye,
  MousePointerClick,
  ShoppingCart,
  DollarSign,
  Users,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Package,
} from 'lucide-react'
import { getAccountDetails } from '@/api/accounts'
import {
  getSellerSummary,
  type BannerDataItem,
  type GraphDataItem,
  type SellerSummaryRequest,
} from '@/api/data_analysis'
import { useUIStore } from '@/store/uiStore'
import type { AccountDetail } from '@/types'
import { BrowseDistribution } from './BrowseDistribution'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts'

/** 时间范围选项 */
const DATE_TYPE_OPTIONS = [
  { value: 'recent1d', label: '近1天' },
  { value: 'recent7d', label: '近7天' },
  { value: 'recent30d', label: '近30天' },
  { value: 'customDate', label: '自定义' },
] as const

type DateTypeValue = typeof DATE_TYPE_OPTIONS[number]['value']

/** 指标名称映射（中文） */
const METRIC_NAME_MAP: Record<string, string> = {
  payAmt: '支付金额（元）',
  fstByrPayAmt: '首次买家支付金额',
  rptByrPayAmt: '复购买家支付金额',
  payOrdCnt: '支付笔数',
  aov: '客单价（元）',
  rfdAmt: '退款金额（元）',
  showUv: '商品曝光人数',
  showPv: '商品曝光次数',
  ipvUv: '商品浏览人数',
  ipv: '商品浏览次数',
  payByrCnt: '支付买家数',
  vstPv: '商品访问次数',
  vstUv: '商品访问人数',
  showItmCnt: '曝光商品数',
  ipvItmCnt: '访问商品数',
  stItmCnt: '成交商品数',
  uctr: '访问转化率',
  onlCnt: '在架商品数',
  chatUv: '咨询人数',
  rptOrdCnt: '复购订单数',
  rptByrCnt: '复购买家数',
  rpr: '复购率',
  rep3minUvRate: '3分钟回复率',
  showPvCmpPctl: '曝光竞争力',
  payOrdCntCmpPctl: '成交竞争力',
  rfdOrdCnt: '退款笔数',
  addRecItemCnt: '加入推荐商品数',
  priceCutItmCnt: '降价商品数',
  favCnt: '收藏数',
  newItmCnt: '新发商品数',
  cmtItmCnt: '评价商品数',
}

/** 核心指标卡片配置（按官方顺序，两列排列） */
const CORE_METRICS = [
  { name: 'vstPv', icon: MousePointerClick, label: '商品访问次数' },
  { name: 'vstUv', icon: Users, label: '商品访问人数' },
  { name: 'showPv', icon: Eye, label: '商品曝光次数' },
  { name: 'showUv', icon: Eye, label: '商品曝光人数' },
  { name: 'ipv', icon: MousePointerClick, label: '商品浏览次数' },
  { name: 'ipvUv', icon: Users, label: '商品浏览人数' },
  { name: 'payOrdCnt', icon: ShoppingCart, label: '支付笔数' },
  { name: 'payAmt', icon: DollarSign, label: '支付金额（元）' },
  { name: 'rfdOrdCnt', icon: Package, label: '发起退款笔数' },
  { name: 'rfdAmt', icon: DollarSign, label: '发起退款金额（元）' },
]

export function DataOverview() {
  const { addToast } = useUIStore()
  const [accounts, setAccounts] = useState<AccountDetail[]>([])
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  const [dateType, setDateType] = useState<DateTypeValue>('recent1d')
  const [customStartDate, setCustomStartDate] = useState('')
  const [customEndDate, setCustomEndDate] = useState('')
  const [loading, setLoading] = useState(false)
  const [bannerData, setBannerData] = useState<BannerDataItem[]>([])
  const [graphData, setGraphData] = useState<GraphDataItem[]>([])
  const [chartMetric, setChartMetric] = useState('vstPv')

  /** 将 yyyy-MM-dd 转为 yyyyMMdd */
  const toCompactDate = (dateStr: string): string => {
    return dateStr.replace(/-/g, '')
  }

  /** 加载账号列表 */
  useEffect(() => {
    const loadAccounts = async () => {
      try {
        const data = await getAccountDetails()
        setAccounts(data)
      } catch {
        addToast({ type: 'error', message: '加载账号列表失败' })
      }
    }
    loadAccounts()
  }, [])

  /** 获取数据 */
  const fetchData = useCallback(async () => {
    if (!selectedAccountId) return

    // 自定义日期范围校验
    if (dateType === 'customDate') {
      if (!customStartDate || !customEndDate) {
        addToast({ type: 'error', message: '请选择开始日期和结束日期' })
        return
      }
      if (customStartDate > customEndDate) {
        addToast({ type: 'error', message: '开始日期不能晚于结束日期' })
        return
      }
    }

    setLoading(true)
    try {
      const params: SellerSummaryRequest = {
        account_id: selectedAccountId,
        date_type: dateType,
        date_range: dateType === 'customDate'
          ? `${toCompactDate(customStartDate)}|${toCompactDate(customEndDate)}`
          : '',
      }
      const result = await getSellerSummary(params)
      if (result.success && result.data) {
        const summaryData = result.data.data?.graphBannerBenchData
        if (summaryData) {
          setBannerData(summaryData.bannerDataList || [])
          setGraphData(summaryData.graphDataList || [])
        } else {
          setBannerData([])
          setGraphData([])
        }
      } else {
        addToast({ type: 'error', message: result.message || '获取数据失败' })
        setBannerData([])
        setGraphData([])
      }
    } catch {
      addToast({ type: 'error', message: '获取数据失败，请稍后重试' })
    } finally {
      setLoading(false)
    }
  }, [selectedAccountId, dateType, customStartDate, customEndDate, addToast])

  /** 账号或时间范围变化时重新获取数据（非自定义日期时自动触发） */
  useEffect(() => {
    if (selectedAccountId && dateType !== 'customDate') {
      fetchData()
    }
  }, [selectedAccountId, dateType, fetchData])

  /** 根据name查找banner数据 */
  const getBannerItem = (name: string): BannerDataItem | undefined => {
    return bannerData.find((item) => item.name === name)
  }

  /** 格式化日期（20260527 -> 05/27） */
  const formatDate = (ds: string): string => {
    if (!ds || ds.length !== 8) return ds
    return `${ds.slice(4, 6)}/${ds.slice(6, 8)}`
  }

  /** 渲染涨跌幅 */
  const renderRatio = (item: BannerDataItem | undefined) => {
    if (!item || !item.ratioFormat || item.ratioFormat === '-') {
      return <span className="text-gray-400 text-xs">--</span>
    }
    const ratio = item.ratio ?? 0
    const isUp = ratio > 0
    const isDown = ratio < 0
    return (
      <span className={`text-xs flex items-center gap-0.5 ${isUp ? 'text-green-500' : isDown ? 'text-red-500' : 'text-gray-400'}`}>
        {isUp && <TrendingUp className="w-3 h-3" />}
        {isDown && <TrendingDown className="w-3 h-3" />}
        {isUp ? '+' : ''}{item.ratioFormat}
      </span>
    )
  }

  return (
    <div className="space-y-4">
      {/* 顶部操作栏 */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-white dark:bg-slate-800 rounded-lg p-4 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
          数据总览
        </h2>
        <div className="flex flex-wrap items-center gap-3">
          {/* 账号选择 */}
          <select
            className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-slate-700 text-gray-700 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={selectedAccountId ?? ''}
            onChange={(e) => setSelectedAccountId(Number(e.target.value))}
          >
            <option value="" disabled>选择账号</option>
            {[...accounts].sort((a, b) => (a.enabled === b.enabled ? 0 : a.enabled ? -1 : 1)).map((acc) => (
              <option key={acc.pk} value={acc.pk}>
                {acc.note || acc.id || `账号${acc.pk}`}{acc.enabled ? '' : '（已禁用）'}
              </option>
            ))}
          </select>

          {/* 时间范围选择 */}
          <div className="flex rounded-md overflow-hidden border border-gray-300 dark:border-gray-600">
            {DATE_TYPE_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className={`px-3 py-1.5 text-sm transition-colors ${
                  dateType === opt.value
                    ? 'bg-blue-500 text-white'
                    : 'bg-white dark:bg-slate-700 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-slate-600'
                }`}
                onClick={() => setDateType(opt.value)}
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* 自定义日期范围选择器 */}
          {dateType === 'customDate' && (
            <div className="flex items-center gap-2">
              <input
                type="date"
                className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-slate-700 text-gray-700 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={customStartDate}
                onChange={(e) => setCustomStartDate(e.target.value)}
              />
              <span className="text-gray-400 text-sm">至</span>
              <input
                type="date"
                className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-slate-700 text-gray-700 dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
                value={customEndDate}
                onChange={(e) => setCustomEndDate(e.target.value)}
              />
              <button
                className="px-3 py-1.5 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600 transition-colors disabled:opacity-50"
                onClick={fetchData}
                disabled={loading || !selectedAccountId || !customStartDate || !customEndDate}
              >
                查询
              </button>
            </div>
          )}

          {/* 刷新按钮 */}
          <button
            className="p-1.5 rounded-md border border-gray-300 dark:border-gray-600 bg-white dark:bg-slate-700 text-gray-600 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-slate-600 transition-colors disabled:opacity-50"
            onClick={fetchData}
            disabled={loading || !selectedAccountId}
            title="刷新数据"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* 加载遮罩 */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
          <span className="ml-3 text-gray-500 dark:text-gray-400">加载中...</span>
        </div>
      )}

      {/* 核心指标卡片 + 趋势图表（左右布局） */}
      {!loading && bannerData.length > 0 && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col lg:flex-row gap-4"
        >
          {/* 左侧：指标卡片 */}
          <div className="w-full lg:w-[420px] lg:flex-shrink-0 grid grid-cols-2 gap-3 auto-rows-min">
            {CORE_METRICS.map((metric) => {
              const item = getBannerItem(metric.name)
              if (!item) return null
              const Icon = metric.icon
              const isSelected = chartMetric === metric.name
              return (
                <div
                  key={metric.name}
                  className={`bg-white dark:bg-slate-800 rounded-lg p-3 shadow-sm border cursor-pointer transition-all ${
                    isSelected
                      ? 'border-blue-500 ring-2 ring-blue-200 dark:ring-blue-800 shadow-md'
                      : 'border-gray-100 dark:border-slate-700 hover:shadow-md hover:border-blue-300 dark:hover:border-blue-600'
                  }`}
                  onClick={() => setChartMetric(metric.name)}
                >
                  <div className="flex items-center mb-1.5">
                    <span className={`text-xs flex items-center gap-1 ${isSelected ? 'text-blue-600 dark:text-blue-400 font-medium' : 'text-gray-500 dark:text-gray-400'}`}>
                      <Icon className="w-3.5 h-3.5" />
                      {metric.label}
                    </span>
                  </div>
                  <div className="flex items-end justify-between">
                    <span className="text-xl font-bold text-gray-800 dark:text-gray-100">
                      {metric.name === 'payAmt' || metric.name === 'rfdAmt' ? `¥${item.dataStr}` : item.dataStr}
                    </span>
                    <div className="text-right">
                      {renderRatio(item)}
                      {item.lastDataStr && item.lastDataStr !== '-' && (
                        <div className="text-xs text-gray-400 mt-0.5">
                          前{item.cycle?.replace('前', '') || ''} {item.lastDataStr}
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )
            })}
          </div>

          {/* 右侧：趋势图表 */}
          {graphData.length > 0 && (
            <div className="flex-1 min-w-0 bg-white dark:bg-slate-800 rounded-lg p-4 shadow-sm border border-gray-100 dark:border-slate-700">
              <div className="flex items-center mb-4">
                <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 flex items-center gap-1.5">
                  <BarChart3 className="w-4 h-4" />
                  {CORE_METRICS.find((m) => m.name === chartMetric)?.label || METRIC_NAME_MAP[chartMetric] || chartMetric} - 趋势图
                </h3>
              </div>
              <div className="h-[400px]">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={graphData.map((item) => ({ ...item, date: formatDate(item.ds) }))}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
                    <XAxis
                      dataKey="date"
                      tick={{ fontSize: 12 }}
                      stroke="#9ca3af"
                    />
                    <YAxis
                      tick={{ fontSize: 12 }}
                      stroke="#9ca3af"
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'rgba(255,255,255,0.95)',
                        border: '1px solid #e5e7eb',
                        borderRadius: '8px',
                        fontSize: '12px',
                      }}
                      labelFormatter={(label) => `日期: ${label}`}
                      formatter={(value) => [
                        typeof value === 'number' && value < 1 && value > 0
                          ? `${(value * 100).toFixed(2)}%`
                          : String(value ?? ''),
                        CORE_METRICS.find((m) => m.name === chartMetric)?.label || chartMetric,
                      ]}
                    />
                    <Legend />
                    <Line
                      type="monotone"
                      dataKey={chartMetric}
                      name={CORE_METRICS.find((m) => m.name === chartMetric)?.label || chartMetric}
                      stroke="#3b82f6"
                      strokeWidth={2}
                      dot={{ r: 3 }}
                      activeDot={{ r: 5 }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          )}
        </motion.div>
      )}

      {/* 流量分布模块（独立的账号和时间选择） */}
      <BrowseDistribution />

      {/* 无数据提示 */}
      {!loading && bannerData.length === 0 && selectedAccountId && (
        <div className="flex flex-col items-center justify-center py-16 text-gray-400">
          <BarChart3 className="w-12 h-12 mb-3" />
          <p>暂无数据</p>
          <p className="text-sm mt-1">请确认账号Cookie有效且已开通卖家数据罗盘</p>
        </div>
      )}

      {/* 未选择账号提示 */}
      {!selectedAccountId && (
        <div className="flex flex-col items-center justify-center py-16 text-gray-400">
          <Users className="w-12 h-12 mb-3" />
          <p>请先选择一个账号</p>
        </div>
      )}
    </div>
  )
}
