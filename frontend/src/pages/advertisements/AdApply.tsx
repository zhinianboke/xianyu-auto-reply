/**
 * 广告申请页面（所有用户）
 * 
 * 功能：
 * 1. 新建广告申请
 * 2. 修改、删除自己的广告
 * 3. 支持图片上传和预览
 */
import { useState, useEffect, useRef, useMemo } from 'react'
import { motion } from 'framer-motion'
import {
  Megaphone,
  RefreshCw,
  Plus,
  Edit2,
  Trash2,
  X,
  Loader2,
  CheckCircle,
  Clock,
  Upload,
  CreditCard,
  DollarSign,
} from 'lucide-react'
import {
  getMyAds,
  getAdPrices,
  createAd,
  updateMyAd,
  deleteMyAd,
} from '@/api/advertisements'
import type { Advertisement } from '@/api/advertisements'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { AdPaymentModal } from './AdPaymentModal'

const AD_TYPE_OPTIONS = [
  { value: 'carousel', label: '轮播图' },
  { value: 'text', label: '文字广告' },
]

export default function AdApply() {
  const { addToast } = useUIStore()
  const { token, isAuthenticated, _hasHydrated } = useAuthStore()

  const [loading, setLoading] = useState(true)
  const [ads, setAds] = useState<Advertisement[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  // 新建/编辑弹窗
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editAd, setEditAd] = useState<Advertisement | null>(null)
  const [formTitle, setFormTitle] = useState('')
  const [formContent, setFormContent] = useState('')
  const [formLink, setFormLink] = useState('')
  const [formImageUrl, setFormImageUrl] = useState('')
  const [formAdType, setFormAdType] = useState('text')
  const [formMonths, setFormMonths] = useState('')
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 广告价格
  const [adPrices, setAdPrices] = useState<Record<string, string>>({})

  // 图片预览
  const [previewImage, setPreviewImage] = useState<string | null>(null)

  // 付款弹窗
  const [paymentAd, setPaymentAd] = useState<Advertisement | null>(null)
  const [showPayment, setShowPayment] = useState(false)

  // 删除确认
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; ad: Advertisement | null }>({
    open: false,
    ad: null,
  })
  const [deleting, setDeleting] = useState(false)

  // 计算预估金额和到期日
  const estimatedAmount = useMemo(() => {
    const months = parseInt(formMonths)
    if (!months || months <= 0) return null
    const unitPrice = parseFloat(adPrices[formAdType] || '0')
    if (!unitPrice) return null
    return (unitPrice * months).toFixed(2)
  }, [formMonths, formAdType, adPrices])

  const estimatedExpireDate = useMemo(() => {
    const months = parseInt(formMonths)
    if (!months || months <= 0) return null
    const d = new Date()
    d.setMonth(d.getMonth() + months)
    return d.toISOString().split('T')[0]
  }, [formMonths])

  const loadAds = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const [adsResult, pricesResult] = await Promise.all([
        getMyAds({ page, page_size: pageSize }),
        getAdPrices(),
      ])
      if (adsResult.success && adsResult.data) {
        setAds(adsResult.data.items)
        setTotal(adsResult.data.total)
      }
      if (pricesResult.success && pricesResult.data) {
        setAdPrices(pricesResult.data)
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

  const openAddModal = () => {
    setEditAd(null)
    setFormTitle('')
    setFormContent('')
    setFormLink('')
    setFormImageUrl('')
    setFormAdType('text')
    setFormMonths('')
    setIsModalOpen(true)
  }

  const openEditModal = (ad: Advertisement) => {
    setEditAd(ad)
    setFormTitle(ad.title)
    setFormContent(ad.content || '')
    setFormLink(ad.link || '')
    setFormImageUrl(ad.image_url || '')
    setFormAdType(ad.ad_type)
    setFormMonths(ad.months ? String(ad.months) : '')
    setIsModalOpen(true)
  }

  const handleSave = async () => {
    if (!formTitle.trim()) {
      addToast({ type: 'warning', message: '请输入标题' })
      return
    }
    const months = parseInt(formMonths)
    if (!months || months <= 0) {
      addToast({ type: 'warning', message: '请输入有效的月数（大于0的整数）' })
      return
    }
    setSaving(true)
    try {
      const data = {
        title: formTitle.trim(),
        ad_type: formAdType,
        months,
        content: formContent || undefined,
        link: formLink || undefined,
        image_url: formImageUrl || undefined,
      }
      const result = editAd
        ? await updateMyAd(editAd.id, data)
        : await createAd(data)
      if (result.success) {
        addToast({ type: 'success', message: editAd ? '修改成功' : '提交成功' })
        setIsModalOpen(false)
        loadAds()
      } else {
        addToast({ type: 'error', message: result.message || '操作失败' })
      }
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (ad: Advertisement) => {
    setDeleting(true)
    try {
      const result = await deleteMyAd(ad.id)
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
          <h1 className="page-title">广告申请</h1>
          <p className="page-description">申请发布广告</p>
        </div>
        <div className="flex gap-3">
          <button onClick={openAddModal} className="btn-ios-primary">
            <Plus className="w-4 h-4" />
            新建申请
          </button>
          <button onClick={loadAds} className="btn-ios-secondary">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {/* 表格 */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">
            <Megaphone className="w-4 h-4" />
            我的广告
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
                      暂无广告申请
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
                            onClick={() => setPreviewImage(ad.image_url)}
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
                          {ad.status === 'unpaid' && (
                            <button
                              onClick={() => { setPaymentAd(ad); setShowPayment(true) }}
                              className="px-3 py-1.5 text-xs font-bold text-white bg-gradient-to-r from-orange-500 to-red-500 hover:from-orange-600 hover:to-red-600 rounded-lg shadow-sm hover:shadow-md transition-all flex items-center gap-1"
                              title="付款"
                            >
                              <CreditCard className="w-3.5 h-3.5" />
                              付款
                            </button>
                          )}
                          {ad.status !== 'approved' && (
                            <button
                              onClick={() => openEditModal(ad)}
                              className="p-1.5 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded"
                              title="编辑"
                            >
                              <Edit2 className="w-4 h-4" />
                            </button>
                          )}
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

      {/* 新建/编辑弹窗 */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg">
            <div className="modal-header">
              <h2 className="text-lg font-semibold">{editAd ? '编辑广告' : '新建广告申请'}</h2>
              <button onClick={() => setIsModalOpen(false)} className="p-1 hover:bg-gray-100 dark:hover:bg-slate-700 rounded-lg">
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              <div className="input-group">
                <label className="input-label">标题 *</label>
                <input type="text" value={formTitle} onChange={(e) => setFormTitle(e.target.value)} className="input-ios" maxLength={200} placeholder="广告标题" />
              </div>
              <div className="input-group">
                <label className="input-label">正文</label>
                <textarea value={formContent} onChange={(e) => setFormContent(e.target.value)} className="input-ios min-h-[80px] resize-none" placeholder="广告正文内容" />
              </div>
              <div className="input-group">
                <label className="input-label">广告类型</label>
                <Select value={formAdType} onChange={setFormAdType} options={AD_TYPE_OPTIONS} />
              </div>
              <div className="input-group">
                <label className="input-label">链接</label>
                <input type="text" value={formLink} onChange={(e) => setFormLink(e.target.value)} className="input-ios" placeholder="https://" />
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="input-group">
                  <label className="input-label">购买月数 *</label>
                  <input
                    type="number"
                    min="1"
                    step="1"
                    value={formMonths}
                    onChange={(e) => {
                      const val = e.target.value
                      if (val === '' || /^[1-9]\d*$/.test(val)) {
                        setFormMonths(val)
                      }
                    }}
                    className="input-ios"
                    placeholder="输入月数"
                  />
                </div>
                <div className="input-group">
                  <label className="input-label">到期日期</label>
                  <input
                    type="text"
                    value={estimatedExpireDate || ''}
                    disabled
                    className="input-ios bg-gray-50 dark:bg-gray-800 cursor-not-allowed text-slate-500"
                    placeholder="自动计算"
                  />
                </div>
              </div>
              {estimatedAmount && (
                <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
                  <div className="flex items-center gap-2 text-amber-700 dark:text-amber-400">
                    <DollarSign className="w-4 h-4" />
                    <span className="text-sm">预计费用：</span>
                    <span className="text-lg font-bold">¥{estimatedAmount}</span>
                    <span className="text-xs text-amber-600 dark:text-amber-500">
                      （{adPrices[formAdType] || '0'}元/月 × {formMonths}月）
                    </span>
                  </div>
                </div>
              )}
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
              <button onClick={() => setIsModalOpen(false)} className="btn-ios-secondary" disabled={saving}>取消</button>
              <button onClick={handleSave} className="btn-ios-primary" disabled={saving}>
                {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                {editAd ? '保存' : '提交'}
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

      {/* 付款弹窗 */}
      <AdPaymentModal
        visible={showPayment}
        ad={paymentAd}
        onClose={() => { setShowPayment(false); setPaymentAd(null) }}
        onSuccess={loadAds}
      />
    </div>
  )
}
