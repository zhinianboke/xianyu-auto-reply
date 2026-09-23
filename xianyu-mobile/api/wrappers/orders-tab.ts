import { getApiClient, extractError } from './client';

// ---------------------------------------------------------------------------
// 类型定义
//
// 注意：对外暴露的字段命名遵循本 Tab 的业务语义（text / api_mode / image_url），
// 但后端 OpenAPI 的真实 schema 字段为 rate_type / text_content / api_url 与
// message_content / message_image。下方各函数在调用前后做一次字段翻译，
// 以同时满足“接口简洁”与“真实可用”两个目标。
// ---------------------------------------------------------------------------

/** 订单列表项 */
export interface Order {
  /** 数据库主键（字符串化），删除接口 DELETE /orders/{id} 需要它 */
  id: string;
  order_no: string;
  item_title: string;
  buyer_id: string;
  buyer_nick?: string;
  amount: string;
  quantity: number;
  status: string;
  delivery_method: string;
  /** 只发卡券流程已处理，禁止重复耗卡（用于发货守卫） */
  card_only_delivered?: boolean;
  placed_at: string;
  account_id?: string;
}

/** 订单详情（含规格与收货信息） */
export interface OrderDetail extends Order {
  spec_name?: string;
  spec_value?: string;
  receiver_name?: string;
  receiver_phone?: string;
  receiver_address?: string;
  // 以下为详情弹窗补字段（字段名与后端 OrderOut/详情响应一致）
  chat_id?: string; // 会话ID（任务 conversation_id）
  is_bargain?: boolean; // 是否小刀
  is_red_flower?: boolean; // 是否已求小红花（任务 has_red_flower）
  is_agent_order?: boolean; // 订单类型：代销/自营（任务 order_type）
  delivery_content?: string; // 发货内容（卡券内容）
  delivery_fail_reason?: string; // 发货失败原因
  delivery_send_status?: string | null; // 关联消息发送状态
  delivery_send_fail_reason?: string | null; // 关联消息发送失败原因
  created_at?: string;
  updated_at?: string;
}

/** 自动评价配置（对外语义字段） */
export interface AutoRateConfig {
  enabled: boolean;
  text?: string;
  api_mode?: boolean;
}

/**
 * 自动确认收货配置（对外语义字段）。
 *
 * 说明：后端 PUT 要求 enabled，此处显式声明（任务描述中“同上”即指
 * 与自动评价一致，包含启用开关）。
 */
export interface ConfirmReceiptConfig {
  enabled: boolean;
  text?: string;
  image_url?: string;
}

// ---------------------------------------------------------------------------
// 内部工具：响应解包
// ---------------------------------------------------------------------------

/**
 * 后端统一响应可能裸返回，也可能包一层 `{ success, data }`。
 * 这里统一取出内部 data；无包裹则原样返回。
 */
function unwrap(data: unknown): unknown {
  if (data && typeof data === 'object' && 'data' in (data as Record<string, unknown>)) {
    const inner = (data as { data?: unknown }).data;
    if (inner != null) return inner;
  }
  return data;
}

/** 安全读取对象上的字符串字段 */
function str(obj: Record<string, unknown> | null, ...keys: string[]): string | undefined {
  if (!obj) return undefined;
  for (const k of keys) {
    const v = obj[k];
    if (v != null) return String(v);
  }
  return undefined;
}

/** 安全读取对象上的布尔字段 */
function bool(obj: Record<string, unknown> | null, ...keys: string[]): boolean {
  if (!obj) return false;
  for (const k of keys) {
    const v = obj[k];
    if (typeof v === 'boolean') return v;
    if (typeof v === 'string') return v === 'true' || v === 'True';
  }
  return false;
}

// ---------------------------------------------------------------------------
// 订单列表与详情
// ---------------------------------------------------------------------------

/**
 * 将后端原始订单对象映射为 Order 接口格式。
 * 后端字段 order_id/buyer_fish_nick/cookie_id → 前端 order_no/buyer_nick/account_id
 */
function mapOrder(raw: Record<string, unknown>): Order {
  return {
    id: String(raw.id ?? ''),
    order_no: String(raw.order_id ?? raw.order_no ?? raw.id ?? ''),
    item_title: String(raw.item_title ?? ''),
    buyer_id: String(raw.buyer_id ?? ''),
    buyer_nick: raw.buyer_fish_nick != null ? String(raw.buyer_fish_nick) : (raw.buyer_nick as string | undefined),
    amount: String(raw.amount ?? ''),
    quantity: Number(raw.quantity ?? 1),
    status: String(raw.status ?? ''),
    delivery_method: String(raw.delivery_method ?? ''),
    card_only_delivered: bool(raw, 'card_only_delivered'),
    placed_at: String(raw.placed_at ?? ''),
    account_id: raw.cookie_id != null ? String(raw.cookie_id) : (raw.account_id as string | undefined),
  };
}

/** 将原始订单详情对象映射为 OrderDetail 格式 */
function mapOrderDetail(raw: Record<string, unknown>): OrderDetail {
  return {
    ...mapOrder(raw),
    spec_name: raw.spec_name != null ? String(raw.spec_name) : (raw.sku_info != null ? String(raw.sku_info) : undefined),
    spec_value: raw.spec_value != null ? String(raw.spec_value) : undefined,
    receiver_name: raw.receiver_name != null ? String(raw.receiver_name) : undefined,
    receiver_phone: raw.receiver_phone != null ? String(raw.receiver_phone) : undefined,
    receiver_address: raw.receiver_address != null ? String(raw.receiver_address) : undefined,
    chat_id: str(raw, 'chat_id'),
    is_bargain: bool(raw, 'is_bargain'),
    is_red_flower: bool(raw, 'is_red_flower'),
    is_agent_order: bool(raw, 'is_agent_order'),
    delivery_content: str(raw, 'delivery_content'),
    delivery_fail_reason: str(raw, 'delivery_fail_reason'),
    delivery_send_status: str(raw, 'delivery_send_status'),
    delivery_send_fail_reason: str(raw, 'delivery_send_fail_reason'),
    created_at: str(raw, 'created_at'),
    updated_at: str(raw, 'updated_at'),
  };
}

/**
 * 分页获取订单列表。
 *
 * 后端响应约定为 `{ data: Order[], total }`，但也可能包一层 `{ success, data }`
 * 或直接返回裸数组，三种形态均兼容。
 */
export async function getOrders(
  page: number,
  pageSize: number,
): Promise<{ data: Order[]; total: number }> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/orders', {
    params: { query: { page, page_size: pageSize } },
  })) as { data?: unknown; error?: unknown };

  const body = data;
  // 裸数组
  if (Array.isArray(body)) {
    const arr = (body as Record<string, unknown>[]).map(mapOrder);
    return { data: arr, total: arr.length };
  }
  if (body && typeof body === 'object') {
    const obj = body as Record<string, unknown>;
    // 包一层 { success, data: { data, total } }
    if (
      'success' in obj &&
      obj.data != null &&
      typeof obj.data === 'object' &&
      !Array.isArray(obj.data)
    ) {
      const inner = obj.data as Record<string, unknown>;
      const rawArr = Array.isArray(inner.data) ? (inner.data as Record<string, unknown>[]) : [];
      const arr = rawArr.map(mapOrder);
      return {
        data: arr,
        total: typeof inner.total === 'number' ? inner.total : arr.length,
      };
    }
    // 直接 { data: [...], total }
    if (Array.isArray(obj.data)) {
      const rawArr = obj.data as Record<string, unknown>[];
      const arr = rawArr.map(mapOrder);
      return {
        data: arr,
        total: typeof obj.total === 'number' ? obj.total : arr.length,
      };
    }
  }
  return { data: [], total: 0 };
}

/**
 * 获取订单详情。
 *
 * 响应可能裸返回 OrderDetail，也可能包一层 `{ success, data }`，两种都兼容
 * （与 api/wrappers/orders.ts 中 getOrderDetail 的处理方式保持一致）。
 */
export async function getOrderDetail(orderNo: string): Promise<OrderDetail> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `/api/v1/orders/${encodeURIComponent(orderNo)}`,
  )) as {
    data?: OrderDetail | { success?: boolean; data?: OrderDetail; message?: string };
    error?: unknown;
  };
  if (!data) throw new Error('获取订单详情失败');
  if (typeof data === 'object' && 'order_no' in data) {
    return mapOrderDetail(data as unknown as Record<string, unknown>);
  }
  if (typeof data === 'object' && 'order_id' in data) {
    return mapOrderDetail(data as unknown as Record<string, unknown>);
  }
  const wrapped = data as { data?: Record<string, unknown>; message?: string };
  if (wrapped.data) return mapOrderDetail(wrapped.data);
  throw new Error(wrapped.message || '获取订单详情失败');
}

/**
 * 删除订单。
 *
 * 后端 DELETE /api/v1/orders/{order_id} 的路径参数为数据库主键 id（声明为 int，
 * 但 FastAPI 会把数字字符串解析为 int；web 端亦直接传 order.id 字符串）。
 * 故此处传入 Order.id（即后端返回的 str(order.id)）。
 */
export async function deleteOrder(id: string): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/orders/${encodeURIComponent(id)}`);
}

// ---------------------------------------------------------------------------
// 同步闲鱼订单
// ---------------------------------------------------------------------------

/**
 * 同步闲鱼订单到数据库。
 *
 * 注意：请求体字段为 `cookie_id`（与后端 FetchXianyuOrdersRequest schema 一致，
 * 而非 account_id）。该接口可能耗时较长，通过 AbortController 设置 10 分钟超时。
 */
export async function fetchXianyuOrders(cookieId: string): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)('/api/v1/orders/fetch-xianyu', {
    body: { cookie_id: cookieId },
  });
}

// ---------------------------------------------------------------------------
// 自动评价配置
// ---------------------------------------------------------------------------

/**
 * 获取账号的自动评价配置。
 *
 * 后端字段 enabled / rate_type / text_content / api_url → 翻译为
 * { enabled, text, api_mode }。
 */
export async function getAutoRateConfig(
  accountId: string,
): Promise<AutoRateConfig> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `/api/v1/auto-rate/${encodeURIComponent(accountId)}`,
  )) as { data?: unknown; error?: unknown };
  const body = unwrap(data) as Record<string, unknown> | null;
  if (!body || typeof body !== 'object') {
    return { enabled: false, text: '', api_mode: false };
  }
  const rateType = str(body, 'rate_type');
  return {
    enabled: bool(body, 'enabled'),
    text: str(body, 'text_content', 'text') ?? '',
    api_mode: rateType != null ? rateType === 'api' : bool(body, 'api_mode'),
  };
}

/**
 * 更新账号的自动评价配置。
 *
 * 将 { enabled, text, api_mode } 翻译为后端 AutoRateConfigUpdate：
 * { enabled, rate_type, text_content, api_url }。
 */
export async function updateAutoRateConfig(
  accountId: string,
  config: AutoRateConfig,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(`/api/v1/auto-rate/${encodeURIComponent(accountId)}`, {
    body: {
      enabled: config.enabled,
      rate_type: config.api_mode ? 'api' : 'text',
      text_content: config.text ?? '',
      api_url: null,
    },
  });
}

/**
 * 批量补评价。
 *
 * 对所有选中账号执行补评价操作（后端会逐个执行，每笔间隔 1 秒）。
 */
export async function batchRate(accountIds: string[]): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)('/api/v1/auto-rate/batch-rate', {
    body: { account_ids: accountIds },
  });
}

// ---------------------------------------------------------------------------
// 自动确认收货消息配置
// ---------------------------------------------------------------------------

/**
 * 获取账号的确认收货消息配置。
 *
 * 后端字段 enabled / message_content / message_image → 翻译为
 * { enabled, text, image_url }。
 */
export async function getConfirmReceiptConfig(
  accountId: string,
): Promise<ConfirmReceiptConfig> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `/api/v1/confirm-receipt-messages/${encodeURIComponent(accountId)}`,
  )) as { data?: unknown; error?: unknown };
  const body = unwrap(data) as Record<string, unknown> | null;
  if (!body || typeof body !== 'object') {
    return { enabled: false, text: '', image_url: '' };
  }
  return {
    enabled: bool(body, 'enabled'),
    text: str(body, 'message_content', 'text') ?? '',
    image_url: str(body, 'message_image', 'image_url') ?? '',
  };
}

/**
 * 更新账号的确认收货消息配置。
 *
 * 将 { enabled, text, image_url } 翻译为后端 ConfirmReceiptMessageUpdate：
 * { enabled, message_content, message_image }（三者均为必填）。
 */
export async function updateConfirmReceiptConfig(
  accountId: string,
  config: ConfirmReceiptConfig,
): Promise<void> {
  const client = await getApiClient();
  await (client.PUT as any)(
    `/api/v1/confirm-receipt-messages/${encodeURIComponent(accountId)}`,
    {
      body: {
        enabled: config.enabled,
        message_content: config.text ?? '',
        message_image: config.image_url ?? '',
      },
    },
  );
}
