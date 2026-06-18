/**
 * 兜底下单账号配置 API
 *
 * 功能：
 * 1. 查询当前用户的兜底下单账号配置
 * 2. 保存（新增/更新）兜底下单账号配置
 *
 * 说明：当定时下单任务发现监控任务自身无可用下单账号时，
 * 回退使用此处配置的兜底账号下单。
 */
import { get, put } from '@/utils/request'
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/product-monitor/order-fallback-accounts'

// 单个兜底账号的有效性信息
export interface OrderFallbackAccountStatus {
  account_id: string
  valid: boolean
  reason?: string | null
}

export interface OrderFallbackAccountConfig {
  id: number | null
  account_ids: string[]
  accounts: OrderFallbackAccountStatus[]
  created_at?: string | null
  updated_at?: string | null
}

// 查询当前用户的兜底下单账号配置
export const getOrderFallbackAccounts = (): Promise<ApiResponse<OrderFallbackAccountConfig>> => {
  return get(`${PREFIX}`)
}

// 保存（新增/更新）兜底下单账号配置
export const saveOrderFallbackAccounts = (
  accountIds: string[]
): Promise<ApiResponse<OrderFallbackAccountConfig>> => {
  return put(`${PREFIX}`, { account_ids: accountIds })
}
