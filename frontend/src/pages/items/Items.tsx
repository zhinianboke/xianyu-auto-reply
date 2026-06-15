import { Button, Checkbox, Empty, Form, Input, Modal, Popconfirm, Select as ArcoSelect, Space, Spin, Table, Tag, Typography, type TableColumnProps } from '@arco-design/web-react'
import { useEffect, useState, useRef } from 'react'
import { ChevronDown, ExternalLink, Package, X, ImagePlus } from 'lucide-react'
import { batchDeleteItems, deleteItem, fetchAllItemsFromAccount, getItems, updateItem, updateItemMultiQuantityDelivery, updateItemMultiSpec, getItemDefaultReply, saveItemDefaultReply, deleteItemDefaultReply, batchSaveItemDefaultReply, batchDeleteItemDefaultReply, uploadItemDefaultReplyImage } from '@/api/items'
import { getAccounts } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import { useAuthStore } from '@/store/authStore'
import { ActionMenu } from '@/components/common/ActionMenu'
import type { Account, Item } from '@/types'

interface ItemTableRow extends Item {
  key: string | number
}

const TAG_STYLE = { borderRadius: 4 }
const { Text } = Typography
const { TextArea } = Input

export function Items() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState<Item[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')
  const [searchKeyword, setSearchKeyword] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string | number>>(new Set())
  const [fetching, setFetching] = useState(false)

  // 编辑弹窗状态
  const [editingItem, setEditingItem] = useState<Item | null>(null)
  const [editDetail, setEditDetail] = useState('')
  const [editSaving, setEditSaving] = useState(false)

  // 商品默认回复弹窗状态
  const [defaultReplyItem, setDefaultReplyItem] = useState<Item | null>(null)
  const [defaultReplyContent, setDefaultReplyContent] = useState('')
  const [defaultReplyImage, setDefaultReplyImage] = useState('')
  const [defaultReplyEnabled, setDefaultReplyEnabled] = useState(true)
  const [defaultReplyOnce, setDefaultReplyOnce] = useState(false)
  const [defaultForbiddenKeywords, setDefaultForbiddenKeywords] = useState('')
  const [defaultForbiddenAction, setDefaultForbiddenAction] = useState<'ignore' | 'fixed_reply'>('ignore')
  const [defaultForbiddenReplyContent, setDefaultForbiddenReplyContent] = useState('')
  const [loadingDefaultReply, setLoadingDefaultReply] = useState(false)
  const [savingDefaultReply, setSavingDefaultReply] = useState(false)
  const [defaultReplyImageUploading, setDefaultReplyImageUploading] = useState(false)
  const defaultReplyImageInputRef = useRef<HTMLInputElement>(null)

  // 批量默认回复弹窗状态
  const [showBatchDefaultReplyModal, setShowBatchDefaultReplyModal] = useState(false)
  const [batchReplyContent, setBatchReplyContent] = useState('')
  const [batchReplyImage, setBatchReplyImage] = useState('')
  const [batchReplyEnabled, setBatchReplyEnabled] = useState(true)
  const [batchReplyOnce, setBatchReplyOnce] = useState(false)
  const [batchForbiddenKeywords, setBatchForbiddenKeywords] = useState('')
  const [batchForbiddenAction, setBatchForbiddenAction] = useState<'ignore' | 'fixed_reply'>('ignore')
  const [batchForbiddenReplyContent, setBatchForbiddenReplyContent] = useState('')
  const [savingBatchReply, setSavingBatchReply] = useState(false)
  const [batchReplyImageUploading, setBatchReplyImageUploading] = useState(false)
  const batchReplyImageInputRef = useRef<HTMLInputElement>(null)

  // 删除确认状态
  const [deleteDefaultReplyConfirm, setDeleteDefaultReplyConfirm] = useState(false)
  const [batchDeleteDefaultReplyConfirm, setBatchDeleteDefaultReplyConfirm] = useState(false)

  const loadItems = async (options: { showLoading?: boolean } = {}) => {
    if (!_hasHydrated || !isAuthenticated || !token) {
      return
    }
    const showLoading = options.showLoading ?? true
    try {
      if (showLoading) {
        setLoading(true)
      }
      const result = await getItems(selectedAccount || undefined)
      if (result.success) {
        setItems(result.data || [])
      }
    } catch {
      addToast({ type: 'error', message: '加载商品列表失败' })
    } finally {
      if (showLoading) {
        setLoading(false)
      }
    }
  }


  const handleFetchItems = async () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号后再获取商品' })
      return
    }

    setFetching(true)

    try {
      const result = await fetchAllItemsFromAccount(selectedAccount)

      if (result.success) {
        const totalCount = (result as { total_count?: number }).total_count || 0
        const savedCount = (result as { saved_count?: number }).saved_count || 0
        addToast({ type: 'success', message: `成功获取商品，共 ${totalCount} 件，保存 ${savedCount} 件` })
        await loadItems()
      } else {
        addToast({ type: 'error', message: (result as { message?: string }).message || '获取商品失败' })
      }
    } catch {
      addToast({ type: 'error', message: '获取商品失败' })
    } finally {
      setFetching(false)
    }
  }

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) {
      return
    }
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
    loadItems()
  }, [_hasHydrated, isAuthenticated, token])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadItems()
  }, [_hasHydrated, isAuthenticated, token, selectedAccount])

  const handleDelete = async (item: Item) => {
    try {
      await deleteItem(item.cookie_id, item.item_id)
      addToast({ type: 'success', message: '删除成功' })
      loadItems()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    }
  }

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) {
      addToast({ type: 'warning', message: '请先选择要删除的商品' })
      return
    }
    Modal.confirm({
      title: '确认删除',
      content: `确定要删除选中的 ${selectedIds.size} 个商品吗？`,
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { status: 'danger' },
      onOk: async () => {
        try {
          const itemsToDelete = items
            .filter((item) => selectedIds.has(item.id))
            .map((item) => ({ cookie_id: item.cookie_id, item_id: item.item_id }))
          await batchDeleteItems(itemsToDelete)
          addToast({ type: 'success', message: `成功删除 ${selectedIds.size} 个商品` })
          setSelectedIds(new Set())
          loadItems()
        } catch {
          addToast({ type: 'error', message: '批量删除失败' })
        }
      },
    })
  }

  // 切换多数量发货状态
  const handleToggleMultiQuantity = async (item: Item) => {
    try {
      const newStatus = !item.multi_quantity_delivery
      await updateItemMultiQuantityDelivery(item.cookie_id, item.item_id, newStatus)
      addToast({ type: 'success', message: `多数量发货已${newStatus ? '开启' : '关闭'}` })
      await loadItems({ showLoading: false })
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  // 切换多规格状态
  const handleToggleMultiSpec = async (item: Item) => {
    try {
      const newStatus = !(item.is_multi_spec || item.has_sku)
      await updateItemMultiSpec(item.cookie_id, item.item_id, newStatus)
      addToast({ type: 'success', message: `多规格已${newStatus ? '开启' : '关闭'}` })
      await loadItems({ showLoading: false })
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  // 打开编辑弹窗
  const handleEdit = (item: Item) => {
    setEditingItem(item)
    setEditDetail(item.item_detail || item.desc || '')
  }

  // 保存编辑
  const handleSaveEdit = async () => {
    if (!editingItem) return
    setEditSaving(true)
    try {
      await updateItem(editingItem.cookie_id, editingItem.item_id, {
        item_detail: editDetail,
      })
      addToast({ type: 'success', message: '商品详情已更新' })
      setEditingItem(null)
      loadItems()
    } catch {
      addToast({ type: 'error', message: '更新失败' })
    } finally {
      setEditSaving(false)
    }
  }


  // 打开默认回复配置弹窗
  const handleOpenDefaultReply = async (item: Item) => {
    setDefaultReplyItem(item)
    setDefaultReplyImage('')
    setLoadingDefaultReply(true)

    try {
      const result = await getItemDefaultReply(item.cookie_id, item.item_id)
      if (result.success && result.data) {
        setDefaultReplyContent(result.data.reply_content || '')
        setDefaultReplyImage(result.data.reply_image || '')
        setDefaultReplyEnabled(result.data.enabled ?? true)
        setDefaultReplyOnce(result.data.reply_once ?? false)
        setDefaultForbiddenKeywords(result.data.forbidden_keywords || '')
        setDefaultForbiddenAction(result.data.forbidden_action || 'ignore')
        setDefaultForbiddenReplyContent(result.data.forbidden_reply_content || '')
      } else {
        setDefaultReplyContent('')
        setDefaultReplyImage('')
        setDefaultReplyEnabled(true)
        setDefaultReplyOnce(false)
        setDefaultForbiddenKeywords('')
        setDefaultForbiddenAction('ignore')
        setDefaultForbiddenReplyContent('')
      }
    } catch {
      setDefaultReplyContent('')
      setDefaultReplyImage('')
      setDefaultReplyEnabled(true)
      setDefaultReplyOnce(false)
      setDefaultForbiddenKeywords('')
      setDefaultForbiddenAction('ignore')
      setDefaultForbiddenReplyContent('')
    } finally {
      setLoadingDefaultReply(false)
    }
  }

  // 关闭默认回复配置弹窗
  const closeDefaultReply = () => {
    setDefaultReplyItem(null)
    setDefaultReplyContent('')
    setDefaultReplyImage('')
    setDefaultReplyEnabled(true)
    setDefaultReplyOnce(false)
    setDefaultForbiddenKeywords('')
    setDefaultForbiddenAction('ignore')
    setDefaultForbiddenReplyContent('')
    setDeleteDefaultReplyConfirm(false)
  }

  // 保存默认回复配置
  const handleSaveDefaultReply = async () => {
    if (!defaultReplyItem) return
    setSavingDefaultReply(true)

    try {
      await saveItemDefaultReply(defaultReplyItem.cookie_id, defaultReplyItem.item_id, {
        reply_content: defaultReplyContent,
        reply_image_url: defaultReplyImage,
        enabled: defaultReplyEnabled,
        reply_once: defaultReplyOnce,
        forbidden_keywords: defaultForbiddenKeywords,
        forbidden_action: defaultForbiddenAction,
        forbidden_reply_content: defaultForbiddenReplyContent,
      })
      addToast({ type: 'success', message: '商品默认回复保存成功' })
      closeDefaultReply()
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setSavingDefaultReply(false)
    }
  }

  // 删除默认回复配置
  const handleDeleteDefaultReply = async () => {
    if (!defaultReplyItem) return

    try {
      await deleteItemDefaultReply(defaultReplyItem.cookie_id, defaultReplyItem.item_id)
      addToast({ type: 'success', message: '商品默认回复已删除' })
      closeDefaultReply()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    }
  }

  // 上传默认回复图片
  const handleDefaultReplyImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !defaultReplyItem) return

    setDefaultReplyImageUploading(true)
    try {
      const result = await uploadItemDefaultReplyImage(defaultReplyItem.cookie_id, defaultReplyItem.item_id, file)
      if (result.success && result.image_url) {
        setDefaultReplyImage(result.image_url)
        addToast({ type: 'success', message: '图片上传成功' })
      } else {
        addToast({ type: 'error', message: result.message || '图片上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '图片上传失败' })
    } finally {
      setDefaultReplyImageUploading(false)
      if (defaultReplyImageInputRef.current) {
        defaultReplyImageInputRef.current.value = ''
      }
    }
  }

  // 打开批量默认回复弹窗
  const handleOpenBatchDefaultReply = () => {
    if (selectedIds.size === 0) {
      addToast({ type: 'warning', message: '请先选择商品' })
      return
    }
    setBatchReplyContent('')
    setBatchReplyImage('')
    setBatchReplyEnabled(true)
    setBatchReplyOnce(false)
    setBatchForbiddenKeywords('')
    setBatchForbiddenAction('ignore')
    setBatchForbiddenReplyContent('')
    setShowBatchDefaultReplyModal(true)
  }

  const handleOpenBatchDeleteDefaultReplyConfirm = () => {
    if (selectedIds.size === 0) {
      addToast({ type: 'warning', message: '请先选择商品' })
      return
    }
    setBatchDeleteDefaultReplyConfirm(true)
  }

  // 保存批量默认回复
  const handleSaveBatchDefaultReply = async () => {
    if (selectedIds.size === 0) return

    const selectedItems = items.filter((item) => selectedIds.has(item.id))
    const cookieId = selectedItems[0]?.cookie_id
    if (!cookieId) return

    // 检查是否所有选中的商品都属于同一个账号
    const allSameCookie = selectedItems.every((item) => item.cookie_id === cookieId)
    if (!allSameCookie) {
      addToast({ type: 'error', message: '批量操作只能针对同一账号的商品' })
      return
    }

    setSavingBatchReply(true)
    try {
      const itemIds = selectedItems.map((item) => item.item_id)
      await batchSaveItemDefaultReply(cookieId, {
        item_ids: itemIds,
        reply_content: batchReplyContent,
        reply_image_url: batchReplyImage,
        enabled: batchReplyEnabled,
        reply_once: batchReplyOnce,
        forbidden_keywords: batchForbiddenKeywords,
        forbidden_action: batchForbiddenAction,
        forbidden_reply_content: batchForbiddenReplyContent,
      })
      addToast({ type: 'success', message: `批量保存成功，共 ${itemIds.length} 个商品` })
      setShowBatchDefaultReplyModal(false)
      setSelectedIds(new Set())
    } catch {
      addToast({ type: 'error', message: '批量保存失败' })
    } finally {
      setSavingBatchReply(false)
    }
  }

  // 上传批量默认回复图片
  const handleBatchReplyImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    setBatchReplyImageUploading(true)
    try {
      // 使用通用图片上传接口
      const formData = new FormData()
      formData.append('image', file)
      const response = await fetch('/upload-image', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
        body: formData,
      })
      const result = await response.json()
      if (result.image_url) {
        setBatchReplyImage(result.image_url)
        addToast({ type: 'success', message: '图片上传成功' })
      } else {
        addToast({ type: 'error', message: result.detail || result.message || '图片上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '图片上传失败' })
    } finally {
      setBatchReplyImageUploading(false)
      if (batchReplyImageInputRef.current) {
        batchReplyImageInputRef.current.value = ''
      }
    }
  }

  // 批量删除默认回复
  const handleBatchDeleteDefaultReply = async () => {
    if (selectedIds.size === 0) return

    const selectedItems = items.filter((item) => selectedIds.has(item.id))
    const cookieId = selectedItems[0]?.cookie_id
    if (!cookieId) return

    const allSameCookie = selectedItems.every((item) => item.cookie_id === cookieId)
    if (!allSameCookie) {
      addToast({ type: 'error', message: '批量操作只能针对同一账号的商品' })
      return
    }

    try {
      const itemIds = selectedItems.map((item) => item.item_id)
      await batchDeleteItemDefaultReply(cookieId, itemIds)
      addToast({ type: 'success', message: `批量删除成功，共 ${itemIds.length} 个商品` })
      setBatchDeleteDefaultReplyConfirm(false)
      setSelectedIds(new Set())
    } catch {
      addToast({ type: 'error', message: '批量删除失败' })
    }
  }

  const filteredItems = items.filter((item) => {
    if (!searchKeyword) return true
    const keyword = searchKeyword.toLowerCase()
    const title = item.item_title || item.title || ''
    const desc = item.item_detail || item.desc || ''
    return (
      title.toLowerCase().includes(keyword) ||
      desc.toLowerCase().includes(keyword) ||
      item.item_id?.includes(keyword)
    )
  })

  const columns: TableColumnProps<ItemTableRow>[] = [
    {
      title: '账号ID',
      dataIndex: 'cookie_id',
      width: 150,
      render: (cookieId: string) => (
        <span>{cookieId}</span>
      ),
    },
    {
      title: '商品ID',
      dataIndex: 'item_id',
      width: 150,
      render: (itemId: string) => (
        <a
          href={`https://www.goofish.com/item?id=${itemId}`}
          target="_blank"
          rel="noopener noreferrer"
          className="hover:text-blue-500 flex items-center gap-1 text-xs text-gray-500"
        >
          {itemId}
          <ExternalLink className="w-3 h-3" />
        </a>
      ),
    },
    {
      title: '商品标题',
      dataIndex: 'item_title',
      width: 180,
      render: (_value, item) => (
        <div>
          <div
            className="line-clamp-2 cursor-help"
            title={item.item_title || item.title || '-'}
          >
            {item.item_title || item.title || '-'}
          </div>
          {/* {(item.item_detail || item.desc) && (
            <div
              className="text-xs text-gray-400 line-clamp-1 mt-0.5 cursor-help"
              title={item.item_detail || item.desc}
            >
              {item.item_detail || item.desc}
            </div>
          )} */}
        </div>
      ),
    },
    {
      title: '价格',
      dataIndex: 'item_price',
      width: 100,
      render: (_value, item) => (
        <span className="font-semibold text-red-500">
          {item.item_price || (item.price ? `¥${item.price}` : '-')}
        </span>
      ),
    },
    {
      title: '多规格',
      dataIndex: 'is_multi_spec',
      width: 110,
      render: (_value, item) => {
        const enabled = item.is_multi_spec || item.has_sku
        return (
          <Tag
            color={enabled ? 'green' : 'gray'}
            style={{ ...TAG_STYLE, cursor: 'pointer' }}
            onClick={() => handleToggleMultiSpec(item)}
          >
            {enabled ? '已开启' : '已关闭'}
          </Tag>
        )
      },
    },
    {
      title: '多数量发货',
      dataIndex: 'multi_quantity_delivery',
      width: 130,
      render: (enabled: boolean, item) => (
        <Tag
          color={enabled ? 'arcoblue' : 'gray'}
          style={{ ...TAG_STYLE, cursor: 'pointer' }}
          onClick={() => handleToggleMultiQuantity(item)}
        >
          {enabled ? '已开启' : '已关闭'}
        </Tag>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 180,
      render: (updatedAt?: string) => (
        <span className="text-gray-500 text-xs">
          {updatedAt ? new Date(updatedAt).toLocaleString() : '-'}
        </span>
      ),
    },
    {
      title: '操作',
      dataIndex: 'operation',
      width: 220,
      fixed: 'right',
      render: (_value, item) => (
        <Space size={8}>
          <Button type="text" className="accounts-table-action-btn" onClick={() => handleOpenDefaultReply(item)}>
            默认回复
          </Button>
          <Button type="text" className="accounts-table-action-btn" onClick={() => handleEdit(item)}>
            编辑
          </Button>
          <Popconfirm
            title="确定要删除这个商品吗？"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ status: 'danger' }}
            onOk={() => handleDelete(item)}
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

  const tableData: ItemTableRow[] = filteredItems.map((item) => ({
    ...item,
    key: item.id,
  }))

  if (loading) {
    return <PageLoading />
  }


  return (
    <div className="space-y-4">
      <div className="vben-card">
        {/* 标题区 */}
        <div className="accounts-page-intro">
          <h1>商品管理</h1>
          <p>管理各账号的商品信息</p>
        </div>

        {/* 筛选栏 + 操作按钮 */}
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
              <Form.Item label="关键词">
                <Input
                  allowClear
                  value={searchKeyword}
                  onChange={setSearchKeyword}
                  placeholder="输入商品型号或名称"
                  style={{ width: 200, borderRadius: 8 }}
                />
              </Form.Item>
              <Space className="table-filter-actions">
                <Button type="primary">查询</Button>
                <Button onClick={() => {
                  setSearchKeyword('')
                  setSelectedAccount('')
                }}>重置</Button>
              </Space>
            </Form>
          </div>
          <div className="table-action-row">
            <Space className="batch-actions">
              <Button
                type="primary"
                loading={fetching}
                onClick={handleFetchItems}>获取商品</Button>
              <ActionMenu
                trigger={(
                  <Button className="accounts-header-btn">
                    操作
                    <ChevronDown />
                  </Button>
                )}
                items={[
                  { key: 'default-reply', label: '批量默认回复' },
                  { key: 'delete-reply', label: '批量删除回复' },
                  {
                    key: 'delete-items',
                    label: `删除选中${selectedIds.size > 0 ? ` (${selectedIds.size})` : ''}`,
                    danger: true,
                  },
                ]}
                onSelect={(key) => {
                  if (key === 'default-reply') handleOpenBatchDefaultReply()
                  if (key === 'delete-reply') handleOpenBatchDeleteDefaultReplyConfirm()
                  if (key === 'delete-items') handleBatchDelete()
                }}
                menuClassName="min-w-36"
              />
              <Button onClick={() => loadItems()}>刷新</Button>
            </Space>
          </div>
        </div>

        <Table
          rowKey="key"
          columns={columns}
          data={tableData}
          pagination={false}
          border={false}
          scroll={{ x: 1290 }}
          className="accounts-arco-table table-main"
          rowSelection={{
            type: 'checkbox',
            selectedRowKeys: Array.from(selectedIds),
            onChange: (selectedRowKeys) => {
              setSelectedIds(new Set(selectedRowKeys as Array<string | number>))
            },
          }}
          noDataElement={(
            <Empty
              icon={<Package className="w-12 h-12 text-gray-300" />}
              description="暂无商品数据"
            />
          )}
        />
      </div>


      {/* 编辑弹窗 */}
      <Modal
        visible={!!editingItem}
        title="编辑商品"
        footer={null}
        onCancel={() => setEditingItem(null)}
        unmountOnExit
        className="accounts-arco-modal"
      >
        {editingItem && (
          <>
            <Form layout="vertical">
              <Form.Item label="商品ID">
                <Input value={editingItem.item_id} disabled />
              </Form.Item>
              <Form.Item label="商品标题">
                <Input value={editingItem.item_title || editingItem.title || ''} disabled />
              </Form.Item>
              <Form.Item label="商品详情">
                <TextArea
                  value={editDetail}
                  onChange={setEditDetail}
                  autoSize={{ minRows: 6, maxRows: 10 }}
                  placeholder="输入商品详情..."
                />
              </Form.Item>
            </Form>
            <div className="modal-footer px-0 pb-0">
              <Button onClick={() => setEditingItem(null)} disabled={editSaving}>取消</Button>
              <Button type="primary" onClick={handleSaveEdit} loading={editSaving}>保存</Button>
            </div>
          </>
        )}
      </Modal>

      {/* 商品默认回复配置弹窗 */}
      <Modal
        visible={!!defaultReplyItem}
        title="商品默认回复配置"
        footer={null}
        onCancel={closeDefaultReply}
        unmountOnExit
        className="accounts-arco-modal !w-[960px] max-w-[96vw]"
      >
        {defaultReplyItem && (
          <>
            {loadingDefaultReply ? (
              <div className="flex items-center justify-center py-8">
                <Spin tip="加载中..." />
              </div>
            ) : (
              <Form layout="vertical">
                <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
                  <div>
                    <Form.Item label="商品信息">
                      <div className="rounded-lg border border-slate-200 px-3 py-2 dark:border-slate-700">
                        <Text className="block">ID: {defaultReplyItem.item_id}</Text>
                        <Text type="secondary" className="line-clamp-1 block">
                          {defaultReplyItem.item_title || defaultReplyItem.title || '-'}
                        </Text>
                      </div>
                    </Form.Item>
                    <Form.Item>
                      <Checkbox checked={defaultReplyEnabled} onChange={setDefaultReplyEnabled}>
                        启用商品默认回复
                      </Checkbox>
                    </Form.Item>
                    <Form.Item>
                      <Checkbox checked={defaultReplyOnce} onChange={setDefaultReplyOnce}>
                        只回复一次（同一用户只回复一次）
                      </Checkbox>
                    </Form.Item>
                    <Form.Item label="回复图片">
                      <div className="flex items-center gap-2">
                        <Input
                          value={defaultReplyImage}
                          onChange={setDefaultReplyImage}
                          placeholder="图片URL（可选）"
                        />
                        <input
                          type="file"
                          ref={defaultReplyImageInputRef}
                          onChange={handleDefaultReplyImageUpload}
                          accept="image/*"
                          className="hidden"
                        />
                        <Button
                          onClick={() => defaultReplyImageInputRef.current?.click()}
                          loading={defaultReplyImageUploading}
                        >
                          上传
                        </Button>
                      </div>
                      {defaultReplyImage && (
                        <div className="mt-2">
                          <img src={defaultReplyImage} alt="预览" className="max-h-24 rounded" />
                        </div>
                      )}
                    </Form.Item>
                  </div>
                  <div>
                    <Form.Item label="回复内容">
                      <TextArea
                        value={defaultReplyContent}
                        onChange={setDefaultReplyContent}
                        autoSize={{ minRows: 4, maxRows: 7 }}
                        placeholder="输入默认回复内容，支持变量：{send_user_name}、{send_user_id}、{send_message}、{item_id}"
                      />
                    </Form.Item>
                    <Form.Item label="商品违禁词">
                      <TextArea
                        value={defaultForbiddenKeywords}
                        onChange={setDefaultForbiddenKeywords}
                        autoSize={{ minRows: 4, maxRows: 6 }}
                        placeholder="输入违禁词，支持逗号、分号或换行分隔"
                      />
                    </Form.Item>
                    <Form.Item label="违禁词处理方式">
                      <ArcoSelect
                        value={defaultForbiddenAction}
                        onChange={(value) => setDefaultForbiddenAction(value as 'ignore' | 'fixed_reply')}
                        options={[
                          { label: '冷处理，不回复', value: 'ignore' },
                          { label: '固定回复', value: 'fixed_reply' },
                        ]}
                      />
                    </Form.Item>
                    {defaultForbiddenAction === 'fixed_reply' && (
                      <Form.Item label="违禁词固定回复">
                        <TextArea
                          value={defaultForbiddenReplyContent}
                          onChange={setDefaultForbiddenReplyContent}
                          autoSize={{ minRows: 4, maxRows: 6 }}
                          placeholder="命中违禁词后的固定回复话术"
                        />
                      </Form.Item>
                    )}
                  </div>
                </div>
              </Form>
            )}
            <div className="modal-footer px-0 pb-0">
              {!deleteDefaultReplyConfirm ? (
                <>
                  <Button
                    status="danger"
                    onClick={() => setDeleteDefaultReplyConfirm(true)}
                    disabled={loadingDefaultReply || savingDefaultReply}
                    className="mr-auto"
                  >
                    删除
                  </Button>
                  <Button onClick={closeDefaultReply} disabled={savingDefaultReply}>取消</Button>
                  <Button
                    type="primary"
                    onClick={handleSaveDefaultReply}
                    loading={savingDefaultReply}
                    disabled={loadingDefaultReply}
                  >
                    保存
                  </Button>
                </>
              ) : (
                <>
                  <Text type="error">确定要删除此商品的默认回复配置吗？</Text>
                  <Button onClick={() => setDeleteDefaultReplyConfirm(false)}>取消</Button>
                  <Button status="danger" onClick={handleDeleteDefaultReply}>确认删除</Button>
                </>
              )}
            </div>
          </>
        )}
      </Modal>


      {/* 批量默认回复弹窗 */}
      <Modal
        visible={showBatchDefaultReplyModal}
        title="批量设置默认回复"
        footer={null}
        onCancel={() => setShowBatchDefaultReplyModal(false)}
        unmountOnExit
        className="accounts-arco-modal"
      >
        <Form layout="vertical">
          <Form.Item>
            <Text type="secondary">已选择 {selectedIds.size} 个商品</Text>
          </Form.Item>
          <Form.Item>
            <Checkbox checked={batchReplyEnabled} onChange={setBatchReplyEnabled}>
              启用默认回复
            </Checkbox>
          </Form.Item>
          <Form.Item label="回复内容">
            <TextArea
              value={batchReplyContent}
              onChange={setBatchReplyContent}
              autoSize={{ minRows: 5, maxRows: 8 }}
              placeholder="输入默认回复内容，支持变量：{send_user_name}、{send_user_id}、{send_message}、{item_id}"
            />
          </Form.Item>
          <Form.Item label="回复图片（可选）">
            <div className="flex gap-2">
              <Input
                value={batchReplyImage}
                onChange={setBatchReplyImage}
                placeholder="图片URL，或点击上传按钮"
              />
              <input
                type="file"
                ref={batchReplyImageInputRef}
                onChange={handleBatchReplyImageUpload}
                accept="image/*"
                className="hidden"
              />
              <Button
                onClick={() => batchReplyImageInputRef.current?.click()}
                loading={batchReplyImageUploading}
                icon={!batchReplyImageUploading ? <ImagePlus className="w-4 h-4" /> : undefined}
              >
                上传
              </Button>
              {batchReplyImage && (
                <Button status="danger" onClick={() => setBatchReplyImage('')} icon={<X className="w-4 h-4" />} />
              )}
            </div>
            {batchReplyImage && (
              <div className="mt-2">
                <img src={batchReplyImage} alt="预览" className="max-h-24 rounded border" />
              </div>
            )}
          </Form.Item>
          <Form.Item>
            <Checkbox checked={batchReplyOnce} onChange={setBatchReplyOnce}>
              只回复一次
            </Checkbox>
          </Form.Item>
          <Form.Item label="商品违禁词">
            <TextArea
              value={batchForbiddenKeywords}
              onChange={setBatchForbiddenKeywords}
              autoSize={{ minRows: 3, maxRows: 6 }}
              placeholder="输入违禁词，支持逗号、分号或换行分隔"
            />
          </Form.Item>
          <Form.Item label="违禁词处理方式">
            <ArcoSelect
              value={batchForbiddenAction}
              onChange={(value) => setBatchForbiddenAction(value as 'ignore' | 'fixed_reply')}
              options={[
                { label: '冷处理，不回复', value: 'ignore' },
                { label: '固定回复', value: 'fixed_reply' },
              ]}
            />
          </Form.Item>
          {batchForbiddenAction === 'fixed_reply' && (
            <Form.Item label="违禁词固定回复">
              <TextArea
                value={batchForbiddenReplyContent}
                onChange={setBatchForbiddenReplyContent}
                autoSize={{ minRows: 3, maxRows: 6 }}
                placeholder="命中违禁词后的固定回复话术"
              />
            </Form.Item>
          )}
        </Form>
        <div className="modal-footer px-0 pb-0">
          <Button onClick={() => setShowBatchDefaultReplyModal(false)} disabled={savingBatchReply}>取消</Button>
          <Button type="primary" onClick={handleSaveBatchDefaultReply} loading={savingBatchReply}>批量保存</Button>
        </div>
      </Modal>

      {/* 批量删除默认回复确认弹窗 */}
      <Modal
        visible={batchDeleteDefaultReplyConfirm}
        title="确认删除"
        footer={null}
        onCancel={() => setBatchDeleteDefaultReplyConfirm(false)}
        unmountOnExit
        className="accounts-arco-modal"
      >
        <Text type="secondary">
          确定要删除选中的 {selectedIds.size} 个商品的默认回复配置吗？
        </Text>
        <div className="modal-footer px-0 pb-0">
          <Button onClick={() => setBatchDeleteDefaultReplyConfirm(false)}>取消</Button>
          <Button status="danger" onClick={handleBatchDeleteDefaultReply}>确认删除</Button>
        </div>
      </Modal>
    </div>
  )
}
