/**
 * 广告申请页面（所有用户）
 * 
 * 功能：
 * 1. 新建广告申请
 * 2. 修改、删除自己的广告
 * 3. 支持图片上传和预览
 */
import { useState, useEffect, useMemo } from 'react'
import { motion } from 'framer-motion'
import {
  Megaphone,
  RefreshCw,
  Plus,
  X,
  CheckCircle,
  Clock,
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
import { Loading, PageLoading } from '@/components/common/Loading'
import { Pager } from '@/components/common/Pager'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { AdvertisementFormModal } from './AdvertisementFormModal'
import { useAdvertisementTypes } from './useAdvertisementTypes'
import { getApiErrorMessage } from '@/utils/apiError'
import { AdPaymentModal } from './AdPaymentModal'

export default function AdApply() {
  const { addToast } = useUIStore()
  const { adTypeOptions, typesLoading, typesError, reloadTypes } = useAdvertisementTypes()
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
    const months = Number(formMonths)
    if (!Number.isInteger(months) || months < 1 || months > 120) return null
    const unitPrice = Number(adPrices[formAdType])
    if (!Number.isFinite(unitPrice) || unitPrice <= 0) return null
    return (unitPrice * months).toFixed(2)
  }, [formMonths, formAdType, adPrices])

  const estimatedExpireDate = useMemo(() => {
    const months = Number(formMonths)
    if (!Number.isInteger(months) || months < 1 || months > 120) return null
    const today = new Date(Date.now() + 8 * 60 * 60 * 1000)
    const target = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() + months, 1))
    const lastDay = new Date(Date.UTC(target.getUTCFullYear(), target.getUTCMonth() + 1, 0)).getUTCDate()
    target.setUTCDate(Math.min(today.getUTCDate(), lastDay))
    return target.toISOString().slice(0, 10)
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
      } else addToast({ type: 'error', message: adsResult.message || '加载广告列表失败' })
      if (pricesResult.success && pricesResult.data) {
        setAdPrices(pricesResult.data)
      } else {
        setAdPrices({})
        addToast({ type: 'error', message: pricesResult.message || '加载广告费用失败' })
      }
    } catch (error: unknown) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载广告列表失败') })
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
    const months = Number(formMonths)
    if (!Number.isInteger(months) || months < 1 || months > 120) {
      addToast({ type: 'warning', message: '请输入1至120之间的整数月数' })
      return
    }
    if (typesLoading || typesError || !adTypeOptions.some((option) => option.value === formAdType)) {
      addToast({ type: 'warning', message: typesError || '请等待广告类型加载完成' })
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
    } catch (error: unknown) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '操作失败') })
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

      {typesError && <div role="alert" className="flex flex-wrap items-center gap-3 text-sm text-red-600 dark:text-red-400">
        {typesError}<button onClick={() => void reloadTypes()} className="btn-ios-secondary">重新加载类型</button>
      </div>}
      {/* 表格 */}
      <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">
            <Megaphone className="w-4 h-4" />
            我的广告
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
                        {ad.ad_type_label || adTypeOptions.find((option) => option.value === ad.ad_type)?.label || ad.ad_type}
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
                          {(ad.can_edit ?? ad.status !== 'approved') && (
                            <button
                              onClick={() => openEditModal(ad)}
                              className="p-1.5 text-blue-600 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded"
                              title="编辑"
                            >
                              编辑
                            </button>
                          )}
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

      {/* 新建/编辑弹窗 */}
      {isModalOpen && (
        <AdvertisementFormModal title={editAd ? '编辑广告' : '新建广告申请'} token={token}
          fields={{
            title: { value: formTitle, onChange: setFormTitle }, content: { value: formContent, onChange: setFormContent },
            link: { value: formLink, onChange: setFormLink }, image: { value: formImageUrl, onChange: setFormImageUrl },
            type: { value: formAdType, onChange: setFormAdType },
          }} typeOptions={adTypeOptions} typesLoading={typesLoading} typesError={typesError} saving={saving} onSave={handleSave}
          submitText={editAd ? '保存' : '提交'} onClose={() => setIsModalOpen(false)}>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="input-group"><label className="input-label">购买月数 *</label>
              <input type="number" min="1" max="120" step="1" value={formMonths} onChange={(e) => {
                const value = e.target.value
                if (value === '' || /^[1-9]\d*$/.test(value)) setFormMonths(value)
              }} className="input-ios" placeholder="输入月数" /></div>
            <div className="input-group"><label className="input-label">到期日期</label>
              <input value={estimatedExpireDate || ''} disabled className="input-ios" placeholder="自动计算" /></div>
          </div>
          {estimatedAmount ? <div className="p-3 bg-amber-50 dark:bg-amber-900/20 rounded-lg border border-amber-200 dark:border-amber-800">
            <div className="flex flex-wrap items-center gap-2 text-amber-700 dark:text-amber-400">
              <DollarSign className="w-4 h-4" /><span className="text-sm">预计费用：</span><span className="text-lg font-bold">¥{estimatedAmount}</span>
              <span className="text-xs">（{adPrices[formAdType]}元/月 × {formMonths}月）</span>
            </div>
          </div> : !Number(adPrices[formAdType]) && <p className="text-sm text-amber-700 dark:text-amber-400">该类型尚未配置有效价格，请联系管理员</p>}
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
