import { getApiClient } from './client';

const PREFIX = '/api/v1/ai-listing';

/** 解开 {success, message, data} 信封（后端业务失败也返回 HTTP 200，靠 success 区分） */
function unwrapData<T>(body: unknown): T {
  if (body && typeof body === 'object' && 'success' in body && 'data' in body) {
    const obj = body as { success: unknown; data: unknown };
    if (obj.success === true || obj.success === 'true') return obj.data as T;
    // 业务失败：抛出 message
    const msg = (body as { message?: string }).message || '操作失败';
    throw new Error(msg);
  }
  return body as T;
}

// ==================== 类型 ====================

export interface AiListingConfig {
  id: number;
  name: string;
  provider_type: string;
  text_base_url: string;
  text_api_key_masked: string;
  text_model: string;
  text_temperature: number;
  text_max_tokens: number;
  prompt_template: string;
  image_enabled: boolean;
  image_base_url: string;
  image_api_key_masked: string;
  has_image_api_key: boolean;
  image_model: string;
  image_size: string;
  image_count: number;
  created_at: string | null;
  updated_at: string | null;
}

export interface AiListingConfigParams {
  name: string;
  provider_type?: string;
  text_base_url: string;
  text_api_key: string; // 创建必填非空；编辑留空=不修改
  text_model: string;
  text_temperature?: number;
  text_max_tokens?: number;
  prompt_template?: string;
  image_enabled: boolean;
  image_base_url?: string;
  image_api_key: string; // 启用时创建必填，编辑可空
  image_model?: string;
  image_size?: string;
  image_count?: number;
}

export interface AiListingMaterialDefaults {
  category?: string;
  condition?: string;
  brand?: string;
  quantity?: number;
  delivery_method?: 'express' | 'pickup';
  shipping_method?: 'free' | 'distance' | 'fixed' | 'template' | 'none';
  support_pickup?: boolean;
  postage?: number;
  address?: string;
  remark?: string;
  images: string[]; // 未启用 AI 图片时必须至少 1 张
}

export interface AiListingTaskParams {
  config_id: number;
  keyword: string;
  count: number; // 1~50
  price_mode: 'fixed' | 'range';
  price?: number;
  price_min?: number;
  price_max?: number;
  image_enabled?: boolean;
  material_defaults: AiListingMaterialDefaults;
}

export interface AiListingTaskItem {
  seq: number;
  status: 'pending' | 'running' | 'success' | 'failed';
  title: string;
  material_id: number | null;
  image_count: number;
  error_message: string;
}

export interface AiListingTask {
  task_id: string;
  config_id: number;
  config_name: string;
  keyword: string;
  total: number;
  success: number;
  failed: number;
  status: 'pending' | 'running' | 'success' | 'partial' | 'failed' | 'canceled';
  finished: boolean;
  progress_percent: number;
  error_message: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string | null;
}

export interface AiListingTaskDetail extends AiListingTask {
  items: AiListingTaskItem[];
}

interface Paged<T> { list: T[]; total: number; page: number; page_size: number; total_pages: number; }

// ==================== 配置接口 ====================

export async function getAiListingConfigs(page = 1, pageSize = 20, name?: string): Promise<Paged<AiListingConfig>> {
  const client = await getApiClient();
  const query: Record<string, string> = { page: String(page), page_size: String(pageSize) };
  if (name) query.name = name;
  const { data } = (await (client.GET as any)(`${PREFIX}/configs`, { params: { query } })) as { data?: unknown };
  return unwrapData<Paged<AiListingConfig>>(data) ?? { list: [], total: 0, page, page_size: pageSize, total_pages: 0 };
}

export async function createAiListingConfig(params: AiListingConfigParams): Promise<number> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(`${PREFIX}/configs`, { body: params })) as { data?: unknown };
  const r = unwrapData<{ id: number }>(data);
  return r.id;
}

export async function updateAiListingConfig(id: number, params: AiListingConfigParams): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`${PREFIX}/configs/${id}`, { body: params });
}

export async function deleteAiListingConfig(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`${PREFIX}/configs/${id}`);
}

export async function getAiListingModels(req: {
  provider_type?: string;
  base_url: string;
  api_key?: string;
  config_id?: number;
}): Promise<Array<{ id: string; name?: string }>> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(`${PREFIX}/configs/models`, { body: req })) as { data?: unknown };
  const r = unwrapData<{ models: Array<{ id: string; name?: string }> }>(data);
  return r?.models ?? [];
}

export async function testAiListingConfig(id: number): Promise<string> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(`${PREFIX}/configs/${id}/test`, { body: {} })) as { data?: unknown };
  const r = unwrapData<{ reply: string }>(data);
  return r?.reply ?? '';
}

// ==================== 任务接口 ====================

export async function createAiListingTask(params: AiListingTaskParams): Promise<{ task_id: string; total: number; image_enabled: boolean }> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(`${PREFIX}/tasks`, { body: params })) as { data?: unknown };
  return unwrapData<{ task_id: string; total: number; image_enabled: boolean }>(data);
}

export async function getAiListingTasks(page = 1, pageSize = 10, status?: string): Promise<Paged<AiListingTask>> {
  const client = await getApiClient();
  const query: Record<string, string> = { page: String(page), page_size: String(pageSize) };
  if (status) query.status = status;
  const { data } = (await (client.GET as any)(`${PREFIX}/tasks`, { params: { query } })) as { data?: unknown };
  return unwrapData<Paged<AiListingTask>>(data) ?? { list: [], total: 0, page, page_size: pageSize, total_pages: 0 };
}

export async function getAiListingTask(taskId: string): Promise<AiListingTaskDetail> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(`${PREFIX}/tasks/${taskId}`)) as { data?: unknown };
  return unwrapData<AiListingTaskDetail>(data);
}

export async function cancelAiListingTask(taskId: string): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)(`${PREFIX}/tasks/${taskId}/cancel`, { body: {} });
}
