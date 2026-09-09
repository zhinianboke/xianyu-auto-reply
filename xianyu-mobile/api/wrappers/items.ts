import { getApiClient, extractError } from './client';

// ---------------------------------------------------------------------------
// 闲鱼已发布商品列表（对齐 web src/api/items.ts 的 getItemsPaginated）
// 后端路由前缀: /api/v1/items
// ---------------------------------------------------------------------------

const PREFIX = '/api/v1/items';

/** 商品规格明细（鱼小铺多规格商品，来自 item_sku_list，含 sku_id 供改价回传） */
export interface XianyuItemSku {
  sku_id: string;
  inventory_id?: string;
  quantity?: string | number;
  /** 该规格价格（元，字符串） */
  price?: string;
  /** 规格名/值组合，如 [{ name: '颜色', value: '红色' }] */
  specs?: Array<{ name: string; value: string }>;
}

/** 已发布商品（列表展示所需字段，原始响应字段更全，此处只取展示用） */
export interface XianyuItem {
  id: string | number;
  cookie_id: string;
  item_id: string;
  title: string;
  price: string;
  status: string; // item_status_desc，鱼小铺商品的状态文案（普通账号为空）
  quantity: string | number | null;
  /** 主图 URL：从 item_detail（平台商品 JSON）解析，缺失为 null */
  image: string | null;
  is_seller_item: boolean;
  created_at?: string;
  /** 是否已擦亮（列表筛选用） */
  is_polished?: boolean;
  /** 多规格标记（列表筛选用） */
  is_multi_spec?: boolean;
  /** 多数量发货标记（列表筛选用） */
  multi_quantity_delivery?: boolean;
  /** 多规格明细（含 sku_id/price/quantity/specs，供改价与规格展示） */
  item_sku_list?: XianyuItemSku[];
}

export interface XianyuItemsPage {
  items: XianyuItem[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** 商品列表筛选条件（GET /paginated 的可选 query，对齐 web ItemFilterParams） */
export interface XianyuItemFilters {
  /** 关键字（商品ID/标题/详情） */
  keyword?: string;
  /** 是否擦亮 */
  isPolished?: boolean;
  /** 多规格 */
  isMultiSpec?: boolean;
  /** 多数量发货 */
  multiQuantityDelivery?: boolean;
}

/**
 * 从 item_detail（平台商品 JSON 字符串）解析主图 URL。
 * 平台 detail 的 imageInfoDOList 中 type=0 为图片，major="true" 为主图。
 */
function extractImage(itemDetail: unknown): string | null {
  if (typeof itemDetail !== 'string' || !itemDetail) return null;
  try {
    const parsed = JSON.parse(itemDetail) as { imageInfoDOList?: unknown };
    const list = parsed.imageInfoDOList;
    if (!Array.isArray(list)) return null;
    const entries = list as Array<Record<string, unknown>>;
    const major = entries.find(
      (e) => typeof e === 'object' && e && String(e.major).toLowerCase() === 'true' && e.url,
    );
    const anyImg = entries.find(
      (e) => typeof e === 'object' && e && e.url,
    );
    const entry = major || anyImg;
    return (entry?.url as string) ?? null;
  } catch {
    return null;
  }
}

/** 宽松解析后端 item_sku_list 条目（字段缺失/类型异常时兜底） */
function mapSkuList(raw: unknown): XianyuItemSku[] | undefined {
  if (!Array.isArray(raw)) return undefined;
  return raw
    .filter((s): s is Record<string, unknown> => !!s && typeof s === 'object')
    .map((s) => ({
      sku_id: String(s.sku_id ?? ''),
      inventory_id: s.inventory_id != null ? String(s.inventory_id) : undefined,
      quantity: (s.quantity ?? undefined) as string | number | undefined,
      price: s.price != null ? String(s.price) : undefined,
      specs: Array.isArray(s.specs)
        ? (s.specs as Array<Record<string, unknown>>)
            .filter((sp) => !!sp && typeof sp === 'object')
            .map((sp) => ({ name: String(sp.name ?? ''), value: String(sp.value ?? '') }))
        : undefined,
    }))
    .filter((s) => s.sku_id);
}

function mapItem(raw: Record<string, unknown>): XianyuItem {
  return {
    id: raw.id as string | number,
    cookie_id: (raw.cookie_id as string) ?? '',
    item_id: (raw.item_id as string) ?? '',
    title: (raw.item_title as string) || (raw.title as string) || '',
    price: (raw.item_price as string) || (raw.price as string) || '',
    status: (raw.item_status_desc as string) ?? '',
    quantity: (raw.item_quantity ?? null) as string | number | null,
    image: extractImage(raw.item_detail),
    is_seller_item: Boolean(raw.is_seller_item),
    created_at: raw.created_at as string | undefined,
    is_polished: raw.is_polished != null ? Boolean(raw.is_polished) : undefined,
    is_multi_spec: raw.is_multi_spec != null ? Boolean(raw.is_multi_spec) : undefined,
    multi_quantity_delivery:
      raw.multi_quantity_delivery != null ? Boolean(raw.multi_quantity_delivery) : undefined,
    item_sku_list: mapSkuList(raw.item_sku_list),
  };
}

/**
 * 获取闲鱼已发布商品列表（分页）。
 * 后端: GET /api/v1/items/paginated?page&page_size&cookie_id&keyword&is_polished&is_multi_spec&multi_quantity_delivery
 * 响应: { success, data: Item[], total, page, page_size, total_pages }
 * cookieId 为空时返回当前权限范围内所有账号的商品。
 * filters 为可选筛选条件，字段缺省表示不过滤。
 */
export async function getXianyuItems(
  page: number = 1,
  pageSize: number = 20,
  cookieId?: string,
  filters?: XianyuItemFilters,
): Promise<XianyuItemsPage> {
  const client = await getApiClient();
  const query: Record<string, string | number> = { page, page_size: pageSize };
  if (cookieId) query.cookie_id = cookieId;
  if (filters?.keyword) query.keyword = filters.keyword;
  // 后端为 bool query 参数，以 'true'/'false' 字符串传递，仅在被设置时过滤
  if (filters?.isPolished != null) query.is_polished = filters.isPolished ? 'true' : 'false';
  if (filters?.isMultiSpec != null) query.is_multi_spec = filters.isMultiSpec ? 'true' : 'false';
  if (filters?.multiQuantityDelivery != null)
    query.multi_quantity_delivery = filters.multiQuantityDelivery ? 'true' : 'false';

  const { data } = (await (client.GET as any)(`${PREFIX}/paginated`, {
    params: { query },
  })) as { data?: unknown; error?: unknown };

  const body = (data ?? {}) as Record<string, unknown>;
  // 后端响应为 { success, data: [...], total, ... }；兼容裸数组与 { items: [...] }
  const rawList = Array.isArray(body.data)
    ? (body.data as Record<string, unknown>[])
    : Array.isArray(body)
      ? (body as Record<string, unknown>[])
      : Array.isArray((body as Record<string, unknown>).items)
        ? ((body as Record<string, unknown>).items as Record<string, unknown>[])
        : [];

  const total = typeof body.total === 'number' ? body.total : rawList.length;
  return {
    items: rawList.map(mapItem),
    total,
    page: typeof body.page === 'number' ? body.page : page,
    page_size: typeof body.page_size === 'number' ? body.page_size : pageSize,
    total_pages:
      typeof body.total_pages === 'number'
        ? body.total_pages
        : total > 0 ? Math.ceil(total / pageSize) : 0,
  };
}

/**
 * 获取单个商品详情（本地库记录，含 item_sku_list / 筛选标记等完整字段）。
 * 后端: GET /api/v1/items/{cookie_id}/{item_id} → { item: {...} }
 */
export async function getXianyuItemDetail(
  cookieId: string,
  itemId: string,
): Promise<{ item: XianyuItem }> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    `${PREFIX}/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}`,
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const body = (data ?? {}) as Record<string, unknown>;
  const raw = (body.item ?? body) as Record<string, unknown>;
  if (!raw || typeof raw !== 'object' || !raw.item_id) throw new Error('商品不存在');
  return { item: mapItem(raw) };
}

/** 商品同步统计（POST /items/get-all-from-account 响应） */
export interface XianyuItemsSyncResult {
  success: boolean;
  message?: string;
  /** 平台拉取到的商品总数 */
  total_count: number;
  /** 新增/更新入库数 */
  saved_count: number;
  /** 以下字段仅同步全部账号时返回 */
  account_count?: number;
  success_account_count?: number;
  failed_account_count?: number;
  /** 失败账号列表，形如 "account_id: 原因" */
  failed_accounts?: string[];
}

/**
 * 从闲鱼平台同步商品到本地库（后端自动遍历该账号所有页）。
 * 后端: POST /api/v1/items/get-all-from-account
 * cookieId 传入时同步单账号，缺省（{}）时同步当前权限范围内全部账号。
 */
export async function syncXianyuItemsFromAccount(
  cookieId?: string,
): Promise<XianyuItemsSyncResult> {
  const client = await getApiClient();
  const body: Record<string, string> = {};
  if (cookieId) body.cookie_id = cookieId;
  const { data, error } = (await (client.POST as any)(`${PREFIX}/get-all-from-account`, {
    body,
  })) as { data?: Record<string, unknown>; error?: unknown };
  if (error) throw await extractError(error);
  const res = (data ?? {}) as Record<string, unknown>;
  if (res.success === false) {
    throw new Error(typeof res.message === 'string' && res.message ? res.message : '同步商品失败');
  }
  const numOf = (k: string): number => (typeof res[k] === 'number' ? (res[k] as number) : 0);
  return {
    success: true,
    message: typeof res.message === 'string' ? res.message : undefined,
    total_count: numOf('total_count'),
    saved_count: numOf('saved_count'),
    account_count: res.account_count != null ? numOf('account_count') : undefined,
    success_account_count:
      res.success_account_count != null ? numOf('success_account_count') : undefined,
    failed_account_count:
      res.failed_account_count != null ? numOf('failed_account_count') : undefined,
    failed_accounts: Array.isArray(res.failed_accounts)
      ? (res.failed_accounts as unknown[]).map(String)
      : undefined,
  };
}

/** 批量下架结果（透传闲鱼 suc/fail 统计与失败商品） */
export interface XianyuBatchOfflineResult {
  success: boolean;
  message?: string;
  suc_count: number;
  fail_count: number;
  /** 下架失败的商品ID（闲鱼逐条返回，最多展示用） */
  failed_item_ids: string[];
}

/**
 * 批量下架闲鱼商品（调用闲鱼接口，使用指定账号的 Cookie，不改本地库记录）。
 * 后端: POST /api/v1/items/batch-offline，body: { cookie_id, item_ids }
 * 注意：所选账号必须是这些商品的归属账号。
 */
export async function batchOfflineXianyuItems(
  cookieId: string,
  itemIds: string[],
): Promise<XianyuBatchOfflineResult> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)(`${PREFIX}/batch-offline`, {
    body: { cookie_id: cookieId, item_ids: itemIds },
  })) as { data?: Record<string, unknown>; error?: unknown };
  if (error) throw await extractError(error);
  const res = (data ?? {}) as Record<string, unknown>;
  const inner =
    res.data && typeof res.data === 'object'
      ? (res.data as Record<string, unknown>)
      : {};
  if (res.success === false) {
    throw new Error(typeof res.message === 'string' && res.message ? res.message : '下架失败');
  }
  const numOf = (k: string): number => (typeof inner[k] === 'number' ? (inner[k] as number) : 0);
  const results = Array.isArray(inner.results)
    ? (inner.results as Array<Record<string, unknown>>)
    : [];
  return {
    success: true,
    message: typeof res.message === 'string' ? res.message : undefined,
    suc_count: numOf('suc_count'),
    fail_count: numOf('fail_count'),
    failed_item_ids: results
      .filter((r) => r.success === false && r.item_id != null)
      .map((r) => String(r.item_id)),
  };
}

/**
 * 批量删除本地商品记录（不改闲鱼平台，孤儿商品 cookie_id 传 null）。
 * 后端: DELETE /api/v1/items/batch，body: { items: [{ cookie_id, item_id }] }
 */
export async function batchDeleteItemRecords(
  entries: Array<{ cookie_id: string | null; item_id: string }>,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.DELETE as any)(`${PREFIX}/batch`, {
    body: { items: entries },
  })) as { data?: Record<string, unknown>; error?: unknown };
  if (error) throw await extractError(error);
  const res = (data ?? {}) as Record<string, unknown>;
  if (res.success === false) {
    throw new Error(
      typeof res.message === 'string' && res.message ? res.message : '批量删除失败',
    );
  }
  return {
    success: true,
    message: typeof res.message === 'string' ? res.message : undefined,
  };
}

/** 断言本地标记更新类接口业务成功（HTTP 200 + success:false 视为失败） */
function assertFlagOk(data: unknown, fallbackMsg: string): string {
  const res = (data ?? {}) as Record<string, unknown>;
  if (res.success === false) {
    throw new Error(typeof res.message === 'string' && res.message ? res.message : fallbackMsg);
  }
  return typeof res.message === 'string' ? res.message : fallbackMsg;
}

/**
 * 更新商品的多规格标记（本地库标记，供列表筛选）。
 * 后端: PUT /api/v1/items/{cookie_id}/{item_id}/multi-spec，body: { is_multi_spec }
 */
export async function setItemMultiSpec(
  cookieId: string,
  itemId: string,
  enabled: boolean,
): Promise<string> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `${PREFIX}/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}/multi-spec`,
    { body: { is_multi_spec: enabled } },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  return assertFlagOk(data, enabled ? '多规格已开启' : '多规格已关闭');
}

/**
 * 更新商品的多数量发货标记（本地库标记，供列表筛选）。
 * 后端: PUT /api/v1/items/{cookie_id}/{item_id}/multi-quantity-delivery，body: { multi_quantity_delivery }
 */
export async function setItemMultiQuantityDelivery(
  cookieId: string,
  itemId: string,
  enabled: boolean,
): Promise<string> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `${PREFIX}/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}/multi-quantity-delivery`,
    { body: { multi_quantity_delivery: enabled } },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  return assertFlagOk(data, enabled ? '多数量发货已开启' : '多数量发货已关闭');
}
