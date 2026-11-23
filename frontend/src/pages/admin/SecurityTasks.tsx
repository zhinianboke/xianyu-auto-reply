/** 安全任务列表：真实下次执行及上次结果，手动执行共用后端审计，插件调度保持独立。 */
import { useEffect, useRef, useState } from 'react'
import { RefreshCw, ShieldCheck } from 'lucide-react'
import { executeSecurityTask, getSecurityTasks, securityLabel } from '@/api/securityManagement'
import { Loading } from '@/components/common/Loading'
import { Pager } from '@/components/common/Pager'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { formatBeijingDateTime } from '@/utils/date'
import { useSecurityPage } from './useSecurityPage'

const NO_FILTERS = {}
export function SecurityTasks() {
  const { data, filters, loading, error, load, isCurrentSession, page, pageSize } = useSecurityPage(getSecurityTasks, NO_FILTERS)
  const [executing, setExecuting] = useState(false)
  const executingRef = useRef(false)
  const generation = useRef(0)
  useEffect(() => {
    executingRef.current = false
    setExecuting(false)
    return () => { generation.current += 1 }
  }, [isCurrentSession])
  const { addToast } = useUIStore()
  const run = (code: string) => {
    if (executingRef.current || !isCurrentSession()) return
    executingRef.current = true
    setExecuting(true)
    const id = ++generation.current
    void executeSecurityTask(code).then((response) => {
      if (id !== generation.current || !isCurrentSession()) return
      addToast({ type: response.success ? 'success' : 'error', message: response.message || '安全检查未返回执行结果' })
      load(page, pageSize, filters)
    }).catch((reason: unknown) => {
      if (id !== generation.current || !isCurrentSession()) return
      addToast({ type: 'error', message: getApiErrorMessage(reason, '安全检查执行失败') })
      load(page, pageSize, filters)
    }).finally(() => {
      if (id === generation.current && isCurrentSession()) { executingRef.current = false; setExecuting(false) }
    })
  }
  return <section className="vben-card relative flex min-h-0 flex-1 flex-col overflow-hidden">
    {(loading || executing) && <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-white/80 dark:bg-slate-900/80"><Loading text={executing ? '正在执行安全检查并保存审计…' : '正在加载安全任务…'} /></div>}
    <div className="vben-card-header flex flex-wrap justify-between gap-3"><h2 className="vben-card-title"><ShieldCheck className="h-4 w-4" />安全定时任务</h2><button className="btn-ios-secondary" disabled={loading || executing} onClick={() => load(page, pageSize, filters)}><RefreshCw className="h-4 w-4" />刷新安全任务</button></div>
    <div className="vben-card-body max-h-[25%] shrink-0 overflow-y-auto"><p className="text-sm text-slate-500 dark:text-slate-400">安全频率检查每20秒执行，七档阈值在「系统设置 → 安全设置」中管理；时间为北京时间。手动执行完成后可在「安全日志」查看完整统计。</p></div>
    <div className="table-scroll"><table className="table-ios"><thead><tr><th>任务名称</th><th>执行间隔</th><th>运行状态</th><th>真实下次执行</th><th>上次执行</th><th>上次结果</th><th>说明</th><th>操作</th></tr></thead><tbody>
      {error || !data || !data.items.length ? <tr><td colSpan={8} className="py-8 text-center text-slate-500">{error || (!data ? '安全任务尚未加载' : '暂无安全任务')}</td></tr> : data.items.map((task) => <tr key={task.id}><td>{securityLabel(data.dictionaries, 'security_task_name', task.task_code)}</td><td>{task.interval_seconds}秒</td><td>{task.running ? '正在执行' : '等待执行'}</td><td>{formatBeijingDateTime(task.next_run_at)}</td><td>{formatBeijingDateTime(task.last_run_at)}</td><td>{securityLabel(data.dictionaries, 'security_execution_result', task.last_result)}</td><td className="max-w-[300px] break-words">{task.last_message || '-'}</td><td><button className="btn-ios-primary" disabled={loading || executing || task.running} onClick={() => run(task.task_code)}>手动执行</button></td></tr>)}
    </tbody></table></div>
    {data && !error && <div className="max-h-[50%] shrink-0 overflow-y-auto"><Pager page={data.page} pageSize={data.page_size} total={data.total} totalPages={data.pages} loading={loading || executing} onPageChange={(page) => load(page, pageSize, filters)} onPageSizeChange={(size) => load(1, size, filters)} /></div>}
  </section>
}
