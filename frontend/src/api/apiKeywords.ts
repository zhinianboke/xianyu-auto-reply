/** API关键词配置接口，支持新建、编辑、软删除和配置查询。 */
import { del, get, post, put } from '@/utils/request'
import type { ApiResponse } from '@/types'

export interface ApiKeywordPayload {
  request_id: string
  keyword: string
  item_id: string
  url: string
  method: string
  timeout: number
  headers: Record<string, unknown>
  params: Record<string, unknown>
  response_field: string
  sync_confirm_delivery: boolean
  trigger_after_order: boolean
  follow_order_quantity: boolean
  skip_same_message: boolean
}
export interface ApiKeyword extends Omit<ApiKeywordPayload, 'request_id'> {
  id: string
  account_id: string
  created_at: string
  updated_at: string
  revision: string
}
export interface ApiKeywordUpdate extends Omit<ApiKeywordPayload, 'request_id'> { expected_revision: string }
export interface ApiKeywordOptions {
  methods: Array<{ value: string; label: string }>
  parameters: Array<{ value: string; label: string; placeholder: string }>
}
export interface ApiKeywordPage { list: ApiKeyword[]; total: number; page: number; page_size: number }

/** 检查列表的分页及行内必要字段，防止异常响应导致页面崩溃或使用错误ID删除。 */
export const isApiKeywordPage = (value: unknown): value is ApiKeywordPage => {
  if (!value || typeof value !== 'object') return false
  const page = value as Partial<ApiKeywordPage>
  return Number.isSafeInteger(page.total) && (page.total ?? -1) >= 0
    && Array.isArray(page.list) && page.list.every(item => item
      && typeof item.id === 'string' && /^[1-9]\d*$/.test(item.id)
      && typeof item.account_id === 'string' && item.account_id.trim().length > 0
      && typeof item.keyword === 'string' && typeof item.url === 'string'
      && typeof item.method === 'string' && typeof item.created_at === 'string')
}

const PREFIX = '/api/v1/api-keywords'
let deleteVersion = 0
const deleteListeners = new Set<() => void>()

/** 订阅删除结果；返回取消订阅方法，页面卸载时释放监听。 */
export const subscribeApiKeywordDeletes = (listener: () => void) => {
  deleteListeners.add(listener)
  return () => { deleteListeners.delete(listener) }
}
/** 读取删除版本，供列表同步订阅并检查挂载期间是否遗漏变化。 */
export const getApiKeywordDeleteVersion = () => deleteVersion

export const getApiKeywordOptions = () => get<ApiResponse<ApiKeywordOptions>>(`${PREFIX}/options`)
export const getApiKeywords = (accountId: string, page: number, pageSize: number, signal?: AbortSignal) =>
  get<ApiResponse<ApiKeywordPage>>(PREFIX, { params: { account_id: accountId, page, page_size: pageSize }, signal })
export const createApiKeyword = (accountId: string, payload: ApiKeywordPayload) =>
  post<ApiResponse<ApiKeyword>>(`${PREFIX}/${encodeURIComponent(accountId)}`, payload)
/** 多选商品一次保存，共用请求标识保障失败重试不会重复创建。 */
export const createApiKeywordsBatch = (accountId: string, config: ApiKeywordPayload, itemIds: string[]) =>
  post<ApiResponse<{ list: ApiKeyword[]; total: number }>>(`${PREFIX}/${encodeURIComponent(accountId)}/batch`, { config, item_ids: itemIds })
export const getApiKeywordDetail = (accountId: string, ruleId: string) =>
  get<ApiResponse<ApiKeyword>>(`${PREFIX}/${encodeURIComponent(accountId)}/${encodeURIComponent(ruleId)}`)
export const updateApiKeyword = (accountId: string, ruleId: string, payload: ApiKeywordUpdate) =>
  put<ApiResponse<ApiKeyword>>(`${PREFIX}/${encodeURIComponent(accountId)}/${encodeURIComponent(ruleId)}`, payload)
/** 按记录所属账号和主键删除配置，保留后端原始数据。 */
export const deleteApiKeyword = async (accountId: string, ruleId: string) => {
  const result = await del<ApiResponse<{ id: string; account_id: string }>>(`${PREFIX}/${encodeURIComponent(accountId)}/${encodeURIComponent(ruleId)}`)
  if (result?.success === true) {
    deleteVersion += 1
    deleteListeners.forEach(listener => listener())
  }
  return result
}

/** 生成幂等请求标识，兼容HTTP访问时randomUUID不可用的浏览器。 */
export { createRequestId as createApiKeywordRequestId } from '@/utils/uuid'
