/** 管理员安全设置独立接口；不提交 SMTP 字段，不用默认值代替读取失败。 */
import type { ApiResponse } from '@/types'
import { get, put } from '@/utils/request'
import { isApiResponse } from '@/utils/apiResponse'

export interface SecuritySettings {
  email_allowed_suffixes: string
  email_denied_suffixes: string
  email_denied_message: string
  denied_ips: string
  common_email_suffixes: string
  frequency_1m: number
  frequency_5m: number
  frequency_10m: number
  frequency_1h: number
  frequency_5h: number
  frequency_10h: number
  frequency_24h: number
  config_version: string
}

/** 七档配置字段及中文单位，表单和校验共用，窗口详情统一按分钟记录。 */
export const SECURITY_FREQUENCY_FIELDS = [
  ['frequency_1m', '1分钟频率'], ['frequency_5m', '5分钟频率'], ['frequency_10m', '10分钟频率'],
  ['frequency_1h', '1小时频率'], ['frequency_5h', '5小时频率'], ['frequency_10h', '10小时频率'], ['frequency_24h', '24小时频率'],
] as const

export interface SecuritySettingsResponse extends ApiResponse<SecuritySettings> {
  message: string
}

const SECURITY_SETTINGS_URL = '/api/v1/system-settings/security'

/** 校验响应信封，HTTP 200 的空值、错误字段类型和缺失消息不能作为正常业务结果。 */
export const isSecuritySettingsResponse = (result: unknown): result is SecuritySettingsResponse => isApiResponse(result)

/** 校验真实接口数据完整性，缺失字段不能默认为空并用于保存。 */
export const isSecuritySettings = (data: unknown): data is SecuritySettings => {
  if (!data || typeof data !== 'object') return false
  const values = data as Record<string, unknown>
  return ['email_allowed_suffixes', 'email_denied_suffixes', 'email_denied_message', 'denied_ips', 'common_email_suffixes', 'config_version']
    .every((key) => typeof values[key] === 'string')
    && SECURITY_FREQUENCY_FIELDS.every(([key]) =>
      Number.isSafeInteger(values[key]) && Number(values[key]) >= 0)
}

/** 读取管理员安全设置，保留后端中文业务失败响应。 */
export const getSecuritySettings = (): Promise<SecuritySettingsResponse> =>
  get<SecuritySettingsResponse>(SECURITY_SETTINGS_URL)

/** 整组提交安全设置；显式空字符串清空对应配置，后端原子校验和保存。 */
export const updateSecuritySettings = (settings: SecuritySettings): Promise<SecuritySettingsResponse> =>
  put<SecuritySettingsResponse>(SECURITY_SETTINGS_URL, settings)
