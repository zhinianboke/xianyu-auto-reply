import { useState, useEffect } from 'react'
import { FileText, RefreshCw, Trash2, AlertCircle, AlertTriangle, Info } from 'lucide-react'
import { getSystemLogs, clearSystemLogs, type SystemLog } from '@/api/admin'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { cn } from '@/utils/cn'

const limitOptions = [
  { value: 50, label: '50 条' },
  { value: 100, label: '100 条' },
  { value: 200, label: '200 条' },
  { value: 500, label: '500 条' },
]

export function Logs() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState<SystemLog[]>([])
  const [levelFilter, setLevelFilter] = useState('')
  const [limit, setLimit] = useState(100)

  // 从后端获取最近 N 条日志（不按级别过滤）
  const loadLogs = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getSystemLogs({ limit })
      if (result.success) {
        setLogs(result.data || [])
      }
    } catch {
      addToast({ type: 'error', message: '加载系统日志失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated) return
    if (!isAuthenticated || !token) return
    loadLogs()
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [_hasHydrated, isAuthenticated, token, limit])

  // 前端根据当前筛选级别过滤日志
  const filteredLogs = levelFilter
    ? logs.filter((log) => log.level === levelFilter)
    : logs

  const handleClear = async () => {
    if (!confirm('确定要清空所有系统日志吗？此操作不可恢复！')) return
    try {
      await clearSystemLogs()
      addToast({ type: 'success', message: '日志已清空' })
      loadLogs()
    } catch {
      addToast({ type: 'error', message: '清空失败' })
    }
  }

  const getLevelIcon = (level: string) => {
    switch (level) {
      case 'error':
        return <AlertCircle className="w-4 h-4 text-red-500" />
      case 'warning':
        return <AlertTriangle className="w-4 h-4 text-amber-500" />
      default:
        return <Info className="w-4 h-4 text-blue-500" />
    }
  }

  const getLevelBadge = (level: string) => {
    switch (level) {
      case 'error':
        return <span className="badge-danger">错误</span>
      case 'warning':
        return <span className="badge-warning">警告</span>
      default:
        return <span className="badge-info">信息</span>
    }
  }

  if (loading && logs.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="page-header flex-between flex-wrap gap-4">
        <div>
          <h1 className="page-title">系统日志</h1>
          <p className="page-description">查看系统运行日志</p>
        </div>
        <div className="flex gap-2">
          <button onClick={handleClear} className="btn-ios-danger">
            <Trash2 className="w-4 h-4" />
            清空日志
          </button>
          <button onClick={loadLogs} className="btn-ios-secondary">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {/* Filter */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex gap-2">
          {['', 'info', 'warning', 'error'].map((level) => (
            <button
              key={level}
              onClick={() => setLevelFilter(level)}
              className={cn(
                'px-4 py-2 rounded-lg text-sm font-medium transition-colors',
                levelFilter === level
                  ? 'bg-blue-500 text-white'
                  : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600'
              )}
            >
              {level === '' ? '全部' : level === 'info' ? '信息' : level === 'warning' ? '警告' : '错误'}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-500 dark:text-slate-400">显示条数:</span>
          <select
            value={limit}
            onChange={(e) => setLimit(Number(e.target.value))}
            className="px-3 py-2 rounded-lg text-sm bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300 border-0 focus:ring-2 focus:ring-blue-500"
          >
            {limitOptions.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Logs List */}
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title flex items-center gap-2">
            <FileText className="w-4 h-4" />
            日志列表
          </h2>
          <span className="badge-primary">{filteredLogs.length} 条记录</span>
        </div>
        <div className="divide-y divide-slate-100 dark:divide-slate-700 max-h-[600px] overflow-y-auto">
          {filteredLogs.length === 0 ? (
            <div className="text-center py-12 text-slate-500 dark:text-slate-400">
              <FileText className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
              <p>暂无日志记录</p>
            </div>
          ) : (
            filteredLogs.map((log) => (
              <div key={log.id} className="px-6 py-4 hover:bg-slate-50 dark:hover:bg-slate-700/50 transition-colors">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5">{getLevelIcon(log.level)}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      {getLevelBadge(log.level)}
                      <span className="text-xs text-slate-500 dark:text-slate-400 bg-slate-100 dark:bg-slate-700 px-2 py-0.5 rounded">
                        {log.module}
                      </span>
                      <span className="text-xs text-slate-400 dark:text-slate-500">
                        {new Date(log.created_at).toLocaleString()}
                      </span>
                    </div>
                    <p className="text-sm text-slate-700 dark:text-slate-300 break-all">{log.message}</p>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  )
}
