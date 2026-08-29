import axios from 'axios'
import type { ApiResponse } from '@/types'

/** FastAPI 校验失败（422）的单条明细结构。 */
interface ValidationDetailItem {
  loc?: Array<string | number>
  msg?: string
}

/**
 * 把 FastAPI 的 422 校验明细转成中文提示。
 *
 * FastAPI 校验失败时 detail 是数组（如 [{loc:["body","quantity"],msg:"..."}]），
 * 直接展示会变成英文的 "Request failed with status code 422"，这里改为指出具体字段。
 *
 * @param detail 响应体里的 detail 字段。
 * @returns 中文提示，detail 不是校验明细数组时返回空串。
 */
function messageFromValidationDetail(detail: unknown): string {
  if (!Array.isArray(detail) || !detail.length) return ''
  const fields = (detail as ValidationDetailItem[])
    .map((item) => {
      const path = (item.loc || []).filter((part) => part !== 'body' && part !== 'query')
      const field = path.length ? path.join('.') : ''
      return field ? `${field}（${item.msg || '取值不符合要求'}）` : item.msg || ''
    })
    .filter(Boolean)
  if (!fields.length) return ''
  return `提交内容校验失败：${fields.join('；')}`
}

export function getApiErrorMessage(error: unknown, fallback: string): string {
  if (axios.isAxiosError(error)) {
    const responseData = error.response?.data as ApiResponse | string | undefined

    if (typeof responseData === 'string' && responseData.trim()) {
      return responseData
    }

    if (responseData && typeof responseData === 'object') {
      const message = responseData.message || responseData.msg || responseData.detail
      if (typeof message === 'string' && message.trim()) {
        return message
      }
      const validationMessage = messageFromValidationDetail(responseData.detail)
      if (validationMessage) {
        return validationMessage
      }
    }

    if (error.message?.trim()) {
      return error.message
    }
  }

  if (error instanceof Error && error.message.trim()) {
    return error.message
  }

  return fallback
}
