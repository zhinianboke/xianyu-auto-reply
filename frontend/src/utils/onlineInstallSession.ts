/** 在线安装访客会话、任务标识及最终结果恢复；不保存 SSH 凭据或连接配置。 */
import type { InstallLogs } from '@/api/onlineInstall'
import { createRequestId } from '@/utils/uuid'

const SESSION_KEY = 'online-install-session'
const TASK_KEY = 'online-install-task'
const RESULT_KEY = 'online-install-result'

/** 异步访问会话存储，浏览器禁止存储时给出可展示的中文错误。 */
function accessStorage<T>(action: (storage: Storage) => T): Promise<T> {
  return Promise.resolve().then(() => action(sessionStorage)).catch(() => {
    throw new Error('浏览器会话存储不可用，请允许此网站使用存储后重试')
  })
}

/** 在同一次存储操作中获取或创建随机访客标识，保持请求与日志范围一致。 */
function sessionId(storage: Storage): string {
  let id = storage.getItem(SESSION_KEY)
  if (!id) {
    id = createRequestId()
    storage.setItem(SESSION_KEY, id)
  }
  return id
}

export const getInstallSession = () => accessStorage(sessionId)
export const readInstallTask = () => accessStorage(storage => storage.getItem(TASK_KEY))

/** 读取与当前任务匹配的最终结果；不存在时向后端确认，损坏时明确报错。 */
export async function readInstallResult(taskId: string): Promise<InstallLogs | null> {
  const raw = await accessStorage(storage => storage.getItem(TASK_KEY) === taskId ? storage.getItem(RESULT_KEY) : null)
  if (!raw) return null
  let result: InstallLogs
  try {
    result = JSON.parse(raw)
    if (!result || result.task_id !== taskId || result.finished !== true || result.has_more !== false ||
      typeof result.created_at !== 'string' || typeof result.message !== 'string' ||
      typeof result.elapsed_seconds !== 'number' || !Number.isFinite(result.elapsed_seconds) || result.elapsed_seconds < 0 ||
      !Number.isInteger(result.cursor) || result.cursor < 0 || typeof result.success !== 'boolean' ||
      (result.exit_code !== null && !Number.isInteger(result.exit_code)) ||
      !Array.isArray(result.logs) || result.logs.length !== 1 || typeof result.logs[0] !== 'string') {
      throw new Error('invalid result')
    }
  } catch {
    throw new Error('安装结果缓存无效，正在向服务器重新确认任务状态')
  }
  return result
}

/** 仅保存任务的真实最终结果、最终日志和固定耗时；旧请求不能覆盖另一任务。 */
export const rememberInstallResult = (result: InstallLogs, finalLog: string) => accessStorage(storage => {
  if (!result.finished || storage.getItem(TASK_KEY) !== result.task_id) return
  const completed: InstallLogs = {
    task_id: result.task_id, created_at: result.created_at, finished: true,
    elapsed_seconds: result.elapsed_seconds, cursor: result.cursor, has_more: false,
    success: result.success, exit_code: result.exit_code, message: result.message, logs: [finalLog],
  }
  storage.setItem(RESULT_KEY, JSON.stringify(completed))
})

/** 提交前同时确认访客会话与任务标识可持久保存，避免无法恢复已提交的任务。 */
export const rememberInstallTask = (id: string) => accessStorage(storage => {
  sessionId(storage)
  if (storage.getItem(TASK_KEY) !== id) storage.removeItem(RESULT_KEY)
  storage.setItem(TASK_KEY, id)
})

/** 移除浏览器的当前任务标识和最终结果，不影响访客会话、服务器任务或历史日志。 */
export const forgetInstallTask = () => accessStorage(storage => {
  storage.removeItem(TASK_KEY)
  storage.removeItem(RESULT_KEY)
})
