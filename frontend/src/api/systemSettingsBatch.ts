/**
 * 系统设置批量保存接口。
 *
 * 同一模块的字段通过一个请求交给后端事务保存，避免出现部分字段已生效、
 * 其余字段保存失败的中间状态。
 */
import type { ApiResponse, SystemSettings } from '@/types'
import { put } from '@/utils/request'

const SYSTEM_SETTINGS_BATCH_URL = '/api/v1/system-settings/batch'
const READONLY_SYSTEM_SETTING_KEYS = ['runtime.is_exe_mode']
const INDEPENDENT_SYSTEM_SETTING_KEYS = [
  'password_login.mode',
  'captcha.slider_mode',
  'token.api_mode',
  'token.remote_url',
  'token.remote_secret_key',
]

const serializeSystemSettingValue = (value: unknown): string => {
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') return String(value)
  return String(value ?? '')
}

/** 在同一事务中保存一组系统设置。 */
export const updateSystemSettingsBatch = async (
  data: Partial<SystemSettings>,
): Promise<ApiResponse> => {
  const settings = Object.fromEntries(
    Object.entries(data)
      .filter(([key]) => !READONLY_SYSTEM_SETTING_KEYS.includes(key))
      .map(([key, value]) => [key, { value: serializeSystemSettingValue(value) }]),
  )
  if (!Object.keys(settings).length) return { success: true, message: '没有需要保存的设置' }
  return put<ApiResponse>(SYSTEM_SETTINGS_BATCH_URL, { settings })
}

/** 保存通用设置；认证方式等独立模块由各自保存入口提交。 */
export const updateSystemSettings = async (
  data: Partial<SystemSettings>,
): Promise<ApiResponse> => {
  const filtered = Object.fromEntries(
    Object.entries(data).filter(([key]) => !INDEPENDENT_SYSTEM_SETTING_KEYS.includes(key)),
  ) as Partial<SystemSettings>
  return updateSystemSettingsBatch(filtered)
}
