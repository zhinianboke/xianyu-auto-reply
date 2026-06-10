/**
 * 在线聊天工作台 - 右侧客户订单面板
 *
 * 展示当前会话对方买家的近期订单，并提供查看详情、取消订单、无物流发货、发卡发货等操作。
 * 仅负责渲染与回调透传，数据与业务逻辑由父组件 ChatNew 维护。
 */
import { Eye, Loader2, Package, RefreshCw, Truck, X } from 'lucide-react'
import type { CustomerOrder } from '@/api/chatNew'
import { CANCELLABLE_STATUSES, SHIPPABLE_STATUSES, getOrderStatusMeta } from './orderStatus'

interface CustomerOrdersPanelProps {
  /** 当前选中的会话ID，为空时展示占位提示 */
  activeCid: string
  /** 客户订单列表 */
  orders: CustomerOrder[]
  /** 订单列表加载中 */
  loading: boolean
  /** 正在发卡发货的订单号 */
  deliveringOrderNo: string
  /** 正在无物流发货的订单号 */
  confirmingOrderNo: string
  /** 正在取消的订单号 */
  cancellingOrderNo: string
  /** 订单详情加载中 */
  loadingOrderDetail: boolean
  /** 同步并刷新订单 */
  onSync: () => void
  /** 查看订单详情 */
  onViewDetail: (orderNo: string) => void
  /** 取消订单 */
  onCancel: (orderNo: string) => void
  /** 无物流发货 */
  onNoLogistics: (orderNo: string) => void
  /** 发卡发货 */
  onDeliver: (orderNo: string) => void
}

export function CustomerOrdersPanel({
  activeCid,
  orders,
  loading,
  deliveringOrderNo,
  confirmingOrderNo,
  cancellingOrderNo,
  loadingOrderDetail,
  onSync,
  onViewDetail,
  onCancel,
  onNoLogistics,
  onDeliver,
}: CustomerOrdersPanelProps) {
  const anyActionRunning = !!deliveringOrderNo || !!confirmingOrderNo
  return (
    <div className="basis-3/5 min-h-0 bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col">
      <div className="p-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Package className="w-4 h-4 text-blue-500" />
          <span className="font-medium text-sm text-gray-700 dark:text-gray-300">客户订单</span>
          {orders.length > 0 && <span className="text-xs text-gray-400">({orders.length})</span>}
        </div>
        <button onClick={onSync} disabled={!activeCid || loading} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded disabled:opacity-40" title="同步并刷新订单">
          <RefreshCw className={`w-4 h-4 text-gray-500 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-2">
        {!activeCid ? (
          <p className="text-center text-sm text-gray-400 py-10">选择会话后查看该客户订单</p>
        ) : loading && orders.length === 0 ? (
          <div className="flex justify-center py-10"><Loader2 className="w-5 h-5 animate-spin text-blue-500" /></div>
        ) : orders.length === 0 ? (
          <p className="text-center text-sm text-gray-400 py-10">暂未匹配到该客户订单</p>
        ) : orders.map((order) => (
          <div key={order.order_no} className="rounded-lg border border-gray-200 dark:border-gray-700 p-2.5 text-xs">
            <div className="font-medium text-gray-800 dark:text-gray-200 line-clamp-2">{order.item_title}</div>
            <div className="mt-1 flex justify-between items-center text-gray-500"><span>¥{order.amount || '--'} × {order.quantity}</span><span className={`px-1.5 py-0.5 rounded ${getOrderStatusMeta(order.status).className}`}>{getOrderStatusMeta(order.status).label}</span></div>
            <div className="mt-1 text-gray-400 truncate" title={order.order_no}>订单：{order.order_no}</div>
            {order.delivery_fail_reason && <div className="mt-1 text-red-500 line-clamp-2">{order.delivery_fail_reason}</div>}
            <div className="mt-2 grid grid-cols-2 gap-1.5">
              <button onClick={() => onViewDetail(order.order_no)} disabled={loadingOrderDetail} className="flex items-center justify-center gap-1 py-1.5 rounded border border-gray-200 text-gray-600 hover:bg-gray-50 disabled:opacity-40">
                <Eye className="w-3.5 h-3.5" />
                订单详情
              </button>
              {CANCELLABLE_STATUSES.includes(order.status) && (
                <button onClick={() => onCancel(order.order_no)} disabled={!!cancellingOrderNo || anyActionRunning} className="flex items-center justify-center gap-1 py-1.5 rounded border border-red-200 text-red-500 hover:bg-red-50 disabled:opacity-40">
                  {cancellingOrderNo === order.order_no ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <X className="w-3.5 h-3.5" />}
                  取消订单
                </button>
              )}
            </div>
            {SHIPPABLE_STATUSES.includes(order.status) && (
              <button onClick={() => onNoLogistics(order.order_no)} disabled={anyActionRunning} className="mt-2 w-full flex items-center justify-center gap-1 py-1.5 rounded bg-blue-500 text-white hover:bg-blue-600 disabled:bg-gray-300 disabled:cursor-not-allowed">
                {confirmingOrderNo === order.order_no ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Truck className="w-3.5 h-3.5" />}
                无物流发货
              </button>
            )}
            {SHIPPABLE_STATUSES.includes(order.status) && (
              <button onClick={() => onDeliver(order.order_no)} disabled={anyActionRunning} className="mt-1.5 w-full flex items-center justify-center gap-1 py-1.5 rounded border border-blue-300 text-blue-600 hover:bg-blue-50 disabled:bg-gray-100 disabled:text-gray-400 disabled:cursor-not-allowed">
                {deliveringOrderNo === order.order_no ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Truck className="w-3.5 h-3.5" />}
                发卡发货
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
