import { getApiClient, extractError } from './client';

// ---------------------------------------------------------------------------
// 黑名单管理（个人黑名单 CRUD + 闲鱼平台黑名单）
// 后端路由前缀: /api/v1/blacklist
// ---------------------------------------------------------------------------

export interface PersonalBlacklistItem {
  id: number;
  buyer_id: string;
  account_id?: string;
  item_id?: string;
  reason?: string;
  is_enabled: boolean;
  created_at?: string;
}

export interface PlatformBlacklistItem {
  id: string;
  buyer_id: string;
  buyer_nick?: string;
  account_id?: string;
  remark?: string;
}

function unwrap<T>(data: unknown): T | null {
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if ('data' in obj && obj.data != null) return obj.data as T;
    if ('success' in obj && obj.success === false) return null;
  }
  return (data as T) ?? null;
}

function extractArray<T>(data: unknown, normalize: (raw: Record<string, unknown>) => T): T[] {
  const body = unwrap<unknown>(data);
  let arr: unknown[] | null = null;
  if (Array.isArray(body)) arr = body;
  else if (body && typeof body === 'object') {
    const obj = body as Record<string, unknown>;
    if (Array.isArray(obj.data)) arr = obj.data;
    else if (obj.data && typeof obj.data === 'object' && Array.isArray((obj.data as Record<string, unknown>).items)) {
      arr = (obj.data as { items: unknown[] }).items;
    }
  }
  if (!arr) return [];
  return arr.map((it) => normalize(it as Record<string, unknown>));
}

/** 获取个人黑名单列表 */
export async function getPersonalBlacklist(
  page = 1,
  pageSize = 50,
): Promise<{ items: PersonalBlacklistItem[]; total: number }> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/blacklist/personal', {
    params: { query: { page, page_size: pageSize } },
  })) as { data?: unknown; error?: unknown };
  const body = unwrap<unknown>(data);
  const items = extractArray<PersonalBlacklistItem>(data, (raw) => ({
    id: Number(raw.id ?? 0),
    buyer_id: String(raw.buyer_id ?? ''),
    account_id: raw.account_id != null ? String(raw.account_id) : undefined,
    item_id: raw.item_id != null ? String(raw.item_id) : undefined,
    reason: raw.reason != null ? String(raw.reason) : undefined,
    is_enabled: Boolean(raw.is_enabled ?? true),
    created_at: raw.created_at != null ? String(raw.created_at) : undefined,
  }));
  let total = items.length;
  if (body && typeof body === 'object') {
    const t = (body as Record<string, unknown>).total;
    if (typeof t === 'number') total = t;
  }
  return { items, total };
}

/** 新增个人黑名单（支持逗号分隔批量） */
export async function createPersonalBlacklist(
  buyerIds: string,
  reason?: string,
  accountId?: string,
): Promise<{ count: number; skipped: number; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)('/api/v1/blacklist/personal', {
    body: { buyer_ids: buyerIds, reason: reason ?? null, account_id: accountId ?? null, is_enabled: true },
  })) as {
    data?: { data?: { count?: number; skipped?: number }; message?: string };
    error?: unknown;
  };
  if (error) throw await extractError(error);
  const body = data as Record<string, unknown> | undefined;
  const inner = (body?.data ?? {}) as Record<string, unknown>;
  return {
    count: Number(inner.count ?? 0),
    skipped: Number(inner.skipped ?? 0),
    message: body?.message as string | undefined,
  };
}

/** 删除个人黑名单 */
export async function deletePersonalBlacklist(recordId: number): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/blacklist/personal/${recordId}`);
}

/** 批量删除个人黑名单 */
export async function batchDeletePersonalBlacklist(recordIds: number[]): Promise<void> {
  const client = await getApiClient();
  // 后端要求字段名为 ids，而非 record_ids
  await (client.POST as any)('/api/v1/blacklist/personal/batch-delete', {
    body: { ids: recordIds },
  });
}

/** 获取闲鱼平台黑名单 */
export async function getPlatformBlacklist(
  accountId: string,
): Promise<PlatformBlacklistItem[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/blacklist/platform', {
    params: { query: { cookie_id: accountId } },
  })) as { data?: unknown; error?: unknown };
  return extractArray<PlatformBlacklistItem>(data, (raw) => ({
    id: String(raw.id ?? raw.record_id ?? ''),
    buyer_id: String(raw.buyer_id ?? raw.user_id ?? ''),
    buyer_nick: raw.buyer_nick != null ? String(raw.buyer_nick) : undefined,
    account_id: raw.account_id != null ? String(raw.account_id) : raw.cookie_id != null ? String(raw.cookie_id) : undefined,
    remark: raw.remark != null ? String(raw.remark) : undefined,
  }));
}

// ---------------------------------------------------------------------------
// 风控日志
// 后端路由: /api/v1/risk-control-logs
// ---------------------------------------------------------------------------

export interface RiskControlLog {
  id: number;
  cookie_id?: string;
  call_type?: string;
  call_user?: string;
  processing_status?: string;
  success?: boolean;
  message?: string;
  created_at?: string;
}

export interface RiskLogQuery {
  limit?: number;
  offset?: number;
  cookie_id?: string;
  start_date?: string;
  end_date?: string;
  processing_status?: string;
  call_type?: string;
}

/** 获取风控日志列表 */
export async function getRiskControlLogs(
  query: RiskLogQuery = {},
): Promise<{ items: RiskControlLog[]; total: number }> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/risk-control-logs', {
    params: { query: { limit: query.limit ?? 20, offset: query.offset ?? 0, ...query } },
  })) as { data?: unknown; error?: unknown };
  const body = unwrap<unknown>(data);
  let items: RiskControlLog[] = [];
  let total = 0;
  if (body && typeof body === 'object') {
    const obj = body as Record<string, unknown>;
    const rawArr = Array.isArray(obj.items) ? obj.items : Array.isArray(obj.data) ? (obj.data as unknown[]) : [];
    items = rawArr.map((it) => {
      const raw = it as Record<string, unknown>;
      return {
        id: Number(raw.id ?? 0),
        cookie_id: raw.cookie_id != null ? String(raw.cookie_id) : undefined,
        call_type: raw.call_type != null ? String(raw.call_type) : undefined,
        call_user: raw.call_user != null ? String(raw.call_user) : undefined,
        processing_status: raw.processing_status != null ? String(raw.processing_status) : undefined,
        success: Boolean(raw.success),
        message: raw.message != null ? String(raw.message) : undefined,
        created_at: raw.created_at != null ? String(raw.created_at) : undefined,
      };
    });
    if (typeof obj.total === 'number') total = obj.total;
  }
  return { items, total };
}

/** 获取今日成功率 */
export async function getRiskTodaySuccessRate(): Promise<{
  total: number;
  success: number;
  success_rate: number;
} | null> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/risk-control-logs/today-success-rate')) as {
    data?: unknown;
    error?: unknown;
  };
  const body = unwrap<Record<string, unknown>>(data);
  if (!body) return null;
  return {
    total: Number(body.total ?? 0),
    success: Number(body.success ?? 0),
    // 后端实际返回字段名为 rate（已换算为百分数），success_rate 为兼容保留
    success_rate: Number(body.success_rate ?? body.rate ?? 0),
  };
}
