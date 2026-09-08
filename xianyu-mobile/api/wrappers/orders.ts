import { getApiClient, extractError } from './client';

/** 客户订单（会话对方买家视角的订单摘要） */
export interface CustomerOrder {
  order_no: string;
  item_id: string;
  item_title: string;
  buyer_id: string;
  quantity: number;
  amount: string;
  status: string;
  delivery_method: string;
  delivery_fail_reason: string;
  card_only_delivered: boolean;
  placed_at: string;
}

/** 订单详情（含规格与收货信息） */
export interface OrderDetail {
  order_no: string;
  item_title: string;
  amount: string;
  quantity: number;
  status: string;
  spec_name?: string;
  spec_value?: string;
  receiver_name?: string;
  receiver_phone?: string;
  receiver_address?: string;
}

/**
 * 获取客户订单列表
 *
 * 后端响应可能为裸数组，也可能包一层 `{ data: [...] }`，
 * 两种形态都兼容（与 chat.ts 中 accounts 的处理方式保持一致）。
 */
export async function getCustomerOrders(
  accountId: string,
  buyerId: string,
): Promise<CustomerOrder[]> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `/api/v1/chat-new/customer-orders/${accountId}/${buyerId}`,
  )) as {
    data?: CustomerOrder[] | { data?: CustomerOrder[]; success?: boolean };
    error?: unknown;
  };
  if (!data) return [];
  if (Array.isArray(data)) return data;
  return (data as { data?: CustomerOrder[] }).data ?? [];
}

/**
 * 获取订单详情
 *
 * 订单接口响应包一层 `{ success, data }`，这里同时兼容裸对象。
 */
export async function getOrderDetail(orderNo: string): Promise<OrderDetail> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `/api/v1/orders/${orderNo}`,
  )) as {
    data?: OrderDetail | { success?: boolean; data?: OrderDetail; message?: string };
    error?: unknown;
  };
  if (!data) throw new Error('获取订单详情失败');
  // 裸对象：直接含 order_no
  if (typeof data === 'object' && 'order_no' in data) {
    return data as OrderDetail;
  }
  // 包一层：{ success, data }
  const wrapped = data as { data?: OrderDetail; message?: string };
  if (wrapped.data) return wrapped.data;
  throw new Error(wrapped.message || '获取订单详情失败');
}

/**
 * 同步闲鱼订单到数据库
 *
 * 注意：该接口可能耗时较长，这里通过 AbortController 给到 10 分钟超时，
 * 与原前端 600s 超时一致。任务描述中请求体写作 `{ account_id }`，
 * 但仓库 OpenAPI 生成的 schema（FetchXianyuOrdersRequest）字段为 `cookie_id`，
 * 原生产前端也发送 `cookie_id`，故此处按 schema 发送 `cookie_id`。
 */
export async function fetchXianyuOrders(accountId: string): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)('/api/v1/orders/fetch-xianyu', {
    body: { cookie_id: accountId },
  });
}

/** 取消订单（待付款/待发货状态可取消） */
export async function cancelOrder(orderNo: string): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)('/api/v1/orders/cancel', {
    body: { order_no: orderNo },
  });
}

/** 无物流发货：仅在闲鱼确认发货，不发卡券/聊天内容 */
export async function noLogisticsDelivery(orderNo: string): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)('/api/v1/orders/no-logistics-delivery', {
    body: { order_no: orderNo },
  });
}

/** 手动发卡发货：通过 WebSocket 把卡券发给买家 */
export async function manualDelivery(orderNo: string): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)('/api/v1/orders/manual-delivery', {
    body: { order_no: orderNo },
  });
}
