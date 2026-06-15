import { get } from '@/utils/request'

export interface AICallLog {
  id: number
  cookie_id: string
  cookie_remark?: string
  chat_id?: string
  user_id?: string
  item_id?: string
  model_name?: string
  provider?: string
  request_message?: string
  reply_text?: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  estimated: boolean
  duration_ms: number
  status: 'success' | 'failed'
  error_message?: string | null
  created_at: string
}

export interface AITokenDailyStat {
  date: string
  call_count: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface AITokenModelStat {
  model_name: string
  call_count: number
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface AITokenSummary {
  call_count?: number
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  estimated_count?: number
}

export const getAICallLogs = async (params?: {
  cookie_id?: string
  limit?: number
  offset?: number
}): Promise<{ success: boolean; data?: AICallLog[]; total?: number }> => {
  const query = new URLSearchParams()
  if (params?.cookie_id) query.set('cookie_id', params.cookie_id)
  if (params?.limit) query.set('limit', String(params.limit))
  if (params?.offset) query.set('offset', String(params.offset))
  return get(`/ai-call-logs?${query.toString()}`)
}

export const getAITokenStats = async (params?: {
  cookie_id?: string
  days?: number
}): Promise<{
  success: boolean
  daily?: AITokenDailyStat[]
  by_model?: AITokenModelStat[]
  summary?: AITokenSummary
}> => {
  const query = new URLSearchParams()
  if (params?.cookie_id) query.set('cookie_id', params.cookie_id)
  if (params?.days) query.set('days', String(params.days))
  return get(`/ai-token-stats?${query.toString()}`)
}
