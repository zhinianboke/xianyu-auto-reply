import { getApiClient, extractError } from './client';
import type { DisplayLinkEntry } from './item-query-config';

// ---------------------------------------------------------------------------
// 通用展示入口模板（用户级，xy_display_link_templates）
// 后端路由前缀: /api/v1/display-link-templates
//   GET    /api/v1/display-link-templates               列表（按 id 升序）
//   POST   /api/v1/display-link-templates               新建
//   PUT    /api/v1/display-link-templates/{id}          部分更新（仅更新显式提供的字段）
//   DELETE /api/v1/display-link-templates/{id}          删除
//   POST   /api/v1/display-link-templates/upload-image  multipart，字段名 image
// is_default 的模板由买家提卡页自动合并到所有商品；商品自身同名条目优先。
// ---------------------------------------------------------------------------

const PREFIX = '/api/v1/display-link-templates';

/** 通用展示入口模板（条目字段与商品 metadata_json.display_links 元素一致，另含 id/is_default） */
export interface DisplayLinkTemplate extends Record<string, unknown> {
  id: number;
  name: string;
  type: 'link' | 'text' | 'image';
  url?: string;
  note?: string;
  title?: string;
  content?: string;
  is_default: boolean;
}

/** 从 { templates: [...] }（可被 ApiResponse 包一层 data）中取出模板列表 */
function unwrapList(data: unknown): DisplayLinkTemplate[] {
  const res = (data ?? {}) as Record<string, unknown>;
  const inner =
    res.data && typeof res.data === 'object' ? (res.data as Record<string, unknown>) : res;
  const list = Array.isArray(inner.templates) ? inner.templates : [];
  return list.filter(
    (t): t is DisplayLinkTemplate =>
      !!t && typeof t === 'object' && typeof (t as Record<string, unknown>).id === 'number',
  );
}

/**
 * 获取通用展示入口模板列表。
 * 后端: GET /api/v1/display-link-templates → data: { templates }
 * 未配置时返回空数组。
 */
export async function getDisplayLinkTemplates(): Promise<DisplayLinkTemplate[]> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(PREFIX)) as {
    data?: unknown;
    error?: unknown;
  };
  if (error) throw await extractError(error);
  const res = (data ?? {}) as Record<string, unknown>;
  if (res.success === false) {
    throw new Error(
      typeof res.message === 'string' && res.message ? res.message : '获取通用入口模板失败',
    );
  }
  return unwrapList(data);
}

/**
 * 新建通用展示入口模板。
 * 后端: POST /api/v1/display-link-templates，body: { name, type, url?, note?, title?, content?, is_default }
 * 校验规则与商品展示入口一致（type 三型、link/image 需 url、text 需 title/content）。
 */
export async function createDisplayLinkTemplate(
  payload: Partial<DisplayLinkEntry> & { is_default?: boolean },
): Promise<void> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)(PREFIX, { body: payload })) as {
    data?: unknown;
    error?: unknown;
  };
  if (error) throw await extractError(error);
  const res = (data ?? {}) as Record<string, unknown>;
  if (res.success === false) {
    throw new Error(
      typeof res.message === 'string' && res.message ? res.message : '创建通用入口模板失败',
    );
  }
}

/**
 * 更新通用展示入口模板（部分更新：只提交显式提供的字段，未提供的保持原值）。
 * 后端: PUT /api/v1/display-link-templates/{id}
 */
export async function updateDisplayLinkTemplate(
  id: number,
  payload: Record<string, unknown>,
): Promise<void> {
  const client = await getApiClient();
  const { data, error } = (await (client.PUT as any)(`${PREFIX}/${id}`, {
    body: payload,
  })) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const res = (data ?? {}) as Record<string, unknown>;
  if (res.success === false) {
    throw new Error(
      typeof res.message === 'string' && res.message ? res.message : '更新通用入口模板失败',
    );
  }
}

/** 删除通用展示入口模板。后端: DELETE /api/v1/display-link-templates/{id} */
export async function deleteDisplayLinkTemplate(id: number): Promise<void> {
  const client = await getApiClient();
  const { data, error } = (await (client.DELETE as any)(`${PREFIX}/${id}`)) as {
    data?: unknown;
    error?: unknown;
  };
  if (error) throw await extractError(error);
  const res = (data ?? {}) as Record<string, unknown>;
  if (res.success === false) {
    throw new Error(
      typeof res.message === 'string' && res.message ? res.message : '删除通用入口模板失败',
    );
  }
}

/**
 * 上传模板图片（multipart/form-data，字段名 image），返回图片 URL。
 *
 * 与 item-query-config.ts uploadItemDisplayLinkImage 同一实现：openapi-fetch 识别
 * FormData 后交由 fetch 自动设置 boundary，勿手动指定 Content-Type。
 * 后端返回 { success, message, data: { image_url } }，兼容无 data 包裹的 { image_url }。
 * @param fileUri 本地图片 uri（来自 expo-image-picker）
 */
export async function uploadDisplayLinkTemplateImage(fileUri: string): Promise<string> {
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

  const { data, error } = (await (client.POST as any)(`${PREFIX}/upload-image`, {
    body: formData,
  })) as { data?: unknown; error?: unknown };
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
