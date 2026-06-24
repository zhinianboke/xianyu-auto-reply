/**
 * 兜底下单账号配置 API（按分类）
 *
 * 功能：
 * 1. 列出当前用户已配置的兜底下单账号（按分类，含无分类那条）
 * 2. 新建/修改某个分类的兜底下单账号配置
 * 3. 删除某个分类的兜底下单账号配置
 *
 * 说明：定时下单/私信任务在监控任务无可用下单账号时，按 5 层链回退使用兜底账号。
 */
import { get, put, del } from '@/utils/request'
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/product-monitor/order-fallback-accounts'

export interface OrderFallbackAccountStatus {
  account_id: string
  valid: boolean
  reason?: string | null
}

export interface OrderFallbackAccountConfig {
  id: number | null
  category_id: number | null
  category_name?: string | null
  account_ids: string[]
  accounts: OrderFallbackAccountStatus[]
  created_at?: string | null
  updated_at?: string | null
}

export const getOrderFallbackAccounts = (): Promise<ApiResponse<OrderFallbackAccountConfig[]>> => {
  return get(`${PREFIX}`)
}

export const saveOrderFallbackAccounts = (
  categoryId: number | null,
  accountIds: string[]
): Promise<ApiResponse<OrderFallbackAccountConfig>> => {
  return put(`${PREFIX}`, { category_id: categoryId, account_ids: accountIds })
}

export const deleteOrderFallbackAccounts = (
  categoryId: number | null
): Promise<ApiResponse<null>> => {
  const query = categoryId != null ? `?category_id=${categoryId}` : ''
  return del(`${PREFIX}${query}`)
}
