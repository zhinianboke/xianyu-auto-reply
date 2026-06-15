/**
 * 商品监控 - 采集商品页面
 *
 * 功能：
 * 1. 分页查看监控任务采集到的商品
 * 2. 支持按监控任务、商品标题筛选
 */
import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Loader2, PackageSearch, RefreshCw, Search } from 'lucide-react'
import {
  getListingMonitorItems,
  getListingMonitorTaskOptions,
  MONITOR_TYPE_LABELS,
  type ListingMonitorItem,
  type ListingMonitorTaskOption,
} from '@/api/listingMonitor'
import { PageLoading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

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
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)

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

  useEffect(() => {
    void loadItems(page, pageSize)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize, taskId])

  const handleSearch = () => {
    if (page === 1) {
      void loadItems(1, pageSize)
    } else {
      setPage(1)
    }
  }

  const startIndex = total === 0 ? 0 : (page - 1) * pageSize + 1
  const endIndex = Math.min(page * pageSize, total)

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
        <button className="btn-ios-secondary" onClick={() => loadItems(page, pageSize)} disabled={tableLoading}>
          {tableLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          刷新
        </button>
      </div>

      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-end gap-3">
            <div className="input-group">
              <label className="input-label">监控任务</label>
              <select
                className="input-ios"
                value={taskId}
                onChange={(e) => {
                  setTaskId(e.target.value === '' ? '' : Number(e.target.value))
                  setPage(1)
                }}
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
            <button className="btn-ios-primary" onClick={handleSearch}>
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
          <table className="table-ios min-w-[900px]">
            <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
              <tr>
                <th>图片</th>
                <th>商品标题</th>
                <th>价格</th>
                <th>地区</th>
                <th>卖家</th>
                <th>卖家真实ID</th>
                <th>想要</th>
                <th>发布时间</th>
                <th>已私信</th>
                <th>已下单</th>
                <th>详情</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tableLoading ? (
                <tr>
                  <td colSpan={12} className="text-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : items.length === 0 ? (
                <tr>
                  <td colSpan={12} className="text-center py-12 text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <PackageSearch className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>暂无采集商品</p>
                    </div>
                  </td>
                </tr>
              ) : (
                items.map((item) => (
                  <tr key={item.id}>
                    <td>
                      {item.pic_url ? (
                        <img src={item.pic_url} alt="" className="w-12 h-12 object-cover rounded" loading="lazy" />
                      ) : (
                        <div className="w-12 h-12 rounded bg-slate-100 dark:bg-slate-700" />
                      )}
                    </td>
                    <td className="max-w-[280px] font-medium text-slate-800 dark:text-slate-100">
                      <span className="truncate block" title={item.title || ''}>{item.title || '-'}</span>
                    </td>
                    <td className="whitespace-nowrap text-red-600 dark:text-red-400">{item.price != null ? `¥${item.price}` : '-'}</td>
                    <td className="whitespace-nowrap">{item.area || '-'}</td>
                    <td className="max-w-[120px]"><span className="truncate block" title={item.seller_nick || ''}>{item.seller_nick || '-'}</span></td>
                    <td className="whitespace-nowrap text-slate-600 dark:text-slate-300">{item.seller_user_id || '-'}</td>
                    <td>{item.want_count || '-'}</td>
                    <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">{item.publish_time ? new Date(item.publish_time).toLocaleString('zh-CN') : '-'}</td>
                    <td className="whitespace-nowrap">
                      {item.is_dm_sent ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">已私信</span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400">未私信</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap">
                      {item.is_ordered ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">已下单</span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400">未下单</span>
                      )}
                    </td>
                    <td>
                      {item.has_detail ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">已获取</span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400">未获取</span>
                      )}
                    </td>
                    <td>
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
    </div>
  )
}

export default MonitorItems
