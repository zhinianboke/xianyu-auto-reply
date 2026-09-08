import { getApiClient, extractError } from './client';

/** 后端统一响应为 { success, message, data }，抽出内部 data；未包裹则原样返回 */
function unwrapData<T>(body: unknown): T {
  if (body && typeof body === 'object' && 'success' in body && 'data' in body) {
    const inner = (body as { data: unknown }).data;
    if (inner != null) return inner as T;
  }
  return body as T;
}

/**
 * 查询指定会话的黑名单状态。
 * GET /api/v1/chat-new/official-blacklist/{account_id}/{cid}
 */
export async function getBlacklistStatus(
  accountId: string,
  cid: string,
): Promise<{ is_blacklisted: boolean }> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `/api/v1/chat-new/official-blacklist/${accountId}/${cid}`,
  )) as { data?: unknown; error?: unknown };
  return unwrapData<{ is_blacklisted: boolean }>(data ?? { is_blacklisted: false });
}

/**
 * 加入或解除黑名单。
 * POST /api/v1/chat-new/official-blacklist/{account_id}/{cid}/{action}
 */
export async function changeBlacklist(
  accountId: string,
  cid: string,
  action: 'add' | 'remove',
): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)(
    `/api/v1/chat-new/official-blacklist/${accountId}/${cid}/${action}`,
  );
}
