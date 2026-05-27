/**
 * 个人黑名单Tab页
 */
import { useState, useEffect, useCallback, useRef, type MutableRefObject } from 'react'
import { Plus, Trash2, ToggleLeft, ToggleRight, Download, Upload } from 'lucide-react'
import { getPersonalBlacklist, deletePersonalBlacklist, batchDeletePersonalBlacklist, togglePersonalBlacklist, exportPersonalBlacklist, importPersonalBlacklist, type PersonalBlacklistItem } from '@/api/blacklist'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { getApiErrorMessage } from '@/utils/request'
import { PersonalBlacklistFormModal } from './PersonalBlacklistFormModal'

interface Props {
  onRefreshRef: MutableRefObject<() => void>
}

export function PersonalBlacklist({ onRefreshRef }: Props) {
  const { addToast } = useUIStore()
  const { _hasHydrated, isAuthenticated, token } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState<PersonalBlacklistItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)

  // 筛选输入
  const [filterBuyerId, setFilterBuyerId] = useState('')
  const [filterBuyerNick, setFilterBuyerNick] = useState('')

  // 已提交的筛选条件（点击搜索后才更新）
  const [appliedBuyerId, setAppliedBuyerId] = useState('')
  const [appliedBuyerNick, setAppliedBuyerNick] = useState('')

  // 新建弹窗
  const [showCreateModal, setShowCreateModal] = useState(false)

  // 勾选状态
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())

  // 删除确认
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; item: PersonalBlacklistItem | null }>({ open: false, item: null })
  const [batchDeleteConfirm, setBatchDeleteConfirm] = useState(false)

  // 导入文件输入
  const fileInputRef = useRef<HTMLInputElement>(null)

  const totalPages = Math.ceil(total / pageSize)

  const loadData = useCallback(async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    setLoading(true)
    try {
      const res = await getPersonalBlacklist({
        buyer_id: appliedBuyerId || undefined,
        buyer_nick: appliedBuyerNick || undefined,
        page,
        page_size: pageSize,
      })
      if (res.success) {
        setItems(res.data)
        setTotal(res.total)
        setSelectedIds(new Set())
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载黑名单失败') })
    } finally {
      setLoading(false)
    }
  }, [_hasHydrated, isAuthenticated, token, appliedBuyerId, appliedBuyerNick, page, pageSize, addToast])

  useEffect(() => {
    loadData()
  }, [loadData])

  // 暴露刷新方法
  useEffect(() => {
    onRefreshRef.current = loadData
  }, [onRefreshRef, loadData])

  const handleSearch = () => {
    setAppliedBuyerId(filterBuyerId)
    setAppliedBuyerNick(filterBuyerNick)
    setPage(1)
  }

  const handleDelete = async () => {
    if (!deleteConfirm.item) return
    try {
      const res = await deletePersonalBlacklist(deleteConfirm.item.id)
      if (res.success) {
        addToast({ type: 'success', message: '删除成功' })
        loadData()
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '删除失败') })
    } finally {
      setDeleteConfirm({ open: false, item: null })
    }
  }

  const handleBatchDelete = async () => {
    const ids = Array.from(selectedIds)
    try {
      const res = await batchDeletePersonalBlacklist(ids)
      if (res.success) {
        addToast({ type: 'success', message: res.message || `成功删除 ${ids.length} 条` })
        setSelectedIds(new Set())
        loadData()
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '批量删除失败') })
    } finally {
      setBatchDeleteConfirm(false)
    }
  }

  const handleToggle = async (item: PersonalBlacklistItem) => {
    try {
      const res = await togglePersonalBlacklist(item.id, !item.is_enabled)
      if (res.success) {
        addToast({ type: 'success', message: item.is_enabled ? '已禁用' : '已启用' })
        loadData()
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '操作失败') })
    }
  }

  const toggleSelectItem = (id: number) => {
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
    if (selectedIds.size === items.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(items.map((item) => item.id)))
    }
  }

  const handleCreateSuccess = () => {
    setShowCreateModal(false)
    loadData()
  }

  const handleExport = async () => {
    try {
      const blob = await exportPersonalBlacklist()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `个人黑名单_${new Date().toLocaleDateString()}.xlsx`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      addToast({ type: 'success', message: '导出成功' })
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '导出失败') })
    }
  }

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const res = await importPersonalBlacklist(file)
      if (res.success) {
        addToast({ type: 'success', message: res.message || '导入成功' })
        loadData()
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '导入失败') })
    } finally {
      // 清空文件输入，允许重复选择同一文件
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  if (loading && items.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* 筛选栏 */}
      <div className="flex items-center gap-3 flex-wrap">
        <input
          type="text"
          placeholder="买家ID"
          value={filterBuyerId}
          onChange={(e) => setFilterBuyerId(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          className="px-3 py-1.5 text-sm border border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <input
          type="text"
          placeholder="买家昵称"
          value={filterBuyerNick}
          onChange={(e) => setFilterBuyerNick(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
          className="px-3 py-1.5 text-sm border border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <button
          onClick={handleSearch}
          className="px-3 py-1.5 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600 transition-colors"
        >
          搜索
        </button>
        {selectedIds.size > 0 && (
          <button
            onClick={() => setBatchDeleteConfirm(true)}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-red-500 text-white rounded-md hover:bg-red-600 transition-colors"
          >
            <Trash2 className="w-4 h-4" />
            删除选中({selectedIds.size})
          </button>
        )}
        <div className="flex items-center gap-2 ml-auto">
          <button
            onClick={handleExport}
            className="flex items-center gap-1 px-3 py-1.5 text-sm border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 rounded-md hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
          >
            <Download className="w-4 h-4" />
            导出
          </button>
          <button
            onClick={() => fileInputRef.current?.click()}
            className="flex items-center gap-1 px-3 py-1.5 text-sm border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 rounded-md hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
          >
            <Upload className="w-4 h-4" />
            导入
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls"
            onChange={handleImport}
            className="hidden"
          />
          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-1 px-3 py-1.5 text-sm bg-green-500 text-white rounded-md hover:bg-green-600 transition-colors"
          >
            <Plus className="w-4 h-4" />
            新建
          </button>
        </div>
      </div>

      {/* 表格 */}
      <div className="overflow-x-auto bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 dark:bg-slate-700/50">
            <tr>
              <th className="px-3 py-2 w-10">
                <input
                  type="checkbox"
                  checked={items.length > 0 && selectedIds.size === items.length}
                  onChange={toggleSelectAll}
                  className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500"
                />
              </th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">ID</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">用户ID</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">账号ID</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">买家ID</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">买家昵称</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">商品ID</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">拉黑原因</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">创建时间</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">更新时间</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">状态</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
            {items.length === 0 ? (
              <tr>
                <td colSpan={12} className="px-3 py-8 text-center text-slate-400 dark:text-slate-500">
                  暂无数据
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr key={item.id} className={`hover:bg-slate-50 dark:hover:bg-slate-700/30 ${selectedIds.has(item.id) ? 'bg-blue-50 dark:bg-blue-900/10' : ''}`}>
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(item.id)}
                      onChange={() => toggleSelectItem(item.id)}
                      className="w-4 h-4 text-blue-600 rounded focus:ring-2 focus:ring-blue-500"
                    />
                  </td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{item.id}</td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{item.owner_id}</td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{item.account_id || '-'}</td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{item.buyer_id}</td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{item.buyer_nick || '-'}</td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{item.item_id || '-'}</td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300 max-w-[200px] truncate" title={item.reason || ''}>
                    {item.reason || '-'}
                  </td>
                  <td className="px-3 py-2 text-slate-500 dark:text-slate-400 text-xs whitespace-nowrap">
                    {item.created_at ? new Date(item.created_at).toLocaleString() : '-'}
                  </td>
                  <td className="px-3 py-2 text-slate-500 dark:text-slate-400 text-xs whitespace-nowrap">
                    {item.updated_at ? new Date(item.updated_at).toLocaleString() : '-'}
                  </td>
                  <td className="px-3 py-2">
                    <span className={`inline-flex px-2 py-0.5 text-xs rounded-full ${
                      item.is_enabled
                        ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                        : 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400'
                    }`}>
                      {item.is_enabled ? '启用' : '禁用'}
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => handleToggle(item)}
                        className={`p-1 rounded transition-colors ${
                          item.is_enabled
                            ? 'text-orange-500 hover:bg-orange-50 dark:hover:bg-orange-900/20'
                            : 'text-green-500 hover:bg-green-50 dark:hover:bg-green-900/20'
                        }`}
                        title={item.is_enabled ? '禁用' : '启用'}
                      >
                        {item.is_enabled ? <ToggleRight className="w-4 h-4" /> : <ToggleLeft className="w-4 h-4" />}
                      </button>
                      <button
                        onClick={() => setDeleteConfirm({ open: true, item })}
                        className="p-1 text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded transition-colors"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-500 dark:text-slate-400">
            共 {total} 条，第 {page}/{totalPages} 页
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="px-3 py-1 text-sm border border-slate-300 dark:border-slate-600 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300"
            >
              上一页
            </button>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              className="px-3 py-1 text-sm border border-slate-300 dark:border-slate-600 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300"
            >
              下一页
            </button>
          </div>
        </div>
      )}

      {/* 新建弹窗 */}
      {showCreateModal && (
        <PersonalBlacklistFormModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={handleCreateSuccess}
        />
      )}

      {/* 单条删除确认 */}
      <ConfirmModal
        isOpen={deleteConfirm.open}
        title="确认删除"
        message={`确定要删除买家 ${deleteConfirm.item?.buyer_id || ''} 的黑名单记录吗？`}
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm({ open: false, item: null })}
      />

      {/* 批量删除确认 */}
      <ConfirmModal
        isOpen={batchDeleteConfirm}
        title="批量删除确认"
        message={`确定要删除选中的 ${selectedIds.size} 条黑名单记录吗？删除后无法恢复。`}
        type="danger"
        onConfirm={handleBatchDelete}
        onCancel={() => setBatchDeleteConfirm(false)}
      />
    </div>
  )
}
