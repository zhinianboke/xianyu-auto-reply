/**
 * 商品监控 - 监控日志页面
 *
 * 功能：
 * 1. 分页查看监控执行日志
 * 2. 支持按监控任务筛选
 */
import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Loader2, RefreshCw, ScrollText } from 'lucide-react'
import {
  getListingMonitorLogs,
  getListingMonitorTaskOptions,
  MONITOR_TYPE_LABELS,
  MONITOR_TYPE_OPTIONS,
  type ListingMonitorLog,
  type ListingMonitorTaskOption,
  type MonitorType,
} from '@/api/listingMonitor'
import { PageLoading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

const STATUS_LABELS: Record<string, { text: string; cls: string }> = {
  success: { text: '成功', cls: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' },
  partial: { text: '部分成功', cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' },
  failed: { text: '失败', cls: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400' },
}

export function MonitorLogs() {
  const { addToast } = useUIStore()

  const [loading, setLoading] = useState(true)
  const [tableLoading, setTableLoading] = useState(false)
  const [logs, setLogs] = useState<ListingMonitorLog[]>([])
  const [taskOptions, setTaskOptions] = useState<ListingMonitorTaskOption[]>([])
  const [taskId, setTaskId] = useState<number | ''>('')
  const [statusFilter, setStatusFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState<MonitorType | ''>('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)

  const loadTaskOptions = async () => {
    try {
      const result = await getListingMonitorTaskOptions()
      if (result.success && result.data) {
        setTaskOptions(result.data.list || [])
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载监控任务列表失败') })
    }
  }

  const loadLogs = async (nextPage = page, nextPageSize = pageSize) => {
    try {
      setTableLoading(true)
      const result = await getListingMonitorLogs(nextPage, nextPageSize, {
        monitorTaskId: taskId === '' ? undefined : taskId,
        status: statusFilter || undefined,
        monitorType: typeFilter === '' ? undefined : typeFilter,
      })
      if (!result.success || !result.data) {
        setLogs([])
        setTotal(0)
        setTotalPages(0)
        addToast({ type: 'error', message: result.message || '加载监控日志失败' })
        return
      }
      setLogs(result.data.list || [])
      setTotal(result.data.total || 0)
      setTotalPages(result.data.total_pages || 0)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载监控日志失败') })
    } finally {
      setLoading(false)
      setTableLoading(false)
    }
  }

  useEffect(() => {
    void loadTaskOptions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void loadLogs(page, pageSize)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, taskId, statusFilter, typeFilter])

  const startIndex = total === 0 ? 0 : (page - 1) * pageSize + 1
  const endIndex = Math.min(page * pageSize, total)

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">监控日志</h1>
          <p className="page-description">查看每次商品监控任务执行的获取、新增、更新数量与使用的账号。</p>
        </div>
        <button className="btn-ios-secondary" onClick={() => loadLogs(page, pageSize)} disabled={tableLoading}>
          {tableLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          刷新
        </button>
      </div>

      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-end gap-3">
            <div className="input-group">
              <label className="input-label">监控任务</label>
              <select
                className="input-ios"
                value={taskId}
                onChange={(e) => {
                  setTaskId(e.target.value === '' ? '' : Number(e.target.value))
                  setPage(1)
                }}
              >
                <option value="">全部任务</option>
                {taskOptions.map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {`#${opt.id} ${opt.keyword}（${MONITOR_TYPE_LABELS[opt.monitor_type] || opt.monitor_type}）`}
                  </option>
                ))}
              </select>
            </div>
            <div className="input-group">
              <label className="input-label">监控类型</label>
              <select
                className="input-ios"
                value={typeFilter}
                onChange={(e) => {
                  setTypeFilter(e.target.value === '' ? '' : (e.target.value as MonitorType))
                  setPage(1)
                }}
              >
                <option value="">全部类型</option>
                {MONITOR_TYPE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div className="input-group">
              <label className="input-label">执行状态</label>
              <select
                className="input-ios"
                value={statusFilter}
                onChange={(e) => {
                  setStatusFilter(e.target.value)
                  setPage(1)
                }}
              >
                <option value="">全部状态</option>
                <option value="success">成功</option>
                <option value="partial">部分成功</option>
                <option value="failed">失败</option>
              </select>
            </div>
          </div>
        </div>
      </div>

      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 320px)', minHeight: '420px' }}>
        <div className="vben-card-header flex items-center justify-between">
          <h2 className="vben-card-title">
            <ScrollText className="w-4 h-4" />
            日志列表
          </h2>
          <span className="badge-primary">共 {total} 条</span>
        </div>

        <div className="flex-1 overflow-auto">
          <table className="table-ios min-w-[900px]">
            <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
              <tr>
                <th>执行时间</th>
                <th>监控类型</th>
                <th>关键字</th>
                <th>使用账号</th>
                <th>页数</th>
                <th>获取</th>
                <th>新增</th>
                <th>更新</th>
                <th>状态</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              {tableLoading ? (
                <tr>
                  <td colSpan={10} className="text-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={10} className="text-center py-12 text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <ScrollText className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>暂无监控日志</p>
                    </div>
                  </td>
                </tr>
              ) : (
                logs.map((item) => {
                  const statusInfo = STATUS_LABELS[item.status] || { text: item.status, cls: 'bg-slate-100 text-slate-500' }
                  const accounts = item.used_account_ids && item.used_account_ids.length > 0 ? item.used_account_ids.join('，') : (item.account_id || '-')
                  return (
                    <tr key={item.id}>
                      <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">{item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '-'}</td>
                      <td className="whitespace-nowrap">{item.monitor_type ? (MONITOR_TYPE_LABELS[item.monitor_type] || item.monitor_type) : '-'}</td>
                      <td className="max-w-[160px]"><span className="truncate block" title={item.keyword || ''}>{item.keyword || '-'}</span></td>
                      <td className="max-w-[200px]"><span className="truncate block" title={accounts}>{accounts}</span></td>
                      <td>{item.pages}</td>
                      <td>{item.fetched_count}</td>
                      <td className="text-green-600 dark:text-green-400">{item.inserted_count}</td>
                      <td className="text-blue-600 dark:text-blue-400">{item.updated_count}</td>
                      <td className="whitespace-nowrap">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs ${statusInfo.cls}`}>{statusInfo.text}</span>
                      </td>
                      <td className="max-w-[260px]"><span className="truncate block" title={item.message || ''}>{item.message || '-'}</span></td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        {total > 0 && (
          <div className="flex-shrink-0 vben-card-footer flex flex-col sm:flex-row items-center justify-between gap-4 px-4 py-3 border-t border-slate-200 dark:border-slate-700">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value))
                  setPage(1)
                }}
                className="px-2 py-1 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>条</span>
              <span className="ml-2">显示 {startIndex}-{endIndex} 条，共 {total} 条</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                disabled={page === 1 || tableLoading}
                className="p-2 rounded border border-slate-300 dark:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-700"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-3 py-1 text-sm text-slate-600 dark:text-slate-400">第 {page} / {totalPages || 1} 页</span>
              <button
                onClick={() => setPage((prev) => Math.min(totalPages || 1, prev + 1))}
                disabled={page >= (totalPages || 1) || tableLoading}
                className="p-2 rounded border border-slate-300 dark:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-700"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

export default MonitorLogs
