/**
 * 卡密推送配置接口。
 *
 * 功能：
 * 1. 从当前用户的个人设置中读取卡密提交与状态查询 URL
 * 2. 保存当前用户的卡密推送配置
 */
import type { ApiResponse } from '@/types'
import { getApiErrorMessage } from '@/utils/apiError'
import { get, put } from '@/utils/request'

const CARD_SUBMIT_URL_KEY = 'card_push.submit_url'
const CARD_STATUS_QUERY_URL_KEY = 'card_push.status_query_url'

interface UserSettingValueResponse {
  success: boolean
  code?: number
  message?: string
  value?: string
}

export interface CardPushSettings {
  submitUrl: string
  statusQueryUrl: string
}

/** 读取当前用户的卡密推送配置。 */
export async function getCardPushSettings(): Promise<ApiResponse<CardPushSettings>> {
  return Promise.all([
    get<UserSettingValueResponse>(`/api/v1/user-settings/${CARD_SUBMIT_URL_KEY}`),
    get<UserSettingValueResponse>(`/api/v1/user-settings/${CARD_STATUS_QUERY_URL_KEY}`),
  ]).then(([submitResult, statusResult]) => {
    if (!submitResult.success || !statusResult.success) {
      return {
        success: false,
        code: submitResult.code || statusResult.code || 40001,
        message: submitResult.message || statusResult.message || '卡密推送配置加载失败',
      }
    }

    return {
      success: true,
      code: 200,
      message: '卡密推送配置加载成功',
      data: {
        submitUrl: submitResult.value || '',
        statusQueryUrl: statusResult.value || '',
      },
    }
  }).catch((error: unknown) => ({
    success: false,
    code: 40001,
    message: getApiErrorMessage(error, '卡密推送配置加载失败'),
  }))
}

/** 保存当前用户的卡密推送配置。 */
export async function saveCardPushSettings(settings: CardPushSettings): Promise<ApiResponse> {
  return Promise.all([
    put<ApiResponse>(`/api/v1/user-settings/${CARD_SUBMIT_URL_KEY}`, {
      value: settings.submitUrl,
      description: '卡密提交URL',
    }),
    put<ApiResponse>(`/api/v1/user-settings/${CARD_STATUS_QUERY_URL_KEY}`, {
      value: settings.statusQueryUrl,
      description: '卡密状态查询URL',
    }),
  ]).then(([submitResult, statusResult]) => {
    if (!submitResult.success || !statusResult.success) {
      return {
        success: false,
        code: submitResult.code || statusResult.code || 40001,
        message: submitResult.message || statusResult.message || '卡密推送配置保存失败',
      }
    }

    return {
      success: true,
      code: 200,
      message: '卡密推送配置已保存',
    }
  }).catch((error: unknown) => ({
    success: false,
    code: 40001,
    message: getApiErrorMessage(error, '卡密推送配置保存失败'),
  }))
}
