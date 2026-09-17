import { getApiClient } from './client';
import type { QueryButton } from './item-query-config';

const PREFIX = '/api/v1/product-publish';

/** 解开 {success, message, data} 信封（后端业务失败也返回 HTTP 200，靠 success 区分） */
function unwrapData<T>(body: unknown): T {
  if (body && typeof body === 'object' && 'success' in body && 'data' in body) {
    const obj = body as { success: unknown; data: unknown };
    if (obj.success === true || obj.success === 'true') return obj.data as T;
    const msg = (body as { message?: string }).message || '操作失败';
    throw new Error(msg);
  }
  return body as T;
}

/** 从本地 uri 推断扩展名与 MIME 类型 */
function mimeFromUri(uri: string): { name: string; type: string } {
  const ext = (uri.split('.').pop() || 'jpg').toLowerCase().split('?')[0];
  const typeMap: Record<string, string> = {
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    png: 'image/png',
    gif: 'image/gif',
    webp: 'image/webp',
    heic: 'image/heic',
    bmp: 'image/bmp',
  };
  return { name: `image.${ext}`, type: typeMap[ext] || 'image/jpeg' };
}

export interface UploadedImages {
  paths: string[];
  urls: string[];
}

/**
 * 上传商品图片（multipart/form-data，字段名 files，多文件）。
 * 返回 {paths, urls}：paths 是服务器本地绝对路径（发布时传给闲鱼 Playwright 用），
 * urls 是静态预览地址（/static/uploads/products/...，相对路径需拼服务器地址）。
 * RN FormData 文件字段需 { uri, name, type }，openapi-fetch 识别 FormData 后交由 fetch 自动设置 boundary。
 */
export async function uploadProductImages(uris: string[]): Promise<UploadedImages> {
  if (uris.length === 0) return { paths: [], urls: [] };

  const client = await getApiClient();

  const formData = new FormData();
  uris.forEach((uri) => {
    const { name, type } = mimeFromUri(uri);
    formData.append('files', { uri, name, type } as any);
  });

  const { data } = (await (client.POST as any)(`${PREFIX}/upload/images`, {
    body: formData,
  })) as { data?: unknown };

  return unwrapData<UploadedImages>(data);
}

// ==================== 类型 ====================

/**
 * 素材携带的商品列表配置（镜像 xy_catalog_items 配置，发布时一步回写到新商品列表项）。
 * 字段语义与 web/frontend 的商品列表配置一致，CRUD 整体透传，不在 wrapper 拆解。
 */
export interface MaterialItemConfig {
  multi_quantity_delivery: boolean;
  /** 关联卡券 ID 列表（多对多，发布回写时整体覆盖目标商品的卡券关联） */
  card_ids: number[];
  /** 默认回复内容（text 类型；发布回写到 xy_default_replies） */
  default_reply: string;
  /** AI 提示词（发布回写到 xy_catalog_items.ai_prompt） */
  ai_prompt: string;
  /** 查询按钮配置（结构同商品 metadata_json.query_buttons） */
  query_buttons: QueryButton[];
  /** 展示入口配置（结构同商品 metadata_json.display_links） */
  display_links?: any[];
  /** 查询页提示文案（存 metadata_json.page_hint） */
  page_hint?: string;
}

/** 素材创建入参（对齐后端 MaterialCreateRequest，只暴露移动端用到的字段） */
export interface MaterialCreateParams {
  title: string;
  description: string;
  price: number;
  original_price?: number | null;
  category?: string | null;
  /** 服务器本地路径列表（uploadProductImages 返回的 paths），至少 1 张，最多 9 张 */
  images: string[];
  quantity?: number;
  brand?: string | null;
  condition?: string;
  delivery_method?: 'express' | 'pickup';
  shipping_method?: 'free' | 'distance' | 'fixed' | 'template' | 'none';
  support_pickup?: boolean;
  postage?: number;
  address?: string | null;
  remark?: string | null;
  /** 商品列表配置（透传，发布时回写；缺省表示不携带配置） */
  item_config?: MaterialItemConfig | null;
}

/** 素材更新入参（全部可选，未传字段后端保持原值） */
export type MaterialUpdateParams = Partial<MaterialCreateParams>;

/** 素材（批量发布的数据源） */
export interface ProductMaterial {
  id: number;
  title: string;
  description: string;
  price: number;
  original_price?: number | null;
  category?: string | null;
  images: string[];
  quantity: number;
  brand?: string | null;
  condition: string;
  remark?: string | null;
  created_at?: string | null;
  /** 商品列表配置（可能为 null/undefined：旧素材未携带） */
  item_config?: MaterialItemConfig | null;
}

/** 从商品列表项采集出的素材草稿（含 item_config，用于一键初始化素材表单） */
export interface CollectedMaterialDraft {
  title: string;
  description: string;
  price: number | string;
  original_price?: number | null;
  category?: string | null;
  images: string[];
  quantity?: number;
  brand?: string | null;
  condition?: string;
  remark?: string | null;
  item_config?: MaterialItemConfig | null;
}

export interface MaterialsPage {
  list: ProductMaterial[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** 平台分类路径中的一级分类 */
export interface CategoryPathItem {
  id: string;
  name: string;
}

/** 类目推荐候选 */
export interface CategoryCandidate {
  cat_id?: string | null;
  cat_name?: string | null;
  channel_cat_id?: string | null;
  channel_cat_name?: string | null;
  leaf_id?: string | null;
  tb_cat_id?: string | null;
  score?: number | null;
  path?: CategoryPathItem[];
}

export interface CategoryRecommendData {
  candidates: CategoryCandidate[];
  account_id?: string;
}

/** 单品发布入参（对齐后端 PublishSingleRequest） */
export interface PublishSingleParams {
  /** 闲鱼账号 ID（cookie_id），必填 */
  account_id: string;
  title: string;
  description: string;
  price: number;
  original_price?: number | null;
  category?: string | null;
  /** 服务器本地路径列表（uploadProductImages 返回的 paths），至少 1 张 */
  images: string[];
  // 类目推荐回填的平台分类字段
  platform_category_id?: string | null;
  platform_category_name?: string | null;
  platform_channel_category_id?: string | null;
  platform_channel_category_name?: string | null;
  platform_leaf_id?: string | null;
  platform_tb_category_id?: string | null;
  platform_category_path?: CategoryPathItem[];
  category_source?: 'manual' | 'recommendation';
  category_confidence?: number | null;
  quantity?: number;
  stock?: number | null;
  address?: string | null;
  delivery_method?: 'express' | 'pickup';
  shipping_method?: 'free' | 'distance' | 'fixed' | 'template' | 'none';
  support_pickup?: boolean;
  postage?: number;
  brand?: string | null;
  condition?: string;
}

export interface PublishSingleResult {
  item_url?: string | null;
  item_id?: string | null;
  log_id?: number;
  sync_status?: string;
  sync_message?: string | null;
  sync_total_count?: number;
  sync_saved_count?: number;
}

/** 批量发布返回 */
export interface BatchPublishResult {
  batch_id: string;
  total: number;
}

/** 批量进度：单账号维度统计 */
export interface BatchAccountStatus {
  account_id: string;
  total: number;
  success: number;
  failed: number;
  publishing: number;
  pending: number;
  sync_status: 'pending' | 'running' | 'success' | 'failed' | 'skipped' | 'unknown';
  sync_message: string;
  sync_total_count: number;
  sync_saved_count: number;
}

/** 批量进度状态（GET /publish/batch/{id}/status） */
export interface BatchStatus {
  batch_id: string;
  total: number;
  success: number;
  failed: number;
  publishing: number;
  pending: number;
  finished: boolean;
  account_statuses: BatchAccountStatus[];
}

/** 发布日志条目 */
export interface PublishLogItem {
  id: number;
  account_id: string;
  title: string;
  price?: string | null;
  material_id?: number | null;
  batch_id?: string | null;
  status: 'pending' | 'publishing' | 'success' | 'failed';
  item_id?: string | null;
  item_url?: string | null;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PublishLogsPage {
  list: PublishLogItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ==================== 发布接口 ====================

/** 单品发布（同步调用闲鱼发布接口，耗时较长） */
export async function publishSingle(params: PublishSingleParams): Promise<PublishSingleResult> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(`${PREFIX}/publish/single`, {
    body: params,
  })) as { data?: unknown };
  return unwrapData<PublishSingleResult>(data);
}

/** 批量发布（后台异步执行，立即返回 batch_id 供轮询进度） */
export async function publishBatch(
  accountIds: string[],
  materialIds: number[],
): Promise<BatchPublishResult> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(`${PREFIX}/publish/batch`, {
    body: { account_ids: accountIds, material_ids: materialIds },
  })) as { data?: unknown };
  return unwrapData<BatchPublishResult>(data);
}

/**
 * 查询批量发布进度（5 秒轮询直到 finished）。
 * 任务不存在或状态已失效时后端返回 success=false，unwrapData 会 throw。
 */
export async function getBatchStatus(batchId: string): Promise<BatchStatus> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `${PREFIX}/publish/batch/${encodeURIComponent(batchId)}/status`,
  )) as { data?: unknown };
  return unwrapData<BatchStatus>(data);
}

// ==================== 发布日志 ====================

/** 分页查询发布日志（可按账号/状态过滤：pending/publishing/success/failed） */
export async function getPublishLogs(
  page: number = 1,
  pageSize: number = 20,
  accountId?: string,
  status?: string,
): Promise<PublishLogsPage> {
  const client = await getApiClient();
  const query: Record<string, string | number> = { page, page_size: pageSize };
  if (accountId) query.account_id = accountId;
  if (status) query.status = status;

  const { data } = (await (client.GET as any)(`${PREFIX}/logs`, {
    params: { query },
  })) as { data?: unknown };

  const body = unwrapData<Record<string, unknown>>(data);
  const rawList = Array.isArray(body.list) ? (body.list as PublishLogItem[]) : [];
  return {
    list: rawList,
    total: typeof body.total === 'number' ? body.total : rawList.length,
    page: typeof body.page === 'number' ? body.page : page,
    page_size: typeof body.page_size === 'number' ? body.page_size : pageSize,
    total_pages: typeof body.total_pages === 'number' ? body.total_pages : 0,
  };
}

// ==================== 素材库 ====================

/**
 * 宽松解析 item_config：兼容后端返回的 JSON 对象或 JSON 字符串两种形态，
 * 缺字段补默认值。query_buttons 直接透传后端结构（草稿编辑由调用方归一化）。
 */
function normalizeItemConfig(raw: unknown): MaterialItemConfig | null {
  if (raw == null) return null;
  let obj = raw;
  if (typeof raw === 'string') {
    try {
      obj = JSON.parse(raw);
    } catch {
      return null;
    }
  }
  if (!obj || typeof obj !== 'object' || Array.isArray(obj)) return null;
  const r = obj as Record<string, unknown>;
  const cardIds = Array.isArray(r.card_ids)
    ? r.card_ids
        .map((x) => Number(x))
        .filter((n) => Number.isFinite(n) && n > 0)
    : [];
  return {
    multi_quantity_delivery: Boolean(r.multi_quantity_delivery),
    card_ids: cardIds,
    default_reply: typeof r.default_reply === 'string' ? r.default_reply : '',
    ai_prompt: typeof r.ai_prompt === 'string' ? r.ai_prompt : '',
    query_buttons: Array.isArray(r.query_buttons)
      ? (r.query_buttons as QueryButton[])
      : [],
  };
}

/** 分页查询素材列表（可按标题模糊搜索） */
export async function listMaterials(
  page: number = 1,
  pageSize: number = 20,
  title?: string,
): Promise<MaterialsPage> {
  const client = await getApiClient();
  const query: Record<string, string | number> = { page, page_size: pageSize };
  if (title) query.title = title;

  const { data } = (await (client.GET as any)(`${PREFIX}/materials`, {
    params: { query },
  })) as { data?: unknown };

  const body = unwrapData<Record<string, unknown>>(data);
  const rawList = Array.isArray(body.list) ? (body.list as Record<string, unknown>[]) : [];
  // 透传后端字段，仅对 item_config 做容错解析（旧素材无该字段时为 null）
  const list: ProductMaterial[] = rawList.map((it) => ({
    ...(it as unknown as ProductMaterial),
    item_config: normalizeItemConfig(it.item_config),
  }));
  return {
    list,
    total: typeof body.total === 'number' ? body.total : list.length,
    page: typeof body.page === 'number' ? body.page : page,
    page_size: typeof body.page_size === 'number' ? body.page_size : pageSize,
    total_pages: typeof body.total_pages === 'number' ? body.total_pages : 0,
  };
}

/** 获取单个素材详情（含 item_config 全量配置） */
export async function getMaterial(id: number): Promise<ProductMaterial> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(`${PREFIX}/materials/${id}`)) as {
    data?: unknown;
  };
  const body = unwrapData<unknown>(data);
  const raw =
    body && typeof body === 'object' && !Array.isArray(body)
      ? (body as Record<string, unknown>)
      : {};
  return {
    ...(raw as unknown as ProductMaterial),
    id: Number(raw.id ?? id),
    item_config: normalizeItemConfig(raw.item_config),
  };
}

/** 创建素材，返回新素材 ID */
export async function createMaterial(params: MaterialCreateParams): Promise<{ id: number }> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(`${PREFIX}/materials`, {
    body: params,
  })) as { data?: unknown };
  return unwrapData<{ id: number }>(data);
}

/** 更新素材（仅传需变更字段，item_config 整体覆盖） */
export async function updateMaterial(
  id: number,
  params: MaterialUpdateParams,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`${PREFIX}/materials/${id}`, { body: params });
}

/** 删除素材 */
export async function deleteMaterial(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`${PREFIX}/materials/${id}`);
}

/**
 * 从已发布商品列表项采集素材草稿（含 item_config）。
 * 后端: GET /api/v1/product-publish/materials/collect-from-item/{item_id}
 * 配置来源：ai_prompt/metadata/card_ids/default_reply 拼装为 item_config 一并返回。
 */
export async function collectFromItem(itemId: string): Promise<CollectedMaterialDraft> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `/api/v1/product-publish/materials/collect-from-item/${encodeURIComponent(itemId)}`,
  )) as { data?: unknown };
  const body = unwrapData<unknown>(data);
  const raw =
    body && typeof body === 'object' && !Array.isArray(body)
      ? (body as Record<string, unknown>)
      : {};
  return {
    title: String(raw.title ?? raw.item_title ?? ''),
    description: String(raw.description ?? ''),
    price: (raw.price != null
      ? raw.price
      : raw.item_price != null
        ? raw.item_price
        : 0) as number | string,
    original_price:
      raw.original_price != null ? Number(raw.original_price) : null,
    category: raw.category != null ? String(raw.category) : null,
    images: Array.isArray(raw.images) ? (raw.images as unknown[]).map(String) : [],
    quantity: raw.quantity != null ? Number(raw.quantity) : undefined,
    brand: raw.brand != null ? String(raw.brand) : null,
    condition: typeof raw.condition === 'string' ? raw.condition : undefined,
    remark: raw.remark != null ? String(raw.remark) : null,
    item_config: normalizeItemConfig(raw.item_config),
  };
}

// ==================== 类目推荐 ====================

/** 按标题和描述推荐闲鱼平台分类（可指定账号，缺省由后端自动轮换） */
export async function recommendCategory(params: {
  title: string;
  description: string;
  account_id?: string;
}): Promise<CategoryRecommendData> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(`${PREFIX}/category/recommend`, {
    body: params,
  })) as { data?: unknown };
  const body = unwrapData<Record<string, unknown>>(data);
  return {
    candidates: Array.isArray(body.candidates) ? (body.candidates as CategoryCandidate[]) : [],
    account_id: typeof body.account_id === 'string' ? body.account_id : undefined,
  };
}
