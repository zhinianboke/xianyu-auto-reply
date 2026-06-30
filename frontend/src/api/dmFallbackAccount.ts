/**
 * 兜底私信账号配置 API（按分类）
 *
 * 功能：
 * 1. 列出当前用户已配置的兜底私信账号（按分类，含无分类那条）
 * 2. 新建/修改某个分类的兜底私信账号配置
 * 3. 删除某个分类的兜底私信账号配置
 *
 * 说明：私信任务在商品下单账号发私信不可用时，按链回退使用兜底私信账号。
 */
import { get, put, del } from '@/utils/request'
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/product-monitor/dm-fallback-accounts'

export interface DmFallbackAccountStatus {
  account_id: string
  valid: boolean
  reason?: string | null
}

export interface DmFallbackAccountConfig {
  id: number | null
  category_id: number | null
  category_name?: string | null
  account_ids: string[]
  accounts: DmFallbackAccountStatus[]
  created_at?: string | null
  updated_at?: string | null
}

export const getDmFallbackAccounts = (): Promise<ApiResponse<DmFallbackAccountConfig[]>> => {
  return get(`${PREFIX}`)
}

export const saveDmFallbackAccounts = (
  categoryId: number | null,
  accountIds: string[]
): Promise<ApiResponse<DmFallbackAccountConfig>> => {
  return put(`${PREFIX}`, { category_id: categoryId, account_ids: accountIds })
}

export const deleteDmFallbackAccounts = (
  categoryId: number | null
): Promise<ApiResponse<null>> => {
  const query = categoryId != null ? `?category_id=${categoryId}` : ''
  return del(`${PREFIX}${query}`)
}
