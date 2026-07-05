/**
 * 商品监控 - 监控日志页面
 *
 * 功能：
 * 1. 分页查看监控执行日志
 * 2. 支持按监控任务筛选
 */
import { useEffect, useState } from 'react'
import { CheckSquare, ChevronLeft, ChevronRight, Copy, Loader2, RefreshCw, RotateCcw, ScrollText, Search, Square, Trash2 } from 'lucide-react'
import {
  getListingMonitorLogs,
  getListingMonitorTaskOptions,
  copyListingMonitorLogCookies,
  clearListingMonitorLogs,
  MONITOR_TYPE_LABELS,
  MONITOR_TYPE_OPTIONS,
  type ListingMonitorLog,
  type ListingMonitorTaskOption,
  type MonitorType,
} from '@/api/listingMonitor'
import { PageLoading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { copyToClipboard } from '@/utils/clipboard'

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
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [copying, setCopying] = useState(false)
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const [clearing, setClearing] = useState(false)

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

  const loadLogs = async (
    nextPage = page,
    nextPageSize = pageSize,
    // 可选筛选覆盖：重置时传入清空后的值，避免读到尚未提交的旧 state
    filters?: { taskId: number | ''; statusFilter: string; typeFilter: MonitorType | '' },
  ) => {
    try {
      setTableLoading(true)
      const activeTaskId = filters ? filters.taskId : taskId
      const activeStatus = filters ? filters.statusFilter : statusFilter
      const activeType = filters ? filters.typeFilter : typeFilter
      const result = await getListingMonitorLogs(nextPage, nextPageSize, {
        monitorTaskId: activeTaskId === '' ? undefined : activeTaskId,
        status: activeStatus || undefined,
        monitorType: activeType === '' ? undefined : activeType,
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
      const currentIdSet = new Set((result.data.list || []).map((item) => item.id))
      setSelectedIds((prev) => new Set(Array.from(prev).filter((id) => currentIdSet.has(id))))
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

  // 仅翻页 / 改每页大小时自动加载；筛选下拉改动不再即时触发，统一由「查询」按钮触发
  useEffect(() => {
    void loadLogs(page, pageSize)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize])

  // 点击「查询」：回到第一页并用当前筛选条件加载（第一页直接加载，否则借分页副作用触发）
  const handleSearch = () => {
    if (page === 1) {
      void loadLogs(1, pageSize)
    } else {
      setPage(1)
    }
  }

  // 点击「重置」：清空全部筛选条件并回到第一页重新加载（用清空后的值直接加载，规避 state 异步更新）
  const handleReset = () => {
    setTaskId('')
    setTypeFilter('')
    setStatusFilter('')
    if (page === 1) {
      // 已在第一页：state 更新是异步的，直接用清空后的值加载
      void loadLogs(1, pageSize, { taskId: '', statusFilter: '', typeFilter: '' })
    } else {
      // 非第一页：回到第一页，state 提交后由分页副作用用清空后的筛选重新加载
      setPage(1)
    }
  }

  const startIndex = total === 0 ? 0 : (page - 1) * pageSize + 1
  const endIndex = Math.min(page * pageSize, total)
  const isAllSelected = logs.length > 0 && logs.every((item) => selectedIds.has(item.id))

  const handleSelectAll = () => {
    const currentPageIds = logs.map((item) => item.id)
    if (currentPageIds.length === 0) {
      setSelectedIds(new Set())
      return
    }
    const allSelected = currentPageIds.every((id) => selectedIds.has(id))
    setSelectedIds(allSelected ? new Set() : new Set(currentPageIds))
  }

  const handleSelect = (logId: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(logId)) {
        next.delete(logId)
      } else {
        next.add(logId)
      }
      return next
    })
  }

  const handleCopyCookies = async () => {
    const ids = Array.from(selectedIds)
    if (ids.length === 0) {
      addToast({ type: 'warning', message: '请先勾选要复制的监控日志' })
      return
    }
    setCopying(true)
    try {
      const result = await copyListingMonitorLogCookies(ids)
      if (!result.success || !result.data) {
        addToast({ type: 'error', message: result.message || '复制账号Cookies失败' })
        return
      }
      const list = result.data.list || []
      if (list.length === 0) {
        addToast({ type: 'warning', message: '选中的日志没有可复制的账号信息' })
        return
      }
      const json = JSON.stringify(list, null, 2)
      const ok = await copyToClipboard(json)
      if (!ok) {
        addToast({ type: 'error', message: '复制失败，请手动复制或检查浏览器权限' })
        return
      }
      addToast({ type: 'success', message: `已复制 ${list.length} 个账号的Cookies到剪贴板` })
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '复制账号Cookies失败') })
    } finally {
      setCopying(false)
    }
  }

  const handleClearLogs = async () => {
    setClearing(true)
    try {
      const result = await clearListingMonitorLogs()
      if (result.success) {
        addToast({ type: 'success', message: result.message || '清空成功' })
        setShowClearConfirm(false)
        // 清空后回到第一页：已在第一页则直接刷新，否则由分页副作用触发重新加载
        if (page === 1) {
          loadLogs(1, pageSize)
        } else {
          setPage(1)
        }
      } else {
        addToast({ type: 'error', message: result.message || '清空监控日志失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '清空监控日志失败') })
    } finally {
      setClearing(false)
    }
  }

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
        <div className="flex gap-3 flex-wrap">
          {selectedIds.size > 0 && (
            <button className="btn-ios-secondary" onClick={() => void handleCopyCookies()} disabled={copying || tableLoading}>
              {copying ? <Loader2 className="w-4 h-4 animate-spin" /> : <Copy className="w-4 h-4" />}
              复制账号Cookies ({selectedIds.size})
            </button>
          )}
          <button className="btn-ios-secondary" onClick={() => loadLogs(page, pageSize)} disabled={tableLoading}>
            {tableLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            刷新
          </button>
          <button
            className="btn-ios-danger"
            onClick={() => setShowClearConfirm(true)}
            disabled={tableLoading || clearing}
            title="清空10天前的日志"
          >
            <Trash2 className="w-4 h-4" />
            清空日志
          </button>
        </div>
      </div>

      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-end gap-3">
            <div className="input-group">
              <label className="input-label">监控任务</label>
              <select
                className="input-ios"
                value={taskId}
                onChange={(e) => setTaskId(e.target.value === '' ? '' : Number(e.target.value))}
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
                onChange={(e) => setTypeFilter(e.target.value === '' ? '' : (e.target.value as MonitorType))}
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
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <option value="">全部状态</option>
                <option value="success">成功</option>
                <option value="partial">部分成功</option>
                <option value="failed">失败</option>
              </select>
            </div>
            <div className="ml-auto flex items-end gap-2">
              <button className="btn-ios-primary" onClick={handleSearch} disabled={tableLoading}>
                <Search className="w-4 h-4" />查询
              </button>
              {(taskId !== '' || typeFilter !== '' || statusFilter !== '') && (
                <button className="btn-ios-secondary text-red-500" onClick={handleReset} disabled={tableLoading}>
                  <RotateCcw className="w-4 h-4" />重置
                </button>
              )}
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
                <th className="w-10 whitespace-nowrap">
                  <button onClick={handleSelectAll} className="p-1 hover:bg-gray-100 rounded" title={isAllSelected ? '取消全选' : '全选'}>
                    {isAllSelected ? (
                      <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                    ) : (
                      <Square className="w-4 h-4 text-gray-400" />
                    )}
                  </button>
                </th>
                <th>执行时间</th>
                <th>监控类型</th>
                <th>触发方式</th>
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
                  <td colSpan={12} className="text-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : logs.length === 0 ? (
                <tr>
                  <td colSpan={12} className="text-center py-12 text-slate-400">
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
                      <td className="w-10 whitespace-nowrap">
                        <button onClick={() => handleSelect(item.id)} className="p-1 hover:bg-gray-100 rounded" title={selectedIds.has(item.id) ? '取消勾选' : '勾选'}>
                          {selectedIds.has(item.id) ? (
                            <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                          ) : (
                            <Square className="w-4 h-4 text-gray-400" />
                          )}
                        </button>
                      </td>
                      <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">{item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '-'}</td>
                      <td className="whitespace-nowrap">{item.monitor_type ? (MONITOR_TYPE_LABELS[item.monitor_type] || item.monitor_type) : '-'}</td>
                      <td className="whitespace-nowrap">
                        {item.trigger_type === 'manual' ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">手动</span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400">自动</span>
                        )}
                      </td>
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

      {showClearConfirm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl max-w-md w-full p-6">
            <h3 className="text-lg font-semibold mb-4">确认清空日志</h3>
            <p className="text-slate-600 dark:text-slate-400 mb-6">
              此操作将清空10天前的监控日志数据，最近10天的日志将被保留。确定要继续吗？
            </p>
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

export default MonitorLogs
