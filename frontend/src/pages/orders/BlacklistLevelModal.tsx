/**
 * 拉黑级别选择弹窗
 * 
 * 用户点击"一键拉黑"后弹出，选择拉黑级别：
 * - 商品级拉黑：绑定到具体商品（account_id + item_id）
 * - 账户级拉黑：绑定到具体账号（account_id）
 * - 用户级拉黑：不绑定账号和商品，全局拉黑
 */
import { useState } from 'react'
import { X, Package, User, Users } from 'lucide-react'
import { createPersonalBlacklist } from '@/api/blacklist'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/request'

export type BlacklistLevel = 'item' | 'account' | 'user'

interface OrderInfo {
  buyer_id: string
  cookie_id: string
  item_id: string
}

interface Props {
  orders: OrderInfo[]
  onClose: () => void
  onSuccess: () => void
}

export function BlacklistLevelModal({ orders, onClose, onSuccess }: Props) {
  const { addToast } = useUIStore()
  const [submitting, setSubmitting] = useState(false)
  const [reason, setReason] = useState('')

  const buyerCount = new Set(orders.map((o) => o.buyer_id)).size

  const handleSubmit = async (level: BlacklistLevel) => {
    setSubmitting(true)
    try {
      // 按照不同级别组织数据
      // 去重：同一个 buyer_id 在同一级别下只需要一条记录
      let successCount = 0
      let failCount = 0

      if (level === 'user') {
        // 用户级：不绑定账号和商品
        const buyerIds = [...new Set(orders.map((o) => o.buyer_id))].join(',')
        const res = await createPersonalBlacklist({
          buyer_ids: buyerIds,
          reason: reason || '订单页一键拉黑（用户级）',
          is_enabled: true,
        })
        if (res.success) successCount = buyerCount
      } else if (level === 'account') {
        // 账户级：绑定账号，不绑定商品
        // 按 account_id 分组，buyer_id 去重
        const grouped: Record<string, string[]> = {}
        for (const order of orders) {
          if (!grouped[order.cookie_id]) grouped[order.cookie_id] = []
          if (!grouped[order.cookie_id].includes(order.buyer_id)) {
            grouped[order.cookie_id].push(order.buyer_id)
          }
        }
        for (const [accountId, buyerIds] of Object.entries(grouped)) {
          try {
            const res = await createPersonalBlacklist({
              account_id: accountId,
              buyer_ids: buyerIds.join(','),
              reason: reason || '订单页一键拉黑（账户级）',
              is_enabled: true,
            })
            if (res.success) successCount += buyerIds.length
          } catch {
            failCount += buyerIds.length
          }
        }
      } else {
        // 商品级：绑定账号和商品
        // 按 account_id + item_id + buyer_id 去重
        const grouped: Record<string, { accountId: string; itemId: string; buyerIds: string[] }> = {}
        for (const order of orders) {
          const groupKey = `${order.cookie_id}||${order.item_id}`
          if (!grouped[groupKey]) grouped[groupKey] = { accountId: order.cookie_id, itemId: order.item_id, buyerIds: [] }
          if (!grouped[groupKey].buyerIds.includes(order.buyer_id)) {
            grouped[groupKey].buyerIds.push(order.buyer_id)
          }
        }
        for (const group of Object.values(grouped)) {
          try {
            const res = await createPersonalBlacklist({
              account_id: group.accountId,
              buyer_ids: group.buyerIds.join(','),
              item_id: group.itemId,
              reason: reason || '订单页一键拉黑（商品级）',
              is_enabled: true,
            })
            if (res.success) successCount += group.buyerIds.length
          } catch {
            failCount += group.buyerIds.length
          }
        }
      }

      if (successCount > 0) {
        const msg = failCount > 0
          ? `成功拉黑 ${successCount} 个买家，${failCount} 个失败`
          : `成功拉黑 ${successCount} 个买家`
        addToast({ type: failCount > 0 ? 'warning' : 'success', message: msg })
        onSuccess()
      } else {
        addToast({ type: 'error', message: '拉黑失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '拉黑失败') })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-md mx-4">
        {/* 头部 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700">
          <h3 className="text-lg font-medium text-slate-800 dark:text-slate-100">
            一键拉黑（{buyerCount} 个买家）
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 内容 */}
        <div className="px-6 py-4 space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            请选择拉黑级别：
          </p>

          {/* 拉黑原因 */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              拉黑原因（可选）
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="输入拉黑原因"
              className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* 三个级别按钮 */}
          <div className="space-y-3">
            <button
              onClick={() => handleSubmit('item')}
              disabled={submitting}
              className="w-full flex items-center gap-3 px-4 py-3 border border-slate-200 dark:border-slate-600 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 hover:border-blue-300 dark:hover:border-blue-700 transition-colors disabled:opacity-50"
            >
              <Package className="w-5 h-5 text-blue-500 flex-shrink-0" />
              <div className="text-left">
                <div className="text-sm font-medium text-slate-800 dark:text-slate-100">商品级拉黑</div>
                <div className="text-xs text-slate-500 dark:text-slate-400">仅在对应商品下生效（绑定账号+商品）</div>
              </div>
            </button>

            <button
              onClick={() => handleSubmit('account')}
              disabled={submitting}
              className="w-full flex items-center gap-3 px-4 py-3 border border-slate-200 dark:border-slate-600 rounded-lg hover:bg-orange-50 dark:hover:bg-orange-900/20 hover:border-orange-300 dark:hover:border-orange-700 transition-colors disabled:opacity-50"
            >
              <User className="w-5 h-5 text-orange-500 flex-shrink-0" />
              <div className="text-left">
                <div className="text-sm font-medium text-slate-800 dark:text-slate-100">账户级拉黑</div>
                <div className="text-xs text-slate-500 dark:text-slate-400">在对应账号下所有商品生效（绑定账号）</div>
              </div>
            </button>

            <button
              onClick={() => handleSubmit('user')}
              disabled={submitting}
              className="w-full flex items-center gap-3 px-4 py-3 border border-slate-200 dark:border-slate-600 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 hover:border-red-300 dark:hover:border-red-700 transition-colors disabled:opacity-50"
            >
              <Users className="w-5 h-5 text-red-500 flex-shrink-0" />
              <div className="text-left">
                <div className="text-sm font-medium text-slate-800 dark:text-slate-100">用户级拉黑</div>
                <div className="text-xs text-slate-500 dark:text-slate-400">全局生效，不绑定任何账号和商品</div>
              </div>
            </button>
          </div>
        </div>

        {/* 底部 */}
        <div className="flex items-center justify-end px-6 py-4 border-t border-slate-200 dark:border-slate-700">
          <button
            onClick={onClose}
            disabled={submitting}
            className="px-4 py-2 text-sm text-slate-600 dark:text-slate-300 border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
          >
            取消
          </button>
        </div>
      </div>
    </div>
  )
}
