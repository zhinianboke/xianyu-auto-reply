import { getApiClient, extractError } from './client';

export interface ChatAccount {
  account_id: string;
  display_name: string;
  remark: string;
  connected: boolean;
  status: string;
  owner?: string;
}

export interface Conversation {
  cid: string;
  rawCid: string;
  otherUserId: string;
  otherUserName: string;
  otherUserAvatar: string;
  itemTitle: string;
  lastMessageSummary: string;
  lastMessageTime: number;
  unreadCount: number;
}

export interface ChatMessage {
  messageId: string;
  senderId: string;
  senderName: string;
  isSelf: boolean;
  type: 'text' | 'image' | 'system' | 'card';
  text: string;
  images: string[];
  time: number;
  failed?: boolean;
  failReason?: string;
}

interface ConvResponse {
  conversations: Conversation[];
  hasMore: boolean;
  nextCursor: number | null;
}

interface MsgResponse {
  messages: ChatMessage[];
  hasMore: boolean;
  nextCursor: number | null;
}

export async function getChatAccounts(): Promise<ChatAccount[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/chat-new/accounts')) as {
    data?: ChatAccount[] | { data: ChatAccount[]; total: number };
    error?: unknown;
  };
  if (!data) return [];
  return Array.isArray(data) ? data : (data as { data: ChatAccount[] }).data;
}

export async function connectAccount(accountId: string): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)(`/api/v1/chat-new/connect/${accountId}`);
}

export async function disconnectAccount(accountId: string): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)(`/api/v1/chat-new/disconnect/${accountId}`);
}

export async function getConversations(
  accountId: string,
  cursor?: number | null,
): Promise<ConvResponse> {
  const client = await getApiClient();
  const params: Record<string, unknown> = { limit: 20 };
  if (cursor != null) params.cursor = cursor;
  const { data } = (await (client.GET as any)(
    `/api/v1/chat-new/conversations/${accountId}`,
    { params: { query: params } },
  )) as { data?: ConvResponse | { success?: boolean; data?: ConvResponse | null }; error?: unknown };
  if (!data) return { conversations: [], hasMore: false, nextCursor: null };
  // 后端返回 { success, data } 包裹格式，需提取内层 data
  if ('conversations' in data) return data as ConvResponse;
  const wrapped = (data as { success?: boolean; data?: ConvResponse | null }).data;
  return wrapped ?? { conversations: [], hasMore: false, nextCursor: null };
}

export async function getMessages(
  accountId: string,
  cid: string,
  cursor?: number | null,
): Promise<MsgResponse> {
  const client = await getApiClient();
  const params: Record<string, unknown> = { limit: 20 };
  if (cursor != null) params.cursor = cursor;
  const { data } = (await (client.GET as any)(
    `/api/v1/chat-new/messages/${accountId}/${cid}`,
    { params: { query: params } },
  )) as { data?: MsgResponse | { success?: boolean; data?: MsgResponse | null }; error?: unknown };
  if (!data) return { messages: [], hasMore: false, nextCursor: null };
  if ('messages' in data) return data as MsgResponse;
  const wrapped = (data as { success?: boolean; data?: MsgResponse | null }).data;
  return wrapped ?? { messages: [], hasMore: false, nextCursor: null };
}

export async function sendMessage(
  accountId: string,
  cid: string,
  toUserId: string,
  text: string,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)(
    `/api/v1/chat-new/send-message/${accountId}`,
    { body: { cid, toUserId, text } },
  )) as { data?: { success: boolean; message?: string }; error?: unknown };
  if (error) throw await extractError(error);
  return data ?? { success: false };
}

export async function recallMessage(
  accountId: string,
  messageId: string,
  messageTime: number,
): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)(`/api/v1/chat-new/recall-message/${accountId}`, {
    body: { messageId, messageTime },
  });
}

// ============ 快捷短语 ============

export interface QuickPhrase {
  id: number;
  title: string;
  content: string;
  sort_order: number;
}

export async function getQuickPhrases(): Promise<QuickPhrase[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/chat-new/quick-phrases')) as {
    data?: QuickPhrase[] | { data?: QuickPhrase[] };
    error?: unknown;
  };
  if (!data) return [];
  return Array.isArray(data) ? data : (data.data ?? []);
}

export async function createQuickPhrase(
  title: string,
  content: string,
): Promise<QuickPhrase> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)(
    '/api/v1/chat-new/quick-phrases',
    { body: { title, content, sort_order: 0 } },
  )) as { data?: QuickPhrase; error?: unknown };
  if (error) throw await extractError(error);
  if (!data) throw new Error('创建快捷短语失败');
  return data;
}

export async function updateQuickPhrase(
  id: number,
  title: string,
  content: string,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/chat-new/quick-phrases/${id}`, {
    body: { title, content, sort_order: 0 },
  });
}

export async function deleteQuickPhrase(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/chat-new/quick-phrases/${id}`);
}

// ============ 图片发送 ============

/**
 * 通过 multipart/form-data 发送图片消息。
 * React Native 的 FormData 使用 { uri, name, type } 描述本地文件，
 * 由 openapi-fetch 原生识别 FormData 交由 fetch 自动设置 boundary。
 */
export async function sendImageMessage(
  accountId: string,
  cid: string,
  toUserId: string,
  uri: string,
): Promise<void> {
  const client = await getApiClient();

  // 从 uri 推断扩展名与 MIME 类型
  const ext = (uri.split('.').pop() || 'jpg').toLowerCase().split('?')[0];
  const typeMap: Record<string, string> = {
    jpg: 'image/jpeg',
    jpeg: 'image/jpeg',
    png: 'image/png',
    gif: 'image/gif',
    webp: 'image/webp',
    heic: 'image/heic',
    bmp: 'image/bmp',
  };
  const mimeType = typeMap[ext] || 'image/jpeg';
  const filename = `image.${ext}`;

  const formData = new FormData();
  formData.append('cid', cid);
  formData.append('toUserId', toUserId);
  // RN FormData 文件字段需要 { uri, name, type } 结构
  formData.append('file', { uri, name: filename, type: mimeType } as any);

  await (client.POST as any)(`/api/v1/chat-new/send-image/${accountId}`, {
    body: formData,
  });
}
