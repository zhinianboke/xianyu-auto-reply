import createClient from 'openapi-fetch';
import type { paths } from '../generated/types';
import { getToken, getServerUrl } from '@/lib/config';
import { ApiError } from './errors';
import { useAuthStore } from '@/stores/auth';
import { logger } from '@/lib/logger';

let cachedClient: ReturnType<typeof createClient<paths>> | null = null;
let cachedBaseUrl: string | null = null;

export function getClient(baseUrl?: string): ReturnType<typeof createClient<paths>> {
  const effectiveBaseUrl = baseUrl ?? cachedBaseUrl;
  if (!effectiveBaseUrl) {
    throw new ApiError('未配置服务器地址', 0);
  }
  if (cachedClient && cachedBaseUrl === effectiveBaseUrl) {
    return cachedClient;
  }

  const client = createClient<paths>({ baseUrl: effectiveBaseUrl });

  // 请求拦截：注入 JWT token + 日志
  client.use({
    onRequest: async ({ request }) => {
      const token = await getToken();
      if (token) {
        request.headers.set('Authorization', `Bearer ${token}`);
      }
      logger.debug('HTTP', `${request.method} ${request.url}`);
      return request;
    },
  });

  // 响应拦截：统一错误处理 + 日志
  client.use({
    onResponse: async ({ response }) => {
      if (response.status === 401) {
        logger.warn('HTTP', `401 未授权: ${response.url}`);
        useAuthStore.getState().logout();
      }
      if (!response.ok) {
        logger.error('HTTP', `HTTP ${response.status}: ${response.url}`);
        // 统一抛出错误：openapi-fetch 非 2xx 返回 {data:undefined,error}，
        // 若不在此抛出，未检查 error 的 wrapper 会把失败当成功处理
        let message = `请求失败 (${response.status})`;
        try {
          const body = await response.clone().json();
          if (body && typeof body === 'object') {
            const b = body as Record<string, unknown>;
            if (typeof b.message === 'string') message = b.message;
            else if (typeof b.detail === 'string') message = b.detail;
          }
        } catch {
          // 响应体不是 JSON，保留默认消息
        }
        throw new ApiError(message, response.status);
      }
      // 不返回 response：openapi-fetch 的 instanceof Response 检查在 RN 中会失败
    },
  });

  cachedClient = client;
  cachedBaseUrl = effectiveBaseUrl;
  return client;
}

/** 异步获取客户端（从 config 读取 baseUrl） */
export async function getApiClient(): Promise<ReturnType<typeof createClient<paths>>> {
  const baseUrl = await getServerUrl();
  if (!baseUrl) throw new ApiError('未配置服务器地址', 0);
  return getClient(baseUrl);
}

/**
 * 从 openapi-fetch 的 error 中提取错误消息。
 * 所有 wrapper 调用后在 error 分支使用此函数。
 */
export async function extractError(error: unknown): Promise<ApiError> {
  if (error instanceof ApiError) return error;
  if (error instanceof Response) {
    let msg = `请求失败 (${error.status})`;
    try {
      const data = await error.json();
      if (data && typeof data === 'object') {
        const d = data as Record<string, unknown>;
        if (typeof d.message === 'string') msg = d.message;
        else if (typeof d.detail === 'string') msg = d.detail;
      }
    } catch {
      // 响应体不是 JSON
    }
    return new ApiError(msg, error.status);
  }
  if (error instanceof Error) {
    return new ApiError(error.message, 0);
  }
  return new ApiError('未知错误', 0);
}
