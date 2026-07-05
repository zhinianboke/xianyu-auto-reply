/**
 * 代理订单页面
 * 
 * 两个TAB：
 * 1. 我的代理订单 - 我作为分销商，使用对接卡券发货产生的订单
 * 2. 代理我的订单 - 别人使用我的卡券发货产生的订单
 */
import { useState, useEffect, useCallback } from 'react'
import { RefreshCw, ShoppingCart, Eye } from 'lucide-react'
import { getMyAgentOrders, getUpstreamAgentOrders } from '@/api/distribution'
import type { AgentOrder } from '@/api/distribution'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { AgentOrderDetailModal } from './AgentOrderDetailModal'

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

type TabKey = 'my' | 'upstream'

export function AgentOrders() {
  const { addToast } = useUIStore()
  const { user } = useAuthStore()
  const isAdmin = Boolean(user?.is_admin)
  const [activeTab, setActiveTab] = useState<TabKey>('my')
  const [loading, setLoading] = useState(true)
  const [orders, setOrders] = useState<AgentOrder[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [totalPages, setTotalPages] = useState(0)
  const [statusFilter, setStatusFilter] = useState('')
  const [detailOrderId, setDetailOrderId] = useState<number | null>(null)

  // 加载数据
  const loadData = useCallback(async (
    tab: TabKey = activeTab,
    p: number = page,
    ps: number = pageSize,
    status: string = statusFilter,
  ) => {
    setLoading(true)
    try {
      const fetcher = tab === 'my' ? getMyAgentOrders : getUpstreamAgentOrders
      const result = await fetcher(p, ps, status)
      if (result.success && result.data) {
        setOrders(result.data.list)
        setTotal(result.data.total)
        setPage(result.data.page)
        setPageSize(result.data.page_size)
        setTotalPages(result.data.total_pages)
      }
    } catch {
      addToast({ type: 'error', message: '加载代理订单失败' })
    } finally {
      setLoading(false)
    }
  }, [activeTab, page, pageSize, statusFilter, addToast])

  useEffect(() => {
    loadData(activeTab, 1, pageSize, statusFilter)
  }, [])

  // 切换TAB
  const handleTabChange = (tab: TabKey) => {
    setActiveTab(tab)
    setPage(1)
    setStatusFilter('')
    loadData(tab, 1, pageSize, '')
  }

  // 状态筛选：仅更新草稿，不立即查询（点「查询」按钮后才生效）
  const handleStatusChange = (status: string) => {
    setStatusFilter(status)
  }

  // 点击查询：带当前状态草稿回到第1页
  const handleSearch = () => {
    loadData(activeTab, 1, pageSize, statusFilter)
  }

  // 重置筛选：清空状态并以空值查询
  const handleReset = () => {
    setStatusFilter('')
    loadData(activeTab, 1, pageSize, '')
  }

  // 分页
  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return
    loadData(activeTab, newPage, pageSize, statusFilter)
  }

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize)
    loadData(activeTab, 1, newSize, statusFilter)
  }


  // 利润颜色
  const profitColor = (profit: string) => {
    const val = parseFloat(profit)
    if (val > 0) return 'text-green-600 dark:text-green-400'
    if (val < 0) return 'text-red-600 dark:text-red-400'
    return 'text-gray-500'
  }

  return (
    <div className="space-y-4">
      {/* 页头 */}
      <div className="page-header flex-between flex-wrap gap-4">
        <div>
          <h1 className="page-title">代理订单</h1>
          <p className="page-description">查看通过对接卡券发货产生的订单记录</p>
        </div>
        <button onClick={() => loadData(activeTab, page, pageSize, statusFilter)} className="btn-ios-secondary">
          <RefreshCw className="w-4 h-4" />
          刷新
        </button>
      </div>

      {/* 列表卡片：TAB + 筛选 + 表格 + 分页，参照账号管理布局 */}
      <div
        className="vben-card flex flex-col"
        style={{ height: 'calc(100vh - 220px)', minHeight: '420px' }}
      >
        {/* 卡片头：左侧 TAB 切换 + 总数；右侧状态筛选 */}
        <div className="vben-card-header flex-shrink-0 flex-wrap gap-3">
          <div className="flex items-center gap-4 flex-wrap">
            <div className="flex items-center gap-1 p-1 rounded-lg bg-slate-100 dark:bg-slate-700/60">
              <button
                onClick={() => handleTabChange('my')}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'my'
                    ? 'bg-white dark:bg-slate-800 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100'
                }`}
              >
                我代理的订单
              </button>
              <button
                onClick={() => handleTabChange('upstream')}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                  activeTab === 'upstream'
                    ? 'bg-white dark:bg-slate-800 text-blue-600 dark:text-blue-400 shadow-sm'
                    : 'text-slate-600 dark:text-slate-300 hover:text-slate-800 dark:hover:text-slate-100'
                }`}
              >
                代理我的订单
              </button>
            </div>
            <span className="badge-primary">{total} 条记录</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-600 dark:text-slate-300">状态</span>
              <select
                value={statusFilter}
                onChange={(e) => handleStatusChange(e.target.value)}
                className="input-ios w-auto py-1.5 px-3 text-sm"
              >
                <option value="">全部</option>
                <option value="delivered">已发货</option>
                <option value="settled">已结算</option>
                <option value="failed">失败</option>
              </select>
            </div>
            {/* 查询/重置按钮组，右对齐 */}
            <div className="flex items-center gap-2 ml-auto">
              <button onClick={handleSearch} className="btn-ios-primary btn-sm">
                查询
              </button>
              {statusFilter && (
                <button onClick={handleReset} className="btn-ios-secondary btn-sm text-red-500">
                  重置
                </button>
              )}
            </div>
          </div>
        </div>

        {/* 表格主体：横向 + 纵向滚动，粘性表头 */}
        <div className="flex-1 overflow-x-auto overflow-y-auto scrollbar-visible">
          {loading ? (
            <div className="flex justify-center py-8">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : (
            <table className="table-ios min-w-[1600px]">
              <thead className="sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">
                <tr>
                  <th className="whitespace-nowrap">ID</th>
                  {isAdmin && <th className="whitespace-nowrap">所属用户</th>}
                  <th className="whitespace-nowrap">订单号</th>
                  <th className="whitespace-nowrap">来源</th>
                  <th className="whitespace-nowrap">卡券</th>
                  <th className="whitespace-nowrap">对接名称</th>
                  <th className="whitespace-nowrap">层级</th>
                  {activeTab === 'upstream' && <th className="whitespace-nowrap">分销商</th>}
                  <th className="whitespace-nowrap">售价</th>
                  <th className="whitespace-nowrap">对接价</th>
                  <th className="whitespace-nowrap">手续费</th>
                  <th className="whitespace-nowrap">承担方</th>
                  <th className="whitespace-nowrap">利润</th>
                  <th className="whitespace-nowrap">状态</th>
                  <th className="whitespace-nowrap">发货内容</th>
                  <th className="whitespace-nowrap">时间</th>
                  <th className="whitespace-nowrap sticky right-0 bg-slate-50 dark:bg-slate-800 z-20">操作</th>
                </tr>
              </thead>
              <tbody>
                {orders.length === 0 ? (
                  <tr>
                    <td colSpan={99}>
                      <div className="empty-state py-12">
                        <ShoppingCart className="empty-state-icon" />
                        <p className="text-slate-500 dark:text-slate-400">
                          {activeTab === 'my' ? '暂无代理订单' : '暂无被代理订单'}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  orders.map(order => (
                    <tr key={order.id}>
                      <td className="whitespace-nowrap text-sm text-slate-500 dark:text-slate-400">{order.id}</td>
                      {isAdmin && (
                        <td className="whitespace-nowrap text-sm text-slate-600 dark:text-slate-300 max-w-[160px] truncate" title={(activeTab === 'my' ? order.user_name : order.dealer_name) || ''}>
                          {activeTab === 'my' ? (order.user_name || '-') : (order.dealer_name || '-')}
                        </td>
                      )}
                      <td className="whitespace-nowrap text-sm font-mono text-slate-600 dark:text-slate-300">
                        {order.order_no}
                      </td>
                      <td className="whitespace-nowrap">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                          SOURCE_MAP[order.source || 'order']?.className || SOURCE_MAP.order.className
                        }`}>
                          {SOURCE_MAP[order.source || 'order']?.label || '闲鱼订单'}
                        </span>
                      </td>
                      <td className="whitespace-nowrap text-sm text-slate-700 dark:text-slate-200 max-w-[220px] truncate" title={order.card_name || ''}>
                        {order.card_name || '-'}
                      </td>
                      <td className="whitespace-nowrap text-sm text-slate-700 dark:text-slate-200 max-w-[220px] truncate" title={order.dock_name || ''}>
                        {order.dock_name || '-'}
                      </td>
                      <td className="whitespace-nowrap">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                          order.dock_level === 1
                            ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
                            : 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                        }`}>
                          {DOCK_LEVEL_MAP[order.dock_level] || `L${order.dock_level}`}
                        </span>
                      </td>
                      {activeTab === 'upstream' && (
                        <td className="whitespace-nowrap text-sm text-slate-600 dark:text-slate-300 max-w-[160px] truncate" title={order.dealer_name || ''}>
                          {order.dealer_name || '-'}
                        </td>
                      )}
                      <td className="whitespace-nowrap text-sm font-medium text-slate-800 dark:text-slate-100">¥{order.sale_price}</td>
                      <td className="whitespace-nowrap text-sm text-slate-600 dark:text-slate-300">¥{order.dock_price}</td>
                      <td className="whitespace-nowrap text-sm text-orange-600 dark:text-orange-400">
                        {order.fee_amount && order.fee_amount !== '0' ? `¥${order.fee_amount}` : '-'}
                      </td>
                      <td className="whitespace-nowrap text-sm">
                        {order.fee_payer === 'dealer'
                          ? <span className="text-blue-600 dark:text-blue-400">分销商</span>
                          : order.fee_payer === 'distributor'
                            ? <span className="text-purple-600 dark:text-purple-400">货主</span>
                            : <span className="text-slate-400">-</span>}
                      </td>
                      <td className={`whitespace-nowrap text-sm font-medium ${profitColor(order.profit)}`}>
                        ¥{order.profit}
                      </td>
                      <td className="whitespace-nowrap">
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                          STATUS_MAP[order.status]?.className || 'bg-gray-100 text-gray-600'
                        }`}>
                          {STATUS_MAP[order.status]?.label || order.status}
                        </span>
                      </td>
                      <td className="whitespace-nowrap text-sm text-slate-500 max-w-[220px] truncate" title={order.delivery_content || ''}>
                        {order.delivery_content || '-'}
                      </td>
                      <td className="whitespace-nowrap text-xs text-slate-500">
                        {order.created_at
                          ? new Date(order.created_at).toLocaleString('zh-CN')
                          : '-'}
                      </td>
                      <td className="whitespace-nowrap sticky right-0 bg-white dark:bg-slate-900 z-10">
                        <button
                          onClick={() => setDetailOrderId(order.id)}
                          className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded transition-colors"
                          title="查看明细"
                        >
                          <Eye className="w-3.5 h-3.5" />
                          明细
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}
        </div>

        {/* 分页控件：固定底部 */}
        {total > 0 && (
          <div className="flex-shrink-0 flex flex-col sm:flex-row items-center justify-between px-4 py-3 border-t border-slate-200 dark:border-slate-700 gap-3">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                className="input-ios w-auto py-1 px-2 text-sm"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>条，共 {total} 条</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-500 dark:text-slate-400">
                第 {page} / {totalPages || 1} 页
              </span>
              <button
                onClick={() => handlePageChange(page - 1)}
                disabled={page <= 1 || loading}
                className="btn-ios-secondary btn-sm"
              >
                上一页
              </button>
              <button
                onClick={() => handlePageChange(page + 1)}
                disabled={page >= totalPages || loading}
                className="btn-ios-secondary btn-sm"
              >
                下一页
              </button>
            </div>
          </div>
        )}
      </div>
      {/* 明细弹窗 */}
      {detailOrderId !== null && (
        <AgentOrderDetailModal
          orderId={detailOrderId}
          onClose={() => setDetailOrderId(null)}
        />
      )}
    </div>
  )
}
