import { getApiClient } from './client';
import { ApiError } from './errors';
import type { ListingCategory } from './products';

// ---------------------------------------------------------------------------
// 商品监控扩展（分类管理 / 执行日志 / 兜底账号）
//
// 端点均挂在 /api/v1/product-monitor 下（与 listing-tasks 平级）：
// - categories                  分类 CRUD
// - listing-tasks/logs          执行日志分页/清空
// - collect-fallback-accounts   兜底采集账号（按分类）
// - order-fallback-accounts     兜底下单账号（按分类）
// 分类列表复用 products.ts 的 getListingCategories。
// ---------------------------------------------------------------------------

/** 判断错误是否为「后端无此端点」（旧版后端 404），供页面提示升级后端 */
export function isEndpointMissing(error: unknown): boolean {
  if (error instanceof ApiError) {
    return error.status === 404 || /\b404\b|not found/i.test(error.message);
  }
  const msg = error instanceof Error ? error.message : String(error);
  return /\b404\b|not found/i.test(msg);
}

// ---------------------------------------------------------------------------
// 类型定义
// ---------------------------------------------------------------------------

export type { ListingCategory };

/** 监控任务下拉选项（GET /listing-tasks/options，用于日志页按任务筛选） */
export interface MonitorTaskOption {
  id: number;
  keyword: string;
  monitor_type: string;
}

/** 监控执行日志（GET /listing-tasks/logs，字段见后端 _log_to_dict） */
export interface MonitorLog {
  id: number;
  monitor_task_id: number | null;
  monitor_type: string;
  keyword: string;
  trigger_type: string;
  account_id: string;
  used_account_ids: string[];
  pages: number;
  fetched_count: number;
  inserted_count: number;
  updated_count: number;
  /** success / partial / failed */
  status: string;
  message: string;
  created_at: string;
}

/** 兜底账号配置（collect/order 共用结构，每用户每分类一条；category_id=null 为无分类全局兜底） */
export interface FallbackConfig {
  id: number | null;
  owner_id: number | null;
  owner_username: string | null;
  category_id: number | null;
  category_name: string | null;
  account_ids: string[];
  /** 后端附带的有效性信息；旧版后端可能缺失 */
  accounts?: FallbackAccountValidity[];
  created_at: string | null;
  updated_at: string | null;
}

export interface FallbackAccountValidity {
  account_id: string;
  valid: boolean;
  reason: string | null;
}

/** 兜底账号配置类型：collect-采集账号，order-下单账号 */
export type FallbackKind = 'collect' | 'order';

// ---------------------------------------------------------------------------
// 通用解析工具（与 products.ts 中的私有实现保持一致）
// ---------------------------------------------------------------------------

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

function str(val: unknown, fallback = ''): string {
  if (val == null) return fallback;
  const s = String(val);
  return s === 'undefined' || s === 'null' ? fallback : s;
}

function num(val: unknown, fallback = 0): number {
  if (val == null || val === '') return fallback;
  const n = Number(val);
  return Number.isFinite(n) ? n : fallback;
}

function strArray(val: unknown): string[] {
  return Array.isArray(val) ? val.map((v) => str(v)).filter(Boolean) : [];
}

/** 断言 ApiResponse 业务成功（后端约定业务错误也返回 HTTP 200） */
function assertOk(body: unknown): void {
  if (
    body &&
    typeof body === 'object' &&
    (body as Record<string, unknown>).success === false
  ) {
    throw new Error(str((body as Record<string, unknown>).message, '操作失败'));
  }
}

// ---------------------------------------------------------------------------
// 监控分类（/product-monitor/categories）
// ---------------------------------------------------------------------------

/** 新建分类：POST /product-monitor/categories，名称同用户下不可重复 */
export async function createListingCategory(name: string): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    '/api/v1/product-monitor/categories',
    { body: { name } },
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
}

/** 修改分类名称：PUT /product-monitor/categories/{id} */
export async function updateListingCategory(
  categoryId: number,
  name: string,
): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.PUT as any)(
    `/api/v1/product-monitor/categories/${categoryId}`,
    { body: { name } },
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
}

/**
 * 删除分类：DELETE /product-monitor/categories/{id}（软删除）。
 * 有关联监控任务或兜底配置时后端业务失败，message 会说明原因，直接抛给页面展示。
 */
export async function deleteListingCategory(categoryId: number): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.DELETE as any)(
    `/api/v1/product-monitor/categories/${categoryId}`,
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
}

// ---------------------------------------------------------------------------
// 监控日志（/product-monitor/listing-tasks/logs）
// ---------------------------------------------------------------------------

function normalizeTaskOption(raw: Record<string, unknown>): MonitorTaskOption {
  return {
    id: num(raw.id),
    keyword: str(raw.keyword),
    monitor_type: str(raw.monitor_type, 'listing'),
  };
}

/** 监控任务下拉选项（GET /listing-tasks/options），用于日志/商品页按任务筛选 */
export async function getMonitorTaskOptions(): Promise<MonitorTaskOption[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/product-monitor/listing-tasks/options',
  )) as { data?: unknown; error?: unknown };
  const inner = unwrapData<unknown>(data);
  let arr: unknown[] = [];
  if (Array.isArray(inner)) arr = inner;
  else if (inner && typeof inner === 'object' && Array.isArray((inner as Record<string, unknown>).list)) {
    arr = (inner as Record<string, unknown>).list as unknown[];
  }
  return arr.map((raw) =>
    normalizeTaskOption((raw ?? {}) as Record<string, unknown>),
  );
}

export interface MonitorLogQuery {
  page: number;
  pageSize: number;
  /** 按监控任务筛选 */
  monitorTaskId?: number;
  /** 按执行状态筛选：success/partial/failed */
  status?: string;
  /** 按监控类型筛选：listing/price_drop */
  monitorType?: string;
}

function normalizeLog(raw: Record<string, unknown>): MonitorLog {
  return {
    id: num(raw.id),
    monitor_task_id: raw.monitor_task_id != null ? num(raw.monitor_task_id) : null,
    monitor_type: str(raw.monitor_type, 'listing'),
    keyword: str(raw.keyword),
    trigger_type: str(raw.trigger_type),
    account_id: str(raw.account_id),
    used_account_ids: strArray(raw.used_account_ids),
    pages: num(raw.pages),
    fetched_count: num(raw.fetched_count),
    inserted_count: num(raw.inserted_count),
    updated_count: num(raw.updated_count),
    status: str(raw.status),
    message: str(raw.message),
    created_at: str(raw.created_at),
  };
}

/** 分页查询监控执行日志：GET /listing-tasks/logs，data 为 { list, total, page, ... } */
export async function getMonitorLogs(
  query: MonitorLogQuery,
): Promise<{ list: MonitorLog[]; total: number }> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/product-monitor/listing-tasks/logs',
    {
      params: {
        query: {
          page: query.page,
          page_size: query.pageSize,
          ...(query.monitorTaskId != null
            ? { monitor_task_id: query.monitorTaskId }
            : {}),
          ...(query.status ? { status: query.status } : {}),
          ...(query.monitorType ? { monitor_type: query.monitorType } : {}),
        },
      },
    },
  )) as { data?: unknown; error?: unknown };
  const inner = unwrapData<Record<string, unknown>>(data);
  const obj =
    inner && typeof inner === 'object' ? (inner as Record<string, unknown>) : {};
  const rawList = Array.isArray(obj.list)
    ? obj.list
    : Array.isArray(inner)
      ? (inner as unknown[])
      : [];
  return {
    list: rawList.map((raw) =>
      normalizeLog((raw ?? {}) as Record<string, unknown>),
    ),
    total: num(obj.total, rawList.length),
  };
}

/**
 * 清空监控日志：DELETE /listing-tasks/logs/clear。
 * 后端仅删除 10 天前的记录（LOG_RETENTION_DAYS），返回删除条数。
 */
export async function clearMonitorLogs(): Promise<number> {
  const client = await getApiClient();
  const { data } = (await (client.DELETE as any)(
    '/api/v1/product-monitor/listing-tasks/logs/clear',
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
  const inner = unwrapData<Record<string, unknown>>(data);
  if (inner && typeof inner === 'object') {
    return num((inner as Record<string, unknown>).deleted_count);
  }
  return 0;
}

// ---------------------------------------------------------------------------
// 兜底账号（/product-monitor/{collect,order}-fallback-accounts，按分类）
// ---------------------------------------------------------------------------

function fallbackPath(kind: FallbackKind): string {
  return `/api/v1/product-monitor/${kind === 'order' ? 'order' : 'collect'}-fallback-accounts`;
}

function normalizeFallbackConfig(raw: Record<string, unknown>): FallbackConfig {
  const accountsRaw = Array.isArray(raw.accounts) ? raw.accounts : [];
  return {
    id: raw.id != null ? num(raw.id) : null,
    owner_id: raw.owner_id != null ? num(raw.owner_id) : null,
    owner_username: str(raw.owner_username) || null,
    category_id: raw.category_id != null ? num(raw.category_id) : null,
    category_name: str(raw.category_name) || null,
    account_ids: strArray(raw.account_ids),
    accounts: accountsRaw.map((a) => {
      const o = (a ?? {}) as Record<string, unknown>;
      return {
        account_id: str(o.account_id),
        valid: Boolean(o.valid),
        reason: str(o.reason) || null,
      };
    }),
    created_at: str(raw.created_at) || null,
    updated_at: str(raw.updated_at) || null,
  };
}

/** 列出兜底账号配置（GET，按分类；管理员返回全部用户配置） */
export async function getFallbackConfigs(
  kind: FallbackKind,
): Promise<FallbackConfig[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(fallbackPath(kind))) as {
    data?: unknown;
    error?: unknown;
  };
  const inner = unwrapData<unknown>(data);
  const arr = Array.isArray(inner)
    ? inner
    : inner && typeof inner === 'object' && Array.isArray((inner as Record<string, unknown>).list)
      ? ((inner as Record<string, unknown>).list as unknown[])
      : [];
  return arr.map((raw) =>
    normalizeFallbackConfig((raw ?? {}) as Record<string, unknown>),
  );
}

/**
 * 保存某分类的兜底账号配置：PUT（upsert，同分类仅一条）。
 * categoryId 传 null 表示「无分类全局兜底」；accountIds 可为空数组（即清空选择）。
 */
export async function saveFallbackConfig(
  kind: FallbackKind,
  categoryId: number | null,
  accountIds: string[],
): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.PUT as any)(fallbackPath(kind), {
    body: { category_id: categoryId, account_ids: accountIds },
  })) as { data?: unknown; error?: unknown };
  assertOk(data);
}

/** 删除某分类的兜底账号配置：DELETE（软删除），categoryId 传 null 删无分类那条 */
export async function deleteFallbackConfig(
  kind: FallbackKind,
  categoryId: number | null,
): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.DELETE as any)(fallbackPath(kind), {
    params: { query: categoryId != null ? { category_id: categoryId } : {} },
  })) as { data?: unknown; error?: unknown };
  assertOk(data);
}

// ---------------------------------------------------------------------------
// 监控任务完整字段（/product-monitor/listing-tasks）
//
// 后端 _task_to_dict 返回全部字段；products.ts 的 getListingTask 仅映射子集，
// 这里提供完整版建/改任务与批量操作，供 listing-monitor 页面使用。
// ---------------------------------------------------------------------------

/** 监控类型：listing-上新监控，price_drop-降价监控 */
export type MonitorType = 'listing' | 'price_drop';

/** 监控任务完整模型（后端 _task_to_dict 全字段） */
export interface MonitorTaskFull {
  id: number;
  owner_id: number | null;
  category_id: number | null;
  monitor_type: string;
  keyword: string;
  price_min: number | null;
  price_max: number | null;
  /** 上新天数筛选（publishDays，天，null=不限/最新） */
  publish_days: number | null;
  interval_minutes: number;
  collect_pages: number;
  proxy_url: string | null;
  /** 采集账号ID列表 */
  account_ids: string[];
  /** 下单账号ID列表（私信与下单共用） */
  order_account_ids: string[];
  /** 私信内容（配置下单账号后必填） */
  dm_content: string | null;
  dm_batch_size: number;
  order_batch_size: number;
  /** 采集后直接下单 */
  direct_order: boolean;
  is_enabled: boolean;
  last_run_at: string | null;
  remark: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** 新建/更新监控任务入参（对齐后端 ListingMonitorCreate/UpdateRequest） */
export interface MonitorTaskPayload {
  monitor_type: MonitorType | string;
  category_id: number;
  keyword: string;
  price_min?: number | null;
  price_max?: number | null;
  /** 上新天数筛选：仅 listing 类型有效，null=最新（不限天数） */
  publish_days?: number | null;
  interval_minutes: number;
  collect_pages?: number;
  proxy_url?: string | null;
  account_ids?: string[];
  order_account_ids?: string[] | null;
  dm_content?: string | null;
  dm_batch_size?: number;
  order_batch_size?: number;
  direct_order?: boolean;
  is_enabled?: boolean;
  remark?: string | null;
}

function normalizeTaskFull(raw: Record<string, unknown>): MonitorTaskFull {
  return {
    id: num(raw.id),
    owner_id: raw.owner_id != null ? num(raw.owner_id) : null,
    category_id: raw.category_id != null ? num(raw.category_id) : null,
    monitor_type: str(raw.monitor_type, 'listing'),
    keyword: str(raw.keyword),
    price_min: raw.price_min != null ? num(raw.price_min) : null,
    price_max: raw.price_max != null ? num(raw.price_max) : null,
    publish_days: raw.publish_days != null ? num(raw.publish_days) : null,
    interval_minutes: num(raw.interval_minutes, 1),
    collect_pages: num(raw.collect_pages, 1),
    proxy_url: str(raw.proxy_url) || null,
    account_ids: strArray(raw.account_ids),
    order_account_ids: strArray(raw.order_account_ids),
    dm_content: str(raw.dm_content) || null,
    dm_batch_size: num(raw.dm_batch_size, 5),
    order_batch_size: num(raw.order_batch_size, 5),
    direct_order: Boolean(raw.direct_order),
    is_enabled: raw.is_enabled != null ? Boolean(raw.is_enabled) : true,
    last_run_at: str(raw.last_run_at) || null,
    remark: str(raw.remark) || null,
    created_at: str(raw.created_at) || null,
    updated_at: str(raw.updated_at) || null,
  };
}

/**
 * 获取监控任务列表（完整字段版）
 *
 * GET /listing-tasks（分页），data 为 { list, total }，元素为 _task_to_dict 全字段。
 * 取较大 page_size 一次拿全，用于任务卡片展示与编辑表单回填。
 */
export async function getMonitorTasksFull(): Promise<MonitorTaskFull[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/product-monitor/listing-tasks',
    { params: { query: { page: 1, page_size: 200 } } },
  )) as { data?: unknown; error?: unknown };
  const inner = unwrapData<unknown>(data);
  let arr: unknown[] = [];
  if (Array.isArray(inner)) arr = inner;
  else if (inner && typeof inner === 'object' && Array.isArray((inner as Record<string, unknown>).list)) {
    arr = (inner as Record<string, unknown>).list as unknown[];
  }
  return arr.map((raw) =>
    normalizeTaskFull((raw ?? {}) as Record<string, unknown>),
  );
}

/**
 * 新建监控任务（完整字段版，替代 products.ts 的 createListingTask）
 *
 * POST /listing-tasks。后端必填：monitor_type/category_id/keyword/interval_minutes；
 * 配置下单账号后 dm_content 必填（或开启 direct_order）。返回新建的任务（可能缺失）。
 */
export async function createMonitorTask(
  payload: MonitorTaskPayload,
): Promise<MonitorTaskFull | null> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    '/api/v1/product-monitor/listing-tasks',
    { body: payload },
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
  const inner = unwrapData<unknown>(data);
  if (
    inner &&
    typeof inner === 'object' &&
    (inner as Record<string, unknown>).task &&
    typeof (inner as Record<string, unknown>).task === 'object'
  ) {
    return normalizeTaskFull(
      (inner as Record<string, unknown>).task as Record<string, unknown>,
    );
  }
  return null;
}

/**
 * 更新监控任务：PUT /listing-tasks/{id}，body 仅传需要修改的字段
 * （后端 exclude_unset + partial 校验）。返回更新后的任务（可能缺失）。
 */
export async function updateMonitorTask(
  taskId: number,
  payload: Partial<MonitorTaskPayload>,
): Promise<MonitorTaskFull | null> {
  const client = await getApiClient();
  const { data } = (await (client.PUT as any)(
    `/api/v1/product-monitor/listing-tasks/${taskId}`,
    { body: payload },
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
  const inner = unwrapData<unknown>(data);
  if (
    inner &&
    typeof inner === 'object' &&
    (inner as Record<string, unknown>).task &&
    typeof (inner as Record<string, unknown>).task === 'object'
  ) {
    return normalizeTaskFull(
      (inner as Record<string, unknown>).task as Record<string, unknown>,
    );
  }
  return null;
}

/** 批量结果（success_count/total_count） */
export interface BatchResult {
  success_count: number;
  total_count: number;
}

function toBatchResult(data: unknown, fallbackTotal: number): BatchResult {
  const inner = unwrapData<Record<string, unknown>>(data);
  const obj = inner && typeof inner === 'object' ? inner : {};
  return {
    success_count: num(obj.success_count),
    total_count: num(obj.total_count, fallbackTotal),
  };
}

/** 批量删除监控任务：POST /listing-tasks/batch-delete，body { ids } */
export async function batchDeleteMonitorTasks(
  ids: number[],
): Promise<BatchResult> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    '/api/v1/product-monitor/listing-tasks/batch-delete',
    { body: { ids } },
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
  return toBatchResult(data, ids.length);
}

/**
 * 批量修改监控任务账号：POST /listing-tasks/batch-update-accounts。
 * field: account_ids-采集账号，order_account_ids-下单账号。
 */
export async function batchUpdateMonitorAccounts(
  ids: number[],
  field: 'account_ids' | 'order_account_ids',
  accountIds: string[],
): Promise<BatchResult> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    '/api/v1/product-monitor/listing-tasks/batch-update-accounts',
    { body: { ids, field, account_ids: accountIds } },
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
  return toBatchResult(data, ids.length);
}

/** 批量修改监控任务分类：POST /listing-tasks/batch-update-category */
export async function batchUpdateMonitorCategory(
  ids: number[],
  categoryId: number,
): Promise<BatchResult> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    '/api/v1/product-monitor/listing-tasks/batch-update-category',
    { body: { ids, category_id: categoryId } },
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
  return toBatchResult(data, ids.length);
}

/** 批量修改监控任务私信内容：POST /listing-tasks/batch-update-dm-content */
export async function batchUpdateMonitorDmContent(
  ids: number[],
  dmContent: string,
): Promise<BatchResult> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    '/api/v1/product-monitor/listing-tasks/batch-update-dm-content',
    { body: { ids, dm_content: dmContent } },
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
  return toBatchResult(data, ids.length);
}

// ---------------------------------------------------------------------------
// 采集商品（/product-monitor/listing-tasks/items）
// ---------------------------------------------------------------------------

/** 采集商品（后端 _item_to_dict 全字段，详情接口额外含 detail_json/raw_json） */
export interface MonitorItem {
  id: number;
  monitor_task_id: number | null;
  monitor_task_keyword: string | null;
  item_id: string;
  title: string;
  price: string;
  area: string;
  pic_url: string;
  seller_id: string;
  seller_user_id: string;
  seller_nick: string;
  want_count: number;
  tags: string;
  publish_time: string | null;
  target_url: string;
  has_detail: boolean;
  /** filled/pending/failed */
  seller_fill_status: string;
  seller_fill_fail_reason: string;
  is_dm_sent: boolean;
  dm_account_id: string;
  dm_chat_id: string;
  /** not_sent/waiting/pending/success/failed */
  dm_status: string;
  dm_fail_reason: string;
  dm_attempts: number;
  is_ordered: boolean;
  order_id: string;
  order_account_id: string;
  /** not_ordered/ordered/failed/no_account/duplicate */
  order_status: string;
  order_fail_reason: string;
  order_attempts: number;
  ordered_at: string | null;
  last_seen_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** 采集商品列表筛选（字段见后端 GET /items Query 参数） */
export interface MonitorItemQuery {
  page: number;
  pageSize: number;
  monitorTaskId?: number;
  /** 商品标题关键字 */
  keyword?: string;
  area?: string;
  sellerNick?: string;
  /** 商品ID精确筛选 */
  itemId?: string;
  sellerFill?: string;
  /** 是否已获取详情 */
  hasDetail?: boolean;
  /** 私信状态：not_sent/waiting/pending/success/failed */
  dmState?: string;
  /** 下单状态：not_ordered/ordered/failed/no_account/duplicate */
  orderState?: string;
  /** 采集时间区间（北京时间 YYYY-MM-DDTHH:mm） */
  createdStart?: string;
  createdEnd?: string;
}

function normalizeItem(raw: Record<string, unknown>): MonitorItem {
  return {
    id: num(raw.id),
    monitor_task_id: raw.monitor_task_id != null ? num(raw.monitor_task_id) : null,
    monitor_task_keyword: str(raw.monitor_task_keyword) || null,
    item_id: str(raw.item_id),
    title: str(raw.title),
    price: str(raw.price, '0'),
    area: str(raw.area),
    pic_url: str(raw.pic_url),
    seller_id: str(raw.seller_id),
    seller_user_id: str(raw.seller_user_id),
    seller_nick: str(raw.seller_nick),
    want_count: num(raw.want_count),
    tags: str(raw.tags),
    publish_time: str(raw.publish_time) || null,
    target_url: str(raw.target_url),
    has_detail: Boolean(raw.has_detail),
    seller_fill_status: str(raw.seller_fill_status),
    seller_fill_fail_reason: str(raw.seller_fill_fail_reason),
    is_dm_sent: Boolean(raw.is_dm_sent),
    dm_account_id: str(raw.dm_account_id),
    dm_chat_id: str(raw.dm_chat_id),
    dm_status: str(raw.dm_status, 'not_sent'),
    dm_fail_reason: str(raw.dm_fail_reason),
    dm_attempts: num(raw.dm_attempts),
    is_ordered: Boolean(raw.is_ordered),
    order_id: str(raw.order_id),
    order_account_id: str(raw.order_account_id),
    order_status: str(raw.order_status, 'not_ordered'),
    order_fail_reason: str(raw.order_fail_reason),
    order_attempts: num(raw.order_attempts),
    ordered_at: str(raw.ordered_at) || null,
    last_seen_at: str(raw.last_seen_at) || null,
    created_at: str(raw.created_at) || null,
    updated_at: str(raw.updated_at) || null,
  };
}

/** 分页查询采集商品：GET /listing-tasks/items，data 为 { list, total, ... } */
export async function getMonitorItems(
  query: MonitorItemQuery,
): Promise<{ list: MonitorItem[]; total: number }> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/product-monitor/listing-tasks/items',
    {
      params: {
        query: {
          page: query.page,
          page_size: query.pageSize,
          ...(query.monitorTaskId != null
            ? { monitor_task_id: query.monitorTaskId }
            : {}),
          ...(query.keyword ? { keyword: query.keyword } : {}),
          ...(query.area ? { area: query.area } : {}),
          ...(query.sellerNick ? { seller_nick: query.sellerNick } : {}),
          ...(query.itemId ? { item_id: query.itemId } : {}),
          ...(query.sellerFill ? { seller_fill: query.sellerFill } : {}),
          ...(query.hasDetail != null ? { has_detail: query.hasDetail } : {}),
          ...(query.dmState ? { dm_state: query.dmState } : {}),
          ...(query.orderState ? { order_state: query.orderState } : {}),
          ...(query.createdStart ? { created_start: query.createdStart } : {}),
          ...(query.createdEnd ? { created_end: query.createdEnd } : {}),
        },
      },
    },
  )) as { data?: unknown; error?: unknown };
  const inner = unwrapData<Record<string, unknown>>(data);
  const obj = inner && typeof inner === 'object' ? inner : {};
  const rawList = Array.isArray(obj.list)
    ? obj.list
    : Array.isArray(inner)
      ? (inner as unknown[])
      : [];
  return {
    list: rawList.map((raw) =>
      normalizeItem((raw ?? {}) as Record<string, unknown>),
    ),
    total: num(obj.total, rawList.length),
  };
}

/** 批量重置「私信失败」采集商品为未私信：POST /listing-tasks/items/reset-dm */
export async function resetMonitorItemsDm(ids: number[]): Promise<BatchResult> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    '/api/v1/product-monitor/listing-tasks/items/reset-dm',
    { body: { ids } },
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
  return toBatchResult(data, ids.length);
}

/**
 * 查询单条采集商品完整信息：GET /listing-tasks/items/{pk}，data 为 { item }。
 * 业务失败（不存在）抛错。
 */
export async function getMonitorItemDetail(pk: number): Promise<MonitorItem> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `/api/v1/product-monitor/listing-tasks/items/${pk}`,
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
  const inner = unwrapData<Record<string, unknown>>(data);
  const item =
    inner && typeof inner === 'object'
      ? (inner as Record<string, unknown>).item
      : null;
  if (!item || typeof item !== 'object') {
    throw new Error('采集商品不存在');
  }
  return normalizeItem(item as Record<string, unknown>);
}

// ---------------------------------------------------------------------------
// 监控日志复制账号Cookies（POST /listing-tasks/logs/copy-cookies）
// ---------------------------------------------------------------------------

/** 复制Cookies返回的单条账号信息（account_id/cookies/secret_key） */
export interface MonitorLogCookie {
  account_id: string;
  cookies: string;
  secret_key: string;
}

/**
 * 汇总选中监控日志涉及账号（去重）的 Cookie 与分销秘钥：
 * POST /listing-tasks/logs/copy-cookies，body { ids }，data 为 { list }。
 * 返回空数组表示选中日志没有可复制的账号。
 */
export async function copyMonitorLogCookies(
  ids: number[],
): Promise<MonitorLogCookie[]> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    '/api/v1/product-monitor/listing-tasks/logs/copy-cookies',
    { body: { ids } },
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
  const inner = unwrapData<unknown>(data);
  let arr: unknown[] = [];
  if (Array.isArray(inner)) arr = inner;
  else if (inner && typeof inner === 'object' && Array.isArray((inner as Record<string, unknown>).list)) {
    arr = (inner as Record<string, unknown>).list as unknown[];
  }
  return arr.map((raw) => {
    const o = (raw ?? {}) as Record<string, unknown>;
    return {
      account_id: str(o.account_id),
      cookies: str(o.cookies),
      secret_key: str(o.secret_key),
    };
  });
}
