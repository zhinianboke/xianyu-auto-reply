import { get, post, put, del } from '@/utils/request'
import type { ApiResponse, DeliveryRule } from '@/types'

// 获取发货规则列表
export const getDeliveryRules = async (): Promise<{ success: boolean; data?: DeliveryRule[] }> => {
  const result = await get<DeliveryRule[] | { rules?: DeliveryRule[] }>('/delivery-rules')
  // 后端可能返回数组或 { rules: [...] } 格式
  const data = Array.isArray(result) ? result : (result.rules || [])
  return { success: true, data }
}

// 添加发货规则
export const addDeliveryRule = (data: Partial<DeliveryRule>): Promise<ApiResponse> => {
  return post('/delivery-rules', data)
}

// 更新发货规则
export const updateDeliveryRule = (ruleId: string, data: Partial<DeliveryRule>): Promise<ApiResponse> => {
  return put(`/delivery-rules/${ruleId}`, data)
}

// 删除发货规则
export const deleteDeliveryRule = (ruleId: string): Promise<ApiResponse> => {
  return del(`/delivery-rules/${ruleId}`)
}

// 获取账号的发货规则
export const getDeliveryRulesByAccount = (accountId: string): Promise<DeliveryRule[]> => {
  return get(`/delivery-rules/${accountId}`)
}
