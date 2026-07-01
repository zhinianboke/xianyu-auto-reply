/**
 * 兜底采集账号配置 API（按分类）
 *
 * 功能：
 * 1. 列出当前用户已配置的兜底采集账号（按分类，含无分类那条）
 * 2. 新建/修改某个分类的兜底采集账号配置
 * 3. 删除某个分类的兜底采集账号配置
 *
 * 说明：采集/卖家补全任务在监控任务无可用采集账号时，按 5 层链回退使用兜底账号。
 */
import { get, put, del } from '@/utils/request'
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/product-monitor/collect-fallback-accounts'

export interface CollectFallbackAccountStatus {
  account_id: string
  valid: boolean
  reason?: string | null
}

export interface CollectFallbackAccountConfig {
  id: number | null
  owner_id?: number | null
  owner_username?: string | null
  category_id: number | null
  category_name?: string | null
  account_ids: string[]
  accounts: CollectFallbackAccountStatus[]
  created_at?: string | null
  updated_at?: string | null
}

export const getCollectFallbackAccounts = (): Promise<ApiResponse<CollectFallbackAccountConfig[]>> => {
  return get(`${PREFIX}`)
}

export const saveCollectFallbackAccounts = (
  categoryId: number | null,
  accountIds: string[],
  ownerId?: number | null
): Promise<ApiResponse<CollectFallbackAccountConfig>> => {
  const body: Record<string, unknown> = { category_id: categoryId, account_ids: accountIds }
  // 管理员编辑其他用户配置时传 owner_id；普通用户不传，后端按当前用户处理
  if (ownerId != null) body.owner_id = ownerId
  return put(`${PREFIX}`, body)
}

export const deleteCollectFallbackAccounts = (
  categoryId: number | null,
  ownerId?: number | null
): Promise<ApiResponse<null>> => {
  const params = new URLSearchParams()
  if (categoryId != null) params.set('category_id', String(categoryId))
  if (ownerId != null) params.set('owner_id', String(ownerId))
  const query = params.toString()
  return del(`${PREFIX}${query ? `?${query}` : ''}`)
}
