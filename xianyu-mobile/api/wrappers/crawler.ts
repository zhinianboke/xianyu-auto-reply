import { getApiClient } from './client';

// ---------------------------------------------------------------------------
// Goofish 定时采集（爬虫定时任务）
// 后端路由前缀: /api/v1/goofish/crawler（backend-web/app/api/routes/goofish_crawler.py）
//
// 说明：distribution.ts 中遗留的 getCrawlerJobs/startCrawler/stopCrawler 不含
// 创建/删除/立即执行能力，且未解析后端 { jobs: [...] } 包裹。本文件为完整实现，
// 页面统一迁移到本文件，旧函数保持不动。
// ---------------------------------------------------------------------------

const PREFIX = '/api/v1/goofish/crawler';

/** 采集任务（后端 GET /jobs 的 list 项，字段见 goofish_crawler.py list_jobs） */
export interface CrawlerJob {
  id: number;
  cookie_id: string;
  keyword: string;
  interval_seconds: number;
  start_page: number;
  pages: number;
  page_size: number;
  fetch_detail: boolean;
  detail_limit: number;
  enabled: boolean;
  running: boolean;
  last_run_at: string | null;
  last_error: string | null;
  item_count: number;
  latest_item_fetched_at: string | null;
}

/** 采集结果商品（后端 GET /jobs/{id}/items 的 list 项） */
export interface CrawlerItem {
  job_id?: number;
  item_id: string;
  title: string;
  price: string;
  area: string;
  seller_name: string;
  item_url: string;
  main_image: string;
  want_count: number | null;
  view_count: number | null;
  fetched_at: string;
}

/** 创建任务入参（对齐后端 GoofishCrawlJobCreate，数值范围由后端校验） */
export interface CrawlerJobCreateInput {
  cookie_id: string;
  keyword: string;
  /** 执行间隔（秒），60~86400 */
  interval_seconds: number;
  /** 起始页码，1~50 */
  start_page: number;
  /** 抓取页数，1~10 */
  pages: number;
  /** 每页数量，1~50 */
  page_size: number;
  fetch_detail: boolean;
  /** 详情抓取数量限制，0~50 */
  detail_limit: number;
  enabled: boolean;
}

/** 立即执行一次的结果（后端返回 { success, upserted, total, error? }） */
export interface CrawlerRunOnceResult {
  success: boolean;
  upserted: number;
  total: number;
  error?: string;
}

// ---------------------------------------------------------------------------
// 通用解析工具（与 card-relation.ts 的 unwrapData/assertOk 保持一致）
// 注意：该路由多数接口返回裸 dict（非 ApiResponse 包裹），需同时兼容两种形态。
// ---------------------------------------------------------------------------

/** 取出 `{ success, data }` 包裹的内部 data；未包裹则原样返回 */
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

/** 断言业务成功：body.success === false 时抛出 message（后端业务错误也返回 HTTP 200） */
function assertOk(body: unknown, fallback = '操作失败'): void {
  if (
    body &&
    typeof body === 'object' &&
    (body as Record<string, unknown>).success === false
  ) {
    const msg = (body as Record<string, unknown>).message;
    const err = (body as Record<string, unknown>).error;
    const text = typeof msg === 'string' ? msg : typeof err === 'string' ? err : '';
    throw new Error(text || fallback);
  }
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

function bool(val: unknown, fallback = false): boolean {
  if (val == null) return fallback;
  if (typeof val === 'boolean') return val;
  if (val === 1 || val === '1' || val === 'true') return true;
  if (val === 0 || val === '0' || val === 'false') return false;
  return fallback;
}

/** 从对象中取名为 keys 之一的数组字段（兼容裸数组） */
function pickArray(body: unknown, keys: string[]): unknown[] {
  const inner = unwrapData<unknown>(body);
  if (Array.isArray(inner)) return inner;
  if (inner && typeof inner === 'object') {
    const obj = inner as Record<string, unknown>;
    for (const k of keys) {
      if (Array.isArray(obj[k])) return obj[k] as unknown[];
    }
  }
  return [];
}

function nullableStr(val: unknown): string | null {
  const s = str(val);
  return s === '' ? null : s;
}

function normalizeJob(raw: Record<string, unknown>): CrawlerJob {
  return {
    id: num(raw.id ?? raw.job_id),
    cookie_id: str(raw.cookie_id),
    keyword: str(raw.keyword),
    interval_seconds: num(raw.interval_seconds, 900),
    start_page: num(raw.start_page, 1),
    pages: num(raw.pages, 1),
    page_size: num(raw.page_size, 20),
    fetch_detail: bool(raw.fetch_detail, true),
    detail_limit: num(raw.detail_limit, 20),
    enabled: bool(raw.enabled, false),
    running: bool(raw.running, false),
    last_run_at: nullableStr(raw.last_run_at),
    last_error: nullableStr(raw.last_error),
    item_count: num(raw.item_count ?? raw.items_count, 0),
    latest_item_fetched_at: nullableStr(raw.latest_item_fetched_at),
  };
}

function normalizeItem(raw: Record<string, unknown>): CrawlerItem {
  return {
    job_id: raw.job_id != null ? num(raw.job_id) : undefined,
    item_id: str(raw.item_id ?? raw.id),
    title: str(raw.title),
    price: str(raw.price, '0'),
    area: str(raw.area),
    seller_name: str(raw.seller_name),
    item_url: str(raw.item_url),
    main_image: str(raw.main_image),
    want_count: raw.want_count != null ? num(raw.want_count) : null,
    view_count: raw.view_count != null ? num(raw.view_count) : null,
    fetched_at: str(raw.fetched_at),
  };
}

/** 任务列表：GET /jobs → 裸 { jobs: [...] }（失败时后端也返回 { jobs: [] }） */
export async function getCrawlerJobs(): Promise<CrawlerJob[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(`${PREFIX}/jobs`)) as {
    data?: unknown;
    error?: unknown;
  };
  return pickArray(data, ['jobs', 'items', 'list', 'data']).map((it) =>
    normalizeJob((it ?? {}) as Record<string, unknown>),
  );
}

/**
 * 创建任务：POST /jobs。
 * 成功返回 job_id（后端 { success: true, job_id, message }）；业务失败抛错。
 */
export async function createCrawlerJob(
  input: CrawlerJobCreateInput,
): Promise<number | null> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(`${PREFIX}/jobs`, {
    body: input,
  })) as { data?: unknown; error?: unknown };
  assertOk(data, '创建失败');
  const inner = unwrapData<Record<string, unknown>>(data);
  const jobId =
    inner && typeof inner === 'object'
      ? (inner as Record<string, unknown>).job_id
      : null;
  return jobId != null ? num(jobId) : null;
}

/** 删除任务（连同采集结果）：DELETE /jobs/{job_id} */
export async function deleteCrawlerJob(jobId: number): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.DELETE as any)(`${PREFIX}/jobs/${jobId}`)) as {
    data?: unknown;
    error?: unknown;
  };
  assertOk(data, '删除失败');
}

/** 启动任务（enabled=True 并调度）：POST /jobs/{job_id}/start */
export async function startCrawlerJob(jobId: number): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    `${PREFIX}/jobs/${jobId}/start`,
  )) as { data?: unknown; error?: unknown };
  assertOk(data, '启动失败');
}

/** 停止任务（enabled=False 并取消调度）：POST /jobs/{job_id}/stop */
export async function stopCrawlerJob(jobId: number): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    `${PREFIX}/jobs/${jobId}/stop`,
  )) as { data?: unknown; error?: unknown };
  assertOk(data, '停止失败');
}

/**
 * 立即执行一次：POST /jobs/{job_id}/run-once。
 * 后端同步执行采集（可能耗时较长），返回 { success, upserted, total, error? }。
 * 注意：该接口无论成败均返回 HTTP 200，业务失败通过返回值 success/error 表达。
 */
export async function runCrawlerJobOnce(
  jobId: number,
): Promise<CrawlerRunOnceResult> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    `${PREFIX}/jobs/${jobId}/run-once`,
  )) as { data?: unknown; error?: unknown };
  const inner = unwrapData<Record<string, unknown>>(data);
  const body = (inner && typeof inner === 'object' ? inner : {}) as Record<string, unknown>;
  return {
    success: bool(body.success, false),
    upserted: num(body.upserted, 0),
    total: num(body.total, 0),
    error: typeof body.error === 'string' ? body.error : undefined,
  };
}

/** 采集结果：GET /jobs/{job_id}/items → 裸 { items: [...] } */
export async function getCrawlerJobItems(
  jobId: number,
  limit = 50,
  offset = 0,
): Promise<CrawlerItem[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(`${PREFIX}/jobs/${jobId}/items`, {
    params: { query: { limit, offset } },
  })) as { data?: unknown; error?: unknown };
  return pickArray(data, ['items', 'list', 'data']).map((it) =>
    normalizeItem((it ?? {}) as Record<string, unknown>),
  );
}
