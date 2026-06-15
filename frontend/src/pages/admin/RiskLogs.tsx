import { useState, useEffect } from 'react'
import { ShieldAlert, RefreshCw, Trash2 } from 'lucide-react'
import { getRiskLogs, clearRiskLogs, type RiskLog } from '@/api/admin'
import { Button, Empty, Form, Modal, Select as ArcoSelect, Space, Table, Tag, Tooltip } from '@arco-design/web-react'
import type { TableColumnProps } from '@arco-design/web-react'
import { getAccounts } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import type { Account } from '@/types'
import { getRiskStatus, getRiskTypeLabel } from '@/utils/riskLabels'

export function RiskLogs() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState<RiskLog[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')

  const loadLogs = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getRiskLogs({ cookie_id: selectedAccount || undefined })
      if (result.success) {
        setLogs(result.data || [])
      }
    } catch {
      addToast({ type: 'error', message: '加载风控日志失败' })
    } finally {
      setLoading(false)
    }
  }

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const data = await getAccounts()
      setAccounts(data)
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadAccounts()
    loadLogs()
  }, [_hasHydrated, isAuthenticated, token])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadLogs()
  }, [_hasHydrated, isAuthenticated, token, selectedAccount])

  const handleClear = async () => {
    Modal.confirm({
      title: '清空风控日志',
      content: '确定要清空所有风控日志吗？此操作不可恢复。',
      okButtonProps: { status: 'danger' },
      onOk: async () => {
        try {
          const result = await clearRiskLogs()
          if (result.success) {
            addToast({ type: 'success', message: '日志已清空' })
            loadLogs()
          } else {
            addToast({ type: 'error', message: result.message || '清空失败' })
          }
        } catch {
          addToast({ type: 'error', message: '清空失败' })
        }
      },
    })
  }

  if (loading && logs.length === 0) {
    return <PageLoading />
  }

  const columns: TableColumnProps<RiskLog>[] = [
    {
      title: '账号ID',
      dataIndex: 'cookie_id',
      render: (value) => <span className="font-medium text-blue-600 dark:text-blue-400 whitespace-nowrap">{value}</span>,
    },
    {
      title: '风控类型',
      dataIndex: 'risk_type',
      render: (value) => <Tag color="red">{getRiskTypeLabel(value)}</Tag>,
    },
    {
      title: '事件描述',
      dataIndex: 'message',
      render: (value: string) => (
        <Tooltip content={value || '-'}>
          <span className="block max-w-[280px] truncate text-slate-500 dark:text-slate-400">
            {value || '-'}
          </span>
        </Tooltip>
      ),
    },
    {
      title: '处理结果',
      dataIndex: 'processing_result',
      render: (value: string) => (
        <Tooltip content={value || '-'}>
          <span className="block max-w-[280px] truncate text-slate-500 dark:text-slate-400">
            {value || '-'}
          </span>
        </Tooltip>
      ),
    },
    {
      title: '处理状态',
      dataIndex: 'processing_status',
      render: (value: string) => {
        const status = getRiskStatus(value)
        return <Tag color={status.color}>{status.label}</Tag>
      },
    },
    {
      title: '错误信息',
      dataIndex: 'error_message',
      render: (value: string) => (
        <Tooltip content={value || '-'}>
          <span className="block max-w-[220px] truncate text-red-500 dark:text-red-400">
            {value || '-'}
          </span>
        </Tooltip>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      render: (value: string) => (
        <span className="text-slate-500 dark:text-slate-400 text-sm whitespace-nowrap">
          {new Date(value).toLocaleString()}
        </span>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      render: (value?: string) => (
        <span className="text-slate-500 dark:text-slate-400 text-sm whitespace-nowrap">
          {value ? new Date(value).toLocaleString() : '-'}
        </span>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      {/* Filter */}
      <div className="vben-card">
        <div className="accounts-page-intro">
          <h1>风控日志</h1>
          <p>查看账号风控相关日志</p>
        </div>
        <div className="table-toolbar">
          <div className="table-filter-row table-filter-row--lined">
            <Form layout="inline" className="table-filter-form">
              <Form.Item label="选择账号">
                <ArcoSelect
                  allowClear
                  value={selectedAccount || undefined}
                  onChange={(value) => setSelectedAccount(value || '')}
                  placeholder="所有账号"
                  style={{ width: 180 }}
                  options={[
                    { value: '', label: '所有账号' },
                    ...accounts.map((account) => ({
                      value: account.id,
                      label: account.id,
                    })),
                  ]}
                />
              </Form.Item>
            </Form>
            <div className="flex gap-2">
              <Space className="batch-actions">
                <Button
                  type="primary"
                  onClick={handleClear} className="accounts-header-btn">
                  <Trash2 />
                  清空日志
                </Button>
                <Button onClick={loadLogs} className="accounts-header-btn">
                  <RefreshCw />
                  刷新
                </Button>
              </Space>
            </div>
          </div>
        </div>

        <Table
          className="accounts-arco-table"
          columns={columns}
          data={logs}
          rowKey="id"
          borderCell={false}
          pagination={false}
          scroll={{ x: 'max-content' }}
          noDataElement={(
            <Empty
              icon={<ShieldAlert className="w-12 h-12 text-slate-300 dark:text-slate-600" />}
              description="暂无风控日志"
            />
          )}
        />
      </div>
    </div>
  )
}
