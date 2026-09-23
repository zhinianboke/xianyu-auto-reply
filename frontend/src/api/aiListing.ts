/**
 * AI 铺货接口
 *
 * 功能：
 * 1. AI 铺货配置的增删改查、连通性测试、模型列表
 * 2. AI 铺货任务的启动、进度查询、历史列表、取消
 */
import { del, get, post, put } from '@/utils/request'
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/ai-listing'

// ==================== 类型定义 ====================

/** AI 铺货配置（密钥字段为脱敏值，仅用于展示） */
export interface AiListingConfig {
  id: number
  name: string
  provider_type: string
  text_base_url: string
  text_api_key_masked: string
  text_model: string
  text_temperature: number
  text_max_tokens: number
  prompt_template: string
  image_enabled: boolean
  image_base_url: string
  image_api_key_masked: string
  has_image_api_key: boolean
  image_model: string
  image_size: string
  image_count: number
  created_at: string | null
  updated_at: string | null
}

/** 保存配置的请求参数（密钥留空表示不修改） */
export interface AiListingConfigParams {
  name: string
  provider_type: string
  text_base_url: string
  text_api_key: string
  text_model: string
  text_temperature: number
  text_max_tokens: number
  prompt_template?: string
  image_enabled: boolean
  image_base_url?: string
  image_api_key: string
  image_model?: string
  image_size: string
  image_count: number
}

/** 生成素材时套用的默认字段 */
export interface AiListingMaterialDefaults {
  category?: string
  condition: string
  brand?: string
  quantity: number
  delivery_method: 'express' | 'pickup'
  shipping_method: 'free' | 'distance' | 'fixed' | 'template' | 'none'
  support_pickup: boolean
  postage: number
  address?: string
  remark?: string
  images: string[]
}

/** 启动任务的请求参数 */
export interface AiListingTaskParams {
  config_id: number
  keyword: string
  count: number
  price_mode: 'fixed' | 'range'
  price?: number
  price_min?: number
  price_max?: number
  image_enabled?: boolean
  material_defaults: AiListingMaterialDefaults
}

/** 任务明细（每条素材一行） */
export interface AiListingTaskItem {
  seq: number
  status: 'pending' | 'running' | 'success' | 'failed'
  title: string
  material_id: number | null
  image_count: number
  error_message: string
}

/** 任务进度 */
export interface AiListingTask {
  task_id: string
  config_id: number
  config_name: string
  keyword: string
  total: number
  success: number
  failed: number
  status: 'pending' | 'running' | 'success' | 'partial' | 'failed' | 'canceled'
  finished: boolean
  progress_percent: number
  error_message: string
  started_at: string | null
  finished_at: string | null
  created_at: string | null
}

/** 任务详情（含明细） */
export interface AiListingTaskDetail extends AiListingTask {
  items: AiListingTaskItem[]
}

/** 配置分页响应 */
export interface AiListingConfigListResponse {
  success: boolean
  message: string
  data: {
    list: AiListingConfig[]
    total: number
    page: number
    page_size: number
    total_pages: number
  }
}

/** 任务分页响应 */
export interface AiListingTaskListResponse {
  success: boolean
  message: string
  data: {
    list: AiListingTask[]
    total: number
    page: number
    page_size: number
    total_pages: number
  }
}

// ==================== 配置接口 ====================

/** 分页查询 AI 铺货配置 */
export const getAiListingConfigs = (page = 1, pageSize = 20, name?: string): Promise<AiListingConfigListResponse> => {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (name) params.append('name', name)
  return get(`${PREFIX}/configs?${params}`)
}

/** 新增 AI 铺货配置 */
export const createAiListingConfig = (params: AiListingConfigParams): Promise<ApiResponse<{ id: number }>> =>
  post(`${PREFIX}/configs`, params)

/** 编辑 AI 铺货配置 */
export const updateAiListingConfig = (id: number, params: AiListingConfigParams): Promise<ApiResponse<{ id: number }>> =>
  put(`${PREFIX}/configs/${id}`, params)

/** 删除 AI 铺货配置（软删除） */
export const deleteAiListingConfig = (id: number): Promise<ApiResponse> => del(`${PREFIX}/configs/${id}`)

/** 拉取服务商可用模型列表 */
export const getAiListingModels = (params: {
  provider_type: string
  base_url: string
  api_key?: string
  config_id?: number
}): Promise<ApiResponse<{ models: Array<{ id: string; name: string }> }>> =>
  post(`${PREFIX}/configs/models`, params)

/** 测试配置连通性 */
export const testAiListingConfig = (id: number): Promise<ApiResponse<{ reply: string }>> =>
  post(`${PREFIX}/configs/${id}/test`, {})

// ==================== 任务接口 ====================

/** 启动 AI 铺货任务 */
export const createAiListingTask = (
  params: AiListingTaskParams
): Promise<ApiResponse<{ task_id: string; total: number; image_enabled: boolean }>> =>
  post(`${PREFIX}/tasks`, params)

/** 分页查询任务历史 */
export const getAiListingTasks = (page = 1, pageSize = 10, status?: string): Promise<AiListingTaskListResponse> => {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (status) params.append('status', status)
  return get(`${PREFIX}/tasks?${params}`)
}

/** 查询单个任务进度与明细 */
export const getAiListingTask = (taskId: string): Promise<ApiResponse<AiListingTaskDetail>> =>
  get(`${PREFIX}/tasks/${taskId}`)

/** 取消任务 */
export const cancelAiListingTask = (taskId: string): Promise<ApiResponse> =>
  post(`${PREFIX}/tasks/${taskId}/cancel`, {})


