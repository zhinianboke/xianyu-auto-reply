/**
 * 定时任务管理页面
 * 
 * 功能：
 * 1. 显示定时任务列表（任务名称、间隔时间、是否启用、运行状态）
 * 2. 支持开启/关闭定时任务
 * 3. 支持修改定时任务间隔时间
 * 4. 原列表追加安全频率任务，修改和手动执行后实时反馈
 */
import { useState, useEffect } from 'react'
import { Clock, RefreshCw, Loader2, Play, Pause, Zap } from 'lucide-react'
import { useUIStore } from '@/store/uiStore'
import { Loading } from '@/components/common/Loading'
import { useScheduledTasks } from './useScheduledTasks'
import { Pager } from '@/components/common/Pager'
import { useViewportContentHeight } from '@/components/common/useViewportContentHeight'

export function ScheduledTasks() {
  const { containerRef, height } = useViewportContentHeight<HTMLDivElement>()
  const state = useScheduledTasks()
  const { data, error: loadError, busy, operation } = state
  const { addToast } = useUIStore()
  const [editingTask, setEditingTask] = useState<string | null>(null)
  const [editInterval, setEditInterval] = useState(0)
  const tasks = data?.items || []
  const updating = operation?.kind === 'update' ? operation.code : null
  const triggering = operation?.kind === 'trigger' ? operation.code : null
  useEffect(() => { setEditingTask(null) }, [state.isCurrentSession])
  const handleCancelEdit = () => { setEditingTask(null); setEditInterval(0) }
  const handleSaveInterval = (code: string) => {
    if (!Number.isInteger(editInterval) || editInterval < 1 || editInterval > 2147483647) {
      addToast({ type: 'error', message: '执行间隔必须是1至2147483647之间的整数秒数' })
      return
    }
    state.update(code, { interval_seconds: editInterval }, handleCancelEdit)
  }

  return (
    <div ref={containerRef} style={{ height }} className="relative flex min-h-0 flex-col gap-4 overflow-hidden">
      {busy && <div className="absolute inset-0 z-20 flex items-center justify-center rounded-lg bg-white/80 dark:bg-slate-900/80"><Loading text={operation ? '正在处理任务并保存结果…' : '正在加载定时任务…'} /></div>}
      {/* Header */}
      <div className="max-h-[35%] shrink-0 overflow-y-auto flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">定时任务管理</h1>
          <p className="page-description">管理系统定时任务的执行间隔和启用状态</p>
        </div>
        <div className="flex gap-3">
          <button onClick={state.refresh} disabled={busy} className="btn-ios-secondary">
            {busy ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            刷新
          </button>
        </div>
      </div>

      {/* Tasks List */}
      <div className="vben-card flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="vben-card-header flex items-center justify-between">
          <h2 className="vben-card-title">
            <Clock className="w-4 h-4" />
            定时任务列表
          </h2>
          <span className="badge-primary">{loadError ? '任务加载异常' : data ? `${data.total} 个任务` : '正在加载'}</span>
        </div>
        <div className="table-scroll">
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
              {loadError ? <tr><td colSpan={6} className="text-center py-8 text-red-600 dark:text-red-400">{loadError}</td></tr> : tasks.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-slate-500 dark:text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <Clock className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>{data ? '暂无定时任务' : '定时任务尚未加载'}</p>
                    </div>
                  </td>
                </tr>
              ) : (
                tasks.map((task) => (
                  <tr key={task.id}>
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
                            max="2147483647"
                            step="1"
                            disabled={busy}
                            value={editInterval}
                            onChange={(e) => setEditInterval(Number(e.target.value))}
                            className="w-20 px-2 py-1 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 text-sm"
                          />
                          <span className="text-sm text-slate-500">秒</span>
                          <button
                            onClick={() => handleSaveInterval(task.task_code)}
                            disabled={busy}
                            className="p-1 rounded hover:bg-green-50 dark:hover:bg-green-900/20 transition-colors"
                            title="保存"
                          >
                            {updating === task.task_code ? (
                              <Loader2 className="w-4 h-4 animate-spin text-green-500" />
                            ) : (
                              '保存'
                            )}
                          </button>
                          <button
                            onClick={handleCancelEdit}
                            disabled={busy}
                            className="p-1 rounded hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                            title="取消"
                          >
                            取消
                          </button>
                        </div>
                      ) : (
                        <div className="flex items-center gap-2">
                          <span className="font-medium">{task.interval_seconds}</span>
                          <span className="text-sm text-slate-500">秒</span>
                          <button
                            onClick={() => { setEditingTask(task.task_code); setEditInterval(task.interval_seconds) }}
                            disabled={busy}
                            className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                            title="编辑"
                          >
                            编辑
                          </button>
                        </div>
                      )}
                    </td>
                    <td>
                      {task.enabled ? (
                        <span className="badge-success">已启用</span>
                      ) : (
                        <span className="badge-gray">已停止</span>
                      )}
                    </td>
                    <td className="text-slate-500 dark:text-slate-400 text-sm max-w-sm break-words">
                      <p>{task.description || '-'}</p>
                    </td>
                    <td>
                      <div className="flex flex-wrap items-center gap-2">
                        <button
                          onClick={() => state.run(task.task_code)}
                          disabled={busy}
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
                          onClick={() => state.update(task.task_code, { enabled: !task.enabled })}
                          disabled={busy}
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
                          {task.enabled ? '停止' : '启用'}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        {data && !loadError && <div className="max-h-[35%] shrink-0 overflow-y-auto">
          <Pager page={data.page} pageSize={data.page_size} total={data.total} totalPages={data.pages} loading={busy}
            onPageChange={(page) => { handleCancelEdit(); state.load(page, state.pageSize, state.filters) }}
            onPageSizeChange={(size) => { handleCancelEdit(); state.load(1, size, state.filters) }} />
        </div>}
      </div>

      {/* 提示信息 */}
      <div className="vben-card max-h-[30%] shrink-0 overflow-y-auto">
        <div className="vben-card-body">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            提示：修改定时任务配置后会立即生效。停止任务后，自动调度暂停，仍可手动执行。
          </p>
        </div>
      </div>
    </div>
  )
}
