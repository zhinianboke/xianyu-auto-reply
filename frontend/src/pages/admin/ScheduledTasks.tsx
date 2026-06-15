/**
 * 定时任务管理页面
 * 
 * 功能：
 * 1. 显示定时任务列表（任务名称、间隔时间、是否启用、运行状态）
 * 2. 支持开启/关闭定时任务
 * 3. 支持修改定时任务间隔时间
 * 4. 修改后实时生效
 */
import { useState, useEffect } from 'react'
import { Clock, RefreshCw, Loader2, Play, Pause, Edit2, Check, X, Zap } from 'lucide-react'
import { getScheduledTasks, updateScheduledTask, triggerScheduledTask, type ScheduledTask } from '@/api/scheduledTasks'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'

export function ScheduledTasks() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [tasks, setTasks] = useState<ScheduledTask[]>([])
  
  // 编辑状态
  const [editingTask, setEditingTask] = useState<string | null>(null)
  const [editInterval, setEditInterval] = useState<number>(0)
  const [updating, setUpdating] = useState<string | null>(null)
  const [triggering, setTriggering] = useState<string | null>(null)

  const loadTasks = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getScheduledTasks()
      if (result.success) {
        setTasks(result.data || [])
      }
    } catch {
      addToast({ type: 'error', message: '加载定时任务列表失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadTasks()
  }, [_hasHydrated, isAuthenticated, token])

  // 手动触发任务
  const handleTrigger = async (task: ScheduledTask) => {
    setTriggering(task.task_code)
    try {
      const result = await triggerScheduledTask(task.task_code)
      if (result.success) {
        addToast({ type: 'success', message: result.message || `${task.task_name} 已触发执行` })
      } else {
        addToast({ type: 'error', message: result.message || '触发失败' })
      }
    } catch (error: any) {
      addToast({ type: 'error', message: error.response?.data?.detail || '触发失败' })
    } finally {
      setTriggering(null)
    }
  }

  // 切换任务启用状态
  const handleToggleEnabled = async (task: ScheduledTask) => {
    setUpdating(task.task_code)
    try {
      const result = await updateScheduledTask(task.task_code, { enabled: !task.enabled })
      if (result.success) {
        addToast({ type: 'success', message: result.message })
        loadTasks()
      } else {
        addToast({ type: 'error', message: '更新失败' })
      }
    } catch (error: any) {
      addToast({ type: 'error', message: error.response?.data?.detail || '更新失败' })
    } finally {
      setUpdating(null)
    }
  }

  // 开始编辑间隔时间
  const handleStartEdit = (task: ScheduledTask) => {
    setEditingTask(task.task_code)
    setEditInterval(task.interval_seconds)
  }

  // 取消编辑
  const handleCancelEdit = () => {
    setEditingTask(null)
    setEditInterval(0)
  }

  // 保存间隔时间
  const handleSaveInterval = async (taskCode: string) => {
    if (editInterval < 1) {
      addToast({ type: 'error', message: '间隔时间不能小于1秒' })
      return
    }
    
    setUpdating(taskCode)
    try {
      const result = await updateScheduledTask(taskCode, { interval_seconds: editInterval })
      if (result.success) {
        addToast({ type: 'success', message: result.message })
        setEditingTask(null)
        loadTasks()
      } else {
        addToast({ type: 'error', message: '更新失败' })
      }
    } catch (error: any) {
      addToast({ type: 'error', message: error.response?.data?.detail || '更新失败' })
    } finally {
      setUpdating(null)
    }
  }

  if (loading && tasks.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      <div className="vben-card">
        <div className="accounts-page-intro blacklist-page-intro">
          <div>
            <h1>定时任务管理</h1>
            <p>管理系统定时任务的执行间隔和启用状态</p>
          </div>
          <button onClick={loadTasks} disabled={loading} className="btn-ios-secondary">
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            刷新
          </button>
        </div>

        <div className="table-toolbar">
          <div className="table-filter-row table-filter-row--lined">
            <div className="flex items-center gap-2 text-sm font-medium text-slate-600 dark:text-slate-300">
              <Clock className="w-4 h-4" />
              定时任务列表
            </div>
            <span className="badge-primary">{tasks.length} 个任务</span>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="table-ios">
            <thead>
              <tr>
                <th>任务名称</th>
                <th>任务代码</th>
                <th>执行间隔</th>
                <th>启用状态</th>
                <th>描述</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tasks.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-slate-500 dark:text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <Clock className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>暂无定时任务</p>
                    </div>
                  </td>
                </tr>
              ) : (
                tasks.map((task) => (
                  <tr key={task.task_code}>
                    <td className="font-medium text-slate-900 dark:text-white">
                      {task.task_name}
                    </td>
                    <td className="text-slate-500 dark:text-slate-400 font-mono text-sm">
                      {task.task_code}
                    </td>
                    <td>
                      {editingTask === task.task_code ? (
                        <div className="flex items-center gap-2">
                          <input
                            type="number"
                            min="1"
                            value={editInterval}
                            onChange={(e) => setEditInterval(Number(e.target.value))}
                            className="w-20 px-2 py-1 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-sm"
                          />
                          <span className="text-sm text-slate-500">秒</span>
                          <button
                            onClick={() => handleSaveInterval(task.task_code)}
                            disabled={updating === task.task_code}
                            className="p-1 rounded hover:bg-green-50 dark:hover:bg-green-900/20 transition-colors"
                            title="保存"
                          >
                            {updating === task.task_code ? (
                              <Loader2 className="w-4 h-4 animate-spin text-green-500" />
                            ) : (
                              <Check className="w-4 h-4 text-green-500" />
                            )}
                          </button>
                          <button
                            onClick={handleCancelEdit}
                            className="p-1 rounded hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                            title="取消"
                          >
                            <X className="w-4 h-4 text-red-500" />
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{task.interval_seconds}</span>
                          <span className="text-sm text-slate-500">秒</span>
                          <button
                            onClick={() => handleStartEdit(task)}
                            className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                            title="编辑"
                          >
                            <Edit2 className="w-3.5 h-3.5 text-slate-400" />
                          </button>
                        </div>
                      )}
                    </td>
                    <td>
                      {task.enabled ? (
                        <span className="badge-success">已启用</span>
                      ) : (
                        <span className="badge-gray">已禁用</span>
                      )}
                    </td>
                    <td className="text-slate-500 dark:text-slate-400 text-sm max-w-xs truncate">
                      {task.description || '-'}
                    </td>
                    <td>
                      <div className="flex items-center gap-2">
                        <button
                          onClick={() => handleTrigger(task)}
                          disabled={triggering === task.task_code}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors bg-blue-50 text-blue-600 hover:bg-blue-100 dark:bg-blue-900/20 dark:text-blue-400 dark:hover:bg-blue-900/30"
                          title="手动执行一次该任务"
                        >
                          {triggering === task.task_code ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : (
                            <Zap className="w-4 h-4" />
                          )}
                          执行
                        </button>
                        <button
                          onClick={() => handleToggleEnabled(task)}
                          disabled={updating === task.task_code}
                          className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                            task.enabled
                              ? 'bg-red-50 text-red-600 hover:bg-red-100 dark:bg-red-900/20 dark:text-red-400 dark:hover:bg-red-900/30'
                              : 'bg-green-50 text-green-600 hover:bg-green-100 dark:bg-green-900/20 dark:text-green-400 dark:hover:bg-green-900/30'
                          }`}
                        >
                          {updating === task.task_code ? (
                            <Loader2 className="w-4 h-4 animate-spin" />
                          ) : task.enabled ? (
                            <Pause className="w-4 h-4" />
                          ) : (
                            <Play className="w-4 h-4" />
                          )}
                          {task.enabled ? '禁用' : '启用'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <div className="mt-4 border-t border-slate-200 pt-4 dark:border-slate-700">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            提示：修改定时任务配置后会立即生效。禁用任务后，该任务将不再执行，但调度器仍会按间隔时间检查任务状态。
          </p>
        </div>
      </div>
    </div>
  )
}
