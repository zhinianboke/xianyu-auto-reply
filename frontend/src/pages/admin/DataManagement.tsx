import { useState, useEffect } from 'react'
import { Database, RefreshCw, Trash2, Table } from 'lucide-react'
import { getTableData, clearTableData } from '@/api/admin'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading, ButtonLoading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'

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
    if (!confirm(`确定要清空 ${tableOptions.find(t => t.value === selectedTable)?.label} 吗？此操作不可恢复！`)) return
    if (!confirm('再次确认：是否真的要清空该表的所有数据？')) return

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
  }

  if (!_hasHydrated) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* 数据表选择 */}
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">
            <Table className="w-4 h-4" />
            数据表选择
          </h2>
        </div>
        <div className="vben-card-body">
          <div className="grid grid-cols-1 sm:grid-cols-12 gap-4 items-end">
            <div className="sm:col-span-6">
              <label className="input-label mb-1">选择数据表</label>
              <Select
                value={selectedTable}
                onChange={setSelectedTable}
                options={tableOptions}
                placeholder="选择数据表"
              />
            </div>
            <div className="sm:col-span-2 text-center py-2 px-4 bg-slate-50 dark:bg-slate-800/50 rounded-lg">
              <p className="text-xs text-slate-500 dark:text-slate-400">数据统计</p>
              <p className="text-xl font-bold text-slate-900 dark:text-slate-100">{count}</p>
              <p className="text-xs text-slate-400">条记录</p>
            </div>
            <div className="sm:col-span-4 flex justify-end">
              <button
                onClick={loadTableData}
                disabled={loading}
                className="btn-ios-primary w-full sm:w-auto"
              >
                {loading ? <ButtonLoading /> : <RefreshCw className="w-4 h-4" />}
                刷新数据
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* 数据表展示 */}
      <div className="vben-card">
        <div className="vben-card-header flex items-center justify-between">
          <h2 className="vben-card-title">
            <Database className="w-4 h-4" />
            {tableOptions.find(t => t.value === selectedTable)?.label || selectedTable}
          </h2>
          <button
            onClick={handleClearTable}
            disabled={clearing || count === 0}
            className="btn-ios-danger text-sm"
          >
            {clearing ? <ButtonLoading /> : <Trash2 className="w-4 h-4" />}
            清空
          </button>
        </div>
        <div className="vben-card-body p-0">
          {loading ? (
            <div className="p-8 text-center">
              <ButtonLoading />
              <p className="text-slate-500 mt-2">加载中...</p>
            </div>
          ) : tableData.length === 0 ? (
            <div className="p-8 text-center">
              <Database className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-3" />
              <p className="text-slate-500 dark:text-slate-400">该表暂无数据</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm table-fixed">
                <thead className="bg-slate-50 dark:bg-slate-800/50 border-b border-slate-200 dark:border-slate-700">
                  <tr>
                    {columns.map((col, index) => (
                      <th
                        key={col}
                        className={`px-4 py-3 text-left font-medium text-slate-700 dark:text-slate-300 ${
                          index === 0 ? 'w-32' : 'min-w-[120px]'
                        }`}
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                  {tableData.slice(0, 100).map((row, idx) => (
                    <tr key={idx} className="hover:bg-slate-50 dark:hover:bg-slate-800/30">
                      {columns.map((col) => (
                        <td
                          key={col}
                          className="px-4 py-3 text-slate-600 dark:text-slate-400 truncate"
                          title={String(row[col] ?? '')}
                        >
                          {String(row[col] ?? '-')}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
              {tableData.length > 100 && (
                <div className="p-3 text-center text-sm text-slate-500 bg-slate-50 dark:bg-slate-800/30 border-t border-slate-200 dark:border-slate-700">
                  仅显示前 100 条记录，共 {tableData.length} 条
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
