/**
 * Token 续期日志 API。
 *
 * 功能：
 * 1. 获取 Token 续期任务执行批次列表。
 * 2. 获取指定批次的逐账号续期明细。
 */
import {
  createUnifiedBatchLogApi,
  type BatchDetailResponse,
  type BatchListResponse,
} from './batchLogFactory'

export interface TokenRenewalLog {
  id: number
  batch_id: string
  account_id: string
  token_user_id: string
  status: 'success' | 'failed'
  renew_expire_at: string | null
  error_message: string | null
  created_at: string
}

export interface TokenRenewalBatch {
  batch_id: string
  executed_at: string
  total_accounts: number
  success_count: number
  failed_count: number
}

export interface TokenRenewalBatchDetail extends TokenRenewalBatch {
  logs: TokenRenewalLog[]
}

export type TokenRenewalBatchListResponse = BatchListResponse<TokenRenewalBatch>
export type TokenRenewalBatchDetailResponse = BatchDetailResponse<TokenRenewalBatchDetail>

const api = createUnifiedBatchLogApi<TokenRenewalBatch, TokenRenewalBatchDetail>(
  'token-renewal-batches',
)

export const getTokenRenewalBatches = api.getBatches
export const getTokenRenewalBatchDetail = api.getBatchDetail
