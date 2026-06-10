import { get } from '@/utils/request'

const PREFIX = '/api/v1'

export interface AutoReplyLogItem {
  id: number
  owner_id: number | null
  owner_username: string | null
  account_pk: number | null
  account_id: string
  account_name: string | null
  chat_id: string
  item_id: string | null
  item_title: string | null
  source_message_id: string | null
  sender_user_id: string
  sender_user_name: string | null
  source_message: string | null
  source_message_time: string | null
  process_status: string
  decision_reason: string
  reply_strategy: string
  reply_mode: string
  matched_keyword: string | null
  matched_rule_type: string | null
  default_reply_scope: string | null
  default_reply_once: boolean
  ai_model_name: string | null
  ai_provider_name: string | null
  reply_text: string | null
  reply_image_url: string | null
  error_message: string | null
  send_status: string
  send_fail_reason: string | null
  created_at: string | null
  updated_at: string | null
}

export interface AutoReplyLogListResponse {
  success: boolean
  message?: string
  data: AutoReplyLogItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export const getAutoReplyLogs = async (params?: {
  account_id?: string
  start_date?: string
  end_date?: string
  matched_rule_type?: string
  send_status?: string
  message_type?: string
  page?: number
  page_size?: number
}): Promise<AutoReplyLogListResponse> => {
  const queryParams = new URLSearchParams()
  if (params?.account_id) queryParams.append('account_id', params.account_id)
  if (params?.start_date) queryParams.append('start_date', params.start_date)
  if (params?.end_date) queryParams.append('end_date', params.end_date)
  if (params?.matched_rule_type) queryParams.append('matched_rule_type', params.matched_rule_type)
  if (params?.send_status) queryParams.append('send_status', params.send_status)
  if (params?.message_type) queryParams.append('message_type', params.message_type)
  if (params?.page) queryParams.append('page', params.page.toString())
  if (params?.page_size) queryParams.append('page_size', params.page_size.toString())

  const queryString = queryParams.toString()
  return get<AutoReplyLogListResponse>(`${PREFIX}/auto-reply-logs${queryString ? `?${queryString}` : ''}`)
}
