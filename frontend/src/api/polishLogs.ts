/**
 * 定时擦亮日志API
 *
 * 功能：
 * 1. 获取定时任务执行批次列表
 * 2. 获取批次详情（包含所有擦亮日志）
 * 3. 清空10天前的擦亮日志
 */
import {
  createBatchLogApi,
  type BatchDetailResponse,
  type BatchListResponse,
} from './batchLogFactory'

export interface PolishLog {
  id: number
  batch_id: string
  account_id: string
  item_id: string
  status: 'success' | 'failed'
  error_message: string | null
  created_at: string
}

export interface PolishBatch {
  batch_id: string
  executed_at: string
  total_items: number
  success_count: number
  failed_count: number
}

export interface PolishBatchDetail extends PolishBatch {
  logs: PolishLog[]
}

export type PolishBatchListResponse = BatchListResponse<PolishBatch>
export type PolishBatchDetailResponse = BatchDetailResponse<PolishBatchDetail>

const api = createBatchLogApi<PolishBatch, PolishBatchDetail>({
  batches: 'polish-batches',
  clearLogs: 'polish-logs/clear',
})

export const getPolishBatches = api.getBatches
export const getPolishBatchDetail = api.getBatchDetail
export const clearPolishLogs = api.clearLogs
