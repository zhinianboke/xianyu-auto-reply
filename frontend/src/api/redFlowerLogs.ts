/**
 * 求小红花日志API
 *
 * 功能：
 * 1. 获取求小红花执行批次列表
 * 2. 获取批次详情（包含所有求小红花日志）
 * 3. 清空10天前的求小红花日志
 */
import {
  createBatchLogApi,
  type BatchDetailResponse,
  type BatchListResponse,
} from './batchLogFactory'

export interface RedFlowerLog {
  id: number
  batch_id: string
  account_id: string
  order_no: string
  status: 'success' | 'failed'
  error_message: string | null
  created_at: string
}

export interface RedFlowerBatch {
  batch_id: string
  executed_at: string
  total_orders: number
  success_count: number
  failed_count: number
}

export interface RedFlowerBatchDetail extends RedFlowerBatch {
  logs: RedFlowerLog[]
}

export type RedFlowerBatchListResponse = BatchListResponse<RedFlowerBatch>
export type RedFlowerBatchDetailResponse = BatchDetailResponse<RedFlowerBatchDetail>

const api = createBatchLogApi<RedFlowerBatch, RedFlowerBatchDetail>({
  batches: 'red-flower-batches',
  clearLogs: 'red-flower-logs/clear',
})

export const getRedFlowerBatches = api.getBatches
export const getRedFlowerBatchDetail = api.getBatchDetail
export const clearRedFlowerLogs = api.clearLogs
