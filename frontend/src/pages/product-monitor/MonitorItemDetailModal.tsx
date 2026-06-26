/**
 * 采集商品详情弹窗
 *
 * 功能：
 * 1. 根据采集商品主键加载数据库中采集到的完整信息
 * 2. 以结构化方式展示商品字段、私信/下单状态、卖家补全结果
 * 3. 附带展示数据库中存储的原始详情数据（detail_json）与搜索原始数据（raw_json）
 */
import { useEffect, useState } from 'react'
import { Loader2, X } from 'lucide-react'
import {
  getListingMonitorItemDetail,
  type ListingMonitorItemDetail,
} from '@/api/listingMonitor'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

interface MonitorItemDetailModalProps {
  itemPk: number
  onClose: () => void
}

// 私信状态文案
const dmStatusText = (item: ListingMonitorItemDetail): string => {
  if (item.dm_status === 'failed') return `私信失败（重试 ${item.dm_attempts || 0}/3）`
  if (item.is_dm_sent) return item.dm_status === 'success' ? '私信成功' : '已发待确认'
  return '未私信'
}

// 下单状态文案
const orderStatusText = (item: ListingMonitorItemDetail): string => {
  if (item.order_status === 'duplicate') return '重复跳过（其他任务已下单）'
  if (item.is_ordered) return '已下单'
  if (item.order_status === 'failed') return `下单失败（重试 ${item.order_attempts || 0}/3）`
  return '未下单'
}

const formatTime = (value?: string | null): string =>
  value ? new Date(value).toLocaleString('zh-CN') : '-'

export function MonitorItemDetailModal({ itemPk, onClose }: MonitorItemDetailModalProps) {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [item, setItem] = useState<ListingMonitorItemDetail | null>(null)

  useEffect(() => {
    const load = async () => {
      try {
        setLoading(true)
        const result = await getListingMonitorItemDetail(itemPk)
        if (!result.success || !result.data?.item) {
          addToast({ type: 'error', message: result.message || '加载商品详情失败' })
          return
        }
        setItem(result.data.item)
      } catch (error) {
        addToast({ type: 'error', message: getApiErrorMessage(error, '加载商品详情失败') })
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [itemPk, addToast])

  const rows: { label: string; value: React.ReactNode }[] = item
    ? [
        { label: '商品ID', value: item.item_id || '-' },
        { label: '商品标题', value: item.title || '-' },
        { label: '价格', value: item.price != null ? `¥${item.price}` : '-' },
        { label: '地区', value: item.area || '-' },
        { label: '想要数', value: item.want_count || '-' },
        { label: '营销标签', value: item.tags || '-' },
        { label: '发布时间', value: formatTime(item.publish_time) },
        { label: '卖家昵称', value: item.seller_nick || '-' },
        { label: '卖家真实ID', value: item.seller_user_id || '-' },
        { label: '卖家ID（搜索）', value: item.seller_id || '-' },
        {
          label: '卖家ID补全',
          value:
            item.seller_fill_status === 'failed'
              ? `失败：${item.seller_fill_fail_reason || '未知原因'}`
              : item.seller_user_id
                ? '已补全'
                : '待补全',
        },
        { label: '私信状态', value: dmStatusText(item) },
        { label: '私信账号', value: item.dm_account_id || '-' },
        { label: '私信会话ID', value: item.dm_chat_id || '-' },
        { label: '私信原因', value: item.dm_fail_reason || '-' },
        { label: '下单状态', value: orderStatusText(item) },
        { label: '订单ID', value: item.order_id || '-' },
        { label: '下单账号', value: item.order_account_id || '-' },
        { label: '下单时间', value: formatTime(item.ordered_at) },
        { label: '下单失败原因', value: item.order_fail_reason || '-' },
        { label: '采集时间', value: formatTime(item.created_at) },
        { label: '最近采集', value: formatTime(item.last_seen_at) },
      ]
    : []

  return (
    <div className="modal-overlay">
      <div className="modal-content max-w-3xl">
        <div className="modal-header">
          <h2 className="modal-title">采集商品详情</h2>
          <button className="modal-close" onClick={onClose}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="modal-body">
          {loading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
              <span className="ml-2 text-slate-500 dark:text-slate-400">正在加载商品详情...</span>
            </div>
          ) : !item ? (
            <div className="py-16 text-center text-slate-400">未查询到商品信息</div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-start gap-4">
                {item.pic_url ? (
                  <img src={item.pic_url} alt="" className="w-24 h-24 object-cover rounded flex-shrink-0" />
                ) : (
                  <div className="w-24 h-24 rounded bg-slate-100 dark:bg-slate-700 flex-shrink-0" />
                )}
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-slate-800 dark:text-slate-100 break-words">{item.title || '-'}</p>
                  <p className="mt-1 text-red-600 dark:text-red-400">{item.price != null ? `¥${item.price}` : '-'}</p>
                  <a
                    href={`https://www.goofish.com/item?id=${item.item_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-1 inline-block text-sm text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    在闲鱼打开
                  </a>
                </div>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-2">
                {rows.map((row) => (
                  <div key={row.label} className="flex text-sm border-b border-slate-100 dark:border-slate-700/60 py-1.5">
                    <span className="w-28 flex-shrink-0 text-slate-500 dark:text-slate-400">{row.label}</span>
                    <span className="flex-1 min-w-0 break-words text-slate-800 dark:text-slate-200">{row.value}</span>
                  </div>
                ))}
              </div>

              {item.detail_json != null && (
                <details className="rounded-md border border-slate-200 dark:border-slate-700">
                  <summary className="cursor-pointer select-none px-3 py-2 text-sm text-slate-600 dark:text-slate-300">
                    原始详情数据（detail_json）
                  </summary>
                  <pre className="overflow-x-auto px-3 py-2 text-xs text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-900/40 whitespace-pre-wrap break-words">
                    {JSON.stringify(item.detail_json, null, 2)}
                  </pre>
                </details>
              )}

              {item.raw_json != null && (
                <details className="rounded-md border border-slate-200 dark:border-slate-700">
                  <summary className="cursor-pointer select-none px-3 py-2 text-sm text-slate-600 dark:text-slate-300">
                    搜索原始数据（raw_json）
                  </summary>
                  <pre className="overflow-x-auto px-3 py-2 text-xs text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-900/40 whitespace-pre-wrap break-words">
                    {JSON.stringify(item.raw_json, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn-ios-secondary" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  )
}

export default MonitorItemDetailModal
