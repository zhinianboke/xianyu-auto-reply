/**
 * 在线聊天工作台 - 订单详情弹窗
 *
 * 展示单个订单的商品、金额、买家与收货信息。
 * 按项目规范：弹窗仅可通过右上角关闭按钮关闭，禁止点击遮罩关闭。
 */
import { X } from 'lucide-react'
import type { OrderDetail } from '@/api/orders'
import { getOrderStatusMeta, getDeliveryMethodLabel } from './orderStatus'

interface OrderDetailModalProps {
  /** 订单详情，为 null 时不渲染 */
  order: OrderDetail | null
  /** 买家昵称兜底值（订单无昵称时使用当前会话对方昵称） */
  fallbackBuyerNick?: string
  /** 关闭弹窗 */
  onClose: () => void
}

export function OrderDetailModal({ order, fallbackBuyerNick, onClose }: OrderDetailModalProps) {
  if (!order) return null
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-lg rounded-xl bg-white dark:bg-gray-800 shadow-xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h3 className="font-semibold text-gray-800 dark:text-gray-100">订单详情</h3>
            <p className="mt-0.5 text-xs text-gray-400">{order.order_id}</p>
          </div>
          <button onClick={onClose} className="p-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700"><X className="w-5 h-5" /></button>
        </div>
        <div className="p-5 space-y-4 text-sm">
          <div className="rounded-lg bg-gray-50 dark:bg-gray-700/50 p-3">
            <div className="font-medium text-gray-800 dark:text-gray-100">{order.item_title || order.item_id}</div>
            <div className="mt-2 grid grid-cols-2 gap-2 text-gray-500">
              <span>实收：<b className="text-red-500">¥{order.amount}</b></span>
              <span>数量：{order.quantity}</span>
              <span>规格：{order.sku_info || '无'}</span>
              <span>状态：{getOrderStatusMeta(order.status).label}</span>
            </div>
          </div>
          <div className="grid grid-cols-[88px_1fr] gap-x-3 gap-y-2 text-gray-600 dark:text-gray-300">
            <span className="text-gray-400">买家昵称</span><span>{order.buyer_fish_nick || fallbackBuyerNick || '未获取'}</span>
            <span className="text-gray-400">买家ID</span><span className="break-all">{order.buyer_id || '未获取'}</span>
            <span className="text-gray-400">下单时间</span><span>{order.placed_at ? new Date(order.placed_at).toLocaleString() : '未获取'}</span>
            <span className="text-gray-400">收货人</span><span>{order.receiver_name || '未获取'}</span>
            <span className="text-gray-400">联系电话</span><span>{order.receiver_phone || '未获取'}</span>
            <span className="text-gray-400">收货地址</span><span className="break-words">{order.receiver_address || '未获取'}</span>
            <span className="text-gray-400">发货方式</span><span>{getDeliveryMethodLabel(order.delivery_method)}</span>
          </div>
        </div>
      </div>
    </div>
  )
}
