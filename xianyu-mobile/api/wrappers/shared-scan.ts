import { getApiClient } from './client';

// ---------------------------------------------------------------------------
// 共享多人扫码登录（管理端）
// 后端路由前缀: /api/v1/shared-scan（backend-web/app/api/routes/shared_scan.py）
// 管理员创建会话 → 生成分享链接 → 兼职通过链接各自扫码 → 管理端实时查看状态。
// ---------------------------------------------------------------------------

const PREFIX = '/api/v1/shared-scan';

/** 共享会话（GET /list 的 list 项） */
export interface SharedScanSession {
  session_id: string;
  status: string;
  /** 兼职端分享链接（后端按请求来源拼接：{frontend_url}/shared-scan-page?session_id=...） */
  share_url: string;
  expires_at: string;
  created_at: string;
  /** 会话下兼职数量 */
  worker_count: number;
  /** 已扫码成功的兼职数量 */
  success_count: number;
}

/** 创建会话结果（POST /create 的 data） */
export interface SharedScanSessionCreated {
  session_id: string;
  share_url: string;
  expires_at: string;
}

/** 单个兼职的实时扫码状态（GET /status → part_time_workers 的 list 项） */
export interface SharedScanWorkerInfo {
  sub_session_id: string;
  status: string;
  account_id: string | null;
  cookie_saved: boolean;
  /** 加入时间（Unix 秒时间戳） */
  joined_at: number;
}

/** 会话下所有兼职的实时状态（GET /status?session_id=... 的 data） */
export interface SharedSessionStatus {
  session_id: string;
  session_status: string;
  part_time_workers: SharedScanWorkerInfo[];
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
    throw new Error(
      (typeof msg === 'string' && msg) || fallback,
    );
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

function nullableStr(val: unknown): string | null {
  const s = str(val);
  return s === '' ? null : s;
}

function normalizeSession(raw: Record<string, unknown>): SharedScanSession {
  return {
    session_id: str(raw.session_id),
    status: str(raw.status, 'active'),
    share_url: str(raw.share_url),
    expires_at: str(raw.expires_at),
    created_at: str(raw.created_at),
    worker_count: num(raw.worker_count, 0),
    success_count: num(raw.success_count, 0),
  };
}

function normalizeWorker(raw: Record<string, unknown>): SharedScanWorkerInfo {
  return {
    sub_session_id: str(raw.sub_session_id),
    status: str(raw.status, 'qrcode_ready'),
    account_id: nullableStr(raw.account_id),
    cookie_saved: Boolean(raw.cookie_saved),
    joined_at: num(raw.joined_at, 0),
  };
}

/** 创建共享会话：POST /create（无需 body），返回会话与分享链接 */
export async function createSharedSession(): Promise<SharedScanSessionCreated> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(`${PREFIX}/create`)) as {
    data?: unknown;
    error?: unknown;
  };
  assertOk(data, '创建失败');
  const inner = unwrapData<Record<string, unknown>>(data);
  const body = (inner && typeof inner === 'object' ? inner : {}) as Record<string, unknown>;
  return {
    session_id: str(body.session_id),
    share_url: str(body.share_url),
    expires_at: str(body.expires_at),
  };
}

/** 会话列表（含兼职统计）：GET /list → data.sessions */
export async function listSharedSessions(): Promise<SharedScanSession[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(`${PREFIX}/list`)) as {
    data?: unknown;
    error?: unknown;
  };
  assertOk(data, '获取会话列表失败');
  const inner = unwrapData<unknown>(data);
  let arr: unknown[] = [];
  if (Array.isArray(inner)) arr = inner;
  else if (inner && typeof inner === 'object') {
    const obj = inner as Record<string, unknown>;
    if (Array.isArray(obj.sessions)) arr = obj.sessions;
    else if (Array.isArray(obj.list)) arr = obj.list;
    else if (Array.isArray(obj.data)) arr = obj.data;
  }
  return arr.map((it) => normalizeSession((it ?? {}) as Record<string, unknown>));
}

/** 查询会话下所有兼职实时状态：GET /status?session_id=... */
export async function getSharedSessionStatus(
  sessionId: string,
): Promise<SharedSessionStatus> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(`${PREFIX}/status`, {
    params: { query: { session_id: sessionId } },
  })) as { data?: unknown; error?: unknown };
  assertOk(data, '获取兼职状态失败');
  const inner = unwrapData<Record<string, unknown>>(data);
  const body = (inner && typeof inner === 'object' ? inner : {}) as Record<string, unknown>;
  const workers = Array.isArray(body.part_time_workers) ? body.part_time_workers : [];
  return {
    session_id: str(body.session_id, sessionId),
    session_status: str(body.session_status),
    part_time_workers: workers.map((it) =>
      normalizeWorker((it ?? {}) as Record<string, unknown>),
    ),
  };
}

/** 删除会话（连同兼职记录）：DELETE /{session_id} */
export async function deleteSharedSession(sessionId: string): Promise<void> {
  const client = await getApiClient();
  const { data } = (await (client.DELETE as any)(
    `${PREFIX}/${sessionId}`,
  )) as { data?: unknown; error?: unknown };
  assertOk(data, '删除失败');
}
