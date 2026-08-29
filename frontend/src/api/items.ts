import { get, post, put, del } from '@/utils/request'
import type { Item, ApiResponse } from '@/types'
import type {
  MaterialVideo,
  PlatformCategoryPathItem,
  PlatformMaterialAttribute,
  PublishSkuRow,
  PublishSpecification,
} from '@/api/productPublish'

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

// ==================== 卡券关联商品选择弹窗 ====================

// 可选商品轻量项（仅选择场景所需字段）
export interface SelectableItem {
  item_id: string
  title?: string | null
  price?: string | null
}

// 获取全部匹配的可选商品轻量项（供「全选当前筛选结果」）
export const getAllSelectableItemKeys = (
  keyword: string = ''
): Promise<{ list: SelectableItem[]; total: number }> => {
  const params = new URLSearchParams()
  if (keyword && keyword.trim()) params.append('keyword', keyword.trim())
  const qs = params.toString()
  return get(`${ITEM_PREFIX}/selectable/all${qs ? `?${qs}` : ''}`)
}

// 获取卡券已关联商品的轻量详情（弹窗右侧「已选商品」展示用）
export const getItemsByCardId = (
  cardId: number
): Promise<{ list: SelectableItem[]; total: number }> => {
  return get(`${ITEM_PREFIX}/by-card/${cardId}`)
}

// 删除商品（账号可选）
// - 传入 cookieId：按账号删除
// - cookieId 为空（账号已删除的孤儿商品）：后端按商品ID删除
export const deleteItem = (cookieId: string | null | undefined, itemId: string): Promise<ApiResponse> => {
  return del(`${ITEM_PREFIX}/delete`, { data: { cookie_id: cookieId || null, item_id: itemId } })
}

// 批量删除商品
export const batchDeleteItems = (ids: { cookie_id: string; item_id: string }[]): Promise<ApiResponse> => {
  return del(`${ITEM_PREFIX}/batch`, { data: { items: ids } })
}

// 批量下架商品（调用闲鱼接口，使用所选账号的Cookie）
export const batchOfflineItems = (cookieId: string, itemIds: string[]): Promise<ApiResponse> => {
  return post(`${ITEM_PREFIX}/batch-offline`, { cookie_id: cookieId, item_ids: itemIds })
}

// 批量删除闲鱼平台商品（本地商品记录保留）
export const batchDeleteXianyuItems = (cookieId: string, itemIds: string[]): Promise<ApiResponse> => {
  return post(`${ITEM_PREFIX}/batch-delete-xianyu`, { cookie_id: cookieId, item_ids: itemIds })
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

// 鱼小铺商品改价（价格与库存一并提交）
// 单规格：{ price, quantity }；多规格：{ skus: [{ sku_id, price, quantity }] }
export interface UpdateItemPricePayload {
  price?: number
  quantity?: number
  skus?: Array<{ sku_id: string; price: number; quantity: number }>
}

export const updateItemPrice = (
  cookieId: string,
  itemId: string,
  payload: UpdateItemPricePayload,
): Promise<ApiResponse> => {
  return put(`${ITEM_PREFIX}/${cookieId}/${itemId}/price`, payload)
}

// ==================== 鱼小铺商品编辑（同步到闲鱼平台）====================

// 平台商品编辑详情，字段与素材库/单品发布保持一致，可直接回填发布表单
export interface SellerItemEditForm {
  item_id: string
  title: string
  description: string
  price: number | null
  original_price: number | null
  category: string
  quantity: number
  images: string[]
  videos: MaterialVideo[]
  specifications: PublishSpecification[]
  sku_rows: PublishSkuRow[]
  platform_category_id: string
  platform_category_name: string
  platform_channel_category_id: string
  platform_channel_category_name: string
  platform_leaf_id: string
  platform_tb_category_id: string
  platform_category_path: PlatformCategoryPathItem[]
  platform_attributes: PlatformMaterialAttribute[]
  category_source: 'manual' | 'recommendation'
  address: string
  address_expected_text: string
  shipping_method: 'free' | 'distance' | 'fixed' | 'template' | 'none'
  postage: number
  support_pickup: boolean
  delivery_method: 'express' | 'pickup'
  condition: string
  brand: string
}

// 鱼小铺商品编辑提交参数（字段与单品发布一致，不含账号ID）
export interface SellerItemEditPayload {
  title: string
  description: string
  price: number
  original_price?: number | null
  images: string[]
  // 平台已有视频带 file_id（后端凭此原样回传，不重复上传）；空数组表示清空平台视频
  videos: MaterialVideo[]
  platform_category_id?: string | null
  platform_category_name?: string | null
  platform_channel_category_id?: string | null
  platform_channel_category_name?: string | null
  platform_leaf_id?: string | null
  platform_tb_category_id?: string | null
  platform_attributes: PlatformMaterialAttribute[]
  specifications: PublishSpecification[]
  sku_rows: PublishSkuRow[]
  quantity: number
  address?: string | null
  address_expected_text?: string | null
  shipping_method: 'free' | 'distance' | 'fixed' | 'template' | 'none'
  support_pickup: boolean
  postage: number
  brand?: string | null
  condition?: string | null
}

// 获取鱼小铺商品的平台编辑详情（用于编辑弹窗回填）
export const getSellerItemEditDetail = (
  cookieId: string,
  itemId: string,
): Promise<ApiResponse<{ form: SellerItemEditForm }>> => {
  return get(`${ITEM_PREFIX}/${cookieId}/${itemId}/seller-detail`)
}

// 提交鱼小铺商品编辑到闲鱼平台，成功后后端会重新同步该账号商品
export const updateSellerItem = (
  cookieId: string,
  itemId: string,
  payload: SellerItemEditPayload,
): Promise<ApiResponse> => {
  return put(`${ITEM_PREFIX}/${cookieId}/${itemId}/seller-edit`, payload)
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
