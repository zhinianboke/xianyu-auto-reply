import { get } from '@/utils/request'
import type { Order, ApiResponse } from '@/types'

// 获取订单列表
export const getOrders = (cookieId?: string, status?: string): Promise<{ success: boolean; data: Order[] }> => {
  const params = new URLSearchParams()
  if (cookieId) params.append('cookie_id', cookieId)
  if (status) params.append('status', status)
  const queryString = params.toString()
  return get(`/api/orders${queryString ? `?${queryString}` : ''}`)
}

// 删除订单 - 后端暂未实现
export const deleteOrder = async (_id: string): Promise<ApiResponse> => {
  // 后端暂未实现 DELETE /api/orders/{id} 接口
  return { success: false, message: '后端暂未实现订单删除接口' }
}

// 批量删除订单 - 后端暂未实现
export const batchDeleteOrders = async (_ids: string[]): Promise<ApiResponse> => {
  // 后端暂未实现批量删除接口
  return { success: false, message: '后端暂未实现批量删除订单接口' }
}

// 更新订单状态 - 后端暂未实现
export const updateOrderStatus = async (_id: string, _status: string): Promise<ApiResponse> => {
  // 后端暂未实现订单状态更新接口
  return { success: false, message: '后端暂未实现订单状态更新接口' }
}
