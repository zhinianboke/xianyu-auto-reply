import { useEffect, useState } from 'react'
import { CheckSquare, Download, Edit2, ExternalLink, Loader2, Package, RefreshCw, Search, Square, Trash2, X } from 'lucide-react'
import { batchDeleteItems, deleteItem, fetchItemsFromAccount, getItems, updateItem, updateItemMultiQuantityDelivery, updateItemMultiSpec } from '@/api/items'
import { getAccounts } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import { useAuthStore } from '@/store/authStore'
import { Select } from '@/components/common/Select'
import type { Account, Item } from '@/types'

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
  const [fetchProgress, setFetchProgress] = useState({ current: 0, total: 0 })

  // 编辑弹窗状态
  const [editingItem, setEditingItem] = useState<Item | null>(null)
  const [editDetail, setEditDetail] = useState('')
  const [editSaving, setEditSaving] = useState(false)

  const loadItems = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) {
      return
    }
    try {
      setLoading(true)
      const result = await getItems(selectedAccount || undefined)
      if (result.success) {
        setItems(result.data || [])
      }
    } catch {
      addToast({ type: 'error', message: '加载商品列表失败' })
    } finally {
      setLoading(false)
    }
  }

  const handleFetchItems = async () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号后再获取商品' })
      return
    }

    setFetching(true)
    setFetchProgress({ current: 0, total: 0 })

    try {
      let page = 1
      let hasMore = true
      let totalFetched = 0

      while (hasMore) {
        setFetchProgress({ current: page, total: page })
        const result = await fetchItemsFromAccount(selectedAccount, page)

        if (result.success) {
          const fetchedCount = (result as { count?: number }).count || 0
          totalFetched += fetchedCount
          hasMore = (result as { has_more?: boolean }).has_more === true
          page++
        } else {
          hasMore = false
        }

        // 防止无限循环，最多抓取20页
        if (page > 20) hasMore = false
      }

      addToast({ type: 'success', message: `成功获取商品，共 ${totalFetched} 件` })
      await loadItems()
    } catch {
      addToast({ type: 'error', message: '获取商品失败' })
    } finally {
      setFetching(false)
      setFetchProgress({ current: 0, total: 0 })
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
    if (!confirm('确定要删除这个商品吗？')) return
    try {
      await deleteItem(item.cookie_id, item.item_id)
      addToast({ type: 'success', message: '删除成功' })
      loadItems()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    }
  }

  // 批量选择相关
  const toggleSelect = (id: string | number) => {
    setSelectedIds((prev) => {
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
    if (selectedIds.size === filteredItems.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(filteredItems.map((item) => item.id)))
    }
  }

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) {
      addToast({ type: 'warning', message: '请先选择要删除的商品' })
      return
    }
    if (!confirm(`确定要删除选中的 ${selectedIds.size} 个商品吗？`)) return
    try {
      // 将选中的 ID 转换为 { cookie_id, item_id } 格式
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
  }

  // 切换多数量发货状态
  const handleToggleMultiQuantity = async (item: Item) => {
    try {
      const newStatus = !item.multi_quantity_delivery
      await updateItemMultiQuantityDelivery(item.cookie_id, item.item_id, newStatus)
      addToast({ type: 'success', message: `多数量发货已${newStatus ? '开启' : '关闭'}` })
      loadItems()
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
      loadItems()
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

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="page-header flex-between flex-wrap gap-4">
        <div>
          <h1 className="page-title">商品管理</h1>
          <p className="page-description">管理各账号的商品信息</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {selectedIds.size > 0 && (
            <button onClick={handleBatchDelete} className="btn-ios-danger">
              <Trash2 className="w-4 h-4" />
              删除选中 ({selectedIds.size})
            </button>
          )}
          <button
            onClick={handleFetchItems}
            disabled={fetching}
            className="btn-ios-primary"
          >
            {fetching ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                抓取中 (第{fetchProgress.current}页)
              </>
            ) : (
              <>
                <Download className="w-4 h-4" />
                获取商品
              </>
            )}
          </button>
          <button onClick={loadItems} className="btn-ios-secondary">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {/* Filters */}
      <div className="vben-card">
        <div className="vben-card-body">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="input-group">
              <label className="input-label">筛选账号</label>
              <Select
                value={selectedAccount}
                onChange={setSelectedAccount}
                options={[
                  { value: '', label: '所有账号' },
                  ...accounts.map((account) => ({
                    value: account.id,
                    label: account.id,
                  })),
                ]}
                placeholder="所有账号"
              />
            </div>
            <div className="input-group">
              <label className="input-label">搜索商品</label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  value={searchKeyword}
                  onChange={(e) => setSearchKeyword(e.target.value)}
                  placeholder="搜索商品标题或详情..."
                  className="input-ios pl-9"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Items List */}
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title ">
            <Package className="w-4 h-4" />
            商品列表
          </h2>
          <span className="badge-primary">{filteredItems.length} 个商品</span>
        </div>
        <div className="overflow-x-auto">
          <table className="table-ios min-w-[900px]">
            <thead>
              <tr>
                <th className="w-10 whitespace-nowrap">
                  <button
                    onClick={toggleSelectAll}
                    className="p-1 hover:bg-gray-100 rounded"
                    title={selectedIds.size === filteredItems.length ? '取消全选' : '全选'}
                  >
                    {selectedIds.size === filteredItems.length && filteredItems.length > 0 ? (
                      <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                    ) : (
                      <Square className="w-4 h-4 text-gray-400" />
                    )}
                  </button>
                </th>
                <th className="whitespace-nowrap">账号ID</th>
                <th className="whitespace-nowrap">商品ID</th>
                <th className="whitespace-nowrap">商品标题</th>
                <th className="whitespace-nowrap">价格</th>
                <th className="whitespace-nowrap">多规格</th>
                <th className="whitespace-nowrap">多数量发货</th>
                <th className="whitespace-nowrap">更新时间</th>
                <th className="whitespace-nowrap sticky right-0 bg-slate-50 dark:bg-slate-800">操作</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.length === 0 ? (
                <tr>
                  <td colSpan={9}>
                    <div className="empty-state py-8">
                      <Package className="empty-state-icon" />
                      <p className="text-gray-500">暂无商品数据</p>
                    </div>
                  </td>
                </tr>
              ) : (
                filteredItems.map((item) => (
                  <tr key={item.id} className={selectedIds.has(item.id) ? 'bg-blue-50 dark:bg-blue-900/30' : ''}>
                    <td>
                      <button
                        onClick={() => toggleSelect(item.id)}
                        className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
                      >
                        {selectedIds.has(item.id) ? (
                          <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                        ) : (
                          <Square className="w-4 h-4 text-gray-400" />
                        )}
                      </button>
                    </td>
                    <td className="font-medium text-blue-600 dark:text-blue-400">{item.cookie_id}</td>
                    <td className="text-xs text-gray-500">
                      <a
                        href={`https://www.goofish.com/item?id=${item.item_id}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="hover:text-blue-500 flex items-center gap-1"
                      >
                        {item.item_id}
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    </td>
                    <td className="max-w-[280px]">
                      <div
                        className="font-medium line-clamp-2 cursor-help"
                        title={item.item_title || item.title || '-'}
                      >
                        {item.item_title || item.title || '-'}
                      </div>
                      {(item.item_detail || item.desc) && (
                        <div
                          className="text-xs text-gray-400 line-clamp-1 mt-0.5 cursor-help"
                          title={item.item_detail || item.desc}
                        >
                          {item.item_detail || item.desc}
                        </div>
                      )}
                    </td>
                    <td className="text-amber-600 font-medium">
                      {item.item_price || (item.price ? `¥${item.price}` : '-')}
                    </td>
                    <td>
                      <button
                        onClick={() => handleToggleMultiSpec(item)}
                        className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                          (item.is_multi_spec || item.has_sku)
                            ? 'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400'
                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400'
                        }`}
                        title={(item.is_multi_spec || item.has_sku) ? '点击关闭多规格' : '点击开启多规格'}
                      >
                        {(item.is_multi_spec || item.has_sku) ? '已开启' : '已关闭'}
                      </button>
                    </td>
                    <td>
                      <button
                        onClick={() => handleToggleMultiQuantity(item)}
                        className={`px-2 py-1 rounded text-xs font-medium transition-colors ${
                          item.multi_quantity_delivery
                            ? 'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-400'
                            : 'bg-gray-100 text-gray-500 hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400'
                        }`}
                        title={item.multi_quantity_delivery ? '点击关闭多数量发货' : '点击开启多数量发货'}
                      >
                        {item.multi_quantity_delivery ? '已开启' : '已关闭'}
                      </button>
                    </td>
                    <td className="text-gray-500 text-xs">
                      {item.updated_at ? new Date(item.updated_at).toLocaleString() : '-'}
                    </td>
                    <td className="sticky right-0 bg-white dark:bg-slate-900">
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleEdit(item)}
                          className="table-action-btn hover:!bg-blue-50"
                          title="编辑"
                        >
                          <Edit2 className="w-4 h-4 text-blue-500" />
                        </button>
                        <button
                          onClick={() => handleDelete(item)}
                          className="table-action-btn hover:!bg-red-50"
                          title="删除"
                        >
                          <Trash2 className="w-4 h-4 text-red-500" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 编辑弹窗 */}
      {editingItem && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg">
            <div className="modal-header">
              <h2 className="modal-title">编辑商品</h2>
              <button onClick={() => setEditingItem(null)} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              <div className="input-group">
                <label className="input-label">商品ID</label>
                <input
                  type="text"
                  value={editingItem.item_id}
                  disabled
                  className="input-ios bg-slate-100 dark:bg-slate-700"
                />
              </div>
              <div className="input-group">
                <label className="input-label">商品标题</label>
                <input
                  type="text"
                  value={editingItem.item_title || editingItem.title || ''}
                  disabled
                  className="input-ios bg-slate-100 dark:bg-slate-700"
                />
              </div>
              <div className="input-group">
                <label className="input-label">商品详情</label>
                <textarea
                  value={editDetail}
                  onChange={(e) => setEditDetail(e.target.value)}
                  className="input-ios h-32 resize-none"
                  placeholder="输入商品详情..."
                />
              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                onClick={() => setEditingItem(null)}
                className="btn-ios-secondary"
                disabled={editSaving}
              >
                取消
              </button>
              <button
                onClick={handleSaveEdit}
                className="btn-ios-primary"
                disabled={editSaving}
              >
                {editSaving ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    保存中...
                  </span>
                ) : (
                  '保存'
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
