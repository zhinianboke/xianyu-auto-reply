/**
 * 商品素材表单弹窗
 * 新建 / 编辑商品素材，支持图片上传（最多9张）
 */
import React, { useState, useRef } from 'react'
import { X, Loader2, Upload, Trash2 } from 'lucide-react'
import { useUIStore } from '@/store/uiStore'
import {
  createMaterial, updateMaterial, uploadProductImages,
  type ProductDeliveryMethod, type ProductMaterial, type MaterialCreateParams,
} from '@/api/productPublish'

const CONDITIONS = ['全新', '99新', '95新', '9成新', '8成新', '7成新以下']
const CATEGORIES = ['数码家电', '服饰鞋包', '家居日用', '图书音像', '美妆个护', '母婴用品', '运动户外', '食品生鲜', '虚拟商品', '其他']

function normalizeMoney(value: number | null | undefined): number | undefined {
  if (value === null || value === undefined || Number.isNaN(value)) return undefined
  return Math.round(value * 100) / 100
}

interface Props {
  initial: ProductMaterial | null
  onClose: () => void
  onSaved: () => void
}

export function MaterialFormModal({ initial, onClose, onSaved }: Props) {
  const { addToast } = useUIStore()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [previewImage, setPreviewImage] = useState<string | null>(null)
  const rawInitialDeliveryMethod = initial?.delivery_method as string | undefined
  const initialDeliveryMethod: ProductDeliveryMethod =
    rawInitialDeliveryMethod === 'distance_billing' || rawInitialDeliveryMethod === 'fixed_fee' || rawInitialDeliveryMethod === 'no_shipping'
      ? rawInitialDeliveryMethod
      : rawInitialDeliveryMethod === 'virtual'
        ? 'no_shipping'
        : 'free_shipping'
  const [form, setForm] = useState<MaterialCreateParams>({
    title: initial?.title ?? '',
    description: initial?.description ?? '',
    price: initial?.price ?? 0,
    original_price: initial?.original_price ?? undefined,
    category: initial?.category ?? '',
    images: initial?.images ?? [],
    delivery_method: initialDeliveryMethod,
    support_pickup: initial?.support_pickup ?? false,
    postage: initial?.postage ?? 0,
    address: initial?.address ?? '',
    brand: initial?.brand ?? '',
    condition: initial?.condition ?? '全新',
    remark: initial?.remark ?? '',
  })

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (!files.length) return
    const curr = (form.images || []).length
    if (curr + files.length > 9) { addToast({ type: 'warning', message: '最多9张图片' }); return }
    setUploading(true)
    try {
      const res = await uploadProductImages(files)
      if (res.success && res.data) {
        setForm(f => ({ ...f, images: [...(f.images || []), ...res.data!.urls] }))
      } else {
        addToast({ type: 'error', message: res.message || '上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '图片上传失败' })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const removeImage = (idx: number) => {
    setForm(f => ({ ...f, images: (f.images || []).filter((_, i) => i !== idx) }))
  }

  const updateDeliveryMethod = (deliveryMethod: ProductDeliveryMethod) => {
    setForm(f => ({
      ...f,
      delivery_method: deliveryMethod,
      postage: deliveryMethod === 'fixed_fee' ? f.postage : 0,
    }))
  }

  const handleSave = async () => {
    if (!form.title.trim()) { addToast({ type: 'warning', message: '请填写商品标题' }); return }
    if (!form.description.trim()) { addToast({ type: 'warning', message: '请填写商品描述' }); return }
    const normalizedPrice = normalizeMoney(form.price)
    const normalizedOriginalPrice = normalizeMoney(form.original_price)
    if (!normalizedPrice || normalizedPrice < 0.01) { addToast({ type: 'warning', message: '售价最小为0.01' }); return }
    if (normalizedOriginalPrice !== undefined && normalizedOriginalPrice < 0.01) { addToast({ type: 'warning', message: '原价最小为0.01' }); return }
    if (!form.images || form.images.length === 0) { addToast({ type: 'warning', message: '请至少上传一张商品图片' }); return }
    setSaving(true)
    try {
      const payload = {
        ...form,
        price: normalizedPrice,
        original_price: normalizedOriginalPrice,
        postage: form.delivery_method === 'fixed_fee' ? (normalizeMoney(form.postage) ?? 0) : 0,
      }
      if (initial) {
        const res = await updateMaterial(initial.id, payload)
        if (!res.success) { addToast({ type: 'error', message: res.message || '更新失败' }); return }
        addToast({ type: 'success', message: '素材更新成功' })
      } else {
        const res = await createMaterial(payload)
        if (!res.success) { addToast({ type: 'error', message: res.message || '创建失败' }); return }
        addToast({ type: 'success', message: '素材创建成功' })
      }
      onSaved()
    } catch {
      addToast({ type: 'error', message: '操作失败，请重试' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content max-w-2xl">
        <div className="modal-header">
          <h2 className="modal-title">{initial ? '编辑素材' : '新建素材'}</h2>
          <button className="modal-close" onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <div className="modal-body">
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="sm:col-span-2 input-group">
                <label className="input-label">商品标题 <span className="text-red-500">*</span></label>
                <input className="input-ios" placeholder="请输入商品标题"
                  value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
              </div>
              <div className="input-group">
                <label className="input-label">售价（元）<span className="text-red-500">*</span></label>
                <input type="number" className="input-ios" placeholder="0.01" min="0.01" step="0.01"
                  value={form.price || ''} onChange={e => setForm(f => ({ ...f, price: parseFloat(e.target.value) || 0 }))} />
              </div>
              <div className="input-group">
                <label className="input-label">原价（划线价，选填）</label>
                <input type="number" className="input-ios" placeholder="0.01" min="0.01" step="0.01"
                  value={form.original_price || ''} onChange={e => setForm(f => ({ ...f, original_price: parseFloat(e.target.value) || undefined }))} />
              </div>
              <div className="input-group">
                <label className="input-label">商品分类</label>
                <select className="input-ios" value={form.category}
                  onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>
                  <option value="">请选择分类</option>
                  {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">成色</label>
                <select className="input-ios" value={form.condition}
                  onChange={e => setForm(f => ({ ...f, condition: e.target.value }))}>
                  {CONDITIONS.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">品牌（选填）</label>
                <input className="input-ios" placeholder="请输入品牌"
                  value={form.brand} onChange={e => setForm(f => ({ ...f, brand: e.target.value }))} />
              </div>
              <div className="input-group sm:col-span-2">
                <label className="input-label">发货方式</label>
                <div className="flex items-center gap-3 flex-wrap">
                  <select className="input-ios w-full sm:w-[320px]" value={form.delivery_method}
                    onChange={e => updateDeliveryMethod(e.target.value as ProductDeliveryMethod)}>
                    <option value="free_shipping">包邮</option>
                    <option value="distance_billing">按距离计费</option>
                    <option value="fixed_fee">一口价</option>
                    <option value="no_shipping">无需邮寄</option>
                  </select>
                  <label className="switch-ios flex-shrink-0">
                    <input
                      type="checkbox"
                      checked={Boolean(form.support_pickup)}
                      onChange={e => setForm(f => ({ ...f, support_pickup: e.target.checked }))}
                    />
                    <span className="switch-slider"></span>
                  </label>
                  <span className="text-sm text-slate-600 dark:text-slate-300 flex-shrink-0">支持自提</span>
                </div>
              </div>
              {form.delivery_method === 'fixed_fee' && (
                <div className="input-group">
                  <label className="input-label">运费（元）</label>
                  <input type="number" className="input-ios w-full sm:w-[320px]" placeholder="0" min="0" step="0.01"
                    value={form.postage || ''} onChange={e => setForm(f => ({ ...f, postage: parseFloat(e.target.value) || 0 }))} />
                </div>
              )}
              <div className="sm:col-span-2 input-group">
                <label className="input-label">宝贝所在地</label>
                <input className="input-ios" placeholder="如：北京市朝阳区；仅做素材记录，发布时统一走随机地址"
                  value={form.address} onChange={e => setForm(f => ({ ...f, address: e.target.value }))} />
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  这里填写的地址仅做素材记录，实际发布时会自动从随机地址库分配宝贝所在地。
                </p>
              </div>
              <div className="sm:col-span-2 input-group">
                <label className="input-label">商品描述 <span className="text-red-500">*</span></label>
                <textarea className="input-ios" rows={4} placeholder="请详细描述商品状态、配件、使用情况等"
                  value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
              </div>
              <div className="sm:col-span-2 input-group">
                <label className="input-label">备注（内部使用，不公开）</label>
                <input className="input-ios" placeholder="选填"
                  value={form.remark} onChange={e => setForm(f => ({ ...f, remark: e.target.value }))} />
              </div>
            </div>
            <div className="input-group">
              <label className="input-label">商品图片（最多9张） <span className="text-red-500">*</span></label>
              <div className="flex flex-wrap gap-2 mt-1.5">
                {(form.images || []).map((url, i) => (
                  <div key={i} className="relative w-20 h-20 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-600 group">
                    <button type="button" className="w-full h-full cursor-zoom-in" onClick={() => setPreviewImage(url)}>
                      <img src={url} alt="" className="w-full h-full object-cover" />
                    </button>
                    {i === 0 && (
                      <span className="absolute bottom-0 left-0 right-0 bg-blue-500/80 text-white text-[10px] text-center py-0.5">封面</span>
                    )}
                    <button type="button" onClick={() => removeImage(i)}
                      className="absolute top-0.5 right-0.5 bg-black/60 hover:bg-red-500 text-white rounded p-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                ))}
                {(form.images || []).length < 9 && (
                  <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploading}
                    className="w-20 h-20 border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-lg flex flex-col items-center justify-center text-slate-400 hover:border-blue-400 hover:text-blue-500 transition-colors disabled:opacity-50">
                    {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}
                    <span className="text-xs mt-1">{uploading ? '上传中' : '添加图片'}</span>
                  </button>
                )}
              </div>
              <input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={handleUpload} />
            </div>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-ios-secondary" onClick={onClose} disabled={saving}>取消</button>
          <button className="btn-ios-primary" onClick={handleSave} disabled={saving || uploading}>
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            {initial ? '保存修改' : '创建素材'}
          </button>
        </div>
      </div>

      {previewImage && (
        <div className="modal-overlay" style={{ zIndex: 70 }}>
          <div className="modal-content max-w-4xl">
            <div className="modal-header">
              <h2 className="modal-title">图片预览</h2>
              <button className="modal-close" onClick={() => setPreviewImage(null)}>
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="modal-body flex items-center justify-center">
              <img src={previewImage} alt="预览图片" className="max-w-full max-h-[70vh] object-contain rounded-lg" />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default MaterialFormModal
