/**
 * 数据库备份日志页面
 *
 * 功能：
 * 1. 显示数据库备份任务的执行日志列表（每小时自动备份一次，每次一条记录）
 * 2. 支持按状态、时间范围筛选与分页查询
 * 3. 支持下载备份文件（.sql.gz）
 */
import { useEffect, useState } from 'react'
import {
  Calendar,
  ChevronLeft,
  ChevronRight,
  Database,
  Download,
  Loader2,
  RefreshCw,
} from 'lucide-react'

import {
  downloadDbBackupFile,
  getDbBackupLogs,
  type DbBackupLog,
} from '@/api/admin'
import { PageLoading } from '@/components/common/Loading'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/request'

// 备份状态中文映射 + 标签颜色
const STATUS_LABELS: Record<string, { text: string; cls: string }> = {
  success: {
    text: '成功',
    cls: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  },
  failed: {
    text: '失败',
    cls: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  },
}

// 将字节数格式化为易读文本
const formatFileSize = (size: number | null): string => {
  if (size === null || size === undefined) return '-'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(2)} MB`
  return `${(size / 1024 / 1024 / 1024).toFixed(2)} GB`
}

// 将耗时（毫秒）格式化为易读文本
const formatDuration = (ms: number | null): string => {
  if (ms === null || ms === undefined) return '-'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

export function DbBackupLogs() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()

  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState<DbBackupLog[]>([])

  // 时间筛选 - 默认当天
  const today = new Date().toISOString().split('T')[0]
  const [startDate, setStartDate] = useState(today)
  const [endDate, setEndDate] = useState(today)

  // 状态筛选
  const [selectedStatus, setSelectedStatus] = useState('')

  // 下载中的日志ID
  const [downloadingId, setDownloadingId] = useState<number | null>(null)

  // 分页
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)

  const loadLogs = async (nextPage: number = currentPage, nextPageSize: number = pageSize) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getDbBackupLogs({
        page: nextPage,
        pageSize: nextPageSize,
        status: selectedStatus || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
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
    loadLogs(1, pageSize)
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

  // 分页计算
  const totalPages = Math.ceil(total / pageSize)
  const startIndex = total === 0 ? 0 : (currentPage - 1) * pageSize + 1
  const endIndex = Math.min(currentPage * pageSize, total)

  const handlePageChange = (nextPage: number) => {
    if (nextPage < 1 || nextPage > totalPages) {
      return
    }
    loadLogs(nextPage, pageSize)
  }

  const handlePageSizeChange = (nextPageSize: number) => {
    loadLogs(1, nextPageSize)
  }

  const renderStatus = (status: string) => {
    const meta = STATUS_LABELS[status] || {
      text: status || '-',
      cls: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
    }
    return (
      <span className={`inline-block text-xs px-2 py-1 rounded whitespace-nowrap ${meta.cls}`}>
        {meta.text}
      </span>
    )
  }

  if (loading && logs.length === 0) {
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
            <button onClick={handleSearch} className="btn-ios-primary">
              <Calendar className="w-4 h-4" />
              查询
            </button>
          </div>
        </div>
      </div>

      {/* Logs List */}
      <div
        className="vben-card flex flex-col"
        style={{ height: 'calc(100vh - 380px)', minHeight: '400px' }}
      >
        <div className="vben-card-header flex-shrink-0">
          <h2 className="vben-card-title">
            <Database className="w-4 h-4 text-blue-500" />
            备份执行记录
          </h2>
          <span className="badge-primary">{total} 条记录</span>
        </div>
        <div className="flex-1 overflow-x-auto overflow-y-auto">
          <table className="table-ios">
            <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
              <tr>
                <th className="min-w-[100px]">状态</th>
                <th className="min-w-[280px]">备份文件名</th>
                <th className="min-w-[100px]">文件大小</th>
                <th className="min-w-[80px]">表数量</th>
                <th className="min-w-[100px]">数据行数</th>
                <th className="min-w-[90px]">耗时</th>
                <th className="min-w-[250px]">错误详情</th>
                <th className="min-w-[155px]">备份时间</th>
                <th className="min-w-[100px]">操作</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={9} className="text-center py-8 text-slate-500 dark:text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <Database className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>暂无数据库备份日志</p>
                    </div>
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id}>
                    <td className="whitespace-nowrap">{renderStatus(log.status)}</td>
                    <td className="font-medium text-blue-600 dark:text-blue-400 max-w-[300px]">
                      <span className="block truncate" title={log.file_name || ''}>
                        {log.file_name || '-'}
                      </span>
                    </td>
                    <td className="text-slate-600 dark:text-slate-300 whitespace-nowrap">
                      {formatFileSize(log.file_size)}
                    </td>
                    <td className="text-slate-600 dark:text-slate-300">
                      {log.table_count ?? '-'}
                    </td>
                    <td className="text-slate-600 dark:text-slate-300">
                      {log.total_rows ?? '-'}
                    </td>
                    <td className="text-slate-500 dark:text-slate-400 whitespace-nowrap">
                      {formatDuration(log.duration_ms)}
                    </td>
                    <td className="max-w-[260px] text-slate-500 dark:text-slate-400">
                      <span className="block truncate cursor-help" title={log.error_message || ''}>
                        {log.error_message || '-'}
                      </span>
                    </td>
                    <td className="text-slate-500 dark:text-slate-400 text-sm whitespace-nowrap">
                      {new Date(log.created_at).toLocaleString()}
                    </td>
                    <td className="whitespace-nowrap">
                      {log.downloadable ? (
                        <button
                          onClick={() => handleDownload(log)}
                          disabled={downloadingId === log.id}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors bg-blue-50 text-blue-600 hover:bg-blue-100 dark:bg-blue-900/20 dark:text-blue-400 dark:hover:bg-blue-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
                          title="下载备份文件"
                        >
                          {downloadingId === log.id ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Download className="w-4 h-4" />
                          )}
                          下载
                        </button>
                      ) : (
                        <span className="text-xs text-slate-400 dark:text-slate-500">不可下载</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* 分页 */}
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
    </div>
  )
}
