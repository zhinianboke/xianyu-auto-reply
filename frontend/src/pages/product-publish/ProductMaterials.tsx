/**
 * 商品素材库页面
 *
 * 功能：
 * 1. 分页展示所有商品素材
 * 2. 新建/编辑/删除素材
 * 3. 筛选（标题、分类、成色）
 * 4. 勾选批量删除
 * 5. 素材用于单品发布和批量发布
 */
import { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { Plus, Pencil, Trash2, RefreshCw, Image, ChevronLeft, ChevronRight, Search, X, Bot } from 'lucide-react'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import {
  getMaterials,
  deleteMaterial,
  batchDeleteMaterials,
  getAiListingTaskStatus,
  getAiListingTasks,
  type AiListingTaskStatus,
  type ProductMaterial,
} from '@/api/productPublish'
import { PageLoading } from '@/components/common/Loading'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { MaterialFormModal } from './MaterialFormModal'
import { AiListingModal } from './AiListingModal'

const CATEGORIES = ['数码家电', '服饰鞋包', '家居日用', '图书音像', '美妆个护', '母婴用品', '运动户外', '食品生鲜', '虚拟商品', '其他']
const CONDITIONS = ['全新', '99新', '95新', '9成新', '8成新', '7成新以下']
const AI_LISTING_TASK_STORAGE_KEY = 'product_publish_ai_listing_task_ids'
export function ProductMaterials() {
  const { addToast } = useUIStore()
  const { user } = useAuthStore()
  const isAdmin = Boolean(user?.is_admin)
  const [loading, setLoading] = useState(true)
  const [tableLoading, setTableLoading] = useState(false)
  const [materials, setMaterials] = useState<ProductMaterial[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [totalPages, setTotalPages] = useState(0)
  const [showModal, setShowModal] = useState(false)
  const [showAiListingModal, setShowAiListingModal] = useState(false)
  const [editTarget, setEditTarget] = useState<ProductMaterial | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; item: ProductMaterial | null }>({ open: false, item: null })
  const [deleting, setDeleting] = useState(false)
  const [aiListingTasks, setAiListingTasks] = useState<AiListingTaskStatus[]>([])
  const [taskSyncLoaded, setTaskSyncLoaded] = useState(false)
  const aiListingTasksRef = useRef<AiListingTaskStatus[]>([])
  const materialRefreshTickRef = useRef(0)

  const [filterTitle, setFilterTitle] = useState('')
  const [filterCategory, setFilterCategory] = useState('')
  const [filterCondition, setFilterCondition] = useState('')

  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [batchDeleteConfirm, setBatchDeleteConfirm] = useState(false)
  const [batchDeleting, setBatchDeleting] = useState(false)
  const runningTaskCount = aiListingTasks.filter(item => !item.finished).length

  const load = async (p = page, size = pageSize, options?: { silent?: boolean }) => {
    if (!options?.silent) setTableLoading(true)
    try {
      const filters: { title?: string; category?: string; condition?: string } = {}
      if (filterTitle.trim()) filters.title = filterTitle.trim()
      if (filterCategory) filters.category = filterCategory
      if (filterCondition) filters.condition = filterCondition
      const res = await getMaterials(p, size, Object.keys(filters).length > 0 ? filters : undefined)
      if (res.success) {
        setMaterials(res.data.list)
        setTotal(res.data.total)
        setTotalPages(res.data.total_pages)
        const currentIds = new Set(res.data.list.map(m => m.id))
        setSelectedIds(prev => prev.filter(id => currentIds.has(id)))
      } else {
        addToast({ type: 'error', message: res.message || '加载失败' })
      }
    } catch {
      if (!options?.silent) {
        addToast({ type: 'error', message: '网络错误，请重试' })
      }
    } finally {
      setLoading(false)
      if (!options?.silent) setTableLoading(false)
    }
  }

  useEffect(() => { load(page, pageSize) }, [page, pageSize])

  useEffect(() => {
    aiListingTasksRef.current = aiListingTasks
  }, [aiListingTasks])

  useEffect(() => {
    try {
      const raw = localStorage.getItem(AI_LISTING_TASK_STORAGE_KEY)
      const taskIds = raw ? JSON.parse(raw) : []
      if (!Array.isArray(taskIds) || taskIds.length === 0) return
      setAiListingTasks(taskIds.map((taskId: string) => ({
        task_id: String(taskId),
        config_id: 0,
        config_name: '',
        total: 0,
        current: 0,
        success: 0,
        failed: 0,
        status: 'pending',
        message: '等待同步任务状态',
        progress_percent: 0,
        active_stage: 'pending',
        stage_label: '等待开始',
        stage_detail: '',
        step_counts: {
          text: { done: 0, total: 0 },
          image_polish: { done: 0, total: 0 },
          image_generate: { done: 0, total: 0 },
          material_create: { done: 0, total: 0 },
        },
        created_material_ids: [],
        errors: [],
        finished: false,
      })))
    } catch {
      localStorage.removeItem(AI_LISTING_TASK_STORAGE_KEY)
    }
  }, [])

  useEffect(() => {
    let stopped = false
    const currentTasks = aiListingTasksRef.current
    const hasRunningTasks = currentTasks.some(item => !item.finished)
    if (taskSyncLoaded && !hasRunningTasks) return

    const syncTasks = async () => {
      try {
        const previousTasks = aiListingTasksRef.current
        const previousRunning = previousTasks.some(item => !item.finished)
        const listRes = await getAiListingTasks()
        if (!listRes.success || !listRes.data || stopped) return

        const remoteTasks = listRes.data
        const remoteTaskMap = new Map(remoteTasks.map(item => [item.task_id, item]))
        const rememberedTaskIds = previousTasks.map(item => item.task_id)
        const mergedTaskIds = rememberedTaskIds.length > 0
          ? rememberedTaskIds
          : remoteTasks.filter(item => !item.finished).map(item => item.task_id)
        const detailedTasks = await Promise.all(mergedTaskIds.map(async taskId => {
          const remoteTask = remoteTaskMap.get(taskId)
          if (remoteTask) return remoteTask
          const res = await getAiListingTaskStatus(taskId)
          return res.success && res.data ? res.data : null
        }))
        if (stopped) return

        const nextTasks = detailedTasks.filter((item): item is AiListingTaskStatus => Boolean(item))
        setTaskSyncLoaded(true)
        aiListingTasksRef.current = nextTasks
        setAiListingTasks(nextTasks)
        const nextTaskIds = nextTasks.map(item => item.task_id)
        if (nextTaskIds.length > 0) {
          localStorage.setItem(AI_LISTING_TASK_STORAGE_KEY, JSON.stringify(nextTaskIds))
        } else {
          localStorage.removeItem(AI_LISTING_TASK_STORAGE_KEY)
        }

        const nextRunning = nextTasks.some(item => !item.finished)
        if (nextRunning) {
          materialRefreshTickRef.current += 1
          if (materialRefreshTickRef.current % 2 === 0) {
            void load(page, pageSize, { silent: true })
          }
        } else {
          materialRefreshTickRef.current = 0
        }
        if (previousRunning && !nextRunning) {
          void load(page, pageSize, { silent: true })
        }
      } catch {
        // 保留当前任务状态，下一轮继续轮询
      }
    }

    syncTasks()
    const timer = window.setInterval(syncTasks, 1500)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [page, pageSize, filterTitle, filterCategory, filterCondition, taskSyncLoaded, aiListingTasks.length, runningTaskCount])

  const handleFilter = () => {
    setPage(1)
    setSelectedIds([])
    load(1, pageSize)
  }

  const handleResetFilter = () => {
    setFilterTitle('')
    setFilterCategory('')
    setFilterCondition('')
    setPage(1)
    setSelectedIds([])
    setTableLoading(true)
    getMaterials(1, pageSize).then(res => {
      if (res.success) {
        setMaterials(res.data.list)
        setTotal(res.data.total)
        setTotalPages(res.data.total_pages)
        setSelectedIds([])
      }
    }).catch(() => {
      addToast({ type: 'error', message: '加载失败' })
    }).finally(() => {
      setLoading(false)
      setTableLoading(false)
    })
  }

  const handleConfirmDelete = async () => {
    if (!deleteConfirm.item) return
    setDeleting(true)
    try {
      const res = await deleteMaterial(deleteConfirm.item.id)
      if (res.success) {
        addToast({ type: 'success', message: '删除成功' })
        setDeleteConfirm({ open: false, item: null })
        setSelectedIds(prev => prev.filter(id => id !== deleteConfirm.item!.id))
        load(page, pageSize)
      } else {
        addToast({ type: 'error', message: res.message || '删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '删除失败，请重试' })
    } finally {
      setDeleting(false)
    }
  }

  const handleBatchDelete = async () => {
    if (selectedIds.length === 0) return
    setBatchDeleting(true)
    try {
      const res = await batchDeleteMaterials(selectedIds)
      if (res.success) {
        addToast({ type: 'success', message: res.message || `成功删除 ${selectedIds.length} 条素材` })
        setBatchDeleteConfirm(false)
        setSelectedIds([])
        load(page, pageSize)
      } else {
        addToast({ type: 'error', message: res.message || '批量删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '批量删除失败，请重试' })
    } finally {
      setBatchDeleting(false)
    }
  }

  const handleSelectAll = () => {
    if (materials.length === 0) return
    const currentPageIds = materials.map(m => m.id)
    const allSelected = currentPageIds.every(id => selectedIds.includes(id))
    if (allSelected) {
      setSelectedIds(prev => prev.filter(id => !currentPageIds.includes(id)))
    } else {
      setSelectedIds(prev => [...new Set([...prev, ...currentPageIds])])
    }
  }

  const toggleSelect = (id: number) => {
    setSelectedIds(prev =>
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    )
  }

  const closeAiListingTask = (taskId: string) => {
    setAiListingTasks(prev => {
      const nextTasks = prev.filter(item => item.task_id !== taskId)
      const nextTaskIds = nextTasks.map(item => item.task_id)
      if (nextTaskIds.length > 0) {
        localStorage.setItem(AI_LISTING_TASK_STORAGE_KEY, JSON.stringify(nextTaskIds))
      } else {
        localStorage.removeItem(AI_LISTING_TASK_STORAGE_KEY)
      }
      return nextTasks
    })
  }

  const handleAiListingTaskStarted = (taskId: string, total: number, configId: number, configName: string) => {
    setAiListingTasks(prev => {
      const nextTasks = [
        {
          task_id: taskId,
          config_id: configId,
          config_name: configName,
          total,
          current: 0,
          success: 0,
          failed: 0,
          status: 'pending' as const,
          message: '任务已提交，正在后台生成',
          progress_percent: 0,
          active_stage: 'pending',
          stage_label: '任务已提交',
          stage_detail: '等待后台开始处理',
          step_counts: {
            text: { done: 0, total },
            image_polish: { done: 0, total },
            image_generate: { done: 0, total },
            material_create: { done: 0, total },
          },
          created_material_ids: [],
          errors: [],
          finished: false,
        },
        ...prev.filter(item => item.task_id !== taskId),
      ]
      localStorage.setItem(AI_LISTING_TASK_STORAGE_KEY, JSON.stringify(nextTasks.map(item => item.task_id)))
      return nextTasks
    })
  }

  const runningAiListingTasks = aiListingTasks.filter(item => !item.finished)
  const aiListingTaskLimitReached = runningTaskCount >= 5
  const allCurrentSelected = materials.length > 0 && materials.every(m => selectedIds.includes(m.id))
  const handlePageSizeChange = (size: number) => { setPageSize(size); setPage(1) }

  const handleOpenAiListingModal = () => {
    if (aiListingTaskLimitReached) {
      addToast({ type: 'warning', message: '最多只能同时执行5个AI铺货任务，请等待生成完成后再继续铺货' })
      return
    }
    setShowAiListingModal(true)
  }

  if (loading) return <PageLoading />

  return (
    <div className="space-y-3 sm:space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="page-title">商品素材库</h1>
          <p className="page-description">管理商品素材，用于单品发布和批量发布</p>
        </div>
        <div className="flex gap-2">
          {selectedIds.length > 0 && (
            <button className="btn-ios-danger" onClick={() => setBatchDeleteConfirm(true)}>
              <Trash2 className="w-4 h-4" />批量删除 ({selectedIds.length})
            </button>
          )}
          <button className="btn-ios-secondary" onClick={() => load(page, pageSize)} disabled={tableLoading}>
            <RefreshCw className={`w-4 h-4 ${tableLoading ? 'animate-spin' : ''}`} />刷新
          </button>
          <button
            className="btn-ios-primary"
            style={{
              backgroundColor: 'transparent',
              borderColor: 'transparent',
              backgroundImage:
                'linear-gradient(135deg, rgb(var(--theme-gradient-from)) 0%, rgb(var(--theme-gradient-via)) 55%, rgb(var(--theme-gradient-to)) 100%)',
            }}
            disabled={aiListingTaskLimitReached}
            onClick={handleOpenAiListingModal}
          >
            <Bot className="w-4 h-4" />AI铺货
          </button>
          <button className="btn-ios-primary" onClick={() => { setEditTarget(null); setShowModal(true) }}>
            <Plus className="w-4 h-4" />新建素材
          </button>
        </div>
      </div>

      {aiListingTasks.length > 0 && (
        <div className="vben-card">
          <div className="vben-card-body py-3 px-4">
            <div className="space-y-3">
              <div className="flex items-center gap-2 min-w-[180px]">
                <Bot className="w-4 h-4 text-blue-500" />
                <span className="font-medium text-slate-700 dark:text-slate-200">AI铺货后台任务</span>
                <span className="text-xs text-slate-400">运行中 {runningAiListingTasks.length}/5</span>
              </div>
              {aiListingTasks.map(task => {
                const progress = Math.max(0, Math.min(100, Number(task.progress_percent || 0)))
                return (
                  <div key={task.task_id} className="flex items-start gap-3 rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2.5">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-3">
                        <div className="min-w-0">
                          <div className="text-sm font-medium text-slate-700 dark:text-slate-200 truncate">{task.config_name || `配置 ID ${task.config_id}`}</div>
                          <div className="mt-1 flex items-center gap-2 min-w-0 text-xs text-slate-400">
                            <span className="flex-shrink-0">任务 {task.task_id.slice(0, 8)}</span>
                            {!task.finished && <span className="inline-flex w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse flex-shrink-0" />}
                            <span className="truncate">{task.stage_label || task.message}</span>
                          </div>
                        </div>
                        <span className="text-xs text-slate-400 flex-shrink-0">{progress.toFixed(0)}%</span>
                      </div>
                      <div className="mt-2 h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full transition-[width] duration-1000 ease-out bg-gradient-to-r from-sky-500 via-blue-500 to-violet-500"
                          style={{ width: `${progress}%` }}
                        />
                      </div>
                      <div className="mt-2 text-xs text-slate-500 truncate">
                        {task.current}/{task.total}，成功 {task.success}，失败 {task.failed}，{task.stage_detail || task.message}
                      </div>
                      {task.errors.length > 0 && (
                        <div className="mt-1 text-xs text-red-500 truncate">
                          {task.errors[task.errors.length - 1]}
                        </div>
                      )}
                    </div>
                    {task.finished && (
                      <button className="btn-ios-secondary btn-sm" onClick={() => closeAiListingTask(task.task_id)}>
                        关闭
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      )}

      <div className="vben-card">
        <div className="vben-card-body py-3 px-4">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <input
                className="input-ios w-48"
                placeholder="搜索标题..."
                value={filterTitle}
                onChange={e => setFilterTitle(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleFilter()}
              />
            </div>
            <select className="input-ios w-32" value={filterCategory} onChange={e => { setFilterCategory(e.target.value) }}>
              <option value="">全部分类</option>
              {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <select className="input-ios w-28" value={filterCondition} onChange={e => { setFilterCondition(e.target.value) }}>
              <option value="">全部成色</option>
              {CONDITIONS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
            <button className="btn-ios-primary btn-sm" onClick={handleFilter}>
              <Search className="w-3.5 h-3.5" />筛选
            </button>
            {(filterTitle || filterCategory || filterCondition) && (
              <button className="btn-ios-secondary btn-sm" onClick={handleResetFilter}>
                <X className="w-3.5 h-3.5" />重置
              </button>
            )}
          </div>
        </div>
      </div>

      <motion.div
        initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
        className="vben-card flex flex-col"
        style={{ height: 'calc(100vh - 280px)', minHeight: '400px' }}
      >
        <div className="vben-card-header">
          <h2 className="vben-card-title"><Image className="w-4 h-4" />素材列表</h2>
          <span className="badge-primary">共 {total} 条</span>
        </div>
        <div className="flex-1 overflow-x-auto overflow-y-auto">
          <table className="table-ios">
            <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
              <tr>
                <th className="w-10">
                  <input
                    type="checkbox"
                    checked={allCurrentSelected}
                    onChange={handleSelectAll}
                    className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  />
                </th>
                {isAdmin && <th>所属用户</th>}
                <th>标题</th>
                <th>价格</th>
                <th>分类</th>
                <th>成色</th>
                <th>图片</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tableLoading ? (
                <tr><td colSpan={isAdmin ? 9 : 8} className="text-center py-12">
                  <RefreshCw className="w-6 h-6 animate-spin text-blue-500 mx-auto" />
                </td></tr>
              ) : materials.length === 0 ? (
                <tr><td colSpan={isAdmin ? 9 : 8} className="text-center py-12 text-slate-400">
                  <div className="flex flex-col items-center gap-2">
                    <Image className="w-12 h-12 text-slate-300" />
                    <p>暂无素材，点击「新建素材」添加</p>
                  </div>
                </td></tr>
              ) : materials.map(m => (
                <tr key={m.id} className={selectedIds.includes(m.id) ? 'bg-blue-50 dark:bg-blue-900/10' : ''}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(m.id)}
                      onChange={() => toggleSelect(m.id)}
                      className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                    />
                  </td>
                  {isAdmin && (
                    <td className="text-sm text-slate-600 dark:text-slate-400 whitespace-nowrap">
                      {m.username || '-'}
                    </td>
                  )}
                  <td className="max-w-[200px]">
                    <span className="truncate block font-medium text-slate-800 dark:text-slate-100" title={m.title}>{m.title}</span>
                  </td>
                  <td>
                    <span className="text-amber-600 font-medium">{m.price}</span>
                    {m.original_price && (
                      <span className="text-xs text-slate-400 line-through ml-1">{m.original_price}</span>
                    )}
                  </td>
                  <td className="text-slate-500">{m.category || '-'}</td>
                  <td><span className="badge-gray">{m.condition}</span></td>
                  <td><span className="badge-info">{(m.images || []).length} 张</span></td>
                  <td className="text-sm text-slate-500 whitespace-nowrap">
                    {m.created_at ? new Date(m.created_at).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '-'}
                  </td>
                  <td>
                    <div className="table-actions">
                      <button className="table-action-btn" title="编辑" onClick={() => { setEditTarget(m); setShowModal(true) }}>
                        <Pencil className="w-4 h-4 text-blue-500" />
                      </button>
                      <button className="table-action-btn" title="删除" onClick={() => setDeleteConfirm({ open: true, item: m })}>
                        <Trash2 className="w-4 h-4 text-red-500" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {total > 0 && (
          <div className="flex-shrink-0 flex flex-col sm:flex-row items-center justify-between px-4 py-3 border-t border-slate-200 dark:border-slate-700 gap-3">
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={e => handlePageSizeChange(Number(e.target.value))}
                className="px-2 py-1 border border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value={10}>10 条</option>
                <option value={20}>20 条</option>
                <option value={50}>50 条</option>
                <option value={100}>100 条</option>
              </select>
              <span>共 {total} 条</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-500">第 {page} / {totalPages} 页</span>
              <button
                onClick={() => setPage(p => p - 1)}
                disabled={page <= 1 || tableLoading}
                className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <button
                onClick={() => setPage(p => p + 1)}
                disabled={page >= totalPages || tableLoading}
                className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </motion.div>

      {showModal && (
        <MaterialFormModal
          initial={editTarget}
          onClose={() => setShowModal(false)}
          onSaved={() => { setShowModal(false); load(page, pageSize) }}
        />
      )}

      {showAiListingModal && (
        <AiListingModal
          onClose={() => setShowAiListingModal(false)}
          onTaskStarted={handleAiListingTaskStarted}
        />
      )}

      <ConfirmModal
        isOpen={deleteConfirm.open}
        title="确认删除"
        message={`确认删除素材「${deleteConfirm.item?.title ?? ''}」？此操作不可撤销。`}
        confirmText="删除"
        type="danger"
        loading={deleting}
        onConfirm={handleConfirmDelete}
        onCancel={() => setDeleteConfirm({ open: false, item: null })}
      />

      <ConfirmModal
        isOpen={batchDeleteConfirm}
        title="确认批量删除"
        message={`确认删除选中的 ${selectedIds.length} 条素材？此操作不可撤销。`}
        confirmText={`删除 ${selectedIds.length} 条`}
        type="danger"
        loading={batchDeleting}
        onConfirm={handleBatchDelete}
        onCancel={() => setBatchDeleteConfirm(false)}
      />
    </div>
  )
}

export default ProductMaterials
