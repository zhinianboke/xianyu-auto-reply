/**
 * 定时任务管理 API
 * 
 * 功能：
 * 1. 获取定时任务列表
 * 2. 更新定时任务配置（间隔时间、是否启用）
 */
import { get, put, post } from '@/utils/request'
import type { ApiResponse } from '@/types'
import type { SecurityPage, SecurityTask } from '@/api/securityManagement'
import { isSecurityExecutionResult, isSecurityPage, isSecurityTask, validateResponse } from '@/api/securityManagement'

// API前缀
const ADMIN_PREFIX = '/api/v1/admin'

/** 定时任务数据结构 */
export interface ScheduledTask {
  id: number
  task_code: string
  task_name: string
  interval_seconds: number
  enabled: boolean
  description: string | null
  task_running?: boolean
  created_at: string | null
  updated_at: string | null
}

/** 获取定时任务列表响应 */
export interface ScheduledTasksResponse {
  success: boolean
  message?: string
  data: ScheduledTask[] | null
  scheduler_running?: boolean
}

/** 同表任务保留真实ID，来源用于区分两表可能重合的ID与不同操作。 */
export type ScheduledTaskItem = (ScheduledTask & { task_source: 'scheduled' })
  | (SecurityTask & { task_source: 'security'; task_name: string | null })

const isScheduledTaskItem = (item: unknown) => {
  if (!item || typeof item !== 'object') return false
  const row = item as Record<string, unknown>
  if (!Number.isSafeInteger(row.id) || typeof row.task_code !== 'string'
    || !Number.isSafeInteger(row.interval_seconds)) return false
  if (row.task_source === 'scheduled') return typeof row.task_name === 'string'
    && typeof row.enabled === 'boolean' && (row.description === null || typeof row.description === 'string')
  return row.task_source === 'security' && isSecurityTask(row)
    && (row.task_name === null || typeof row.task_name === 'string')
    && ['next_run_at', 'last_run_at', 'last_result', 'last_message'].every((key) => row[key] === null || typeof row[key] === 'string')
}

/** 原管理接口分页读取两类任务，未带分页的旧调用仍使用原数组响应。 */
export const getScheduledTaskPage = (page: number, pageSize: number) =>
  get<ApiResponse<SecurityPage<ScheduledTaskItem>>>(`${ADMIN_PREFIX}/scheduled-tasks`, {
    params: { page, page_size: pageSize },
  }).then((response) => validateResponse(response, (data) => isSecurityPage(data, isScheduledTaskItem),
    '定时任务响应不完整或格式异常，请重新加载'))

/** 更新定时任务请求参数 */
export interface UpdateScheduledTaskParams {
  interval_seconds?: number
  enabled?: boolean
}

/** 更新定时任务响应 */
export interface UpdateScheduledTaskResponse {
  success: boolean
  message: string
  data: ScheduledTask | SecurityTask | null
}

/**
 * 获取定时任务列表
 */
export async function getScheduledTasks(): Promise<ScheduledTasksResponse> {
  return get<ScheduledTasksResponse>(`${ADMIN_PREFIX}/scheduled-tasks`)
}

/**
 * 更新定时任务配置
 * @param taskCode 任务代码
 * @param params 更新参数
 */
export async function updateScheduledTask(
  taskCode: string,
  params: UpdateScheduledTaskParams
): Promise<UpdateScheduledTaskResponse> {
  const query = new URLSearchParams()
  if (params.interval_seconds !== undefined) {
    query.set('interval_seconds', String(params.interval_seconds))
  }
  if (params.enabled !== undefined) {
    query.set('enabled', String(params.enabled))
  }
  return put<UpdateScheduledTaskResponse>(`${ADMIN_PREFIX}/scheduled-tasks/${encodeURIComponent(taskCode)}?${query.toString()}`)
    .then((response) => {
      validateResponse(response, (data) => taskCode === 'security_frequency' ? isSecurityTask(data)
        : Boolean(data && typeof data === 'object' && isScheduledTaskItem({ ...data, task_source: 'scheduled' })),
      '定时任务未返回完整配置，请重新加载确认保存结果')
      return response
    })
}

/** 手动触发定时任务响应 */
export interface TriggerScheduledTaskResponse {
  success: boolean
  message: string
  code?: number
  data?: unknown
}

/**
 * 手动触发定时任务
 * @param taskCode 任务代码
 */
export async function triggerScheduledTask(
  taskCode: string
): Promise<TriggerScheduledTaskResponse> {
  return post<TriggerScheduledTaskResponse>(`${ADMIN_PREFIX}/scheduled-tasks/${encodeURIComponent(taskCode)}/trigger`)
    .then((response) => {
      validateResponse(response, (data) => taskCode !== 'security_frequency' || isSecurityExecutionResult(data),
        '定时任务未返回完整执行结果，请重新加载并查询执行日志')
      return response
    })
}
