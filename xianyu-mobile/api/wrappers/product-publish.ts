import { getApiClient } from './client';

const PREFIX = '/api/v1/product-publish';

/** 解开 {success, message, data} 信封（后端业务失败也返回 HTTP 200，靠 success 区分） */
function unwrapData<T>(body: unknown): T {
  if (body && typeof body === 'object' && 'success' in body && 'data' in body) {
    const obj = body as { success: unknown; data: unknown };
    if (obj.success === true || obj.success === 'true') return obj.data as T;
    const msg = (body as { message?: string }).message || '操作失败';
    throw new Error(msg);
  }
  return body as T;
}

/** 从本地 uri 推断扩展名与 MIME 类型 */
function mimeFromUri(uri: string): { name: string; type: string } {
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
  return { name: `image.${ext}`, type: typeMap[ext] || 'image/jpeg' };
}

export interface UploadedImages {
  paths: string[];
  urls: string[];
}

/**
 * 上传商品兜底图片（multipart/form-data，字段名 files，多文件）。
 * 返回 {paths, urls}，提交任务时取 urls 填入 material_defaults.images
 * （与 web AiListingTaskPanel 一致：images 存预览 url）。
 * RN FormData 文件字段需 { uri, name, type }，openapi-fetch 识别 FormData 后交由 fetch 自动设置 boundary。
 */
export async function uploadProductImages(uris: string[]): Promise<UploadedImages> {
  if (uris.length === 0) return { paths: [], urls: [] };

  const client = await getApiClient();

  const formData = new FormData();
  uris.forEach((uri) => {
    const { name, type } = mimeFromUri(uri);
    formData.append('files', { uri, name, type } as any);
  });

  const { data } = (await (client.POST as any)(`${PREFIX}/upload/images`, {
    body: formData,
  })) as { data?: unknown };

  return unwrapData<UploadedImages>(data);
}
