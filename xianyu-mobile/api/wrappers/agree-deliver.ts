import { getApiClient, extractError } from './client';

// ---------------------------------------------------------------------------
// 同意后发货配置（管理员/卖家为每个闲鱼账号配置）
// 后端路由前缀: /api/v1/agree-deliver
// ---------------------------------------------------------------------------

export interface AgreeDeliverConfig {
  enabled: boolean;
  notify_message?: string;
  pickup_url?: string;
}

export interface PickupUrlSuggestion {
  pickup_url: string;
  warning?: string;
  env_name?: string;
  example_url?: string;
}

/** 统一解包 { success, data } 包裹格式 */
function unwrap<T>(data: unknown): T | null {
  if (data && typeof data === 'object') {
    const obj = data as Record<string, unknown>;
    if ('data' in obj && obj.data != null) return obj.data as T;
    if ('success' in obj && obj.success === false) return null;
  }
  return (data as T) ?? null;
}

/** 获取账号的同意后发货配置 */
export async function getAgreeDeliverConfig(
  accountId: string,
): Promise<AgreeDeliverConfig> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    `/api/v1/agree-deliver/${encodeURIComponent(accountId)}`,
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const cfg = unwrap<AgreeDeliverConfig>(data);
  return cfg ?? { enabled: false, notify_message: '', pickup_url: '' };
}

/** 更新账号的同意后发货配置（enabled=true 时 pickup_url 必填） */
export async function updateAgreeDeliverConfig(
  accountId: string,
  config: AgreeDeliverConfig,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `/api/v1/agree-deliver/${encodeURIComponent(accountId)}`,
    { body: config },
  )) as { data?: { success?: boolean; message?: string }; error?: unknown };
  if (error) throw await extractError(error);
  return { success: data?.success ?? true, message: data?.message };
}

/** 获取推荐的提货页地址（用于配置填写提示） */
export async function getPickupUrlSuggestion(): Promise<PickupUrlSuggestion | null> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/agree-deliver/pickup-url/suggestion',
  )) as { data?: unknown; error?: unknown };
  return unwrap<PickupUrlSuggestion>(data);
}

// ---------------------------------------------------------------------------
// 买家提货页（公开接口，无需登录）
// 后端路由前缀: /api/v1/agree-pickup
// 注意：后端用原生 fetch 实现、一律 HTTP 200，业务结果看 success 字段
// ---------------------------------------------------------------------------

/** 买家提货页订单信息 */
export interface PickupOrder {
  order_no: string;
  amount: string;
  quantity: number;
  spec_name?: string;
  spec_value?: string;
  item_id: string;
  item_title: string;
  item_url?: string;
  already_agreed: boolean;
  /** 卡券发货内容（仅已同意后非空） */
  content?: string;
}

/** 查询买家提货订单信息（orderNo 和 orderId 必须同时匹配） */
export async function getPickupOrder(
  orderNo: string,
  orderId: string,
): Promise<PickupOrder | null> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/agree-pickup/order', {
    params: { query: { orderNo, orderId } },
  })) as { data?: unknown; error?: unknown };
  const result = unwrap<{ success?: boolean; data?: PickupOrder }>(data);
  if (result && typeof result === 'object' && 'success' in result) {
    if (result.success === false) return null;
    return (result as { data?: PickupOrder }).data ?? null;
  }
  return (result as PickupOrder) ?? null;
}

/** 买家确认同意提货（幂等，返回卡券内容） */
export async function agreePickup(
  orderNo: string,
  orderId: string,
): Promise<{ order_no: string; content: string; already_agreed?: boolean }> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)('/api/v1/agree-pickup/agree', {
    body: { order_no: orderNo, order_id: orderId },
  })) as {
    data?: { success?: boolean; data?: { order_no: string; content: string; already_agreed?: boolean }; message?: string };
    error?: unknown;
  };
  if (error) throw await extractError(error);
  const body = data as Record<string, unknown> | undefined;
  if (body && body.success === false) {
    throw new Error(String(body.message || '操作失败'));
  }
  const result = (body?.data ?? body) as {
    order_no: string;
    content: string;
    already_agreed?: boolean;
  };
  return result;
}
