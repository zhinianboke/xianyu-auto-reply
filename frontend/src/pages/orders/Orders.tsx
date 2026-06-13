import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { ShoppingCart, RefreshCw, Search, Trash2, Eye, X, Send, Loader2, Settings, Filter, Ban } from 'lucide-react'
import { fetchXianyuOrders, getOrders, deleteOrder, batchDeleteOrders, getOrderDetail, manualDelivery, type OrderDetail, type OrderFilterParams } from '@/api/orders'
import { getAccountDetails } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { BlacklistLevelModal } from './BlacklistLevelModal'
import type { Order, Account } from '@/types'

// 列配置类型
type ColumnKey = 'cookie_id' | 'order_id' | 'receiver' | 'item_id' | 'sku_info' | 'buyer_id' | 'buyer_fish_nick' | 'chat_id' | 'quantity' | 'amount' | 'status' | 'delivery_method' | 'delivery_send_status' | 'delivery_fail_reason' | 'is_bargain' | 'is_rated' | 'is_red_flower' | 'is_agent_order' | 'source' | 'placed_at' | 'created_at'

interface ColumnConfig {
  key: ColumnKey
  label: string
  visible: boolean
  fixed?: boolean // 固定列，不可隐藏
}

// 默认列配置
const defaultColumns: ColumnConfig[] = [
  { key: 'cookie_id', label: '账号ID', visible: true, fixed: true },
  { key: 'order_id', label: '订单ID', visible: true, fixed: true },
  { key: 'receiver', label: '收货人', visible: false },
  { key: 'item_id', label: '商品ID', visible: true, fixed: true },
  { key: 'sku_info', label: '规格', visible: true, fixed: true },
  { key: 'buyer_id', label: '买家ID', visible: true, fixed: true },
  { key: 'buyer_fish_nick', label: '买家昵称', visible: true, fixed: true },
  { key: 'chat_id', label: '会话ID', visible: false },
  { key: 'quantity', label: '数量', visible: true, fixed: true },
  { key: 'amount', label: '金额', visible: true, fixed: true },
  { key: 'status', label: '状态', visible: true, fixed: true },
  { key: 'delivery_method', label: '发货方式', visible: true, fixed: true },
  { key: 'delivery_send_status', label: '发送状态', visible: true },
  { key: 'delivery_fail_reason', label: '发货失败原因', visible: true },
  { key: 'is_bargain', label: '小刀', visible: true, fixed: true },
  { key: 'is_rated', label: '已评价', visible: true, fixed: true },
  { key: 'is_red_flower', label: '小红花', visible: true, fixed: true },
  { key: 'is_agent_order', label: '代销', visible: true, fixed: true },
  { key: 'source', label: '数据来源', visible: true },
  { key: 'placed_at', label: '订单时间', visible: true, fixed: true },
  { key: 'created_at', label: '创建时间', visible: false },
]

const statusMap: Record<string, { label: string; class: string }> = {
  pending_payment: { label: '待付款', class: 'badge-warning' },
  processing: { label: '处理中', class: 'badge-warning' },
  pending_ship: { label: '待发货', class: 'badge-info' },
  processed: { label: '已处理', class: 'badge-info' },
  shipped: { label: '已发货', class: 'badge-success' },
  completed: { label: '已完成', class: 'badge-success' },
  refunding: { label: '退款中', class: 'badge-warning' },
  cancelled: { label: '已关闭', class: 'badge-danger' },
  unknown: { label: '未知', class: 'badge-gray' },
}

export function Orders() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [orders, setOrders] = useState<Order[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')
  const [selectedStatus, setSelectedStatus] = useState('')
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [orderDetail, setOrderDetail] = useState<OrderDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  const [deliveringOrderId, setDeliveringOrderId] = useState<string | null>(null)
  // 分页状态
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [ordersLoading, setOrdersLoading] = useState(false)
  const [fetchingXianyuOrders, setFetchingXianyuOrders] = useState(false)
  
  // 筛选状态
  const [filters, setFilters] = useState<OrderFilterParams>({
    search: null,
    delivery_method: null,
    is_bargain: null,
    is_rated: null,
    start_date: null,
    end_date: null,
    delivery_send_status: null,
  })

  // 勾选状态
  const [selectedOrderIds, setSelectedOrderIds] = useState<Set<string>>(new Set())

  // 确认弹窗状态
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; id: string | null }>({ open: false, id: null })
  const [batchDeleteConfirm, setBatchDeleteConfirm] = useState(false)
  const [deliveryConfirm, setDeliveryConfirm] = useState<{ open: boolean; orderNo: string | null }>({ open: false, orderNo: null })
  const [deleting, setDeleting] = useState(false)

  // 筛选面板展开状态
  const [showFilters, setShowFilters] = useState(false)

  // 拉黑弹窗状态
  const [blacklistModal, setBlacklistModal] = useState<{ open: boolean; orders: Array<{ buyer_id: string; cookie_id: string; item_id: string }> }>({ open: false, orders: [] })

  // 列配置状态
  const [columns, setColumns] = useState<ColumnConfig[]>(() => {
    const saved = localStorage.getItem('order-columns-config')
    if (saved) {
      const parsed: ColumnConfig[] = JSON.parse(saved)
      // 如果缓存的列数量与默认不一致（新增/删除了列），重置为默认
      if (parsed.length !== defaultColumns.length) {
        localStorage.removeItem('order-columns-config')
        return defaultColumns
      }
      return parsed
    }
    return defaultColumns
  })
  const [columnSettingsOpen, setColumnSettingsOpen] = useState(false)

  const loadOrders = async (page: number = currentPage, size: number = pageSize, currentFilters: OrderFilterParams = filters) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setOrdersLoading(true)
      setSelectedOrderIds(new Set())
      const result = await getOrders(selectedAccount || undefined, selectedStatus || undefined, page, size, currentFilters)
      if (result.success) {
        setOrders(result.data || [])
        setTotal(result.total || 0)
        setTotalPages(result.total_pages || 0)
        setCurrentPage(page)
      }
    } catch {
      addToast({ type: 'error', message: '加载订单列表失败' })
    } finally {
      setOrdersLoading(false)
      setLoading(false)
    }
  }

  // 每页条数切换
  const handlePageSizeChange = (newPageSize: number) => {
    setPageSize(newPageSize)
    loadOrders(1, newPageSize, filters)
  }
  
  // 筛选条件变更
  const handleFilterChange = (key: keyof OrderFilterParams, value: string | boolean | null) => {
    const newFilters = { ...filters, [key]: value }
    setFilters(newFilters)
    loadOrders(1, pageSize, newFilters)
  }
  
  // 重置筛选条件
  const handleResetFilters = () => {
    const emptyFilters: OrderFilterParams = {
      search: null,
      delivery_method: null,
      is_bargain: null,
      is_rated: null,
      start_date: null,
      end_date: null,
      delivery_send_status: null,
    }
    setFilters(emptyFilters)
    const hasAccountOrStatusFilter = Boolean(selectedAccount || selectedStatus)
    setSelectedAccount('')
    setSelectedStatus('')
    if (!hasAccountOrStatusFilter) {
      loadOrders(1, pageSize, emptyFilters)
    }
  }
  
  // 检查是否有筛选条件
  const hasActiveFilters = Boolean(selectedAccount || selectedStatus) || Object.entries(filters).some(([key, v]) => {
    if (key === 'search') return !!v
    return v !== null
  })

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const data = await getAccountDetails()
      setAccounts(data)
    } catch {
      // ignore
    }
  }

  // 列配置处理
  const toggleColumn = (key: ColumnKey) => {
    const newColumns = columns.map(col => 
      col.key === key ? { ...col, visible: !col.visible } : col
    )
    setColumns(newColumns)
    localStorage.setItem('order-columns-config', JSON.stringify(newColumns))
  }

  const resetColumns = () => {
    setColumns(defaultColumns)
    localStorage.setItem('order-columns-config', JSON.stringify(defaultColumns))
    addToast({ type: 'success', message: '已恢复默认列设置' })
  }

  const visibleColumns = columns.filter(col => col.visible)

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadAccounts()
    loadOrders(1, pageSize, filters)
  }, [_hasHydrated, isAuthenticated, token])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    setCurrentPage(1)
    loadOrders(1, pageSize, filters)
  }, [_hasHydrated, isAuthenticated, token, selectedAccount, selectedStatus])

  const handleDelete = async (id: string) => {
    setDeleting(true)
    try {
      const result = await deleteOrder(id)
      if (result.success) {
        addToast({ type: 'success', message: '删除成功' })
        setDeleteConfirm({ open: false, id: null })
        loadOrders()
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setDeleting(false)
    }
  }

  const handleShowDetail = async (orderNo: string) => {
    setLoadingDetail(true)
    setDetailModalOpen(true)
    try {
      const result = await getOrderDetail(orderNo)
      if (result.success) {
        setOrderDetail(result.data)
      } else {
        addToast({ type: 'error', message: '获取订单详情失败' })
        setDetailModalOpen(false)
      }
    } catch {
      addToast({ type: 'error', message: '获取订单详情失败' })
      setDetailModalOpen(false)
    } finally {
      setLoadingDetail(false)
    }
  }

  const handleManualDelivery = async (orderNo: string) => {
    setDeliveringOrderId(orderNo)
    setDeliveryConfirm({ open: false, orderNo: null })
    try {
      const result = await manualDelivery(orderNo)
      if (result.success) {
        addToast({ type: 'success', message: `发货成功: ${result.data?.card_name || ''}` })
        loadOrders()
      } else {
        addToast({ type: 'error', message: result.message || '发货失败' })
      }
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string } } }
      const errorMessage = axiosError.response?.data?.detail || '发货失败'
      addToast({ type: 'error', message: errorMessage })
    } finally {
      setDeliveringOrderId(null)
    }
  }

  const handleFetchXianyuOrders = async () => {
    setFetchingXianyuOrders(true)
    try {
      const result = await fetchXianyuOrders(selectedAccount || undefined)
      if (result.success) {
        const syncData = result.data
        addToast({
          type: 'success',
          message: result.message || `同步完成：获取${syncData?.total_fetched || 0}条，新增${syncData?.new_inserted || 0}条，更新${syncData?.updated || 0}条`,
        })
        if (syncData?.errors?.length) {
          addToast({ type: 'error', message: `部分账号同步失败：${syncData.errors.slice(0, 2).join('；')}` })
        }
        loadOrders(1, pageSize, filters)
      } else {
        addToast({ type: 'error', message: result.message || '获取闲鱼订单失败' })
      }
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string } } }
      const errorMessage = axiosError.response?.data?.detail || '获取闲鱼订单失败'
      addToast({ type: 'error', message: errorMessage })
    } finally {
      setFetchingXianyuOrders(false)
    }
  }

  // 勾选操作
  const toggleSelectOrder = (id: string) => {
    setSelectedOrderIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const toggleSelectAll = () => {
    if (selectedOrderIds.size === orders.length) {
      setSelectedOrderIds(new Set())
    } else {
      setSelectedOrderIds(new Set(orders.map(o => o.id)))
    }
  }

  const handleBatchDelete = async () => {
    const ids = Array.from(selectedOrderIds).map(id => Number(id))
    setDeleting(true)
    setBatchDeleteConfirm(false)
    try {
      const result = await batchDeleteOrders(ids)
      if (result.success) {
        addToast({ type: 'success', message: result.message || `删除成功${ids.length}条` })
        setSelectedOrderIds(new Set())
        loadOrders(currentPage, pageSize, filters)
      } else {
        addToast({ type: 'error', message: result.message || '批量删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '批量删除失败' })
    } finally {
      setDeleting(false)
    }
  }

  // 搜索防抖
  useEffect(() => {
    const timer = setTimeout(() => {
      loadOrders(1, pageSize, filters)
    }, 300)
    return () => clearTimeout(timer)
  }, [filters.search])

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-3 sm:space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 sm:gap-4">
        <div>
          <h1 className="page-title">订单管理</h1>
          <p className="page-description">查看和管理所有订单信息</p>
        </div>
        <div className="flex flex-col sm:flex-row gap-3 w-full sm:w-auto">
          <button onClick={handleFetchXianyuOrders} disabled={fetchingXianyuOrders || !selectedAccount} className="btn-ios-primary w-full sm:w-auto" title={!selectedAccount ? '请先选择账号' : '只能获取近3个月内的订单'}>
            {fetchingXianyuOrders ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <ShoppingCart className="w-4 h-4" />
            )}
            获取闲鱼订单
            <span className="text-xs opacity-70">（近3个月）</span>
          </button>
          <button onClick={() => loadOrders(currentPage)} disabled={ordersLoading} className="btn-ios-secondary w-full sm:w-auto">
            {ordersLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            刷新
          </button>
        </div>
      </div>

      {/* Orders List：筛选 + 表格 + 分页合卡，参照账号管理布局 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="vben-card flex flex-col"
        style={{ height: 'calc(100vh - 220px)', minHeight: '420px' }}
      >
        {/* 卡片头：标题 + 总数 + 操作按钮组 */}
        <div className="vben-card-header flex-shrink-0 flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="vben-card-title">
              <ShoppingCart className="w-4 h-4" />
              订单列表
            </h2>
            <span className="badge-primary">共 {total} 个订单</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            {selectedOrderIds.size > 0 && (
              <>
                <button
                  onClick={() => {
                    const selectedOrders = orders
                      .filter((o) => selectedOrderIds.has(o.id))
                      .map((o) => ({ buyer_id: o.buyer_id, cookie_id: o.cookie_id, item_id: o.item_id }))
                    setBlacklistModal({ open: true, orders: selectedOrders })
                  }}
                  className="btn-ios-secondary btn-sm flex items-center gap-1 text-orange-600 border-orange-300 hover:bg-orange-50 dark:hover:bg-orange-900/20"
                >
                  <Ban className="w-3.5 h-3.5" />
                  批量拉黑({selectedOrderIds.size})
                </button>
                <button
                  onClick={() => setBatchDeleteConfirm(true)}
                  disabled={deleting}
                  className="btn-ios-danger btn-sm"
                >
                  {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                  删除选中({selectedOrderIds.size})
                </button>
              </>
            )}
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`btn-ios-secondary btn-sm flex items-center gap-1 ${hasActiveFilters ? 'text-blue-600 border-blue-300' : ''}`}
            >
              <Filter className="w-4 h-4" />
              筛选
              {hasActiveFilters && <span className="ml-1 px-1.5 py-0.5 text-xs bg-blue-100 text-blue-600 rounded-full">已启用</span>}
            </button>
            {hasActiveFilters && (
              <button onClick={handleResetFilters} className="btn-ios-secondary btn-sm text-red-500">
                重置
              </button>
            )}
            <button
              onClick={() => setColumnSettingsOpen(!columnSettingsOpen)}
              className="btn-icon"
              title="列设置"
            >
              <Settings className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* 筛选面板：可折叠 */}
        {showFilters && (
          <div className="flex-shrink-0 px-4 py-3 border-b border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 xl:grid-cols-8 gap-3">
              <div className="input-group">
                <label className="input-label">筛选账号</label>
                <Select
                  value={selectedAccount}
                  onChange={setSelectedAccount}
                  options={[
                    { value: '', label: '所有账号', key: 'all' },
                    ...accounts.map((account) => ({
                      value: account.id,
                      label: account.note ? `${account.id} (${account.note})` : account.id,
                      key: account.pk?.toString() || account.id,
                    })),
                  ]}
                  placeholder="所有账号"
                />
              </div>
              <div className="input-group">
                <label className="input-label">订单状态</label>
                <Select
                  value={selectedStatus}
                  onChange={setSelectedStatus}
                  options={[
                    { value: '', label: '所有状态' },
                    { value: 'pending_payment', label: '待付款' },
                    { value: 'processing', label: '处理中' },
                    { value: 'pending_ship', label: '待发货' },
                    { value: 'shipped', label: '已发货' },
                    { value: 'completed', label: '已完成' },
                    { value: 'refunding', label: '退款中' },
                    { value: 'cancelled', label: '已关闭' },
                  ]}
                  placeholder="所有状态"
                />
              </div>
              <div className="input-group">
                <label className="input-label">发货方式</label>
                <select
                  value={filters.delivery_method || ''}
                  onChange={(e) => handleFilterChange('delivery_method', e.target.value || null)}
                  className="input-ios"
                >
                  <option value="">全部</option>
                  <option value="none">未发货</option>
                  <option value="manual">手动发货</option>
                  <option value="auto">自动发货</option>
                  <option value="scheduled">定时发货</option>
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">发送状态</label>
                <select
                  value={filters.delivery_send_status || ''}
                  onChange={(e) => handleFilterChange('delivery_send_status', e.target.value || null)}
                  className="input-ios"
                >
                  <option value="">全部</option>
                  <option value="success">发送成功</option>
                  <option value="failed">发送失败</option>
                  <option value="unknown">待确认</option>
                  <option value="timeout">超时</option>
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">小刀</label>
                <select
                  value={filters.is_bargain === null ? '' : String(filters.is_bargain)}
                  onChange={(e) => handleFilterChange('is_bargain', e.target.value === '' ? null : e.target.value === 'true')}
                  className="input-ios"
                >
                  <option value="">全部</option>
                  <option value="true">是</option>
                  <option value="false">否</option>
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">已评价</label>
                <select
                  value={filters.is_rated === null ? '' : String(filters.is_rated)}
                  onChange={(e) => handleFilterChange('is_rated', e.target.value === '' ? null : e.target.value === 'true')}
                  className="input-ios"
                >
                  <option value="">全部</option>
                  <option value="true">是</option>
                  <option value="false">否</option>
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">开始日期</label>
                <input
                  type="date"
                  value={filters.start_date || ''}
                  onChange={(e) => handleFilterChange('start_date', e.target.value || null)}
                  className="input-ios"
                />
              </div>
              <div className="input-group">
                <label className="input-label">结束日期</label>
                <input
                  type="date"
                  value={filters.end_date || ''}
                  onChange={(e) => handleFilterChange('end_date', e.target.value || null)}
                  className="input-ios"
                />
              </div>
              <div className="input-group">
                <label className="input-label">搜索订单</label>
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                  <input
                    type="text"
                    value={filters.search || ''}
                    onChange={(e) => setFilters(prev => ({ ...prev, search: e.target.value || null }))}
                    placeholder="搜索订单ID或商品ID..."
                    className="input-ios pl-9"
                  />
                </div>
              </div>
            </div>
          </div>
        )}
        <div className="flex-1 overflow-x-auto overflow-y-auto scrollbar-visible">
          <table className="table-ios min-w-[1800px]">
            <thead className="sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">
              <tr>
                <th className="w-10">
                  <input
                    type="checkbox"
                    checked={orders.length > 0 && selectedOrderIds.size === orders.length}
                    onChange={toggleSelectAll}
                    className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500"
                  />
                </th>
                {visibleColumns.map(col => (
                  <th key={col.key} className="whitespace-nowrap">{col.label}</th>
                ))}
                <th className="whitespace-nowrap sticky right-0 bg-slate-50 dark:bg-slate-800 z-20">操作</th>
              </tr>
            </thead>
            <tbody>
              {orders.length === 0 ? (
                <tr>
                  <td colSpan={visibleColumns.length + 2}>
                    <div className="empty-state py-12">
                      <ShoppingCart className="empty-state-icon" />
                      <p className="text-slate-500 dark:text-slate-400">暂无订单数据</p>
                    </div>
                  </td>
                </tr>
              ) : (
                orders.map((order) => {
                  const status = statusMap[order.status] || statusMap.unknown
                  return (
                    <tr key={order.id} className={selectedOrderIds.has(order.id) ? 'bg-blue-50 dark:bg-blue-900/10' : ''}>
                      <td className="whitespace-nowrap">
                        <input
                          type="checkbox"
                          checked={selectedOrderIds.has(order.id)}
                          onChange={() => toggleSelectOrder(order.id)}
                          className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500"
                        />
                      </td>
                      {visibleColumns.map(col => {
                        switch (col.key) {
                          case 'cookie_id':
                            return (
                              <td key={col.key} className="whitespace-nowrap font-medium text-blue-600 dark:text-blue-400 max-w-[180px] truncate" title={(() => {
                                const account = accounts.find(acc => acc.id === order.cookie_id)
                                return account?.note ? `${order.cookie_id} (${account.note})` : order.cookie_id
                              })()}>
                                {(() => {
                                  const account = accounts.find(acc => acc.id === order.cookie_id)
                                  return account?.note ? `${order.cookie_id} (${account.note})` : order.cookie_id
                                })()}
                              </td>
                            )
                          case 'order_id':
                            return <td key={col.key} className="whitespace-nowrap font-mono text-sm text-slate-600 dark:text-slate-300">{order.order_id}</td>
                          case 'receiver':
                            return (
                              <td key={col.key} className="whitespace-nowrap text-sm">
                                <div className="flex flex-col group relative cursor-pointer">
                                  <span>{order.receiver_name || '-'}</span>
                                  <span className="text-gray-400 text-xs">{order.receiver_phone || ''}</span>
                                  {order.receiver_address && (
                                    <div className="absolute left-0 top-full mt-1 z-50 hidden group-hover:block bg-gray-800 text-white text-xs rounded-lg px-3 py-2 max-w-xs whitespace-normal shadow-lg">
                                      {order.receiver_address}
                                    </div>
                                  )}
                                </div>
                              </td>
                            )
                          case 'item_id':
                            return (
                              <td key={col.key} className="whitespace-nowrap text-sm text-slate-700 dark:text-slate-200">
                                <div className="group relative cursor-pointer">
                                  <span>{order.item_id}</span>
                                  {order.item_title && (
                                    <div className="absolute left-0 top-full mt-1 z-50 hidden group-hover:block bg-gray-800 text-white text-xs rounded-lg px-3 py-2 max-w-xs whitespace-normal shadow-lg">
                                      {order.item_title}
                                    </div>
                                  )}
                                </div>
                              </td>
                            )
                          case 'sku_info':
                            return <td key={col.key} className="whitespace-nowrap text-sm text-slate-500 dark:text-slate-400 max-w-[180px] truncate" title={order.sku_info || ''}>{order.sku_info || '-'}</td>
                          case 'buyer_id':
                            return <td key={col.key} className="whitespace-nowrap text-sm text-slate-700 dark:text-slate-200">{order.buyer_id}</td>
                          case 'buyer_fish_nick':
                            return <td key={col.key} className="whitespace-nowrap text-sm text-slate-700 dark:text-slate-200">{order.buyer_fish_nick || '-'}</td>
                          case 'chat_id':
                            return <td key={col.key} className="whitespace-nowrap text-sm text-slate-500 dark:text-slate-400">{order.chat_id || '-'}</td>
                          case 'quantity':
                            return <td key={col.key} className="whitespace-nowrap text-sm text-slate-700 dark:text-slate-200">{order.quantity}</td>
                          case 'amount':
                            return <td key={col.key} className="whitespace-nowrap text-sm text-amber-600 dark:text-amber-400 font-medium">¥{order.amount}</td>
                          case 'status':
                            return (
                              <td key={col.key} className="whitespace-nowrap">
                                <span className={status.class}>{status.label}</span>
                              </td>
                            )
                          case 'delivery_method':
                            return (
                              <td key={col.key} className="whitespace-nowrap">
                                {order.delivery_method ? (
                                  <span className={
                                    order.delivery_method === 'manual' ? 'badge-info' :
                                    order.delivery_method === 'auto' ? 'badge-success' :
                                    order.delivery_method === 'scheduled' ? 'badge-warning' :
                                    'badge-gray'
                                  }>
                                    {order.delivery_method === 'manual' ? '手动' :
                                     order.delivery_method === 'auto' ? '自动' :
                                     order.delivery_method === 'scheduled' ? '定时' :
                                     order.delivery_method}
                                  </span>
                                ) : (
                                  <span className="text-gray-400">-</span>
                                )}
                              </td>
                            )
                          case 'delivery_send_status':
                            return (
                              <td key={col.key} className="whitespace-nowrap text-sm">
                                {order.delivery_send_status ? (
                                  <div className="group relative cursor-pointer">
                                    <span className={
                                      order.delivery_send_status === 'success' ? 'badge-success' :
                                      order.delivery_send_status === 'failed' ? 'badge-danger' :
                                      order.delivery_send_status === 'timeout' ? 'badge-warning' :
                                      'badge-gray'
                                    }>
                                      {order.delivery_send_status === 'success' ? '发送成功' :
                                       order.delivery_send_status === 'failed' ? '发送失败' :
                                       order.delivery_send_status === 'timeout' ? '超时' :
                                       '待确认'}
                                    </span>
                                    {order.delivery_send_fail_reason ? (
                                      <div className="absolute left-0 top-full mt-1 z-50 hidden group-hover:block bg-gray-800 text-white text-xs rounded-lg px-3 py-2 max-w-sm whitespace-normal shadow-lg break-words">
                                        {order.delivery_send_fail_reason}
                                      </div>
                                    ) : null}
                                  </div>
                                ) : (
                                  <span className="text-gray-400">-</span>
                                )}
                              </td>
                            )
                          case 'delivery_fail_reason':
                            return (
                              <td key={col.key} className="whitespace-nowrap text-sm">
                                {order.delivery_fail_reason ? (
                                  <div className="group relative cursor-pointer max-w-[160px]">
                                    <span className="block truncate text-red-500">{order.delivery_fail_reason}</span>
                                    <div className="absolute left-0 top-full mt-1 z-50 hidden group-hover:block bg-gray-800 text-white text-xs rounded-lg px-3 py-2 max-w-sm whitespace-normal shadow-lg break-words">
                                      {order.delivery_fail_reason}
                                    </div>
                                  </div>
                                ) : (
                                  <span className="text-gray-400">-</span>
                                )}
                              </td>
                            )
                          case 'is_bargain':
                            return (
                              <td key={col.key} className="whitespace-nowrap">
                                {order.is_bargain ? (
                                  <span className="badge-warning">是</span>
                                ) : (
                                  <span className="badge-gray">否</span>
                                )}
                              </td>
                            )
                          case 'is_rated':
                            return (
                              <td key={col.key} className="whitespace-nowrap">
                                {order.is_rated ? (
                                  <span className="badge-success">是</span>
                                ) : (
                                  <span className="badge-gray">否</span>
                                )}
                              </td>
                            )
                          case 'is_red_flower':
                            return (
                              <td key={col.key} className="whitespace-nowrap">
                                {order.is_red_flower ? (
                                  <span className="badge-success">是</span>
                                ) : (
                                  <span className="badge-gray">否</span>
                                )}
                              </td>
                            )
                          case 'is_agent_order':
                            return (
                              <td key={col.key} className="whitespace-nowrap">
                                {order.is_agent_order ? (
                                  <span className="badge-info">代销</span>
                                ) : (
                                  <span className="badge-gray">自营</span>
                                )}
                              </td>
                            )
                          case 'source':
                            return (
                              <td key={col.key} className="whitespace-nowrap text-sm">
                                {order.source ? (
                                  <span className={
                                    order.source === 'fetch_xianyu' ? 'badge-info' : 'badge-gray'
                                  }>
                                    {order.source === 'fetch_xianyu' ? '手动获取' : order.source}
                                  </span>
                                ) : (
                                  <span className="badge-gray">自动</span>
                                )}
                              </td>
                            )
                          case 'placed_at':
                            return (
                              <td key={col.key} className="whitespace-nowrap text-xs text-slate-500 dark:text-slate-400">
                                {order.placed_at ? new Date(order.placed_at).toLocaleString('zh-CN') : '-'}
                              </td>
                            )
                          case 'created_at':
                            return (
                              <td key={col.key} className="whitespace-nowrap text-xs text-slate-500 dark:text-slate-400">
                                {order.created_at ? new Date(order.created_at).toLocaleString('zh-CN') : '-'}
                              </td>
                            )
                          default:
                            return <td key={col.key} className="whitespace-nowrap">-</td>
                        }
                      })}
                      <td className="whitespace-nowrap sticky right-0 bg-white dark:bg-slate-900 z-10">
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleShowDetail(order.order_id)}
                            className="p-2 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
                            title="查看详情"
                          >
                            <Eye className="w-4 h-4 text-blue-500" />
                          </button>
                          <button
                            onClick={() => setDeliveryConfirm({ open: true, orderNo: order.order_id })}
                            disabled={deliveringOrderId === order.order_id || order.status === 'shipped' || order.status === 'completed'}
                            className={`p-2 rounded-lg transition-colors ${
                              order.status === 'shipped' || order.status === 'completed'
                                ? 'opacity-50 cursor-not-allowed'
                                : 'hover:bg-green-50 dark:hover:bg-green-900/20'
                            }`}
                            title={order.status === 'shipped' || order.status === 'completed' ? '已发货' : '手动发货'}
                          >
                            {deliveringOrderId === order.order_id ? (
                              <Loader2 className="w-4 h-4 text-green-500 animate-spin" />
                            ) : (
                              <Send className="w-4 h-4 text-green-500" />
                            )}
                          </button>
                          <button
                            onClick={() => setBlacklistModal({ open: true, orders: [{ buyer_id: order.buyer_id, cookie_id: order.cookie_id, item_id: order.item_id }] })}
                            className="p-2 rounded-lg hover:bg-orange-50 dark:hover:bg-orange-900/20 transition-colors"
                            title="一键拉黑"
                          >
                            <Ban className="w-4 h-4 text-orange-500" />
                          </button>
                          <button
                            onClick={() => setDeleteConfirm({ open: true, id: order.id })}
                            className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                            title="删除"
                          >
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>

        {/* 分页 */}
        {total > 0 && (
          <div className="flex-shrink-0 flex flex-col sm:flex-row items-center justify-between px-4 py-3 border-t border-slate-200 dark:border-slate-700 gap-3">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                disabled={ordersLoading}
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
                第 {currentPage} / {totalPages || 1} 页
              </span>
              <button
                onClick={() => loadOrders(currentPage - 1)}
                disabled={currentPage <= 1 || ordersLoading}
                className="btn-ios-secondary btn-sm"
                title="上一页"
              >
                上一页
              </button>
              <button
                onClick={() => loadOrders(currentPage + 1)}
                disabled={currentPage >= totalPages || ordersLoading}
                className="btn-ios-secondary btn-sm"
                title="下一页"
              >
                下一页
              </button>
            </div>
          </div>
        )}
      </motion.div>

      {/* 订单详情弹窗 */}
      {detailModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content max-w-2xl">
            <div className="modal-header flex items-center justify-between">
              <h2 className="text-lg font-semibold">订单详情</h2>
              <button
                onClick={() => setDetailModalOpen(false)}
                className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg"
              >
                <X className="w-5 h-5 text-gray-500" />
              </button>
            </div>
            <div className="modal-body">
              {loadingDetail ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                  <span className="ml-2 text-gray-500">加载中...</span>
                </div>
              ) : orderDetail ? (
                <div className="space-y-4">
                  {/* 收货人信息 */}
                  <div>
                    <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">收货人信息</h3>
                    <div className="grid grid-cols-1 gap-2 text-sm">
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">收货人姓名</span>
                        <span>{orderDetail.receiver_name || '未知'}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">手机号</span>
                        <span>{orderDetail.receiver_phone || '未知'}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">收货地址</span>
                        <span className="text-right max-w-xs">{orderDetail.receiver_address || '未知'}</span>
                      </div>
                    </div>
                  </div>

                  {/* 基本信息 */}
                  <div>
                    <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">基本信息</h3>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">订单ID</span>
                        <span className="font-mono">{orderDetail.order_id}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">商品ID</span>
                        <span>{orderDetail.item_id || '未知'}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">买家ID</span>
                        <span>{orderDetail.buyer_id || '未知'}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">买家昵称</span>
                        <span>{orderDetail.buyer_fish_nick || '-'}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">会话ID</span>
                        <span>{orderDetail.chat_id || '未知'}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">账号ID</span>
                        <span className="text-blue-600">
                          {(() => {
                            const account = accounts.find(acc => acc.id === orderDetail.cookie_id)
                            return account?.note ? `${orderDetail.cookie_id} (${account.note})` : (orderDetail.cookie_id || '未知')
                          })()}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">订单状态</span>
                        <span className={statusMap[orderDetail.status]?.class || 'badge-gray'}>
                          {statusMap[orderDetail.status]?.label || '未知'}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">是否小刀</span>
                        {orderDetail.is_bargain ? (
                          <span className="badge-warning">是</span>
                        ) : (
                          <span className="badge-gray">否</span>
                        )}
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">已求小红花</span>
                        {orderDetail.is_red_flower ? (
                          <span className="badge-success">是</span>
                        ) : (
                          <span className="badge-gray">否</span>
                        )}
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">发货方式</span>
                        {orderDetail.delivery_method ? (
                          <span className={
                            orderDetail.delivery_method === 'manual' ? 'badge-info' :
                            orderDetail.delivery_method === 'auto' ? 'badge-success' :
                            orderDetail.delivery_method === 'scheduled' ? 'badge-warning' :
                            'badge-gray'
                          }>
                            {orderDetail.delivery_method === 'manual' ? '手动发货' :
                             orderDetail.delivery_method === 'auto' ? '自动发货' :
                             orderDetail.delivery_method === 'scheduled' ? '定时发货' :
                             orderDetail.delivery_method}
                          </span>
                        ) : (
                          <span className="text-gray-400">未发货</span>
                        )}
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">订单类型</span>
                        {orderDetail.is_agent_order ? (
                          <span className="badge-info">代销订单</span>
                        ) : (
                          <span className="badge-gray">自营订单</span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* 发货内容 */}
                  {orderDetail.delivery_content && (
                    <div>
                      <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">发货内容</h3>
                      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 text-sm">
                        <pre className="whitespace-pre-wrap break-words text-gray-700 dark:text-gray-300">
                          {orderDetail.delivery_content}
                        </pre>
                      </div>
                    </div>
                  )}

                  {/* 发货失败原因 */}
                  {orderDetail.delivery_fail_reason && (
                    <div>
                      <h3 className="text-sm font-medium text-red-600 dark:text-red-400 mb-2">发货失败原因</h3>
                      <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 text-sm">
                        <pre className="whitespace-pre-wrap break-words text-red-700 dark:text-red-300">
                          {orderDetail.delivery_fail_reason}
                        </pre>
                      </div>
                    </div>
                  )}

                  {/* 关联消息日志：发送状态 */}
                  {orderDetail.delivery_send_status && (
                    <div>
                      <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">消息发送状态</h3>
                      <div className="bg-gray-50 dark:bg-gray-800 rounded-lg p-3 text-sm space-y-2">
                        <div className="flex items-center gap-2">
                          <span className="text-gray-500">发送状态</span>
                          <span className={
                            orderDetail.delivery_send_status === 'success' ? 'badge-success' :
                            orderDetail.delivery_send_status === 'failed' ? 'badge-danger' :
                            orderDetail.delivery_send_status === 'timeout' ? 'badge-warning' :
                            'badge-gray'
                          }>
                            {orderDetail.delivery_send_status === 'success' ? '发送成功' :
                             orderDetail.delivery_send_status === 'failed' ? '发送失败' :
                             orderDetail.delivery_send_status === 'timeout' ? '超时' :
                             '待确认'}
                          </span>
                        </div>
                        {orderDetail.delivery_send_fail_reason ? (
                          <pre className="whitespace-pre-wrap break-words text-red-700 dark:text-red-300">
                            {orderDetail.delivery_send_fail_reason}
                          </pre>
                        ) : null}
                      </div>
                    </div>
                  )}

                  {/* 商品信息 */}
                  <div>
                    <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">商品信息</h3>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">规格名称</span>
                        <span>{orderDetail.spec_name || '无'}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">规格值</span>
                        <span>{orderDetail.spec_value || '无'}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">数量</span>
                        <span>{orderDetail.quantity || 1}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">金额</span>
                        <span className="text-amber-600 font-medium">¥{orderDetail.amount || '0.00'}</span>
                      </div>
                    </div>
                  </div>

                  {/* 时间信息 */}
                  <div>
                    <h3 className="text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">时间信息</h3>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">订单时间</span>
                        <span>{orderDetail.placed_at ? new Date(orderDetail.placed_at).toLocaleString('zh-CN') : '未知'}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">创建时间</span>
                        <span>{orderDetail.created_at ? new Date(orderDetail.created_at).toLocaleString('zh-CN') : '未知'}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-gray-100 dark:border-gray-700">
                        <span className="text-gray-500">更新时间</span>
                        <span>{orderDetail.updated_at ? new Date(orderDetail.updated_at).toLocaleString('zh-CN') : '未知'}</span>
                      </div>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="text-center py-8 text-gray-500">暂无数据</div>
              )}
            </div>
            <div className="modal-footer">
              <button onClick={() => setDetailModalOpen(false)} className="btn-ios-secondary">
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 删除确认弹窗 */}
      <ConfirmModal
        isOpen={deleteConfirm.open}
        title="删除确认"
        message="确定要删除这个订单吗？删除后无法恢复。"
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={() => deleteConfirm.id && handleDelete(deleteConfirm.id)}
        onCancel={() => setDeleteConfirm({ open: false, id: null })}
      />

      {/* 批量删除确认弹窗 */}
      <ConfirmModal
        isOpen={batchDeleteConfirm}
        title="批量删除确认"
        message={`确定要删除选中的 ${selectedOrderIds.size} 个订单吗？删除后无法恢复。`}
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={handleBatchDelete}
        onCancel={() => setBatchDeleteConfirm(false)}
      />

      {/* 发货确认弹窗 */}
      <ConfirmModal
        isOpen={deliveryConfirm.open}
        title="发货确认"
        message="确定要手动发货吗？"
        confirmText="确定发货"
        cancelText="取消"
        type="warning"
        onConfirm={() => deliveryConfirm.orderNo && handleManualDelivery(deliveryConfirm.orderNo)}
        onCancel={() => setDeliveryConfirm({ open: false, orderNo: null })}
      />

      {/* 列设置面板 */}
      {columnSettingsOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={() => setColumnSettingsOpen(false)}>
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-xl w-full max-w-md mx-4" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3 className="modal-title">列显示设置</h3>
              <button onClick={() => setColumnSettingsOpen(false)} className="modal-close">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="modal-body max-h-[60vh] overflow-y-auto">
              <div className="space-y-2">
                {columns.map(col => (
                  <label
                    key={col.key}
                    className={`flex items-center justify-between p-3 rounded-lg border transition-colors cursor-pointer ${
                      col.visible
                        ? 'border-blue-200 bg-blue-50 dark:border-blue-800 dark:bg-blue-900/20'
                        : 'border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700/50'
                    } ${col.fixed ? 'opacity-100' : ''}`}
                  >
                    <div className="flex items-center gap-3">
                      <input
                        type="checkbox"
                        checked={col.visible}
                        onChange={() => !col.fixed && toggleColumn(col.key)}
                        disabled={col.fixed}
                        className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
                      />
                      <span className={`text-sm ${col.fixed ? 'font-medium' : ''}`}>
                        {col.label}
                        {col.fixed && <span className="ml-2 text-xs text-gray-400">(固定)</span>}
                      </span>
                    </div>
                  </label>
                ))}
              </div>
            </div>
            <div className="modal-footer flex justify-between">
              <button onClick={resetColumns} className="btn-ios-secondary">
                恢复默认
              </button>
              <button onClick={() => setColumnSettingsOpen(false)} className="btn-ios-primary">
                确定
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 拉黑级别选择弹窗 */}
      {blacklistModal.open && (
        <BlacklistLevelModal
          orders={blacklistModal.orders}
          onClose={() => setBlacklistModal({ open: false, orders: [] })}
          onSuccess={() => {
            setBlacklistModal({ open: false, orders: [] })
            setSelectedOrderIds(new Set())
          }}
        />
      )}
    </div>
  )
}
