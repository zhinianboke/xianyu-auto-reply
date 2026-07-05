/**
 * 定时补发货日志API
 *
 * 功能：
 * 1. 获取定时任务执行批次列表
 * 2. 获取批次详情（包含所有发货日志）
 * 3. 清空10天前的补发货日志
 */
import {
  createBatchLogApi,
  type BatchDetailResponse,
  type BatchListResponse,
} from './batchLogFactory'

export interface RedeliveryLog {
  id: number
  batch_id: string
  account_id: string
  order_no: string
  status: 'success' | 'failed'
  error_message: string | null
  created_at: string
}

export interface RedeliveryBatch {
  batch_id: string
  executed_at: string
  total_orders: number
  success_count: number
  failed_count: number
}

export interface RedeliveryBatchDetail extends RedeliveryBatch {
  logs: RedeliveryLog[]
}

export type RedeliveryBatchListResponse = BatchListResponse<RedeliveryBatch>
export type RedeliveryBatchDetailResponse = BatchDetailResponse<RedeliveryBatchDetail>

const api = createBatchLogApi<RedeliveryBatch, RedeliveryBatchDetail>({
  batches: 'redelivery-batches',
  clearLogs: 'redelivery-logs/clear',
})

export const getRedeliveryBatches = api.getBatches
export const getRedeliveryBatchDetail = api.getBatchDetail
export const clearRedeliveryLogs = api.clearLogs
