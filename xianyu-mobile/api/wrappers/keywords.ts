import { getApiClient, extractError } from './client';

export interface Keyword {
  keyword: string;
  reply: string;
  item_id?: string;
  type?: string;
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

export async function saveKeywords(cookieId: string, keywords: Keyword[]): Promise<void> {
  const client = await getApiClient();
  const textKeywords = keywords
    .filter((k) => k.type !== 'image')
    .map((k) => ({ keyword: k.keyword, reply: k.reply || '', item_id: k.item_id || '' }));
  await (client.POST as any)(`/api/v1/keywords-with-item-id/${cookieId}`, {
    body: { keywords: textKeywords },
  });
}

export async function updateKeyword(
  cookieId: string,
  keyword: string,
  reply: string,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/keywords-with-item-id/${cookieId}/${encodeURIComponent(keyword)}`, {
    body: { reply },
  });
}

export async function deleteKeyword(cookieId: string, keyword: string): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/keywords-with-item-id/${cookieId}/${encodeURIComponent(keyword)}`);
}
