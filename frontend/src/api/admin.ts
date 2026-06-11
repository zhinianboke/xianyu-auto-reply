import { del, get, post, put } from '@/utils/request'
import type { ApiResponse, User, UserRole, UserStatus } from '@/types'

// API前缀
const ADMIN_PREFIX = '/api/v1/admin'
const API_PREFIX = '/api/v1'

// ========== 用户管理 ==========

export interface AdminUserApiItem {
  id: number
  username: string
  email?: string
  phone?: string
  role?: UserRole
  status?: UserStatus
  is_admin: boolean
  account_limit?: number | null
  cookie_count?: number
  card_count?: number
}

export interface CreateAdminUserPayload {
  username: string
  email: string
  phone?: string
  password: string
  role: UserRole
  status: UserStatus
  account_limit: number | null
}

export interface UpdateAdminUserPayload {
  username?: string
  email?: string
  phone?: string
  password?: string
  role?: UserRole
  status?: UserStatus
  account_limit?: number | null
}

const mapAdminUser = (user: AdminUserApiItem): User => ({
  user_id: user.id,
  username: user.username,
  email: user.email,
  phone: user.phone,
  role: user.role,
  status: user.status,
  is_admin: user.is_admin,
  account_limit: user.account_limit,
})

// 获取用户列表
export const getUsers = async (params?: { page?: number; pageSize?: number }): Promise<{ success: boolean; data?: User[]; total?: number; message?: string }> => {
  const query = new URLSearchParams()
  const page = params?.page || 1
  const pageSize = params?.pageSize || 20
  const offset = (page - 1) * pageSize
  query.set('limit', String(pageSize))
  query.set('offset', String(offset))

  const result = await get<{ success: boolean; message?: string; users?: AdminUserApiItem[]; total?: number }>(`${ADMIN_PREFIX}/users?${query.toString()}`)
  if (!result.success) {
    return { success: false, data: [], total: result.total, message: result.message }
  }
  const users: User[] = (result.users || []).map(mapAdminUser)
  return { success: true, data: users, total: result.total, message: result.message }
}

export const addUser = (payload: CreateAdminUserPayload): Promise<ApiResponse<{ user: AdminUserApiItem }>> => {
  return post(`${ADMIN_PREFIX}/users`, payload)
}

export const updateUser = (userId: number, payload: UpdateAdminUserPayload): Promise<ApiResponse<{ user: AdminUserApiItem }>> => {
  return put(`${ADMIN_PREFIX}/users/${userId}`, payload)
}

// 停用用户
export const deleteUser = (userId: number): Promise<ApiResponse> => {
  return del(`${ADMIN_PREFIX}/users/${userId}`)
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
  const result = await get<{ logs?: string[]; total?: number }>(`${ADMIN_PREFIX}/logs?${query.toString()}`)
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
  return post(`${ADMIN_PREFIX}/logs/clear`)
}

// ========== 风控日志 ==========

export interface RiskLog {
  id: string
  cookie_id: string
  risk_type: string
  message: string
  processing_result: string
  processing_status: string
  captcha_engine: string | null
  error_message: string | null
  created_at: string
  updated_at: string
}

// 获取风控日志
export const getRiskLogs = async (params?: { 
  page?: number
  pageSize?: number
  cookie_id?: string
  start_date?: string
  end_date?: string
  processing_status?: string
}): Promise<{ success: boolean; data?: RiskLog[]; total?: number; message?: string }> => {
  const query = new URLSearchParams()
  const page = params?.page || 1
  const pageSize = params?.pageSize || 20
  const offset = (page - 1) * pageSize
  query.set('limit', String(pageSize))
  query.set('offset', String(offset))
  if (params?.cookie_id) query.set('cookie_id', params.cookie_id)
  if (params?.start_date) query.set('start_date', params.start_date)
  if (params?.end_date) query.set('end_date', params.end_date)
  if (params?.processing_status) query.set('processing_status', params.processing_status)
  const result = await get<{ success: boolean; message?: string; data?: Array<{
    id: number
    cookie_id: string
    event_type: string
    event_description: string
    processing_result: string
    processing_status: string
    captcha_engine: string | null
    error_message: string | null
    created_at: string
    updated_at: string
    cookie_name: string
  }>; total?: number }>(`${API_PREFIX}/risk-control-logs?${query.toString()}`)
  // 转换后端格式为前端格式
  const logs: RiskLog[] = (result.data || []).map(item => ({
    id: String(item.id),
    cookie_id: item.cookie_id || item.cookie_name,
    risk_type: item.event_type,
    message: item.event_description || '',
    processing_result: item.processing_result || '',
    processing_status: item.processing_status || '',
    captcha_engine: item.captcha_engine ?? null,
    error_message: item.error_message,
    created_at: item.created_at,
    updated_at: item.updated_at,
  }))
  return { success: Boolean(result.success), data: logs, total: result.total, message: result.message }
}

// 清空风控日志
export const clearRiskLogs = async (cookieId?: string): Promise<ApiResponse> => {
  const query = cookieId ? `?cookie_id=${cookieId}` : ''
  return del(`${ADMIN_PREFIX}/risk-control-logs${query}`)
}

// ========== 账号登录日志 ==========

export interface AccountLoginLog {
  id: number
  cookie_id: string
  username: string | null
  trigger_reason: string | null
  login_status: string
  failure_reason: string | null
  error_message: string | null
  updated_cookie_names: string | null
  duration_ms: number | null
  account_status: string
  disable_reason: string | null
  created_at: string
}

// 获取账号登录日志
export const getAccountLoginLogs = async (params?: {
  page?: number
  pageSize?: number
  cookie_id?: string
  start_date?: string
  end_date?: string
  login_status?: string
}): Promise<{ success: boolean; data?: AccountLoginLog[]; total?: number; message?: string }> => {
  const query = new URLSearchParams()
  const page = params?.page || 1
  const pageSize = params?.pageSize || 20
  const offset = (page - 1) * pageSize
  query.set('limit', String(pageSize))
  query.set('offset', String(offset))
  if (params?.cookie_id) query.set('cookie_id', params.cookie_id)
  if (params?.start_date) query.set('start_date', params.start_date)
  if (params?.end_date) query.set('end_date', params.end_date)
  if (params?.login_status) query.set('login_status', params.login_status)
  const result = await get<{
    success: boolean
    message?: string
    data?: AccountLoginLog[]
    total?: number
  }>(`${API_PREFIX}/account-login-logs?${query.toString()}`)
  return {
    success: Boolean(result.success),
    data: result.data || [],
    total: result.total,
    message: result.message,
  }
}

// 清理账号登录日志
// - 不传 days  => 清空全部
// - 传 days=30 => 仅删除 30 天前的日志（保留近 30 天）
// - cookieId   => 仅清理该账号的日志
export const clearAccountLoginLogs = async (params?: {
  days?: number
  cookieId?: string
}): Promise<ApiResponse> => {
  const query = new URLSearchParams()
  if (params?.days !== undefined && params.days !== null) query.set('days', String(params.days))
  if (params?.cookieId) query.set('cookie_id', params.cookieId)
  const qs = query.toString()
  return del(`${ADMIN_PREFIX}/account-login-logs${qs ? `?${qs}` : ''}`)
}

// ========== 数据库备份日志 ==========

export interface DbBackupLog {
  id: number
  status: string
  file_name: string | null
  file_path: string | null
  file_size: number | null
  table_count: number | null
  total_rows: number | null
  duration_ms: number | null
  error_message: string | null
  downloadable: boolean
  created_at: string
}

// 获取数据库备份日志
export const getDbBackupLogs = async (params?: {
  page?: number
  pageSize?: number
  status?: string
  start_date?: string
  end_date?: string
}): Promise<{ success: boolean; data?: DbBackupLog[]; total?: number; message?: string }> => {
  const query = new URLSearchParams()
  const page = params?.page || 1
  const pageSize = params?.pageSize || 20
  const offset = (page - 1) * pageSize
  query.set('limit', String(pageSize))
  query.set('offset', String(offset))
  if (params?.status) query.set('status', params.status)
  if (params?.start_date) query.set('start_date', params.start_date)
  if (params?.end_date) query.set('end_date', params.end_date)
  const result = await get<{
    success: boolean
    message?: string
    data?: DbBackupLog[]
    total?: number
  }>(`${API_PREFIX}/db-backup-logs?${query.toString()}`)
  return {
    success: Boolean(result.success),
    data: result.data || [],
    total: result.total,
    message: result.message,
  }
}

// 下载数据库备份文件（通过 fetch 获取 Blob，便于携带鉴权头并处理错误）
export const downloadDbBackupFile = async (
  logId: number,
): Promise<{ success: boolean; blob?: Blob; filename?: string; message?: string }> => {
  const token = localStorage.getItem('auth_token')
  const response = await fetch(`${API_PREFIX}/db-backup-logs/${logId}/download`, {
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
  })

  const contentType = response.headers.get('content-type') || ''
  // 文件不存在时后端返回 JSON（success=false），否则返回二进制文件流
  if (contentType.includes('application/json')) {
    const data = await response.json()
    return { success: false, message: data?.message || '下载失败' }
  }

  const blob = await response.blob()
  // 从响应头解析文件名
  const disposition = response.headers.get('content-disposition') || ''
  const match = disposition.match(/filename\*?=(?:UTF-8'')?["']?([^"';]+)["']?/i)
  const filename = match ? decodeURIComponent(match[1]) : `backup_${logId}.sql.gz`
  return { success: true, blob, filename }
}

// ========== 数据管理 ==========

// 获取表数据
export interface TableData {
  success: boolean
  data: Record<string, unknown>[]
  columns: string[]
  count: number
}

export const getTableData = async (tableName: string): Promise<TableData> => {
  return get<TableData>(`${ADMIN_PREFIX}/data/${tableName}`)
}

// 清空表数据
export const clearTableData = (tableName: string): Promise<ApiResponse> => {
  return del(`${ADMIN_PREFIX}/data/${tableName}`)
}

// ========== 管理员统计 ==========

export interface AdminStats {
  total_users: number
  total_cookies: number
  total_cards: number
  total_keywords: number
  total_orders: number
  today_reply_count: number
  yesterday_reply_count: number
  active_cookies: number
  password_configured: number  // 已配置账号密码数
  current_user_account_limit: number | null
  current_user_used_account_count: number
  current_user_remaining_account_count: number | null
}

export interface TodayStats {
  today_users: number
  today_accounts: number
  today_orders: number
  today_shipped: number
  today_pending: number
  today_amount: number
  today_agent_orders: number
}

// 获取管理员统计数据
export const getAdminStats = async (): Promise<{ success: boolean; data?: AdminStats }> => {
  try {
    const data = await get<AdminStats & { success: boolean }>(`${ADMIN_PREFIX}/stats`)
    return { success: true, data }
  } catch {
    return { success: false }
  }
}

// 获取今日统计数据（管理员专用）
export const getTodayStats = async (): Promise<{ success: boolean; data?: TodayStats }> => {
  try {
    const data = await get<TodayStats & { success: boolean }>(`${ADMIN_PREFIX}/stats/today`)
    return { success: true, data }
  } catch {
    return { success: false }
  }
}
