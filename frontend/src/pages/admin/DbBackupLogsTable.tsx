/**
 * 数据库备份日志表格。
 *
 * 提供当前页全选、单条选择、下载和删除入口，滚动行为由公共 table-scroll 类负责。
 */
import { useEffect, useRef } from 'react'
import { Database, Download, Loader2, Trash2 } from 'lucide-react'

import type { DbBackupLog } from '@/api/dbBackupLogs'
import { formatDateTime } from '@/utils/date'

interface DbBackupLogsTableProps {
  logs: DbBackupLog[]
  selectedIds: Set<number>
  downloadingId: number | null
  onToggleAll: () => void
  onToggleOne: (logId: number) => void
  onDownload: (log: DbBackupLog) => void
  onDelete: (log: DbBackupLog) => void
}

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

function formatFileSize(size: number | null): string {
  if (size === null || size === undefined) return '-'
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`
  if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(2)} MB`
  return `${(size / 1024 / 1024 / 1024).toFixed(2)} GB`
}

function formatDuration(ms: number | null): string {
  if (ms === null || ms === undefined) return '-'
  if (ms < 1000) return `${ms} ms`
  return `${(ms / 1000).toFixed(1)} s`
}

function renderStatus(status: string) {
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

export function DbBackupLogsTable({
  logs,
  selectedIds,
  downloadingId,
  onToggleAll,
  onToggleOne,
  onDownload,
  onDelete,
}: DbBackupLogsTableProps) {
  const allSelected = logs.length > 0 && logs.every((log) => selectedIds.has(log.id))
  const selectedCount = logs.filter((log) => selectedIds.has(log.id)).length
  const selectAllRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (selectAllRef.current) {
      selectAllRef.current.indeterminate = selectedCount > 0 && !allSelected
    }
  }, [allSelected, selectedCount])

  return (
    <div className="table-scroll">
      <table className="table-ios">
        <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
          <tr>
            <th className="w-12 !text-center">
              <input
                ref={selectAllRef}
                type="checkbox"
                checked={allSelected}
                onChange={onToggleAll}
                aria-label="全选当前页"
                className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500"
              />
            </th>
            <th className="min-w-[100px] !text-center">状态</th>
            <th className="min-w-[280px] !text-center">备份文件名</th>
            <th className="min-w-[100px] !text-center">文件大小</th>
            <th className="min-w-[80px] !text-center">表数量</th>
            <th className="min-w-[100px] !text-center">数据行数</th>
            <th className="min-w-[90px] !text-center">耗时</th>
            <th className="min-w-[250px] !text-center">错误详情</th>
            <th className="min-w-[155px] !text-center">备份时间</th>
            <th className="min-w-[140px] !text-center">操作</th>
          </tr>
        </thead>
        <tbody>
          {logs.length === 0 ? (
            <tr>
              <td colSpan={10} className="text-center py-8 text-slate-500 dark:text-slate-400">
                <div className="flex flex-col items-center gap-2">
                  <Database className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                  <p>暂无数据库备份日志</p>
                </div>
              </td>
            </tr>
          ) : (
            logs.map((log) => (
              <tr key={log.id} className={selectedIds.has(log.id) ? 'bg-blue-50 dark:bg-blue-900/10' : ''}>
                <td className="whitespace-nowrap !text-center">
                  <input
                    type="checkbox"
                    checked={selectedIds.has(log.id)}
                    onChange={() => onToggleOne(log.id)}
                    aria-label={`选择日志 ${log.id}`}
                    className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500"
                  />
                </td>
                <td className="whitespace-nowrap !text-center">{renderStatus(log.status)}</td>
                <td className="font-medium text-blue-600 dark:text-blue-400 max-w-[300px] !text-center">
                  <span className="block truncate" title={log.file_name || ''}>{log.file_name || '-'}</span>
                </td>
                <td className="text-slate-600 dark:text-slate-300 whitespace-nowrap !text-center">{formatFileSize(log.file_size)}</td>
                <td className="text-slate-600 dark:text-slate-300 !text-center">{log.table_count ?? '-'}</td>
                <td className="text-slate-600 dark:text-slate-300 !text-center">{log.total_rows ?? '-'}</td>
                <td className="text-slate-500 dark:text-slate-400 whitespace-nowrap !text-center">{formatDuration(log.duration_ms)}</td>
                <td className="max-w-[260px] text-slate-500 dark:text-slate-400 !text-center">
                  <span className="block truncate cursor-help" title={log.error_message || ''}>{log.error_message || '-'}</span>
                </td>
                <td className="text-slate-500 dark:text-slate-400 text-sm whitespace-nowrap !text-center">{formatDateTime(log.created_at)}</td>
                <td className="whitespace-nowrap !text-center">
                  <div className="inline-flex items-center gap-1.5">
                    {log.downloadable ? (
                      <button
                        onClick={() => onDownload(log)}
                        disabled={downloadingId === log.id}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors bg-blue-50 text-blue-600 hover:bg-blue-100 dark:bg-blue-900/20 dark:text-blue-400 dark:hover:bg-blue-900/30 disabled:opacity-50 disabled:cursor-not-allowed"
                        title="下载备份文件"
                      >
                        {downloadingId === log.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
                        下载
                      </button>
                    ) : (
                      <span className="text-xs text-slate-400 dark:text-slate-500">不可下载</span>
                    )}
                    <button
                      onClick={() => onDelete(log)}
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-900/20 dark:text-red-400 dark:hover:bg-red-900/30"
                      title="删除备份日志"
                    >
                      <Trash2 className="w-4 h-4" />
                      删除
                    </button>
                  </div>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
