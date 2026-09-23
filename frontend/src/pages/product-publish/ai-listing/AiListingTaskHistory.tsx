/**
 * AI 铺货历史任务
 *
 * 功能：
 * 1. 分页查询历史任务（按状态筛选，查询/重置按钮在筛选行最右）
 * 2. 查看单个任务的失败明细，便于排查生成失败原因
 */
import { useCallback, useEffect, useState } from 'react'
import { Eye, Loader2, Search, X } from 'lucide-react'
import {
  getAiListingTask,
  getAiListingTasks,
  type AiListingTask,
  type AiListingTaskDetail,
} from '@/api/aiListing'
import { useUIStore } from '@/store/uiStore'
import { formatDateTime } from '@/utils/date'
import { getApiErrorMessage } from '@/utils/apiError'

/** 状态筛选选项 */
const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'running', label: '生成中' },
  { value: 'success', label: '已完成' },
  { value: 'partial', label: '部分成功' },
  { value: 'failed', label: '失败' },
  { value: 'canceled', label: '已取消' },
]

/** 状态对应的中文与徽章样式 */
const STATUS_META: Record<string, { label: string; className: string }> = {
  pending: { label: '等待中', className: 'badge-info' },
  running: { label: '生成中', className: 'badge-info' },
  success: { label: '已完成', className: 'badge-success' },
  partial: { label: '部分成功', className: 'badge-warning' },
  failed: { label: '失败', className: 'badge-danger' },
  canceled: { label: '已取消', className: 'badge-gray' },
}

export function AiListingTaskHistory() {
  const { addToast } = useUIStore()

  const [tasks, setTasks] = useState<AiListingTask[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(10)
  const [totalPages, setTotalPages] = useState(0)
  const [loading, setLoading] = useState(false)

  // 筛选：改下拉不立即查询，点「查询」才生效
  const [statusInput, setStatusInput] = useState('')
  const [statusFilter, setStatusFilter] = useState('')

  const [detail, setDetail] = useState<AiListingTaskDetail | null>(null)
  const [detailLoadingId, setDetailLoadingId] = useState<string | null>(null)

  const load = useCallback(async (targetPage: number, size: number, status: string) => {
    setLoading(true)
    try {
      const res = await getAiListingTasks(targetPage, size, status || undefined)
      if (!res.success) {
        addToast({ type: 'error', message: res.message || '加载任务历史失败' })
        return
      }
      setTasks(res.data.list)
      setTotal(res.data.total)
      setTotalPages(res.data.total_pages)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载任务历史失败') })
    } finally {
      setLoading(false)
    }
  }, [addToast])

  useEffect(() => {
    void load(page, pageSize, statusFilter)
  }, [load, page, pageSize, statusFilter])

  const handleViewDetail = async (task: AiListingTask) => {
    if (detail?.task_id === task.task_id) {
      setDetail(null)
      return
    }
    setDetailLoadingId(task.task_id)
    try {
      const res = await getAiListingTask(task.task_id)
      if (!res.success || !res.data) {
        addToast({ type: 'error', message: res.message || '加载任务明细失败' })
        return
      }
      setDetail(res.data)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载任务明细失败') })
    } finally {
      setDetailLoadingId(null)
    }
  }

  const failedItems = (detail?.items || []).filter(item => item.status === 'failed')

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-4">
        <div className="input-group">
          <label className="input-label">任务状态</label>
          <select
            className="input-ios w-36"
            value={statusInput}
            onChange={e => setStatusInput(e.target.value)}
          >
            {STATUS_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2 ml-auto">
          <button
            className="btn-ios-primary btn-sm"
            onClick={() => { setPage(1); setStatusFilter(statusInput) }}
            disabled={loading}
          >
            <Search className="w-3.5 h-3.5" />查询
          </button>
          {statusFilter && (
            <button
              className="btn-ios-secondary btn-sm"
              onClick={() => { setStatusInput(''); setStatusFilter(''); setPage(1) }}
              disabled={loading}
            >
              <X className="w-3.5 h-3.5" />重置
            </button>
          )}
        </div>
      </div>

      <div className="table-scroll max-h-72 border border-slate-200 dark:border-slate-700 rounded-lg">
        <table className="table-ios">
          <thead>
            <tr>
              <th>生成主题</th>
              <th>使用配置</th>
              <th>结果</th>
              <th>状态</th>
              <th>创建时间</th>
              <th>明细</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={6} className="text-center py-8 text-slate-400">
                <Loader2 className="w-4 h-4 animate-spin inline mr-2" />加载中...
              </td></tr>
            ) : tasks.length === 0 ? (
              <tr><td colSpan={6} className="text-center py-8 text-slate-400">
                {statusFilter ? '没有符合条件的任务' : '暂无任务记录'}
              </td></tr>
            ) : tasks.map(task => {
              const meta = STATUS_META[task.status] || STATUS_META.pending
              return (
                <tr key={task.task_id}>
                  <td className="max-w-[180px]">
                    <div className="truncate text-slate-900 dark:text-slate-100" title={task.keyword}>
                      {task.keyword}
                    </div>
                    {task.error_message && (
                      <div className="text-xs text-red-500 truncate" title={task.error_message}>
                        {task.error_message}
                      </div>
                    )}
                  </td>
                  <td className="text-slate-600 dark:text-slate-300">{task.config_name || '-'}</td>
                  <td className="text-slate-600 dark:text-slate-300">
                    成功 {task.success} / 失败 {task.failed} / 共 {task.total}
                  </td>
                  <td><span className={meta.className}>{meta.label}</span></td>
                  <td className="text-slate-500 dark:text-slate-400">{formatDateTime(task.created_at)}</td>
                  <td>
                    <div className="table-actions">
                      <button
                        className="table-action-btn"
                        title={detail?.task_id === task.task_id ? '收起明细' : '查看明细'}
                        onClick={() => handleViewDetail(task)}
                        disabled={detailLoadingId === task.task_id}
                      >
                        {detailLoadingId === task.task_id
                          ? <Loader2 className="w-4 h-4 animate-spin text-blue-500" />
                          : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {detail && (
        <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium text-slate-900 dark:text-slate-100">
              任务明细：{detail.keyword}
            </span>
            <button className="btn-ios-secondary btn-sm" onClick={() => setDetail(null)}>
              <X className="w-3.5 h-3.5" />收起
            </button>
          </div>
          {failedItems.length === 0 ? (
            <div className="text-xs text-slate-500 dark:text-slate-400">
              这次任务没有失败的条目（共成功 {detail.success} 条）。
            </div>
          ) : (
            <div className="max-h-40 overflow-y-auto space-y-1">
              {failedItems.map(item => (
                <div key={item.seq} className="text-xs text-slate-500 dark:text-slate-400">
                  第 {item.seq} 条失败：{item.error_message || '未知原因'}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
        <div className="flex items-center gap-2">
          <span>每页</span>
          <select
            className="input-ios py-1 w-20"
            value={pageSize}
            onChange={e => { setPageSize(Number(e.target.value)); setPage(1) }}
          >
            {[10, 20, 50, 100].map(size => <option key={size} value={size}>{size}</option>)}
          </select>
          <span>共 {total} 条</span>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-ios-secondary btn-sm"
            onClick={() => setPage(p => Math.max(1, p - 1))}
            disabled={page <= 1 || loading}
          >
            上一页
          </button>
          <span>第 {page} / {totalPages || 1} 页</span>
          <button
            className="btn-ios-secondary btn-sm"
            onClick={() => setPage(p => (totalPages ? Math.min(totalPages, p + 1) : p))}
            disabled={page >= totalPages || loading}
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  )
}

export default AiListingTaskHistory



