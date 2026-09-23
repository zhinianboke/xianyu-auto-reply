import { getApiClient, extractError } from './client';

/** 管理员视角的用户信息 */
export interface AdminUser {
  id: number;
  username: string;
  email?: string;
  role?: string;
  status?: string;
  is_admin: boolean;
  account_limit?: number;
  cookie_count?: number;
  balance?: string;
  expire_at?: string;
}

/** 日志条目（管理员日志 / 自动回复日志 / 登录日志共用） */
export interface LogEntry {
  id: number;
  type?: string;
  content: string;
  created_at: string;
}

/**
 * 后端统一响应可能为 `{ success, data }` 或裸数据，
 * 抽出内部 data；未包裹则原样返回（与 accounts.ts / settings.ts 保持一致）。
 */
function unwrapData<T>(body: unknown): T {
  if (
    body &&
    typeof body === 'object' &&
    'success' in body &&
    'data' in body
  ) {
    const inner = (body as { data: unknown }).data;
    if (inner != null) return inner as T;
  }
  return body as T;
}

/**
 * 从 `{ success, data }` 包裹的响应中取出内层 data；未包裹则原样返回。
 * 与 unwrapData 不同：unwrapData 在命中 `success && data` 时丢弃外层其余字段，
 * 本函数仅取出 data，适用于 success-rate 这类"外层有 message 但内层才是数据"的形态。
 */
function extractInner<T>(raw: unknown): T | null {
  if (raw && typeof raw === 'object') {
    const obj = raw as Record<string, unknown>;
    if ('data' in obj && obj.data != null) return obj.data as T;
  }
  return (raw as T) ?? null;
}

/**
 * 从分页列表响应中提取 items + total，兼容多种后端包裹形态：
 * - 裸数组 [...]
 * - { data: [...], total }
 * - { success, data: [...], total }
 * - { success, data: { data: [...], total } }
 * 用于风控日志 / 登录日志等 limit/offset 分页接口。
 */
function parseList<T>(
  raw: unknown,
  normalize: (r: Record<string, unknown>) => T,
): { items: T[]; total: number } {
  let arr: unknown[] | null = null;
  let total: number | undefined;
  const probe = (obj: Record<string, unknown>): boolean => {
    if (Array.isArray(obj.data)) {
      arr = obj.data as unknown[];
      total = typeof obj.total === 'number' ? obj.total : undefined;
      return true;
    }
    if (Array.isArray(obj.items)) {
      arr = obj.items;
      total = typeof obj.total === 'number' ? obj.total : undefined;
      return true;
    }
    return false;
  };
  if (Array.isArray(raw)) {
    arr = raw;
  } else if (raw && typeof raw === 'object') {
    const obj = raw as Record<string, unknown>;
    if (!probe(obj)) {
      // 兼容 { success, data: { data: [...], total } } 双层包裹
      const inner = obj.data;
      if (inner && typeof inner === 'object' && !Array.isArray(inner)) {
        probe(inner as Record<string, unknown>);
      }
    }
  }
  if (!arr) return { items: [], total: 0 };
  const items = arr.map((it) => normalize(it as Record<string, unknown>));
  return { items, total: typeof total === 'number' ? total : items.length };
}

/** 获取用户列表（管理员） */
export async function getAdminUsers(): Promise<AdminUser[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/admin/users')) as {
    data?: unknown;
    error?: unknown;
  };
  const body = unwrapData<unknown>(data);
  return Array.isArray(body) ? (body as AdminUser[]) : [];
}

/** 创建用户（管理员） */
export async function createAdminUser(
  username: string,
  email: string,
  password: string,
  role: string,
): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)('/api/v1/admin/users', {
    body: { username, email, password, role },
  });
}

/** 更新用户（管理员） */
export async function updateAdminUser(
  userId: number,
  data: Partial<AdminUser>,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/admin/users/${userId}`, { body: data });
}

/** 删除用户（管理员） */
export async function deleteAdminUser(userId: number): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/admin/users/${userId}`);
}

/** 充值（管理员） */
export async function rechargeUser(
  userId: number,
  amount: string,
): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)(`/api/v1/admin/users/${userId}/recharge`, {
    body: { amount },
  });
}

/** 获取管理员日志（分页） */
export async function getAdminLogs(
  page: number,
  pageSize: number,
): Promise<{ data: LogEntry[]; total: number }> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/admin/logs', {
    params: { query: { page, page_size: pageSize } },
  })) as { data?: unknown; error?: unknown };
  const body = unwrapData<unknown>(data);
  if (body && typeof body === 'object' && 'data' in body) {
    const obj = body as { data?: unknown; total?: number };
    const arr = Array.isArray(obj.data) ? (obj.data as LogEntry[]) : [];
    return { data: arr, total: obj.total ?? arr.length };
  }
  if (Array.isArray(body)) {
    return { data: body as LogEntry[], total: body.length };
  }
  return { data: [], total: 0 };
}

/** 清除管理员日志 */
export async function clearAdminLogs(): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)('/api/v1/admin/logs/clear');
}

/** 获取自动回复日志（分页） */
export async function getAutoReplyLogs(page: number): Promise<LogEntry[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/auto-reply-logs', {
    params: { query: { page } },
  })) as { data?: unknown; error?: unknown };
  const body = unwrapData<unknown>(data);
  if (Array.isArray(body)) return body as LogEntry[];
  if (
    body &&
    typeof body === 'object' &&
    'data' in body &&
    Array.isArray((body as { data?: unknown }).data)
  ) {
    return (body as { data: LogEntry[] }).data;
  }
  return [];
}

// ---------------------------------------------------------------------------
// 账号登录日志（对齐 web AccountLoginLogs）
// 后端路由: GET  /api/v1/account-login-logs
//          DELETE /api/v1/admin/account-login-logs
// ---------------------------------------------------------------------------

/** 账号登录日志条目（对齐 web AccountLoginLog） */
export interface AccountLoginLog {
  id: number;
  cookie_id: string;
  username?: string | null;
  trigger_reason?: string | null;
  login_status: string;
  failure_reason?: string | null;
  error_message?: string | null;
  updated_cookie_names?: string | null;
  duration_ms?: number | null;
  account_status?: string;
  disable_reason?: string | null;
  created_at: string;
}

/** 账号登录日志查询参数（cookie_id/日期/login_status 筛选 + offset 分页） */
export interface AccountLoginLogQuery {
  limit?: number;
  offset?: number;
  cookie_id?: string;
  start_date?: string;
  end_date?: string;
  login_status?: string;
}

/** 获取账号登录日志（支持账号/日期/状态筛选 + offset 分页） */
export async function getAccountLoginLogs(
  query: AccountLoginLogQuery = {},
): Promise<{ items: AccountLoginLog[]; total: number }> {
  const client = await getApiClient();
  const q: Record<string, string | number> = {
    limit: query.limit ?? 20,
    offset: query.offset ?? 0,
  };
  if (query.cookie_id) q.cookie_id = query.cookie_id;
  if (query.start_date) q.start_date = query.start_date;
  if (query.end_date) q.end_date = query.end_date;
  if (query.login_status) q.login_status = query.login_status;
  const { data } = (await (client.GET as any)('/api/v1/account-login-logs', {
    params: { query: q },
  })) as { data?: unknown; error?: unknown };
  return parseList<AccountLoginLog>(data, (r) => ({
    id: Number(r.id ?? 0),
    cookie_id: String(r.cookie_id ?? r.cookie_name ?? ''),
    username: r.username != null ? String(r.username) : null,
    trigger_reason: r.trigger_reason != null ? String(r.trigger_reason) : null,
    login_status: String(r.login_status ?? ''),
    failure_reason: r.failure_reason != null ? String(r.failure_reason) : null,
    error_message: r.error_message != null ? String(r.error_message) : null,
    updated_cookie_names:
      r.updated_cookie_names != null ? String(r.updated_cookie_names) : null,
    duration_ms: r.duration_ms != null ? Number(r.duration_ms) : null,
    account_status: r.account_status != null ? String(r.account_status) : undefined,
    disable_reason: r.disable_reason != null ? String(r.disable_reason) : null,
    created_at: r.created_at != null ? String(r.created_at) : '',
  }));
}

/**
 * 清理账号登录日志。
 * - 传 days  => 仅删除 N 天前的日志（保留近 N 天）
 * - 不传 days => 清空全部
 * - cookieId => 仅清理该账号
 */
export async function clearAccountLoginLogs(
  params?: { days?: number; cookieId?: string },
): Promise<void> {
  const client = await getApiClient();
  const query: Record<string, string> = {};
  if (params?.days != null) query.days = String(params.days);
  if (params?.cookieId) query.cookie_id = params.cookieId;
  const { error } = (await (client.DELETE as any)(
    '/api/v1/admin/account-login-logs',
    { params: { query } },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
}

// ---------------------------------------------------------------------------
// 风控日志（对齐 web RiskLogs）
// 后端路由:
//   GET  /api/v1/risk-control-logs                         列表 + 筛选
//   GET  /api/v1/risk-control-logs/today-success-rate     当日成功率
//   GET  /api/v1/risk-control-logs/local-slider-config    本机滑块开关
//   PUT  /api/v1/risk-control-logs/local-slider-config
//   GET  /api/v1/captcha/remote-config                     远程过滑块配置
//   PUT  /api/v1/captcha/remote-config
//   POST /api/v1/captcha/slider-solve/test                测试远程连通
//   DELETE /api/v1/admin/risk-control-logs                清空（可按账号）
// ---------------------------------------------------------------------------

/** 风控日志条目（对齐 web RiskLog） */
export interface RiskControlLog {
  id: number;
  cookie_id?: string;
  risk_type?: string;
  message?: string;
  processing_result?: string;
  processing_status?: string;
  captcha_engine?: string;
  call_type?: string;
  call_user?: string;
  error_message?: string;
  /** 由 processing_status==='success' 派生，便于列表图标判定 */
  success?: boolean;
  created_at?: string;
  updated_at?: string;
}

/** 风控日志查询参数（多维度筛选 + offset 分页） */
export interface RiskLogQuery {
  limit?: number;
  offset?: number;
  cookie_id?: string;
  start_date?: string;
  end_date?: string;
  processing_status?: string;
  call_type?: string;
  call_user?: string;
}

/** 当日风控成功率（总体/本机/远程三维度，对齐 web RiskTodaySuccessRate） */
export interface RiskTodaySuccessRate {
  date?: string;
  total: number;
  success: number;
  rate: number;
  local_total?: number;
  local_success?: number;
  local_rate?: number;
  remote_total?: number;
  remote_success?: number;
  remote_rate?: number;
  processing?: number;
  local_processing?: number;
  remote_processing?: number;
}

/** 远程过滑块全局配置（存于 system_settings，仅管理员） */
export interface RemoteCaptchaConfig {
  url: string;
  secret_key: string;
  pass_cookies: boolean;
  block_remote_calls: boolean;
  local_weight: number;
  remote_weight: number;
  remote_processing_max: number;
  remote_cooldown_seconds: number;
}

/** 本机滑块处理开关（enabled=true 表示"本机滑块不处理"） */
export interface LocalSliderConfig {
  enabled: boolean;
}

/** 获取风控日志列表（多维度筛选 + offset 分页） */
export async function getRiskControlLogs(
  query: RiskLogQuery = {},
): Promise<{ items: RiskControlLog[]; total: number }> {
  const client = await getApiClient();
  const q: Record<string, string | number> = {
    limit: query.limit ?? 20,
    offset: query.offset ?? 0,
  };
  if (query.cookie_id) q.cookie_id = query.cookie_id;
  if (query.start_date) q.start_date = query.start_date;
  if (query.end_date) q.end_date = query.end_date;
  if (query.processing_status) q.processing_status = query.processing_status;
  if (query.call_type) q.call_type = query.call_type;
  if (query.call_user) q.call_user = query.call_user;
  const { data } = (await (client.GET as any)('/api/v1/risk-control-logs', {
    params: { query: q },
  })) as { data?: unknown; error?: unknown };
  return parseList<RiskControlLog>(data, (r) => {
    const status = r.processing_status != null ? String(r.processing_status) : undefined;
    return {
      id: Number(r.id ?? 0),
      cookie_id:
        r.cookie_id != null
          ? String(r.cookie_id)
          : r.cookie_name != null
            ? String(r.cookie_name)
            : undefined,
      risk_type:
        r.risk_type != null
          ? String(r.risk_type)
          : r.event_type != null
            ? String(r.event_type)
            : undefined,
      message:
        r.message != null
          ? String(r.message)
          : r.event_description != null
            ? String(r.event_description)
            : undefined,
      processing_result:
        r.processing_result != null ? String(r.processing_result) : undefined,
      processing_status: status,
      captcha_engine: r.captcha_engine != null ? String(r.captcha_engine) : undefined,
      call_type: r.call_type != null ? String(r.call_type) : undefined,
      call_user: r.call_user != null ? String(r.call_user) : undefined,
      error_message: r.error_message != null ? String(r.error_message) : undefined,
      success: status === 'success',
      created_at: r.created_at != null ? String(r.created_at) : undefined,
      updated_at: r.updated_at != null ? String(r.updated_at) : undefined,
    };
  });
}

/** 获取当日风控成功率；失败返回 null 不阻断页面（与 web 一致） */
export async function getRiskTodaySuccessRate(): Promise<RiskTodaySuccessRate | null> {
  try {
    const client = await getApiClient();
    const { data } = (await (client.GET as any)(
      '/api/v1/risk-control-logs/today-success-rate',
    )) as { data?: unknown; error?: unknown };
    const inner = extractInner<Record<string, unknown>>(data);
    if (!inner) return null;
    const num = (v: unknown): number | undefined =>
      v != null && typeof v !== 'boolean' ? Number(v) : undefined;
    return {
      date: inner.date != null ? String(inner.date) : undefined,
      total: Number(inner.total ?? 0),
      success: Number(inner.success ?? 0),
      // 后端字段名为 rate（已换算百分数），success_rate 为兼容保留
      rate: Number(inner.rate ?? inner.success_rate ?? 0),
      local_total: num(inner.local_total),
      local_success: num(inner.local_success),
      local_rate: num(inner.local_rate),
      remote_total: num(inner.remote_total),
      remote_success: num(inner.remote_success),
      remote_rate: num(inner.remote_rate),
      processing: num(inner.processing),
      local_processing: num(inner.local_processing),
      remote_processing: num(inner.remote_processing),
    };
  } catch {
    // 成功率加载失败不阻断页面
    return null;
  }
}

/** 清空风控日志（可按账号） */
export async function clearRiskLogs(cookieId?: string): Promise<void> {
  const client = await getApiClient();
  const query: Record<string, string> = {};
  if (cookieId) query.cookie_id = cookieId;
  const { error } = (await (client.DELETE as any)(
    '/api/v1/admin/risk-control-logs',
    { params: { query } },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
}

/** 清空处理中的风控日志（仅删除 processing_status=processing 的记录） */
export async function clearProcessingRiskLogs(): Promise<void> {
  const client = await getApiClient();
  const { error } = (await (client.DELETE as any)(
    '/api/v1/admin/risk-control-logs',
    { params: { query: { processing_status: 'processing' } } },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
}

/** 读取"本机滑块不处理"开关（仅管理员） */
export async function getLocalSliderConfig(): Promise<LocalSliderConfig> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/risk-control-logs/local-slider-config',
  )) as { data?: unknown; error?: unknown };
  const inner = extractInner<Record<string, unknown>>(data);
  return { enabled: Boolean(inner?.enabled) };
}

/** 实时更新"本机滑块不处理"开关（仅管理员） */
export async function updateLocalSliderConfig(
  enabled: boolean,
): Promise<LocalSliderConfig> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    '/api/v1/risk-control-logs/local-slider-config',
    { body: { enabled } },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const inner = extractInner<Record<string, unknown>>(data);
  return { enabled: Boolean(inner?.enabled ?? enabled) };
}

/** 读取远程过滑块全局配置（仅管理员） */
export async function getRemoteCaptchaConfig(): Promise<RemoteCaptchaConfig> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/captcha/remote-config')) as {
    data?: unknown;
    error?: unknown;
  };
  const inner = extractInner<Record<string, unknown>>(data) ?? {};
  return {
    url: String(inner.url ?? ''),
    secret_key: String(inner.secret_key ?? ''),
    pass_cookies: Boolean(inner.pass_cookies),
    block_remote_calls:
      inner.block_remote_calls != null ? Boolean(inner.block_remote_calls) : true,
    local_weight: Number(inner.local_weight ?? 1),
    remote_weight: Number(inner.remote_weight ?? 1),
    remote_processing_max: Number(inner.remote_processing_max ?? 20),
    remote_cooldown_seconds: Number(inner.remote_cooldown_seconds ?? 600),
  };
}

/** 保存远程过滑块全局配置（仅管理员） */
export async function saveRemoteCaptchaConfig(
  cfg: RemoteCaptchaConfig,
): Promise<void> {
  const client = await getApiClient();
  const { error } = (await (client.PUT as any)('/api/v1/captcha/remote-config', {
    body: cfg,
  })) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
}

/**
 * 测试远程过滑块服务连通性。
 * 连接/业务失败时返回 { success: false, message } 而非抛错，
 * 便于调用方用 toast 展示原因（web 同口径：返回[punish 链接不能为空]代表成功）。
 */
export async function testRemoteSliderSolve(
  url: string,
  secretKey: string,
): Promise<{ success: boolean; message?: string }> {
  try {
    const client = await getApiClient();
    const { data } = (await (client.POST as any)(
      '/api/v1/captcha/slider-solve/test',
      { body: { url, secret_key: secretKey } },
    )) as { data?: unknown; error?: unknown };
    const body = (data ?? {}) as Record<string, unknown>;
    return {
      success: body.success != null ? Boolean(body.success) : true,
      message: body.message != null ? String(body.message) : undefined,
    };
  } catch (e) {
    return {
      success: false,
      message: e instanceof Error ? e.message : '测试失败',
    };
  }
}

// ==================== 定时任务 ====================

export interface ScheduledTask {
  id: number;
  task_code: string;
  task_name: string;
  interval_seconds: number;
  enabled: boolean;
  description: string | null;
  task_running: boolean;
}

export async function getScheduledTasks(): Promise<{ tasks: ScheduledTask[]; schedulerRunning: boolean }> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/admin/scheduled-tasks')) as { data?: unknown };
  const body = unwrapData<Record<string, unknown>>(data);
  const tasks = Array.isArray(body) ? body as ScheduledTask[] : (body as { data?: ScheduledTask[] })?.data ?? [];
  return { tasks, schedulerRunning: Boolean((body as { scheduler_running?: boolean })?.scheduler_running) };
}

export async function updateScheduledTask(id: number, params: { interval_seconds?: number; enabled?: boolean }): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/admin/scheduled-tasks/${id}`, { body: params });
}

export async function triggerScheduledTask(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)(`/api/v1/admin/scheduled-tasks/${id}/trigger`, { body: {} });
}

// ==================== 数据管理 ====================

export async function getTableData(tableName: string): Promise<{ rows: Record<string, unknown>[]; count: number; columns: string[] }> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(`/api/v1/admin/data/${tableName}`)) as { data?: unknown };
  const body = unwrapData<Record<string, unknown>>(data);
  const rows = (body?.data as Record<string, unknown>[]) ?? (Array.isArray(body) ? body as Record<string, unknown>[] : []);
  const count = Number(body?.count ?? rows.length);
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];
  return { rows, count, columns };
}

export async function clearTableData(tableName: string): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/admin/data/${tableName}`);
}
