import { get, post } from '@/utils/request'
import type { ApiResponse } from '@/types'

// 系统管理 - 服务重启 API 前缀
const SYSTEM_CONTROL_PREFIX = '/api/v1/system-control'

// 可重启的服务标识
export type ServiceKey = 'backend-web' | 'websocket' | 'scheduler'

// 单个服务状态
export interface ServiceStatusItem {
  key: ServiceKey
  label: string
  port: number
  online: boolean
}

// 服务状态查询响应数据
export interface ServicesStatusData {
  runtime: string
  services: ServiceStatusItem[]
}

/**
 * 查询三个服务的在线状态
 */
export const getServicesStatus = (): Promise<ApiResponse<ServicesStatusData>> => {
  return get<ApiResponse<ServicesStatusData>>(`${SYSTEM_CONTROL_PREFIX}/status`)
}

/**
 * 重启指定服务（先杀端口进程再重新启动，自动适配运行环境）
 * @param key 服务标识：backend-web / websocket / scheduler
 */
export const restartService = (key: ServiceKey): Promise<ApiResponse<{ mode: string }>> => {
  return post<ApiResponse<{ mode: string }>>(`${SYSTEM_CONTROL_PREFIX}/restart/${key}`)
}
