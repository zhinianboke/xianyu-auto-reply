import { get, post, del } from '@/utils/request'
import type { ApiResponse, User } from '@/types'

// ========== 用户管理 ==========

// 获取用户列表
export const getUsers = async (): Promise<{ success: boolean; data?: User[] }> => {
  const result = await get<{ users: Array<{
    id: number
    username: string
    email?: string
    is_admin: boolean
    cookie_count?: number
    card_count?: number
  }> }>('/admin/users')
  // 后端返回 { users: [...] } 格式，转换字段名
  const users: User[] = (result.users || []).map(u => ({
    user_id: u.id,
    username: u.username,
    email: u.email,
    is_admin: u.is_admin,
  }))
  return { success: true, data: users }
}

// TODO: 后端暂未实现 POST /admin/users 接口
// export const addUser = ...

// TODO: 后端暂未实现 PUT /admin/users/{userId} 接口
// export const updateUser = ...

// 删除用户
export const deleteUser = (userId: number): Promise<ApiResponse> => {
  return del(`/admin/users/${userId}`)
}

// ========== 系统日志 ==========

export interface SystemLog {
  id: string
  level: 'info' | 'warning' | 'error'
  message: string
  module: string
  created_at: string
}

// 获取系统日志
export const getSystemLogs = async (params?: { page?: number; limit?: number; level?: string }): Promise<{ success: boolean; data?: SystemLog[]; total?: number }> => {
  const query = new URLSearchParams()
  if (params?.page) query.set('page', String(params.page))
  if (params?.limit) query.set('lines', String(params.limit))  // 后端用 lines 参数
  if (params?.level) query.set('level', params.level.toUpperCase())
  const result = await get<{ logs?: string[]; total?: number }>(`/admin/logs?${query.toString()}`)
  // 后端返回 { logs: [...] } 格式，转换为 SystemLog 数组
  const logs: SystemLog[] = (result.logs || []).map((log, index) => ({
    id: String(index),
    level: log.includes('ERROR') ? 'error' : log.includes('WARNING') ? 'warning' : 'info',
    message: log,
    module: 'system',
    created_at: new Date().toISOString(),
  }))
  return { success: true, data: logs, total: result.total }
}

// 清空系统日志
export const clearSystemLogs = (): Promise<ApiResponse> => {
  return post('/logs/clear')
}

// ========== 风控日志 ==========

export interface RiskLog {
  id: string
  cookie_id: string
  risk_type: string
  message: string
  created_at: string
}

// 获取风控日志
export const getRiskLogs = async (params?: { page?: number; limit?: number; cookie_id?: string }): Promise<{ success: boolean; data?: RiskLog[]; total?: number }> => {
  const query = new URLSearchParams()
  if (params?.page) query.set('page', String(params.page))
  if (params?.limit) query.set('limit', String(params.limit))
  if (params?.cookie_id) query.set('cookie_id', params.cookie_id)
  const result = await get<{ success: boolean; data?: Array<{
    id: number
    cookie_id: string
    event_type: string
    event_description: string
    processing_result: string
    processing_status: string
    error_message: string | null
    created_at: string
    updated_at: string
    cookie_name: string
  }>; total?: number }>(`/admin/risk-control-logs?${query.toString()}`)
  // 转换后端格式为前端格式
  const logs: RiskLog[] = (result.data || []).map(item => ({
    id: String(item.id),
    cookie_id: item.cookie_id || item.cookie_name,
    risk_type: item.event_type,
    message: item.event_description || item.processing_result,
    created_at: item.created_at,
  }))
  return { success: true, data: logs, total: result.total }
}

// 清空风控日志 - 后端暂未实现批量删除接口
export const clearRiskLogs = async (): Promise<ApiResponse> => {
  // 后端只有单条删除接口 DELETE /risk-control-logs/{log_id}
  // 暂时返回提示信息
  return { success: false, message: '后端暂未实现批量清空风控日志接口' }
}

// ========== 数据管理 ==========

// 导出数据 - 后端只支持导出整个数据库
export const exportData = async (type: string): Promise<Blob> => {
  // 后端 /admin/backup/download 不支持 type 参数，只能导出整个数据库
  // 如果需要导出特定表数据，可以使用 /admin/data/{table_name} 获取后转换为 JSON
  if (type === 'all') {
    const token = localStorage.getItem('auth_token')
    const response = await fetch(`/admin/backup/download?token=${token}`)
    if (!response.ok) throw new Error('导出失败')
    return response.blob()
  }
  
  // 导出特定表数据
  const tableMap: Record<string, string> = {
    accounts: 'cookies',
    keywords: 'keywords',
    items: 'item_info',
    orders: 'orders',
    cards: 'cards',
  }
  const tableName = tableMap[type] || type
  const data = await get<{ data: unknown[] }>(`/admin/data/${tableName}`)
  const jsonStr = JSON.stringify(data.data || [], null, 2)
  return new Blob([jsonStr], { type: 'application/json' })
}

// 导入数据
export const importData = (formData: FormData): Promise<ApiResponse> => {
  return post('/admin/backup/upload', formData)
}

// 清理数据
export const cleanupData = (type: string): Promise<ApiResponse> => {
  // 清理类型映射表名
  const tableMap: Record<string, string> = {
    logs: 'logs',
    orders: 'orders',
    cards_used: 'cards',
    all_data: 'all',
  }
  const tableName = tableMap[type] || type
  
  // 如果是清空日志，使用通用接口
  if (type === 'logs') {
    return post('/logs/clear')
  }
  
  return del(`/admin/data/${tableName}`)
}

// 获取表数据
export interface TableData {
  success: boolean
  data: Record<string, unknown>[]
  columns: string[]
  count: number
}

export const getTableData = async (tableName: string): Promise<TableData> => {
  return get<TableData>(`/admin/data/${tableName}`)
}

// 清空表数据
export const clearTableData = (tableName: string): Promise<ApiResponse> => {
  return del(`/admin/data/${tableName}`)
}

// 删除表记录
export const deleteTableRecord = (tableName: string, recordId: string): Promise<ApiResponse> => {
  return del(`/admin/data/${tableName}/${recordId}`)
}
