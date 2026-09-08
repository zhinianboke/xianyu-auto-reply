import { getApiClient, extractError } from './client';

// ---------------------------------------------------------------------------
// 通知渠道管理（钉钉/飞书/Bark/邮件/Webhook/企业微信）
// 后端路由前缀: /api/v1/notification-channels
// ---------------------------------------------------------------------------

export interface NotificationChannel {
  id: number;
  name: string;
  type: string;
  enabled: boolean;
  config: Record<string, unknown>;
  created_at?: string;
}

/** 通知渠道类型选项 */
export const CHANNEL_TYPES = [
  { value: 'dingtalk', label: '钉钉' },
  { value: 'feishu', label: '飞书' },
  { value: 'bark', label: 'Bark' },
  { value: 'email', label: '邮件' },
  { value: 'webhook', label: 'Webhook' },
  { value: 'wecom', label: '企业微信' },
] as const;

function unwrap<T>(data: unknown): T | null {
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if ('data' in obj && obj.data != null) return obj.data as T;
    if ('success' in obj && obj.success === false) return null;
  }
  return (data as T) ?? null;
}

function extractArray<T>(data: unknown, normalize?: (raw: Record<string, unknown>) => T): T[] {
  const body = unwrap<unknown>(data);
  let arr: unknown[] | null = null;
  if (Array.isArray(body)) arr = body;
  else if (body && typeof body === 'object' && Array.isArray((body as Record<string, unknown>).data)) {
    arr = (body as { data: unknown[] }).data;
  }
  if (!arr) return [];
  if (normalize) return arr.map((it) => normalize(it as Record<string, unknown>));
  return arr as T[];
}

function normalizeChannel(raw: Record<string, unknown>): NotificationChannel {
  return {
    id: Number(raw.id ?? raw.channel_id ?? 0),
    name: String(raw.name ?? ''),
    type: String(raw.type ?? raw.channel_type ?? ''),
    enabled: Boolean(raw.enabled ?? true),
    config: (raw.config ?? raw.channel_config ?? {}) as Record<string, unknown>,
    created_at: raw.created_at != null ? String(raw.created_at) : undefined,
  };
}

/** 获取通知渠道列表 */
export async function getNotificationChannels(): Promise<NotificationChannel[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/notification-channels', {
    params: { query: { page: 1, page_size: 200 } },
  })) as { data?: unknown; error?: unknown };
  return extractArray<NotificationChannel>(data, normalizeChannel);
}

/** 新建通知渠道 */
export async function createNotificationChannel(
  name: string,
  type: string,
  config: Record<string, unknown>,
): Promise<NotificationChannel | null> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)('/api/v1/notification-channels', {
    body: { name, type, config, enabled: true },
  })) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const inner = unwrap<unknown>(data);
  if (inner && typeof inner === 'object' && (inner as Record<string, unknown>).id != null) {
    return normalizeChannel(inner as Record<string, unknown>);
  }
  return null;
}

/** 更新通知渠道 */
export async function updateNotificationChannel(
  id: number,
  updates: Partial<Pick<NotificationChannel, 'name' | 'type' | 'config' | 'enabled'>>,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/notification-channels/${id}`, { body: updates });
}

/** 删除通知渠道 */
export async function deleteNotificationChannel(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/notification-channels/${id}`);
}

/** 发送测试消息 */
export async function testNotificationChannel(
  id: number,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)(
    `/api/v1/notification-channels/${id}/test`,
  )) as { data?: { success?: boolean; message?: string }; error?: unknown };
  if (error) throw await extractError(error);
  const body = data as Record<string, unknown> | undefined;
  return { success: body?.success !== false, message: body?.message as string | undefined };
}

// ---------------------------------------------------------------------------
// 消息通知绑定（账号 × 渠道绑定，按账号维度开关消息推送）
// 后端路由前缀: /api/v1/message-notifications
// ---------------------------------------------------------------------------

export interface MessageNotificationBinding {
  id: number;
  account_id: string;
  channel_id: number;
  channel_name?: string;
  enabled: boolean;
}

/** 获取消息通知绑定列表 */
export async function getMessageNotifications(): Promise<MessageNotificationBinding[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/message-notifications', {
    params: { query: { page: 1, page_size: 200 } },
  })) as { data?: unknown; error?: unknown };
  return extractArray<MessageNotificationBinding>(
    data,
    (raw) =>
      ({
        id: Number(raw.id ?? 0),
        account_id: String(raw.account_id ?? raw.cookie_id ?? ''),
        channel_id: Number(raw.channel_id ?? 0),
        channel_name: raw.channel_name != null ? String(raw.channel_name) : undefined,
        enabled: Boolean(raw.enabled ?? true),
      }) as MessageNotificationBinding,
  );
}

/** 新建消息通知绑定 */
export async function createMessageNotification(
  accountId: string,
  channelId: number,
): Promise<MessageNotificationBinding | null> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)(`/api/v1/message-notifications/${accountId}`, {
    body: { channel_id: channelId, enabled: true },
  })) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const inner = unwrap<unknown>(data);
  if (inner && typeof inner === 'object' && (inner as Record<string, unknown>).id != null) {
    const raw = inner as Record<string, unknown>;
    return {
      id: Number(raw.id ?? 0),
      account_id: String(raw.account_id ?? accountId),
      channel_id: Number(raw.channel_id ?? channelId),
      enabled: Boolean(raw.enabled ?? true),
    };
  }
  return null;
}

/** 更新绑定（启停） */
export async function updateMessageNotification(
  id: number,
  enabled: boolean,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/message-notifications/${id}`, { body: { enabled } });
}

/** 删除绑定 */
export async function deleteMessageNotification(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/message-notifications/${id}`);
}
