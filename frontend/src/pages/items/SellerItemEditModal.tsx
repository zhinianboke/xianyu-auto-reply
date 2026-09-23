/**
 * 鱼小铺商品编辑弹窗。
 * 界面复用单品发布表单（ProductPublishForm），提交后直接同步到闲鱼平台。
 * 平台类目默认锁定，可点「重新选择分类」解锁；类目属性（成色/品牌等）可直接修改。
 */
import React, { useEffect, useRef, useState } from 'react'
import { Loader2, Trash2, Upload, X } from 'lucide-react'
import { useUIStore } from '@/store/uiStore'
import {
  getSellerItemEditDetail,
  updateSellerItem,
  type SellerItemEditForm,
  type SellerItemEditPayload,
} from '@/api/items'
import { uploadProductImages, uploadProductVideos, type MaterialVideo, type PublishSkuRow, type PublishSpecification } from '@/api/productPublish'
import { getApiErrorMessage } from '@/utils/apiError'
import ProductPublishForm from '@/pages/product-publish/ProductPublishForm'
import ProductVideoUploader from '@/pages/product-publish/ProductVideoUploader'
import {
  buildSkuKey,
  findDuplicateSpecificationValue,
  type ProductSpecification,
  type PublishForm,
  type SkuRow,
} from '@/pages/product-publish/publishTypes'

type SellerEditFormState = PublishForm & { images: string[] }

interface Props {
  cookieId: string
  itemId: string
  itemTitle?: string
  onClose: () => void
  onSaved: () => void
}

const emptyForm = (): SellerEditFormState => ({
  account_id: '',
  title: '',
  description: '',
  price: '',
  original_price: '',
  category: '',
  platform_category_id: '',
  platform_category_name: '',
  platform_channel_category_id: '',
  platform_channel_category_name: '',
  platform_leaf_id: '',
  platform_tb_category_id: '',
  platform_category_path: [],
  platform_attributes: [],
  category_source: 'manual',
  videos: [],
  quantity: 1,
  address: '',
  address_expected_text: undefined,
  delivery_method: 'express',
  shipping_method: 'free',
  support_pickup: false,
  postage: '0',
  brand: '',
  condition: '全新',
  specifications: [],
  sku_rows: [],
  images: [],
})

const createInternalSpecifications = (specifications: PublishSpecification[] = []): ProductSpecification[] =>
  specifications.map((spec, specIndex) => ({
    id: `spec-${specIndex}-${Date.now()}`,
    name: spec.name,
    supportImage: Boolean(spec.support_image),
    values: (spec.values || []).map((value, valueIndex) => ({
      id: `value-${specIndex}-${valueIndex}-${Date.now()}`,
      name: value.name,
      image: value.image || null,
    })),
  }))

const createInternalSkuRows = (
  rows: PublishSkuRow[] = [],
  specifications: ProductSpecification[] = [],
): SkuRow[] =>
  rows.map((row) => ({
    key: buildSkuKey(specifications, row.specs || {}),
    specs: row.specs || {},
    price: String(row.price ?? ''),
    stock: row.stock == null ? '' : String(row.stock),
  }))

/** 把后端返回的平台商品详情转成发布表单同构的内部状态。 */
const toFormState = (detail: SellerItemEditForm): SellerEditFormState => {
  const specifications = createInternalSpecifications(detail.specifications)
  return {
    ...emptyForm(),
    title: detail.title || '',
    description: detail.description || '',
    price: detail.price == null ? '' : String(detail.price),
    original_price: detail.original_price == null ? '' : String(detail.original_price),
    category: detail.category || '',
    platform_category_id: detail.platform_category_id || '',
    platform_category_name: detail.platform_category_name || '',
    platform_channel_category_id: detail.platform_channel_category_id || '',
    platform_channel_category_name: detail.platform_channel_category_name || '',
    platform_leaf_id: detail.platform_leaf_id || '',
    platform_tb_category_id: detail.platform_tb_category_id || '',
    platform_category_path: detail.platform_category_path || [],
    platform_attributes: detail.platform_attributes || [],
    category_source: detail.category_source || 'manual',
    videos: detail.videos || [],
    // 平台售罄商品库存允许为 0，不能用 || 把它回填成 1。
    quantity: detail.quantity ?? 1,
    address: detail.address || '',
    address_expected_text: detail.address_expected_text || undefined,
    delivery_method: detail.delivery_method || 'express',
    shipping_method: detail.shipping_method || 'free',
    support_pickup: Boolean(detail.support_pickup),
    postage: String(detail.postage ?? 0),
    brand: detail.brand || '',
    condition: detail.condition || '全新',
    specifications,
    sku_rows: createInternalSkuRows(detail.sku_rows, specifications),
    images: detail.images || [],
  }
}

/** 组装提交到闲鱼平台的编辑参数。 */
const toEditPayload = (form: SellerEditFormState): SellerItemEditPayload => {
  const price = form.specifications.length > 0 ? Number(form.sku_rows[0]?.price || form.price) : Number(form.price)
  return {
    title: form.title.trim(),
    description: form.description,
    price,
    original_price: form.original_price.trim() ? Number(form.original_price) : null,
    images: form.images,
    // 平台已有视频带 file_id，后端凭此原样回传不重复上传；
    // 空数组表示用户删光了视频，后端会真正清空平台视频
    videos: form.videos,
    platform_category_id: form.platform_category_id.trim() || null,
    platform_category_name: form.platform_category_name.trim() || null,
    platform_channel_category_id: form.platform_channel_category_id.trim() || null,
    platform_channel_category_name: form.platform_channel_category_name.trim() || null,
    platform_leaf_id: form.platform_leaf_id.trim() || null,
    platform_tb_category_id: form.platform_tb_category_id.trim() || null,
    platform_attributes: form.platform_attributes,
    specifications: form.specifications.map((spec) => ({
      name: spec.name,
      support_image: spec.supportImage,
      values: spec.values.map((value) => ({ name: value.name, image: value.image || undefined })),
    })),
    sku_rows: form.sku_rows.map((row) => ({
      specs: row.specs,
      price: Number(row.price),
      stock: Number(row.stock) || 0,
    })),
    quantity: form.specifications.length > 0 ? 1 : form.quantity,
    address: form.address.trim() || null,
    address_expected_text: form.address_expected_text?.trim() || null,
    delivery_method: form.delivery_method,
    shipping_method: form.shipping_method,
    support_pickup: form.support_pickup,
    postage: Number(form.postage) || 0,
    brand: form.brand.trim() || null,
    condition: form.condition || null,
  }
}

export function SellerItemEditModal({ cookieId, itemId, itemTitle, onClose, onSaved }: Props) {
  const { addToast } = useUIStore()
  const fileInputRef = useRef<HTMLInputElement>(null)
  // 平台原始发货设置：未改动时后端会原样复用平台快照（运费模板/一口价也能保住），
  // 一旦改动则只支持抓包已确认的包邮/无需邮寄，需要在提交前拦下来给出中文提示
  const initialShippingRef = useRef<{ method: string; postage: number } | null>(null)
  const [form, setForm] = useState<SellerEditFormState>(() => emptyForm())
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  // 平台已有类目默认锁定，避免弹窗内的推荐请求覆盖平台已保存的类目与属性
  const [categoryLocked, setCategoryLocked] = useState(true)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setLoadError('')
      // 账号不存在等场景后端返回 HTTP 错误，统一取后端 message 展示，避免控制台报错
      const response = await getSellerItemEditDetail(cookieId, itemId).catch((error: unknown) => ({
        success: false,
        message: getApiErrorMessage(error, '获取商品详情失败'),
        data: undefined,
      }))
      if (cancelled) return
      if (!response.success || !response.data?.form) {
        setLoadError(response.message || '获取商品详情失败')
        setLoading(false)
        return
      }
      setForm(toFormState(response.data.form))
      initialShippingRef.current = {
        method: response.data.form.shipping_method || 'free',
        postage: Number(response.data.form.postage ?? 0) || 0,
      }
      setLoading(false)
    }
    load()
    return () => {
      cancelled = true
    }
  }, [cookieId, itemId])

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
    const response = await uploadProductImages(files).catch((error: unknown) => ({
      success: false,
      message: getApiErrorMessage(error, '图片上传失败'),
      data: undefined,
    }))
    setUploading(false)
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (!response.success || !response.data) {
      addToast({ type: 'error', message: response.message || '图片上传失败' })
      return
    }
    setForm((current) => ({ ...current, images: [...current.images, ...response.data!.urls] }))
  }

  const handleSpecUpload = async (file: File) => {
    setUploading(true)
    const response = await uploadProductImages([file]).catch((error: unknown) => ({
      success: false,
      message: getApiErrorMessage(error, '规格图片上传失败'),
      data: undefined,
    }))
    setUploading(false)
    if (!response.success || !response.data) {
      addToast({ type: 'error', message: response.message || '规格图片上传失败' })
      return null
    }
    return response.data.urls[0] || null
  }

  const handleVideoUpload = async (file: File): Promise<MaterialVideo | null> => {
    setUploading(true)
    const response = await uploadProductVideos([file]).catch((error: unknown) => ({
      success: false,
      message: getApiErrorMessage(error, '视频上传失败'),
      data: undefined,
    }))
    setUploading(false)
    if (!response.success || !response.data) {
      addToast({ type: 'error', message: response.message || '视频上传失败' })
      return null
    }
    addToast({ type: 'success', message: '视频上传成功' })
    return (
      response.data.videos[0]
      || { url: response.data.urls[0], path: response.data.paths[0], name: file.name, size: file.size }
    )
  }

  const handleSave = async () => {
    if (!form.title.trim()) return addToast({ type: 'warning', message: '请填写商品标题' })
    if (!form.description.trim()) return addToast({ type: 'warning', message: '请填写商品描述' })
    if (form.description.length > 5000) return addToast({ type: 'warning', message: '商品描述不能超过5000字' })
    if (!form.images.length) return addToast({ type: 'warning', message: '请至少上传一张商品图片' })
    if (!form.address.trim()) return addToast({ type: 'warning', message: '请选择宝贝所在地' })
    const invalidSpec = form.specifications.find((spec) => !spec.name.trim() || !spec.values.some((value) => value.name.trim()))
    if (invalidSpec) return addToast({ type: 'warning', message: '请完善商品规格类型和规格值' })
    const duplicateSpecValue = findDuplicateSpecificationValue(form.specifications)
    if (duplicateSpecValue) {
      return addToast({
        type: 'warning',
        message: `规格“${duplicateSpecValue.specificationName}”存在重复规格值：${duplicateSpecValue.valueName}`,
      })
    }
    if (form.specifications.length > 0 && !form.sku_rows.length) {
      return addToast({ type: 'warning', message: '请等待规格组合生成后再保存' })
    }
    const invalidSku = form.sku_rows.find((row) => !row.price || Number(row.price) <= 0 || !row.stock.trim() || Number(row.stock) < 0)
    if (invalidSku) return addToast({ type: 'warning', message: '请完善所有规格的价格和库存' })
    // 平台库存只接受整数，带小数会被后端校验拒绝，提前拦下来给中文提示
    const fractionalStock = form.sku_rows.find((row) => !Number.isInteger(Number(row.stock)))
    if (fractionalStock) return addToast({ type: 'warning', message: '规格库存必须是整数' })
    if (!Number.isInteger(Number(form.quantity))) return addToast({ type: 'warning', message: '商品库存必须是整数' })
    const payload = toEditPayload(form)
    if (!payload.price || payload.price <= 0) return addToast({ type: 'warning', message: '请填写有效价格' })
    const initialShipping = initialShippingRef.current
    const shippingChanged = !initialShipping
      || initialShipping.method !== form.shipping_method
      || initialShipping.postage !== (Number(form.postage) || 0)
    if (shippingChanged && form.shipping_method !== 'free' && form.shipping_method !== 'none') {
      return addToast({
        type: 'warning',
        message: '发货方式目前只支持改为「包邮」或「无需邮寄」；保持平台原有设置不变可正常保存，其它方式请在闲鱼后台修改',
      })
    }

    setSaving(true)
    const response = await updateSellerItem(cookieId, itemId, payload).catch((error: unknown) => ({
      success: false,
      message: getApiErrorMessage(error, '商品编辑失败'),
    }))
    setSaving(false)
    if (!response.success) {
      addToast({ type: 'error', message: response.message || '商品编辑失败' })
      return
    }
    addToast({ type: 'success', message: response.message || '商品编辑成功' })
    onSaved()
  }

  return (
    <div className="modal-overlay z-40">
      <div className="modal-content max-w-4xl max-h-[94vh] flex flex-col">
        <div className="modal-header flex-shrink-0">
          <h2 className="modal-title">编辑闲鱼商品{itemTitle ? `：${itemTitle}` : ''}</h2>
          <button type="button" className="modal-close" title="关闭" onClick={onClose}>
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="modal-body overflow-y-auto space-y-4 relative">
          {loading && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-white/70 text-sm text-slate-500 dark:bg-slate-900/70 dark:text-slate-300">
              <Loader2 className="h-6 w-6 animate-spin" />
              <span>正在读取闲鱼商品详情…</span>
            </div>
          )}
          {saving && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-2 bg-white/70 text-sm text-slate-500 dark:bg-slate-900/70 dark:text-slate-300">
              <Loader2 className="h-6 w-6 animate-spin" />
              <span>正在提交到闲鱼并重新同步商品…</span>
            </div>
          )}
          {loadError ? (
            <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300">
              {loadError}
            </div>
          ) : (
            <>
              <div className="vben-card">
                <div className="vben-card-header">
                  <h2 className="vben-card-title">商品图片与视频</h2>
                  <span className="text-xs text-slate-400">{form.images.length}/9 图 · {form.videos.length}/3 视频</span>
                </div>
                <div className="vben-card-body">
                  <div className="flex flex-wrap gap-2">
                    {form.images.map((url, index) => (
                      <div key={`${url}-${index}`} className="relative h-20 w-20 overflow-hidden rounded-lg border border-slate-200 dark:border-slate-600 group">
                        <img src={url} alt="" className="h-full w-full object-cover" />
                        {index === 0 && <span className="absolute bottom-0 left-0 right-0 bg-blue-500/80 py-0.5 text-center text-[10px] text-white">首图</span>}
                        <button
                          type="button"
                          title="移除图片"
                          onClick={() => setForm((current) => ({ ...current, images: current.images.filter((_, itemIndex) => itemIndex !== index) }))}
                          className="absolute right-0.5 top-0.5 rounded bg-black/60 p-0.5 text-white opacity-0 transition-opacity group-hover:opacity-100 hover:bg-red-500"
                        >
                          <Trash2 className="h-3 w-3" />
                        </button>
                      </div>
                    ))}
                    {form.images.length < 9 && (
                      <button
                        type="button"
                        onClick={() => fileInputRef.current?.click()}
                        disabled={uploading}
                        className="flex h-20 w-20 flex-col items-center justify-center rounded-lg border-2 border-dashed border-slate-300 text-slate-400 transition-colors hover:border-blue-400 hover:text-blue-500 disabled:opacity-50 dark:border-slate-600"
                      >
                        {uploading ? <Loader2 className="h-5 w-5 animate-spin" /> : <Upload className="h-5 w-5" />}
                        <span className="mt-1 text-xs">{uploading ? '上传中' : '添加图片'}</span>
                      </button>
                    )}
                  </div>
                  <input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={handleUpload} />
                  <ProductVideoUploader
                    videos={form.videos}
                    onUploadVideo={handleVideoUpload}
                    onChange={(videos) => setForm((current) => ({ ...current, videos }))}
                  />
                  <p className="mt-2 text-xs text-slate-400">
                    平台已有视频已回填，保存时原样保留；删除后保存会同步清空平台视频。
                  </p>
                </div>
              </div>

              {form.specifications.length > 0 && (
                <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 dark:border-blue-700 dark:bg-blue-900/20 dark:text-blue-300">
                  平台原有规格图已回填到下方规格中，保存后会原样提交。闲鱼只允许一组规格带图片，勾选另一组会清空当前组的规格图。
                </div>
              )}

              <ProductPublishForm
                form={form}
                setForm={setPublishForm}
                accounts={[]}
                showAccount={false}
                onUploadSpecImage={handleSpecUpload}
                categoryLocked={categoryLocked}
                onCategoryEdit={() => setCategoryLocked(false)}
                unlockCategoryOnTextChange={false}
              />
            </>
          )}
        </div>
        <div className="modal-footer flex-shrink-0">
          <button type="button" className="btn-ios-secondary" onClick={onClose} disabled={saving}>取消</button>
          <button type="button" className="btn-ios-primary" onClick={handleSave} disabled={loading || saving || uploading || Boolean(loadError)}>
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}保存并同步到闲鱼
          </button>
        </div>
      </div>
    </div>
  )
}

export default SellerItemEditModal
