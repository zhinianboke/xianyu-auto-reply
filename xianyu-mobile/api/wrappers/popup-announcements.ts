import { getApiClient } from './client';

// ---------------------------------------------------------------------------
// 弹窗公告管理（管理员）
// 后端路由前缀: /api/v1/popup-announcements
//（backend-web/app/api/routes/popup_announcements.py，软删除，字段 is_enabled）
// ---------------------------------------------------------------------------

const PREFIX = '/api/v1/popup-announcements';

/** 弹窗公告（GET 列表 items 的元素） */
export interface PopupAnnouncement {
  id: number;
  title: string;
  content: string;
  /** 跳转链接，可为空 */
  link: string | null;
  is_enabled: boolean;
  /** 来源：local=本机 / remote=远程官方服务器同步 */
  source?: string;
  created_at?: string;
  updated_at?: string;
}

/** 新增/更新入参（对齐后端 PopupAnnouncementCreate/Update） */
export interface PopupAnnouncementInput {
  title: string;
  content: string;
  /** 可选跳转链接，空串按无链接处理 */
  link?: string;
  is_enabled: boolean;
}

// ---------------------------------------------------------------------------
// 通用解析工具（与 card-relation.ts 的 unwrapData/assertOk 保持一致）
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

/** 断言业务成功：body.success === false 时抛出 message */
function assertOk(body: unknown, fallback = '操作失败'): void {
  if (
    body &&
    typeof body === 'object' &&
    (body as Record<string, unknown>).success === false
  ) {
    const msg = (body as Record<string, unknown>).message;
    throw new Error((typeof msg === 'string' && msg) || fallback);
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

function normalizeItem(raw: Record<string, unknown>): PopupAnnouncement {
  return {
    id: num(raw.id),
    title: str(raw.title),
    content: str(raw.content),
    link: raw.link != null && str(raw.link) !== '' ? str(raw.link) : null,
    is_enabled: Boolean(raw.is_enabled),
    source: raw.source != null ? str(raw.source) : undefined,
    created_at: raw.created_at != null ? str(raw.created_at) : undefined,
    updated_at: raw.updated_at != null ? str(raw.updated_at) : undefined,
  };
}

/**
 * 弹窗公告列表（管理员，按创建时间倒序）。
 * GET ?page&page_size → data: { items, total, page, page_size }
 */
export async function getPopupAnnouncements(
  page = 1,
  pageSize = 50,
): Promise<PopupAnnouncement[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(PREFIX, {
    params: { query: { page, page_size: pageSize } },
  })) as { data?: unknown; error?: unknown };
  assertOk(data, '获取弹窗公告失败');
  const inner = unwrapData<unknown>(data);
  let arr: unknown[] = [];
  if (Array.isArray(inner)) arr = inner;
  else if (inner && typeof inner === 'object') {
    const obj = inner as Record<string, unknown>;
    if (Array.isArray(obj.items)) arr = obj.items;
    else if (Array.isArray(obj.list)) arr = obj.list;
    else if (Array.isArray(obj.data)) arr = obj.data;
  }
  return arr.map((it) => normalizeItem((it ?? {}) as Record<string, unknown>));
}

/** 新增弹窗公告：POST ''，body { title, content, link?, is_enabled } */
export async function createPopupAnnouncement(
  input: PopupAnnouncementInput,
): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(PREFIX, { body: input })) as {
    data?: unknown;
    error?: unknown;
  };
  assertOk(data, '发布失败');
}

/** 更新弹窗公告：PUT /{id}，body { title, content, link?, is_enabled } */
export async function updatePopupAnnouncement(
  id: number,
  input: PopupAnnouncementInput,
): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.PUT as any)(`${PREFIX}/${id}`, {
    body: input,
  })) as { data?: unknown; error?: unknown };
  assertOk(data, '更新失败');
}

/**
 * 启用/停用弹窗公告：PUT /{id}/toggle（后端取反当前状态）。
 * 返回切换后的 is_enabled。
 */
export async function togglePopupAnnouncement(id: number): Promise<boolean> {
  const client = await getApiClient();
  const { data } = (await (client.PUT as any)(`${PREFIX}/${id}/toggle`)) as {
    data?: unknown;
    error?: unknown;
  };
  assertOk(data, '操作失败');
  const inner = unwrapData<Record<string, unknown>>(data);
  const body = (inner && typeof inner === 'object' ? inner : {}) as Record<string, unknown>;
  return Boolean(body.is_enabled);
}

/** 删除弹窗公告（软删除）：DELETE /{id} */
export async function deletePopupAnnouncement(id: number): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.DELETE as any)(`${PREFIX}/${id}`)) as {
    data?: unknown;
    error?: unknown;
  };
  assertOk(data, '删除失败');
}
