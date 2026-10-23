/**
 * 数据库备份日志页面
 *
 * 功能：
 * 1. 显示数据库备份任务的执行日志列表（每小时自动备份一次，每次一条记录）
 * 2. 支持按状态、时间范围筛选与分页查询
 * 3. 支持下载备份文件（.sql.gz）
 * 4. 支持删除备份日志（关联的备份文件一并删除）
 */
import { useEffect, useRef, useState } from 'react'
import {
  Calendar,
  Database,
  Loader2,
  RefreshCw,
  RotateCcw,
  Trash2,
} from 'lucide-react'

import {
  batchDeleteDbBackupLogs,
  deleteDbBackupLog,
  downloadDbBackupFile,
  getDbBackupLogs,
  type DbBackupLog,
} from '@/api/dbBackupLogs'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { PageLoading } from '@/components/common/Loading'
import { Pager } from '@/components/common/Pager'
import { DbBackupLogsTable } from './DbBackupLogsTable'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/request'
import { getBeijingDateInputValue } from '@/utils/date'

interface DbBackupLogFilters {
  startDate: string
  endDate: string
  status: string
}

// 跑马灯文本：内容超出容器宽度时横向无缝滚动（用于弹窗中展示长文件名）
function MarqueeText({ text }: { text: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [scrolling, setScrolling] = useState(false)

  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    setScrolling(el.scrollWidth > el.clientWidth)
  }, [text])

  return (
    <div ref={containerRef} className="w-full overflow-hidden">
      <div className={`inline-flex whitespace-nowrap ${scrolling ? 'animate-marquee' : ''}`}>
        <span className="pr-8 font-mono text-blue-600 dark:text-blue-400">{text}</span>
        {scrolling && (
          <span className="pr-8 font-mono text-blue-600 dark:text-blue-400" aria-hidden="true">
            {text}
          </span>
        )}
      </div>
    </div>
  )
}

export function DbBackupLogs() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()

  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState<DbBackupLog[]>([])

  // 时间筛选 - 默认当天
  const today = getBeijingDateInputValue()
  const [startDate, setStartDate] = useState(today)
  const [endDate, setEndDate] = useState(today)

  // 状态筛选
  const [selectedStatus, setSelectedStatus] = useState('')
  const [appliedFilters, setAppliedFilters] = useState<DbBackupLogFilters>({
    startDate: today,
    endDate: today,
    status: '',
  })

  // 下载中的日志ID
  const [downloadingId, setDownloadingId] = useState<number | null>(null)

  // 删除确认弹窗
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; log: DbBackupLog | null }>({
    open: false,
    log: null,
  })
  const [deleting, setDeleting] = useState(false)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  // 确认弹窗持有打开时的 ID 快照，列表刷新不会改变本次确认的删除范围。
  const [batchDeleteIds, setBatchDeleteIds] = useState<number[] | null>(null)
  const [batchDeleting, setBatchDeleting] = useState(false)

  // 分页
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)

  const loadLogs = async (
    nextPage: number = currentPage,
    nextPageSize: number = pageSize,
    filters: DbBackupLogFilters = appliedFilters,
  ) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      setSelectedIds(new Set())
      const result = await getDbBackupLogs({
        page: nextPage,
        pageSize: nextPageSize,
        status: filters.status || undefined,
        start_date: filters.startDate || undefined,
        end_date: filters.endDate || undefined,
      })
      if (result.success) {
        const nextLogs = result.data || []
        const nextTotal = result.total || 0
        const lastPage = Math.max(1, Math.ceil(nextTotal / nextPageSize))
        if (nextLogs.length === 0 && nextTotal > 0 && nextPage > lastPage) {
          await loadLogs(lastPage, nextPageSize, filters)
          return
        }
        setLogs(nextLogs)
        setCurrentPage(nextPage)
        setPageSize(nextPageSize)
        setTotal(nextTotal)
      } else {
        setLogs([])
        setCurrentPage(nextPage)
        setPageSize(nextPageSize)
        setTotal(0)
        addToast({ type: 'error', message: result.message || '加载数据库备份日志失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载数据库备份日志失败') })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadLogs(1, pageSize)
    // 仅在认证态变更时初始化加载
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [_hasHydrated, isAuthenticated, token])

  const handleSearch = () => {
    if (startDate && endDate && startDate > endDate) {
      addToast({ type: 'error', message: '开始日期不能晚于结束日期' })
      return
    }
    const filters = { startDate, endDate, status: selectedStatus }
    setAppliedFilters(filters)
    loadLogs(1, pageSize, filters)
  }

  const handleReset = () => {
    const filters = { startDate: today, endDate: today, status: '' }
    setStartDate(today)
    setEndDate(today)
    setSelectedStatus('')
    setAppliedFilters(filters)
    loadLogs(1, pageSize, filters)
  }

  const handleDownload = async (log: DbBackupLog) => {
    if (!log.downloadable) return
    setDownloadingId(log.id)
    try {
      const result = await downloadDbBackupFile(log.id)
      if (!result.success || !result.blob) {
        addToast({ type: 'error', message: result.message || '下载失败' })
        return
      }
      // 触发浏览器下载
      const url = window.URL.createObjectURL(result.blob)
      const link = document.createElement('a')
      link.href = url
      link.download = result.filename || log.file_name || 'backup.sql.gz'
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      window.URL.revokeObjectURL(url)
      addToast({ type: 'success', message: '备份文件下载已开始' })
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '下载失败') })
    } finally {
      setDownloadingId(null)
    }
  }

  // 删除备份日志（日志记录 + 关联备份文件）
  const handleDelete = async () => {
    const log = deleteConfirm.log
    if (!log) return
    setDeleting(true)
    try {
      const result = await deleteDbBackupLog(log.id)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '备份日志已删除' })
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
      const recordRemoved = result.success || result.code === 40002
      if (recordRemoved) {
        setDeleteConfirm({ open: false, log: null })
        const nextPage = logs.length === 1 && currentPage > 1 ? currentPage - 1 : currentPage
        await loadLogs(nextPage, pageSize)
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '删除失败') })
    } finally {
      setDeleting(false)
    }
  }

  const handleBatchDelete = async () => {
    const ids = batchDeleteIds
    if (!ids?.length) {
      addToast({ type: 'error', message: '请选择要删除的备份日志' })
      return
    }
    setBatchDeleting(true)
    try {
      const result = await batchDeleteDbBackupLogs(ids)
      if (result.success) {
        addToast({ type: 'success', message: result.message || `成功删除 ${ids.length} 条备份日志` })
      } else {
        addToast({ type: 'error', message: result.message || '批量删除失败' })
      }
      const recordsRemoved = result.success || result.code === 40002
      if (recordsRemoved) {
        setBatchDeleteIds(null)
        setSelectedIds(new Set())
        // 全部删除成功时直接回退；部分成功时由 loadLogs 根据新的总数校正页码。
        const nextPage = result.success && logs.length === ids.length && currentPage > 1
          ? currentPage - 1
          : currentPage
        await loadLogs(nextPage, pageSize)
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '批量删除失败') })
    } finally {
      setBatchDeleting(false)
    }
  }

  const toggleSelectAll = () => {
    // 只切换当前页全选，避免误选其他页的数据。
    if (logs.length > 0 && logs.every((log) => selectedIds.has(log.id))) {
      setSelectedIds((prev) => {
        const next = new Set(prev)
        logs.forEach((log) => next.delete(log.id))
        return next
      })
      return
    }
    setSelectedIds((prev) => {
      const next = new Set(prev)
      logs.forEach((log) => next.add(log.id))
      return next
    })
  }

  // 分页计算
  const totalPages = Math.ceil(total / pageSize)
  const hasChangedFilters =
    startDate !== today ||
    endDate !== today ||
    selectedStatus !== '' ||
    appliedFilters.startDate !== today ||
    appliedFilters.endDate !== today ||
    appliedFilters.status !== ''

  const handlePageChange = (nextPage: number) => {
    if (nextPage < 1 || nextPage > totalPages) {
      return
    }
    loadLogs(nextPage, pageSize)
  }

  const handlePageSizeChange = (nextPageSize: number) => {
    loadLogs(1, nextPageSize)
  }

  if (loading && logs.length === 0 && !deleteConfirm.open && !batchDeleteIds) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">数据库备份日志</h1>
          <p className="page-description">查看数据库自动备份的执行结果，支持下载备份文件</p>
        </div>
        <div className="flex gap-3 flex-wrap">
          {selectedIds.size > 0 && (
            <button
              onClick={() => setBatchDeleteIds(Array.from(selectedIds))}
              disabled={loading || batchDeleting}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-900/20 dark:text-red-400 dark:hover:bg-red-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <Trash2 className="w-4 h-4" />
              删除选中（{selectedIds.size}）
            </button>
          )}
          <button onClick={() => loadLogs()} disabled={loading} className="btn-ios-secondary">
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
              <label className="input-label">备份状态</label>
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="input-ios"
              >
                <option value="">全部状态</option>
                <option value="success">成功</option>
                <option value="failed">失败</option>
              </select>
            </div>
            <div className="ml-auto flex items-center gap-3">
              {hasChangedFilters && (
                <button onClick={handleReset} disabled={loading} className="btn-ios-secondary">
                  <RotateCcw className="w-4 h-4" />
                  重置
                </button>
              )}
              <button onClick={handleSearch} disabled={loading} className="btn-ios-primary">
                <Calendar className="w-4 h-4" />
                查询
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Logs List */}
      <div
        className="vben-card relative flex flex-col overflow-hidden"
        style={{ height: 'calc(100vh - 380px)', minHeight: '400px' }}
      >
        {loading && (
          <div className="absolute inset-0 z-30 flex items-center justify-center bg-white/70 backdrop-blur-sm dark:bg-slate-900/70">
            <div className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
              <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
              加载中...
            </div>
          </div>
        )}
        <div className="vben-card-header flex-shrink-0">
          <h2 className="vben-card-title">
            <Database className="w-4 h-4 text-blue-500" />
            备份执行记录
          </h2>
          <span className="badge-primary">{total} 条记录</span>
        </div>
        <DbBackupLogsTable
          logs={logs}
          selectedIds={selectedIds}
          downloadingId={downloadingId}
          onToggleAll={toggleSelectAll}
          onToggleOne={(logId) =>
            setSelectedIds((prev) => {
              const next = new Set(prev)
              if (next.has(logId)) next.delete(logId)
              else next.add(logId)
              return next
            })
          }
          onDownload={handleDownload}
          onDelete={(log) => setDeleteConfirm({ open: true, log })}
        />

        {/* 分页 */}
        {total > 0 && (
          <Pager
            page={currentPage}
            pageSize={pageSize}
            total={total}
            totalPages={totalPages}
            loading={loading}
            onPageChange={handlePageChange}
            onPageSizeChange={handlePageSizeChange}
          />
        )}
      </div>

      {/* 删除确认弹窗（沿用删除卡券的弹窗风格） */}
      <ConfirmModal
        isOpen={deleteConfirm.open}
        type="danger"
        title="删除备份日志"
        confirmText="删除"
        loading={deleting}
        message={
          <div className="space-y-1.5">
            <div>确认要删除备份日志</div>
            <MarqueeText text={deleteConfirm.log?.file_name || '-'} />
            <div className="text-amber-500 dark:text-amber-400">
              该记录关联的备份文件也会一并删除
            </div>
            <div className="font-bold text-red-500 dark:text-red-400">此操作不可恢复</div>
          </div>
        }
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm({ open: false, log: null })}
      />

      {/* 批量删除确认弹窗 */}
      <ConfirmModal
        isOpen={batchDeleteIds !== null}
        type="danger"
        title="批量删除备份日志"
        confirmText="批量删除"
        loading={batchDeleting}
        message={`确认删除选中的 ${batchDeleteIds?.length ?? 0} 条备份日志及其关联文件吗？此操作不可恢复。`}
        onConfirm={handleBatchDelete}
        onCancel={() => { if (!batchDeleting) setBatchDeleteIds(null) }}
      />
    </div>
  )
}
