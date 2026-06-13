/**
 * 在线聊天工作台 - 订单状态展示映射
 *
 * 集中维护订单状态码到中文标签与样式的映射，供订单面板与详情弹窗共用，避免重复实现。
 */

/** 订单状态 -> 中文标签与色块样式 */
export const ORDER_STATUS_META: Record<string, { label: string; className: string }> = {
  pending_payment: { label: '待付款', className: 'bg-orange-50 text-orange-600' },
  pending_ship: { label: '待发货', className: 'bg-blue-50 text-blue-600' },
  pending: { label: '待发货', className: 'bg-blue-50 text-blue-600' },
  paid: { label: '待发货', className: 'bg-blue-50 text-blue-600' },
  shipped: { label: '已发货', className: 'bg-green-50 text-green-600' },
  completed: { label: '交易成功', className: 'bg-green-50 text-green-600' },
  cancelled: { label: '交易关闭', className: 'bg-gray-100 text-gray-500' },
  closed: { label: '交易关闭', className: 'bg-gray-100 text-gray-500' },
  refunding: { label: '退款中', className: 'bg-orange-50 text-orange-600' },
  refunded: { label: '已退款', className: 'bg-gray-100 text-gray-500' },
}

/** 取订单状态的展示信息，未知状态回退为灰色标签 */
export const getOrderStatusMeta = (status: string) =>
  ORDER_STATUS_META[status] || { label: status || '未知状态', className: 'bg-gray-100 text-gray-500' }

/** 处于「待发货」语义、可执行发货/取消操作的状态集合 */
export const SHIPPABLE_STATUSES = ['pending_ship', 'pending', 'paid', '待发货']

/** 可执行取消的状态集合（含待付款） */
export const CANCELLABLE_STATUSES = ['pending_payment', 'pending_ship', 'pending', 'paid', '待付款', '待发货']

/** 发货方式 -> 中文标签 */
export const DELIVERY_METHOD_LABELS: Record<string, string> = {
  manual: '手动发货',
  auto: '自动发货',
  scheduled: '定时发货',
}

/** 取发货方式中文标签；未查询到发货方式时返回空字符串（不显示「未发货」） */
export const getDeliveryMethodLabel = (method?: string | null): string =>
  method ? (DELIVERY_METHOD_LABELS[method] || method) : ''
