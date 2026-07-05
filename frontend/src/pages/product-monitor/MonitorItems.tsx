/**
 * 商品监控 - 采集商品页面
 *
 * 功能：
 * 1. 分页查看监控任务采集到的商品
 * 2. 支持按监控任务、商品标题筛选
 */
import { useEffect, useState } from 'react'
import { CheckSquare, ChevronLeft, ChevronRight, Eye, Loader2, PackageSearch, RefreshCw, RotateCcw, Search, Square } from 'lucide-react'
import {
  getListingMonitorItems,
  getListingMonitorTaskOptions,
  resetListingMonitorItemsDm,
  MONITOR_TYPE_LABELS,
  type ListingMonitorItem,
  type ListingMonitorTaskOption,
} from '@/api/listingMonitor'
import { PageLoading } from '@/components/common/Loading'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { MonitorItemDetailModal } from './MonitorItemDetailModal'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

// 计算北京时间（UTC+8）的"今天"日期，避免依赖浏览器本地时区
const getBeijingToday = (): string => {
  const now = new Date()
  // 本地时间转 UTC 再加 8 小时得到北京时间
  const beijing = new Date(now.getTime() + now.getTimezoneOffset() * 60000 + 8 * 3600 * 1000)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${beijing.getFullYear()}-${pad(beijing.getMonth() + 1)}-${pad(beijing.getDate())}`
}
// 采集时间默认区间：当天 00:00 ~ 23:59（datetime-local 格式 YYYY-MM-DDTHH:mm）
const DEFAULT_CREATED_START = `${getBeijingToday()}T00:00`
const DEFAULT_CREATED_END = `${getBeijingToday()}T23:59`

export function MonitorItems() {
  const { addToast } = useUIStore()

  const [loading, setLoading] = useState(true)
  const [tableLoading, setTableLoading] = useState(false)
  const [items, setItems] = useState<ListingMonitorItem[]>([])
  const [taskOptions, setTaskOptions] = useState<ListingMonitorTaskOption[]>([])
  const [taskId, setTaskId] = useState<number | ''>('')
  const [keyword, setKeyword] = useState('')
  const [area, setArea] = useState('')
  const [sellerNick, setSellerNick] = useState('')
  const [itemId, setItemId] = useState('')
  const [dmState, setDmState] = useState('')
  const [orderState, setOrderState] = useState('')
  const [sellerFill, setSellerFill] = useState('')
  const [hasDetail, setHasDetail] = useState('')
  const [createdStart, setCreatedStart] = useState(DEFAULT_CREATED_START)
  const [createdEnd, setCreatedEnd] = useState(DEFAULT_CREATED_END)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [detailItemPk, setDetailItemPk] = useState<number | null>(null)
  // 批量勾选的采集商品主键ID集合
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  // 重置私信失败状态：操作中标记 + 确认弹窗开关
  const [resetting, setResetting] = useState(false)
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false)

  const loadTaskOptions = async () => {
    try {
      const result = await getListingMonitorTaskOptions()
      if (result.success && result.data) {
        setTaskOptions(result.data.list || [])
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载监控任务列表失败') })
    }
  }

  const loadItems = async (nextPage = page, nextPageSize = pageSize) => {
    try {
      setTableLoading(true)
      const result = await getListingMonitorItems(nextPage, nextPageSize, {
        monitorTaskId: taskId === '' ? undefined : taskId,
        keyword: keyword.trim() || undefined,
        area: area.trim() || undefined,
        sellerNick: sellerNick.trim() || undefined,
        itemId: itemId.trim() || undefined,
        dmState: dmState || undefined,
        orderState: orderState || undefined,
        sellerFill: sellerFill || undefined,
        hasDetail: hasDetail === '' ? undefined : hasDetail === 'true',
        createdStart: createdStart || undefined,
        createdEnd: createdEnd || undefined,
      })
      if (!result.success || !result.data) {
        setItems([])
        setTotal(0)
        setTotalPages(0)
        addToast({ type: 'error', message: result.message || '加载采集商品失败' })
        return
      }
      setItems(result.data.list || [])
      setTotal(result.data.total || 0)
      setTotalPages(result.data.total_pages || 0)
      // 重新加载数据后清空勾选，避免跨页/筛选后保留过期选择
      setSelectedIds(new Set())
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载采集商品失败') })
    } finally {
      setLoading(false)
      setTableLoading(false)
    }
  }

  useEffect(() => {
    void loadTaskOptions()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 仅翻页 / 改每页大小时自动加载；筛选下拉改动不再即时触发，统一由「查询」按钮触发
  useEffect(() => {
    void loadItems(page, pageSize)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize])

  const handleSearch = () => {
    if (page === 1) {
      void loadItems(1, pageSize)
    } else {
      setPage(1)
    }
  }

  // 勾选/取消勾选单条
  const handleSelect = (itemPk: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(itemPk)) {
        next.delete(itemPk)
      } else {
        next.add(itemPk)
      }
      return next
    })
  }

  // 全选/取消全选当前页
  const handleSelectAll = () => {
    const currentPageIds = items.map((item) => item.id)
    if (currentPageIds.length === 0) {
      setSelectedIds(new Set())
      return
    }
    const allSelected = currentPageIds.every((id) => selectedIds.has(id))
    setSelectedIds(allSelected ? new Set() : new Set(currentPageIds))
  }

  // 批量将选中的"私信失败"商品重置为"未私信"，等待定时任务重试
  const handleResetDm = async () => {
    const itemIds = Array.from(selectedIds)
    if (itemIds.length === 0) {
      addToast({ type: 'warning', message: '请先勾选要重置的采集商品' })
      return
    }
    setResetting(true)
    try {
      const result = await resetListingMonitorItemsDm(itemIds)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '重置私信失败状态失败' })
        return
      }
      const successCount = result.data?.success_count ?? 0
      setResetConfirmOpen(false)
      if (successCount === 0) {
        // 选中的数据里没有"私信失败"的商品，无可重置项，给出明确提示
        addToast({ type: 'warning', message: '选中的数据中没有可重置的「私信失败」商品' })
        return
      }
      addToast({ type: 'success', message: result.message || `成功重置 ${successCount} 条商品，等待定时任务重试` })
      await loadItems(page, pageSize)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '重置私信失败状态失败') })
    } finally {
      setResetting(false)
    }
  }

  const startIndex = total === 0 ? 0 : (page - 1) * pageSize + 1
  const endIndex = Math.min(page * pageSize, total)
  const isAllSelected = items.length > 0 && items.every((item) => selectedIds.has(item.id))

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">采集商品</h1>
          <p className="page-description">查看各监控任务采集到的闲鱼商品信息（同一任务下按商品ID去重，重复出现则更新）。</p>
        </div>
        <div className="flex gap-3 flex-wrap">
          {selectedIds.size > 0 && (
            <button
              className="btn-ios-secondary"
              onClick={() => setResetConfirmOpen(true)}
              disabled={tableLoading || resetting}
            >
              {resetting ? <Loader2 className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
              重置私信失败 ({selectedIds.size})
            </button>
          )}
          <button className="btn-ios-secondary" onClick={() => loadItems(page, pageSize)} disabled={tableLoading || resetting}>
            {tableLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            刷新
          </button>
        </div>
      </div>

      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-end gap-3">
            <div className="input-group">
              <label className="input-label">监控任务</label>
              <select
                className="input-ios"
                value={taskId}
                onChange={(e) => setTaskId(e.target.value === '' ? '' : Number(e.target.value))}
              >
                <option value="">全部任务</option>
                {taskOptions.map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {`#${opt.id} ${opt.keyword}（${MONITOR_TYPE_LABELS[opt.monitor_type] || opt.monitor_type}）`}
                  </option>
                ))}
              </select>
            </div>
            <div className="input-group flex-1 min-w-[200px]">
              <label className="input-label">商品标题</label>
              <input
                className="input-ios"
                placeholder="输入商品标题关键字"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSearch()
                }}
              />
            </div>
            <div className="input-group min-w-[140px]">
              <label className="input-label">地区</label>
              <input
                className="input-ios"
                placeholder="如：江苏"
                value={area}
                onChange={(e) => setArea(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSearch()
                }}
              />
            </div>
            <div className="input-group min-w-[160px]">
              <label className="input-label">卖家昵称</label>
              <input
                className="input-ios"
                placeholder="输入卖家昵称"
                value={sellerNick}
                onChange={(e) => setSellerNick(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSearch()
                }}
              />
            </div>
            <div className="input-group min-w-[160px]">
              <label className="input-label">商品ID</label>
              <input
                className="input-ios"
                placeholder="输入商品ID精确查询"
                value={itemId}
                onChange={(e) => setItemId(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSearch()
                }}
              />
            </div>
            <div className="input-group min-w-[130px]">
              <label className="input-label">私信状态</label>
              <select
                className="input-ios"
                value={dmState}
                onChange={(e) => setDmState(e.target.value)}
              >
                <option value="">全部</option>
                <option value="not_sent">未私信</option>
                <option value="waiting">等待重试</option>
                <option value="pending">已发待确认</option>
                <option value="success">私信成功</option>
                <option value="failed">私信失败</option>
              </select>
            </div>
            <div className="input-group min-w-[130px]">
              <label className="input-label">下单状态</label>
              <select
                className="input-ios"
                value={orderState}
                onChange={(e) => setOrderState(e.target.value)}
              >
                <option value="">全部</option>
                <option value="not_ordered">未下单</option>
                <option value="ordered">已下单</option>
                <option value="failed">下单失败</option>
                <option value="no_account">无可用账号</option>
                <option value="duplicate">重复跳过</option>
              </select>
            </div>
            <div className="input-group min-w-[140px]">
              <label className="input-label">卖家补全状态</label>
              <select
                className="input-ios"
                value={sellerFill}
                onChange={(e) => setSellerFill(e.target.value)}
              >
                <option value="">全部</option>
                <option value="filled">已补全</option>
                <option value="pending">待补全</option>
                <option value="failed">补全失败</option>
              </select>
            </div>
            <div className="input-group min-w-[130px]">
              <label className="input-label">是否已获取详情</label>
              <select
                className="input-ios"
                value={hasDetail}
                onChange={(e) => setHasDetail(e.target.value)}
              >
                <option value="">全部</option>
                <option value="true">已获取</option>
                <option value="false">未获取</option>
              </select>
            </div>
            <div className="input-group min-w-[190px]">
              <label className="input-label">采集时间（起）</label>
              <input
                type="datetime-local"
                className="input-ios"
                value={createdStart}
                onChange={(e) => setCreatedStart(e.target.value)}
              />
            </div>
            <div className="input-group min-w-[190px]">
              <label className="input-label">采集时间（止）</label>
              <input
                type="datetime-local"
                className="input-ios"
                value={createdEnd}
                onChange={(e) => setCreatedEnd(e.target.value)}
              />
            </div>
            <button className="btn-ios-primary ml-auto" onClick={handleSearch}>
              <Search className="w-4 h-4" />查询
            </button>
          </div>
        </div>
      </div>

      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 320px)', minHeight: '420px' }}>
        <div className="vben-card-header flex items-center justify-between">
          <h2 className="vben-card-title">
            <PackageSearch className="w-4 h-4" />
            采集商品列表
          </h2>
          <span className="badge-primary">共 {total} 条</span>
        </div>

        <div className="flex-1 overflow-auto">
          <table className="table-ios min-w-[2800px]">
            <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
              <tr>
                <th className="w-10 whitespace-nowrap">
                  <button onClick={handleSelectAll} className="p-1 hover:bg-gray-100 rounded" title={isAllSelected ? '取消全选' : '全选'}>
                    {isAllSelected ? (
                      <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                    ) : (
                      <Square className="w-4 h-4 text-gray-400" />
                    )}
                  </button>
                </th>
                <th>ID</th>
                <th>所属任务</th>
                <th>商品ID</th>
                <th>图片</th>
                <th>卖家头像</th>
                <th>商品标题</th>
                <th>价格</th>
                <th>标签</th>
                <th>地区</th>
                <th>卖家昵称</th>
                <th>卖家ID</th>
                <th>卖家真实ID</th>
                <th>补全状态</th>
                <th>补全失败原因</th>
                <th>想要</th>
                <th>发布时间</th>
                <th>已私信</th>
                <th>私信账号</th>
                <th>私信会话ID</th>
                <th>私信原因</th>
                <th>私信次数</th>
                <th>已下单</th>
                <th>订单ID</th>
                <th>下单账号</th>
                <th>下单失败原因</th>
                <th>下单次数</th>
                <th>下单时间</th>
                <th>详情</th>
                <th>最近采集</th>
                <th>采集时间</th>
                <th>更新时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tableLoading ? (
                <tr>
                  <td colSpan={33} className="text-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={33} className="text-center py-12 text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <PackageSearch className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>暂无采集商品</p>
                    </div>
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.id} className={selectedIds.has(item.id) ? 'bg-blue-50/60 dark:bg-blue-900/10' : ''}>
                    <td className="w-10 whitespace-nowrap">
                      <button onClick={() => handleSelect(item.id)} className="p-1 hover:bg-gray-100 rounded" title={selectedIds.has(item.id) ? '取消勾选' : '勾选'}>
                        {selectedIds.has(item.id) ? (
                          <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                        ) : (
                          <Square className="w-4 h-4 text-gray-400" />
                        )}
                      </button>
                    </td>
                    <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">{item.id}</td>
                    <td className="max-w-[160px]">
                      <span className="truncate block text-slate-700 dark:text-slate-200" title={item.monitor_task_keyword || `任务#${item.monitor_task_id}`}>
                        {item.monitor_task_keyword || '-'}
                      </span>
                      <span className="text-xs text-slate-400">#{item.monitor_task_id}</span>
                    </td>
                    <td className="whitespace-nowrap text-slate-600 dark:text-slate-300">{item.item_id}</td>
                    <td>
                      {item.pic_url ? (
                        <img src={item.pic_url} alt="" className="w-12 h-12 object-cover rounded" loading="lazy" />
                      ) : (
                        <div className="w-12 h-12 rounded bg-slate-100 dark:bg-slate-700" />
                      )}
                    </td>
                    <td>
                      {item.seller_avatar ? (
                        <img src={item.seller_avatar} alt="" className="w-9 h-9 object-cover rounded-full" loading="lazy" />
                      ) : (
                        '-'
                      )}
                    </td>
                    <td className="max-w-[280px] font-medium text-slate-800 dark:text-slate-100">
                      <span className="truncate block" title={item.title || ''}>{item.title || '-'}</span>
                    </td>
                    <td className="whitespace-nowrap text-red-600 dark:text-red-400">{item.price != null ? `¥${item.price}` : '-'}</td>
                    <td className="max-w-[160px]"><span className="truncate block" title={item.tags || ''}>{item.tags || '-'}</span></td>
                    <td className="whitespace-nowrap">{item.area || '-'}</td>
                    <td className="max-w-[120px]"><span className="truncate block" title={item.seller_nick || ''}>{item.seller_nick || '-'}</span></td>
                    <td className="max-w-[140px]"><span className="truncate block" title={item.seller_id || ''}>{item.seller_id || '-'}</span></td>
                    <td className="whitespace-nowrap text-slate-600 dark:text-slate-300">{item.seller_user_id || '-'}</td>
                    <td className="whitespace-nowrap">
                      {item.seller_fill_status === 'failed' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">补全失败</span>
                      ) : item.seller_user_id ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">已补全</span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400">待补全</span>
                      )}
                    </td>
                    <td className="max-w-[200px]"><span className="truncate block" title={item.seller_fill_fail_reason || ''}>{item.seller_fill_fail_reason || '-'}</span></td>
                    <td>{item.want_count || '-'}</td>
                    <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">{item.publish_time ? new Date(item.publish_time).toLocaleString('zh-CN') : '-'}</td>
                    <td className="whitespace-nowrap">
                      {item.dm_status === 'failed' ? (
                        (item.dm_attempts || 0) >= 3 ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">私信失败(已放弃)</span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">私信失败(重试中)</span>
                        )
                      ) : item.is_dm_sent ? (
                        item.dm_status === 'success' ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">私信成功</span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">已发待确认</span>
                        )
                      ) : item.dm_status === 'waiting' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400" title={item.dm_fail_reason || '下单账号当前不可用，等待下次重试'}>等待重试</span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400">未私信</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap text-slate-600 dark:text-slate-300">{item.dm_account_id || '-'}</td>
                    <td className="max-w-[160px]"><span className="truncate block" title={item.dm_chat_id || ''}>{item.dm_chat_id || '-'}</span></td>
                    <td className="max-w-[200px]"><span className="truncate block" title={item.dm_fail_reason || ''}>{item.dm_fail_reason || '-'}</span></td>
                    <td className="text-center">{item.dm_attempts || 0}</td>
                    <td className="whitespace-nowrap">
                      {item.order_status === 'duplicate' ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400" title="同商品已在其他监控任务下单，跳过重复下单">重复跳过</span>
                      ) : item.order_status === 'no_account' && !item.is_ordered ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400" title={item.order_fail_reason || '无可用下单账号'}>无可用账号</span>
                      ) : item.order_status === 'failed' && !item.is_ordered ? (
                        (item.order_attempts || 0) >= 3 ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400">下单失败(已放弃)</span>
                        ) : (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">下单失败(重试中)</span>
                        )
                      ) : item.is_ordered ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">已下单</span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400">未下单</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap text-slate-600 dark:text-slate-300">{item.order_id || '-'}</td>
                    <td className="whitespace-nowrap text-slate-600 dark:text-slate-300">{item.order_account_id || '-'}</td>
                    <td className="max-w-[200px]"><span className="truncate block" title={item.order_fail_reason || ''}>{item.order_fail_reason || '-'}</span></td>
                    <td className="text-center">{item.order_attempts || 0}</td>
                    <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">{item.ordered_at ? new Date(item.ordered_at).toLocaleString('zh-CN') : '-'}</td>
                    <td className="whitespace-nowrap">
                      {item.has_detail ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">已获取</span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400">未获取</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">{item.last_seen_at ? new Date(item.last_seen_at).toLocaleString('zh-CN') : '-'}</td>
                    <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">{item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '-'}</td>
                    <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">{item.updated_at ? new Date(item.updated_at).toLocaleString('zh-CN') : '-'}</td>
                    <td>
                      <div className="flex items-center gap-2 whitespace-nowrap">
                        <button
                          type="button"
                          onClick={() => setDetailItemPk(item.id)}
                          className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          <Eye className="w-4 h-4" />详情
                        </button>
                        {item.target_url ? (
                          <a
                            href={`https://www.goofish.com/item?id=${item.item_id}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-blue-600 dark:text-blue-400 hover:underline"
                          >
                            查看
                          </a>
                        ) : (
                          '-'
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {total > 0 && (
          <div className="flex-shrink-0 vben-card-footer flex flex-col sm:flex-row items-center justify-between gap-4 px-4 py-3 border-t border-slate-200 dark:border-slate-700">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value))
                  setPage(1)
                }}
                className="px-2 py-1 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>条</span>
              <span className="ml-2">显示 {startIndex}-{endIndex} 条，共 {total} 条</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((prev) => Math.max(1, prev - 1))}
                disabled={page === 1 || tableLoading}
                className="p-2 rounded border border-slate-300 dark:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-700"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-3 py-1 text-sm text-slate-600 dark:text-slate-400">第 {page} / {totalPages || 1} 页</span>
              <button
                onClick={() => setPage((prev) => Math.min(totalPages || 1, prev + 1))}
                disabled={page >= (totalPages || 1) || tableLoading}
                className="p-2 rounded border border-slate-300 dark:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-700"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {detailItemPk !== null && (
        <MonitorItemDetailModal itemPk={detailItemPk} onClose={() => setDetailItemPk(null)} />
      )}

      <ConfirmModal
        isOpen={resetConfirmOpen}
        title="重置私信失败状态"
        message={`已选中 ${selectedIds.size} 条数据，仅其中"私信失败"的商品会被重置为"未私信"，并等待定时任务重新发送私信。是否继续？`}
        confirmText="确定重置"
        type="warning"
        loading={resetting}
        onConfirm={handleResetDm}
        onCancel={() => setResetConfirmOpen(false)}
      />
    </div>
  )
}

export default MonitorItems
