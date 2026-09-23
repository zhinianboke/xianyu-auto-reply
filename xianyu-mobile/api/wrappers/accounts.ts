import { getApiClient, extractError } from './client';
import { ApiError } from './errors';

export interface AccountOption {
  pk: number;
  id: string;
  enabled: boolean;
  remark?: string;
  show_browser?: boolean;
}

export async function getAccountOptions(): Promise<AccountOption[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/cookies/options')) as {
    data?: AccountOption[];
    error?: unknown;
  };
  return data ?? [];
}

export async function toggleAccount(
  accountId: string,
  enabled: boolean,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/cookies/${accountId}/status`, {
    body: { enabled },
  });
}

// ---------------------------------------------------------------------------
// Phase 2: 扫码登录 + 账号详情 + 账号编辑
// ---------------------------------------------------------------------------

export interface QrLoginSession {
  session_id: string;
  qr_code_url: string;
  status?: string;
  face_qr_url?: string;
  message?: string;
}

/** 后端统一响应为 { success, message, data }，抽出内部 data；未包裹则原样返回 */
function unwrapData<T>(body: unknown): T {
  if (body && typeof body === 'object' && 'success' in body && 'data' in body) {
    const inner = (body as { data: unknown }).data;
    if (inner != null) return inner as T;
  }
  return body as T;
}

/** 生成扫码登录会话 */
export async function generateQrLogin(): Promise<QrLoginSession> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)('/api/v1/qr-login/generate')) as {
    data?: unknown;
    error?: unknown;
  };
  return unwrapData<QrLoginSession>(data);
}

/** 查询扫码登录状态 */
export async function checkQrLoginStatus(
  sessionId: string,
): Promise<QrLoginSession> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `/api/v1/qr-login/status/${sessionId}`,
  )) as { data?: unknown; error?: unknown };
  return unwrapData<QrLoginSession>(data);
}

/** 扫码成功后获取 Cookie，服务端据此持久化账号 */
export async function getQrLoginCookie(sessionId: string): Promise<void> {
  const client = await getApiClient();
  await (client.GET as any)(`/api/v1/qr-login/cookie/${sessionId}`);
}

export interface AccountDetail {
  pk: number;
  id: string;
  enabled: boolean;
  remark?: string;
  online?: boolean;
  keyword_count?: number;
  today_reply_count?: number;
  filter_count?: number;
  disable_reason?: string;
  show_browser?: boolean;
  pause_duration?: number;
  // 高级配置初始值：消息等待时间 / 回复延迟（秒），后端在 details 接口返回
  message_expire_time?: number;
  reply_delay_seconds?: number;
  // 编辑弹窗回显用：Cookie / 登录信息（details 接口随账号一起返回）
  cookie?: string;
  username?: string;
  login_password?: string;
  // Phase 3 功能开关：后端在 details 接口返回时存在则用于回显初始状态
  auto_confirm?: boolean;
  auto_polish?: boolean;
  auto_red_flower?: boolean;
  scheduled_redelivery?: boolean;
  scheduled_rate?: boolean;
  confirm_before_send?: boolean;
  send_before_confirm?: boolean;
  only_send_card?: boolean;
  ai_reply_block_ordered_users?: boolean;
}

/** 分页获取账号详情（含在线状态、今日回复数、关键词数等） */
export async function getAccountDetailsPaginated(
  page: number,
  pageSize: number,
): Promise<{ data: AccountDetail[]; total: number }> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/cookies/details/paginated',
    { params: { query: { page, page_size: pageSize } } },
  )) as { data?: unknown; error?: unknown };
  const body = unwrapData<unknown>(data);
  if (body && typeof body === 'object' && 'data' in body) {
    const obj = body as { data: unknown; total?: number };
    const arr = Array.isArray(obj.data) ? (obj.data as AccountDetail[]) : [];
    return { data: arr, total: obj.total ?? arr.length };
  }
  if (Array.isArray(body)) {
    return { data: body as AccountDetail[], total: body.length };
  }
  return { data: [], total: 0 };
}

/** 更新账号备注 */
export async function updateAccountRemark(
  accountId: string,
  remark: string,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/cookies/${accountId}/remark`, {
    body: { remark },
  });
}

/** 更新账号 Cookie 值（后端 body 字段为 { id, value }） */
export async function updateAccountCookie(
  accountId: string,
  value: string,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/cookies/${accountId}`, {
    body: { id: accountId, value },
  });
}

/** 更新账号暂停时间（pause_duration，单位秒） */
export async function updateAccountPauseDuration(
  accountId: string,
  pauseDuration: number,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(
    `/api/v1/cookies/${accountId}/pause-duration`,
    { body: { pause_duration: pauseDuration } },
  );
}

/** 更新账号登录信息（用户名 / 密码 / 是否显示浏览器） */
export async function updateAccountLoginInfo(
  accountId: string,
  data: { username?: string; login_password?: string; show_browser?: boolean },
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/cookies/${accountId}/login-info`, {
    body: data,
  });
}

/** 删除账号 */
export async function deleteAccount(accountId: string): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/cookies/${accountId}`);
}

// ---------------------------------------------------------------------------
// Phase 3: 账号功能增强 — 9 个功能开关 / 批量操作 / 导入导出
// ---------------------------------------------------------------------------

/** 9 个功能开关的 key，与后端字段命名（snake_case）保持一致 */
export type ToggleKey =
  | 'auto_confirm'
  | 'auto_polish'
  | 'auto_red_flower'
  | 'scheduled_redelivery'
  | 'scheduled_rate'
  | 'confirm_before_send'
  | 'send_before_confirm'
  | 'only_send_card'
  | 'ai_reply_block_ordered_users';

/** ToggleKey → 后端 PUT 路径片段 */
const TOGGLE_PATHS: Record<ToggleKey, string> = {
  auto_confirm: 'auto-confirm',
  auto_polish: 'auto-polish',
  auto_red_flower: 'auto-red-flower',
  scheduled_redelivery: 'scheduled-redelivery',
  scheduled_rate: 'scheduled-rate',
  confirm_before_send: 'confirm-before-send',
  send_before_confirm: 'send-before-confirm',
  only_send_card: 'only-send-card',
  ai_reply_block_ordered_users: 'ai-reply-block-ordered-users',
};

/** 切换单个账号的某个功能开关 */
export async function toggleAccountFeature(
  accountId: string,
  key: ToggleKey,
  enabled: boolean,
): Promise<void> {
  const client = await getApiClient();
  const path = `/api/v1/cookies/${accountId}/${TOGGLE_PATHS[key]}`;
  // 后端要求 body 字段名为 ToggleKey（snake_case，如 auto_confirm），而非 {enabled}
  await (client.PUT as any)(path, { body: { [key]: enabled } });
}

// ---- 批量操作 ----

/** 批量启用/禁用账号 */
export async function batchUpdateStatus(
  accountIds: string[],
  enabled: boolean,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)('/api/v1/cookies/status/batch', {
    body: { account_ids: accountIds, enabled },
  });
}

/** 批量清除 Token 缓存 */
export async function batchClearTokenCache(accountIds: string[]): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)('/api/v1/cookies/clear-token-cache/batch', {
    body: { account_ids: accountIds },
  });
}

/** 批量关闭通知 */
export async function batchCloseNotice(accountIds: string[]): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)('/api/v1/cookies/close-notice/batch', {
    body: { account_ids: accountIds },
  });
}

/** 批量续期登录 */
export async function batchRenewLogin(accountIds: string[]): Promise<void> {
  const client = await getApiClient();
  // 后端要求 body 直接是账号 id 数组，而非 {account_ids}
  await (client.POST as any)('/api/v1/cookies/renew-login', {
    body: accountIds,
  });
}

// ---- 导入导出 ----

/** 导出账号（返回二进制 Blob，调用方负责落盘/分享） */
export async function exportAccounts(accountIds?: string[]): Promise<Blob> {
  const client = await getApiClient();
  const body =
    accountIds && accountIds.length > 0 ? { account_ids: accountIds } : {};
  const { data } = (await (client.POST as any)('/api/v1/cookies/export', {
    body,
    parseAs: 'blob',
  })) as { data?: Blob; error?: unknown };
  if (!data) throw new ApiError('导出失败：未收到文件', 0);
  return data;
}

/** 导入账号（Excel 文件，通过 multipart/form-data 上传） */
export async function importAccounts(fileUri: string): Promise<void> {
  const client = await getApiClient();
  const ext = (fileUri.split('.').pop() || 'xlsx').toLowerCase().split('?')[0];
  const typeMap: Record<string, string> = {
    xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    xls: 'application/vnd.ms-excel',
    csv: 'text/csv',
  };
  const mimeType = typeMap[ext] || 'application/octet-stream';
  const formData = new FormData();
  formData.append('file', {
    uri: fileUri,
    name: `accounts.${ext}`,
    type: mimeType,
  } as any);
  await (client.POST as any)('/api/v1/cookies/import', { body: formData });
}

// ---------------------------------------------------------------------------
// 默认回复设置（每个闲鱼账号独立配置）
// 后端路由前缀: /api/v1/default-replies
// ---------------------------------------------------------------------------

export interface DefaultReplyConfig {
  enabled: boolean;
  reply_content: string;
  reply_image: string;
  reply_once: boolean;
  reply_type: string; // 'text' | 'api'
  api_url: string;
  api_timeout: number;
}

function unwrapReply<T>(data: unknown, fallback: T): T {
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if ('data' in obj && obj.data != null && typeof obj.data === 'object') {
      return { ...fallback, ...(obj.data as Partial<T>) };
    }
    return { ...fallback, ...(obj as Partial<T>) };
  }
  return fallback;
}

/** 获取账号的默认回复设置 */
export async function getDefaultReply(
  accountId: string,
): Promise<DefaultReplyConfig> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    `/api/v1/default-replies/${encodeURIComponent(accountId)}`,
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  return unwrapReply<DefaultReplyConfig>(data, {
    enabled: false,
    reply_content: '',
    reply_image: '',
    reply_once: false,
    reply_type: 'text',
    api_url: '',
    api_timeout: 80,
  });
}

/** 更新账号的默认回复设置 */
export async function updateDefaultReply(
  accountId: string,
  config: DefaultReplyConfig,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `/api/v1/default-replies/${encodeURIComponent(accountId)}`,
    { body: config },
  )) as { data?: { success?: boolean; message?: string }; error?: unknown };
  if (error) throw await extractError(error);
  return { success: data?.success ?? true, message: data?.message };
}

/** 上传默认回复图片（multipart/form-data，字段名 image），返回可保存的图片地址 */
export async function uploadDefaultReplyImage(
  accountId: string,
  fileUri: string,
): Promise<string> {
  const client = await getApiClient();
  const ext = (fileUri.split('.').pop() || 'jpg').toLowerCase().split('?')[0];
  const typeMap: Record<string, string> = {
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    png: 'image/png',
    gif: 'image/gif',
    webp: 'image/webp',
  };
  const mimeType = typeMap[ext] || 'image/jpeg';
  const formData = new FormData();
  formData.append('image', {
    uri: fileUri,
    name: `reply.${ext}`,
    type: mimeType,
  } as any);
  const { data, error } = (await (client.POST as any)(
    `/api/v1/default-replies/${encodeURIComponent(accountId)}/upload-image`,
    { body: formData },
  )) as { data?: { success?: boolean; image_url?: string; message?: string }; error?: unknown };
  if (error) throw await extractError(error);
  const body = data as Record<string, unknown> | undefined;
  const url = body?.image_url as string | undefined;
  if (!url) throw new ApiError(body?.message as string | '图片上传失败', 0);
  return url;
}
