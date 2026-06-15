import { useEffect, useState } from 'react'
import { Activity, Database, HardDrive, RefreshCw, Shield, Users } from 'lucide-react'
import { Button, Empty, Table, Tag } from '@arco-design/web-react'
import type { TableColumnProps } from '@arco-design/web-react'
import { getOpsHealth, type OpsHealth } from '@/api/admin'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import { getRiskStatus, getRiskTypeLabel } from '@/utils/riskLabels'

const formatBytes = (value: number) => {
  if (!value) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(Math.floor(Math.log(value) / Math.log(1024)), units.length - 1)
  return `${(value / Math.pow(1024, index)).toFixed(index === 0 ? 0 : 1)} ${units[index]}`
}

const toNumber = (value: unknown) => Number.isFinite(Number(value)) ? Number(value) : 0

const statusColor: Record<string, string> = {
  healthy: 'green',
  warning: 'orange',
  unhealthy: 'red',
  ok: 'green',
  idle: 'gray',
  error: 'red',
}

export function SystemHealth() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [health, setHealth] = useState<OpsHealth | null>(null)

  const loadHealth = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      setHealth(await getOpsHealth())
    } catch {
      addToast({ type: 'error', message: '加载系统健康信息失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadHealth()
  }, [_hasHydrated, isAuthenticated, token])

  if (loading && !health) return <PageLoading />

  const system = health?.system
  const accounts = health?.accounts
  const risks = health?.risks
  const recentRiskLogs = Array.isArray(risks?.recent) ? risks.recent : []

  const cards = health ? [
    { icon: Activity, label: 'CPU', value: `${toNumber(system?.cpu_percent).toFixed(1)}%` },
    { icon: HardDrive, label: '内存', value: `${toNumber(system?.memory_percent).toFixed(1)}%` },
    { icon: Database, label: '数据库', value: formatBytes(toNumber(system?.database_size)) },
    { icon: Users, label: '账号', value: `${toNumber(accounts?.enabled)}/${toNumber(accounts?.total)}` },
  ] : []

  const riskColumns: TableColumnProps<Record<string, unknown>>[] = [
    { title: '账号', dataIndex: 'cookie_id', render: (value) => <span className="font-medium">{String(value || '-')}</span> },
    { title: '类型', dataIndex: 'event_type', render: (value) => getRiskTypeLabel(String(value || '')) },
    {
      title: '状态',
      dataIndex: 'processing_status',
      render: (value) => {
        const status = getRiskStatus(String(value || ''))
        return <Tag color={status.color}>{status.label}</Tag>
      },
    },
    { title: '时间', dataIndex: 'created_at', render: (value) => <span className="whitespace-nowrap text-slate-500">{String(value || '-')}</span> },
  ]

  return (
    <div className="space-y-4">
      <div className="vben-card">
        <div className="accounts-page-intro">
          <h1>系统健康</h1>
          <p>查看服务、数据库、磁盘、账号和最近风控状态。</p>
        </div>
        <div className="table-toolbar">
          <div className="table-filter-row table-filter-row--lined">
            <div className="flex items-center gap-2">
              <Shield className="w-5 h-5 text-slate-500" />
              <Tag color={statusColor[health?.status || ''] || 'gray'}>{health?.status || '-'}</Tag>
            </div>
            <Button type="primary" onClick={loadHealth} loading={loading} className="accounts-header-btn">
              <RefreshCw />
              刷新
            </Button>
          </div>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 p-4">
          {cards.map((card) => (
            <div key={card.label} className="rounded-lg border border-slate-200 p-4 dark:border-slate-700">
              <div className="flex items-center gap-2 text-sm text-slate-500">
                <card.icon className="w-4 h-4" />
                {card.label}
              </div>
              <div className="mt-2 text-2xl font-semibold text-slate-900 dark:text-slate-100">{card.value}</div>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 p-4 pt-0">
          <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-700">
            <h2 className="settings-section-title">服务状态</h2>
            <div className="mt-3 space-y-2">
              {Object.entries(health?.services || {}).map(([key, value]) => (
                <div key={key} className="flex items-center justify-between text-sm">
                  <span className="text-slate-500">{key}</span>
                  <Tag color={statusColor[value] || 'gray'}>{value}</Tag>
                </div>
              ))}
            </div>
          </div>
          <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-700">
            <h2 className="settings-section-title">风险概览</h2>
            <div className="mt-3 grid grid-cols-3 gap-3 text-center">
              <div><div className="text-xl font-semibold">{toNumber(risks?.recent_total)}</div><div className="text-xs text-slate-500">最近记录</div></div>
              <div><div className="text-xl font-semibold text-red-500">{toNumber(risks?.failed)}</div><div className="text-xs text-slate-500">失败</div></div>
              <div><div className="text-xl font-semibold text-amber-500">{toNumber(risks?.processing)}</div><div className="text-xs text-slate-500">处理中</div></div>
            </div>
          </div>
        </div>
        <Table
          className="accounts-arco-table"
          columns={riskColumns}
          data={recentRiskLogs}
          rowKey="id"
          pagination={false}
          borderCell={false}
          noDataElement={<Empty description="暂无风控记录" />}
        />
      </div>
    </div>
  )
}
