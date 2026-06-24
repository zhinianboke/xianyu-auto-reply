/**
 * 个人地址库 Tab
 *
 * 功能：
 * 1. 分页查看本人的个人地址库
 * 2. 新增、编辑、批量删除本人地址
 * 3. Excel 导入（按地址文本去重）、导出
 */
import { useEffect, useRef, useState } from 'react'
import {
  CheckSquare,
  ChevronLeft,
  ChevronRight,
  Download,
  Loader2,
  MapPin,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  Square,
  Trash2,
  Upload,
} from 'lucide-react'
import {
  batchDeletePersonalAddresses,
  exportPersonalAddresses,
  getPersonalAddresses,
  importPersonalAddresses,
  type PersonalAddress,
} from '@/api/personalAddresses'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { PersonalAddressFormModal } from './PersonalAddressFormModal'

export function PersonalAddressTab() {
  const { addToast } = useUIStore()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [tableLoading, setTableLoading] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [importing, setImporting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [addresses, setAddresses] = useState<PersonalAddress[]>([])
  const [keyword, setKeyword] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [showFormModal, setShowFormModal] = useState(false)
  const [editingAddress, setEditingAddress] = useState<PersonalAddress | null>(null)
  const [batchDeleteConfirmOpen, setBatchDeleteConfirmOpen] = useState(false)

  const loadAddresses = async (nextPage = page, nextPageSize = pageSize, searchKeyword = keyword) => {
    try {
      setTableLoading(true)
      const result = await getPersonalAddresses(nextPage, nextPageSize, {
        keyword: searchKeyword.trim() || undefined,
      })
      if (!result.success || !result.data) {
        setAddresses([])
        setTotal(0)
        setTotalPages(0)
        addToast({ type: 'error', message: result.message || '加载个人地址库失败' })
        return
      }
      const currentList = result.data.list || []
      setAddresses(currentList)
      setTotal(result.data.total || 0)
      setTotalPages(result.data.total_pages || 0)
      const currentIdSet = new Set(currentList.map((item) => item.id))
      setSelectedIds((prev) => new Set(Array.from(prev).filter((id) => currentIdSet.has(id))))
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载个人地址库失败') })
    } finally {
      setTableLoading(false)
    }
  }

  useEffect(() => {
    loadAddresses(page, pageSize)
  }, [page, pageSize])

  const handleSearch = async () => {
    if (page === 1) {
      await loadAddresses(1, pageSize)
      return
    }
    setPage(1)
  }

  const handleReset = async () => {
    setKeyword('')
    if (page === 1) {
      await loadAddresses(1, pageSize, '')
      return
    }
    setPage(1)
  }

  const handleOpenCreate = () => {
    setEditingAddress(null)
    setShowFormModal(true)
  }

  const handleOpenEdit = (address: PersonalAddress) => {
    setEditingAddress(address)
    setShowFormModal(true)
  }

  const handleSaved = async () => {
    setShowFormModal(false)
    setEditingAddress(null)
    await loadAddresses(page, pageSize)
  }

  const handleSelectAll = () => {
    const currentPageIds = addresses.map((item) => item.id)
    if (currentPageIds.length === 0) {
      setSelectedIds(new Set())
      return
    }
    const isAllSelected = currentPageIds.every((id) => selectedIds.has(id))
    setSelectedIds(isAllSelected ? new Set() : new Set(currentPageIds))
  }

  const handleSelect = (addressId: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(addressId)) {
        next.delete(addressId)
      } else {
        next.add(addressId)
      }
      return next
    })
  }

  const handleBatchDelete = async () => {
    const addressIds = Array.from(selectedIds)
    if (addressIds.length === 0) {
      addToast({ type: 'warning', message: '请先勾选要删除的地址' })
      return
    }

    setDeleting(true)
    try {
      const result = await batchDeletePersonalAddresses(addressIds)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '批量删除地址失败' })
        return
      }

      const successCount = result.data?.success_count ?? 0
      addToast({ type: 'success', message: result.message || `成功删除 ${successCount} 条地址` })
      setBatchDeleteConfirmOpen(false)
      setSelectedIds(new Set())

      if (page > 1 && successCount > 0 && successCount >= addresses.length) {
        setPage((prev) => Math.max(1, prev - 1))
        return
      }
      await loadAddresses(page, pageSize)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '批量删除地址失败') })
    } finally {
      setDeleting(false)
    }
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const blob = await exportPersonalAddresses()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `个人地址库_${new Date().toLocaleDateString()}.xlsx`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      addToast({ type: 'success', message: '导出成功' })
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '导出失败') })
    } finally {
      setExporting(false)
    }
  }

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    setImporting(true)
    try {
      const result = await importPersonalAddresses(file)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '导入失败' })
        return
      }
      addToast({ type: 'success', message: result.message || '导入成功' })
      await loadAddresses(1, pageSize, keyword)
      setPage(1)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '导入失败') })
    } finally {
      setImporting(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const startIndex = total === 0 ? 0 : (page - 1) * pageSize + 1
  const endIndex = Math.min(page * pageSize, total)
  const isAllSelected = addresses.length > 0 && addresses.every((item) => selectedIds.has(item.id))

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <p className="page-description">
          维护你自己的发布地址，发布你名下账号的商品时会优先随机使用这里的地址；个人地址库为空时自动回退到全局随机地址库。
        </p>
        <div className="flex gap-3 flex-wrap">
          {selectedIds.size > 0 && (
            <button className="btn-ios-danger" onClick={() => setBatchDeleteConfirmOpen(true)} disabled={tableLoading || deleting}>
              <Trash2 className="w-4 h-4" />
              删除选中 ({selectedIds.size})
            </button>
          )}
          <button className="btn-ios-secondary" onClick={handleExport} disabled={exporting}>
            {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
            导出
          </button>
          <button className="btn-ios-secondary" onClick={() => fileInputRef.current?.click()} disabled={importing}>
            {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Upload className="w-4 h-4" />}
            导入
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept=".xlsx,.xls"
            className="hidden"
            onChange={handleImport}
          />
          <button className="btn-ios-primary" onClick={handleOpenCreate}>
            <Plus className="w-4 h-4" />
            新增地址
          </button>
          <button className="btn-ios-secondary" onClick={() => loadAddresses(page, pageSize)} disabled={tableLoading || deleting}>
            {tableLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            刷新
          </button>
        </div>
      </div>

      <div className="vben-card">
        <div className="vben-card-body">
          <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3">
            <div className="input-group">
              <label className="input-label">关键词</label>
              <input
                className="input-ios"
                placeholder="输入地址关键词"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    void handleSearch()
                  }
                }}
              />
            </div>
            <div className="flex items-end gap-2">
              <button className="btn-ios-primary flex-1" onClick={() => void handleSearch()}>
                <Search className="w-4 h-4" />查询
              </button>
              <button className="btn-ios-secondary" onClick={() => void handleReset()}>
                重置
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 380px)', minHeight: '360px' }}>
        <div className="vben-card-header flex items-center justify-between">
          <h2 className="vben-card-title">
            <MapPin className="w-4 h-4" />
            个人地址列表
          </h2>
          <span className="badge-primary">共 {total} 条</span>
        </div>

        <div className="flex-1 overflow-auto">
          <table className="table-ios min-w-[720px]">
            <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
              <tr>
                <th className="w-10 whitespace-nowrap">
                  <button
                    onClick={handleSelectAll}
                    className="p-1 hover:bg-gray-100 rounded"
                    title={isAllSelected ? '取消全选' : '全选'}
                  >
                    {isAllSelected ? (
                      <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                    ) : (
                      <Square className="w-4 h-4 text-gray-400" />
                    )}
                  </button>
                </th>
                <th>地址</th>
                <th>使用次数</th>
                <th>最后使用</th>
                <th>更新时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tableLoading ? (
                <tr>
                  <td colSpan={6} className="text-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : addresses.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-12 text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <MapPin className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>暂无个人地址数据</p>
                    </div>
                  </td>
                </tr>
              ) : (
                addresses.map((item) => (
                  <tr key={item.id}>
                    <td className="w-10 whitespace-nowrap">
                      <button
                        onClick={() => handleSelect(item.id)}
                        className="p-1 hover:bg-gray-100 rounded"
                        title={selectedIds.has(item.id) ? '取消勾选' : '勾选'}
                      >
                        {selectedIds.has(item.id) ? (
                          <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                        ) : (
                          <Square className="w-4 h-4 text-gray-400" />
                        )}
                      </button>
                    </td>
                    <td className="max-w-[320px] font-medium text-slate-800 dark:text-slate-100">
                      <span className="truncate block" title={item.address}>{item.address}</span>
                    </td>
                    <td>{item.use_count}</td>
                    <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">{item.last_used_at ? new Date(item.last_used_at).toLocaleString('zh-CN') : '-'}</td>
                    <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">{item.updated_at ? new Date(item.updated_at).toLocaleString('zh-CN') : '-'}</td>
                    <td>
                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={() => handleOpenEdit(item)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 text-blue-600 dark:text-blue-400 transition-colors"
                        >
                          <Pencil className="w-4 h-4" />编辑
                        </button>
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

      {showFormModal && (
        <PersonalAddressFormModal
          initial={editingAddress}
          onClose={() => {
            setShowFormModal(false)
            setEditingAddress(null)
          }}
          onSaved={handleSaved}
        />
      )}

      <ConfirmModal
        isOpen={batchDeleteConfirmOpen}
        title="批量删除确认"
        message={`确定要删除选中的 ${selectedIds.size} 条个人地址吗？删除后将不会在列表中显示，也不会再参与发布。`}
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={() => void handleBatchDelete()}
        onCancel={() => {
          if (!deleting) {
            setBatchDeleteConfirmOpen(false)
          }
        }}
      />
    </div>
  )
}

export default PersonalAddressTab
