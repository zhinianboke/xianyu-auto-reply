/** 管理员注册日志接口：统一响应、后端分页，操作与结果名称来自数据库字典。 */
import type { ApiResponse } from '@/types'
import { get } from '@/utils/request'

export interface RegistrationLog {
  id: number
  owner_id: number | null
  owner_username: string | null
  username: string | null
  email: string | null
  operation: string | null
  success: boolean | null
  client_ip: string | null
  message: string | null
  created_at: string | null
}

export interface RegistrationLogOption {
  value: string
  label: string
  enabled: boolean
}

export interface RegistrationLogFilters {
  keyword?: string
  client_ip?: string
  operation?: string
  status?: string
  start_date?: string
  end_date?: string
}

export interface RegistrationLogQuery extends RegistrationLogFilters {
  page?: number
  page_size?: number
}

export interface RegistrationLogPage {
  items: RegistrationLog[]
  total: number
  page: number
  page_size: number
  pages: number
  operation_options: RegistrationLogOption[]
  status_options: RegistrationLogOption[]
}

export interface RegistrationLogResponse extends ApiResponse<RegistrationLogPage> {
  message: string
}

/** 获取真实注册审计与字典，不将失败响应或缺失数据转换为成功空列表。 */
export const getRegistrationLogs = (params: RegistrationLogQuery = {}): Promise<RegistrationLogResponse> => {
  const query = new URLSearchParams()
  query.set('page', String(params.page ?? 1))
  query.set('page_size', String(params.page_size ?? 20))
  for (const key of ['keyword', 'client_ip', 'operation', 'status', 'start_date', 'end_date'] as const) {
    const value = params[key]?.trim()
    if (value) query.set(key, value)
  }
  return get<RegistrationLogResponse>(`/api/v1/registration-logs?${query.toString()}`)
}
