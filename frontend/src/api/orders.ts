import { get, del, post } from '@/utils/request'
import type { Order, ApiResponse } from '@/types'

const ORDER_PREFIX = '/api/v1/orders'

// 订单详情类型
export interface OrderDetail extends Order {
  spec_name?: string
  spec_value?: string
  receiver_name?: string
  receiver_phone?: string
  receiver_address?: string
}

// 分页响应类型
export interface OrderListResponse {
  success: boolean
  data: Order[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// 手动发货响应类型
export interface ManualDeliveryResponse {
  success: boolean
  message: string
  data?: {
    order_no: string
    card_name: string
    card_type: string
  }
}

export interface FetchXianyuOrdersResponse {
  success: boolean
  message: string
  data?: {
    total_fetched: number
    new_inserted: number
    updated: number
    failed: number
    accounts_processed: number
    errors: string[]
  }
}

// 订单筛选参数
export interface OrderFilterParams {
  search?: string | null           // 搜索关键词（订单号、商品ID、买家ID）
  delivery_method?: string | null  // 发货方式：manual/auto/scheduled/none
  is_bargain?: boolean | null      // 是否小刀
  is_rated?: boolean | null        // 是否已评价
  start_date?: string | null       // 开始日期：YYYY-MM-DD
  end_date?: string | null         // 结束日期：YYYY-MM-DD
  delivery_send_status?: string | null  // 关联消息日志发送状态：success/failed/unknown
}

// 获取订单列表（分页）
export const getOrders = (
  cookieId?: string,
  status?: string,
  page: number = 1,
  pageSize: number = 20,
  filters?: OrderFilterParams
): Promise<OrderListResponse> => {
  const params = new URLSearchParams()
  if (cookieId) params.append('cookie_id', cookieId)
  if (status) params.append('status', status)
  params.append('page', String(page))
  params.append('page_size', String(pageSize))
  
  if (filters) {
    if (filters.search) {
      params.append('search', filters.search)
    }
    if (filters.delivery_method !== null && filters.delivery_method !== undefined) {
      params.append('delivery_method', filters.delivery_method)
    }
    if (filters.is_bargain !== null && filters.is_bargain !== undefined) {
      params.append('is_bargain', String(filters.is_bargain))
    }
    if (filters.is_rated !== null && filters.is_rated !== undefined) {
      params.append('is_rated', String(filters.is_rated))
    }
    if (filters.start_date) {
      params.append('start_date', filters.start_date)
    }
    if (filters.end_date) {
      params.append('end_date', filters.end_date)
    }
    if (filters.delivery_send_status !== null && filters.delivery_send_status !== undefined && filters.delivery_send_status !== '') {
      params.append('delivery_send_status', filters.delivery_send_status)
    }
  }
  
  return get(`${ORDER_PREFIX}?${params.toString()}`)
}

// 获取订单详情
export const getOrderDetail = (orderNo: string, refresh = false): Promise<{ success: boolean; data: OrderDetail }> => {
  return get(`${ORDER_PREFIX}/${orderNo}?refresh=${refresh}`)
}

// 删除订单
export const deleteOrder = (id: string): Promise<ApiResponse> => {
  return del(`${ORDER_PREFIX}/${id}`)
}

// 手动发货
export const manualDelivery = (orderNo: string): Promise<ManualDeliveryResponse> => {
  return post(`${ORDER_PREFIX}/manual-delivery`, { order_no: orderNo })
}

// 获取闲鱼订单并同步到数据库（单独设置10分钟超时）
export const noLogisticsDelivery = (orderNo: string): Promise<ManualDeliveryResponse> => {
  return post(`${ORDER_PREFIX}/no-logistics-delivery`, { order_no: orderNo })
}

export const cancelOrder = (orderNo: string): Promise<ApiResponse> => {
  return post(`${ORDER_PREFIX}/cancel`, { order_no: orderNo })
}

export const fetchXianyuOrders = (cookieId?: string): Promise<FetchXianyuOrdersResponse> => {
  return post(`${ORDER_PREFIX}/fetch-xianyu`, { cookie_id: cookieId || null }, { timeout: 600000 })
}

// 批量删除订单
export const batchDeleteOrders = (ids: number[]): Promise<ApiResponse> => {
  return post(`${ORDER_PREFIX}/batch-delete`, { ids })
}

// 更新订单状态 - 后端暂未实现
export const updateOrderStatus = async (_id: string, _status: string): Promise<ApiResponse> => {
  return { success: false, message: '后端暂未实现订单状态更新接口' }
}
