/**
 * 定时补评价日志API
 *
 * 功能：
 * 1. 获取定时任务执行批次列表
 * 2. 获取批次详情（包含所有评价日志）
 * 3. 清空10天前的补评价日志
 */
import {
  createBatchLogApi,
  type BatchDetailResponse,
  type BatchListResponse,
} from './batchLogFactory'

export interface RateLog {
  id: number
  batch_id: string
  account_id: string
  order_no: string
  status: 'success' | 'failed'
  error_message: string | null
  created_at: string
}

export interface RateBatch {
  batch_id: string
  executed_at: string
  total_orders: number
  success_count: number
  failed_count: number
}

export interface RateBatchDetail extends RateBatch {
  logs: RateLog[]
}

export type RateBatchListResponse = BatchListResponse<RateBatch>
export type RateBatchDetailResponse = BatchDetailResponse<RateBatchDetail>

const api = createBatchLogApi<RateBatch, RateBatchDetail>({
  batches: 'rate-batches',
  clearLogs: 'rate-logs/clear',
})

export const getRateBatches = api.getBatches
export const getRateBatchDetail = api.getBatchDetail
export const clearRateLogs = api.clearLogs
