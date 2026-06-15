import { useState, useEffect } from 'react'
import { ShoppingCart, ChevronLeft, ChevronRight } from 'lucide-react'
import { getOrders, deleteOrder, getOrderDetail, type OrderDetail } from '@/api/orders'
import { Button, Descriptions, Empty, Form, Input, Modal, Popconfirm, Select as ArcoSelect, Space, Spin, Table, Tag } from '@arco-design/web-react'
import type { TableColumnProps } from '@arco-design/web-react'
import { getAccounts } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import type { Order, Account } from '@/types'

const statusMap: Record<string, { label: string; color: string }> = {
  processing: { label: '处理中', color: 'orange' },
  pending_ship: { label: '待发货', color: 'arcoblue' },
  processed: { label: '已处理', color: 'arcoblue' },
  shipped: { label: '已发货', color: 'green' },
  completed: { label: '已完成', color: 'green' },
  refunding: { label: '退款中', color: 'orange' },
  refund_cancelled: { label: '退款撤销', color: 'arcoblue' },
  cancelled: { label: '已关闭', color: 'red' },
  unknown: { label: '未知', color: 'gray' },
}

export function Orders() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [orders, setOrders] = useState<Order[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')
  const [selectedStatus, setSelectedStatus] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [orderDetail, setOrderDetail] = useState<OrderDetail | null>(null)
  const [loadingDetail, setLoadingDetail] = useState(false)
  // 分页状态
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)

  const loadOrders = async (page: number = currentPage) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getOrders(selectedAccount || undefined, selectedStatus || undefined, page, pageSize)
      if (result.success) {
        const nextOrders = result.data || []
        setOrders(nextOrders)
        setTotal(result.total || nextOrders.length)
        setTotalPages(result.total_pages || 0)
        setCurrentPage(page)
      }
    } catch {
      addToast({ type: 'error', message: '加载订单列表失败' })
    } finally {
      setLoading(false)
    }
  }

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const data = await getAccounts()
      setAccounts(data)
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadAccounts()
    loadOrders(1)
  }, [_hasHydrated, isAuthenticated, token])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    setCurrentPage(1)
    loadOrders(1)
  }, [_hasHydrated, isAuthenticated, token, selectedAccount, selectedStatus])

  const handleDelete = async (id: string) => {
    try {
      const result = await deleteOrder(id)
      if (result.success) {
        addToast({ type: 'success', message: '删除成功' })
        loadOrders()
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    }
  }

  const handleShowDetail = async (orderNo: string) => {
    setLoadingDetail(true)
    setDetailModalOpen(true)
    try {
      const result = await getOrderDetail(orderNo)
      if (result.success && result.data) {
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

  const filteredOrders = orders.filter((order) => {
    if (!searchKeyword) return true
    const keyword = searchKeyword.toLowerCase()
    return (
      order.order_id?.toLowerCase().includes(keyword) ||
      order.item_id?.toLowerCase().includes(keyword) ||
      order.buyer_id?.toLowerCase().includes(keyword)
    )
  })

  const orderColumns: TableColumnProps<Order>[] = [
    {
      title: '订单ID',
      dataIndex: 'order_id',
      width: 150,
      render: (value: string) => <span className="font-mono orders-nowrap-cell">{value}</span>,
    },
    {
      title: '商品ID',
      dataIndex: 'item_id',
      width: 150,
      render: (value: string) => <span className="font-mono orders-nowrap-cell">{value || '-'}</span>,
    },
    {
      title: '买家ID',
      dataIndex: 'buyer_id',
      width: 120,
      render: (value: string) => <span className="orders-nowrap-cell">{value || '-'}</span>,
    },
    { title: '数量', dataIndex: 'quantity', width: 50 },
    {
      title: '金额',
      dataIndex: 'amount',
      width: 60,
      render: (amount: string) => <span className="text-gray-900 font-medium orders-nowrap-cell">¥{amount}</span>,
    },
    {
      title: '状态',
      dataIndex: 'status',
      width: 70,
      render: (value: string) => {
        const status = statusMap[value] || statusMap.unknown

        return (
          <Tag color={status.color} className="table-status-tag">
            {status.label}
          </Tag>
        )
      },
    },
    {
      title: '小刀',
      dataIndex: 'is_bargain',
      width: 80,
      render: (isBargain: boolean) => (
        isBargain ? (
          <Tag color="orange" className="table-status-tag">是</Tag>
        ) : (
          <Tag color="gray" className="table-status-tag">否</Tag>
        )
      ),
    },
    {
      title: '账号ID',
      dataIndex: 'cookie_id',
      width: 140,
      render: (cookieId: string) => <span className="text-slate-700 dark:text-slate-200 orders-nowrap-cell">{cookieId || '-'}</span>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 150,
      render: (createdAt?: string) => (
        <span className="text-gray-500 orders-nowrap-cell">
          {createdAt ? new Date(createdAt).toLocaleString('zh-CN') : '-'}
        </span>
      ),
    },
    {
      title: '操作',
      dataIndex: 'operation',
      width: 140,
      fixed: 'right',
      render: (_value, order) => (
        <Space size={8}>
          <Button 
            type="text" className="accounts-table-action-btn" onClick={() => handleShowDetail(order.order_id)}>
            查看
          </Button>
          <Popconfirm
            title="确定要删除这个订单吗？"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ status: 'danger' }}
            onOk={() => handleDelete(order.id)}
          >
            <Button
              type="text"
              className="accounts-table-action-btn !text-red-500 hover:!text-red-500"
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  if (loading && orders.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-3 sm:space-y-4">
      {/* Orders List */}
      <div
        className="vben-card"
      >
        <div className="accounts-page-intro">
          <h1>订单管理</h1>
          <p>查看和管理所有订单信息</p>
        </div>
        <div className="table-toolbar">
          <div className="table-filter-row table-filter-row--lined">
            <Form layout="inline" className="table-filter-form">
              <Form.Item label="筛选账号">
                <ArcoSelect
                  allowClear
                  value={selectedAccount || undefined}
                  onChange={(value) => setSelectedAccount(value || '')}
                  placeholder="所有账号"
                  style={{ width: 180 }}
                  options={[
                    { value: '', label: '所有账号' },
                    ...accounts.map((account) => ({
                      value: account.id,
                      label: account.id,
                    })),
                  ]}
                />
              </Form.Item>

              <Form.Item label="订单状态">
                <ArcoSelect
                  allowClear
                  value={selectedStatus || undefined}
                  onChange={(value) => setSelectedStatus(value || '')}
                  placeholder="所有状态"
                  style={{ width: 180 }}
                  options={[
                    { value: '', label: '所有状态' },
                    { value: 'processing', label: '处理中' },
                    { value: 'pending_ship', label: '待发货' },
                    { value: 'shipped', label: '已发货' },
                    { value: 'completed', label: '已完成' },
                    { value: 'refunding', label: '退款中' },
                    { value: 'cancelled', label: '已关闭' },
                  ]}
                />
              </Form.Item>

              <Form.Item label="搜索订单">
                <Input
                  allowClear
                  value={searchKeyword}
                  onChange={setSearchKeyword}
                  placeholder="搜索订单ID或商品ID"
                  style={{ width: 200, borderRadius: 8 }}
                />
              </Form.Item>
            </Form>
            <Space className="table-toolbar-right">
              <Button onClick={() => loadOrders(currentPage)}>刷新</Button>
            </Space>
          </div>
        </div>
        <Table
          rowKey="id"
          columns={orderColumns}
          data={filteredOrders}
          pagination={false}
          border={false}
          scroll={{ x: 1400 }}
          className="accounts-arco-table orders-arco-table table-main"
          noDataElement={(
            <Empty
              icon={<ShoppingCart className="w-12 h-12 text-gray-300" />}
              description="暂无订单数据"
            />
          )}
        />

        {/* 分页 */}
        {totalPages > 0 && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700">
            <div className="text-sm text-gray-500">
              第 {currentPage} 页，共 {totalPages} 页，{total} 条记录
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => loadOrders(currentPage - 1)}
                disabled={currentPage <= 1 || loading}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title="上一页"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <div className="flex items-center gap-1">
                {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                  let pageNum: number
                  if (totalPages <= 5) {
                    pageNum = i + 1
                  } else if (currentPage <= 3) {
                    pageNum = i + 1
                  } else if (currentPage >= totalPages - 2) {
                    pageNum = totalPages - 4 + i
                  } else {
                    pageNum = currentPage - 2 + i
                  }
                  return (
                    <button
                      key={pageNum}
                      onClick={() => loadOrders(pageNum)}
                      disabled={loading}
                      className={`w-8 h-8 rounded-lg text-sm transition-colors ${currentPage === pageNum
                        ? 'bg-blue-500 text-white'
                        : 'hover:bg-gray-100 dark:hover:bg-gray-800'
                        }`}
                    >
                      {pageNum}
                    </button>
                  )
                })}
              </div>
              <button
                onClick={() => loadOrders(currentPage + 1)}
                disabled={currentPage >= totalPages || loading}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                title="下一页"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 订单详情弹窗 */}
      <Modal
        visible={detailModalOpen}
        title="订单详情"
        footer={null}
        onCancel={() => setDetailModalOpen(false)}
        unmountOnExit
        className="accounts-arco-modal"
      >
        {loadingDetail ? (
          <div className="flex items-center justify-center py-8">
            <Spin tip="加载中..." />
          </div>
        ) : orderDetail ? (
          <div className="space-y-4">
            <Descriptions
              column={2}
              title="基本信息"
              data={[
                { label: '订单ID', value: <span className="font-mono">{orderDetail.order_id}</span> },
                { label: '商品ID', value: orderDetail.item_id || '未知' },
                { label: '买家ID', value: orderDetail.buyer_id || '未知' },
                { label: '账号ID', value: orderDetail.cookie_id || '未知' },
                { label: '订单状态', value: <Tag color={(statusMap[orderDetail.status] || statusMap.unknown).color}>{(statusMap[orderDetail.status] || statusMap.unknown).label}</Tag> },
                { label: '是否小刀', value: <Tag color={orderDetail.is_bargain ? 'orange' : 'gray'}>{orderDetail.is_bargain ? '是' : '否'}</Tag> },
              ]}
            />
            <Descriptions
              column={2}
              title="商品信息"
              data={[
                { label: '规格名称', value: orderDetail.spec_name || '无' },
                { label: '规格值', value: orderDetail.spec_value || '无' },
                { label: '数量', value: orderDetail.quantity || 1 },
                { label: '金额', value: `¥${orderDetail.amount || '0.00'}` },
              ]}
            />
            <Descriptions
              column={2}
              title="时间信息"
              data={[
                { label: '创建时间', value: orderDetail.created_at ? new Date(orderDetail.created_at).toLocaleString('zh-CN') : '未知' },
                { label: '更新时间', value: orderDetail.updated_at ? new Date(orderDetail.updated_at).toLocaleString('zh-CN') : '未知' },
              ]}
            />
          </div>
        ) : (
          <div className="text-center py-8 text-gray-500">暂无数据</div>
        )}
        <div className="modal-footer px-0 pb-0">
          <Button onClick={() => setDetailModalOpen(false)}>关闭</Button>
        </div>
      </Modal>
    </div>
  )
}
