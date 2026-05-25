import { get, put, post } from '@/utils/request'

const AUTO_RATE_PREFIX = '/api/v1/auto-rate'

// 自动评价配置类型
export interface AutoRateConfig {
  account_id: string
  enabled: boolean
  rate_type: 'text' | 'api'
  text_content?: string
  api_url?: string
}

// 获取自动评价配置
export const getAutoRateConfig = (accountId: string): Promise<{ success: boolean; data: AutoRateConfig }> => {
  return get(`${AUTO_RATE_PREFIX}/${accountId}`)
}

// 更新自动评价配置
export const updateAutoRateConfig = (
  accountId: string,
  config: Omit<AutoRateConfig, 'account_id'>
): Promise<{ success: boolean; message: string }> => {
  return put(`${AUTO_RATE_PREFIX}/${accountId}`, config)
}

// 批量补评价结果详情
export interface BatchRateDetail {
  account_id: string
  success: boolean
  rated_count: number
  failed_count: number
  total_pending: number
  message: string
}

// 批量补评价响应
export interface BatchRateResponse {
  success: boolean
  message: string
  data?: {
    total_rated: number
    total_failed: number
    success_accounts: number
    total_accounts: number
    details: BatchRateDetail[]
  }
}

// 批量订单补评价
export const batchRateOrders = (accountIds: string[]): Promise<BatchRateResponse> => {
  return post(`${AUTO_RATE_PREFIX}/batch-rate`, { account_ids: accountIds }, { timeout: 600000 })
}

