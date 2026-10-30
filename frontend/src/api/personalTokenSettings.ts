/** 个人 Token 远程配置接口：读取、原子保存及复用系统测试协议。 */
import { get, post, put } from '@/utils/request'
import type { ApiResponse } from '@/types'
import type { RemoteTokenSettingsPayload } from './tokenApiModeSettings'

const TOKEN_SETTINGS_URL = '/api/v1/user-settings/external-api/token'

/** 读取当前登录用户保存的 URL 和秘钥，失败保持后端原始提示。 */
export const getPersonalTokenSettings = (): Promise<ApiResponse<RemoteTokenSettingsPayload>> => {
  return get(TOKEN_SETTINGS_URL)
}

/** 在同一事务中保存个人 URL 和秘钥。 */
export const savePersonalTokenSettings = (
  payload: RemoteTokenSettingsPayload,
): Promise<ApiResponse<RemoteTokenSettingsPayload>> => {
  return put(TOKEN_SETTINGS_URL, payload)
}

/** 测试当前输入的配置，不要求先保存。 */
export const testPersonalTokenSettings = (
  payload: RemoteTokenSettingsPayload,
): Promise<ApiResponse<{ token: string; device_id: string; api_mode: string }>> => {
  return post(`${TOKEN_SETTINGS_URL}/test`, payload)
}
