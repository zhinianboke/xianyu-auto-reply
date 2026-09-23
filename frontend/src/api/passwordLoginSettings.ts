/**
 * 账号密码登录方式设置接口。
 *
 * 功能：
 * 1. 校验账号密码登录方式枚举值
 * 2. 独立保存登录方式，避免提交系统设置页的其他未保存内容
 * 3. 协议登录时保存远程URL与秘钥
 */
import { post, put } from '@/utils/request'
import type { ApiResponse, PasswordLoginMode } from '@/types'

const PASSWORD_LOGIN_MODE_URL = '/api/v1/system-settings/password_login.mode'
const PASSWORD_LOGIN_REMOTE_URL = '/api/v1/system-settings/password_login.remote_url'
const PASSWORD_LOGIN_REMOTE_SECRET_KEY_URL =
  '/api/v1/system-settings/password_login.remote_secret_key'
const PASSWORD_LOGIN_REMOTE_TEST_URL =
  '/api/v1/system-settings/test-password-login-remote'
const PASSWORD_LOGIN_MODES: PasswordLoginMode[] = ['protocol', 'browser']

export interface RemotePasswordLoginTestPayload {
  remote_url: string
  remote_secret_key: string
}

export const normalizePasswordLoginMode = (value: unknown): PasswordLoginMode => {
  return PASSWORD_LOGIN_MODES.includes(value as PasswordLoginMode)
    ? value as PasswordLoginMode
    : 'browser'
}

export const updatePasswordLoginMode = (
  mode: PasswordLoginMode,
): Promise<ApiResponse> => {
  return put<ApiResponse>(PASSWORD_LOGIN_MODE_URL, { value: mode })
}

/**
 * 保存协议登录远程接口设置：先写远程URL与秘钥，再切换登录方式。
 *
 * @param mode 登录方式（通常为 protocol）
 * @param remoteUrl 远程接口URL
 * @param remoteSecretKey 远程接口秘钥
 * @returns 统一响应；任一步骤失败即返回失败结果
 */
export const updateRemotePasswordLoginSettings = async (
  mode: PasswordLoginMode,
  remoteUrl: string,
  remoteSecretKey: string,
): Promise<ApiResponse> => {
  const operations: Array<() => Promise<ApiResponse>> = [
    () => put<ApiResponse>(PASSWORD_LOGIN_REMOTE_URL, { value: remoteUrl }),
    () => put<ApiResponse>(PASSWORD_LOGIN_REMOTE_SECRET_KEY_URL, { value: remoteSecretKey }),
    () => put<ApiResponse>(PASSWORD_LOGIN_MODE_URL, { value: mode }),
  ]

  for (const operation of operations) {
    const result = await operation()
    if (!result?.success) {
      return result || { success: false, message: '协议登录远程接口设置保存失败' }
    }
  }

  return { success: true, message: '协议登录远程接口设置已保存' }
}

/**
 * 测试协议登录远程接口（阿里滑块获取 x5sec）连通性与秘钥有效性。
 *
 * @param payload 远程接口URL与秘钥
 * @returns 统一响应，success 表示连通且秘钥有效
 */
export const testRemotePasswordLoginInterface = (
  payload: RemotePasswordLoginTestPayload,
): Promise<ApiResponse> => {
  return post<ApiResponse>(PASSWORD_LOGIN_REMOTE_TEST_URL, payload)
}
