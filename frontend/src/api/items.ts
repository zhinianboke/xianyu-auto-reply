import { get, post, put, del } from '@/utils/request'
import type { Item, ApiResponse } from '@/types'

// API前缀
const ITEM_PREFIX = '/api/v1/items'

export interface FetchItemsSummaryResponse extends ApiResponse {
  total_count?: number
  saved_count?: number
  account_count?: number
  success_account_count?: number
  failed_account_count?: number
  failed_accounts?: string[]
}

// 获取商品列表
export const getItems = async (cookieId?: string): Promise<{ success: boolean; data: Item[] }> => {
  const url = cookieId ? `${ITEM_PREFIX}/cookie/${cookieId}` : ITEM_PREFIX
  const result = await get<{ items?: Item[] } | Item[]>(url)
  // 后端返回 { items: [...] } 或直接返回数组
  const items = Array.isArray(result) ? result : (result.items || [])
  return { success: true, data: items }
}

// 商品筛选参数
export interface ItemFilterParams {
  keyword?: string | null            // 搜索关键字（商品ID/标题/详情）
  is_polished?: boolean | null      // 是否擦亮
  is_multi_spec?: boolean | null    // 多规格
  multi_quantity_delivery?: boolean | null  // 多数量发货
}

// 获取商品列表（分页）
export const getItemsPaginated = async (
  page: number = 1,
  pageSize: number = 20,
  cookieId?: string,
  filters?: ItemFilterParams
): Promise<{
  success: boolean
  data: Item[]
  total: number
  page: number
  page_size: number
  total_pages: number
}> => {
  const params = new URLSearchParams()
  params.append('page', String(page))
  params.append('page_size', String(pageSize))
  
  if (cookieId) {
    params.append('cookie_id', cookieId)
  }
  
  if (filters) {
    if (filters.keyword && filters.keyword.trim()) {
      params.append('keyword', filters.keyword.trim())
    }
    if (filters.is_polished !== null && filters.is_polished !== undefined) {
      params.append('is_polished', String(filters.is_polished))
    }
    if (filters.is_multi_spec !== null && filters.is_multi_spec !== undefined) {
      params.append('is_multi_spec', String(filters.is_multi_spec))
    }
    if (filters.multi_quantity_delivery !== null && filters.multi_quantity_delivery !== undefined) {
      params.append('multi_quantity_delivery', String(filters.multi_quantity_delivery))
    }
  }
  
  const result = await get<{
    success: boolean
    data: Item[]
    total: number
    page: number
    page_size: number
    total_pages: number
  }>(`${ITEM_PREFIX}/paginated?${params.toString()}`)
  return result
}

// 删除商品
export const deleteItem = (cookieId: string, itemId: string): Promise<ApiResponse> => {
  return del(`${ITEM_PREFIX}/${cookieId}/${itemId}`)
}

// 批量删除商品
export const batchDeleteItems = (ids: { cookie_id: string; item_id: string }[]): Promise<ApiResponse> => {
  return del(`${ITEM_PREFIX}/batch`, { data: { items: ids } })
}

// 从账号获取商品（分页）
export const fetchItemsFromAccount = (cookieId: string, page?: number): Promise<ApiResponse> => {
  return post(`${ITEM_PREFIX}/get-by-page`, { cookie_id: cookieId, page: page || 1 })
}

// 获取账号所有页商品
export const fetchAllItemsFromAccount = (cookieId: string): Promise<FetchItemsSummaryResponse> => {
  return post(`${ITEM_PREFIX}/get-all-from-account`, { cookie_id: cookieId })
}

// 获取当前权限范围内所有账号的所有商品
export const fetchAllItemsFromAccessibleAccounts = (): Promise<FetchItemsSummaryResponse> => {
  return post(`${ITEM_PREFIX}/get-all-from-account`, {})
}

// 更新商品
export const updateItem = (cookieId: string, itemId: string, data: Partial<Item>): Promise<ApiResponse> => {
  return put(`${ITEM_PREFIX}/${cookieId}/${itemId}`, data)
}

// 更新商品多数量发货状态
export const updateItemMultiQuantityDelivery = (cookieId: string, itemId: string, enabled: boolean): Promise<ApiResponse> => {
  return put(`${ITEM_PREFIX}/${cookieId}/${itemId}/multi-quantity-delivery`, { multi_quantity_delivery: enabled })
}

// 更新商品多规格状态
export const updateItemMultiSpec = (cookieId: string, itemId: string, enabled: boolean): Promise<ApiResponse> => {
  return put(`${ITEM_PREFIX}/${cookieId}/${itemId}/multi-spec`, { is_multi_spec: enabled })
}


// ==================== 商品默认回复 ====================

// 商品默认回复配置类型
export interface ItemDefaultReplyConfig {
  item_id: string
  reply_content: string
  reply_image: string
  enabled: boolean
  reply_once: boolean
  reply_type?: string  // text-文本，image-图片，api-接口
  api_url?: string
  api_timeout?: number
}

// 获取商品默认回复配置
export const getItemDefaultReply = (cookieId: string, itemId: string): Promise<ApiResponse<ItemDefaultReplyConfig>> => {
  return get(`${ITEM_PREFIX}/${cookieId}/${itemId}/default-reply`)
}

// 保存商品默认回复配置
export const saveItemDefaultReply = (
  cookieId: string,
  itemId: string,
  data: { reply_content: string; reply_image?: string; enabled: boolean; reply_once: boolean; reply_type?: string; api_url?: string; api_timeout?: number }
): Promise<ApiResponse> => {
  return put(`${ITEM_PREFIX}/${cookieId}/${itemId}/default-reply`, data)
}

// 上传商品默认回复图片
export const uploadItemDefaultReplyImage = async (
  cookieId: string,
  itemId: string,
  image: File
): Promise<{ success: boolean; image_url?: string; message?: string }> => {
  const formData = new FormData()
  formData.append('image', image)
  return post(`${ITEM_PREFIX}/${cookieId}/${itemId}/default-reply/upload-image`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 删除商品默认回复配置
export const deleteItemDefaultReply = (cookieId: string, itemId: string): Promise<ApiResponse> => {
  return del(`${ITEM_PREFIX}/${cookieId}/${itemId}/default-reply`)
}

// 批量保存商品默认回复配置
export const batchSaveItemDefaultReply = (
  cookieId: string,
  data: { item_ids: string[]; reply_content: string; reply_image?: string; enabled: boolean; reply_once: boolean; reply_type?: string; api_url?: string; api_timeout?: number }
): Promise<ApiResponse> => {
  return post(`${ITEM_PREFIX}/${cookieId}/batch-default-reply`, data)
}

// 上传批量默认回复图片（使用第一个商品ID作为临时存储）
export const uploadBatchDefaultReplyImage = async (
  cookieId: string,
  image: File
): Promise<{ success: boolean; image_url?: string; message?: string }> => {
  const formData = new FormData()
  formData.append('image', image)
  return post(`${ITEM_PREFIX}/${cookieId}/batch-default-reply/upload-image`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 批量删除商品默认回复配置
export const batchDeleteItemDefaultReply = (
  cookieId: string,
  itemIds: string[]
): Promise<ApiResponse> => {
  return post(`${ITEM_PREFIX}/${cookieId}/batch-delete-default-reply`, { item_ids: itemIds })
}


// ==================== 商品AI提示词 ====================

// 商品AI提示词配置类型
export interface ItemAiPromptConfig {
  item_id: string
  ai_prompt: string
}

// 获取商品AI提示词配置
export const getItemAiPrompt = (cookieId: string, itemId: string): Promise<ApiResponse<ItemAiPromptConfig>> => {
  return get(`${ITEM_PREFIX}/${cookieId}/${itemId}/ai-prompt`)
}

// 保存商品AI提示词配置
export const saveItemAiPrompt = (
  cookieId: string,
  itemId: string,
  aiPrompt: string
): Promise<ApiResponse> => {
  return put(`${ITEM_PREFIX}/${cookieId}/${itemId}/ai-prompt`, { ai_prompt: aiPrompt })
}

// 批量删除商品AI提示词配置
export const batchDeleteItemAiPrompt = (
  cookieId: string,
  itemIds: string[]
): Promise<ApiResponse> => {
  return post(`${ITEM_PREFIX}/${cookieId}/batch-delete-ai-prompt`, { item_ids: itemIds })
}

// 批量保存商品AI提示词配置
export const batchSaveItemAiPrompt = (
  cookieId: string,
  data: { item_ids: string[]; ai_prompt: string }
): Promise<ApiResponse> => {
  return post(`${ITEM_PREFIX}/${cookieId}/batch-ai-prompt`, data)
}
