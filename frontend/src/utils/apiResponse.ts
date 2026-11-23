/** 校验统一业务响应，空响应或非法字段必须向用户明确报告。 */
import type { ApiResponse } from '@/types'

export const isApiResponse = (result: unknown): result is ApiResponse => {
  if (!result || typeof result !== 'object' || Array.isArray(result)) return false
  const values = result as Record<string, unknown>
  return typeof values.success === 'boolean' && Number.isInteger(values.code)
    && typeof values.message === 'string' && values.message.trim().length > 0
    && Object.prototype.hasOwnProperty.call(values, 'data')
    && (values.success || values.data === null)
}
