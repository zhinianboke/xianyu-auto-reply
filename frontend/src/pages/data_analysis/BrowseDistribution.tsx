/**
 * 流量分布组件
 *
 * 独立的账号选择、时间范围和查询，展示来源分布、商品分布、时间分布、地域分布
 */
import { useEffect, useState, useCallback } from 'react'
import { motion } from 'framer-motion'
import { RefreshCw } from 'lucide-react'
import { getAccountDetails } from '@/api/accounts'
import { getBrowseSummary, type BrowseSummaryRequest, type ProfileItem } from '@/api/data_analysis'
import { useUIStore } from '@/store/uiStore'
import type { AccountDetail } from '@/types'

/** 时间范围选项 */
const DATE_TYPE_OPTIONS = [
  { value: 'recent1d', label: '近1天' },
  { value: 'recent7d', label: '近7天' },
  { value: 'recent30d', label: '近30天' },
  { value: 'customDate', label: '自定义' },
] as const

type DateTypeValue = typeof DATE_TYPE_OPTIONS[number]['value']

/** 单个分布卡片 */
function DistributionCard({
  title,
  items,
  labelWidth = 'w-16',
}: {
  title: string
  items: ProfileItem[]
  labelWidth?: string
}) {
  return (
    <div className="bg-white dark:bg-slate-800 rounded-lg p-4 shadow-sm border border-gray-100 dark:border-slate-700">
      <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-3">{title}</h3>
      <div className="h-[240px] overflow-y-auto pr-2 space-y-2.5">
        {items.map((item, idx) => (
          <div key={idx} className="flex items-center gap-2">
            <span
              className={`text-xs text-gray-600 dark:text-gray-400 ${labelWidth} flex-shrink-0 truncate`}
              title={item.profileVal}
            >
              {item.profileVal}
            </span>
            <div className="flex-1 h-5 bg-gray-100 dark:bg-slate-700 rounded overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded transition-all"
                style={{ width: `${item.usrRatio * 100}%` }}
              />
            </div>
            <span className="text-xs text-gray-500 dark:text-gray-400 w-14 text-right flex-shrink-0">
              {item.usrRatioFormat}
            </span>
          </div>
        ))}
        {items.length === 0 && (
          <p className="text-xs text-gray-400 text-center py-4">暂无数据</p>
        )}
      </div>
    </div>
  )
}

export function BrowseDistribution() {
  const { addToast } = useUIStore()
  const [accounts, setAccounts] = useState<AccountDetail[]>([])
  const [selectedAccountId, setSelectedAccountId] = useState<number | null>(null)
  const [dateType, setDateType] = useState<DateTypeValue>('recent1d')
  const [customStartDate, setCustomStartDate] = useState('')
  const [customEndDate, setCustomEndDate] = useState('')
  const [loading, setLoading] = useState(false)
  const [browseData, setBrowseData] = useState<{
    sceneSourceList: ProfileItem[]
    itemCateList: ProfileItem[]
    buyerActiveList: ProfileItem[]
    buyerProvinceList: ProfileItem[]
  } | null>(null)

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

  /** 获取流量分布数据 */
  const fetchData = useCallback(async () => {
    if (!selectedAccountId) return

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
      const params: BrowseSummaryRequest = {
        account_id: selectedAccountId,
        date_type: dateType,
        date_range: dateType === 'customDate'
          ? `${toCompactDate(customStartDate)}|${toCompactDate(customEndDate)}`
          : '',
      }
      const result = await getBrowseSummary(params)
      if (result.success && result.data) {
        setBrowseData(result.data.data || null)
      } else {
        addToast({ type: 'error', message: result.message || '获取流量分布失败' })
        setBrowseData(null)
      }
    } catch {
      addToast({ type: 'error', message: '获取流量分布失败，请稍后重试' })
      setBrowseData(null)
    } finally {
      setLoading(false)
    }
  }, [selectedAccountId, dateType, customStartDate, customEndDate, addToast])

  /** 非自定义日期时自动触发 */
  useEffect(() => {
    if (selectedAccountId && dateType !== 'customDate') {
      fetchData()
    }
  }, [selectedAccountId, dateType, fetchData])

  return (
    <div className="space-y-4">
      {/* 顶部操作栏 */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 bg-white dark:bg-slate-800 rounded-lg p-4 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-800 dark:text-gray-200">
          流量分布
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

      {/* 加载中 */}
      {loading && (
        <div className="flex items-center justify-center py-8">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
          <span className="ml-2 text-sm text-gray-500 dark:text-gray-400">加载中...</span>
        </div>
      )}

      {/* 分布图表 */}
      {!loading && browseData && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="grid grid-cols-1 lg:grid-cols-2 gap-4"
        >
          <DistributionCard title="来源分布" items={browseData.sceneSourceList || []} />
          <DistributionCard title="商品分布" items={browseData.itemCateList || []} labelWidth="w-24" />
          <DistributionCard title="时间分布" items={browseData.buyerActiveList || []} />
          <DistributionCard title="地域分布" items={browseData.buyerProvinceList || []} />
        </motion.div>
      )}

      {/* 未选择账号提示 */}
      {!selectedAccountId && (
        <div className="flex flex-col items-center justify-center py-12 text-gray-400">
          <p>请先选择一个账号</p>
        </div>
      )}
    </div>
  )
}
