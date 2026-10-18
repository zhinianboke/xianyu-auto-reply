/** 卡密处理结果日志接口。 */
import { get } from '@/utils/request'

const API_PREFIX = '/api/v1'

export interface CardProcessResultLog {
  id: number
  owner_id: number
  order_no: string
  request_body: string
  response_body: string
  trigger_scene: string
  success: boolean
  result_message: string
  created_at: string | null
}

export interface CardProcessResultLogQuery {
  page?: number
  page_size?: number
  order_no?: string
  trigger_scene?: string
  success?: boolean
}

export interface CardProcessResultLogPage {
  list: CardProcessResultLog[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

interface CardProcessResultLogListResult {
  success: boolean
  message?: string
  data?: CardProcessResultLogPage
}

/** 分页查询卡密处理结果日志。 */
export async function getCardProcessResultLogs(
  params: CardProcessResultLogQuery,
): Promise<CardProcessResultLogListResult> {
  const query = new URLSearchParams()
  query.set('page', String(params.page || 1))
  query.set('page_size', String(params.page_size || 20))
  if (params.order_no) query.set('order_no', params.order_no)
  if (params.trigger_scene) query.set('trigger_scene', params.trigger_scene)
  if (typeof params.success === 'boolean')
    query.set('success', String(params.success))
  return get<CardProcessResultLogListResult>(
    `${API_PREFIX}/card-process-result-logs?${query.toString()}`,
  )
}
