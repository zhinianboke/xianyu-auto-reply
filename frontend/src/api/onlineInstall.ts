/** 在线安装接口：统一响应、SSH 测试、幂等提交和增量日志查询。 */
import { get, post } from '@/utils/request'
import { getInstallSession } from '@/utils/onlineInstallSession'

const PREFIX = '/api/v1/online-install'

/** 随机浏览器会话用于隔离安装日志，不依赖用户登录状态。 */
async function installRequestConfig() {
  return { headers: { 'X-Install-Session': await getInstallSession() } }
}

type SSHAuthentication =
  | { auth_method?: 'password'; password: string }
  | { auth_method: 'private_key'; private_key: string; private_key_passphrase?: string }

export type SSHConnection = {
  host: string
  port: number
  username: string
} & SSHAuthentication

export type InstallConnection = SSHConnection

export interface InstallTaskTiming {
  task_id: string
  created_at: string
  finished: boolean
  elapsed_seconds: number
}

export interface InstallLogs extends InstallTaskTiming {
  logs: string[]
  cursor: number
  has_more: boolean
  success: boolean | null
  exit_code: number | null
  message: string
}

export interface InstallResponse<T> {
  success: boolean
  code: number
  message: string
  data: T | null
}

/** 仅验证 SSH 连接，不执行部署脚本或 Docker 检查。 */
export async function testSSHConnection(connection: SSHConnection) {
  return post<InstallResponse<{ server_info: string; response_time: number }>>(`${PREFIX}/test-ssh`, connection, await installRequestConfig())
}

/** 请求 UUID 由页面生成，网络重试复用同一 UUID，避免重复执行安装。 */
export async function startOnlineInstall(taskId: string, connection: InstallConnection) {
  return post<InstallResponse<InstallTaskTiming>>(`${PREFIX}/tasks/${taskId}`, connection, await installRequestConfig())
}

/** 拉取已读取游标之后的真实输出，保持项目统一 90 秒请求超时。 */
export async function getOnlineInstallLogs(taskId: string, cursor: number) {
  return get<InstallResponse<InstallLogs>>(`${PREFIX}/tasks/${taskId}/logs`, { ...await installRequestConfig(), params: { cursor } })
}
