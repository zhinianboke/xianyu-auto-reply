/**
 * Token 获取方式设置接口。
 *
 * 功能：
 * 1. 规范化 Token 获取方式
 * 2. 独立保存设置，避免提交页面其他未保存内容
 * 3. 测试远程 Token 接口连通性
 */
import { post, put } from '@/utils/request'
import type { ApiResponse, TokenApiMode } from '@/types'

const TOKEN_API_MODE_URL = '/api/v1/system-settings/token.api_mode'
const TOKEN_REMOTE_URL = '/api/v1/system-settings/token.remote_url'
const TOKEN_REMOTE_SECRET_KEY_URL = '/api/v1/system-settings/token.remote_secret_key'
const TOKEN_REMOTE_TEST_URL = '/api/v1/system-settings/test-token-remote'
const TOKEN_API_MODES: TokenApiMode[] = ['web', 'remote']

export interface RemoteTokenSettingsPayload {
  remote_url: string
  remote_secret_key: string
}

export const normalizeTokenApiMode = (value: unknown): TokenApiMode => {
  return TOKEN_API_MODES.includes(value as TokenApiMode)
    ? value as TokenApiMode
    : 'web'
}

export const updateTokenApiMode = (mode: TokenApiMode): Promise<ApiResponse> => {
  return put<ApiResponse>(TOKEN_API_MODE_URL, { value: mode })
}

export const updateRemoteTokenSettings = async (
  mode: TokenApiMode,
  remoteUrl: string,
  remoteSecretKey: string,
): Promise<ApiResponse> => {
  const operations: Array<() => Promise<ApiResponse>> = [
    () => put<ApiResponse>(TOKEN_REMOTE_URL, { value: remoteUrl }),
    () => put<ApiResponse>(TOKEN_REMOTE_SECRET_KEY_URL, { value: remoteSecretKey }),
    () => put<ApiResponse>(TOKEN_API_MODE_URL, { value: mode }),
  ]

  for (const operation of operations) {
    const result = await operation()
    if (!result?.success) {
      return result || { success: false, message: 'Token远程接口设置保存失败' }
    }
  }

  return { success: true, message: 'Token远程接口设置已保存' }
}

export const testRemoteTokenInterface = (
  payload: RemoteTokenSettingsPayload,
): Promise<ApiResponse<{ token: string; device_id: string; api_mode: string }>> => {
  return post<ApiResponse<{ token: string; device_id: string; api_mode: string }>>(
    TOKEN_REMOTE_TEST_URL,
    payload,
  )
}
