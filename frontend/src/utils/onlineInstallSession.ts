/** 在线安装的访客会话和任务恢复标识；不保存 SSH 密码、私钥、口令或连接配置。 */
import { createRequestId } from '@/utils/uuid'

const SESSION_KEY = 'online-install-session'
const TASK_KEY = 'online-install-task'

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

/** 提交前同时确认访客会话与任务标识可持久保存，避免无法恢复已提交的任务。 */
export const rememberInstallTask = (id: string) => accessStorage(storage => {
  sessionId(storage)
  storage.setItem(TASK_KEY, id)
})

/** 仅移除当前任务标识，不影响访客会话或服务器上的安装任务。 */
export const forgetInstallTask = () => accessStorage(storage => storage.removeItem(TASK_KEY))
