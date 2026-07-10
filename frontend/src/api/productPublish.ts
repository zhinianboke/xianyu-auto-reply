/**
 * 商品发布 API 接口层
 *
 * 功能：
 * 1. 素材库 CRUD
 * 2. 单品发布 / 批量发布
 * 3. 发布日志查询
 */
import { get, post, put, del } from '@/utils/request'
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/product-publish'

// ==================== 类型定义 ====================

export interface ProductMaterial {
  id: number
  user_id: number
  username?: string  // 管理员场景返回
  title: string
  description: string
  price: number
  original_price?: number | null
  category?: string | null
  images: string[]
  delivery_method: 'express' | 'pickup'
  postage: number
  address?: string | null
  brand?: string | null
  condition: string
  remark?: string | null
  created_at: string
  updated_at: string
}

export interface MaterialCreateParams {
  title: string
  description: string
  price: number
  original_price?: number | null
  category?: string
  images: string[]
  delivery_method?: 'express' | 'pickup'
  postage?: number
  address?: string
  brand?: string
  condition?: string
  remark?: string
}

export type AiListingPriceMode = 'fixed' | 'range'
export type AiListingImageMode = 'ai' | 'random'

export interface AiListingMaterialDefaults {
  category?: string
  condition?: string
  brand?: string
  delivery_method?: ProductDeliveryMethod
  support_pickup?: boolean
  postage?: number
  address?: string
  remark?: string
}

export interface AiListingConfig {
  id: number
  user_id: number
  name: string
  prompt: string
  reference_text?: string | null
  price_mode: AiListingPriceMode
  fixed_price?: number | null
  price_min?: number | null
  price_max?: number | null
  text_api_url: string
  text_api_key: string
  text_model: string
  image_mode: AiListingImageMode
  image_api_url?: string | null
  image_api_key?: string | null
  image_model?: string | null
  image_prompt?: string | null
  image_polish_enabled: boolean
  image_polish_sequential: boolean
  random_images: string[]
  random_image_count: number
  material_defaults: AiListingMaterialDefaults
  created_at: string
  updated_at: string
}

export interface AiListingConfigParams {
  name: string
  prompt: string
  reference_text?: string
  price_mode: AiListingPriceMode
  fixed_price?: number | null
  price_min?: number | null
  price_max?: number | null
  text_api_url: string
  text_api_key: string
  text_model: string
  image_mode: AiListingImageMode
  image_api_url?: string
  image_api_key?: string
  image_model?: string
  image_prompt?: string
  image_polish_enabled: boolean
  image_polish_sequential: boolean
  random_images: string[]
  random_image_count: number
  material_defaults: AiListingMaterialDefaults
}

export interface AiListingTaskStatus {
  task_id: string
  config_id: number
  config_name?: string
  total: number
  current: number
  success: number
  failed: number
  status: 'pending' | 'running' | 'success' | 'failed' | 'partial_success'
  message: string
  progress_percent?: number
  active_stage?: string
  stage_label?: string
  stage_detail?: string
  step_counts?: Record<string, { done: number; total: number }>
  created_material_ids: number[]
  errors: string[]
  finished: boolean
}

export interface MaterialListResponse {
  success: boolean
  message: string
  data: {
    list: ProductMaterial[]
    total: number
    page: number
    page_size: number
    total_pages: number
  }
}

export interface PublishLog {
  id: number
  user_id: number
  username?: string  // 管理员场景返回
  account_id: string
  title: string
  description?: string
  price?: string
  material_id?: number | null
  batch_id?: string | null
  status: 'pending' | 'publishing' | 'success' | 'failed'
  item_url?: string | null
  item_id?: string | null
  error_message?: string | null
  resolved_address_id?: number | null
  resolved_address_text?: string | null
  address_source?: 'material' | 'account_pool' | 'global_pool' | 'personal_pool' | null
  created_at: string
  updated_at: string
}

export interface PublishLogListResponse {
  success: boolean
  message: string
  data: {
    list: PublishLog[]
    total: number
    page: number
    page_size: number
    total_pages: number
  }
}

export interface BatchAccountStatus {
  account_id: string
  total: number
  success: number
  failed: number
  publishing: number
  pending: number
  sync_status: 'pending' | 'running' | 'success' | 'failed' | 'skipped' | 'unknown'
  sync_message: string
  sync_total_count: number
  sync_saved_count: number
}

export interface BatchStatusResponse {
  success: boolean
  message: string
  data: {
    batch_id: string
    total: number
    success: number
    failed: number
    publishing: number
    pending: number
    finished: boolean
    account_statuses: BatchAccountStatus[]
  }
}

export interface PublishSingleResponseData {
  item_url?: string | null
  item_id?: string | null
  log_id?: number
  sync_status?: 'success' | 'failed' | 'skipped'
  sync_message?: string | null
  sync_total_count?: number
  sync_saved_count?: number
}

export type PublishSingleResponse = ApiResponse<PublishSingleResponseData>

export interface PublishBatchResponseData {
  batch_id: string
  total: number
}

export type PublishBatchResponse = ApiResponse<PublishBatchResponseData>

// ==================== 素材库接口 ====================

/** 创建素材 */
export const createMaterial = (params: MaterialCreateParams): Promise<ApiResponse> =>
  post(`${PREFIX}/materials`, params)

/** 分页查询素材列表 */
export const getMaterials = (
  page = 1,
  pageSize = 20,
  filters?: { title?: string; category?: string; condition?: string }
): Promise<MaterialListResponse> => {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (filters?.title) params.append('title', filters.title)
  if (filters?.category) params.append('category', filters.category)
  if (filters?.condition) params.append('condition', filters.condition)
  return get(`${PREFIX}/materials?${params}`)
}

/** 获取单条素材详情 */
export const getMaterial = (id: number): Promise<ApiResponse> =>
  get(`${PREFIX}/materials/${id}`)

/** 更新素材 */
export const updateMaterial = (
  id: number,
  params: Partial<MaterialCreateParams>
): Promise<ApiResponse> => put(`${PREFIX}/materials/${id}`, params)

/** 删除素材 */
export const deleteMaterial = (id: number): Promise<ApiResponse> =>
  del(`${PREFIX}/materials/${id}`)

/** 批量删除素材 */
export const batchDeleteMaterials = (ids: number[]): Promise<ApiResponse> =>
  post(`${PREFIX}/materials/batch-delete`, { ids })

// ==================== AI铺货接口 ====================

export const getAiListingConfigs = (): Promise<ApiResponse<AiListingConfig[]>> =>
  get(`${PREFIX}/ai-listing/configs`)

export const createAiListingConfig = (params: AiListingConfigParams): Promise<ApiResponse<AiListingConfig>> =>
  post(`${PREFIX}/ai-listing/configs`, params)

export const updateAiListingConfig = (
  id: number,
  params: AiListingConfigParams
): Promise<ApiResponse<AiListingConfig>> => put(`${PREFIX}/ai-listing/configs/${id}`, params)

export const deleteAiListingConfig = (id: number): Promise<ApiResponse> =>
  del(`${PREFIX}/ai-listing/configs/${id}`)

export const startAiListingGeneration = (
  configId: number,
  count: number,
  concurrency: number
): Promise<ApiResponse<{ task_id: string; total: number }>> =>
  post(`${PREFIX}/ai-listing/configs/${configId}/generate`, { count, concurrency })

export const getAiListingTaskStatus = (taskId: string): Promise<ApiResponse<AiListingTaskStatus>> =>
  get(`${PREFIX}/ai-listing/tasks/${taskId}/status`)

export const getAiListingTasks = (): Promise<ApiResponse<AiListingTaskStatus[]>> =>
  get(`${PREFIX}/ai-listing/tasks`)

// ==================== 发布接口 ====================

/** 单品发布（同步，超时时间需设长） */
export const publishSingle = (params: {
  account_id: string
  title: string
  description: string
  price: number
  original_price?: number | null
  category?: string
  images: string[]        // 本地绝对路径，由 uploadProductImages 返回
  address?: string
  delivery_method?: string
  postage?: number
  brand?: string
  condition?: string
}): Promise<PublishSingleResponse> =>
  post(`${PREFIX}/publish/single`, params, { timeout: 600000 }) // 10分钟超时

/** 批量发布（异步，立即返回 batch_id） */
export const publishBatch = (params: {
  account_ids: string[]
  material_ids: number[]
}): Promise<PublishBatchResponse> => post(`${PREFIX}/publish/batch`, params)

/** 查询批量发布任务状态 */
export const getBatchStatus = (batchId: string): Promise<BatchStatusResponse> =>
  get(`${PREFIX}/publish/batch/${batchId}/status`)

// ==================== 图片上传 ====================

/** 上传商品图片（返回本地路径供 Playwright 使用 + URL 供预览）
 *  注意：不要手动设置 Content-Type，axios 会自动添加正确的 multipart boundary
 */
export const uploadProductImages = async (files: File[]): Promise<{
  success: boolean
  message: string
  data?: { paths: string[]; urls: string[] }
}> => {
  const formData = new FormData()
  files.forEach(f => formData.append('files', f))
  return post(`${PREFIX}/upload/images`, formData)
}

/** 分页查询发布日志 */
export const getPublishLogs = (
  page = 1,
  pageSize = 20,
  accountId?: string,
  status?: string
): Promise<PublishLogListResponse> => {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (accountId) params.append('account_id', accountId)
  if (status) params.append('status', status)
  return get(`${PREFIX}/logs?${params}`)
}

/** 查询单条发布日志 */
export const getPublishLog = (logId: number): Promise<ApiResponse<PublishLog>> =>
  get(`${PREFIX}/logs/${logId}`)

export const clearPublishLogs = async (): Promise<{ success: boolean; message: string }> => {
  return del<{ success: boolean; message: string }>(`${PREFIX}/logs/clear`)
}
