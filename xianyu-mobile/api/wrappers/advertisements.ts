/**
 * 广告管理 API 封装。
 *
 * 对应 web: src/api/advertisements.ts + AdApply/AdManage/AdPaymentModal。
 * 后端契约要点（来自 generated/types.ts，与 web 实现一致）：
 *  - 创建/修改广告走 query 参数（非 body）：title/ad_type/months 必填，
 *    content/link/image_url 选填。旧 misc.ts 误用 body 提交且缺少必填的 months，
 *    导致创建实际无法生效，这里修正为 query + months。
 *  - 列表响应为 ApiResponse { success, message, data: { items, total, page, page_size } }。
 *  - 上传图片：POST /api/v1/upload/upload-image，multipart 字段名 image，
 *    返回 { data: { image_url } }。
 *  - 付款：POST /api/v1/advertisements/{id}/pay → { order_no, qr_code, amount?, ad_id? }；
 *    轮询 POST /api/v1/advertisements/{id}/pay/notify?order_no= → { status }，
 *    status === 'approved' 表示付款完成（广告自动审核通过）。
 */
import { getApiClient } from './client';

/** 广告实体（与 web Advertisement 同构） */
export interface Advertisement {
  id: number;
  user_id?: number;
  title: string;
  content?: string | null;
  link?: string | null;
  expire_date?: string | null;
  image_url?: string | null;
  ad_type: 'carousel' | 'text';
  months?: number | null;
  total_amount?: string | null;
  /** unpaid=待付款 / pending=待审核 / approved=已通过 / rejected=已拒绝 */
  status: string;
  created_at?: string | null;
  updated_at?: string | null;
  /** 广告来源：local-本站，remote-官方远程 */
  source?: 'local' | 'remote';
}

/** 列表响应体 */
export interface AdListResponse {
  items: Advertisement[];
  total: number;
  page: number;
  page_size: number;
}

/** 各广告类型单月价格：{ carousel: '...', text: '...' } */
export type AdPrices = Record<string, string>;

/** 创建/修改广告入参（均映射到 query 参数） */
export interface AdMutationPayload {
  title: string;
  ad_type: string;
  /** 购买月数，正整数，后端据此计算到期日与费用 */
  months: number;
  content?: string | null;
  link?: string | null;
  image_url?: string | null;
}

/** 付款订单信息 */
export interface AdPaymentOrder {
  order_no: string;
  qr_code: string;
  amount?: string | null;
  ad_id?: number;
}

/** 付款状态查询结果 */
export interface AdPaymentStatus {
  status: string;
}

/** 从 ApiResponse { success, message, data } 中取出 data；兼容已脱壳对象。 */
function unwrapData<T>(raw: unknown): T | null {
  if (raw == null || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  if ('data' in obj && obj.data != null) return obj.data as T;
  return obj as unknown as T;
}

/** 顶层响应可能携带 message（HTTP 200 但逻辑失败时），取出作为兜底错误文案。 */
function topMessage(raw: unknown): string {
  if (raw && typeof raw === 'object' && 'message' in raw) {
    const m = (raw as Record<string, unknown>).message;
    if (typeof m === 'string') return m;
  }
  return '';
}

/** 从列表响应中提取广告数组，兼容 {data:{items}} / {items} / 顶层数组 三种形态。 */
function extractItems(raw: unknown): Advertisement[] {
  if (raw == null) return [];
  if (Array.isArray(raw)) return raw as Advertisement[];
  if (typeof raw !== 'object') return [];
  const obj = raw as Record<string, unknown>;
  const candidate = ('data' in obj && obj.data != null ? obj.data : raw) as unknown;
  if (Array.isArray(candidate)) return candidate as Advertisement[];
  if (candidate && typeof candidate === 'object' && 'items' in candidate) {
    const items = (candidate as Record<string, unknown>).items;
    if (Array.isArray(items)) return items as Advertisement[];
  }
  return [];
}

function str(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

// ---------------------------------------------------------------------------
// 列表
// ---------------------------------------------------------------------------

/** 获取当前用户的广告列表。 */
export async function getAdvertisements(): Promise<Advertisement[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/advertisements')) as {
    data?: unknown;
    error?: unknown;
  };
  return extractItems(data);
}

/**
 * 管理员获取广告审核列表。支持 status/ad_type 服务端筛选
 * （非管理员请用 getAdvertisements）。
 */
export async function getAdminAdvertisements(params?: {
  status?: string;
  ad_type?: string;
}): Promise<Advertisement[]> {
  const client = await getApiClient();
  const query: Record<string, string> = {};
  if (params?.status) query.status = params.status;
  if (params?.ad_type) query.ad_type = params.ad_type;
  const { data } = (await (client.GET as any)('/api/v1/advertisements/admin', {
    params: { query },
  })) as { data?: unknown; error?: unknown };
  return extractItems(data);
}

// ---------------------------------------------------------------------------
// 价格
// ---------------------------------------------------------------------------

/** 获取各广告类型单月价格。 */
export async function getAdPrices(): Promise<AdPrices> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/advertisements/prices')) as {
    data?: unknown;
    error?: unknown;
  };
  const inner = unwrapData<unknown>(data);
  return inner && typeof inner === 'object' ? (inner as AdPrices) : {};
}

// ---------------------------------------------------------------------------
// 创建 / 修改 / 删除
// ---------------------------------------------------------------------------

/** 新建广告申请（query 参数）。 */
export async function createAdvertisement(ad: AdMutationPayload): Promise<void> {
  const client = await getApiClient();
  const query: Record<string, string> = {
    title: ad.title,
    ad_type: ad.ad_type,
    months: String(ad.months),
  };
  if (ad.content) query.content = ad.content;
  if (ad.link) query.link = ad.link;
  if (ad.image_url) query.image_url = ad.image_url;
  await (client.POST as any)('/api/v1/advertisements', { params: { query } });
}

/** 修改我的广告（已复核的广告禁止修改；query 参数）。 */
export async function updateAdvertisement(
  id: number,
  ad: AdMutationPayload,
): Promise<void> {
  const client = await getApiClient();
  const query: Record<string, string> = {
    title: ad.title,
    ad_type: ad.ad_type,
    months: String(ad.months),
  };
  if (ad.content) query.content = ad.content;
  if (ad.link) query.link = ad.link;
  if (ad.image_url) query.image_url = ad.image_url;
  await (client.PUT as any)(`/api/v1/advertisements/${id}`, { params: { query } });
}

/** 删除我的广告。 */
export async function deleteAdvertisement(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/advertisements/${id}`);
}

// ---------------------------------------------------------------------------
// 管理员审核
// ---------------------------------------------------------------------------

/** 管理员审核通过。 */
export async function approveAdvertisement(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/advertisements/admin/${id}/approve`);
}

/** 管理员拒绝 / 取消复核。 */
export async function rejectAdvertisement(id: number): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/advertisements/admin/${id}/reject`);
}

// ---------------------------------------------------------------------------
// 图片上传
// ---------------------------------------------------------------------------

/**
 * 上传广告图片（multipart/form-data，字段名 image）。
 *
 * 复用项目 RN FormData 上传模式（见 products.ts uploadCardImage）：
 * openapi-fetch 识别 FormData 后交由 fetch 自动设置 boundary，
 * 切勿手动指定 Content-Type（会缺少 boundary 致后端解析失败）。
 * 后端返回 { success, data: { image_url } }（兼容无 data 包裹的 { image_url }）。
 *
 * @param uri 本地图片 uri（来自 expo-image-picker）
 * @returns 上传后的图片可访问 URL
 */
export async function uploadAdImage(uri: string): Promise<string> {
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

  const inner = unwrapData<unknown>(data);
  const obj = (inner && typeof inner === 'object' ? inner : {}) as Record<string, unknown>;
  const url = str(obj.image_url);
  if (!url) {
    throw new Error(topMessage(data) || str(obj.message) || '图片上传失败');
  }
  return url;
}

// ---------------------------------------------------------------------------
// 付款
// ---------------------------------------------------------------------------

/** 创建广告付款订单，返回支付宝二维码信息。 */
export async function createAdPayment(adId: number): Promise<AdPaymentOrder> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    `/api/v1/advertisements/${adId}/pay`,
  )) as { data?: unknown; error?: unknown };

  const inner = unwrapData<unknown>(data);
  const obj = (inner && typeof inner === 'object' ? inner : {}) as Record<string, unknown>;
  const order_no = str(obj.order_no);
  const qr_code = str(obj.qr_code);
  if (!order_no || !qr_code) {
    throw new Error(topMessage(data) || str(obj.message) || '创建付款订单失败');
  }
  return {
    order_no,
    qr_code,
    amount: typeof obj.amount === 'string' ? obj.amount : null,
    ad_id: typeof obj.ad_id === 'number' ? obj.ad_id : undefined,
  };
}

/**
 * 轮询广告付款状态。返回 { status }；
 * status === 'approved' 表示付款完成（广告已自动审核通过）。
 */
export async function checkAdPaymentStatus(
  adId: number,
  orderNo: string,
): Promise<AdPaymentStatus> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    `/api/v1/advertisements/${adId}/pay/notify`,
    { params: { query: { order_no: orderNo } } },
  )) as { data?: unknown; error?: unknown };
  const inner = unwrapData<unknown>(data);
  if (inner && typeof inner === 'object' && 'status' in inner) {
    return { status: str((inner as Record<string, unknown>).status) };
  }
  return { status: '' };
}
