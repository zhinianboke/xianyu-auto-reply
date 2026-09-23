import { getApiClient, extractError } from './client';
import { withTimeout } from '@/lib/timeout';

export interface SearchResult {
  item_id: string;
  title: string;
  price: string;
  seller_id?: string;
  seller_name?: string;
  image_url?: string;
  url?: string;
}

/** 解开 {success, message, data} 包裹，与其它 wrapper 保持一致 */
function unwrapData<T>(body: unknown): T {
  if (body && typeof body === 'object' && 'success' in body && 'data' in body) {
    const inner = (body as { data: unknown }).data;
    if (inner != null) return inner as T;
  }
  return body as T;
}

/**
 * 闲鱼商品搜索（指南针）。后端要求 account_id（cookie 的 pk），
 * 响应体为 {success, message, data: {items, total}}。
 */
export async function compassSearch(
  keyword: string,
  page: number,
  account_id: number,
): Promise<{ data: SearchResult[]; total: number }> {
  const client = await getApiClient();
  // 30s 超时：goofish 搜索经账号 cookie 抓取，账号离线时后端会阻塞，避免 UI 无限转圈
  const { data } = (await withTimeout(
    (client.POST as any)('/api/v1/compass/goofish/search', {
      body: { keyword, page, account_id },
    }),
    30000,
    '搜索超时，请确认账号在线后重试',
  )) as { data?: unknown; error?: unknown };
  const body = unwrapData<{ items?: SearchResult[]; total?: number } | SearchResult[]>(data);
  if (Array.isArray(body)) return { data: body, total: body.length };
  const items = body?.items ?? [];
  return { data: items, total: body?.total ?? items.length };
}

export async function searchItems(keyword: string): Promise<SearchResult[]> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)('/api/v1/search/items', {
    body: { keyword },
  })) as { data?: SearchResult[]; error?: unknown };
  return data ?? [];
}

// 保留 extractError 引用：与其它 wrapper 的导入风格保持一致
void extractError;
