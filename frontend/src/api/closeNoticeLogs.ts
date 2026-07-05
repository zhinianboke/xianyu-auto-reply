/**
 * 账号消息通知关闭日志API
 *
 * 功能：
 * 1. 获取定时任务执行批次列表
 * 2. 获取批次详情（包含所有账号的关闭结果日志）
 * 3. 清空10天前的消息通知关闭日志
 */
import {
  createBatchLogApi,
  type BatchDetailResponse,
  type BatchListResponse,
} from './batchLogFactory'

export interface CloseNoticeLog {
  id: number
  batch_id: string
  account_id: string
  status: 'success' | 'failed'
  error_message: string | null
  created_at: string
}

export interface CloseNoticeBatch {
  batch_id: string
  executed_at: string
  total_accounts: number
  success_count: number
  failed_count: number
}

export interface CloseNoticeBatchDetail extends CloseNoticeBatch {
  logs: CloseNoticeLog[]
}

export type CloseNoticeBatchListResponse = BatchListResponse<CloseNoticeBatch>
export type CloseNoticeBatchDetailResponse = BatchDetailResponse<CloseNoticeBatchDetail>

const api = createBatchLogApi<CloseNoticeBatch, CloseNoticeBatchDetail>({
  batches: 'close-notice-batches',
  clearLogs: 'close-notice-logs/clear',
})

export const getCloseNoticeBatches = api.getBatches
export const getCloseNoticeBatchDetail = api.getBatchDetail
export const clearCloseNoticeLogs = api.clearLogs
