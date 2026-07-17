/**
 * 账号密码登录方式设置接口。
 *
 * 功能：
 * 1. 校验账号密码登录方式枚举值
 * 2. 独立保存登录方式，避免提交系统设置页的其他未保存内容
 */
import { put } from '@/utils/request'
import type { ApiResponse, PasswordLoginMode } from '@/types'

const PASSWORD_LOGIN_MODE_URL = '/api/v1/system-settings/password_login.mode'
const PASSWORD_LOGIN_MODES: PasswordLoginMode[] = ['auto', 'protocol', 'browser']

export const normalizePasswordLoginMode = (value: unknown): PasswordLoginMode => {
  return PASSWORD_LOGIN_MODES.includes(value as PasswordLoginMode)
    ? value as PasswordLoginMode
    : 'auto'
}

export const updatePasswordLoginMode = (
  mode: PasswordLoginMode,
): Promise<ApiResponse> => {
  return put<ApiResponse>(PASSWORD_LOGIN_MODE_URL, { value: mode })
}
