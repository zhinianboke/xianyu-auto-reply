import { useEffect, useMemo, useRef, useState } from 'react'
import * as echarts from 'echarts'
import { Button, Form, InputNumber, Select as ArcoSelect, Space } from '@arco-design/web-react'
import { BarChart3 } from 'lucide-react'
import { getAccounts } from '@/api/accounts'
import { getAITokenStats, type AITokenDailyStat, type AITokenModelStat, type AITokenSummary } from '@/api/ai'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import type { Account } from '@/types'

const formatNumber = (value?: number) => Number(value || 0).toLocaleString()

function TokenTrendChart({ data }: { data: AITokenDailyStat[] }) {
  const chartRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!chartRef.current) return
    const chart = echarts.init(chartRef.current)
    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: { top: 0, textStyle: { color: '#64748b' } },
      grid: { top: 42, right: 18, bottom: 24, left: 52, containLabel: true },
      xAxis: { type: 'category', data: data.map((item) => item.date), axisTick: { show: false } },
      yAxis: { type: 'value', splitLine: { lineStyle: { color: '#e9edf3' } } },
      series: [
        { name: '总Token', type: 'line', smooth: true, data: data.map((item) => Number(item.total_tokens || 0)), itemStyle: { color: '#165dff' }, lineStyle: { width: 3 } },
        { name: '输入Token', type: 'line', smooth: true, data: data.map((item) => Number(item.prompt_tokens || 0)), itemStyle: { color: '#14b8a6' } },
        { name: '输出Token', type: 'line', smooth: true, data: data.map((item) => Number(item.completion_tokens || 0)), itemStyle: { color: '#f97316' } },
      ],
    })
    const resizeObserver = new ResizeObserver(() => chart.resize())
    resizeObserver.observe(chartRef.current)
    return () => {
      resizeObserver.disconnect()
      chart.dispose()
    }
  }, [data])

  return <div ref={chartRef} className="h-[320px] w-full" role="img" aria-label="AI Token趋势折线图" />
}

function TokenModelBarChart({ data }: { data: AITokenModelStat[] }) {
  const chartRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    if (!chartRef.current) return
    const chart = echarts.init(chartRef.current)
    chart.setOption({
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { top: 22, right: 18, bottom: 24, left: 84, containLabel: true },
      xAxis: { type: 'value', splitLine: { lineStyle: { color: '#e9edf3' } } },
      yAxis: { type: 'category', data: data.map((item) => item.model_name), axisTick: { show: false } },
      series: [
        {
          name: 'Token',
          type: 'bar',
          data: data.map((item) => Number(item.total_tokens || 0)),
          barWidth: 18,
          itemStyle: { color: '#165dff', borderRadius: [0, 8, 8, 0] },
        },
      ],
    })
    const resizeObserver = new ResizeObserver(() => chart.resize())
    resizeObserver.observe(chartRef.current)
    return () => {
      resizeObserver.disconnect()
      chart.dispose()
    }
  }, [data])

  return <div ref={chartRef} className="h-[320px] w-full" role="img" aria-label="AI Token模型柱状图" />
}

export function AITokenStats() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')
  const [days, setDays] = useState(30)
  const [daily, setDaily] = useState<AITokenDailyStat[]>([])
  const [byModel, setByModel] = useState<AITokenModelStat[]>([])
  const [summary, setSummary] = useState<AITokenSummary>({})

  const loadData = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getAITokenStats({ cookie_id: selectedAccount || undefined, days })
      if (result.success) {
        setDaily(result.daily || [])
        setByModel(result.by_model || [])
        setSummary(result.summary || {})
      }
    } catch {
      addToast({ type: 'error', message: '加载AI Token统计失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    ;(async () => {
      try {
        setAccounts(await getAccounts())
      } catch {
        // ignore
      }
    })()
    loadData()
  }, [_hasHydrated, isAuthenticated, token])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadData()
  }, [_hasHydrated, isAuthenticated, token, selectedAccount, days])

  const hasData = daily.length > 0 || byModel.length > 0
  const averageTokens = useMemo(() => {
    const calls = Number(summary.call_count || 0)
    return calls ? Math.round(Number(summary.total_tokens || 0) / calls) : 0
  }, [summary])

  if (loading && daily.length === 0 && byModel.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      <div className="vben-card">
        <div className="accounts-page-intro">
          <h1>AI Token统计</h1>
          <p>按日期和模型查看AI调用次数、输入Token、输出Token和总Token趋势</p>
        </div>

        <div className="table-toolbar">
          <div className="table-filter-row table-filter-row--lined">
            <Form layout="inline" className="table-filter-form">
              <Form.Item label="筛选账号">
                <ArcoSelect
                  allowClear
                  value={selectedAccount || undefined}
                  onChange={(value) => setSelectedAccount(value || '')}
                  placeholder="所有账号"
                  style={{ width: 180 }}
                  options={accounts.map((account) => ({ label: account.id, value: account.id }))}
                />
              </Form.Item>
              <Form.Item label="统计天数">
                <InputNumber min={1} max={365} value={days} onChange={(value) => setDays(Number(value || 30))} style={{ width: 120 }} />
              </Form.Item>
              <Space className="table-filter-actions">
                <Button onClick={loadData}>
                  刷新
                </Button>
              </Space>
            </Form>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-5 mb-4">
          <div className="rounded-xl bg-slate-50 p-4 dark:bg-white/5"><p className="text-slate-500">调用次数</p><strong className="text-xl">{formatNumber(summary.call_count)}</strong></div>
          <div className="rounded-xl bg-slate-50 p-4 dark:bg-white/5"><p className="text-slate-500">输入Token</p><strong className="text-xl">{formatNumber(summary.prompt_tokens)}</strong></div>
          <div className="rounded-xl bg-slate-50 p-4 dark:bg-white/5"><p className="text-slate-500">输出Token</p><strong className="text-xl">{formatNumber(summary.completion_tokens)}</strong></div>
          <div className="rounded-xl bg-slate-50 p-4 dark:bg-white/5"><p className="text-slate-500">总Token</p><strong className="text-xl">{formatNumber(summary.total_tokens)}</strong></div>
          <div className="rounded-xl bg-slate-50 p-4 dark:bg-white/5"><p className="text-slate-500">单次均值</p><strong className="text-xl">{formatNumber(averageTokens)}</strong></div>
        </div>

        {hasData ? (
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            <div className="rounded-2xl border border-slate-100 p-4 dark:border-white/10">
              <div className="mb-3 flex items-center justify-center gap-2">
                <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">Token趋势</h2>
              </div>
              <TokenTrendChart data={daily} />
            </div>
            <div className="rounded-2xl border border-slate-100 p-4 dark:border-white/10">
              <div className="mb-3 flex items-center justify-center gap-2">
                <h2 className="text-base font-semibold text-slate-800 dark:text-slate-100">模型消耗</h2>
              </div>
              <TokenModelBarChart data={byModel} />
            </div>
          </div>
        ) : (
          <div className="flex min-h-[260px] flex-col items-center justify-center text-center">
            <BarChart3 className="mb-4 h-14 w-14 text-gray-300" />
            <p className="text-sm text-slate-400">暂无AI Token统计数据</p>
          </div>
        )}
      </div>
    </div>
  )
}
