/**
 * 同意后发货 - 提货页公开接口（无需登录）
 *
 * 说明：
 * - 提货页无需认证，使用原生 fetch 绕过 axios 的 token / 401 拦截。
 * - 后端统一返回 { success, message, data }，一律 HTTP 200，业务错误通过 success 传递。
 * - 响应类型复用全局 ApiResponse<T>，不再另立一套。
 */
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/agree-pickup'

export interface PickupOrderView {
  order_no: string
  amount: string | null
  quantity: number | null
  spec_name: string | null
  spec_value: string | null
  item_id: string | null
  item_title: string | null
  item_url: string | null
  already_agreed: boolean
  content: string | null
}

export interface PickupAgreeResult {
  order_no: string
  content: string | null
  already_agreed?: boolean
}

/**
 * 提货页加载：按订单号 + 订单id 校验并返回展示信息
 */
export async function queryPickupOrder(
  orderNo: string,
  orderId: string,
): Promise<ApiResponse<PickupOrderView>> {
  const params = new URLSearchParams({ orderNo, orderId })
  const response = await fetch(`${PREFIX}/order?${params.toString()}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  })
  return response.json()
}

/**
 * 买家点击「同意」：触发真实发货并返回卡券内容
 */
export async function agreePickup(
  orderNo: string,
  orderId: string,
): Promise<ApiResponse<PickupAgreeResult>> {
  const response = await fetch(`${PREFIX}/agree`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ order_no: orderNo, order_id: orderId }),
  })
  return response.json()
}
