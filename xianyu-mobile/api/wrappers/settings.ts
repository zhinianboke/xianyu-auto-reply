import { getApiClient, extractError } from './client';
import { getServerUrl } from '@/lib/config';

/** 资金流水记录 */
export interface FundFlow {
  id: number;
  amount: string;
  type: string;
  description: string;
  created_at: string;
}

/** 从可能被包一层 `{ data }` 的响应中取出实际数据 */
function unwrap<T>(data: unknown): T | null {
  if (data == null) return null;
  if (typeof data === 'object' && 'data' in (data as Record<string, unknown>)) {
    const inner = (data as { data?: unknown }).data;
    if (inner != null) return inner as T;
  }
  return data as T;
}

/**
 * 获取系统设置
 *
 * 后端返回 `Record<string, string>`，可能裸返回也可能包一层 `{ data }`，两种都兼容。
 */
export async function getSystemSettings(): Promise<Record<string, string>> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/system-settings')) as {
    data?: Record<string, string> | { data?: Record<string, string> };
    error?: unknown;
  };
  const result = unwrap<Record<string, string>>(data);
  return result ?? {};
}

/**
 * 更新单个系统设置项
 *
 * 失败时 client 拦截器会抛出 ApiError，此处直接放行。
 */
export async function updateSystemSetting(
  key: string,
  value: string,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/system-settings/${encodeURIComponent(key)}`, {
    body: { value },
  });
}

/**
 * 修改密码
 *
 * 成功返回 `{ success: true }`；若后端以 200 + `{ success: false, message }` 表示逻辑失败，
 * 则原样透传该结果。非 2xx 响应由拦截器抛出，调用方需 try/catch。
 */
export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    '/api/v1/users/change-password',
    {
      body: {
        current_password: currentPassword,
        new_password: newPassword,
      },
    },
  )) as {
    data?: { success?: boolean; message?: string } | { data?: { success?: boolean; message?: string } };
    error?: unknown;
  };
  const result = unwrap<{ success?: boolean; message?: string }>(data);
  if (!result) return { success: true };
  return {
    success: result.success ?? true,
    message: result.message,
  };
}

/**
 * 充值
 *
 * 返回订单号与支付链接（若有）。
 */
export async function recharge(
  amount: string,
): Promise<{ order_no: string; pay_url?: string }> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)('/api/v1/payment/recharge', {
    body: { amount },
  })) as {
    data?: { order_no: string; pay_url?: string } | { data?: { order_no: string; pay_url?: string } };
    error?: unknown;
  };
  const result = unwrap<{ order_no: string; pay_url?: string }>(data);
  if (!result || !result.order_no) throw new Error('获取充值订单失败');
  return { order_no: result.order_no, pay_url: result.pay_url };
}

/**
 * 提现
 *
 * 与 changePassword 类似：200 + `{ success, message }` 透传，非 2xx 抛出。
 */
export async function withdraw(
  amount: string,
  paymentMethod: string,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)('/api/v1/payment/withdraw', {
    body: { amount, payment_method: paymentMethod },
  })) as {
    data?: { success?: boolean; message?: string } | { data?: { success?: boolean; message?: string } };
    error?: unknown;
  };
  const result = unwrap<{ success?: boolean; message?: string }>(data);
  if (!result) return { success: true };
  return {
    success: result.success ?? true,
    message: result.message,
  };
}

/**
 * 获取资金流水
 *
 * 后端响应可能为裸数组，也可能包一层 `{ data: [...] }`，两种形态都兼容
 * （与 orders.ts 中 customer-orders 的处理方式保持一致）。
 */
export async function getFundFlows(): Promise<FundFlow[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/distribution/fund-flows',
  )) as {
    data?: FundFlow[] | { data?: FundFlow[] };
    error?: unknown;
  };
  if (!data) return [];
  if (Array.isArray(data)) return data;
  return (data as { data?: FundFlow[] }).data ?? [];
}

// ========== 用户资料 / 账户续期 / 结算记录 ==========

/** 当前登录用户资料（含到期日），对应 web getCurrentUserProfile */
export interface UserProfile {
  id: number;
  username: string;
  email?: string;
  phone?: string;
  role?: string;
  status?: string;
  account_limit?: number | null;
  last_login_at?: string | null;
  expire_at?: string | null;
}

/**
 * 获取当前登录用户资料（含到期日）。
 * GET /api/v1/users/me —— 后端裸返回 profile 对象，也可能二次包一层 { data }，unwrap 兼容两者。
 */
export async function getCurrentUserProfile(): Promise<UserProfile> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/users/me')) as {
    data?: unknown;
    error?: unknown;
  };
  const profile = unwrap<UserProfile>(data);
  if (!profile || typeof profile !== 'object') {
    throw new Error('获取用户资料失败');
  }
  return profile;
}

/** 账户续期结果（扣减前/后余额、新到期日），对应 web RenewMembershipResult */
export interface RenewAccountResult {
  months: number;
  unit_price: string;
  total: string;
  balance_before: string;
  balance_after: string;
  expire_at: string | null;
}

/**
 * 账户续期：按系统设置的续期单价扣减余额并延长到期日。
 * POST /api/v1/users/renew { months }，响应为 ApiResponse 信封 { success, message, data }。
 * 余额不足等逻辑失败时后端返回 200 + { success:false, message }，需透传 success/message。
 */
export async function renewAccount(
  months: number,
): Promise<{
  success: boolean;
  message?: string;
  data?: RenewAccountResult;
}> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)('/api/v1/users/renew', {
    body: { months },
  })) as { data?: unknown; error?: unknown };
  const env = unwrapEnvelope<RenewAccountResult>(data);
  return { success: env.success, message: env.message, data: env.data };
}

/** 结算记录（提现申请流水），对应 web SettlementRecord */
export interface SettlementRecord {
  id: number;
  alipay_id?: string;
  payment_type?: 'alipay' | 'wechat';
  payment_qrcode?: string;
  amount: string;
  status: 'pending_review' | 'approved' | 'rejected' | 'paid';
  remark?: string;
  reject_reason?: string;
  created_at?: string;
  updated_at?: string;
}

/** 结算记录分页数据 */
export interface SettlementRecordListData {
  list: SettlementRecord[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

/**
 * 查询结算记录（分页）。
 * GET /api/v1/payment/settlement-records?page=&page_size=，响应为 ApiResponse 信封 { success, message, data }。
 */
export async function getSettlementRecords(
  page: number = 1,
  pageSize: number = 20,
): Promise<{
  success: boolean;
  message?: string;
  data?: SettlementRecordListData;
}> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/payment/settlement-records',
    { params: { query: { page, page_size: pageSize } } },
  )) as { data?: unknown; error?: unknown };
  const env = unwrapEnvelope<SettlementRecordListData>(data);
  return { success: env.success, message: env.message, data: env.data };
}

// ========== 服务管理（重启） ==========

const SYSTEM_CONTROL_PREFIX = '/api/v1/system-control';

export type ServiceKey = 'backend-web' | 'websocket' | 'scheduler';

export interface ServiceStatusItem {
  key: ServiceKey;
  label: string;
  port: number;
  online: boolean;
}

/**
 * 从 ApiResponse 信封 `{ success, message, data }` 中取出内容；
 * 裸对象（无 success 字段）视为成功并整体作为 data 返回。
 */
function unwrapEnvelope<T>(raw: unknown): {
  success: boolean;
  message?: string;
  data?: T;
} {
  if (raw == null) return { success: true };
  if (typeof raw !== 'object') return { success: true, data: raw as T };
  const obj = raw as Record<string, unknown>;
  if ('success' in obj) {
    return {
      success: obj.success === true || obj.success === 'true',
      message: typeof obj.message === 'string' ? obj.message : undefined,
      data: obj.data as T | undefined,
    };
  }
  // `{ data }` 嵌套（部分端点二次包裹）
  if ('data' in obj) {
    return { success: true, data: obj.data as T };
  }
  return { success: true, data: obj as unknown as T };
}

/** 从可能被信封/裸对象/二次嵌套的响应中定位 services 数组 */
function extractServices(raw: unknown): ServiceStatusItem[] {
  if (!raw || typeof raw !== 'object') return [];
  const candidates: unknown[] = [
    raw,
    (raw as { data?: unknown }).data,
    (raw as { data?: { data?: unknown } })?.data?.data,
  ];
  for (const c of candidates) {
    if (c && typeof c === 'object' && Array.isArray((c as { services?: unknown }).services)) {
      return (c as { services: ServiceStatusItem[] }).services;
    }
  }
  return [];
}

/** 查询三服务（消息/后端/定时任务）在线状态 */
export async function getServicesStatus(): Promise<{
  success: boolean;
  services: ServiceStatusItem[];
  message?: string;
}> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(`${SYSTEM_CONTROL_PREFIX}/status`)) as {
    data?: unknown;
    error?: unknown;
  };
  const services = extractServices(data);
  if (!services.length) {
    return { success: false, services: [], message: '查询服务状态失败' };
  }
  return { success: true, services };
}

/** 重启指定服务（先杀端口进程再启动，后端适配运行环境） */
export async function restartService(
  key: ServiceKey,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    `${SYSTEM_CONTROL_PREFIX}/restart/${key}`,
  )) as { data?: unknown; error?: unknown };
  const env = unwrapEnvelope<{ success?: boolean; message?: string }>(data);
  return { success: env.success ?? true, message: env.message };
}

// ========== 测试邮件 / 测试远程登录接口 ==========

/** 发送测试邮件（query 参数 email） */
export async function testEmailSend(
  email: string,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    `/api/v1/system-settings/test-email?email=${encodeURIComponent(email)}`,
  )) as { data?: unknown; error?: unknown };
  const env = unwrapEnvelope<{ success?: boolean; message?: string }>(data);
  return { success: env.success ?? true, message: env.message };
}

/** 测试密码登录远程接口（阿里滑块获取 x5sec）连通性与秘钥有效性 */
export async function testPasswordLoginRemote(payload: {
  remote_url: string;
  remote_secret_key: string;
}): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    '/api/v1/system-settings/test-password-login-remote',
    { body: payload },
  )) as { data?: unknown; error?: unknown };
  const env = unwrapEnvelope<{ success?: boolean; message?: string }>(data);
  return { success: env.success ?? true, message: env.message };
}

/**
 * 健康检查：后端服务重启后轮询直到恢复。
 * 后端重启自身时本客户端会短暂不可用，用无鉴权的公开 ping 端点探测。
 */
export async function pingHealth(): Promise<boolean> {
  const baseUrl = await getServerUrl();
  if (!baseUrl) return false;
  try {
    const res = await fetch(`${baseUrl.replace(/\/$/, '')}/api/v1/health/ping`, {
      method: 'GET',
    });
    return res.ok;
  } catch {
    return false;
  }
}

// ========== 菜单可见性 ==========

const MENU_HIDDEN_SETTING_KEY = 'navigation.hidden_menu_keys';

/** 解析隐藏菜单 key 列表：兼容数组 / JSON 字符串 / 逗号分隔字符串 */
export function parseHiddenMenuKeys(value: unknown): string[] {
  if (!value) return [];
  if (Array.isArray(value)) {
    return value.map((v) => String(v).trim()).filter(Boolean);
  }
  if (typeof value !== 'string') return [];
  const trimmed = value.trim();
  if (!trimmed) return [];
  try {
    const parsed = JSON.parse(trimmed);
    if (Array.isArray(parsed)) {
      return parsed.map((v) => String(v).trim()).filter(Boolean);
    }
  } catch {
    return trimmed.split(',').map((v) => v.trim()).filter(Boolean);
  }
  return [];
}

export function serializeHiddenMenuKeys(keys: string[]): string {
  return JSON.stringify(Array.from(new Set(keys.filter(Boolean))));
}

export function getHiddenMenuKeysFromSettings(
  settings: Record<string, string>,
): string[] {
  return parseHiddenMenuKeys(settings[MENU_HIDDEN_SETTING_KEY]);
}
