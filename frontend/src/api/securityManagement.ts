/** 安全日志与任务管理接口，保留后端中文消息、真实统计和调度时间。 */
import type { ApiResponse } from '@/types'
import { get, post } from '@/utils/request'
import { isApiResponse } from '@/utils/apiResponse'

export interface SecurityOption { value: string; label: string; enabled: boolean }
export type SecurityDictionaries = Record<string, SecurityOption[]>
export interface SecurityLog {
  id: number; execution_id: string; owner_id: number | null; execution_method: string
  result: string; message: string; added_suffixes: string; added_ips: string
  started_at: string | null; finished_at: string | null; details?: unknown
}
export interface SecurityTask {
  id: number; task_code: string; interval_seconds: number; next_run_at: string | null
  last_run_at: string | null; last_result: string | null; last_message: string | null
  enabled: boolean; running: boolean; execution_id: string | null; lease_expires_at: string | null
}
export interface SecurityPage<T> {
  items: T[]; total: number; page: number; page_size: number; pages: number
  dictionaries: SecurityDictionaries
}
export interface SecurityFilters {
  keyword?: string; added_ip?: string; execution_method?: string; result?: string
  start_date?: string; end_date?: string
}

/** 校验字典及列表字段，异常响应不得进入表格渲染或被当成执行成功。 */
const isRecord = (data: unknown): data is Record<string, unknown> =>
  Boolean(data && typeof data === 'object' && !Array.isArray(data))
const isText = (value: unknown) => value === null || typeof value === 'string'
const isId = (value: unknown) => Number.isSafeInteger(value) && Number(value) > 0
const isDictionaries = (data: unknown) => isRecord(data)
  && ['security_execution_method', 'security_execution_result', 'security_task_name'].every((type) =>
    Array.isArray(data[type]) && data[type].every((option: unknown) => isRecord(option)
      && typeof option.value === 'string' && typeof option.label === 'string' && typeof option.enabled === 'boolean'))
const isLog = (data: unknown) => isRecord(data) && isId(data.id)
  && (data.owner_id === null || isId(data.owner_id))
  && ['execution_id', 'execution_method', 'result', 'message', 'added_suffixes', 'added_ips', 'started_at', 'finished_at']
    .every((key) => isText(data[key]))
export const isSecurityTask = (data: unknown) => isRecord(data) && isId(data.id) && typeof data.task_code === 'string'
  && typeof data.enabled === 'boolean'
  && Number.isSafeInteger(data.interval_seconds) && Number(data.interval_seconds) > 0 && typeof data.running === 'boolean'
  && ['next_run_at', 'last_run_at', 'last_result', 'last_message', 'execution_id', 'lease_expires_at']
    .every((key) => isText(data[key]))
/** 执行成功必须包含已提交审计编号与真实结果，供两种兼容执行接口共用。 */
export const isSecurityExecutionResult = (data: unknown) => isRecord(data)
  && isId(data.id) && typeof data.execution_id === 'string' && typeof data.result === 'string'
  && typeof data.message === 'string' && ['started_at', 'finished_at'].every((key) => typeof data[key] === 'string')
  && ['added_suffixes', 'added_ips'].every((key) => Array.isArray(data[key])
    && data[key].every((item: unknown) => typeof item === 'string'))
export const isSecurityPage = (data: unknown, isItem: (item: unknown) => boolean) => isRecord(data)
  && Array.isArray(data.items) && data.items.every(isItem) && isDictionaries(data.dictionaries)
  && ['total', 'pages'].every((key) => Number.isSafeInteger(data[key]) && Number(data[key]) >= 0)
  && isId(data.page) && Number.isSafeInteger(data.page_size) && [10, 20, 50, 100].includes(Number(data.page_size))
export const validateResponse = <T>(response: ApiResponse<T>, isData: (data: unknown) => boolean,
  message = '安全管理响应不完整或格式异常，请重新加载'): ApiResponse<T> => {
  if (!isApiResponse(response) || (response.success && !isData(response.data))) {
    throw new Error(message)
  }
  return response
}

export const getSecurityLogs = (page: number, pageSize: number, filters: SecurityFilters) =>
  get<ApiResponse<SecurityPage<SecurityLog>>>('/api/v1/security-logs', { params: { page, page_size: pageSize, ...filters } })
    .then((response) => validateResponse(response, (data) => isSecurityPage(data, isLog)))
export const getSecurityLog = (id: number) => get<ApiResponse<SecurityLog>>(`/api/v1/security-logs/${id}`)
  .then((response) => validateResponse(response, (data) => isLog(data) && isRecord(data)
    && Object.prototype.hasOwnProperty.call(data, 'details') && isDictionaries(data.dictionaries)))
export const getSecurityTasks = (page: number, pageSize: number) =>
  get<ApiResponse<SecurityPage<SecurityTask>>>('/api/v1/security-tasks', { params: { page, page_size: pageSize } })
    .then((response) => validateResponse(response, (data) => isSecurityPage(data, isSecurityTask)))
export const executeSecurityTask = (code: string) =>
  post<ApiResponse<unknown>>(`/api/v1/security-tasks/${encodeURIComponent(code)}/execute`)
    .then((response) => validateResponse(response, isSecurityExecutionResult))

/** 字典名称来自数据库；缺失名称显示空值，不自行推测。 */
export const securityLabel = (dictionaries: SecurityDictionaries, type: string, value: string | null) =>
  dictionaries[type]?.find((option) => option.value === value)?.label || '-'
