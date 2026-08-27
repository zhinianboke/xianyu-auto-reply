/**
 * 定时任务管理 API
 * 
 * 功能：
 * 1. 获取定时任务列表
 * 2. 更新定时任务配置（间隔时间、是否启用）
 */
import { get, put, post } from '@/utils/request'

// API前缀
const ADMIN_PREFIX = '/api/v1/admin'

/** 定时任务数据结构 */
export interface ScheduledTask {
  id: number
  task_code: string
  task_name: string
  interval_seconds: number
  enabled: boolean
  run_start_time: string
  run_end_time: string
  description: string | null
  task_running: boolean
  created_at: string | null
  updated_at: string | null
}

/** 获取定时任务列表响应 */
export interface ScheduledTasksResponse {
  success: boolean
  data: ScheduledTask[]
  scheduler_running: boolean
}

/** 更新定时任务请求参数 */
export interface UpdateScheduledTaskParams {
  interval_seconds?: number
  enabled?: boolean
  run_start_time?: string
  run_end_time?: string
}

/** 更新定时任务响应 */
export interface UpdateScheduledTaskResponse {
  success: boolean
  message: string
  data: ScheduledTask
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
  if (params.run_start_time !== undefined) {
    query.set('run_start_time', params.run_start_time)
  }
  if (params.run_end_time !== undefined) {
    query.set('run_end_time', params.run_end_time)
  }
  return put<UpdateScheduledTaskResponse>(`${ADMIN_PREFIX}/scheduled-tasks/${taskCode}?${query.toString()}`)
}

/** 手动触发定时任务响应 */
export interface TriggerScheduledTaskResponse {
  success: boolean
  message: string
}

/**
 * 手动触发定时任务
 * @param taskCode 任务代码
 */
export async function triggerScheduledTask(
  taskCode: string
): Promise<TriggerScheduledTaskResponse> {
  return post<TriggerScheduledTaskResponse>(`${ADMIN_PREFIX}/scheduled-tasks/${taskCode}/trigger`)
}
