import { getApiClient, extractError } from './client';
import type { AuthUser } from '@/stores/auth';

export interface LoginResponse {
  success: boolean;
  message?: string;
  token?: string | null;
  refresh_token?: string | null;
  user_id?: number | null;
  username?: string | null;
  is_admin?: boolean | null;
  account_limit?: number | null;
}

interface VerifyResponse {
  authenticated: boolean;
  user_id?: number;
  username?: string;
  is_admin?: boolean;
  account_limit?: number | null;
}

export async function login(
  username: string,
  password: string,
  geetestChallenge?: string,
): Promise<LoginResponse> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)('/api/v1/auth/login', {
    body: { username, password, geetest_challenge: geetestChallenge },
  })) as { data?: LoginResponse; error?: unknown };

  if (error) throw await extractError(error);
  return data as LoginResponse;
}

export async function verifyToken(): Promise<VerifyResponse> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)('/api/v1/auth/verify')) as {
    data?: VerifyResponse;
    error?: unknown;
  };
  return data as VerifyResponse;
}

export async function logout(): Promise<void> {
  const client = await getApiClient();
  await (client.POST as any)('/api/v1/auth/logout');
}

/** 将 LoginResponse 的平铺字段转为 AuthUser */
export function extractUser(resp: LoginResponse): AuthUser | null {
  if (resp.user_id == null || resp.username == null) return null;
  return {
    user_id: resp.user_id,
    username: resp.username,
    is_admin: resp.is_admin ?? false,
    account_limit: resp.account_limit ?? null,
  };
}

/** 邮箱 + 密码登录（若后端开启极验，需传入 geetestChallenge） */
export async function loginWithEmail(
  email: string,
  password: string,
  geetestChallenge?: string,
): Promise<LoginResponse> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)('/api/v1/auth/login', {
    body: { email, password, geetest_challenge: geetestChallenge },
  })) as { data?: LoginResponse; error?: unknown };

  if (error) throw await extractError(error);
  return data as LoginResponse;
}

/** 邮箱 + 验证码登录（emailSessionId 由 sendEmailCode 返回） */
export async function loginWithVerificationCode(
  email: string,
  verificationCode: string,
  emailSessionId: string,
): Promise<LoginResponse> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)('/api/v1/auth/login', {
    body: {
      email,
      verification_code: verificationCode,
      email_session_id: emailSessionId,
    },
  })) as { data?: LoginResponse; error?: unknown };

  if (error) throw await extractError(error);
  return data as LoginResponse;
}

/** 注册 */
export async function register(
  username: string,
  email: string,
  password: string,
  verificationCode: string,
  sessionId: string,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)('/api/v1/auth/register', {
    body: {
      username,
      email,
      password,
      verification_code: verificationCode,
      session_id: sessionId,
    },
  })) as { data?: { success: boolean; message?: string }; error?: unknown };

  if (error) throw await extractError(error);
  return data as { success: boolean; message?: string };
}

/** 发送邮箱验证码，返回 session_id（register/login/reset_password 通用） */
export async function sendEmailCode(
  email: string,
  type: 'register' | 'login' | 'reset_password',
): Promise<{ session_id: string; success: boolean }> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)(
    '/api/v1/captcha/send-email-code',
    {
      body: { email, type },
    },
  )) as { data?: { session_id: string; success: boolean }; error?: unknown };

  if (error) throw await extractError(error);
  return data as { session_id: string; success: boolean };
}

/** 重置密码 */
export async function resetPassword(
  email: string,
  verificationCode: string,
  newPassword: string,
): Promise<{ success: boolean; message?: string }> {
  const client = await getApiClient();
  const { data, error } = (await (client.POST as any)(
    '/api/v1/auth/reset-password',
    {
      body: {
        email,
        verification_code: verificationCode,
        new_password: newPassword,
      },
    },
  )) as { data?: { success: boolean; message?: string }; error?: unknown };

  if (error) throw await extractError(error);
  return data as { success: boolean; message?: string };
}

/**
 * 获取极验滑块配置（challenge / gt / new_captcha / offline）。
 *
 * 后端返回两层信封结构：{ success, code, message, data: { success, gt, challenge, new_captcha } }。
 * 此前实现直接读取外层，导致 gt/challenge 恒为 undefined、SDK 卡在“加载验证码”。
 * 这里统一解包到内层 data，并做参数完整性校验（缺参数立即抛错，避免静默卡死）。
 * 内层 success === 0 表示极验宕机降级模式（离线本地验证）。
 */
export async function getGeetestConfig(): Promise<{
  challenge: string;
  gt: string;
  new_captcha: boolean;
  offline: boolean;
}> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    '/api/v1/geetest/register',
  )) as {
    data?: {
      data?: {
        success?: number;
        gt?: string;
        challenge?: string;
        new_captcha?: boolean;
      };
      gt?: string;
      challenge?: string;
      new_captcha?: boolean;
    };
    error?: unknown;
  };

  if (error) throw await extractError(error);

  // 解包信封：优先取内层 data；若内层缺少 gt/challenge 则回退外层（兼容未来结构调整）
  const envelope = (data ?? {}) as Record<string, any>;
  const inner =
    envelope.data && (envelope.data.gt || envelope.data.challenge)
      ? envelope.data
      : envelope;

  const gt = inner.gt as string | undefined;
  const challenge = inner.challenge as string | undefined;
  if (!gt || !challenge) {
    throw new Error('验证码参数不完整，请重试');
  }

  return {
    gt,
    challenge,
    new_captcha: inner.new_captcha !== false,
    offline: inner.success === 0,
  };
}

/** 校验极验滑动结果 */
export async function validateGeetest(
  challenge: string,
  validate: string,
  seccode: string,
): Promise<void> {
  const client = await getApiClient();
  const { error } = (await (client.POST as any)('/api/v1/geetest/validate', {
    body: { challenge, validate, seccode },
  })) as { error?: unknown };

  if (error) throw await extractError(error);
}

/** 获取公共系统设置（login_captcha_enabled / registration_enabled 等） */
export async function getPublicSettings(): Promise<Record<string, unknown>> {
  const client = await getApiClient();
  const { data, error } = (await (client.GET as any)(
    '/api/v1/system-settings/public',
  )) as { data?: Record<string, unknown>; error?: unknown };

  if (error) throw await extractError(error);
  return (data ?? {}) as Record<string, unknown>;
}
