/** API关键词配置接口，支持新建、编辑和配置查询。 */
import { get, post, put } from '@/utils/request'
import type { ApiResponse } from '@/types'

export interface ApiKeywordPayload {
  request_id: string
  keyword: string
  url: string
  method: string
  timeout: number
  headers: Record<string, unknown>
  params: Record<string, unknown>
  response_field: string
  sync_confirm_delivery: boolean
  trigger_after_order: boolean
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

const PREFIX = '/api/v1/api-keywords'
export const getApiKeywordOptions = () => get<ApiResponse<ApiKeywordOptions>>(`${PREFIX}/options`)
export const getApiKeywords = (accountId: string, page: number, pageSize: number, signal?: AbortSignal) =>
  get<ApiResponse<ApiKeywordPage>>(PREFIX, { params: { account_id: accountId, page, page_size: pageSize }, signal })
export const createApiKeyword = (accountId: string, payload: ApiKeywordPayload) =>
  post<ApiResponse<ApiKeyword>>(`${PREFIX}/${encodeURIComponent(accountId)}`, payload)
export const getApiKeywordDetail = (accountId: string, ruleId: string) =>
  get<ApiResponse<ApiKeyword>>(`${PREFIX}/${encodeURIComponent(accountId)}/${encodeURIComponent(ruleId)}`)
export const updateApiKeyword = (accountId: string, ruleId: string, payload: ApiKeywordUpdate) =>
  put<ApiResponse<ApiKeyword>>(`${PREFIX}/${encodeURIComponent(accountId)}/${encodeURIComponent(ruleId)}`, payload)

/** 生成幂等请求标识，兼容HTTP访问时randomUUID不可用的浏览器。 */
export function createApiKeywordRequestId(): string {
  const bytes = crypto.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40
  bytes[8] = (bytes[8] & 0x3f) | 0x80
  const hex = Array.from(bytes, value => value.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
