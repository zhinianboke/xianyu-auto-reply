/**
 * 登录续期日志API
 *
 * 功能：
 * 1. 获取定时任务执行批次列表
 * 2. 获取批次详情（包含所有续期日志）
 * 3. 清空10天前的登录续期日志
 */
import {
  createBatchLogApi,
  type BatchDetailResponse,
  type BatchListResponse,
} from './batchLogFactory'

export interface LoginRenewLog {
  id: number
  batch_id: string
  account_id: string
  status: 'success' | 'token_refreshed' | 'session_expired' | 'failed'
  error_message: string | null
  created_at: string
}

export interface LoginRenewBatch {
  batch_id: string
  executed_at: string
  total_accounts: number
  success_count: number
  token_refreshed_count: number
  session_expired_count: number
  failed_count: number
}

export interface LoginRenewBatchDetail extends LoginRenewBatch {
  logs: LoginRenewLog[]
}

export type LoginRenewBatchListResponse = BatchListResponse<LoginRenewBatch>
export type LoginRenewBatchDetailResponse = BatchDetailResponse<LoginRenewBatchDetail>

const api = createBatchLogApi<LoginRenewBatch, LoginRenewBatchDetail>({
  batches: 'login-renew-batches',
  clearLogs: 'login-renew-logs/clear',
})

export const getLoginRenewBatches = api.getBatches
export const getLoginRenewBatchDetail = api.getBatchDetail
export const clearLoginRenewLogs = api.clearLogs
