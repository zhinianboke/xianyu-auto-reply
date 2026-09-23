import { getApiClient, extractError } from './client';

// ---------------------------------------------------------------------------
// 类型定义（与任务规格保持一致）
// ---------------------------------------------------------------------------

export interface ListingTask {
  id: number;
  name: string;
  account_ids: string[];
  status: string;
  /** 后端任务无 name 字段，keyword 才是任务的业务标识 */
  keyword?: string;
  /** 监控类型：listing-上新监控，price_drop-降价监控 */
  monitor_type?: string;
  category_id?: number;
  price_min?: number | null;
  price_max?: number | null;
  interval_minutes?: number;
  is_enabled?: boolean;
}

export interface ListingOverview {
  total_tasks: number;
  active_tasks: number;
  total_items: number;
  /** 今日定时/手动执行总次数（后端 today_run_total） */
  today_run_total?: number;
}

/** 监控分类（用于任务的目标分类展示与新建表单选择） */
export interface ListingCategory {
  id: number;
  name: string;
}

/** 新建上新监控任务的入参（仅覆盖后端必填 + 核心可选字段） */
export interface NewListingTask {
  keyword: string;
  categoryId: number;
  /** 执行间隔（分钟），后端要求 ≥ 1 */
  intervalMinutes: number;
  priceMin?: number;
  priceMax?: number;
  enabled?: boolean;
}

export interface MonitoredItem {
  item_id: string;
  title: string;
  price: string;
  status: string;
  /** 商品所属账号（改价等卖家操作需要）；采集接口未返回时为 undefined */
  cookie_id?: string;
}

/** 卡券类型枚举：固定文字/批量数据/API接口/图片 */
export type CardKind = 'api' | 'text' | 'data' | 'image';

/** 卡券 API 配置（type==='api' 时使用）。headers/params 在后端以 JSON 字符串存储。 */
export interface CardApiConfig {
  url: string;
  method: string;
  timeout?: number;
  headers?: string;
  params?: string;
  response_field?: string;
}

/**
 * 卡券完整模型，对齐后端 Card 对象。
 * content/remark 为兼容旧调用方（products 页旧版 cards 子页）的派生字段：
 * - content ← text/data/image 首图/api url 兜底的可展示正文
 * - remark  ← name（展示用名称）
 * 其余字段供多类型编辑表单读写、round-trip 回填。
 */
export interface Card {
  id: number;
  /** 兼容旧 UI：可展示正文 */
  content: string;
  /** 兼容旧 UI：展示用名称（= name） */
  remark?: string;
  name: string;
  type: CardKind;
  text_content?: string;
  data_content?: string;
  api_config?: CardApiConfig | null;
  image_url?: string;
  image_urls: string[];
  enabled: boolean;
  delay_seconds: number;
  use_no_logistics_form: boolean;
  description?: string;
  price?: string;
  is_dockable: boolean;
  fee_payer?: string;
  min_price?: string;
  dock_visibility?: string;
  is_multi_spec: boolean;
  spec_name?: string;
  spec_value?: string;
  delivery_count?: number;
}

/** 新建卡券入参（对齐后端 CardCreate）。name/type 必填，其余可选。 */
export interface CardCreateParams {
  name: string;
  type: CardKind;
  description?: string | null;
  enabled?: boolean;
  delay_seconds?: number;
  use_no_logistics_form?: boolean;
  price?: string | null;
  is_dockable?: boolean;
  fee_payer?: string | null;
  min_price?: string | null;
  dock_visibility?: string | null;
  is_multi_spec?: boolean;
  spec_name?: string | null;
  spec_value?: string | null;
  api_config?: CardApiConfig | null;
  text_content?: string | null;
  data_content?: string | null;
  image_url?: string | null;
  image_urls?: string[] | null;
  item_id?: string | null;
}

/** 更新卡券入参（对齐后端 CardUpdate，全部可选）。 */
export type CardUpdateParams = Partial<CardCreateParams>;

export interface ProductItem {
  item_id: string;
  title: string;
  price: string;
  cookie_id: string;
  item_quantity?: number;
  item_status_desc?: string;
  item_sku_count?: number;
  is_seller_item?: boolean;
  item_shelf_time?: string;
}

export interface DeliveryBlockRule {
  id: number;
  rule_type: string;
  rule_value: string;
  enabled: boolean;
}

// ---------------------------------------------------------------------------
// 通用解析工具
// ---------------------------------------------------------------------------

/**
 * 后端统一响应为 `{ success, message, data }`，抽出内部 data；未包裹则原样返回。
 * 与 accounts.ts / blacklist.ts 中的 unwrapData 保持一致。
 */
function unwrapData<T>(body: unknown): T {
  if (
    body &&
    typeof body === 'object' &&
    'success' in (body as Record<string, unknown>) &&
    'data' in (body as Record<string, unknown>)
  ) {
    const inner = (body as { data: unknown }).data;
    if (inner != null) return inner as T;
  }
  return body as T;
}

/**
 * 从可能被包一层 `{ data: [...] }` / `{ items: [...] }` / 裸数组的响应中取出数组。
 * 兼容 ApiResponse 包裹（先 unwrapData 再取数组）与裸返回两种形态。
 */
function extractArray<T>(
  data: unknown,
  normalize: (raw: Record<string, unknown>) => T,
): T[] {
  const inner = unwrapData<unknown>(data);
  let arr: unknown[] | null = null;
  if (Array.isArray(inner)) {
    arr = inner;
  } else if (inner && typeof inner === 'object') {
    const obj = inner as Record<string, unknown>;
    if (Array.isArray(obj.data)) arr = obj.data;
    else if (Array.isArray(obj.items)) arr = obj.items;
    else if (Array.isArray(obj.list)) arr = obj.list;
    else if (Array.isArray(obj.rules)) arr = obj.rules;
  }
  if (!arr) return [];
  return arr.map((item) => normalize((item ?? {}) as Record<string, unknown>));
}

/** 安全取字符串：null/undefined → fallback */
function str(val: unknown, fallback = ''): string {
  if (val == null) return fallback;
  const s = String(val);
  return s === 'undefined' || s === 'null' ? fallback : s;
}

/** 安全取数字 */
function num(val: unknown, fallback = 0): number {
  if (val == null || val === '') return fallback;
  const n = Number(val);
  return Number.isFinite(n) ? n : fallback;
}

// ---------------------------------------------------------------------------
// 商品监控
// ---------------------------------------------------------------------------

function normalizeTask(raw: Record<string, unknown>): ListingTask {
  const statusRaw = raw.status;
  const status =
    statusRaw != null
      ? String(statusRaw)
      : raw.is_enabled != null
        ? raw.is_enabled
          ? 'active'
          : 'inactive'
        : 'unknown';
  return {
    id: num(raw.id ?? raw.task_id),
    name: str(raw.name ?? raw.task_name),
    account_ids: Array.isArray(raw.account_ids)
      ? raw.account_ids.map((a) => String(a))
      : Array.isArray(raw.cookie_ids)
        ? raw.cookie_ids.map((a) => String(a))
        : [],
    status,
    keyword: str(raw.keyword),
    monitor_type: str(raw.monitor_type, 'listing'),
    category_id: raw.category_id != null ? num(raw.category_id) : undefined,
    price_min: raw.price_min != null ? num(raw.price_min) : null,
    price_max: raw.price_max != null ? num(raw.price_max) : null,
    interval_minutes:
      raw.interval_minutes != null ? num(raw.interval_minutes) : undefined,
    is_enabled:
      raw.is_enabled != null
        ? Boolean(raw.is_enabled)
        : status === 'active',
  };
}

/**
 * 获取商品监控任务列表
 *
 * 后端分页查询（GET /api/v1/product-monitor/listing-tasks），响应包在 ApiResponse 里，
 * 内部 data 可能是 `{ data: [...], total }` 也可能是裸数组，两种都兼容。
 * 这里取首页（page_size 较大）以便一次性拿到全部任务用于展示。
 */
export async function getListingTasks(): Promise<ListingTask[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/product-monitor/listing-tasks',
    { params: { query: { page: 1, page_size: 200 } } },
  )) as { data?: unknown; error?: unknown };
  return extractArray<ListingTask>(data, normalizeTask);
}

function normalizeOverview(raw: Record<string, unknown>): ListingOverview {
  return {
    total_tasks: num(
      raw.total_tasks ?? raw.task_count ?? raw.tasks_total ?? raw.tasks,
    ),
    active_tasks: num(
      raw.active_tasks ??
        raw.enabled_tasks ??
        raw.active_task_count ??
        raw.running_tasks ??
        raw.active_count,
    ),
    total_items: num(
      raw.total_items ?? raw.item_count ?? raw.items_total ?? raw.items,
    ),
    today_run_total: num(raw.today_run_total ?? raw.today_runs),
  };
}

/**
 * 获取商品监控概览统计
 *
 * GET /api/v1/product-monitor/listing-tasks/overview
 * 后端返回任务数、活跃任务数、商品数等统计，包在 ApiResponse 中。
 */
export async function getListingOverview(): Promise<ListingOverview> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/product-monitor/listing-tasks/overview',
  )) as { data?: unknown; error?: unknown };
  const inner = unwrapData<unknown>(data);
  if (inner && typeof inner === 'object') {
    return normalizeOverview(inner as Record<string, unknown>);
  }
  return { total_tasks: 0, active_tasks: 0, total_items: 0 };
}

/** 由采集商品的私信/下单状态派生展示用状态文案 */
function deriveItemStatus(raw: Record<string, unknown>): string {
  const orderState = str(raw.order_state);
  const dmState = str(raw.dm_state);
  if (orderState === 'ordered') return '已下单';
  if (orderState === 'failed') return '下单失败';
  if (orderState === 'duplicate') return '重复下单';
  if (dmState === 'success') return '已私信';
  if (dmState === 'failed') return '私信失败';
  if (dmState === 'pending' || dmState === 'waiting') return '私信中';
  const status = str(raw.status);
  return status || '监控中';
}

function normalizeMonitoredItem(raw: Record<string, unknown>): MonitoredItem {
  return {
    item_id: str(raw.item_id ?? raw.id),
    title: str(raw.title ?? raw.item_title),
    price: str(raw.price ?? raw.item_price, '0'),
    status: deriveItemStatus(raw),
    cookie_id: str(raw.cookie_id ?? raw.account_id) || undefined,
  };
}

/**
 * 获取监控商品项列表
 *
 * GET /api/v1/product-monitor/listing-tasks/items（分页），响应包在 ApiResponse 中。
 * 取首页若干条用于展示最新采集的商品；传入 monitorTaskId 时按任务过滤
 * （后端 query 参数 monitor_task_id）。
 */
export async function getMonitoredItems(
  monitorTaskId?: number,
): Promise<MonitoredItem[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/product-monitor/listing-tasks/items',
    {
      params: {
        query: {
          page: 1,
          page_size: 50,
          ...(monitorTaskId != null
            ? { monitor_task_id: monitorTaskId }
            : {}),
        },
      },
    },
  )) as { data?: unknown; error?: unknown };
  return extractArray<MonitoredItem>(data, normalizeMonitoredItem);
}

// ---------------------------------------------------------------------------
// 上新监控任务管理（新建 / 启停 / 立即执行 / 删除 / 分类）
// ---------------------------------------------------------------------------

/**
 * 断言 ApiResponse 业务成功。后端约定「业务错误也返回 HTTP 200」，
 * 仅凭请求不抛错无法区分成败，需检查 body.success 并抛出 message。
 */
function assertOk(body: unknown): void {
  if (
    body &&
    typeof body === 'object' &&
    (body as Record<string, unknown>).success === false
  ) {
    const msg = str((body as Record<string, unknown>).message);
    throw new Error(msg || '操作失败');
  }
}

/** 获取监控分类列表（GET /api/v1/product-monitor/categories，按用户隔离） */
export async function getListingCategories(): Promise<ListingCategory[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/product-monitor/categories',
  )) as { data?: unknown; error?: unknown };
  return extractArray<ListingCategory>(data, (raw) => ({
    id: num(raw.id),
    name: str(raw.name),
  }));
}

/**
 * 新建上新监控任务
 *
 * POST /api/v1/product-monitor/listing-tasks。后端必填：monitor_type/category_id/
 * keyword/interval_minutes，monitor_type 固定传 'listing'（上新监控）。
 * TODO: 采集账号(account_ids)、下单账号(order_account_ids)、私信内容(dm_content)、
 * 直接下单(direct_order)、代理(proxy_url)、上新天数(publish_days)、采集页数
 * (collect_pages)、备注(remark) 等高级字段待后续版本补充。
 */
export async function createListingTask(input: NewListingTask): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    '/api/v1/product-monitor/listing-tasks',
    {
      body: {
        monitor_type: 'listing',
        category_id: input.categoryId,
        keyword: input.keyword,
        interval_minutes: input.intervalMinutes,
        price_min: input.priceMin ?? null,
        price_max: input.priceMax ?? null,
        is_enabled: input.enabled ?? true,
      },
    },
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
}

/** 启用/停用任务：PUT /api/v1/product-monitor/listing-tasks/{id}/status */
export async function updateListingTaskStatus(
  taskId: number,
  isEnabled: boolean,
): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.PUT as any)(
    `/api/v1/product-monitor/listing-tasks/${taskId}/status`,
    { body: { is_enabled: isEnabled } },
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
}

/**
 * 立即执行任务：POST /api/v1/product-monitor/listing-tasks/{id}/run。
 * 后端要求任务处于启用状态，停用任务会以业务失败返回。
 */
export async function runListingTask(taskId: number): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    `/api/v1/product-monitor/listing-tasks/${taskId}/run`,
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
}

/**
 * 删除任务：后端仅提供批量删除端点 POST /batch-delete，单个删除复用
 * `{ ids: [taskId] }`。
 */
export async function deleteListingTask(taskId: number): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    '/api/v1/product-monitor/listing-tasks/batch-delete',
    { body: { ids: [taskId] } },
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
}

// ---------------------------------------------------------------------------
// 卡券管理
// ---------------------------------------------------------------------------

/** 安全解析 api_config：headers/params 容错对象（JSON.stringify）与字符串两种后端形态。 */
function parseApiConfig(raw: unknown): CardApiConfig | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;
  const headers = r.headers;
  const params = r.params;
  return {
    url: str(r.url),
    method: str(r.method, 'GET') || 'GET',
    timeout: num(r.timeout, 60),
    headers:
      typeof headers === 'string'
        ? headers
        : headers && typeof headers === 'object'
          ? JSON.stringify(headers)
          : '',
    params:
      typeof params === 'string'
        ? params
        : params && typeof params === 'object'
          ? JSON.stringify(params)
          : '',
    response_field: str(r.response_field),
  };
}

/** 解析图片 URL 列表：优先 image_urls 数组，回退单个 image_url。 */
function parseImageUrls(raw: unknown, single?: unknown): string[] {
  if (Array.isArray(raw)) {
    const arr = raw.map((u) => (u == null ? '' : String(u))).filter(Boolean);
    if (arr.length) return arr;
  }
  const one = str(single);
  return one ? [one] : [];
}

/**
 * 卡券归一化：保留后端全部字段供多类型表单读写，同时派生 content/remark
 * 兼容仍消费旧简化模型的调用方（products 页 cards 子页）。
 * - content ← text_content → data_content → 首张图片 → api url（依次兜底）
 * - remark  ← name → remark → description
 */
function normalizeCard(raw: Record<string, unknown>): Card {
  const nameStr = str(raw.name);
  const kind = (str(raw.type, 'text') || 'text') as CardKind;
  const textContent = str(raw.text_content);
  const dataContent = str(raw.data_content);
  const imageUrls = parseImageUrls(raw.image_urls, raw.image_url);
  // content 兜底链，保证旧 UI 永远有可展示正文
  let contentFallback = textContent || dataContent;
  if (!contentFallback) contentFallback = imageUrls[0] || '';
  if (!contentFallback) contentFallback = parseApiConfig(raw.api_config)?.url || '';
  const remarkStr = nameStr || str(raw.remark) || str(raw.description);
  return {
    id: num(raw.id ?? raw.card_id),
    content: contentFallback,
    remark: remarkStr || undefined,
    name: nameStr,
    type: kind,
    text_content: textContent || undefined,
    data_content: dataContent || undefined,
    api_config: parseApiConfig(raw.api_config),
    image_url: str(raw.image_url) || undefined,
    image_urls: imageUrls,
    enabled: raw.enabled != null ? Boolean(raw.enabled) : true,
    delay_seconds: num(raw.delay_seconds, 0),
    use_no_logistics_form: Boolean(raw.use_no_logistics_form),
    description: str(raw.description) || undefined,
    price: str(raw.price) || undefined,
    is_dockable: Boolean(raw.is_dockable),
    fee_payer: str(raw.fee_payer) || undefined,
    min_price: str(raw.min_price) || undefined,
    dock_visibility: str(raw.dock_visibility) || undefined,
    is_multi_spec: Boolean(raw.is_multi_spec),
    spec_name: str(raw.spec_name) || undefined,
    spec_value: str(raw.spec_value) || undefined,
    delivery_count: raw.delivery_count != null ? num(raw.delivery_count) : undefined,
  };
}

/**
 * 获取卡券列表
 *
 * GET /api/v1/cards（分页），响应为裸对象（OpenAPI schema 为空），可能形如
 * `{ data: [...], total }`、`{ items: [...] }` 或被 ApiResponse 包一层，统一兼容。
 * 使用较大 page_size 一次性取回全部卡券。
 */
export async function getCards(): Promise<Card[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/cards', {
    params: { query: { page: 1, page_size: 9999 } },
  })) as { data?: unknown; error?: unknown };
  return extractArray<Card>(data, normalizeCard);
}

/**
 * 新建卡券
 *
 * POST /api/v1/cards。两种调用方式：
 * 1. 完整 params（多类型表单）：createCard({ name, type, text_content, api_config, ... })
 * 2. 兼容旧位置参数（products 页旧版 cards 子页仍在用）：
 *    createCard(content, remark?, useNoLogisticsForm?) —— 退化为 text 卡券。
 * 成功后若响应含新建卡券则返回之，否则用入参回退一个占位 Card（调用方通常会刷新列表）。
 */
export async function createCard(
  params: CardCreateParams | string,
  legacyRemark?: string,
  legacyUseNoLogistics?: boolean,
): Promise<Card> {
  const client = await getApiClient();
  const body: Record<string, unknown> =
    typeof params === 'string'
      ? {
          name: legacyRemark?.trim() || '未命名卡券',
          type: 'text',
          text_content: params,
          description: legacyRemark ?? null,
          use_no_logistics_form: legacyUseNoLogistics ?? false,
        }
      : (params as unknown as Record<string, unknown>);
  const { data } = (await (client.POST as any)('/api/v1/cards', {
    body,
  })) as { data?: unknown; error?: unknown };
  const inner = unwrapData<unknown>(data);
  if (inner && typeof inner === 'object' && (inner as Record<string, unknown>).id != null) {
    return normalizeCard(inner as Record<string, unknown>);
  }
  // 后端未回传完整对象时用入参回退占位，调用方刷新列表即可拿到真实数据
  return normalizeCard(body);
}

/**
 * 更新卡券
 *
 * PUT /api/v1/cards/{card_id}。两种调用方式：
 * 1. 完整 params（多类型表单）：updateCard(id, { name, type, text_content, ... })
 * 2. 兼容旧位置参数（products 页旧版 cards 子页仍在用）：
 *    updateCard(id, content, remark?, useNoLogisticsForm?) —— 退化为 text 字段更新
 *    （与历史行为一致：不传 type，use_no_logistics_form 未传时按 false 处理）。
 */
export async function updateCard(
  cardId: number,
  params: CardUpdateParams | string,
  legacyRemark?: string,
  legacyUseNoLogistics?: boolean,
): Promise<void> {
  const client = await getApiClient();
  const body: Record<string, unknown> =
    typeof params === 'string'
      ? {
          name: legacyRemark?.trim() || '未命名卡券',
          text_content: params,
          description: legacyRemark ?? null,
          use_no_logistics_form: legacyUseNoLogistics ?? false,
        }
      : (params as unknown as Record<string, unknown>);
  await (client.PUT as any)(`/api/v1/cards/${cardId}`, { body });
}

/**
 * 上传卡券图片（multipart/form-data，字段名 image）
 *
 * POST /api/v1/cards/upload-image。复用 chat.ts / product-publish.ts 的 RN FormData
 * 文件上传模式：openapi-fetch 识别 FormData 后交由 fetch 自动设置 boundary，勿手动
 * 指定 Content-Type（手动指定会缺少 boundary 导致后端解析失败）。
 * 后端返回 { success, image_url, message }（可能被 ApiResponse 包一层 data），均兼容。
 * @param uri 本地图片 uri（来自 expo-image-picker）
 * @returns 上传后的图片可访问 URL
 */
export async function uploadCardImage(uri: string): Promise<string> {
  const client = await getApiClient();
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
  const mimeType = typeMap[ext] || 'image/jpeg';
  const formData = new FormData();
  // RN FormData 文件字段需要 { uri, name, type } 结构
  formData.append('image', { uri, name: `image.${ext}`, type: mimeType } as any);

  const { data } = (await (client.POST as any)('/api/v1/cards/upload-image', {
    body: formData,
  })) as { data?: unknown; error?: unknown };

  const inner = unwrapData<unknown>(data);
  const obj = (inner && typeof inner === 'object' ? inner : {}) as Record<string, unknown>;
  const url =
    str(obj.image_url) ||
    (obj.data && typeof obj.data === 'object'
      ? str((obj.data as Record<string, unknown>).image_url)
      : '');
  if (!url) {
    throw new Error(str(obj.message) || '图片上传失败');
  }
  return url;
}

/** 删除卡券：DELETE /api/v1/cards/{card_id} */
export async function deleteCard(cardId: number): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/cards/${cardId}`);
}

// ---------------------------------------------------------------------------
// 商品列表（分页）
// ---------------------------------------------------------------------------

function normalizeProductItem(raw: Record<string, unknown>): ProductItem {
  return {
    item_id: str(raw.item_id ?? raw.id),
    title: str(raw.title ?? raw.item_title),
    price: str(raw.price ?? raw.item_price, '0'),
    cookie_id: str(raw.cookie_id ?? raw.account_id),
  };
}

/**
 * 分页获取商品列表
 *
 * GET /api/v1/items/paginated，响应为裸对象，可能形如
 * `{ data: [...], total }` 或被 ApiResponse 包一层，统一兼容。
 */
export async function getProductItems(
  page: number,
  pageSize: number,
): Promise<{ data: ProductItem[]; total: number }> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/items/paginated', {
    params: { query: { page, page_size: pageSize } },
  })) as { data?: unknown; error?: unknown };
  const inner = unwrapData<unknown>(data);
  let arr: unknown[] = [];
  let total = 0;
  if (Array.isArray(inner)) {
    arr = inner;
    total = inner.length;
  } else if (inner && typeof inner === 'object') {
    const obj = inner as Record<string, unknown>;
    arr = Array.isArray(obj.data)
      ? obj.data
      : Array.isArray(obj.items)
        ? obj.items
        : Array.isArray(obj.list)
          ? obj.list
          : [];
    total = typeof obj.total === 'number' ? obj.total : arr.length;
  }
  return {
    data: arr.map((item) =>
      normalizeProductItem((item ?? {}) as Record<string, unknown>),
    ),
    total,
  };
}

// ---------------------------------------------------------------------------
// 发货规则（禁止发货规则）
// ---------------------------------------------------------------------------

/**
 * 获取账号的禁止发货规则列表
 *
 * 合并两个接口的结果：
 * 1. GET /api/v1/cookies/delivery-block-rules/available —— 全部可用规则定义（用于展示标签）
 * 2. GET /api/v1/cookies/{account_id}/delivery-block-rules —— 账号当前已配置规则（用于 enabled 状态）
 *
 * 后端规则以 `rule_code`（字符串）作为标识，本模块对外暴露为 `rule_type`，
 * 规则展示文案取 name/description 作为 `rule_value`。
 */
export async function getDeliveryBlockRules(
  accountId: string,
): Promise<DeliveryBlockRule[]> {
  const client = await getApiClient();
  const [availRes, acctRes] = await Promise.all([
    (client.GET as any)(
      '/api/v1/cookies/delivery-block-rules/available',
    ) as { data?: unknown; error?: unknown },
    (client.GET as any)(
      `/api/v1/cookies/${accountId}/delivery-block-rules`,
    ) as { data?: unknown; error?: unknown },
  ]);

  const available = extractArray<Record<string, unknown>>(
    availRes.data,
    (r) => r,
  );
  const accountRules = extractArray<Record<string, unknown>>(
    acctRes.data,
    (r) => r,
  );

  // 以 rule_code 为键建立账号 enabled 映射
  const enabledMap = new Map<string, boolean>();
  for (const r of accountRules) {
    const code = str(r.rule_code ?? r.rule_type);
    if (code) enabledMap.set(code, Boolean(r.enabled));
  }

  const result: DeliveryBlockRule[] = [];
  const seen = new Set<string>();
  let id = 0;

  const pushRule = (r: Record<string, unknown>, fallbackEnabled: boolean) => {
    const code = str(r.rule_code ?? r.rule_type);
    if (!code || seen.has(code)) return;
    seen.add(code);
    result.push({
      id: id++,
      rule_type: code,
      rule_value:
        str(r.name ?? r.label ?? r.title ?? r.description).trim() || code,
      enabled: enabledMap.has(code)
        ? Boolean(enabledMap.get(code))
        : fallbackEnabled,
    });
  };

  // 先用 available 提供的标签 + 账号 enabled 状态
  for (const r of available) pushRule(r, false);
  // 再补 available 中缺失但账号已配置的规则
  for (const r of accountRules) pushRule(r, Boolean(r.enabled));

  return result;
}

/**
 * 批量更新账号的禁止发货规则
 *
 * PUT /api/v1/cookies/{account_id}/delivery-block-rules，请求体为
 * `{ rules: [{ rule_code, enabled, ... }] }`（DeliveryBlockRulesUpdate）。
 * 这里仅发送 rule_code + enabled，其余字段由后端补默认值。
 */
export async function updateDeliveryBlockRules(
  accountId: string,
  rules: DeliveryBlockRule[],
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(
    `/api/v1/cookies/${accountId}/delivery-block-rules`,
    {
      body: {
        rules: rules.map((r) => ({
          rule_code: r.rule_type,
          enabled: r.enabled,
        })),
      },
    },
  );
}
