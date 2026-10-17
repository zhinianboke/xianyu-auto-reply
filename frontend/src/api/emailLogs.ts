/**
 * 邮件发送日志接口
 *
 * 后端路由：
 * - GET /api/v1/email-logs         仅管理员，后端分页（page / page_size）
 * - GET /api/v1/email-logs/options 仅管理员，返回触发操作 / 发送结果枚举及中文名称
 *
 * 说明：枚举中文名称统一来自后端数据字典接口，前端禁止硬编码映射。
 */
import { get } from '@/utils/request'

const API_PREFIX = '/api/v1'

export interface EmailLog {
  id: number
  owner_id: number | null
  recipient_email: string
  trigger_operation: string
  success: boolean
  client_ip: string | null
  result_message: string | null
  created_at: string | null
}

export interface EmailLogQuery {
  page?: number
  page_size?: number
  recipient_email?: string
  trigger_operation?: string
  send_result?: string
  start_date?: string
  end_date?: string
}

/** 枚举选项（中文名称由后端数据字典提供） */
export interface EmailLogOption {
  value: string
  label: string
}

export interface EmailLogOptions {
  trigger_operations: EmailLogOption[]
  send_results: EmailLogOption[]
}

/** 后端分页返回体 */
export interface EmailLogPage {
  list: EmailLog[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface EmailLogListResult {
  success: boolean
  message?: string
  data?: EmailLogPage
}

export interface EmailLogOptionsResult {
  success: boolean
  message?: string
  data?: EmailLogOptions
}

/** 获取邮件发送日志（后端分页，支持指定页码 page） */
export const getEmailLogs = async (params?: EmailLogQuery): Promise<EmailLogListResult> => {
  const query = new URLSearchParams()
  query.set('page', String(params?.page || 1))
  query.set('page_size', String(params?.page_size || 20))
  if (params?.recipient_email) query.set('recipient_email', params.recipient_email)
  if (params?.trigger_operation) query.set('trigger_operation', params.trigger_operation)
  if (params?.send_result) query.set('send_result', params.send_result)
  if (params?.start_date) query.set('start_date', params.start_date)
  if (params?.end_date) query.set('end_date', params.end_date)

  const result = await get<EmailLogListResult>(`${API_PREFIX}/email-logs?${query.toString()}`)

  return {
    success: Boolean(result.success),
    message: result.message,
    data: result.data,
  }
}

/** 获取邮件日志筛选枚举（触发操作 / 发送结果） */
export const getEmailLogOptions = async (): Promise<EmailLogOptionsResult> => {
  const result = await get<EmailLogOptionsResult>(`${API_PREFIX}/email-logs/options`)
  return {
    success: Boolean(result.success),
    message: result.message,
    data: result.data,
  }
}
