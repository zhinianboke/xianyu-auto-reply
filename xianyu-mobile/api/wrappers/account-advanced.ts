import { getApiClient, extractError } from './client';
import { ApiError } from './errors';

// ---------------------------------------------------------------------------
// 账号高级配置（8 项）：代理 / 消息等待时间 / 回复延迟 / 人脸验证截图 /
// 确认收货消息 / 自动评价 / 禁止发货规则 / 退款订单注销
// 路径与字段对齐 web src/api/accounts.ts、src/api/autoRate.ts
// ---------------------------------------------------------------------------

/** 后端统一响应为 { success, message, data }，抽出内部 data；未包裹则原样返回 */
function unwrapEnvelope<T>(body: unknown): T | null {
  if (body && typeof body === 'object') {
    const obj = body as Record<string, unknown>;
    if ('success' in obj && obj.data != null) return obj.data as T;
  }
  return (body as T) ?? null;
}

/** 取 { success, message? } 状态字段；data 缺失时 success 默认 true */
function readStatus(body: unknown): { success: boolean; message?: string } {
  if (body && typeof body === 'object') {
    const obj = body as Record<string, unknown>;
    return {
      success: typeof obj.success === 'boolean' ? obj.success : true,
      message: typeof obj.message === 'string' ? obj.message : undefined,
    };
  }
  return { success: true };
}

// ==================== 1. 代理设置 ====================
// GET/PUT /api/v1/proxy/{accountId}

export type ProxyType = 'none' | 'http' | 'https' | 'socks5';

export interface ProxyConfig {
  proxy_type: ProxyType;
  proxy_host?: string;
  proxy_port?: number;
  proxy_user?: string;
  proxy_pass?: string;
}

export async function getProxyConfig(
  accountId: string,
): Promise<ProxyConfig> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    `/api/v1/proxy/${encodeURIComponent(accountId)}`,
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  return (
    unwrapEnvelope<ProxyConfig>(data) ?? {
      proxy_type: 'none',
      proxy_host: '',
      proxy_port: undefined,
      proxy_user: '',
      proxy_pass: '',
    }
  );
}

export async function updateProxyConfig(
  accountId: string,
  config: ProxyConfig,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `/api/v1/proxy/${encodeURIComponent(accountId)}`,
    { body: config },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  return readStatus(data);
}

// ==================== 2. 消息等待时间 ====================
// PUT /api/v1/cookies/{id}/message-expire-time  body: { message_expire_time }
// 初始值取自账号详情 AccountDetail.message_expire_time（默认 3600）

export async function updateMessageExpireTime(
  accountId: string,
  seconds: number,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `/api/v1/cookies/${encodeURIComponent(accountId)}/message-expire-time`,
    { body: { message_expire_time: seconds } },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  return readStatus(data);
}

// ==================== 3. 回复延迟 ====================
// PUT /api/v1/cookies/{id}/reply-delay  body: { reply_delay_seconds }
// 初始值取自账号详情 AccountDetail.reply_delay_seconds（默认 0）

export async function updateReplyDelay(
  accountId: string,
  seconds: number,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `/api/v1/cookies/${encodeURIComponent(accountId)}/reply-delay`,
    { body: { reply_delay_seconds: seconds } },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  return readStatus(data);
}

// ==================== 4. 人脸验证截图管理 ====================
// GET/DELETE /api/v1/face-verification/screenshot/{accountId}

export interface FaceVerificationScreenshot {
  filename: string;
  account_id: string;
  path: string;
  size: number;
  created_time: number;
  created_time_str: string;
}

/** 获取人脸验证截图；不存在时返回 null */
export async function getFaceVerificationScreenshot(
  accountId: string,
): Promise<FaceVerificationScreenshot | null> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    `/api/v1/face-verification/screenshot/${encodeURIComponent(accountId)}`,
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const inner = unwrapEnvelope<{ screenshot?: FaceVerificationScreenshot }>(data);
  return inner?.screenshot ?? null;
}

/** 删除人脸验证截图 */
export async function deleteFaceVerificationScreenshot(
  accountId: string,
): Promise<{ success: boolean; message?: string; deleted_count?: number }> {
  const client = await getApiClient();
  const { data, error } = (await (client.DELETE as any)(
    `/api/v1/face-verification/screenshot/${encodeURIComponent(accountId)}`,
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const status = readStatus(data);
  const inner = unwrapEnvelope<{ deleted_count?: number }>(data);
  return { ...status, deleted_count: inner?.deleted_count };
}

// ==================== 5. 确认收货消息 ====================
// GET/PUT /api/v1/confirm-receipt-messages/{accountId}
// POST  /api/v1/confirm-receipt-messages/{accountId}/upload-image (multipart, field image)

export interface ConfirmReceiptConfig {
  enabled: boolean;
  message_content: string;
  message_image: string;
}

export async function getConfirmReceiptMessage(
  accountId: string,
): Promise<ConfirmReceiptConfig> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    `/api/v1/confirm-receipt-messages/${encodeURIComponent(accountId)}`,
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const cfg = unwrapEnvelope<ConfirmReceiptConfig>(data);
  return cfg ?? { enabled: false, message_content: '', message_image: '' };
}

export async function updateConfirmReceiptMessage(
  accountId: string,
  config: ConfirmReceiptConfig,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `/api/v1/confirm-receipt-messages/${encodeURIComponent(accountId)}`,
    { body: config },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  return readStatus(data);
}

/** 上传确认收货消息图片（multipart/form-data，字段名 image），返回可保存的图片地址 */
export async function uploadConfirmReceiptImage(
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
    name: `receipt.${ext}`,
    type: mimeType,
  } as any);
  const { data, error } = (await (client.POST as any)(
    `/api/v1/confirm-receipt-messages/${encodeURIComponent(accountId)}/upload-image`,
    { body: formData },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const inner = unwrapEnvelope<{ image_url?: string; message?: string }>(data);
  const url = inner?.image_url;
  if (!url) throw new ApiError(inner?.message || '图片上传失败', 0);
  return url;
}

// ==================== 6. 自动评价 ====================
// GET/PUT /api/v1/auto-rate/{accountId}

export interface AutoRateConfig {
  enabled: boolean;
  rate_type: 'text' | 'api';
  text_content: string;
  api_url: string;
}

export async function getAutoRateConfig(
  accountId: string,
): Promise<AutoRateConfig> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    `/api/v1/auto-rate/${encodeURIComponent(accountId)}`,
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const cfg = unwrapEnvelope<AutoRateConfig>(data);
  return cfg ?? { enabled: false, rate_type: 'text', text_content: '', api_url: '' };
}

export async function updateAutoRateConfig(
  accountId: string,
  config: AutoRateConfig,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `/api/v1/auto-rate/${encodeURIComponent(accountId)}`,
    { body: config },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  return readStatus(data);
}

// ==================== 7. 禁止发货规则 ====================
// GET/PUT /api/v1/cookies/{id}/delivery-block-rules

export interface DeliveryBlockRuleItem {
  rule_code: string;
  rule_name: string;
  rule_description: string;
  enabled: boolean;
  priority: number;
  block_reason: string;
  auto_close_order: boolean;
  only_card_after_close: boolean;
  excluded_item_ids: string[];
  config: Record<string, unknown>;
  default_config: Record<string, unknown>;
}

/** 保存时每条规则的提交结构 */
export interface DeliveryBlockRulePayload {
  rule_code: string;
  enabled: boolean;
  priority: number;
  block_reason: string | null;
  auto_close_order: boolean;
  only_card_after_close: boolean;
  excluded_item_ids: string[];
  config: Record<string, unknown> | null;
}

export async function getDeliveryBlockRules(
  accountId: string,
): Promise<DeliveryBlockRuleItem[]> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    `/api/v1/cookies/${encodeURIComponent(accountId)}/delivery-block-rules`,
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  return unwrapEnvelope<DeliveryBlockRuleItem[]>(data) ?? [];
}

export async function updateDeliveryBlockRules(
  accountId: string,
  rules: DeliveryBlockRulePayload[],
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `/api/v1/cookies/${encodeURIComponent(accountId)}/delivery-block-rules`,
    { body: { rules } },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  return readStatus(data);
}

// ==================== 8. 退款订单注销 ====================
// GET/PUT /api/v1/refund-cancel/{accountId}

export interface RefundCancelConfig {
  enabled: boolean;
  url?: string | null;
  timeout?: number;
}

export async function getRefundCancelConfig(
  accountId: string,
): Promise<RefundCancelConfig> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    `/api/v1/refund-cancel/${encodeURIComponent(accountId)}`,
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  return (
    unwrapEnvelope<RefundCancelConfig>(data) ?? {
      enabled: false,
      url: '',
      timeout: 60,
    }
  );
}

export async function updateRefundCancelConfig(
  accountId: string,
  config: RefundCancelConfig,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `/api/v1/refund-cancel/${encodeURIComponent(accountId)}`,
    { body: config },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  return readStatus(data);
}
