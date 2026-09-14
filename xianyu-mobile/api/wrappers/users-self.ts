import { getApiClient, extractError } from './client';
import { ApiError } from './errors';

// ---------------------------------------------------------------------------
// 当前用户凭证：对接码 / 分销 API 秘钥
// 后端路由前缀: /api/v1/users（users.py）
// 注意：GET 接口为直返信封 { success, dock_code | secret_key }（无 data 包裹），
// 且首次调用时后端会自动生成并持久化凭证，可安全重复调用。
// ---------------------------------------------------------------------------

/** 从后端直返信封中宽松取字符串字段 */
function pickString(data: unknown, key: string): string | null {
  if (data && typeof data === 'object') {
    const v = (data as Record<string, unknown>)[key];
    if (v != null && v !== '') return String(v);
  }
  return null;
}

/** 获取当前用户对接码（8 位大写字母+数字，无则自动生成） */
export async function getDockCode(): Promise<string> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    '/api/v1/users/dock-code',
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const code = pickString(data, 'dock_code');
  if (!code) throw new ApiError('未获取到对接码', 0);
  return code;
}

/** 重置对接码（旧码立即失效，并清除所有已绑定分销商与对接记录） */
export async function resetDockCode(): Promise<{
  success: boolean;
  message?: string;
}> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)(
    '/api/v1/users/dock-code/reset',
  )) as {
    data?: { success?: boolean; message?: string };
    error?: unknown;
  };
  if (error) throw await extractError(error);
  return { success: data?.success ?? true, message: data?.message };
}

/** 获取当前用户分销秘钥（32 位随机字符，无则自动生成） */
export async function getSecretKey(): Promise<string> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    '/api/v1/users/secret-key',
  )) as { data?: unknown; error?: unknown };
  if (error) throw await extractError(error);
  const key = pickString(data, 'secret_key');
  if (!key) throw new ApiError('未获取到分销秘钥', 0);
  return key;
}

/** 更换分销秘钥（旧秘钥立即失效），后端在 data 中直接返回新秘钥 */
export async function resetSecretKey(): Promise<{
  success: boolean;
  message?: string;
  secret_key?: string;
}> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)(
    '/api/v1/users/secret-key/reset',
  )) as {
    data?: {
      success?: boolean;
      message?: string;
      data?: { secret_key?: string } | null;
    };
    error?: unknown;
  };
  if (error) throw await extractError(error);
  const inner = data?.data;
  return {
    success: data?.success ?? true,
    message: data?.message,
    secret_key:
      pickString(inner, 'secret_key') ?? pickString(data, 'secret_key') ??
      undefined,
  };
}
