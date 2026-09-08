import { getApiClient, extractError } from './client';

export interface PasswordLoginSession {
  session_id: string;
  status: 'idle' | 'processing' | 'verification_required' | 'success' | 'failed';
  verification_url?: string;
  face_qr_url?: string;
  screenshot_path?: string;
  message?: string;
}

/** 后端统一响应为 { success, message, data }，抽出内部 data；未包裹则原样返回 */
function unwrapData<T>(body: unknown): T {
  if (body && typeof body === 'object' && 'success' in body && 'data' in body) {
    const inner = (body as { data: unknown }).data;
    if (inner != null) return inner as T;
  }
  return body as T;
}

/**
 * 发起闲鱼账号密码登录。
 * POST /api/v1/password-login  body: { account_id, password, show_browser? }
 */
export async function startPasswordLogin(
  accountId: string,
  password: string,
  showBrowser?: boolean,
): Promise<PasswordLoginSession> {
  const client = await getApiClient();
  const body: Record<string, unknown> = { account_id: accountId, password };
  if (showBrowser != null) body.show_browser = showBrowser;
  const { data } = (await (client.POST as any)('/api/v1/password-login', {
    body,
  })) as { data?: unknown; error?: unknown };
  return unwrapData<PasswordLoginSession>(data ?? {});
}

/**
 * 检查密码登录状态。
 * GET /api/v1/password-login/check/{session_id}
 * 注意：响应可能不含 session_id，调用方应与既有会话合并以维持轮询。
 */
export async function checkPasswordLoginStatus(
  sessionId: string,
): Promise<PasswordLoginSession> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    `/api/v1/password-login/check/${sessionId}`,
  )) as { data?: unknown; error?: unknown };
  return unwrapData<PasswordLoginSession>(data ?? {});
}

/**
 * 取消密码登录会话。
 * DELETE /api/v1/password-login/cancel/{session_id}
 */
export async function cancelPasswordLogin(sessionId: string): Promise<void> {
  const client = await getApiClient();
  await (client.DELETE as any)(`/api/v1/password-login/cancel/${sessionId}`);
}
