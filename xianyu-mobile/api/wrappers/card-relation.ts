import { getApiClient } from './client';

// ---------------------------------------------------------------------------
// 卡券 ↔ 商品 双向关联（对齐 web src/api/cards.ts 的关联接口）
// 后端路由前缀: /api/v1/cards
//
// 两个方向：
//  - 卡券 → 商品：getCardItemIds / updateCardItems / batchClearItemRelations
//  - 商品 → 卡券：getItemCards / updateItemCards / getSelectableCards
// ---------------------------------------------------------------------------

const PREFIX = '/api/v1/cards';

/** 卡券来源：自有 / 一级对接 / 二级对接 */
export type CardSource = 'own' | 'dock_l1' | 'dock_l2';

/** 单条卡券关联信息（更新商品关联卡券时使用） */
export interface CardRelationItem {
  card_id: number;
  source: CardSource;
  dock_record_id?: number | null;
}

/** 可选卡券（自有 + 对接合并后的轻字段，供「商品关联卡券」选择） */
export interface SelectableCard {
  id?: number;
  name: string;
  type: string;
  source: CardSource;
  dock_name?: string | null;
  dock_record_id?: number | null;
  is_multi_spec?: boolean;
  spec_name?: string;
  spec_value?: string;
  enabled?: boolean;
  price?: string | null;
  /** 后端下发的稳定键：own_{cardId} | dock_{dockRecordId} */
  unique_key: string;
}

/** 可选卡券分页结果 */
export interface SelectableCardsPage {
  list: SelectableCard[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/** 商品已关联的卡券（getItemCards 返回，字段为 web CardData 的关联子集） */
export interface ItemCard {
  id?: number;
  name: string;
  type: string;
  source: CardSource;
  dock_record_id?: number | null;
  is_multi_spec?: boolean;
  spec_name?: string;
  spec_value?: string;
  enabled?: boolean;
  price?: string | null;
  /** 前端派生的稳定键：own_{id} | dock_{dock_record_id}，与 selectable 的 unique_key 同构 */
  unique_key: string;
}

// ---------------------------------------------------------------------------
// 通用解析工具（与 products.ts / accounts.ts 中的 unwrapData 保持一致）
// ---------------------------------------------------------------------------

/** 后端统一响应 { success, message, data }，抽出 data；未包裹则原样返回 */
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

/** 卡券来源归一：后端可能返回 'own'/'dock_l1'/'dock_l2' 或旧值，兜底 own */
function normalizeSource(val: unknown): CardSource {
  const s = str(val);
  if (s === 'dock_l1' || s === 'dock_l2' || s === 'own') return s;
  return 'own';
}

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

/** 取分页对象，兼容裸数组、{ list, total, ... } 与 ApiResponse 包裹三种形态 */
function unwrapPage<T>(
  data: unknown,
  normalizeList: (raw: unknown[]) => T[],
): { list: T[]; total: number; page: number; page_size: number; total_pages: number } {
  const inner = unwrapData<unknown>(data);
  const obj =
    inner && typeof inner === 'object' && !Array.isArray(inner)
      ? (inner as Record<string, unknown>)
      : {};
  const list: unknown[] = Array.isArray(inner)
    ? inner
    : Array.isArray(obj.list)
      ? obj.list
      : Array.isArray(obj.data)
        ? obj.data
        : Array.isArray(obj.items)
          ? obj.items
          : [];
  const total = typeof obj.total === 'number' ? obj.total : list.length;
  return {
    list: normalizeList(list),
    total,
    page: typeof obj.page === 'number' ? obj.page : 1,
    page_size: typeof obj.page_size === 'number' ? obj.page_size : list.length,
    total_pages: typeof obj.total_pages === 'number' ? obj.total_pages : 0,
  };
}

function normalizeSelectable(raw: Record<string, unknown>): SelectableCard {
  return {
    id: raw.id != null ? num(raw.id) : undefined,
    name: str(raw.name ?? raw.title),
    type: str(raw.type),
    source: normalizeSource(raw.source),
    dock_name: raw.dock_name != null ? str(raw.dock_name) : null,
    dock_record_id: raw.dock_record_id != null ? num(raw.dock_record_id) : null,
    is_multi_spec: raw.is_multi_spec != null ? Boolean(raw.is_multi_spec) : undefined,
    spec_name: raw.spec_name != null ? str(raw.spec_name) : undefined,
    spec_value: raw.spec_value != null ? str(raw.spec_value) : undefined,
    enabled: raw.enabled != null ? Boolean(raw.enabled) : undefined,
    price: raw.price != null ? str(raw.price) : null,
    unique_key: str(raw.unique_key ?? raw.uniqueKey),
  };
}

/**
 * 获取卡券已关联的商品ID列表。
 * GET /api/v1/cards/{card_id}/items → { item_ids: string[] }（包在 ApiResponse 中）。
 * 选中态以本接口为准，保存时不丢失已删除商品的孤儿关联。
 */
export async function getCardItemIds(cardId: number): Promise<string[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(`${PREFIX}/${cardId}/items`)) as {
    data?: unknown;
    error?: unknown;
  };
  const inner = unwrapData<unknown>(data);
  const ids =
    inner && typeof inner === 'object'
      ? (inner as { item_ids?: unknown }).item_ids
      : inner;
  return Array.isArray(ids) ? ids.map((x) => str(x)) : [];
}

/**
 * 更新卡券关联的商品列表（先删旧关联再插新关联）。
 * PUT /api/v1/cards/{card_id}/items，body: { item_ids: string[] }。
 */
export async function updateCardItems(
  cardId: number,
  itemIds: string[],
): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.PUT as any)(`${PREFIX}/${cardId}/items`, {
    body: { item_ids: itemIds },
  })) as { data?: unknown; error?: unknown };
  assertOk(data);
}

/**
 * 获取商品已关联的卡券列表。
 * GET /api/v1/cards/item/{item_id} → 卡券数组（含 card_source / dock_record_id）。
 * 响应可能为裸数组或 ApiResponse 包裹，统一兼容；unique_key 前端派生，
 * 与 selectable 的 unique_key 同构（own_{id} | dock_{rid}）。
 */
export async function getItemCards(itemId: string): Promise<ItemCard[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(`${PREFIX}/item/${itemId}`)) as {
    data?: unknown;
    error?: unknown;
  };
  const inner = unwrapData<unknown>(data);
  let arr: unknown[] = [];
  if (Array.isArray(inner)) {
    arr = inner;
  } else if (inner && typeof inner === 'object') {
    const obj = inner as Record<string, unknown>;
    arr = Array.isArray(obj.data)
      ? obj.data
      : Array.isArray(obj.list)
        ? obj.list
        : Array.isArray(obj.items)
          ? obj.items
          : [];
  }
  return arr.map((it) => {
    const raw = (it ?? {}) as Record<string, unknown>;
    const id = raw.id != null ? num(raw.id) : undefined;
    const source = normalizeSource(raw.card_source ?? raw.source);
    const dockRecordId =
      raw.dock_record_id != null ? num(raw.dock_record_id) : null;
    const uniqueKey =
      source !== 'own' && dockRecordId != null
        ? `dock_${dockRecordId}`
        : id != null
          ? `own_${id}`
          : str(raw.unique_key);
    return {
      id,
      name: str(raw.name ?? raw.title),
      type: str(raw.type),
      source,
      dock_record_id: dockRecordId,
      is_multi_spec:
        raw.is_multi_spec != null ? Boolean(raw.is_multi_spec) : undefined,
      spec_name: raw.spec_name != null ? str(raw.spec_name) : undefined,
      spec_value: raw.spec_value != null ? str(raw.spec_value) : undefined,
      enabled: raw.enabled != null ? Boolean(raw.enabled) : undefined,
      price: raw.price != null ? str(raw.price) : null,
      unique_key: uniqueKey,
    } satisfies ItemCard;
  });
}

/**
 * 更新商品关联的卡券列表（先删旧关联再插新关联）。
 * PUT /api/v1/cards/item/{item_id}/cards，body: { card_items: CardRelationItem[] }。
 */
export async function updateItemCards(
  itemId: string,
  cardItems: CardRelationItem[],
): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.PUT as any)(`${PREFIX}/item/${itemId}/cards`, {
    body: { card_items: cardItems },
  })) as { data?: unknown; error?: unknown };
  assertOk(data);
}

/**
 * 合并分页获取商品可选卡券（自有 + 对接，服务端分页 + 搜索）。
 * GET /api/v1/cards/selectable?item_id&page&page_size&search
 *
 * 注意：后端要求 item_id（必填，用于过滤已关联与可见性），故本函数第一参数为 itemId，
 * 与 web getSelectableCards 签名一致；响应包在 ApiResponse 中：
 * { list, total, page, page_size, total_pages }。
 */
export async function getSelectableCards(
  itemId: string,
  page: number = 1,
  pageSize: number = 50,
  search: string = '',
): Promise<SelectableCardsPage> {
  const client = await getApiClient();
  const query: Record<string, string | number> = {
    item_id: itemId,
    page,
    page_size: pageSize,
  };
  if (search) query.search = search;
  const { data } = (await (client.GET as any)(`${PREFIX}/selectable`, {
    params: { query },
  })) as { data?: unknown; error?: unknown };
  return unwrapPage<SelectableCard>(data, (arr) =>
    arr.map((it) => normalizeSelectable((it ?? {}) as Record<string, unknown>)),
  );
}

/**
 * 批量清空商品的卡券关联关系（不删除卡券本身）。
 * POST /api/v1/cards/batch-clear-item-relations，body: { item_ids: string[] }。
 */
export async function batchClearItemRelations(itemIds: string[]): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    `${PREFIX}/batch-clear-item-relations`,
    { body: { item_ids: itemIds } },
  )) as { data?: unknown; error?: unknown };
  assertOk(data);
}
