import { getServerUrl } from '@/lib/config';
import { getApiClient, extractError } from './client';
import { ApiError } from './errors';

// ---------------------------------------------------------------------------
// 类型定义（与任务规格保持一致）
// ---------------------------------------------------------------------------

export interface Dealer {
  id: number;
  username: string;
  level: string;
  balance: string;
}

export interface AgentOrder {
  id: number;
  order_no: string;
  amount: string;
  status: string;
  created_at: string;
}

export interface FundFlow {
  id: number;
  amount: string;
  type: string;
  description: string;
  created_at: string;
}

export interface DockRecord {
  id: number;
  card_key: string;
  status: string;
  created_at: string;
}

/** 货源广场-卡券货源（一级，后端 `GET /distribution/supply` 的 list 项） */
export interface SupplyCard {
  id: number;
  user_id: number;
  name: string;
  type: string;
  description: string;
  price: string;
  is_multi_spec: boolean;
  spec_name: string;
  spec_value: string;
  is_docked: boolean;
  dock_record_id: number | null;
  created_at: string;
}

/** 货源广场-分销商货源（二级，后端 `GET /distribution/sub-supply` 的 list 项） */
export interface SubSupplyRecord {
  id: number;
  source_user_id: number;
  source_username: string;
  card_id: number;
  card_name: string;
  card_price: string;
  sub_dock_price: string;
  dock_name: string;
  is_multi_spec: boolean;
  spec_name: string;
  spec_value: string;
  is_docked: boolean;
}

/** 下级分销商（后端 `GET /distribution/sub-dealers` 的 list 项，按用户分组） */
export interface SubDealer {
  user_id: number;
  username: string;
  email: string;
  dock_count: number;
  last_dock_time: string;
}

/** 我的对接记录全量字段（后端 `GET /distribution/dock-records`，分销卡券提货用） */
export interface DockRecordFull {
  id: number;
  card_id: number;
  card_name: string;
  dock_name: string;
  markup_amount: string;
  card_price: string;
  is_multi_spec: boolean;
  spec_name: string;
  spec_value: string;
  delivery_count: number;
  status: boolean;
  level: number;
  owner_username: string;
  created_at: string;
}

/** 下级分销商对接明细（后端 `GET /distribution/sub-dealers/{id}/details` 的 list 项） */
export interface SubDealerDockRecord {
  id: number;
  card_name: string;
  dock_name: string;
  price: string;
  status: boolean;
  created_at: string;
}

export interface CrawlerJob {
  id: number;
  name: string;
  status: string;
  items_count?: number;
}

export interface CrawlerItem {
  item_id: string;
  title: string;
  price: string;
}

export interface PersonalAddress {
  id: number;
  name: string;
  phone: string;
  address: string;
}

// ---------------------------------------------------------------------------
// 通用解析工具
//
// 与 products.ts / accounts.ts 中的同名工具保持一致：后端统一响应为
// `{ success, message, data }`，列表可能裸返回数组，也可能被包成
// `{ data: [...] }` / `{ items: [...] }` / `{ records: [...] }`，这里统一兼容。
// ---------------------------------------------------------------------------

/** 取出 `{ success, data }` 包裹的内部 data；未包裹则原样返回。 */
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

/** 从可能被包一层 / 裸数组的响应中取出数组并逐项归一化。 */
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
    else if (Array.isArray(obj.records)) arr = obj.records;
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

/** 安全取布尔：后端 bool 字段可能以 true/'true'/1 形式返回 */
function bool(val: unknown, fallback = false): boolean {
  if (val == null) return fallback;
  if (typeof val === 'boolean') return val;
  if (val === 1 || val === '1' || val === 'true') return true;
  if (val === 0 || val === '0' || val === 'false') return false;
  return fallback;
}

// ---------------------------------------------------------------------------
// 分销
// ---------------------------------------------------------------------------

function normalizeDealer(raw: Record<string, unknown>): Dealer {
  return {
    id: num(raw.id ?? raw.dealer_id ?? raw.user_id),
    username: str(raw.username ?? raw.name ?? raw.dealer_name),
    level: str(raw.level ?? raw.dealer_level, '-'),
    balance: str(raw.balance ?? raw.amount, '0'),
  };
}

/** 经销商列表：GET /api/v1/distribution/dealers */
export async function getDealers(): Promise<Dealer[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/distribution/dealers',
  )) as { data?: unknown; error?: unknown };
  return extractArray<Dealer>(data, normalizeDealer);
}

function normalizeAgentOrder(raw: Record<string, unknown>): AgentOrder {
  return {
    id: num(raw.id ?? raw.order_id),
    order_no: str(raw.order_no ?? raw.order_number),
    amount: str(raw.amount ?? raw.price, '0'),
    status: str(raw.status ?? raw.order_status, '-'),
    created_at: str(raw.created_at ?? raw.created_time ?? raw.time),
  };
}

/** 我的订单：GET /api/v1/distribution/agent-orders/my */
export async function getAgentOrders(): Promise<AgentOrder[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/distribution/agent-orders/my',
  )) as { data?: unknown; error?: unknown };
  return extractArray<AgentOrder>(data, normalizeAgentOrder);
}

function normalizeFundFlow(raw: Record<string, unknown>): FundFlow {
  return {
    id: num(raw.id ?? raw.flow_id),
    amount: str(raw.amount ?? raw.money, '0'),
    type: str(raw.type ?? raw.flow_type, '-'),
    description: str(raw.description ?? raw.remark ?? raw.note),
    created_at: str(raw.created_at ?? raw.created_time ?? raw.time),
  };
}

/** 资金流水：GET /api/v1/distribution/fund-flows */
export async function getDistributionFundFlows(): Promise<FundFlow[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/distribution/fund-flows',
  )) as { data?: unknown; error?: unknown };
  return extractArray<FundFlow>(data, normalizeFundFlow);
}

function normalizeDockRecord(raw: Record<string, unknown>): DockRecord {
  return {
    id: num(raw.id ?? raw.record_id),
    card_key: str(raw.card_key ?? raw.card_no ?? raw.key),
    status: str(raw.status ?? raw.dock_status, '-'),
    created_at: str(raw.created_at ?? raw.created_time ?? raw.time),
  };
}

/** 对接记录：GET /api/v1/distribution/dock-records */
export async function getDockRecords(): Promise<DockRecord[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/distribution/dock-records',
  )) as { data?: unknown; error?: unknown };
  return extractArray<DockRecord>(data, normalizeDockRecord);
}

// ---------------------------------------------------------------------------
// 货源广场 / 分销卡券提货 / 下级分销商
//
// 端点与 backend-web/app/api/routes/distribution.py 对齐：
// - GET  /distribution/supply                        卡券货源（一级）
// - GET  /distribution/sub-supply                    分销商货源（二级）
// - POST /distribution/dock-records                  创建一级对接
// - POST /distribution/sub-dock-records              创建二级对接
// - GET  /distribution/dock-records                  我的对接记录（全量字段）
// - GET  /distribution/dock-records/{id}/pickup-url  获取提货链接
// - GET  /distribution/sub-dealers                   下级分销商列表
// - GET  /distribution/sub-dealers/{uid}/details     下级分销商对接明细
// ---------------------------------------------------------------------------

function normalizeSupplyCard(raw: Record<string, unknown>): SupplyCard {
  return {
    id: num(raw.id ?? raw.card_id),
    user_id: num(raw.user_id),
    name: str(raw.name ?? raw.card_name),
    type: str(raw.type ?? raw.card_type, '-'),
    description: str(raw.description ?? raw.desc),
    price: str(raw.price ?? raw.card_price, '0'),
    is_multi_spec: bool(raw.is_multi_spec),
    spec_name: str(raw.spec_name),
    spec_value: str(raw.spec_value),
    is_docked: bool(raw.is_docked),
    dock_record_id: raw.dock_record_id != null ? num(raw.dock_record_id) : null,
    created_at: str(raw.created_at ?? raw.created_time),
  };
}

/** 卡券货源（一级分销）：GET /api/v1/distribution/supply */
export async function getSupplyCards(params?: {
  page?: number;
  pageSize?: number;
  search?: string;
  type?: string;
}): Promise<SupplyCard[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/distribution/supply', {
    params: {
      query: {
        page: params?.page ?? 1,
        page_size: params?.pageSize ?? 100,
        search: params?.search ?? '',
        type: params?.type ?? '',
      },
    },
  })) as { data?: unknown; error?: unknown };
  return extractArray<SupplyCard>(data, normalizeSupplyCard);
}

function normalizeSubSupplyRecord(raw: Record<string, unknown>): SubSupplyRecord {
  return {
    id: num(raw.id ?? raw.dock_record_id),
    source_user_id: num(raw.source_user_id ?? raw.user_id),
    source_username: str(raw.source_username ?? raw.owner_username),
    card_id: num(raw.card_id),
    card_name: str(raw.card_name),
    card_price: str(raw.card_price, '0'),
    sub_dock_price: str(raw.sub_dock_price),
    dock_name: str(raw.dock_name),
    is_multi_spec: bool(raw.is_multi_spec),
    spec_name: str(raw.spec_name),
    spec_value: str(raw.spec_value),
    is_docked: bool(raw.is_docked),
  };
}

/** 分销商货源（二级分销）：GET /api/v1/distribution/sub-supply */
export async function getSubSupplyRecords(params?: {
  page?: number;
  pageSize?: number;
  search?: string;
}): Promise<SubSupplyRecord[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/distribution/sub-supply', {
    params: {
      query: {
        page: params?.page ?? 1,
        page_size: params?.pageSize ?? 100,
        search: params?.search ?? '',
      },
    },
  })) as { data?: unknown; error?: unknown };
  return extractArray<SubSupplyRecord>(data, normalizeSubSupplyRecord);
}

/**
 * 从 POST 对接接口的 `ApiResponse` 中取回记录 id；`success=false` 时抛 ApiError。
 * 后端成功返回 `{ success, message, data: { id } }`，失败只有 `{ success, message }`。
 */
function extractDockIdOrThrow(data: unknown, fallbackMsg: string): number {
  const inner = unwrapData<unknown>(data);
  if (inner && typeof inner === 'object' && 'id' in (inner as Record<string, unknown>)) {
    return num((inner as Record<string, unknown>).id);
  }
  const msg =
    data && typeof data === 'object' && 'message' in (data as Record<string, unknown>)
      ? str((data as Record<string, unknown>).message, fallbackMsg)
      : fallbackMsg;
  throw new ApiError(msg, 0);
}

/** 创建一级对接：POST /api/v1/distribution/dock-records → 对接记录 id */
export async function createDockRecord(
  cardId: number,
  dockName: string,
  markupAmount?: string,
  remark?: string,
): Promise<number> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)('/api/v1/distribution/dock-records', {
    body: {
      card_id: cardId,
      dock_name: dockName,
      ...(markupAmount ? { markup_amount: markupAmount } : {}),
      ...(remark ? { remark } : {}),
    },
  })) as { data?: unknown; error?: unknown };
  return extractDockIdOrThrow(data, '对接失败');
}

/** 创建二级对接：POST /api/v1/distribution/sub-dock-records → 对接记录 id */
export async function createSubDockRecord(
  parentDockId: number,
  dockName: string,
  markupAmount?: string,
  remark?: string,
): Promise<number> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)('/api/v1/distribution/sub-dock-records', {
    body: {
      parent_dock_id: parentDockId,
      dock_name: dockName,
      ...(markupAmount ? { markup_amount: markupAmount } : {}),
      ...(remark ? { remark } : {}),
    },
  })) as { data?: unknown; error?: unknown };
  return extractDockIdOrThrow(data, '对接失败');
}

function normalizeDockRecordFull(raw: Record<string, unknown>): DockRecordFull {
  return {
    id: num(raw.id ?? raw.record_id),
    card_id: num(raw.card_id),
    card_name: str(raw.card_name),
    dock_name: str(raw.dock_name),
    markup_amount: str(raw.markup_amount),
    card_price: str(raw.card_price, '0'),
    is_multi_spec: bool(raw.is_multi_spec),
    spec_name: str(raw.spec_name),
    spec_value: str(raw.spec_value),
    delivery_count: num(raw.delivery_count),
    status: bool(raw.status, true),
    level: num(raw.level),
    owner_username: str(raw.owner_username),
    created_at: str(raw.created_at ?? raw.created_time),
  };
}

/** 我的对接记录（全量字段，分销卡券提货页用）：GET /api/v1/distribution/dock-records */
export async function getDockRecordsFull(level?: number): Promise<DockRecordFull[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/distribution/dock-records', {
    params: {
      query: {
        page: 1,
        page_size: 200,
        ...(level != null ? { level } : {}),
      },
    },
  })) as { data?: unknown; error?: unknown };
  return extractArray<DockRecordFull>(data, normalizeDockRecordFull);
}

/** 获取对接记录的免认证提货链接：GET /api/v1/distribution/dock-records/{id}/pickup-url */
export async function getDockRecordPickupUrl(recordId: number): Promise<string> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `/api/v1/distribution/dock-records/${recordId}/pickup-url`,
  )) as { data?: unknown; error?: unknown };
  const inner = unwrapData<unknown>(data);
  const url =
    inner && typeof inner === 'object'
      ? str((inner as Record<string, unknown>).pickup_url)
      : '';
  if (!url) {
    const msg =
      data && typeof data === 'object' && 'message' in (data as Record<string, unknown>)
        ? str((data as Record<string, unknown>).message, '获取提货链接失败')
        : '获取提货链接失败';
    throw new ApiError(msg, 0);
  }
  return url;
}

/**
 * 执行提货：直接 GET 提货链接（免认证），后端返回纯文本卡密内容。
 * 链接一般为绝对地址；若为相对路径则补上当前服务器地址。
 */
export async function fetchPickupContent(url: string): Promise<string> {
  const target = /^https?:\/\//i.test(url) ? url : `${(await getServerUrl()) ?? ''}${url}`;
  const res = await fetch(target);
  const text = await res.text();
  if (!res.ok) {
    throw new ApiError(text.slice(0, 200) || `提货失败 (${res.status})`, res.status);
  }
  return text;
}

function normalizeSubDealer(raw: Record<string, unknown>): SubDealer {
  return {
    user_id: num(raw.user_id ?? raw.id ?? raw.dealer_user_id),
    username: str(raw.username ?? raw.name),
    email: str(raw.email),
    dock_count: num(raw.dock_count ?? raw.count),
    last_dock_time: str(raw.last_dock_time),
  };
}

/** 下级分销商列表：GET /api/v1/distribution/sub-dealers */
export async function getSubDealers(params?: {
  page?: number;
  pageSize?: number;
  search?: string;
}): Promise<SubDealer[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/distribution/sub-dealers', {
    params: {
      query: {
        page: params?.page ?? 1,
        page_size: params?.pageSize ?? 100,
        search: params?.search ?? '',
      },
    },
  })) as { data?: unknown; error?: unknown };
  return extractArray<SubDealer>(data, normalizeSubDealer);
}

function normalizeSubDealerDockRecord(raw: Record<string, unknown>): SubDealerDockRecord {
  return {
    id: num(raw.id ?? raw.record_id),
    card_name: str(raw.card_name),
    dock_name: str(raw.dock_name),
    price: str(raw.card_price ?? raw.price, '0'),
    status: bool(raw.status, true),
    created_at: str(raw.created_at ?? raw.created_time),
  };
}

/** 下级分销商对接明细：GET /api/v1/distribution/sub-dealers/{dealer_user_id}/details */
export async function getSubDealerDetails(
  dealerUserId: number,
  params?: { page?: number; pageSize?: number },
): Promise<SubDealerDockRecord[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `/api/v1/distribution/sub-dealers/${dealerUserId}/details`,
    {
      params: {
        query: {
          page: params?.page ?? 1,
          page_size: params?.pageSize ?? 100,
        },
      },
    },
  )) as { data?: unknown; error?: unknown };
  return extractArray<SubDealerDockRecord>(data, normalizeSubDealerDockRecord);
}

// ---------------------------------------------------------------------------
// 爬虫
// ---------------------------------------------------------------------------

function normalizeCrawlerJob(raw: Record<string, unknown>): CrawlerJob {
  const countRaw = raw.items_count ?? raw.item_count ?? raw.total_items ?? raw.count;
  return {
    id: num(raw.id ?? raw.job_id),
    name: str(raw.name ?? raw.job_name),
    status: str(raw.status ?? raw.state, 'unknown'),
    items_count: countRaw != null ? num(countRaw) : undefined,
  };
}

/** 爬虫任务列表：GET /api/v1/goofish/crawler/jobs → `[{ id, name, status, ... }]` */
export async function getCrawlerJobs(): Promise<CrawlerJob[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/goofish/crawler/jobs',
  )) as { data?: unknown; error?: unknown };
  return extractArray<CrawlerJob>(data, normalizeCrawlerJob);
}

function normalizeCrawlerItem(raw: Record<string, unknown>): CrawlerItem {
  return {
    item_id: str(raw.item_id ?? raw.id),
    title: str(raw.title ?? raw.item_title),
    price: str(raw.price ?? raw.item_price, '0'),
  };
}

/** 爬虫任务商品：GET /api/v1/goofish/crawler/jobs/{job_id}/items */
export async function getCrawlerItems(jobId: number): Promise<CrawlerItem[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `/api/v1/goofish/crawler/jobs/${jobId}/items`,
  )) as { data?: unknown; error?: unknown };
  return extractArray<CrawlerItem>(data, normalizeCrawlerItem);
}

/** 启动爬虫：POST /api/v1/goofish/crawler/jobs/{job_id}/start */
export async function startCrawler(jobId: number): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)(`/api/v1/goofish/crawler/jobs/${jobId}/start`);
}

/** 停止爬虫：POST /api/v1/goofish/crawler/jobs/{job_id}/stop */
export async function stopCrawler(jobId: number): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)(`/api/v1/goofish/crawler/jobs/${jobId}/stop`);
}

// ---------------------------------------------------------------------------
// 商品发布
// ---------------------------------------------------------------------------

function normalizePersonalAddress(raw: Record<string, unknown>): PersonalAddress {
  return {
    id: num(raw.id ?? raw.address_id),
    name: str(raw.name ?? raw.receiver_name ?? raw.contact_name),
    phone: str(raw.phone ?? raw.mobile ?? raw.receiver_phone),
    address: str(
      raw.address ?? raw.detail ?? raw.receiver_address ?? raw.full_address,
    ),
  };
}

/** 发布地址列表：GET /api/v1/product-publish/personal-addresses */
export async function getPersonalAddresses(): Promise<PersonalAddress[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/product-publish/personal-addresses',
  )) as { data?: unknown; error?: unknown };
  return extractArray<PersonalAddress>(data, normalizePersonalAddress);
}
