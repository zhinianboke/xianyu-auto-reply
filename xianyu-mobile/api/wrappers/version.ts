import { extractError, getApiClient } from './client';

interface CurrentVersionResponse {
  success?: boolean;
  message?: string;
  data?: { version?: unknown };
}

/** 获取后台系统版本号。 */
export async function getCurrentVersion(): Promise<string> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    '/api/v1/version/current',
  )) as { data?: unknown; error?: unknown };

  if (error) throw await extractError(error);

  const response = data as CurrentVersionResponse | undefined;
  if (!response || response.success !== true) {
    throw new Error(response?.message || '获取后台版本失败');
  }

  const version = response.data?.version;
  if (typeof version !== 'string' || !version.trim()) {
    throw new Error('后台未返回版本号');
  }

  return version.trim();
}
