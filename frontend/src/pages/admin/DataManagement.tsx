import { useState, useEffect } from 'react'
import { Database, RefreshCw, Trash2 } from 'lucide-react'
import { Button, Empty, Form, Modal, Select as ArcoSelect, Space, Table } from '@arco-design/web-react'
import type { TableColumnProps } from '@arco-design/web-react'
import { getTableData, clearTableData } from '@/api/admin'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading, ButtonLoading } from '@/components/common/Loading'

// 可选择的数据表
const tableOptions = [
  { value: 'default_replies', label: '默认回复表' },
  { value: 'keywords', label: '关键词表' },
  { value: 'cookies', label: '账号表' },
  { value: 'cards', label: '卡券表' },
  { value: 'orders', label: '订单表' },
  { value: 'item_info', label: '商品信息表' },
  { value: 'notification_channels', label: '通知渠道表' },
  { value: 'delivery_rules', label: '发货规则表' },
  { value: 'risk_control_logs', label: '风控日志表' },
]

export function DataManagement() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(false)
  const [selectedTable, setSelectedTable] = useState('default_replies')
  const [tableData, setTableData] = useState<Record<string, unknown>[]>([])
  const [columns, setColumns] = useState<string[]>([])
  const [count, setCount] = useState(0)
  const [clearing, setClearing] = useState(false)

  const loadTableData = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getTableData(selectedTable)
      if (result.success) {
        setTableData(result.data || [])
        setColumns(result.columns || [])
        setCount(result.count || 0)
      } else {
        addToast({ type: 'error', message: '加载数据失败' })
      }
    } catch {
      addToast({ type: 'error', message: '加载数据失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (_hasHydrated && isAuthenticated && token) {
      loadTableData()
    }
  }, [_hasHydrated, isAuthenticated, token, selectedTable])

  const handleClearTable = async () => {
    Modal.confirm({
      title: '清空数据表',
      content: `确定要清空 ${tableOptions.find(t => t.value === selectedTable)?.label} 吗？此操作不可恢复。`,
      okButtonProps: { status: 'danger' },
      onOk: async () => {
        try {
          setClearing(true)
          const result = await clearTableData(selectedTable)
          if (result.success) {
            addToast({ type: 'success', message: '清空成功' })
            loadTableData()
          } else {
            addToast({ type: 'error', message: result.message || '清空失败' })
          }
        } catch {
          addToast({ type: 'error', message: '清空失败' })
        } finally {
          setClearing(false)
        }
      },
    })
  }

  if (!_hasHydrated) {
    return <PageLoading />
  }

  const arcoColumns: TableColumnProps<Record<string, unknown>>[] = columns.map((col, index) => ({
    title: col,
    dataIndex: col,
    width: index === 0 ? 180 : 260,
    render: (value: unknown) => (
      <span
        className={`block truncate text-slate-600 dark:text-slate-400 ${index === 0 ? 'max-w-[180px]' : 'max-w-[260px]'}`}
        title={String(value ?? '')}
      >
        {String(value ?? '-')}
      </span>
    ),
  }))
  const displayTableData = tableData.slice(0, 100).map((row, index) => ({
    ...row,
    key: `${selectedTable}-${index}`,
  }))

  return (
    <div className="space-y-4">
      <div className="vben-card">
        <div className="accounts-page-intro">
          <h1>数据库管理</h1>
          <p>查看并维护系统核心数据表。</p>
        </div>
        <div className="table-toolbar">
          <div className="table-filter-row table-filter-row--lined">
            <Form layout="inline" className="table-filter-form">
              <Form.Item label="选择数据表">
                <ArcoSelect
                  value={selectedTable}
                  onChange={(value) => setSelectedTable(String(value))}
                  style={{ width: 220 }}
                  options={tableOptions}
                  placeholder="选择数据表"
                />
              </Form.Item>
            </Form>
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 rounded-lg bg-slate-50 px-4 py-2 dark:bg-slate-800/50">
                <span className="text-lg font-bold text-slate-900 dark:text-slate-100">{count}</span>
                <span className="text-xs text-slate-400">条记录</span>
              </div>
              <Space className="batch-actions">
                <Button
                  type="primary"
                  onClick={loadTableData}
                  loading={loading}
                  className="accounts-header-btn"
                >
                  <RefreshCw />
                  刷新数据
                </Button>
                <Button
                  status="danger"
                  onClick={handleClearTable}
                  disabled={clearing || count === 0}
                  className="accounts-header-btn"
                >
                  {clearing ? <ButtonLoading /> : <Trash2 />}
                  清空数据
                </Button>
              </Space>
            </div>
          </div>
        </div>
        <div>
          {loading ? (
            <div className="p-8 text-center">
              <ButtonLoading />
              <p className="text-slate-500 mt-2">加载中...</p>
            </div>
          ) : tableData.length === 0 ? (
            <Empty
              className="py-10"
              icon={<Database className="w-12 h-12 text-slate-300 dark:text-slate-600" />}
              description="该表暂无数据"
            />
          ) : (
            <Table
              className="accounts-arco-table"
              columns={arcoColumns}
              data={displayTableData}
              rowKey="key"
              borderCell={false}
              pagination={false}
              scroll={{ x: 'max-content' }}
            />
          )}
          {!loading && tableData.length > 100 && (
            <div className="border-t border-slate-200 bg-slate-50 px-4 py-3 text-center text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800/30">
              仅显示前 100 条记录，共 {tableData.length} 条
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
