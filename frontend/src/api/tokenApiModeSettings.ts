/**
 * Token 获取方式设置接口。
 *
 * 功能：
 * 1. 规范化 Token 获取方式
 * 2. 独立保存设置，避免提交页面其他未保存内容
 */
import { put } from '@/utils/request'
import type { ApiResponse, TokenApiMode } from '@/types'

const TOKEN_API_MODE_URL = '/api/v1/system-settings/token.api_mode'
const TOKEN_API_MODES: TokenApiMode[] = ['miniapp', 'web']

export const normalizeTokenApiMode = (value: unknown): TokenApiMode => {
  return TOKEN_API_MODES.includes(value as TokenApiMode)
    ? value as TokenApiMode
    : 'miniapp'
}

export const updateTokenApiMode = (mode: TokenApiMode): Promise<ApiResponse> => {
  return put<ApiResponse>(TOKEN_API_MODE_URL, { value: mode })
}
