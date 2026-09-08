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
