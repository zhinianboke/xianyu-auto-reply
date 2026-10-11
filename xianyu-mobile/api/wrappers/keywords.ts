import { getApiClient, extractError } from './client';

export interface Keyword {
  keyword: string;
  reply: string;
  item_id?: string;
  type?: string;
  location_name?: string;
  location_longitude?: string;
  location_latitude?: string;
  location_title?: string;
  location_subtitle?: string;
}

export async function getKeywords(cookieId?: string): Promise<Keyword[]> {
  const client = await getApiClient();
  const path = cookieId
    ? `/api/v1/keywords-with-item-id/${cookieId}`
    : '/api/v1/keywords-with-item-id';
  const { data } = (await (client.GET as any)(path)) as {
    data?: Keyword[];
    error?: unknown;
  };
  return data ?? [];
}

/**
 * 保存关键词列表（后端先删光非图片关键词再整表插入）。
 * type 与 location_* 必须原样回传，否则 external_contact 关键词会被降级为 text 并丢定位。
 */
export async function saveKeywords(cookieId: string, keywords: Keyword[]): Promise<void> {
  const client = await getApiClient();
  const textKeywords = keywords
    .filter((k) => k.type !== 'image')
    .map((k) => ({
      keyword: k.keyword,
      reply: k.reply || '',
      item_id: k.item_id || '',
      type: k.type === 'external_contact' ? 'external_contact' : 'text',
      location_name: k.location_name || '',
      location_longitude: k.location_longitude || '',
      location_latitude: k.location_latitude || '',
      location_title: k.location_title || '',
      location_subtitle: k.location_subtitle || '',
    }));
  await (client.POST as any)(`/api/v1/keywords-with-item-id/${cookieId}`, {
    body: { keywords: textKeywords },
  });
}

/** 更新单个关键词；后端 account_id 必填，type 与 location_* 缺省会清空原配置 */
export async function updateKeyword(
  cookieId: string,
  oldKeyword: string,
  data: Partial<Keyword>,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/keywords-with-item-id/${cookieId}/${encodeURIComponent(oldKeyword)}`, {
    body: {
      account_id: cookieId,
      keyword: data.keyword ?? oldKeyword,
      reply: data.reply || '',
      item_id: data.item_id || '',
      type: data.type === 'external_contact' ? 'external_contact' : 'text',
      location_name: data.location_name || '',
      location_longitude: data.location_longitude || '',
      location_latitude: data.location_latitude || '',
      location_title: data.location_title || '',
      location_subtitle: data.location_subtitle || '',
    },
  });
}

export async function deleteKeyword(cookieId: string, keyword: string): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/keywords-with-item-id/${cookieId}/${encodeURIComponent(keyword)}`);
}
