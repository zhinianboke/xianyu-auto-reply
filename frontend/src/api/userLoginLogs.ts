/**
 * 用户登录日志接口
 *
 * 后端路由：GET /api/v1/user-login-logs
 * 仅管理员可访问，返回全部用户的登录记录；
 * 支持关键字、登录方式、时间区间筛选与后端分页（limit/offset）。
 */
import { get } from '@/utils/request'

const API_PREFIX = '/api/v1'

// 登录方式枚举（与后端 user_login_log_service 常量保持一致）
export const LOGIN_METHOD_USERNAME_PASSWORD = 'username_password'
export const LOGIN_METHOD_EMAIL_PASSWORD = 'email_password'
export const LOGIN_METHOD_EMAIL_CODE = 'email_code'

// 登录方式中文名称映射（统一在此维护，页面与其它组件禁止各自硬编码）
export const LOGIN_METHOD_LABELS: Record<string, string> = {
  [LOGIN_METHOD_USERNAME_PASSWORD]: '账号密码',
  [LOGIN_METHOD_EMAIL_PASSWORD]: '邮箱密码',
  [LOGIN_METHOD_EMAIL_CODE]: '邮箱验证码',
}

export interface UserLoginLog {
  id: number
  owner_id: number | null
  login_account: string | null
  login_method: string
  success: boolean
  client_ip: string | null
  result_message: string | null
  created_at: string | null
}

export interface UserLoginLogQuery {
  page?: number
  pageSize?: number
  keyword?: string
  login_method?: string
  start_date?: string
  end_date?: string
}

export interface UserLoginLogResult {
  success: boolean
  data?: UserLoginLog[]
  total?: number
  message?: string
}

// 获取用户登录日志（后端分页）
export const getUserLoginLogs = async (params?: UserLoginLogQuery): Promise<UserLoginLogResult> => {
  const query = new URLSearchParams()
  const page = params?.page || 1
  const pageSize = params?.pageSize || 20
  query.set('limit', String(pageSize))
  query.set('offset', String((page - 1) * pageSize))
  if (params?.keyword) query.set('keyword', params.keyword)
  if (params?.login_method) query.set('login_method', params.login_method)
  if (params?.start_date) query.set('start_date', params.start_date)
  if (params?.end_date) query.set('end_date', params.end_date)

  const result = await get<{
    success: boolean
    message?: string
    data?: UserLoginLog[]
    total?: number
  }>(`${API_PREFIX}/user-login-logs?${query.toString()}`)

  return {
    success: Boolean(result.success),
    data: result.data || [],
    total: result.total,
    message: result.message,
  }
}