import { getApiClient, extractError } from './client';

// ---------------------------------------------------------------------------
// 商品通用查询按钮配置（存 xy_catalog_items.metadata_json.query_buttons）
// 后端路由前缀: /api/v1/items
//   GET/PUT /api/v1/items/{cookie_id}/{item_id}/query-buttons
// 结构见 docs 全局接口契约：买家端只见按钮名，执行走服务端代理。
// ---------------------------------------------------------------------------

const PREFIX = '/api/v1/items';

/** 查询结果字段：path 为 JSON 点路径（数字段作数组下标），highlight=主结果大字，prefix 如 ¥ */
export interface QueryResultField {
  label: string;
  path: string;
  highlight?: boolean;
  prefix?: string;
}

/** 通用查询按钮配置（与后端 metadata_json.query_buttons 元素结构一致） */
export interface QueryButton {
  name: string;
  method: 'GET' | 'POST';
  url: string;
  /** 请求头（值支持变量 {cookie} {account} {api_key} {line}） */
  headers?: Record<string, string> | null;
  /** 仅 POST 用，字符串模板（支持变量） */
  body?: string | null;
  /** 与 success_value 都空时 HTTP 2xx 即成功；否则取响应点路径值做字符串相等比较 */
  success_path?: string | null;
  success_value?: string | null;
  /** 失败时从响应取错误消息的点路径 */
  error_path?: string | null;
  result_fields: QueryResultField[];
}

/** 宽松归一后端下发的单条按钮配置（字段缺失/类型异常时兜底） */
function normalizeButton(raw: unknown): QueryButton | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  const name = typeof obj.name === 'string' ? obj.name : '';
  const url = typeof obj.url === 'string' ? obj.url : '';
  if (!name || !url) return null;
  const headers =
    obj.headers && typeof obj.headers === 'object' && !Array.isArray(obj.headers)
      ? Object.fromEntries(
          Object.entries(obj.headers as Record<string, unknown>).map(([k, v]) => [k, String(v)]),
        )
      : null;
  const fields = Array.isArray(obj.result_fields)
    ? (obj.result_fields as unknown[])
        .filter((f): f is Record<string, unknown> => !!f && typeof f === 'object')
        .map((f) => ({
          label: typeof f.label === 'string' ? f.label : '',
          path: typeof f.path === 'string' ? f.path : '',
          highlight: f.highlight != null ? Boolean(f.highlight) : undefined,
          prefix: typeof f.prefix === 'string' && f.prefix ? f.prefix : undefined,
        }))
        .filter((f) => f.label && f.path)
    : [];
  return {
    name,
    method: obj.method === 'POST' ? 'POST' : 'GET',
    url,
    headers,
    body: typeof obj.body === 'string' && obj.body ? obj.body : null,
    success_path:
      typeof obj.success_path === 'string' && obj.success_path ? obj.success_path : null,
    success_value:
      typeof obj.success_value === 'string' && obj.success_value ? obj.success_value : null,
    error_path: typeof obj.error_path === 'string' && obj.error_path ? obj.error_path : null,
    result_fields: fields,
  };
}

/**
 * 获取商品的通用查询按钮配置。
 * 后端: GET /api/v1/items/{cookie_id}/{item_id}/query-buttons → data: { buttons: QueryButton[] }
 * 未配置时返回空数组。
 */
export async function getItemQueryButtons(
  cookieId: string,
  itemId: string,
): Promise<QueryButton[]> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    `${PREFIX}/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}/query-buttons`,
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const res = (data ?? {}) as Record<string, unknown>;
  if (res.success === false) {
    throw new Error(
      typeof res.message === 'string' && res.message ? res.message : '获取查询配置失败',
    );
  }
  const inner =
    res.data && typeof res.data === 'object' ? (res.data as Record<string, unknown>) : res;
  const rawButtons = Array.isArray(inner.buttons) ? inner.buttons : [];
  return rawButtons
    .map(normalizeButton)
    .filter((b): b is QueryButton => b != null);
}

/**
 * 整体覆盖保存商品的通用查询按钮配置。
 * 后端: PUT /api/v1/items/{cookie_id}/{item_id}/query-buttons，body: { buttons }
 * 后端校验 name/url/result_fields.path 必填、method 枚举、url 必须 http(s)，
 * 业务失败返回 HTTP 200 + success=false，此处统一抛中文 message。
 */
export async function saveItemQueryButtons(
  cookieId: string,
  itemId: string,
  buttons: QueryButton[],
): Promise<string> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `${PREFIX}/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}/query-buttons`,
    { body: { buttons } },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const res = (data ?? {}) as Record<string, unknown>;
  if (res.success === false) {
    throw new Error(
      typeof res.message === 'string' && res.message ? res.message : '保存查询配置失败',
    );
  }
  return typeof res.message === 'string' && res.message ? res.message : '查询配置已保存';
}
