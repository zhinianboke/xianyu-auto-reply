import { useEffect, useState } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button, Empty, Table, Tag } from '@arco-design/web-react'
import type { TableColumnProps } from '@arco-design/web-react'
import { getAccountExceptions, type AccountException } from '@/api/admin'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'

const severityColor: Record<AccountException['severity'], string> = {
  danger: 'red',
  warning: 'orange',
  normal: 'gray',
}

export function AccountExceptions() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState<AccountException[]>([])

  const loadItems = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getAccountExceptions()
      setItems(result.data || [])
    } catch {
      addToast({ type: 'error', message: '加载账号异常失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadItems()
  }, [_hasHydrated, isAuthenticated, token])

  if (loading && items.length === 0) return <PageLoading />

  const columns: TableColumnProps<AccountException>[] = [
    {
      title: '账号',
      dataIndex: 'cookie_id',
      width: 220,
      render: (_, row) => (
        <div>
          <div className="font-medium text-slate-900 dark:text-slate-100">{row.cookie_id}</div>
          <div className="text-xs text-slate-500">{row.remark || '-'}</div>
        </div>
      ),
    },
    {
      title: '级别',
      dataIndex: 'severity',
      width: 100,
      render: (value) => <Tag color={severityColor[value as AccountException['severity']]}>{String(value)}</Tag>,
    },
    {
      title: '问题',
      dataIndex: 'issues',
      render: (_, row) => (
        <div className="flex flex-wrap gap-2">
          {row.issues.map((issue) => <Tag key={issue} color={severityColor[row.severity]}>{issue}</Tag>)}
        </div>
      ),
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 110,
      render: (value) => <Tag color={value ? 'green' : 'gray'}>{value ? '启用' : '停用'}</Tag>,
    },
    {
      title: '暂停时间',
      dataIndex: 'pause_duration',
      width: 120,
      render: (value) => `${value || 0} 分钟`,
    },
  ]

  return (
    <div className="space-y-4">
      <div className="vben-card">
        <div className="accounts-page-intro">
          <h1>账号异常处理</h1>
          <p>集中查看停用、风控失败、待处理和未配置回复的账号。</p>
        </div>
        <div className="table-toolbar">
          <div className="table-filter-row table-filter-row--lined">
            <div className="flex items-center gap-2 rounded-lg bg-slate-50 px-4 py-2 dark:bg-slate-800/50">
              <AlertTriangle className="w-4 h-4 text-amber-500" />
              <span className="text-sm text-slate-500">待处理</span>
              <span className="font-semibold">{items.length}</span>
            </div>
            <Button type="primary" onClick={loadItems} loading={loading} className="accounts-header-btn">
              <RefreshCw />
              刷新
            </Button>
          </div>
        </div>
        <Table
          className="accounts-arco-table"
          columns={columns}
          data={items}
          rowKey="cookie_id"
          pagination={false}
          borderCell={false}
          scroll={{ x: 'max-content' }}
          noDataElement={<Empty description="暂无账号异常" />}
        />
      </div>
    </div>
  )
}
