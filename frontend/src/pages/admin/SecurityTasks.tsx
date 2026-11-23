/** 原定时任务同表中的安全任务行：真实调度状态与数据库中文结果。 */
import { Link } from 'react-router-dom'
import { securityLabel, type SecurityDictionaries, type SecurityTask } from '@/api/securityManagement'
import { formatBeijingDateTime } from '@/utils/date'

export function SecurityTaskRow({ task, dictionaries, busy, run, update }: {
  task: SecurityTask; dictionaries: SecurityDictionaries; busy: boolean; run: (code: string) => void
  update: (code: string, params: { enabled: boolean }) => void
}) {
  return <tr>
    <td className="font-medium text-slate-900 dark:text-white">{securityLabel(dictionaries, 'security_task_name', task.task_code)}</td>
    <td className="text-slate-500 dark:text-slate-400 font-mono text-sm">{task.task_code}</td>
    <td><span className="font-medium">{task.interval_seconds}</span><span className="ml-2 text-sm text-slate-500">秒</span></td>
    <td><span className={task.enabled ? 'badge-success' : 'badge-gray'}>{task.enabled ? '已启用' : '已停止'}</span>
      {task.running && <span className="badge-primary ml-2">正在执行</span>}</td>
    <td className="max-w-sm break-words text-sm text-slate-500 dark:text-slate-400">
      <p>下次执行：{formatBeijingDateTime(task.next_run_at)}</p>
      <p>上次执行：{formatBeijingDateTime(task.last_run_at)}</p>
      <p>上次结果：{securityLabel(dictionaries, 'security_execution_result', task.last_result)}</p>
      {task.last_message && <p>{task.last_message}</p>}
      <p>频率阈值在「系统设置 → 安全设置」中配置。</p>
      <p>默认停止；停止后可手动检查，已开始的执行会完成并保存审计。</p>
    </td>
    <td><div className="flex flex-wrap items-center gap-2">
      <button className="btn-ios-primary" disabled={busy || task.running} onClick={() => run(task.task_code)}>手动执行</button>
      <button className="btn-ios-secondary" disabled={busy}
        onClick={() => update(task.task_code, { enabled: !task.enabled })}>{task.enabled ? '停止' : '启用'}</button>
      <Link className="btn-ios-secondary" to="/admin/security-logs">查看日志</Link>
    </div></td>
  </tr>
}
