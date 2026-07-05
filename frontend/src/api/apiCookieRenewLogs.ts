/**
 * 接口续期Cookies日志API
 *
 * 功能：
 * 1. 获取接口续期Cookies批次列表
 * 2. 获取接口续期Cookies批次详情
 * 3. 清空10天前的历史日志
 */
import {
  createBatchLogApi,
  type BatchDetailResponse,
  type BatchListResponse,
} from './batchLogFactory'

export interface ApiCookieRenewLog {
  id: number
  batch_id: string
  account_id: string
  status: 'success' | 'cookie_updated' | 'failed'
  updated_cookie_count: number
  updated_cookie_names: string | null
  response_content: string | null
  error_message: string | null
  account_status: string
  created_at: string
}

export interface ApiCookieRenewBatch {
  batch_id: string
  executed_at: string
  total_accounts: number
  success_count: number
  cookie_updated_count: number
  failed_count: number
}

export interface ApiCookieRenewBatchDetail extends ApiCookieRenewBatch {
  logs: ApiCookieRenewLog[]
}

export type ApiCookieRenewBatchListResponse = BatchListResponse<ApiCookieRenewBatch>
export type ApiCookieRenewBatchDetailResponse = BatchDetailResponse<ApiCookieRenewBatchDetail | null>

const api = createBatchLogApi<ApiCookieRenewBatch, ApiCookieRenewBatchDetail | null>({
  batches: 'api-cookie-renew-batches',
  clearLogs: 'api-cookie-renew-logs/clear',
})

export const getApiCookieRenewBatches = api.getBatches
export const getApiCookieRenewBatchDetail = api.getBatchDetail
export const clearApiCookieRenewLogs = api.clearLogs
