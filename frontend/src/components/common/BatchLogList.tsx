/**
 * 批次日志列表通用组件
 *
 * 功能：
 * 1. 统一批次日志列表页的日期筛选、分页、刷新和详情跳转交互
 * 2. 统一清空日志确认弹窗，弹窗只能通过按钮关闭
 * 3. 支持不同日志类型通过列配置展示差异字段
 */
import { useEffect, useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Calendar, CheckCircle, ChevronLeft, ChevronRight, Clock, RefreshCw, Trash2, XCircle, type LucideIcon } from 'lucide-react'
import { PageLoading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'
import { formatDateTime } from '@/utils/date'

export interface BatchListQuery {
  start_date?: string
  end_date?: string
  page?: number
  page_size?: number
}

export interface BatchListResponse<T> {
  success: boolean
  message?: string
  data: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface BatchLogBase {
  batch_id: string
  executed_at: string
}

export interface BatchLogColumn<T> {
  title: string
  render: (batch: T) => ReactNode
}

interface PaginationState {
  page: number
  pageSize: number
  total: number
  totalPages: number
}

export interface BatchLogListProps<T extends BatchLogBase> {
  title: string
  description: string
  fetchBatches: (params: BatchListQuery) => Promise<BatchListResponse<T>>
  columns: BatchLogColumn<T>[]
  detailPath: (batchId: string) => string
  clearLogs?: () => Promise<{ success: boolean; message?: string }>
  clearConfirmMessage?: string
  loadErrorMessage?: string
  emptyText?: string
  showPageSizeSelector?: boolean
}

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

function getTodayString() {
  return new Date().toISOString().split('T')[0]
}

export function renderPlainCount(value: number) {
  return <span className="font-medium">{value}</span>
}

export function renderIconCount(value: number, Icon: LucideIcon, colorClass: string) {
  return (
    <span className={`inline-flex items-center gap-1 ${colorClass}`}>
      <Icon className="w-3.5 h-3.5" />
      {value}
    </span>
  )
}

export function renderSuccessCount(value: number) {
  return renderIconCount(value, CheckCircle, 'text-green-600 dark:text-green-400')
}

export function renderFailedCount(value: number) {
  return renderIconCount(value, XCircle, 'text-red-600 dark:text-red-400')
}

export function renderRateCell(successCount: number, failedCount: number, totalCount: number) {
  if (totalCount <= 0) {
    return <span className="text-slate-400">-</span>
  }

  const colorClass = successCount === totalCount
    ? 'text-green-600 dark:text-green-400'
    : failedCount === totalCount
      ? 'text-red-600 dark:text-red-400'
      : 'text-amber-600 dark:text-amber-400'

  return (
    <span className={`font-medium ${colorClass}`}>
      {((successCount / totalCount) * 100).toFixed(1)}%
    </span>
  )
}

export function BatchLogList<T extends BatchLogBase>({
  title,
  description,
  fetchBatches,
  columns,
  detailPath,
  clearLogs,
  clearConfirmMessage = '此操作将清空10天前的日志数据，最近10天的日志将被保留。确定要继续吗？',
  loadErrorMessage = '加载数据失败',
  emptyText = '暂无执行记录',
  showPageSizeSelector = true,
}: BatchLogListProps<T>) {
  const navigate = useNavigate()
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [batches, setBatches] = useState<T[]>([])
  const [pagination, setPagination] = useState<PaginationState>({
    page: 1,
    pageSize: 20,
    total: 0,
    totalPages: 0,
  })
  const [startDate, setStartDate] = useState(getTodayString())
  const [endDate, setEndDate] = useState(getTodayString())
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const [clearing, setClearing] = useState(false)

  const loadBatches = async (page: number = pagination.page, pageSize: number = pagination.pageSize) => {
    try {
      setLoading(true)
      const result = await fetchBatches({
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        page,
        page_size: pageSize,
      })

      if (result.success) {
        setBatches(result.data)
        setPagination({
          page: result.page,
          pageSize: result.page_size,
          total: result.total,
          totalPages: result.total_pages,
        })
      } else {
        addToast({ type: 'error', message: result.message || loadErrorMessage })
      }
    } catch (error) {
      addToast({ type: 'error', message: error instanceof Error ? error.message : loadErrorMessage })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadBatches(1, pagination.pageSize)
  }, [])

  const handleClearLogs = async () => {
    if (!clearLogs) return

    try {
      setClearing(true)
      const result = await clearLogs()
      if (result.success) {
        addToast({ type: 'success', message: result.message || '清空成功' })
        setShowClearConfirm(false)
        loadBatches(1, pagination.pageSize)
      } else {
        addToast({ type: 'error', message: result.message || '清空失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: error instanceof Error ? error.message : '清空失败' })
    } finally {
      setClearing(false)
    }
  }

  if (loading && batches.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      <div className="page-header flex-between">
        <div>
          <h1 className="page-title">{title}</h1>
          <p className="page-description">{description}</p>
        </div>
        <div className="flex gap-2">
          {clearLogs && (
            <button
              onClick={() => setShowClearConfirm(true)}
              className="btn-ios-danger"
              title="清空10天前的日志"
            >
              <Trash2 className="w-4 h-4" />
              清空日志
            </button>
          )}
          <button onClick={() => loadBatches()} className="btn-ios-secondary">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-end gap-4">
            <div className="input-group">
              <label className="input-label">开始日期</label>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="input-ios" />
            </div>
            <div className="input-group">
              <label className="input-label">结束日期</label>
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="input-ios" />
            </div>
            <button onClick={() => loadBatches(1, pagination.pageSize)} className="btn-ios-primary">
              <Calendar className="w-4 h-4" />
              查询
            </button>
          </div>
        </div>
      </div>

      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 320px)', minHeight: '400px' }}>
        <div className="vben-card-header flex-shrink-0 flex-between">
          <h2 className="vben-card-title">执行记录</h2>
          <span className="badge-primary">{pagination.total} 条记录</span>
        </div>
        <div className="flex-1 overflow-auto relative">
          {loading ? (
            <div className="flex justify-center py-8">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : (
            <table className="table-ios">
              <thead className="sticky top-0 bg-white dark:bg-slate-800 z-[1]">
                <tr>
                  <th>执行时间</th>
                  {columns.map((column) => (
                    <th key={column.title}>{column.title}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {batches.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length + 1}>
                      <div className="empty-state py-8">
                        <p className="text-slate-500 dark:text-slate-400">{emptyText}</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  batches.map((batch) => (
                    <tr
                      key={batch.batch_id}
                      onClick={() => navigate(detailPath(batch.batch_id))}
                      className="cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/20"
                    >
                      <td>
                        <span className="inline-flex items-center gap-1.5">
                          <Clock className="w-3.5 h-3.5 text-slate-400" />
                          {formatDateTime(batch.executed_at)}
                        </span>
                      </td>
                      {columns.map((column) => (
                        <td key={column.title}>{column.render(batch)}</td>
                      ))}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}
        </div>

        {pagination.total > 0 && (
          <div className="flex-shrink-0 flex flex-col lg:flex-row items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700 gap-3">
            <div className="flex items-center gap-3 text-sm text-gray-500">
              <span>共 {pagination.total} 条记录</span>
              {showPageSizeSelector && (
                <div className="flex items-center gap-2">
                  <span>每页</span>
                  <select
                    value={pagination.pageSize}
                    onChange={(e) => loadBatches(1, Number(e.target.value))}
                    className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800"
                  >
                    {PAGE_SIZE_OPTIONS.map((size) => (
                      <option key={size} value={size}>{size}</option>
                    ))}
                  </select>
                  <span>条</span>
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">
                第 {pagination.page} / {pagination.totalPages} 页
              </span>
              <button
                onClick={() => loadBatches(pagination.page - 1, pagination.pageSize)}
                disabled={pagination.page <= 1 || loading}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <button
                onClick={() => loadBatches(pagination.page + 1, pagination.pageSize)}
                disabled={pagination.page >= pagination.totalPages || loading}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {showClearConfirm && clearLogs && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl max-w-md w-full p-6">
            <h3 className="text-lg font-semibold mb-4">确认清空日志</h3>
            <p className="text-slate-600 dark:text-slate-400 mb-6">{clearConfirmMessage}</p>
            <div className="flex justify-end gap-3">
              <button onClick={() => setShowClearConfirm(false)} disabled={clearing} className="btn-ios-secondary">
                取消
              </button>
              <button onClick={handleClearLogs} disabled={clearing} className="btn-ios-danger">
                {clearing ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    清空中...
                  </>
                ) : (
                  <>
                    <Trash2 className="w-4 h-4" />
                    确认清空
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
