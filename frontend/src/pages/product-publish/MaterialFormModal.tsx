/**
 * 商品素材新建 / 编辑弹窗。
 * 商品发布字段复用 ProductPublishForm，确保素材导入发布页时字段完全一致。
 */
import React, { useRef, useState } from 'react'
import { Loader2, Trash2, Upload, X } from 'lucide-react'
import { useUIStore } from '@/store/uiStore'
import {
  createMaterial,
  type MaterialCreateParams,
  type MaterialVideo,
  type ProductMaterial,
  type PublishSpecification,
  type PublishSkuRow,
  updateMaterial,
  uploadProductImages,
  uploadProductVideos,
} from '@/api/productPublish'
import ProductPublishForm from './ProductPublishForm'
import ProductVideoUploader from './ProductVideoUploader'
import { buildSkuKey, findDuplicateSpecificationValue, type ProductSpecification, type PublishForm, type SkuRow } from './publishTypes'

type MaterialFormState = PublishForm & { images: string[]; remark: string }

interface Props {
  initial: ProductMaterial | null
  onClose: () => void
  onSaved: () => void
}

const createInternalSpecifications = (specifications: PublishSpecification[] = []): ProductSpecification[] => specifications.map((spec, specIndex) => ({
  id: `spec-${specIndex}-${Date.now()}`,
  name: spec.name,
  supportImage: Boolean(spec.support_image),
  values: (spec.values || []).map((value, valueIndex) => ({
    id: `value-${specIndex}-${valueIndex}-${Date.now()}`,
    name: value.name,
    image: value.image || null,
  })),
}))

const createInternalSkuRows = (rows: PublishSkuRow[] = [], specifications: ProductSpecification[] = []): SkuRow[] => rows.map((row) => ({
  key: buildSkuKey(specifications, row.specs || {}),
  specs: row.specs || {},
  price: String(row.price ?? ''),
  stock: row.stock == null ? '' : String(row.stock),
}))

function hasSavedPlatformCategory(material: ProductMaterial | null): boolean {
  if (!material) return false
  return Boolean(
    material.platform_category_id
      || material.platform_channel_category_id
      || material.platform_tb_category_id
      || material.platform_category_path?.length
      || material.platform_attributes?.length,
  )
}

const initialForm = (material: ProductMaterial | null): MaterialFormState => {
  const specifications = createInternalSpecifications(material?.specifications)
  return {
  account_id: '',
  title: material?.title ?? '',
  description: material?.description ?? '',
  price: String(material?.price ?? ''),
  original_price: material?.original_price == null ? '' : String(material.original_price),
  category: material?.category ?? '',
  platform_category_id: material?.platform_category_id ?? '',
  platform_category_name: material?.platform_category_name ?? '',
  platform_channel_category_id: material?.platform_channel_category_id ?? '',
  platform_channel_category_name: material?.platform_channel_category_name ?? '',
  platform_leaf_id: material?.platform_leaf_id ?? '',
  platform_tb_category_id: material?.platform_tb_category_id ?? '',
  platform_category_path: material?.platform_category_path ?? [],
  platform_attributes: material?.platform_attributes ?? [],
  category_source: material?.category_source ?? 'manual',
  category_confidence: material?.category_confidence ?? undefined,
  videos: material?.videos ?? [],
  quantity: material?.quantity ?? 1,
  address: material?.address ?? '',
  address_expected_text: material?.address_expected_text ?? undefined,
  delivery_method: material?.delivery_method ?? 'express',
  shipping_method: material?.shipping_method ?? (material?.postage ? 'fixed' : 'free'),
  support_pickup: Boolean(material?.support_pickup),
  postage: String(material?.postage ?? 0),
  brand: material?.brand ?? '',
  condition: material?.condition ?? '全新',
  specifications,
  sku_rows: createInternalSkuRows(material?.sku_rows, specifications),
  images: material?.images ?? [],
  remark: material?.remark ?? '',
  }
}

function toMaterialPayload(form: MaterialFormState): MaterialCreateParams {
  const price = form.specifications.length > 0 ? Number(form.sku_rows[0]?.price || form.price) : Number(form.price)
  return {
    title: form.title.trim(),
    description: form.description,
    price,
    original_price: form.original_price.trim() ? Number(form.original_price) : null,
    category: form.category.trim() || null,
    platform_category_id: form.platform_category_id.trim() || null,
    platform_category_name: form.platform_category_name.trim() || null,
    platform_channel_category_id: form.platform_channel_category_id.trim() || null,
    platform_channel_category_name: form.platform_channel_category_name.trim() || null,
    platform_leaf_id: form.platform_leaf_id.trim() || null,
    platform_tb_category_id: form.platform_tb_category_id.trim() || null,
    platform_category_path: form.platform_category_path,
    platform_attributes: form.platform_attributes,
    category_source: form.category_source,
    category_confidence: form.category_confidence,
    images: form.images,
    videos: form.videos,
    specifications: form.specifications.map((spec) => ({
      name: spec.name,
      support_image: spec.supportImage,
      values: spec.values.map((value) => ({ name: value.name, image: value.image || undefined })),
    })),
    sku_rows: form.sku_rows.map((row) => ({ specs: row.specs, price: Number(row.price), stock: Number(row.stock) || 0 })),
    quantity: form.quantity,
    delivery_method: form.delivery_method,
    shipping_method: form.shipping_method,
    support_pickup: form.support_pickup,
    postage: Number(form.postage) || 0,
    address: form.address.trim() || null,
    address_expected_text: form.address_expected_text?.trim() || null,
    brand: form.brand.trim() || null,
    condition: form.condition,
    remark: form.remark.trim() || null,
  }
}

export function MaterialFormModal({ initial, onClose, onSaved }: Props) {
  const { addToast } = useUIStore()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [form, setForm] = useState<MaterialFormState>(() => initialForm(initial))
  // 编辑已有素材时，不能因弹窗初始化的推荐请求清空已保存的平台属性。
  const [categoryLocked, setCategoryLocked] = useState(() => hasSavedPlatformCategory(initial))
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)

  const setPublishForm: React.Dispatch<React.SetStateAction<PublishForm>> = (value) => {
    setForm((current) => {
      const next = typeof value === 'function' ? value(current) : value
      return { ...current, ...next }
    })
  }

  const handleUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || [])
    if (!files.length) return
    if (form.images.length + files.length > 9) {
      addToast({ type: 'warning', message: '最多上传9张图片' })
      return
    }
    setUploading(true)
    try {
      const response = await uploadProductImages(files)
      if (!response.success || !response.data) {
        addToast({ type: 'error', message: response.message || '图片上传失败' })
        return
      }
      setForm((current) => ({ ...current, images: [...current.images, ...response.data!.urls] }))
    } catch {
      addToast({ type: 'error', message: '图片上传失败，请重试' })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleSpecUpload = async (file: File) => {
    setUploading(true)
    try {
      const response = await uploadProductImages([file])
      if (!response.success || !response.data) {
        addToast({ type: 'error', message: response.message || '规格图片上传失败' })
        return null
      }
      return response.data.urls[0] || null
    } catch {
      addToast({ type: 'error', message: '规格图片上传失败，请重试' })
      return null
    } finally {
      setUploading(false)
    }
  }

  const handleVideoUpload = async (file: File): Promise<MaterialVideo | null> => {
    setUploading(true)
    try {
      const response = await uploadProductVideos([file])
      if (!response.success || !response.data) {
        addToast({ type: 'error', message: response.message || '视频上传失败' })
        return null
      }
      addToast({ type: 'success', message: '视频上传成功' })
      return response.data.videos[0] || { url: response.data.urls[0], path: response.data.paths[0], name: file.name, size: file.size }
    } catch {
      addToast({ type: 'error', message: '视频上传失败，请重试' })
      return null
    } finally {
      setUploading(false)
    }
  }

  const handleSave = async () => {
    if (!form.title.trim()) return addToast({ type: 'warning', message: '请填写商品标题' })
    if (!form.description.trim()) return addToast({ type: 'warning', message: '请填写商品描述' })
    if (form.description.length > 1500) return addToast({ type: 'warning', message: '商品描述不能超过1500字' })
    if (!form.images.length) return addToast({ type: 'warning', message: '请至少上传一张商品图片' })
    const invalidSpec = form.specifications.find((spec) => !spec.name.trim() || !spec.values.some((value) => value.name.trim()))
    if (invalidSpec) return addToast({ type: 'warning', message: '请完善商品规格类型和规格值' })
    const duplicateSpecValue = findDuplicateSpecificationValue(form.specifications)
    if (duplicateSpecValue) return addToast({ type: 'warning', message: `规格“${duplicateSpecValue.specificationName}”存在重复规格值：${duplicateSpecValue.valueName}` })
    if (form.specifications.length > 0 && !form.sku_rows.length) return addToast({ type: 'warning', message: '请等待规格组合生成后再保存' })
    const invalidSku = form.sku_rows.find((row) => !row.price || Number(row.price) <= 0 || !row.stock.trim() || Number(row.stock) < 0)
    if (invalidSku) return addToast({ type: 'warning', message: '请完善所有规格的价格和库存' })
    const payload = toMaterialPayload(form)
    if (!payload.price || payload.price <= 0) return addToast({ type: 'warning', message: '请填写有效价格' })
    setSaving(true)
    try {
      const response = initial ? await updateMaterial(initial.id, payload) : await createMaterial(payload)
      if (!response.success) {
        addToast({ type: 'error', message: response.message || (initial ? '更新失败' : '创建失败') })
        return
      }
      addToast({ type: 'success', message: initial ? '素材更新成功' : '素材创建成功' })
      onSaved()
    } catch {
      addToast({ type: 'error', message: '操作失败，请重试' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay z-40">
      <div className="modal-content max-w-4xl max-h-[94vh] flex flex-col">
        <div className="modal-header flex-shrink-0">
          <h2 className="modal-title">{initial ? '编辑素材' : '新建素材'}</h2>
          <button type="button" className="modal-close" title="关闭" onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <div className="modal-body overflow-y-auto space-y-4">
          <div className="vben-card">
            <div className="vben-card-header"><h2 className="vben-card-title">商品图片与视频</h2><span className="text-xs text-slate-400">{form.images.length}/9 图 · {form.videos.length}/3 视频</span></div>
            <div className="vben-card-body"><div className="flex flex-wrap gap-2">{form.images.map((url, index) => <div key={`${url}-${index}`} className="relative h-20 w-20 overflow-hidden rounded-lg border border-slate-200 dark:border-slate-600 group"><img src={url} alt="" className="h-full w-full object-cover" />{index === 0 && <span className="absolute bottom-0 left-0 right-0 bg-blue-500/80 py-0.5 text-center text-[10px] text-white">首图</span>}<button type="button" title="移除图片" onClick={() => setForm((current) => ({ ...current, images: current.images.filter((_, itemIndex) => itemIndex !== index) }))} className="absolute right-0.5 top-0.5 rounded bg-black/60 p-0.5 text-white opacity-0 transition-opacity group-hover:opacity-100 hover:bg-red-500"><Trash2 className="h-3 w-3" /></button></div>)}{form.images.length < 9 && <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploading} className="flex h-20 w-20 flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-300 text-slate-400 transition-colors hover:border-blue-400 hover:text-blue-500 disabled:opacity-50 dark:border-slate-600">{uploading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Upload className="h-5 w-5" />}<span className="mt-1 text-xs">{uploading ? '上传中' : '添加图片'}</span></button>}</div><input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={handleUpload} /><ProductVideoUploader videos={form.videos} onUploadVideo={handleVideoUpload} onChange={(videos) => setForm((current) => ({ ...current, videos }))} /></div>
          </div>

          <ProductPublishForm
            form={form}
            setForm={setPublishForm}
            accounts={[]}
            showAccount={false}
            onUploadSpecImage={handleSpecUpload}
            categoryLocked={categoryLocked}
            onCategoryEdit={() => setCategoryLocked(false)}
          />

          <div className="input-group"><label className="input-label">备注（内部使用，不公开）</label><input className="input-ios" maxLength={500} placeholder="选填" value={form.remark} onChange={(event) => setForm((current) => ({ ...current, remark: event.target.value }))} /></div>
        </div>
        <div className="modal-footer flex-shrink-0"><button type="button" className="btn-ios-secondary" onClick={onClose} disabled={saving}>取消</button><button type="button" className="btn-ios-primary" onClick={handleSave} disabled={saving || uploading}>{saving && <Loader2 className="w-4 h-4 animate-spin" />}{initial ? '保存修改' : '创建素材'}</button></div>
      </div>
    </div>
  )
}

export default MaterialFormModal
