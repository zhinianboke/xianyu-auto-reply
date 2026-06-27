/**
 * 上新监控页面
 *
 * 功能：
 * 1. 分页查看上新监控任务
 * 2. 新建、编辑、启停、批量删除监控任务
 */
import { useEffect, useState } from 'react'
import {
  CheckSquare,
  ChevronLeft,
  ChevronRight,
  Loader2,
  MessageSquare,
  PackageSearch,
  Pencil,
  Play,
  Plus,
  RefreshCw,
  Search,
  Square,
  Tags,
  Trash2,
  Users,
  ShoppingCart,
} from 'lucide-react'
import {
  batchDeleteListingMonitorTasks,
  getListingMonitorTasks,
  runListingMonitorTask,
  updateListingMonitorTaskStatus,
  MONITOR_TYPE_LABELS,
  type ListingMonitorTask,
} from '@/api/listingMonitor'
import { getListingMonitorCategories } from '@/api/listingMonitorCategory'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { PageLoading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { ListingMonitorFormModal } from './ListingMonitorFormModal'
import { BatchAccountsModal, type BatchAccountField } from './BatchAccountsModal'
import { BatchCategoryModal } from './BatchCategoryModal'
import { BatchDmContentModal } from './BatchDmContentModal'

const formatPriceRange = (task: ListingMonitorTask): string => {
  const min = task.price_min
  const max = task.price_max
  if (min == null && max == null) return '不限'
  if (min != null && max != null) return `${min} ~ ${max}`
  if (min != null) return `≥ ${min}`
  return `≤ ${max}`
}

export function ListingMonitor() {
  const { addToast } = useUIStore()

  const [loading, setLoading] = useState(true)
  const [tableLoading, setTableLoading] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [tasks, setTasks] = useState<ListingMonitorTask[]>([])
  const [keyword, setKeyword] = useState('')
  const [categoryId, setCategoryId] = useState<number | undefined>(undefined)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [showFormModal, setShowFormModal] = useState(false)
  const [editingTask, setEditingTask] = useState<ListingMonitorTask | null>(null)
  const [batchDeleteConfirmOpen, setBatchDeleteConfirmOpen] = useState(false)
  const [batchAccountsField, setBatchAccountsField] = useState<BatchAccountField | null>(null)
  const [showBatchCategory, setShowBatchCategory] = useState(false)
  const [showBatchDmContent, setShowBatchDmContent] = useState(false)
  const [categoryMap, setCategoryMap] = useState<Record<number, string>>({})
  const [statusUpdatingId, setStatusUpdatingId] = useState<number | null>(null)
  const [runningId, setRunningId] = useState<number | null>(null)

  // 加载分类映射（用于列表展示分类名与筛选下拉；普通用户仅见自己的分类，管理员见全部）
  useEffect(() => {
    const loadCategories = async () => {
      try {
        const result = await getListingMonitorCategories()
        if (result.success && result.data) {
          const map: Record<number, string> = {}
          result.data.forEach((c) => {
            map[c.id] = c.name
          })
          setCategoryMap(map)
        }
      } catch {
        // 分类加载失败不阻塞任务列表展示
      }
    }
    void loadCategories()
  }, [])

  const loadTasks = async (nextPage = page, nextPageSize = pageSize) => {
    try {
      setTableLoading(true)
      const result = await getListingMonitorTasks(nextPage, nextPageSize, {
        keyword: keyword.trim() || undefined,
        categoryId,
      })
      if (!result.success || !result.data) {
        setTasks([])
        setTotal(0)
        setTotalPages(0)
        addToast({ type: 'error', message: result.message || '加载监控任务失败' })
        return
      }
      const currentList = result.data.list || []
      setTasks(currentList)
      setTotal(result.data.total || 0)
      setTotalPages(result.data.total_pages || 0)
      const currentIdSet = new Set(currentList.map((item) => item.id))
      setSelectedIds((prev) => new Set(Array.from(prev).filter((id) => currentIdSet.has(id))))
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载监控任务失败') })
    } finally {
      setLoading(false)
      setTableLoading(false)
    }
  }

  useEffect(() => {
    loadTasks(page, pageSize)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [page, pageSize])

  const handleSearch = async () => {
    if (page === 1) {
      await loadTasks(1, pageSize)
      return
    }
    setPage(1)
  }

  const handleReset = async () => {
    setKeyword('')
    setCategoryId(undefined)
    if (page === 1) {
      try {
        setTableLoading(true)
        const result = await getListingMonitorTasks(1, pageSize)
        if (!result.success || !result.data) {
          addToast({ type: 'error', message: result.message || '重置筛选失败' })
          return
        }
        const currentList = result.data.list || []
        setTasks(currentList)
        setTotal(result.data.total || 0)
        setTotalPages(result.data.total_pages || 0)
        const currentIdSet = new Set(currentList.map((item) => item.id))
        setSelectedIds((prev) => new Set(Array.from(prev).filter((id) => currentIdSet.has(id))))
      } catch (error) {
        addToast({ type: 'error', message: getApiErrorMessage(error, '重置筛选失败') })
      } finally {
        setLoading(false)
        setTableLoading(false)
      }
      return
    }
    setPage(1)
  }

  const handleOpenCreate = () => {
    setEditingTask(null)
    setShowFormModal(true)
  }

  const handleOpenEdit = (task: ListingMonitorTask) => {
    setEditingTask(task)
    setShowFormModal(true)
  }

  const handleSaved = async () => {
    setShowFormModal(false)
    setEditingTask(null)
    await loadTasks(page, pageSize)
  }

  const handleToggleStatus = async (task: ListingMonitorTask) => {
    setStatusUpdatingId(task.id)
    try {
      const result = await updateListingMonitorTaskStatus(task.id, !task.is_enabled)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '更新状态失败' })
        return
      }
      addToast({ type: 'success', message: result.message || '状态更新成功' })
      await loadTasks(page, pageSize)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '更新状态失败') })
    } finally {
      setStatusUpdatingId(null)
    }
  }

  const handleRunNow = async (task: ListingMonitorTask) => {
    setRunningId(task.id)
    try {
      const result = await runListingMonitorTask(task.id)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '已发起采集' })
        void loadTasks(page, pageSize)
      } else {
        addToast({ type: 'error', message: result.message || '采集执行失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '采集执行失败') })
    } finally {
      setRunningId(null)
    }
  }

  const handleSelectAll = () => {
    const currentPageIds = tasks.map((item) => item.id)
    if (currentPageIds.length === 0) {
      setSelectedIds(new Set())
      return
    }
    const isAllSelected = currentPageIds.every((id) => selectedIds.has(id))
    setSelectedIds(isAllSelected ? new Set() : new Set(currentPageIds))
  }

  const handleSelect = (taskId: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(taskId)) {
        next.delete(taskId)
      } else {
        next.add(taskId)
      }
      return next
    })
  }

  const handleBatchDelete = async () => {
    const taskIds = Array.from(selectedIds)
    if (taskIds.length === 0) {
      addToast({ type: 'warning', message: '请先勾选要删除的监控任务' })
      return
    }
    setDeleting(true)
    try {
      const result = await batchDeleteListingMonitorTasks(taskIds)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '批量删除监控任务失败' })
        return
      }
      const successCount = result.data?.success_count ?? 0
      addToast({ type: 'success', message: result.message || `成功删除 ${successCount} 条监控任务` })
      setBatchDeleteConfirmOpen(false)
      setSelectedIds(new Set())
      if (page > 1 && successCount > 0 && successCount >= tasks.length) {
        setPage((prev) => Math.max(1, prev - 1))
        return
      }
      await loadTasks(page, pageSize)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '批量删除监控任务失败') })
    } finally {
      setDeleting(false)
    }
  }

  const startIndex = total === 0 ? 0 : (page - 1) * pageSize + 1
  const endIndex = Math.min(page * pageSize, total)
  const isAllSelected = tasks.length > 0 && tasks.every((item) => selectedIds.has(item.id))

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">商品监控</h1>
          <p className="page-description">按关键字与价格区间监控闲鱼商品上新或降价，可设置任务间隔并关联指定账号。</p>
        </div>
        <div className="flex gap-3 flex-wrap">
          {selectedIds.size > 0 && (
            <>
              <button className="btn-ios-secondary" onClick={() => setBatchAccountsField('account_ids')} disabled={tableLoading || deleting}>
                <Users className="w-4 h-4" />
                批量改采集账号 ({selectedIds.size})
              </button>
              <button className="btn-ios-secondary" onClick={() => setBatchAccountsField('order_account_ids')} disabled={tableLoading || deleting}>
                <ShoppingCart className="w-4 h-4" />
                批量改下单账号 ({selectedIds.size})
              </button>
              <button className="btn-ios-secondary" onClick={() => setShowBatchCategory(true)} disabled={tableLoading || deleting}>
                <Tags className="w-4 h-4" />
                批量改分类 ({selectedIds.size})
              </button>
              <button className="btn-ios-secondary" onClick={() => setShowBatchDmContent(true)} disabled={tableLoading || deleting}>
                <MessageSquare className="w-4 h-4" />
                批量改私信 ({selectedIds.size})
              </button>
              <button className="btn-ios-danger" onClick={() => setBatchDeleteConfirmOpen(true)} disabled={tableLoading || deleting}>
                <Trash2 className="w-4 h-4" />
                删除选中 ({selectedIds.size})
              </button>
            </>
          )}
          <button className="btn-ios-primary" onClick={handleOpenCreate}>
            <Plus className="w-4 h-4" />
            新建监控任务
          </button>
          <button className="btn-ios-secondary" onClick={() => loadTasks(page, pageSize)} disabled={tableLoading || deleting}>
            {tableLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            刷新
          </button>
        </div>
      </div>

      <div className="vben-card">
        <div className="vben-card-body">
          <div className="grid grid-cols-1 md:grid-cols-[1fr_220px_auto] gap-3">
            <div className="input-group">
              <label className="input-label">商品关键字</label>
              <input
                className="input-ios"
                placeholder="输入商品关键字"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    void handleSearch()
                  }
                }}
              />
            </div>
            <div className="input-group">
              <label className="input-label">分类</label>
              <select
                className="input-ios"
                value={categoryId === undefined ? '' : String(categoryId)}
                onChange={(e) => setCategoryId(e.target.value === '' ? undefined : Number(e.target.value))}
              >
                <option value="">全部分类</option>
                {Object.entries(categoryMap).map(([id, name]) => (
                  <option key={id} value={id}>
                    {name}
                  </option>
                ))}
              </select>
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

      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 320px)', minHeight: '420px' }}>
        <div className="vben-card-header flex items-center justify-between">
          <h2 className="vben-card-title">
            <PackageSearch className="w-4 h-4" />
            监控任务列表
          </h2>
          <span className="badge-primary">共 {total} 条</span>
        </div>

        <div className="flex-1 overflow-auto">
          <table className="table-ios min-w-[900px]">
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
                <th>任务ID</th>
                <th>监控类型</th>
                <th>所属分类</th>
                <th>所属用户</th>
                <th>商品关键字</th>
                <th>价格区间</th>
                <th>监控天数</th>
                <th>间隔(分钟)</th>
                <th>采集页数</th>
                <th>私信条数</th>
                <th>下单条数</th>
                <th>已私信数</th>
                <th>已下单数</th>
                <th>重复跳过</th>
                <th>直接下单</th>
                <th>关联账号</th>
                <th>状态</th>
                <th>更新时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tableLoading ? (
                <tr>
                  <td colSpan={20} className="text-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : tasks.length === 0 ? (
                <tr>
                  <td colSpan={20} className="text-center py-12 text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <PackageSearch className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>暂无监控任务，点击右上角新建</p>
                    </div>
                  </td>
                </tr>
              ) : (
                tasks.map((item) => (
                  <tr key={item.id}>
                    <td className="w-10 whitespace-nowrap">
                      <button onClick={() => handleSelect(item.id)} className="p-1 hover:bg-gray-100 rounded" title={selectedIds.has(item.id) ? '取消勾选' : '勾选'}>
                        {selectedIds.has(item.id) ? (
                          <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                        ) : (
                          <Square className="w-4 h-4 text-gray-400" />
                        )}
                      </button>
                    </td>
                    <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">#{item.id}</td>
                    <td className="whitespace-nowrap">
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                        {MONITOR_TYPE_LABELS[item.monitor_type] || item.monitor_type}
                      </span>
                    </td>
                    <td className="whitespace-nowrap text-slate-600 dark:text-slate-300">
                      {item.category_id != null ? (categoryMap[item.category_id] || `#${item.category_id}`) : '-'}
                    </td>
                    <td className="whitespace-nowrap text-slate-600 dark:text-slate-300">{item.owner_username || '-'}</td>
                    <td className="max-w-[220px] font-medium text-slate-800 dark:text-slate-100">
                      <span className="truncate block" title={item.keyword}>{item.keyword}</span>
                    </td>
                    <td className="whitespace-nowrap">{formatPriceRange(item)}</td>
                    <td className="whitespace-nowrap">{item.monitor_type === 'price_drop' ? '-' : (item.publish_days ? `${item.publish_days}天内` : '最新')}</td>
                    <td>{item.interval_minutes}</td>
                    <td>{item.collect_pages}</td>
                    <td>{item.dm_batch_size ?? 5}</td>
                    <td>{item.order_batch_size ?? 5}</td>
                    <td className="text-green-600 dark:text-green-400">{item.dm_sent_count ?? 0}</td>
                    <td className="text-blue-600 dark:text-blue-400">{item.ordered_count ?? 0}</td>
                    <td className="text-purple-600 dark:text-purple-400">{item.duplicate_count ?? 0}</td>
                    <td className="whitespace-nowrap">
                      {item.direct_order ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">开启</span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400">关闭</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap">
                      {item.account_ids && item.account_ids.length > 0 ? `${item.account_ids.length} 个账号` : '不限'}
                    </td>
                    <td className="whitespace-nowrap">
                      {item.is_enabled ? (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">启用中</span>
                      ) : (
                        <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400">已停用</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">{item.updated_at ? new Date(item.updated_at).toLocaleString('zh-CN') : '-'}</td>
                    <td className="whitespace-nowrap">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleOpenEdit(item)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 text-blue-600 dark:text-blue-400 transition-colors"
                        >
                          <Pencil className="w-4 h-4" />编辑
                        </button>
                        <button
                          onClick={() => void handleRunNow(item)}
                          disabled={runningId === item.id || !item.is_enabled}
                          title={item.is_enabled ? '立即执行一次采集' : '请先启用任务'}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg hover:bg-green-50 dark:hover:bg-green-900/20 text-green-600 dark:text-green-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                        >
                          {runningId === item.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                          立即采集
                        </button>
                        <button
                          onClick={() => void handleToggleStatus(item)}
                          disabled={statusUpdatingId === item.id}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors disabled:opacity-50"
                        >
                          {statusUpdatingId === item.id && <Loader2 className="w-4 h-4 animate-spin" />}
                          {item.is_enabled ? '停用' : '启用'}
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
        <ListingMonitorFormModal
          initial={editingTask}
          onClose={() => {
            setShowFormModal(false)
            setEditingTask(null)
          }}
          onSaved={handleSaved}
        />
      )}

      {batchAccountsField && (
        <BatchAccountsModal
          field={batchAccountsField}
          taskIds={Array.from(selectedIds)}
          onClose={() => setBatchAccountsField(null)}
          onSaved={async () => {
            setBatchAccountsField(null)
            await loadTasks(page, pageSize)
          }}
        />
      )}

      {showBatchCategory && (
        <BatchCategoryModal
          taskIds={Array.from(selectedIds)}
          onClose={() => setShowBatchCategory(false)}
          onSaved={async () => {
            setShowBatchCategory(false)
            await loadTasks(page, pageSize)
          }}
        />
      )}

      {showBatchDmContent && (
        <BatchDmContentModal
          taskIds={Array.from(selectedIds)}
          onClose={() => setShowBatchDmContent(false)}
          onSaved={async () => {
            setShowBatchDmContent(false)
            await loadTasks(page, pageSize)
          }}
        />
      )}

      <ConfirmModal
        isOpen={batchDeleteConfirmOpen}
        title="批量删除确认"
        message={`确定要删除选中的 ${selectedIds.size} 条监控任务吗？删除后将不再执行监控。`}
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

export default ListingMonitor
