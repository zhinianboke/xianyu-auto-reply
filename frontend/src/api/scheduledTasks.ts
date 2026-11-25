/**
 * 定时任务管理 API
 * 
 * 功能：
 * 1. 获取定时任务列表
 * 2. 更新定时任务配置（间隔时间、是否启用）
 */
import { get, put, post } from '@/utils/request'
import type { ApiResponse } from '@/types'
import type { SecurityPage } from '@/api/securityManagement'
import { isSecurityPage, validateResponse } from '@/api/securityManagement'

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

/** 所有任务共用原任务表配置字段。 */
export type ScheduledTaskItem = ScheduledTask

const isScheduledTaskItem = (item: unknown) => {
  if (!item || typeof item !== 'object') return false
  const row = item as Record<string, unknown>
  if (!Number.isSafeInteger(row.id) || typeof row.task_code !== 'string'
    || !Number.isSafeInteger(row.interval_seconds)) return false
  return typeof row.task_name === 'string' && typeof row.enabled === 'boolean'
    && (row.description === null || typeof row.description === 'string')
}

/** 保存响应使用原配置字段，执行状态由刷新列表取得。 */
const isScheduledTaskConfig = (item: unknown) => {
  if (!item || typeof item !== 'object') return false
  const row = item as Record<string, unknown>
  return Number.isSafeInteger(row.id) && typeof row.task_name === 'string' && typeof row.task_code === 'string'
    && typeof row.enabled === 'boolean' && Number.isSafeInteger(row.interval_seconds)
}

/** 原管理接口统一分页读取，未带分页的旧调用仍使用原数组响应。 */
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
  data: ScheduledTask | null
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
      validateResponse(response, isScheduledTaskConfig,
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
      validateResponse(response, (data) => Boolean(data && typeof data === 'object'),
        '定时任务未返回完整执行结果，请重新加载并查询执行日志')
      return response
    })
}
