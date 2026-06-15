import { useEffect, useMemo, useState } from 'react'
import { Button, Empty, Form, InputNumber, Select as ArcoSelect, Space, Table, Tag, Tooltip } from '@arco-design/web-react'
import type { TableColumnProps } from '@arco-design/web-react'
import { FileText } from 'lucide-react'
import { getAccounts } from '@/api/accounts'
import { getAICallLogs, type AICallLog } from '@/api/ai'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import type { Account } from '@/types'

const formatNumber = (value?: number) => Number(value || 0).toLocaleString()

export function AICallDetails() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState<AICallLog[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')
  const [inputRate, setInputRate] = useState(0)
  const [outputRate, setOutputRate] = useState(0)

  const loadData = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getAICallLogs({ cookie_id: selectedAccount || undefined, limit: 200 })
      if (result.success) {
        setLogs(result.data || [])
      }
    } catch {
      addToast({ type: 'error', message: '加载AI调用明细失败' })
    } finally {
      setLoading(false)
    }
  }

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setAccounts(await getAccounts())
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadAccounts()
    loadData()
  }, [_hasHydrated, isAuthenticated, token])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadData()
  }, [_hasHydrated, isAuthenticated, token, selectedAccount])

  const totals = useMemo(() => {
    const prompt = logs.reduce((sum, item) => sum + Number(item.prompt_tokens || 0), 0)
    const completion = logs.reduce((sum, item) => sum + Number(item.completion_tokens || 0), 0)
    const cost = (prompt / 1_000_000) * inputRate + (completion / 1_000_000) * outputRate
    return { prompt, completion, total: prompt + completion, cost }
  }, [logs, inputRate, outputRate])

  if (loading && logs.length === 0) {
    return <PageLoading />
  }

  const columns: TableColumnProps<AICallLog>[] = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 170,
      render: (value) => <span className="whitespace-nowrap text-slate-500">{value}</span>,
    },
    {
      title: '账号',
      dataIndex: 'cookie_id',
      width: 150,
      render: (value, record) => (
        <Tooltip content={record.cookie_remark || value}>
          <span className="font-medium text-blue-600 dark:text-blue-400">{value}</span>
        </Tooltip>
      ),
    },
    {
      title: '用户消息',
      dataIndex: 'request_message',
      render: (value: string) => (
        <Tooltip content={value || '-'}>
          <span className="block max-w-[260px] truncate text-slate-600 dark:text-slate-300">{value || '-'}</span>
        </Tooltip>
      ),
    },
    {
      title: 'AI回复',
      dataIndex: 'reply_text',
      render: (value: string) => (
        <Tooltip content={value || '-'}>
          <span className="block max-w-[260px] truncate text-slate-500 dark:text-slate-400">{value || '-'}</span>
        </Tooltip>
      ),
    },
    {
      title: '模型',
      dataIndex: 'model_name',
      width: 150,
      render: (value, record) => <Tag color="arcoblue">{value || record.provider || 'unknown'}</Tag>,
    },
    {
      title: '输入Token',
      dataIndex: 'prompt_tokens',
      align: 'right',
      width: 120,
      render: (value) => formatNumber(value),
    },
    {
      title: '输出Token',
      dataIndex: 'completion_tokens',
      align: 'right',
      width: 120,
      render: (value) => formatNumber(value),
    },
    {
      title: '费用($)',
      align: 'right',
      width: 120,
      render: (_, record) => {
        const cost = (Number(record.prompt_tokens || 0) / 1_000_000) * inputRate
          + (Number(record.completion_tokens || 0) / 1_000_000) * outputRate
        return cost.toFixed(6)
      },
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 100,
      render: (value, record) => (
        <Tooltip content={record.error_message || (record.estimated ? 'Token为估算值' : '')}>
          <Tag color={value === 'success' ? (record.estimated ? 'orange' : 'green') : 'red'}>
            {value === 'success' ? (record.estimated ? '估算' : '成功') : '失败'}
          </Tag>
        </Tooltip>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="vben-card">
        <div className="accounts-page-intro">
          <h1>AI调用明细</h1>
          <p>查看每条买家消息消耗的输入/输出Token，并按自定义倍率估算美元成本</p>
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
              <Form.Item label="输入$/百万Token">
                <InputNumber min={0} precision={4} value={inputRate} onChange={(value) => setInputRate(Number(value || 0))} style={{ width: 160 }} />
              </Form.Item>
              <Form.Item label="输出$/百万Token">
                <InputNumber min={0} precision={4} value={outputRate} onChange={(value) => setOutputRate(Number(value || 0))} style={{ width: 160 }} />
              </Form.Item>
              <Space className="table-filter-actions">
                <Button onClick={loadData}>
                  刷新
                </Button>
              </Space>
            </Form>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-4 mb-4">
          <div className="rounded-xl bg-slate-50 p-4 dark:bg-white/5"><p className="text-slate-500">调用次数</p><strong className="text-xl">{formatNumber(logs.length)}</strong></div>
          <div className="rounded-xl bg-slate-50 p-4 dark:bg-white/5"><p className="text-slate-500">输入Token</p><strong className="text-xl">{formatNumber(totals.prompt)}</strong></div>
          <div className="rounded-xl bg-slate-50 p-4 dark:bg-white/5"><p className="text-slate-500">输出Token</p><strong className="text-xl">{formatNumber(totals.completion)}</strong></div>
          <div className="rounded-xl bg-slate-50 p-4 dark:bg-white/5"><p className="text-slate-500">估算费用</p><strong className="text-xl">${totals.cost.toFixed(6)}</strong></div>
        </div>

        <Table
          rowKey="id"
          columns={columns}
          data={logs}
          loading={loading}
          pagination={{ pageSize: 20 }}
          border={false}
          scroll={{ x: 1360 }}
          className="accounts-arco-table table-main"
          noDataElement={<Empty icon={<FileText className="w-12 h-12 text-gray-300" />} description="暂无AI调用记录" />}
        />
      </div>
    </div>
  )
}
