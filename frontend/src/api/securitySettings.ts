/** 管理员安全设置独立接口；不提交 SMTP 字段，不用默认值代替读取失败。 */
import type { ApiResponse } from '@/types'
import { get, put } from '@/utils/request'

export interface SecuritySettings {
  email_allowed_suffixes: string
  email_denied_suffixes: string
  email_denied_message: string
  denied_ips: string
}

export interface SecuritySettingsResponse extends ApiResponse<SecuritySettings> {
  message: string
}

const SECURITY_SETTINGS_URL = '/api/v1/system-settings/security'

/** 校验响应信封，HTTP 200 的空值、错误字段类型和缺失消息不能作为正常业务结果。 */
export const isSecuritySettingsResponse = (result: unknown): result is SecuritySettingsResponse => {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return false
  const values = result as Record<string, unknown>
  return typeof values.success === 'boolean' && Number.isInteger(values.code)
    && typeof values.message === 'string' && values.message.trim().length > 0
    && Object.prototype.hasOwnProperty.call(values, 'data')
    && (values.success || values.data === null)
}

/** 校验真实接口数据完整性，缺失字段不能默认为空并用于保存。 */
export const isSecuritySettings = (data: unknown): data is SecuritySettings => {
  if (!data || typeof data !== 'object') return false
  const values = data as Record<string, unknown>
  return ['email_allowed_suffixes', 'email_denied_suffixes', 'email_denied_message', 'denied_ips']
    .every((key) => typeof values[key] === 'string')
}

/** 读取管理员安全设置，保留后端中文业务失败响应。 */
export const getSecuritySettings = (): Promise<SecuritySettingsResponse> =>
  get<SecuritySettingsResponse>(SECURITY_SETTINGS_URL)

/** 整组提交安全设置；显式空字符串清空对应配置，后端原子校验和保存。 */
export const updateSecuritySettings = (settings: SecuritySettings): Promise<SecuritySettingsResponse> =>
  put<SecuritySettingsResponse>(SECURITY_SETTINGS_URL, settings)
