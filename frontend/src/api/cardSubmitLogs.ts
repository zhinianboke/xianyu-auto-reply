/** 卡密提交日志接口。 */
import { get } from '@/utils/request'


const API_PREFIX = '/api/v1'


export interface CardSubmitLog {
  id: number
  owner_id: number
  order_no: string
  response_body: string
  success: boolean
  result_message: string
  created_at: string | null
}

export interface CardSubmitLogQuery {
  page?: number
  page_size?: number
  order_no?: string
  submit_result?: string
  start_date?: string
  end_date?: string
}

export interface CardSubmitLogOption {
  value: string
  label: string
}

export interface CardSubmitLogPage {
  list: CardSubmitLog[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

interface CardSubmitLogListResult {
  success: boolean
  message?: string
  data?: CardSubmitLogPage
}

interface CardSubmitLogOptionsResult {
  success: boolean
  message?: string
  data?: { submit_results: CardSubmitLogOption[] }
}

/** 分页查询卡密提交日志。 */
export async function getCardSubmitLogs(
  params: CardSubmitLogQuery,
): Promise<CardSubmitLogListResult> {
  const query = new URLSearchParams()
  query.set('page', String(params.page || 1))
  query.set('page_size', String(params.page_size || 20))
  if (params.order_no) query.set('order_no', params.order_no)
  if (params.submit_result) query.set('submit_result', params.submit_result)
  if (params.start_date) query.set('start_date', params.start_date)
  if (params.end_date) query.set('end_date', params.end_date)
  return get<CardSubmitLogListResult>(`${API_PREFIX}/card-submit-logs?${query.toString()}`)
}

/** 获取提交结果数据字典。 */
export function getCardSubmitLogOptions(): Promise<CardSubmitLogOptionsResult> {
  return get<CardSubmitLogOptionsResult>(`${API_PREFIX}/card-submit-logs/options`)
}
