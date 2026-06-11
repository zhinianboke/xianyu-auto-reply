/**
 * 风控日志页面
 * 
 * 功能：
 * 1. 显示风控日志列表
 * 2. 支持按账号筛选
 * 3. 支持按时间范围筛选
 * 4. 支持按处理状态筛选
 * 5. 支持分页
 * 6. 支持清空日志
 */
import { useState, useEffect } from 'react'
import { ShieldAlert, RefreshCw, Trash2, ChevronLeft, ChevronRight, Loader2, Calendar } from 'lucide-react'
import { getRiskLogs, clearRiskLogs, type RiskLog } from '@/api/admin'
import { getAccountDetails } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { getApiErrorMessage } from '@/utils/request'
import type { Account } from '@/types'

export function RiskLogs() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated, user } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState<RiskLog[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')

  // 时间筛选 - 默认当天
  const today = new Date().toISOString().split('T')[0]
  const [startDate, setStartDate] = useState(today)
  const [endDate, setEndDate] = useState(today)

  // 状态筛选
  const [selectedStatus, setSelectedStatus] = useState('')

  // 分页状态
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)

  // 清空确认弹窗状态
  const [clearConfirm, setClearConfirm] = useState(false)
  const [clearing, setClearing] = useState(false)

  const loadLogs = async (nextPage: number = currentPage, nextPageSize: number = pageSize) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getRiskLogs({ 
        page: nextPage,
        pageSize: nextPageSize,
        cookie_id: selectedAccount || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        processing_status: selectedStatus || undefined,
      })
      if (result.success) {
        setLogs(result.data || [])
        setCurrentPage(nextPage)
        setPageSize(nextPageSize)
        setTotal(result.total || 0)
      } else {
        setLogs([])
        setCurrentPage(nextPage)
        setPageSize(nextPageSize)
        setTotal(0)
        addToast({ type: 'error', message: result.message || '加载风控日志失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载风控日志失败') })
    } finally {
      setLoading(false)
    }
  }

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const data = await getAccountDetails()
      setAccounts(data)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载账号列表失败') })
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadAccounts()
    loadLogs(1, pageSize)
  }, [_hasHydrated, isAuthenticated, token])

  // 查询按钮点击
  const handleSearch = () => {
    loadLogs(1, pageSize)
  }

  const handlePageChange = (nextPage: number) => {
    if (nextPage < 1 || nextPage > totalPages) {
      return
    }
    loadLogs(nextPage, pageSize)
  }

  const handlePageSizeChange = (nextPageSize: number) => {
    loadLogs(1, nextPageSize)
  }

  const handleClear = async () => {
    setClearing(true)
    try {
      await clearRiskLogs()
      addToast({ type: 'success', message: '日志已清空' })
      setClearConfirm(false)
      loadLogs(1, pageSize)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '清空失败') })
    } finally {
      setClearing(false)
    }
  }

  // 分页计算
  const totalPages = Math.ceil(total / pageSize)
  const startIndex = (currentPage - 1) * pageSize + 1
  const endIndex = Math.min(currentPage * pageSize, total)

  if (loading && logs.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">风控日志</h1>
          <p className="page-description">查看账号风控相关日志</p>
        </div>
        <div className="flex gap-3">
          {user?.is_admin ? (
            <button onClick={() => setClearConfirm(true)} className="btn-ios-danger ">
              <Trash2 className="w-4 h-4" />
              清空日志
            </button>
          ) : null}
          <button onClick={() => loadLogs()} disabled={loading} className="btn-ios-secondary ">
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            刷新
          </button>
        </div>
      </div>

      {/* Filter */}
      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-end gap-4">
            <div className="input-group">
              <label className="input-label">开始日期</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="input-ios"
              />
            </div>
            <div className="input-group">
              <label className="input-label">结束日期</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="input-ios"
              />
            </div>
            <div className="input-group">
              <label className="input-label">处理状态</label>
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="input-ios"
              >
                <option value="">全部状态</option>
                <option value="success">成功</option>
                <option value="failed">失败</option>
                <option value="processing">处理中</option>
              </select>
            </div>
            <div className="input-group min-w-[200px]">
              <label className="input-label">筛选账号</label>
              <Select
                value={selectedAccount}
                onChange={setSelectedAccount}
                options={[
                  { value: '', label: '全部账号', key: 'all' },
                  ...accounts.map((account) => ({
                    value: account.id,
                    label: account.note ? `${account.id} (${account.note})` : account.id,
                    key: account.pk?.toString() || account.id,
                  })),
                ]}
                placeholder="全部账号"
              />
            </div>
            <button onClick={handleSearch} className="btn-ios-primary">
              <Calendar className="w-4 h-4" />
              查询
            </button>
          </div>
        </div>
      </div>

      {/* Logs List */}
      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 380px)', minHeight: '400px' }}>
        <div className="vben-card-header flex-shrink-0">
          <h2 className="vben-card-title">
            <ShieldAlert className="w-4 h-4 text-amber-500" />
            风控日志
          </h2>
          <span className="badge-primary">{total} 条记录</span>
        </div>
        <div className="flex-1 overflow-auto">
          <table className="table-ios">
            <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
              <tr>
                <th>账号ID</th>
                <th>事件描述</th>
                <th>处理结果</th>
                <th>处理状态</th>
                <th>验证引擎</th>
                <th>创建时间</th>
                <th>更新时间</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-slate-500 dark:text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <ShieldAlert className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>暂无风控日志</p>
                    </div>
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id}>
                    <td className="font-medium text-blue-600 dark:text-blue-400">
                      {(() => {
                        const account = accounts.find(acc => acc.id === log.cookie_id)
                        return account?.note ? `${log.cookie_id} (${account.note})` : log.cookie_id
                      })()}
                    </td>
                    <td className="max-w-[200px] text-slate-500 dark:text-slate-400">
                      <span 
                        className="block truncate cursor-help" 
                        title={log.message}
                      >
                        {log.message || '-'}
                      </span>
                    </td>
                    <td className="max-w-[200px] text-slate-500 dark:text-slate-400">
                      <span 
                        className="block truncate cursor-help" 
                        title={log.processing_result}
                      >
                        {log.processing_result || '-'}
                      </span>
                    </td>
                    <td>
                      <span className={`text-xs px-2 py-1 rounded ${
                        log.processing_status === 'success' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                        log.processing_status === 'failed' ? 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' :
                        log.processing_status === 'processing' ? 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400' :
                        'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300'
                      }`}>
                        {log.processing_status === 'success' ? '成功' :
                         log.processing_status === 'failed' ? '失败' :
                         log.processing_status === 'processing' ? '处理中' :
                         log.processing_status || '-'}
                      </span>
                    </td>
                    <td>
                      {log.captcha_engine === 'drissionpage' ? (
                        <span className="text-xs px-2 py-1 rounded bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
                          兜底引擎
                        </span>
                      ) : log.captcha_engine === 'playwright' ? (
                        <span className="text-xs px-2 py-1 rounded bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                          主引擎
                        </span>
                      ) : (
                        <span className="text-slate-400 dark:text-slate-500">-</span>
                      )}
                    </td>
                    <td className="text-slate-500 dark:text-slate-400 text-sm whitespace-nowrap">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="text-slate-500 dark:text-slate-400 text-sm whitespace-nowrap">
                      {log.updated_at ? new Date(log.updated_at).toLocaleString() : '-'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        
        {/* 分页组件 */}
        {total > 0 && (
          <div className="flex-shrink-0 vben-card-footer flex flex-col sm:flex-row items-center justify-between gap-4 px-4 py-3 border-t border-slate-200 dark:border-slate-700">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                className="px-2 py-1 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>条</span>
              <span className="ml-2">
                显示 {startIndex}-{endIndex} 条，共 {total} 条
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handlePageChange(currentPage - 1)}
                disabled={currentPage === 1}
                className="p-2 rounded border border-slate-300 dark:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-700"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-3 py-1 text-sm text-slate-600 dark:text-slate-400">
                第 {currentPage} / {totalPages || 1} 页
              </span>
              <button
                onClick={() => handlePageChange(currentPage + 1)}
                disabled={currentPage >= totalPages}
                className="p-2 rounded border border-slate-300 dark:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-700"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 清空确认弹窗 */}
      {user?.is_admin ? (
        <ConfirmModal
          isOpen={clearConfirm}
          title="清空确认"
          message="确定要清空所有风控日志吗？此操作不可恢复！"
          confirmText="清空"
          cancelText="取消"
          type="danger"
          loading={clearing}
          onConfirm={handleClear}
          onCancel={() => setClearConfirm(false)}
        />
      ) : null}
    </div>
  )
}
