import { getApiClient, extractError } from './client';

/** 消息过滤类型：skip_reply=跳过AI回复，skip_notify=跳过通知 */
export type MessageFilterType = 'skip_reply' | 'skip_notify';

export interface MessageFilter {
  id: number;
  account_id: string;
  keyword: string;
  filter_type: MessageFilterType;
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
}

/** 解开 {success, message, data} 包裹 */
function unwrapData<T>(body: unknown): T {
  if (body && typeof body === 'object' && 'success' in body && 'data' in body) {
    const inner = (body as { data: unknown }).data;
    if (inner != null) return inner as T;
  }
  return body as T;
}

export async function getMessageFilters(accountId?: string): Promise<MessageFilter[]> {
  const client = await getApiClient();
  const params = accountId ? { account_id: accountId } : undefined;
  const { data } = (await (client.GET as any)('/api/v1/message-filters', {
    params: params ? { query: params } : undefined,
  })) as { data?: unknown; error?: unknown };
  const body = unwrapData<unknown>(data);
  return Array.isArray(body) ? (body as MessageFilter[]) : [];
}

/** 创建过滤规则。后端要求 {keyword, filter_types: 类型数组, account_id} */
export async function createMessageFilter(
  filterType: MessageFilterType,
  keyword: string,
  accountId: string,
): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)('/api/v1/message-filters', {
    body: { keyword, filter_types: [filterType], account_id: accountId },
  });
}

/** 更新过滤规则。后端要求 {keyword?, filter_type?, enabled?}（filter_type 单数） */
export async function updateMessageFilter(
  id: number,
  filterType: MessageFilterType,
  keyword: string,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/message-filters/${id}`, {
    body: { keyword, filter_type: filterType },
  });
}

export async function deleteMessageFilter(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/message-filters/${id}`);
}

export async function toggleMessageFilter(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/message-filters/${id}/toggle`);
}

void extractError;
