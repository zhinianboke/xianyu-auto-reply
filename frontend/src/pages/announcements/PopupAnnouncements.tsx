/**
 * 弹窗公告管理页面
 *
 * 功能：
 * 1. 查看弹窗公告列表（按创建时间倒序）
 * 2. 管理员可新增、修改、启用/停用、删除
 * 3. 启用中的公告会在用户每次登录后弹窗展示
 */
import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  Megaphone,
  RefreshCw,
  Plus,
  Edit2,
  Trash2,
  X,
  Loader2,
  Power,
  ExternalLink,
} from 'lucide-react'
import {
  getPopupAnnouncements,
  createPopupAnnouncement,
  updatePopupAnnouncement,
  togglePopupAnnouncement,
  deletePopupAnnouncement,
} from '@/api/popupAnnouncements'
import type { PopupAnnouncement } from '@/api/popupAnnouncements'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { ConfirmModal } from '@/components/common/ConfirmModal'

export function PopupAnnouncements() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated, user } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState<PopupAnnouncement[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  // 新建/编辑弹窗
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [formTitle, setFormTitle] = useState('')
  const [formContent, setFormContent] = useState('')
  const [formLink, setFormLink] = useState('')
  const [formEnabled, setFormEnabled] = useState(true)
  const [saving, setSaving] = useState(false)

  // 删除确认弹窗
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; item: PopupAnnouncement | null }>({
    open: false,
    item: null,
  })
  const [deleting, setDeleting] = useState(false)

  const loadItems = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getPopupAnnouncements({ page, page_size: pageSize })
      if (result.success && result.data) {
        setItems(result.data.items)
        setTotal(result.data.total)
      } else {
        addToast({ type: 'error', message: result.message || '加载弹窗公告失败' })
      }
    } catch {
      addToast({ type: 'error', message: '加载弹窗公告失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadItems()
  }, [_hasHydrated, isAuthenticated, token, page, pageSize])

  const openAddModal = () => {
    setEditingId(null)
    setFormTitle('')
    setFormContent('')
    setFormLink('')
    setFormEnabled(true)
    setIsModalOpen(true)
  }

  const openEditModal = (item: PopupAnnouncement) => {
    setEditingId(item.id)
    setFormTitle(item.title)
    setFormContent(item.content)
    setFormLink(item.link || '')
    setFormEnabled(item.is_enabled)
    setIsModalOpen(true)
  }

  const handleSubmit = async () => {
    if (!formTitle.trim()) {
      addToast({ type: 'warning', message: '请输入公告标题' })
      return
    }
    if (!formContent.trim()) {
      addToast({ type: 'warning', message: '请输入公告内容' })
      return
    }
    setSaving(true)
    try {
      const payload = {
        title: formTitle.trim(),
        content: formContent.trim(),
        link: formLink.trim() || undefined,
        is_enabled: formEnabled,
      }
      const result = editingId
        ? await updatePopupAnnouncement(editingId, payload)
        : await createPopupAnnouncement(payload)
      if (result.success) {
        addToast({ type: 'success', message: editingId ? '弹窗公告更新成功' : '弹窗公告发布成功' })
        setIsModalOpen(false)
        loadItems()
      } else {
        addToast({ type: 'error', message: result.message || (editingId ? '更新失败' : '发布失败') })
      }
    } catch {
      addToast({ type: 'error', message: editingId ? '更新失败' : '发布失败' })
    } finally {
      setSaving(false)
    }
  }

  const handleToggle = async (item: PopupAnnouncement) => {
    try {
      const result = await togglePopupAnnouncement(item.id)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '操作成功' })
        loadItems()
      } else {
        addToast({ type: 'error', message: result.message || '操作失败' })
      }
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  const handleDelete = async (item: PopupAnnouncement) => {
    setDeleting(true)
    try {
      const result = await deletePopupAnnouncement(item.id)
      if (result.success) {
        addToast({ type: 'success', message: '删除成功' })
        setDeleteConfirm({ open: false, item: null })
        loadItems()
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setDeleting(false)
    }
  }

  if (loading && items.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">弹窗公告</h1>
          <p className="page-description">启用中的公告会在用户每次登录后弹窗展示</p>
        </div>
        <div className="flex gap-3">
          {user?.is_admin && (
            <button onClick={openAddModal} className="btn-ios-primary">
              <Plus className="w-4 h-4" />
              新建弹窗公告
            </button>
          )}
          <button onClick={loadItems} className="btn-ios-secondary">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {/* 列表 */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">
            <Megaphone className="w-4 h-4" />
            弹窗公告列表
          </h2>
          <span className="badge-primary">{total} 条</span>
        </div>
        <div className="divide-y divide-slate-100 dark:divide-slate-700">
          {items.length === 0 ? (
            <div className="py-12 text-center text-slate-500">
              <Megaphone className="w-12 h-12 mx-auto mb-3 text-slate-300" />
              <p>暂无弹窗公告</p>
            </div>
          ) : (
            items.map((item) => (
              <div
                key={item.id}
                className="p-4 hover:bg-slate-50 dark:hover:bg-slate-800/50 transition-colors"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <Megaphone className="w-4 h-4 text-blue-500" />
                      <span className="font-medium text-slate-900 dark:text-slate-100">
                        {item.title}
                      </span>
                      {item.is_enabled ? (
                        <span className="px-1.5 py-0.5 text-[10px] leading-none rounded bg-green-100 text-green-600 dark:bg-green-900/40 dark:text-green-300">启用</span>
                      ) : (
                        <span className="px-1.5 py-0.5 text-[10px] leading-none rounded bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400">停用</span>
                      )}
                    </div>
                    <p className="text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap">
                      {item.content}
                    </p>
                    {item.link && (
                      <a
                        href={item.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="inline-flex items-center gap-1 mt-1 text-xs text-blue-600 dark:text-blue-400 hover:underline truncate max-w-full"
                      >
                        {item.link}
                        <ExternalLink className="w-3 h-3 flex-shrink-0" />
                      </a>
                    )}
                    <div className="flex items-center gap-3 mt-2 text-xs text-slate-400">
                      <span>发布时间：{new Date(item.created_at).toLocaleString('zh-CN')}</span>
                      {item.updated_at !== item.created_at && (
                        <span>更新时间：{new Date(item.updated_at).toLocaleString('zh-CN')}</span>
                      )}
                    </div>
                  </div>
                  {user?.is_admin && (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleToggle(item)}
                        className={`p-2 rounded-lg transition-colors ${
                          item.is_enabled
                            ? 'text-green-500 hover:bg-green-50 dark:hover:bg-green-900/20'
                            : 'text-slate-400 hover:text-green-500 hover:bg-green-50 dark:hover:bg-green-900/20'
                        }`}
                        title={item.is_enabled ? '停用' : '启用'}
                      >
                        <Power className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => openEditModal(item)}
                        className="p-2 text-slate-400 hover:text-blue-500 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg transition-colors"
                        title="编辑"
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setDeleteConfirm({ open: true, item })}
                        className="p-2 text-slate-400 hover:text-red-500 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
                        title="删除"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))
          )}
        </div>
        {/* 分页 */}
        {total > 0 && (
          <div className="p-4 border-t border-slate-100 dark:border-slate-700 flex flex-col sm:flex-row items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value))
                  setPage(1)
                }}
                className="input-ios py-1 px-2 w-20"
              >
                <option value={10}>10条</option>
                <option value={20}>20条</option>
                <option value={50}>50条</option>
                <option value={100}>100条</option>
              </select>
              <span>共 {total} 条</span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page === 1}
                className="btn-ios-secondary btn-sm"
              >
                上一页
              </button>
              <span className="px-3 py-1.5 text-sm text-slate-500">
                {page} / {Math.ceil(total / pageSize)}
              </span>
              <button
                onClick={() => setPage((p) => p + 1)}
                disabled={page >= Math.ceil(total / pageSize)}
                className="btn-ios-secondary btn-sm"
              >
                下一页
              </button>
            </div>
          </div>
        )}
      </motion.div>

      {/* 新建/编辑弹窗 */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg">
            <div className="modal-header">
              <h2 className="text-lg font-semibold">{editingId ? '编辑弹窗公告' : '新建弹窗公告'}</h2>
              <button onClick={() => setIsModalOpen(false)} className="p-1 hover:bg-gray-100 dark:hover:bg-slate-700 rounded-lg">
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              <div className="input-group">
                <label className="input-label">公告标题 *</label>
                <input
                  type="text"
                  value={formTitle}
                  onChange={(e) => setFormTitle(e.target.value)}
                  placeholder="请输入公告标题"
                  className="input-ios"
                  maxLength={200}
                />
              </div>
              <div className="input-group">
                <label className="input-label">公告内容 *</label>
                <textarea
                  value={formContent}
                  onChange={(e) => setFormContent(e.target.value)}
                  placeholder="请输入公告内容"
                  className="input-ios min-h-[150px] resize-none"
                  maxLength={5000}
                />
              </div>
              <div className="input-group">
                <label className="input-label">跳转链接（选填）</label>
                <input
                  type="text"
                  value={formLink}
                  onChange={(e) => setFormLink(e.target.value)}
                  placeholder="https://"
                  className="input-ios"
                  maxLength={500}
                />
              </div>
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={formEnabled}
                  onChange={(e) => setFormEnabled(e.target.checked)}
                  className="w-4 h-4 accent-blue-500"
                />
                <span className="text-sm text-slate-700 dark:text-slate-300">启用（启用后用户登录时弹窗展示）</span>
              </label>
            </div>
            <div className="modal-footer">
              <button onClick={() => setIsModalOpen(false)} className="btn-ios-secondary" disabled={saving}>
                取消
              </button>
              <button onClick={handleSubmit} className="btn-ios-primary" disabled={saving}>
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                {editingId ? '保存' : '发布'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 删除确认弹窗 */}
      <ConfirmModal
        isOpen={deleteConfirm.open}
        title="删除确认"
        message="确定要删除这条弹窗公告吗？删除后无法恢复。"
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={() => deleteConfirm.item && handleDelete(deleteConfirm.item)}
        onCancel={() => setDeleteConfirm({ open: false, item: null })}
      />
    </div>
  )
}
