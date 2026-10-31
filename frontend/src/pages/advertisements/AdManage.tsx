/**
 * 广告管理页面（管理员）
 * 
 * 功能：
 * 1. 查看所有广告
 * 2. 复核/取消复核广告
 * 3. 修改、删除广告
 * 4. 支持图片预览
 */
import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import {
  Megaphone,
  RefreshCw,
  X,
  CheckCircle,
  Clock,
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
import { Loading, PageLoading } from '@/components/common/Loading'
import { Pager } from '@/components/common/Pager'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { AdvertisementFormModal } from './AdvertisementFormModal'
import { useAdvertisementTypes } from './useAdvertisementTypes'
import { getApiErrorMessage } from '@/utils/apiError'

const STATUS_OPTIONS = [
  { value: 'unpaid', label: '待付款' },
  { value: 'pending', label: '待复核' },
  { value: 'approved', label: '已复核' },
]

export default function AdManage() {
  const { addToast } = useUIStore()
  const { adTypeOptions, typesLoading, typesError, reloadTypes } = useAdvertisementTypes()
  const { token, isAuthenticated, _hasHydrated } = useAuthStore()

  const [loading, setLoading] = useState(true)
  const [ads, setAds] = useState<Advertisement[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [filterStatus, setFilterStatus] = useState('')
  const [filterType, setFilterType] = useState('')
  const [activeFilters, setActiveFilters] = useState({ status: '', type: '' })

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

  // 图片预览
  const [previewImage, setPreviewImage] = useState<string | null>(null)

  // 删除确认
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; ad: Advertisement | null }>({
    open: false,
    ad: null,
  })
  const [deleting, setDeleting] = useState(false)

  // 翻页、刷新及编辑后按已查询条件加载，筛选草稿仅点击查询时生效。
  const loadAds = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getAllAds({
        page,
        page_size: pageSize,
        status: activeFilters.status || undefined,
        ad_type: activeFilters.type || undefined,
      })
      if (result.success && result.data) {
        setAds(result.data.items)
        setTotal(result.data.total)
      } else addToast({ type: 'error', message: result.message || '加载广告列表失败' })
    } catch (error: unknown) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载广告列表失败') })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAds()
  }, [_hasHydrated, isAuthenticated, token, page, pageSize, activeFilters])

  // 点击「查询」：使用当前筛选草稿回到第 1 页并加载
  const handleSearch = () => {
    setPage(1)
    setActiveFilters({ status: filterStatus, type: filterType })
  }

  // 点击「重置」：清空筛选并重新加载
  const handleReset = () => {
    setFilterStatus('')
    setFilterType('')
    setPage(1)
    setActiveFilters({ status: '', type: '' })
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
    if (typesLoading || typesError || !adTypeOptions.some((option) => option.value === formAdType)) {
      addToast({ type: 'warning', message: typesError || '请等待广告类型加载完成' })
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
    } catch (error: unknown) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '保存失败') })
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
    } catch (error: unknown) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '操作失败') })
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
    } catch (error: unknown) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '操作失败') })
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
    } catch (error: unknown) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '删除失败') })
    } finally {
      setDeleting(false)
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
            options={[{ value: '', label: '全部类型' }, ...adTypeOptions]}
            disabled={typesLoading || Boolean(typesError)}
            className="w-48"
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

      {typesError && <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-red-600 dark:text-red-400">
        {typesError}<button onClick={() => void reloadTypes()} className="btn-ios-secondary">重新加载类型</button>
      </div>}
      {/* 表格 */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">
            <Megaphone className="w-4 h-4" />
            广告列表
          </h2>
          <span className="badge-primary">{total} 条</span>
        </div>
        <div className="relative">
        {loading && <div className="absolute inset-0 z-20 flex items-center justify-center bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm"><Loading text="加载中..." /></div>}
        <div className="table-scroll">
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
                        {ad.ad_type_label || adTypeOptions.find((option) => option.value === ad.ad_type)?.label || ad.ad_type}
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
                              复核
                            </button>
                          ) : (
                            <button
                              onClick={() => handleReject(ad)}
                              className="p-1.5 text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-900/20 rounded"
                              title="取消复核"
                            >
                              取消复核
                            </button>
                          )}
                          <button
                            onClick={() => openEditModal(ad)}
                            className="p-1.5 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded"
                            title="编辑"
                          >
                            编辑
                          </button>
                          <button
                            onClick={() => setDeleteConfirm({ open: true, ad })}
                            className="p-1.5 text-red-600 hover:bg-red-50 dark:hover:bg-red-900/20 rounded"
                            title="删除"
                          >
                            删除
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
        <Pager page={page} pageSize={pageSize} total={total} loading={loading}
          onPageChange={setPage} onPageSizeChange={(size) => { setPageSize(size); setPage(1) }} />
      </motion.div>

      {/* 编辑弹窗 */}
      {editAd && (
        <AdvertisementFormModal title="编辑广告" token={token}
          fields={{
            title: { value: formTitle, onChange: setFormTitle }, content: { value: formContent, onChange: setFormContent },
            link: { value: formLink, onChange: setFormLink }, image: { value: formImageUrl, onChange: setFormImageUrl },
            type: { value: formAdType, onChange: setFormAdType },
          }} typeOptions={adTypeOptions} typesLoading={typesLoading} typesError={typesError} saving={saving} onSave={handleSave}
          onClose={() => setEditAd(null)}>
          <div className="input-group"><label className="input-label">审核状态</label>
            <Select value={formStatus} onChange={setFormStatus} options={STATUS_OPTIONS} /></div>
          <div className="input-group"><label className="input-label">到期日期</label>
            <input type="date" value={formExpireDate} onChange={(e) => setFormExpireDate(e.target.value)} className="input-ios" /></div>
        </AdvertisementFormModal>
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
