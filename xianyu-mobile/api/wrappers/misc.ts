import { getApiClient } from './client';

/** 反馈类型：需求/BUG/其他（对齐 web + 后端 query 参数 feedback_type） */
export type FeedbackType = 'FEATURE' | 'BUG' | 'OTHER';

/** 反馈对话中的一条消息（用户或管理员） */
export interface FeedbackMessage {
  id: number;
  is_admin: boolean;
  content: string;
  created_at: string | null;
}

/**
 * 反馈（列表项）。字段对齐 web `api/feedback` 与后端 `/api/v1/feedbacks` 响应。
 * 旧版用 `resolved`/`reply`，后端实际为 `is_resolved`/`admin_reply` + 多轮 `messages`。
 */
export interface Feedback {
  id: number;
  user_id?: number;
  cookie_id?: string | null;
  title: string;
  content: string;
  feedback_type: FeedbackType;
  images: string[];
  is_resolved: boolean;
  resolved_at?: string | null;
  admin_reply?: string | null;
  /** 多轮对话消息数（>1 表示有后续回复） */
  message_count?: number;
  created_at: string;
}

/** 反馈详情：列表项基础上携带完整对话消息 */
export interface FeedbackDetail extends Omit<Feedback, 'admin_reply'> {
  messages: FeedbackMessage[];
}

/** 反馈统计 */
export interface FeedbackStats {
  total: number;
  resolved: number;
  pending: number;
}

/** 从可能被包一层 `{ data }` 的响应中取出实际数据 */
function unwrap<T>(data: unknown): T | null {
  if (data == null) return null;
  if (Array.isArray(data)) return data as T;
  if (typeof data === 'object' && 'data' in (data as Record<string, unknown>)) {
    const inner = (data as { data?: unknown }).data;
    if (inner != null) return inner as T;
  }
  return data as T;
}

/** 安全取字符串：仅当为字符串时返回，否则空串（用于解析后端可能为任意类型的字段） */
function toStr(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

// ---------------------------------------------------------------------------
// 反馈
// ---------------------------------------------------------------------------

/** 反馈列表响应内层结构（ApiResponse.data） */
interface FeedbackListResponse {
  items: Feedback[];
  total: number;
  page: number;
  page_size: number;
}

/**
 * 获取反馈列表。后端 `/api/v1/feedbacks` 返回
 * `ApiResponse<{ items, total, page, page_size }>`，这里剥两层取出 items。
 */
export async function getFeedbacks(): Promise<Feedback[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/feedbacks')) as {
    data?: unknown;
    error?: unknown;
  };
  const result = unwrap<FeedbackListResponse | Feedback[]>(data);
  if (Array.isArray(result)) return result;
  if (result && Array.isArray((result as FeedbackListResponse).items)) {
    return (result as FeedbackListResponse).items;
  }
  return [];
}

/** 获取反馈统计 */
export async function getFeedbackStats(): Promise<FeedbackStats> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/feedbacks/stats')) as {
    data?: FeedbackStats | { data?: FeedbackStats };
    error?: unknown;
  };
  const result = unwrap<FeedbackStats>(data);
  return result ?? { total: 0, resolved: 0, pending: 0 };
}

/** 获取反馈详情（含多轮对话消息） */
export async function getFeedbackDetail(id: number): Promise<FeedbackDetail | null> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(`/api/v1/feedbacks/${id}`)) as {
    data?: unknown;
    error?: unknown;
  };
  return unwrap<FeedbackDetail>(data);
}

/**
 * 创建反馈。后端要求全部以 query 参数提交：title/content/feedback_type，
 * images 为 JSON 字符串数组（与 web 一致）。无 request body。
 */
export async function createFeedback(opts: {
  title: string;
  content: string;
  feedback_type: FeedbackType;
  cookie_id?: string;
  images?: string[];
}): Promise<void> {
  const client = await getApiClient();
  const query: Record<string, string> = {
    title: opts.title,
    content: opts.content,
    feedback_type: opts.feedback_type,
  };
  if (opts.cookie_id) query.cookie_id = opts.cookie_id;
  if (opts.images && opts.images.length > 0) {
    query.images = JSON.stringify(opts.images);
  }
  await (client.POST as any)('/api/v1/feedbacks', { params: { query } });
}

/** 删除反馈 */
export async function deleteFeedback(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/feedbacks/${id}`);
}

/**
 * 回复反馈（用户和管理员均可多轮回复）。后端要求 content 作为 query 参数提交，
 * 非 body（旧实现误用 body `{ reply }` 会被后端忽略）。每次回复追加一条消息。
 */
export async function replyFeedback(id: number, content: string): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)(`/api/v1/feedbacks/${id}/reply`, {
    params: { query: { content } },
  });
}

/** 标记反馈已解决（管理员） */
export async function resolveFeedback(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/feedbacks/${id}/resolve`);
}

/** 标记反馈未解决（管理员） */
export async function unresolveFeedback(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/feedbacks/${id}/unresolve`);
}

/**
 * 上传反馈图片（multipart/form-data，字段名 image）。
 * 复用 chat.ts / products.ts 的 RN FormData 文件上传模式：openapi-fetch 识别
 * FormData 后交由 fetch 自动设置 boundary，勿手动指定 Content-Type。
 * 后端返回 `ApiResponse<{ image_url }>`（兼容 image_url 顶层或再包一层 data）。
 * @param uri 本地图片 uri（来自 expo-image-picker）
 * @returns 上传后的图片可访问 URL
 */
export async function uploadFeedbackImage(uri: string): Promise<string> {
  const client = await getApiClient();
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
  const formData = new FormData();
  // RN FormData 文件字段需要 { uri, name, type } 结构
  formData.append('image', { uri, name: `image.${ext}`, type: mimeType } as any);

  const { data } = (await (client.POST as any)('/api/v1/upload/upload-image', {
    body: formData,
  })) as { data?: unknown; error?: unknown };

  const obj = (unwrap<unknown>(data) ?? {}) as Record<string, unknown>;
  const innerData = obj.data && typeof obj.data === 'object' ? (obj.data as Record<string, unknown>) : null;
  const url = toStr(obj.image_url) || (innerData ? toStr(innerData.image_url) : '');
  if (!url) {
    throw new Error(toStr(obj.message) || '图片上传失败');
  }
  return url;
}

// ---------------------------------------------------------------------------
// 广告相关 API 已迁移至 ./advertisements（含图片上传 / 编辑 / 付款等完整流程）。
// 本文件仅保留用户反馈相关接口。

