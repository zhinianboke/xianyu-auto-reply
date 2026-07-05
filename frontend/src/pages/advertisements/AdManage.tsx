/**
 * 广告管理页面（管理员）
 * 
 * 功能：
 * 1. 查看所有广告
 * 2. 复核/取消复核广告
 * 3. 修改、删除广告
 * 4. 支持图片预览
 */
import { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import {
  Megaphone,
  RefreshCw,
  Edit2,
  Trash2,
  X,
  Loader2,
  CheckCircle,
  Clock,
  Upload,
  DollarSign,
} from 'lucide-react'
import {
  getAllAds,
  approveAd,
  rejectAd,
  deleteAdAdmin,
  updateAdAdmin,
} from '@/api/advertisements'
import type { Advertisement } from '@/api/advertisements'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'

const AD_TYPE_OPTIONS = [
  { value: 'carousel', label: '轮播图' },
  { value: 'text', label: '文字广告' },
]

const STATUS_OPTIONS = [
  { value: 'unpaid', label: '待付款' },
  { value: 'pending', label: '待复核' },
  { value: 'approved', label: '已复核' },
]

export default function AdManage() {
  const { addToast } = useUIStore()
  const { token, isAuthenticated, _hasHydrated } = useAuthStore()

  const [loading, setLoading] = useState(true)
  const [ads, setAds] = useState<Advertisement[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filterStatus, setFilterStatus] = useState('')
  const [filterType, setFilterType] = useState('')

  // 编辑弹窗
  const [editAd, setEditAd] = useState<Advertisement | null>(null)
  const [formTitle, setFormTitle] = useState('')
  const [formContent, setFormContent] = useState('')
  const [formLink, setFormLink] = useState('')
  const [formExpireDate, setFormExpireDate] = useState('')
  const [formImageUrl, setFormImageUrl] = useState('')
  const [formAdType, setFormAdType] = useState('text')
  const [formStatus, setFormStatus] = useState('pending')
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 图片预览
  const [previewImage, setPreviewImage] = useState<string | null>(null)

  // 删除确认
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; ad: Advertisement | null }>({
    open: false,
    ad: null,
  })
  const [deleting, setDeleting] = useState(false)

  // 加载广告列表；可传入筛选覆盖值，避免 setState 异步导致的读取到旧筛选值
  const loadAds = async (overrides?: { status?: string; type?: string }) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    const statusValue = overrides?.status !== undefined ? overrides.status : filterStatus
    const typeValue = overrides?.type !== undefined ? overrides.type : filterType
    try {
      setLoading(true)
      const result = await getAllAds({
        page,
        page_size: pageSize,
        status: statusValue || undefined,
        ad_type: typeValue || undefined,
      })
      if (result.success && result.data) {
        setAds(result.data.items)
        setTotal(result.data.total)
      }
    } catch {
      addToast({ type: 'error', message: '加载广告列表失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAds()
  }, [_hasHydrated, isAuthenticated, token, page, pageSize])

  // 点击「查询」：使用当前筛选草稿回到第 1 页并加载
  const handleSearch = () => {
    if (page !== 1) {
      setPage(1) // 翻页依赖变化会触发 loadAds
    } else {
      loadAds()
    }
  }

  // 点击「重置」：清空筛选并重新加载
  const handleReset = () => {
    setFilterStatus('')
    setFilterType('')
    if (page !== 1) {
      setPage(1) // 翻页依赖变化会触发 loadAds，此时状态已清空
    } else {
      loadAds({ status: '', type: '' }) // 用覆盖值立即加载，避免 setState 异步
    }
  }

  const openEditModal = (ad: Advertisement) => {
    setEditAd(ad)
    setFormTitle(ad.title)
    setFormContent(ad.content || '')
    setFormLink(ad.link || '')
    setFormExpireDate(ad.expire_date || '')
    setFormImageUrl(ad.image_url || '')
    setFormAdType(ad.ad_type)
    setFormStatus(ad.status)
  }

  const handleSave = async () => {
    if (!editAd) return
    if (!formTitle.trim()) {
      addToast({ type: 'warning', message: '请输入标题' })
      return
    }
    setSaving(true)
    try {
      const result = await updateAdAdmin(editAd.id, {
        title: formTitle.trim(),
        ad_type: formAdType,
        content: formContent || undefined,
        link: formLink || undefined,
        expire_date: formExpireDate || undefined,
        image_url: formImageUrl || undefined,
        status: formStatus,
      })
      if (result.success) {
        addToast({ type: 'success', message: '保存成功' })
        setEditAd(null)
        loadAds()
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setSaving(false)
    }
  }

  const handleApprove = async (ad: Advertisement) => {
    try {
      const result = await approveAd(ad.id)
      if (result.success) {
        addToast({ type: 'success', message: '复核成功' })
        loadAds()
      } else {
        addToast({ type: 'error', message: result.message || '操作失败' })
      }
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  const handleReject = async (ad: Advertisement) => {
    try {
      const result = await rejectAd(ad.id)
      if (result.success) {
        addToast({ type: 'success', message: '已取消复核' })
        loadAds()
      } else {
        addToast({ type: 'error', message: result.message || '操作失败' })
      }
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  const handleDelete = async (ad: Advertisement) => {
    setDeleting(true)
    try {
      const result = await deleteAdAdmin(ad.id)
      if (result.success) {
        addToast({ type: 'success', message: '删除成功' })
        setDeleteConfirm({ open: false, ad: null })
        loadAds()
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setDeleting(false)
    }
  }

  const handleUploadImage = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.type.startsWith('image/')) {
      addToast({ type: 'warning', message: '请选择图片文件' })
      return
    }
    setUploading(true)
    try {
      const formData = new FormData()
      formData.append('image', file)
      const response = await fetch('/api/v1/upload/upload-image', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      })
      const result = await response.json()
      if (result.success && result.data?.image_url) {
        setFormImageUrl(result.data.image_url)
      } else {
        addToast({ type: 'error', message: result.message || '上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '上传失败' })
    } finally {
      setUploading(false)
      e.target.value = ''
    }
  }

  if (loading && ads.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">广告管理</h1>
          <p className="page-description">管理所有广告申请</p>
        </div>
        <button onClick={() => loadAds()} className="btn-ios-secondary">
          <RefreshCw className="w-4 h-4" />
          刷新
        </button>
      </div>

      {/* 筛选 */}
      <div className="flex flex-wrap items-end gap-4">
        <div className="input-group">
          <label className="input-label">状态</label>
          <Select
            value={filterStatus}
            onChange={setFilterStatus}
            options={[{ value: '', label: '全部状态' }, ...STATUS_OPTIONS]}
            className="w-32"
          />
        </div>
        <div className="input-group">
          <label className="input-label">类型</label>
          <Select
            value={filterType}
            onChange={setFilterType}
            options={[{ value: '', label: '全部类型' }, ...AD_TYPE_OPTIONS]}
            className="w-32"
          />
        </div>
        <div className="flex items-end gap-2 ml-auto">
          <button onClick={handleSearch} className="btn-ios-primary">
            查询
          </button>
          {(filterStatus || filterType) && (
            <button onClick={handleReset} className="btn-ios-secondary text-red-500">
              重置
            </button>
          )}
        </div>
      </div>

      {/* 表格 */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">
            <Megaphone className="w-4 h-4" />
            广告列表
          </h2>
          <span className="badge-primary">{total} 条</span>
        </div>
        <div className="overflow-x-auto">
          <div className="max-h-[500px] overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 dark:bg-slate-800 sticky top-0">
                <tr>
                  <th className="px-4 py-3 text-left font-medium">标题</th>
                  <th className="px-4 py-3 text-left font-medium">类型</th>
                  <th className="px-4 py-3 text-left font-medium">图片</th>
                  <th className="px-4 py-3 text-left font-medium">到期日</th>
                  <th className="px-4 py-3 text-left font-medium">状态</th>
                  <th className="px-4 py-3 text-left font-medium">创建时间</th>
                  <th className="px-4 py-3 text-center font-medium">操作</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
                {ads.length === 0 ? (
                  <tr>
                    <td colSpan={7} className="px-4 py-12 text-center text-slate-500">
                      暂无广告
                    </td>
                  </tr>
                ) : (
                  ads.map((ad) => (
                    <tr key={ad.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                      <td className="px-4 py-3">
                        <div className="max-w-[200px] truncate" title={ad.title}>
                          {ad.title}
                        </div>
                      </td>
                      <td className="px-4 py-3">
                        {ad.ad_type === 'carousel' ? '轮播图' : '文字广告'}
                      </td>
                      <td className="px-4 py-3">
                        {ad.image_url ? (
                          <img
                            src={ad.image_url}
                            alt=""
                            className="w-12 h-12 object-cover rounded cursor-pointer hover:opacity-80"
                            onClick={() => setPreviewImage(ad.image_url!)}
                          />
                        ) : (
                          <span className="text-slate-400">-</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        {ad.expire_date || <span className="text-slate-400">-</span>}
                      </td>
                      <td className="px-4 py-3">
                        {ad.status === 'approved' ? (
                          <span className="badge-success flex items-center gap-1 w-fit">
                            <CheckCircle className="w-3 h-3" />
                            已复核
                          </span>
                        ) : ad.status === 'unpaid' ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 w-fit">
                            <DollarSign className="w-3 h-3" />
                            待付款
                          </span>
                        ) : (
                          <span className="badge-warning flex items-center gap-1 w-fit">
                            <Clock className="w-3 h-3" />
                            待复核
                          </span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-slate-500">
                        {ad.created_at ? new Date(ad.created_at).toLocaleString('zh-CN') : '-'}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-center gap-1">
                          {ad.status === 'pending' ? (
                            <button
                              onClick={() => handleApprove(ad)}
                              className="p-1.5 text-green-600 hover:bg-green-50 dark:hover:bg-green-900/20 rounded"
                              title="复核"
                            >
                              <CheckCircle className="w-4 h-4" />
                            </button>
                          ) : (
                            <button
                              onClick={() => handleReject(ad)}
                              className="p-1.5 text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-900/20 rounded"
                              title="取消复核"
                            >
                              <Clock className="w-4 h-4" />
                            </button>
                          )}
                          <button
                            onClick={() => openEditModal(ad)}
                            className="p-1.5 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded"
                            title="编辑"
                          >
                            <Edit2 className="w-4 h-4" />
                          </button>
                          <button
                            onClick={() => setDeleteConfirm({ open: true, ad })}
                            className="p-1.5 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
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
        </div>
        {/* 分页 */}
        <div className="p-4 border-t border-slate-100 dark:border-slate-700 flex flex-col sm:flex-row items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span>共 {total} 条</span>
            <span>每页</span>
            <select
              value={pageSize}
              onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1) }}
              className="px-2 py-1 border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-800 text-sm"
            >
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
            <span>条</span>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={page === 1} className="btn-ios-secondary btn-sm">
              上一页
            </button>
            <span className="px-3 py-1.5 text-sm text-slate-500">
              {page} / {Math.max(1, Math.ceil(total / pageSize))}
            </span>
            <button onClick={() => setPage((p) => p + 1)} disabled={page >= Math.ceil(total / pageSize) || total === 0} className="btn-ios-secondary btn-sm">
              下一页
            </button>
          </div>
        </div>
      </motion.div>

      {/* 编辑弹窗 */}
      {editAd && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg">
            <div className="modal-header">
              <h2 className="text-lg font-semibold">编辑广告</h2>
              <button onClick={() => setEditAd(null)} className="p-1 hover:bg-gray-100 dark:hover:bg-slate-700 rounded-lg">
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              <div className="input-group">
                <label className="input-label">标题 *</label>
                <input type="text" value={formTitle} onChange={(e) => setFormTitle(e.target.value)} className="input-ios" maxLength={200} />
              </div>
              <div className="input-group">
                <label className="input-label">正文</label>
                <textarea value={formContent} onChange={(e) => setFormContent(e.target.value)} className="input-ios min-h-[80px] resize-none" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="input-group">
                  <label className="input-label">广告类型</label>
                  <Select value={formAdType} onChange={setFormAdType} options={AD_TYPE_OPTIONS} />
                </div>
                <div className="input-group">
                  <label className="input-label">审核状态</label>
                  <Select value={formStatus} onChange={setFormStatus} options={STATUS_OPTIONS} />
                </div>
              </div>
              <div className="input-group">
                <label className="input-label">链接</label>
                <input type="text" value={formLink} onChange={(e) => setFormLink(e.target.value)} className="input-ios" placeholder="https://" />
              </div>
              <div className="input-group">
                <label className="input-label">到期日期</label>
                <input type="date" value={formExpireDate} onChange={(e) => setFormExpireDate(e.target.value)} className="input-ios" />
              </div>
              <div className="input-group">
                <label className="input-label">图片</label>
                <div className="flex items-center gap-3">
                  {formImageUrl ? (
                    <div className="relative">
                      <img src={formImageUrl} alt="" className="w-20 h-20 object-cover rounded-lg border" />
                      <button onClick={() => setFormImageUrl('')} className="absolute -top-2 -right-2 p-0.5 bg-red-500 text-white rounded-full">
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => fileInputRef.current?.click()}
                      disabled={uploading}
                      className="w-20 h-20 rounded-lg border-2 border-dashed border-slate-300 dark:border-slate-600 flex items-center justify-center text-slate-400 hover:border-blue-400 hover:text-blue-400"
                    >
                      {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}
                    </button>
                  )}
                </div>
                <input ref={fileInputRef} type="file" accept="image/*" onChange={handleUploadImage} className="hidden" />
              </div>
            </div>
            <div className="modal-footer">
              <button onClick={() => setEditAd(null)} className="btn-ios-secondary" disabled={saving}>取消</button>
              <button onClick={handleSave} className="btn-ios-primary" disabled={saving}>
                {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 图片预览 */}
      {previewImage && (
        <div className="modal-overlay">
          <div className="relative max-w-4xl max-h-[90vh] p-2">
            <button
              onClick={() => setPreviewImage(null)}
              className="absolute -top-2 -right-2 z-10 p-1.5 bg-white dark:bg-gray-800 rounded-full shadow-lg hover:bg-gray-100 dark:hover:bg-gray-700"
              title="关闭"
            >
              <X className="w-5 h-5 text-gray-700 dark:text-gray-200" />
            </button>
            <img src={previewImage} alt="" className="max-w-full max-h-full object-contain rounded-lg" />
          </div>
        </div>
      )}

      {/* 删除确认 */}
      <ConfirmModal
        isOpen={deleteConfirm.open}
        title="删除确认"
        message="确定要删除这条广告吗？"
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={() => deleteConfirm.ad && handleDelete(deleteConfirm.ad)}
        onCancel={() => setDeleteConfirm({ open: false, ad: null })}
      />
    </div>
  )
}
