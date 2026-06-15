import { useState, useEffect } from 'react'
import { FileText, RefreshCw, Trash2, AlertCircle, AlertTriangle, Info, Upload } from 'lucide-react'
import { Button, Modal, Select, Typography } from '@arco-design/web-react'
import { getSystemLogs, clearSystemLogs, exportLogs, type SystemLog } from '@/api/admin'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'

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

  // 从后端获取最近 N 条日志
  const loadLogs = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getSystemLogs({ limit, level: levelFilter || undefined })
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
  }, [_hasHydrated, isAuthenticated, token, limit, levelFilter])

  const handleClear = async () => {
    Modal.confirm({
      title: '清空系统日志',
      content: '确定要清空所有系统日志吗？此操作不可恢复。',
      okButtonProps: { status: 'danger' },
      onOk: async () => {
        try {
          await clearSystemLogs()
          addToast({ type: 'success', message: '日志已清空' })
          loadLogs()
        } catch {
          addToast({ type: 'error', message: '清空失败' })
        }
      },
    })
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
        return <span className="logs-terminal-badge logs-terminal-badge--error">ERR</span>
      case 'warning':
        return <span className="logs-terminal-badge logs-terminal-badge--warning">WARN</span>
      default:
        return <span className="logs-terminal-badge logs-terminal-badge--info">INFO</span>
    }
  }

  if (loading && logs.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      <div className="vben-card">
        <div className="accounts-page-intro blacklist-page-intro">
          <div>
            <h1>系统日志</h1>
            <p>查看系统运行日志</p>
          </div>
          <div className="table-toolbar-right">
            <Button
              type="primary"
              onClick={() => window.open(exportLogs(), '_blank')}
              className="accounts-header-btn"
            >
              <Upload />
              导出日志
            </Button>
            <Button onClick={handleClear} className="accounts-header-btn">
              <Trash2 />
              清空日志
            </Button>
            <Button onClick={loadLogs} className="accounts-header-btn">
              <RefreshCw />
              刷新
            </Button>
          </div>
        </div>
        <div className="table-toolbar">
          <div className="table-filter-row table-filter-row--lined flex-wrap">
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type={levelFilter === '' ? 'primary' : 'secondary'}
                status="default"
                onClick={() => setLevelFilter('')}
              >
                全部
              </Button>

              <Button
                type={levelFilter === 'info' ? 'primary' : 'secondary'}
                status="default"
                onClick={() => setLevelFilter('info')}
              >
                信息
              </Button>

              <Button
                type={levelFilter === 'warning' ? 'primary' : 'secondary'}
                status="warning"
                onClick={() => setLevelFilter('warning')}
              >
                警告
              </Button>

              <Button
                type={levelFilter === 'error' ? 'primary' : 'secondary'}
                status="danger"
                onClick={() => setLevelFilter('error')}
              >
                错误
              </Button>
            </div>
            <div className="table-toolbar-right">
              <Typography.Text type="secondary">
                显示条数:
              </Typography.Text>
              <Select
                value={limit}
                onChange={(value) => setLimit(Number(value))}
                style={{ width: 120 }}
                size="small"
                options={limitOptions}
              >
              </Select>
            </div>
          </div>
        </div>
        <div className="logs-terminal-panel max-h-[60vh] overflow-y-auto">
          {logs.length === 0 ? (
            <div className="text-center py-12 text-slate-400">
              <FileText className="w-12 h-12 text-slate-600 mx-auto mb-4" />
              <p>暂无日志记录</p>
            </div>
          ) : (
            logs.map((log) => (
              <div key={log.id} className="logs-terminal-entry">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 logs-terminal-icon">{getLevelIcon(log.level)}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      {getLevelBadge(log.level)}
                      <span className="logs-terminal-module">
                        {log.module}
                      </span>
                      {log.created_at && (
                        <span className="logs-terminal-time">
                          {new Date(log.created_at).toLocaleString()}
                        </span>
                      )}
                    </div>
                    <p className="logs-terminal-message">{log.message}</p>
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
