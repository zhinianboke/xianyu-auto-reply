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

/** 获取商品的通用查询按钮配置。 */
export interface ItemQueryButtonsConfig {
  buttons: QueryButton[];
  /** 查询页顶部提示文案（metadata_json.page_hint），空串表示不显示 */
  pageHint: string;
}

/**
 * 获取商品的通用查询按钮配置。
 * 后端: GET /api/v1/items/{cookie_id}/{item_id}/query-buttons → data: { buttons, page_hint }
 * 未配置时返回空数组与空串。
 */
export async function getItemQueryButtons(
  cookieId: string,
  itemId: string,
): Promise<ItemQueryButtonsConfig> {
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
  const buttons = rawButtons
    .map(normalizeButton)
    .filter((b): b is QueryButton => b != null);
  const pageHint = typeof inner.page_hint === 'string' ? inner.page_hint : '';
  return { buttons, pageHint };
}

/**
 * 整体覆盖保存商品的通用查询按钮配置。
 * 后端: PUT /api/v1/items/{cookie_id}/{item_id}/query-buttons，body: { buttons, page_hint }
 * 后端校验 name/url/result_fields.path 必填、method 枚举、url 必须 http(s)，
 * 业务失败返回 HTTP 200 + success=false，此处统一抛中文 message。
 */
export async function saveItemQueryButtons(
  cookieId: string,
  itemId: string,
  buttons: QueryButton[],
  /** 查询页顶部提示文案，空串表示不显示 */
  pageHint?: string,
): Promise<string> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `${PREFIX}/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}/query-buttons`,
    { body: { buttons, page_hint: pageHint ?? '' } },
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

// ---------------------------------------------------------------------------
// 商品展示入口（存 xy_catalog_items.metadata_json.display_links）
// 后端路由前缀同 query-buttons: /api/v1/items
//   GET/PUT /api/v1/items/{cookie_id}/{item_id}/display-links
//   POST    /api/v1/items/{cookie_id}/{item_id}/display-links/upload-image
// 结构见 docs 全局接口契约：买家提货页底部入口区渲染，text/image 点击弹窗。
// 默认模板的合并由提卡页负责，本模块只读写商品自身条目。
// ---------------------------------------------------------------------------

/** 展示入口条目（三型联合，字段与后端 metadata_json.display_links 元素结构一致） */
export type DisplayLinkEntry =
  | { name: string; type: 'link'; url: string; note?: string }
  | { name: string; type: 'text'; title: string; content: string }
  | { name: string; type: 'image'; url: string; note?: string };

/** 宽松归一后端下发的单条展示入口（必填字段缺失/类型未知时丢弃该条） */
function normalizeDisplayLink(raw: unknown): DisplayLinkEntry | null {
  if (!raw || typeof raw !== 'object') return null;
  const obj = raw as Record<string, unknown>;
  const name = typeof obj.name === 'string' ? obj.name : '';
  if (!name) return null;
  const note = typeof obj.note === 'string' && obj.note ? obj.note : undefined;
  if (obj.type === 'link') {
    const url = typeof obj.url === 'string' ? obj.url : '';
    return url ? { name, type: 'link', url, note } : null;
  }
  if (obj.type === 'image') {
    // url 为 /static/... 相对路径或 http(s) 外链，展示端负责拼服务器地址
    const url = typeof obj.url === 'string' ? obj.url : '';
    return url ? { name, type: 'image', url, note } : null;
  }
  if (obj.type === 'text') {
    const title = typeof obj.title === 'string' ? obj.title : '';
    const content = typeof obj.content === 'string' ? obj.content : '';
    return title && content ? { name, type: 'text', title, content } : null;
  }
  return null;
}

/**
 * 获取商品的展示入口配置。
 * 后端: GET /api/v1/items/{cookie_id}/{item_id}/display-links → data: { links }
 * 未配置时返回空数组。
 */
export async function getItemDisplayLinks(
  cookieId: string,
  itemId: string,
): Promise<DisplayLinkEntry[]> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    `${PREFIX}/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}/display-links`,
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const res = (data ?? {}) as Record<string, unknown>;
  if (res.success === false) {
    throw new Error(
      typeof res.message === 'string' && res.message ? res.message : '获取展示入口配置失败',
    );
  }
  const inner =
    res.data && typeof res.data === 'object' ? (res.data as Record<string, unknown>) : res;
  const rawLinks = Array.isArray(inner.links) ? inner.links : [];
  return rawLinks
    .map(normalizeDisplayLink)
    .filter((e): e is DisplayLinkEntry => e != null);
}

/**
 * 整体覆盖保存商品的展示入口配置。
 * 后端: PUT /api/v1/items/{cookie_id}/{item_id}/display-links，body: { links }
 * 后端按类型白名单收敛字段（link/image 存 name/type/url/note，text 存 name/type/title/content），
 * 业务失败返回 HTTP 200 + success=false，此处统一抛中文 message。
 */
export async function saveItemDisplayLinks(
  cookieId: string,
  itemId: string,
  links: DisplayLinkEntry[],
): Promise<void> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(
    `${PREFIX}/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}/display-links`,
    { body: { links } },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const res = (data ?? {}) as Record<string, unknown>;
  if (res.success === false) {
    throw new Error(
      typeof res.message === 'string' && res.message ? res.message : '保存展示入口配置失败',
    );
  }
}

/**
 * 上传展示入口图片（multipart/form-data，字段名 image），返回图片 URL。
 *
 * 复用项目 RN FormData 上传模式（见 products.ts uploadCardImage）：openapi-fetch 识别
 * FormData 后交由 fetch 自动设置 boundary，勿手动指定 Content-Type（会缺少 boundary
 * 导致后端解析失败）。后端返回 { success, message, data: { image_url } }，
 * 兼容无 data 包裹的 { image_url }。
 * @param fileUri 本地图片 uri（来自 expo-image-picker）
 */
export async function uploadItemDisplayLinkImage(
  cookieId: string,
  itemId: string,
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
    heic: 'image/heic',
    bmp: 'image/bmp',
  };
  const formData = new FormData();
  // RN FormData 文件字段需要 { uri, name, type } 结构
  formData.append('image', {
    uri: fileUri,
    name: `image.${ext}`,
    type: typeMap[ext] || 'image/jpeg',
  } as any);

  const { data, error } = (await (client.POST as any)(
    `${PREFIX}/${encodeURIComponent(cookieId)}/${encodeURIComponent(itemId)}/display-links/upload-image`,
    { body: formData },
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);

  const outer = (data && typeof data === 'object' ? data : {}) as Record<string, unknown>;
  const inner =
    outer.data && typeof outer.data === 'object' ? (outer.data as Record<string, unknown>) : {};
  const url =
    (typeof outer.image_url === 'string' ? outer.image_url : '') ||
    (typeof inner.image_url === 'string' ? inner.image_url : '');
  if (!url) {
    throw new Error(
      typeof outer.message === 'string' && outer.message ? outer.message : '图片上传失败',
    );
  }
  return url;
}
