/**
 * 代理订单明细弹窗
 *
 * 功能：
 * 1. 根据订单ID从后端获取完整明细
 * 2. 分区展示：基本信息、价格信息、人员信息、发货信息、时间信息
 * 3. 加载中显示loading，错误toast提示
 */
import { useState, useEffect } from 'react'
import { X, FileText } from 'lucide-react'
import { getAgentOrderDetail } from '@/api/distribution'
import type { AgentOrder } from '@/api/distribution'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'

/** 状态中文映射 */
const STATUS_MAP: Record<string, { label: string; className: string }> = {
  delivered: {
    label: '已发货',
    className: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  },
  settled: {
    label: '已结算',
    className: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  },
  failed: {
    label: '失败',
    className: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  },
}

/** 对接层级映射 */
const DOCK_LEVEL_MAP: Record<number, string> = {
  1: '一级对接',
  2: '二级对接',
}

/** 手续费承担方映射 */
const FEE_PAYER_MAP: Record<string, string> = {
  dealer: '分销商',
  distributor: '货主',
}

/** 来源映射 */
const SOURCE_MAP: Record<string, { label: string; className: string }> = {
  pickup: {
    label: '提货',
    className: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400',
  },
  order: {
    label: '闲鱼订单',
    className: 'bg-slate-100 text-slate-600 dark:bg-slate-700/50 dark:text-slate-300',
  },
}

interface Props {
  orderId: number
  onClose: () => void
}

/** 明细字段行 */
function DetailRow({ label, value, className }: { label: string; value: React.ReactNode; className?: string }) {
  return (
    <div className="flex items-start py-2.5 border-b border-slate-100 dark:border-slate-700/50 last:border-b-0">
      <span className="text-sm text-gray-500 dark:text-gray-400 w-28 flex-shrink-0">{label}</span>
      <span className={`text-sm font-medium text-gray-900 dark:text-gray-100 flex-1 break-all ${className || ''}`}>
        {value || '-'}
      </span>
    </div>
  )
}

export function AgentOrderDetailModal({ orderId, onClose }: Props) {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [detail, setDetail] = useState<AgentOrder | null>(null)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const result = await getAgentOrderDetail(orderId)
        if (result.success && result.data) {
          setDetail(result.data)
        } else {
          addToast({ type: 'error', message: result.message || '获取订单明细失败' })
          onClose()
        }
      } catch {
        addToast({ type: 'error', message: '获取订单明细失败' })
        onClose()
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [orderId, addToast, onClose])

  /** 利润颜色 */
  const profitColor = (profit: string) => {
    const val = parseFloat(profit)
    if (val > 0) return 'text-green-600 dark:text-green-400'
    if (val < 0) return 'text-red-600 dark:text-red-400'
    return ''
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="bg-white dark:bg-slate-800 rounded-xl shadow-2xl w-full max-w-2xl max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 弹窗头 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700">
          <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 flex items-center gap-2">
            <FileText className="w-5 h-5 text-blue-500" />
            订单明细
          </h3>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 弹窗内容 */}
        <div className="flex-1 overflow-auto px-6 py-4">
          {loading ? (
            <PageLoading />
          ) : detail ? (
            <div className="space-y-5">
              {/* 基本信息 */}
              <div>
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1.5">
                  <span className="w-1 h-4 bg-blue-500 rounded-full inline-block" />
                  基本信息
                </h4>
                <div className="bg-slate-50 dark:bg-slate-700/30 rounded-lg px-4">
                  <DetailRow label="订单ID" value={detail.id} />
                  <DetailRow label="订单号" value={<span className="font-mono">{detail.order_no}</span>} />
                  <DetailRow label="来源" value={
                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                      SOURCE_MAP[detail.source || 'order']?.className || SOURCE_MAP.order.className
                    }`}>
                      {SOURCE_MAP[detail.source || 'order']?.label || '闲鱼订单'}
                    </span>
                  } />
                  <DetailRow label="商品ID" value={<span className="font-mono">{detail.item_id}</span>} />
                  <DetailRow label="状态" value={
                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                      STATUS_MAP[detail.status]?.className || 'bg-gray-100 text-gray-600'
                    }`}>
                      {STATUS_MAP[detail.status]?.label || detail.status}
                    </span>
                  } />
                  <DetailRow label="对接层级" value={
                    <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                      detail.dock_level === 1
                        ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
                        : 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                    }`}>
                      {DOCK_LEVEL_MAP[detail.dock_level] || `L${detail.dock_level}`}
                    </span>
                  } />
                  <DetailRow label="卡券名称" value={detail.card_name} />
                  <DetailRow label="对接名称" value={detail.dock_name} />
                </div>
              </div>

              {/* 价格信息 */}
              <div>
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1.5">
                  <span className="w-1 h-4 bg-green-500 rounded-full inline-block" />
                  价格信息
                </h4>
                <div className="bg-slate-50 dark:bg-slate-700/30 rounded-lg px-4">
                  <DetailRow label="售价" value={`¥${detail.sale_price}`} />
                  <DetailRow label="对接价" value={`¥${detail.dock_price}`} />
                  <DetailRow label="卡券成本" value={detail.card_price && detail.card_price !== '0' ? `¥${detail.card_price}` : '-'} />
                  <DetailRow label="二级拿货价" value={detail.level2_cost && detail.level2_cost !== '0' ? `¥${detail.level2_cost}` : '-'} />
                  <DetailRow label="利润" value={`¥${detail.profit}`} className={profitColor(detail.profit)} />
                  <DetailRow label="手续费" value={detail.fee_amount && detail.fee_amount !== '0' ? `¥${detail.fee_amount}` : '-'} />
                  <DetailRow label="手续费承担方" value={detail.fee_payer ? (FEE_PAYER_MAP[detail.fee_payer] || detail.fee_payer) : '-'} />
                </div>
              </div>

              {/* 人员信息 */}
              <div>
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1.5">
                  <span className="w-1 h-4 bg-purple-500 rounded-full inline-block" />
                  人员信息
                </h4>
                <div className="bg-slate-50 dark:bg-slate-700/30 rounded-lg px-4">
                  <DetailRow label="分销商" value={detail.dealer_name || detail.user_name || '-'} />
                  <DetailRow label="上级用户" value={detail.upstream_name || '-'} />
                  <DetailRow label="货主" value={detail.owner_name || '-'} />
                  <DetailRow label="买家ID" value={detail.buyer_id ? <span className="font-mono">{detail.buyer_id}</span> : '-'} />
                </div>
              </div>

              {/* 发货信息 */}
              <div>
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1.5">
                  <span className="w-1 h-4 bg-orange-500 rounded-full inline-block" />
                  发货信息
                </h4>
                <div className="bg-slate-50 dark:bg-slate-700/30 rounded-lg px-4">
                  <DetailRow label="发货内容" value={
                    detail.delivery_content ? (
                      <pre className="whitespace-pre-wrap text-sm font-normal">{detail.delivery_content}</pre>
                    ) : '-'
                  } />
                  <DetailRow label="结算备注" value={detail.settle_remark} />
                </div>
              </div>

              {/* 时间信息 */}
              <div>
                <h4 className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2 flex items-center gap-1.5">
                  <span className="w-1 h-4 bg-slate-400 rounded-full inline-block" />
                  时间信息
                </h4>
                <div className="bg-slate-50 dark:bg-slate-700/30 rounded-lg px-4">
                  <DetailRow label="创建时间" value={
                    detail.created_at ? new Date(detail.created_at).toLocaleString('zh-CN') : '-'
                  } />
                  <DetailRow label="更新时间" value={
                    detail.updated_at ? new Date(detail.updated_at).toLocaleString('zh-CN') : '-'
                  } />
                </div>
              </div>
            </div>
          ) : null}
        </div>

        {/* 弹窗底部 */}
        <div className="px-6 py-3 border-t border-slate-200 dark:border-slate-700 flex justify-end">
          <button onClick={onClose} className="btn-ios-secondary">
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}
