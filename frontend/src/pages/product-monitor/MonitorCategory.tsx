/**
 * 商品监控 - 监控分类 页面
 *
 * 功能：
 * 1. 查看监控分类列表（普通用户仅见自己的分类，管理员可见全部）
 * 2. 新建、修改分类（名称全局唯一）
 * 3. 删除分类（软删除；有关联任务/兜底配置时禁止删除）
 */
import { useEffect, useState } from 'react'
import { Loader2, Pencil, Plus, RefreshCw, Tags, Trash2, X } from 'lucide-react'
import {
  createListingMonitorCategory,
  deleteListingMonitorCategory,
  getListingMonitorCategories,
  updateListingMonitorCategory,
  type ListingMonitorCategory,
} from '@/api/listingMonitorCategory'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { PageLoading, Loading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

export function MonitorCategory() {
  const { addToast } = useUIStore()

  const [loading, setLoading] = useState(true)
  const [tableLoading, setTableLoading] = useState(false)
  const [categories, setCategories] = useState<ListingMonitorCategory[]>([])

  const [showFormModal, setShowFormModal] = useState(false)
  const [editing, setEditing] = useState<ListingMonitorCategory | null>(null)
  const [name, setName] = useState('')
  const [saving, setSaving] = useState(false)

  const [deleteTarget, setDeleteTarget] = useState<ListingMonitorCategory | null>(null)
  const [deleting, setDeleting] = useState(false)

  const loadCategories = async () => {
    try {
      setTableLoading(true)
      const result = await getListingMonitorCategories()
      if (!result.success || !result.data) {
        setCategories([])
        addToast({ type: 'error', message: result.message || '加载分类列表失败' })
        return
      }
      setCategories(result.data)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载分类列表失败') })
    } finally {
      setLoading(false)
      setTableLoading(false)
    }
  }

  useEffect(() => {
    void loadCategories()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleOpenCreate = () => {
    setEditing(null)
    setName('')
    setShowFormModal(true)
  }

  const handleOpenEdit = (category: ListingMonitorCategory) => {
    setEditing(category)
    setName(category.name)
    setShowFormModal(true)
  }

  const handleSubmit = async () => {
    const trimmed = name.trim()
    if (!trimmed) {
      addToast({ type: 'warning', message: '请填写分类名称' })
      return
    }
    setSaving(true)
    try {
      const result = editing
        ? await updateListingMonitorCategory(editing.id, trimmed)
        : await createListingMonitorCategory(trimmed)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || (editing ? '修改分类失败' : '新建分类失败') })
        return
      }
      addToast({ type: 'success', message: result.message || (editing ? '修改成功' : '创建成功') })
      setShowFormModal(false)
      setEditing(null)
      setName('')
      await loadCategories()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, editing ? '修改分类失败' : '新建分类失败') })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      const result = await deleteListingMonitorCategory(deleteTarget.id)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '删除分类失败' })
        return
      }
      addToast({ type: 'success', message: result.message || '删除成功' })
      setDeleteTarget(null)
      await loadCategories()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '删除分类失败') })
    } finally {
      setDeleting(false)
    }
  }

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {saving && <Loading fullScreen text={editing ? '正在保存分类...' : '正在创建分类...'} />}

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">监控分类</h1>
          <p className="page-description">
            管理商品监控分类（个人仅见自己的分类，名称全局唯一）。新建监控任务、配置下单/采集兜底账号时按分类归类。
          </p>
        </div>
        <div className="flex gap-3 flex-wrap">
          <button className="btn-ios-primary" onClick={handleOpenCreate}>
            <Plus className="w-4 h-4" />
            新建分类
          </button>
          <button className="btn-ios-secondary" onClick={() => void loadCategories()} disabled={tableLoading}>
            {tableLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            刷新
          </button>
        </div>
      </div>

      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 280px)', minHeight: '420px' }}>
        <div className="vben-card-header flex items-center justify-between">
          <h2 className="vben-card-title">
            <Tags className="w-4 h-4" />
            分类列表
          </h2>
          <span className="badge-primary">共 {categories.length} 个</span>
        </div>

        <div className="flex-1 overflow-auto">
          <table className="table-ios min-w-[600px]">
            <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
              <tr>
                <th>分类ID</th>
                <th>分类名称</th>
                <th>创建时间</th>
                <th>更新时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tableLoading ? (
                <tr>
                  <td colSpan={5} className="text-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : categories.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-center py-12 text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <Tags className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>暂无分类，点击右上角新建</p>
                    </div>
                  </td>
                </tr>
              ) : (
                categories.map((item) => (
                  <tr key={item.id}>
                    <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">#{item.id}</td>
                    <td className="font-medium text-slate-800 dark:text-slate-100">{item.name}</td>
                    <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">
                      {item.created_at ? new Date(item.created_at).toLocaleString('zh-CN') : '-'}
                    </td>
                    <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">
                      {item.updated_at ? new Date(item.updated_at).toLocaleString('zh-CN') : '-'}
                    </td>
                    <td className="whitespace-nowrap">
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleOpenEdit(item)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 text-blue-600 dark:text-blue-400 transition-colors"
                        >
                          <Pencil className="w-4 h-4" />编辑
                        </button>
                        <button
                          onClick={() => setDeleteTarget(item)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-600 dark:text-red-400 transition-colors"
                        >
                          <Trash2 className="w-4 h-4" />删除
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

      {showFormModal && (
        <div className="modal-overlay">
          <div className="modal-content max-w-md">
            <div className="modal-header">
              <h2 className="modal-title">{editing ? '编辑分类' : '新建分类'}</h2>
              <button className="modal-close" onClick={() => setShowFormModal(false)} disabled={saving}>
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="modal-body">
              <div className="input-group">
                <label className="input-label">分类名称 <span className="text-red-500">*</span></label>
                <input
                  className="input-ios"
                  placeholder="如：数码产品"
                  value={name}
                  maxLength={100}
                  autoFocus
                  onChange={(e) => setName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') void handleSubmit()
                  }}
                />
                <p className="text-xs text-slate-400 mt-1">名称全局唯一；ID 自动生成。</p>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-ios-secondary" onClick={() => setShowFormModal(false)} disabled={saving}>取消</button>
              <button className="btn-ios-primary" onClick={() => void handleSubmit()} disabled={saving}>
                {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                {editing ? '保存修改' : '确认新建'}
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmModal
        isOpen={Boolean(deleteTarget)}
        title="删除分类确认"
        message={`确定要删除分类「${deleteTarget?.name ?? ''}」吗？若该分类下仍有监控任务或兜底账号配置将无法删除。`}
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={() => void handleDelete()}
        onCancel={() => {
          if (!deleting) setDeleteTarget(null)
        }}
      />
    </div>
  )
}

export default MonitorCategory
