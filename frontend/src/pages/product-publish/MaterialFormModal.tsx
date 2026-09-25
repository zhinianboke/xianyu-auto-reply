/**
 * 商品素材新建 / 编辑弹窗。
 * 商品发布字段复用 ProductPublishForm，确保素材导入发布页时字段完全一致。
 */
import React, { useEffect, useRef, useState } from 'react'
import { ChevronDown, Download, Loader2, Trash2, Upload, X } from 'lucide-react'
import { useUIStore } from '@/store/uiStore'
import {
  createMaterial,
  type CollectMaterialDraft,
  type MaterialCreateParams,
  type MaterialItemConfig,
  type MaterialVideo,
  type ProductMaterial,
  type PublishSpecification,
  type PublishSkuRow,
  updateMaterial,
  uploadProductImages,
  uploadProductVideos,
} from '@/api/productPublish'
import { getAllCards, type CardData } from '@/api/cards'
import { ItemQueryConfigModal } from '@/pages/items/ItemQueryConfigModal'
import ProductPublishForm from './ProductPublishForm'
import ProductVideoUploader from './ProductVideoUploader'
import CollectFromItemModal from './CollectFromItemModal'
import { buildSkuKey, findDuplicateSpecificationValue, type ProductSpecification, type PublishForm, type SkuRow } from './publishTypes'

type MaterialFormState = PublishForm & { images: string[]; remark: string; item_config: MaterialItemConfig }

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

/** 把素材透传的 item_config 归一化为可编辑态（补齐缺省字段、卡券ID去重为数组） */
const normalizeItemConfig = (cfg: ProductMaterial['item_config']): MaterialItemConfig => {
  const source = cfg && typeof cfg === 'object' ? cfg : null
  const rawCardIds = source?.card_ids
  return {
    multi_quantity_delivery: Boolean(source?.multi_quantity_delivery),
    card_ids: Array.isArray(rawCardIds) ? rawCardIds.filter((id): id is number => typeof id === 'number') : [],
    default_reply: source?.default_reply ?? '',
    ai_prompt: source?.ai_prompt ?? '',
    query_buttons: Array.isArray(source?.query_buttons) ? source!.query_buttons : [],
    display_links: Array.isArray(source?.display_links) ? source!.display_links : [],
    page_hint: typeof source?.page_hint === 'string' ? source.page_hint : '',
  }
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
  item_config: normalizeItemConfig(material?.item_config),
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
    item_config: form.item_config,
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
  const [cards, setCards] = useState<CardData[]>([])
  const [cardsLoading, setCardsLoading] = useState(false)
  const [configOpen, setConfigOpen] = useState(true)
  const [showQueryModal, setShowQueryModal] = useState(false)
  const [showCollect, setShowCollect] = useState(false)

  // 关联卡券下拉数据：弹窗打开即拉取一次，供 item_config.card_ids 勾选
  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setCardsLoading(true)
      try {
        const list = await getAllCards()
        if (!cancelled) setCards(list)
      } catch {
        if (!cancelled) addToast({ type: 'error', message: '加载卡券列表失败' })
      } finally {
        if (!cancelled) setCardsLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [addToast])

  const setPublishForm: React.Dispatch<React.SetStateAction<PublishForm>> = (value) => {
    setForm((current) => {
      const next = typeof value === 'function' ? value(current) : value
      return { ...current, ...next }
    })
  }

  const updateItemConfig = (patch: Partial<MaterialItemConfig>) =>
    setForm((current) => ({ ...current, item_config: { ...current.item_config, ...patch } }))

  const toggleCardId = (cardId: number) =>
    setForm((current) => {
      const exists = current.item_config.card_ids.includes(cardId)
      return {
        ...current,
        item_config: {
          ...current.item_config,
          card_ids: exists
            ? current.item_config.card_ids.filter((id) => id !== cardId)
            : [...current.item_config.card_ids, cardId],
        },
      }
    })

  // 从商品列表采集：把草稿的标题/价格/图片/规格 + item_config 整体回填当前素材
  const handleCollect = (draft: CollectMaterialDraft) => {
    setForm((current) => {
      const specifications = createInternalSpecifications(draft.specifications)
      return {
        ...current,
        title: draft.title ?? current.title,
        description: draft.description ?? current.description,
        price: draft.price != null ? String(draft.price) : current.price,
        images: draft.images?.length ? draft.images : current.images,
        specifications,
        sku_rows: createInternalSkuRows([], specifications),
        item_config: draft.item_config ? normalizeItemConfig(draft.item_config) : current.item_config,
      }
    })
    addToast({ type: 'success', message: '已采集并回填表单' })
    setShowCollect(false)
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
          <button type="button" className="btn-ios-secondary w-full" onClick={() => setShowCollect(true)}>
            <Download className="w-4 h-4" />从商品列表采集
          </button>
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
            unlockCategoryOnTextChange={false}
          />

          <div className="input-group"><label className="input-label">备注（内部使用，不公开）</label><input className="input-ios" maxLength={500} placeholder="选填" value={form.remark} onChange={(event) => setForm((current) => ({ ...current, remark: event.target.value }))} /></div>

          {/* 商品列表配置：随素材保存为 item_config，发布时一步到位回写新商品 */}
          <div className="vben-card">
            <button type="button" onClick={() => setConfigOpen((open) => !open)} className="vben-card-header w-full cursor-pointer text-left">
              <h2 className="vben-card-title">商品列表配置</h2>
              <ChevronDown className={`w-4 h-4 flex-shrink-0 text-slate-400 transition-transform ${configOpen ? 'rotate-180' : ''}`} />
            </button>
            {configOpen && (
              <div className="vben-card-body space-y-4">
                <div className="flex items-center justify-between">
                  <label className="input-label mb-0">多数量发货</label>
                  <button
                    type="button"
                    role="switch"
                    aria-checked={form.item_config.multi_quantity_delivery}
                    title={form.item_config.multi_quantity_delivery ? '点击关闭' : '点击开启'}
                    onClick={() => updateItemConfig({ multi_quantity_delivery: !form.item_config.multi_quantity_delivery })}
                    className={`relative w-9 h-5 rounded-full transition-colors ${form.item_config.multi_quantity_delivery ? 'bg-blue-500' : 'bg-gray-300 dark:bg-gray-600'}`}
                  >
                    <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${form.item_config.multi_quantity_delivery ? 'left-[18px]' : 'left-0.5'}`} />
                  </button>
                </div>

                <div className="input-group">
                  <label className="input-label">关联卡券{form.item_config.card_ids.length > 0 && <span className="ml-1 text-xs text-slate-400">（已选 {form.item_config.card_ids.length}）</span>}</label>
                  {cardsLoading ? (
                    <div className="flex items-center gap-2 text-sm text-slate-400"><Loader2 className="w-4 h-4 animate-spin" /> 加载卡券中...</div>
                  ) : cards.length === 0 ? (
                    <p className="text-sm text-slate-400">暂无可用卡券</p>
                  ) : (
                    <div className="max-h-40 overflow-y-auto rounded-lg border border-slate-200 dark:border-slate-600 p-2 space-y-0.5">
                      {cards.map((card) => {
                        const cardId = card.id
                        if (cardId == null) return null
                        const checked = form.item_config.card_ids.includes(cardId)
                        return (
                          <label key={cardId} className="flex items-center gap-2 p-1.5 rounded cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-700">
                            <input type="checkbox" checked={checked} onChange={() => toggleCardId(cardId)} className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
                            <span className="text-sm text-slate-700 dark:text-slate-200 truncate">{card.name}</span>
                            <span className="badge-gray ml-auto">{card.type}</span>
                          </label>
                        )
                      })}
                    </div>
                  )}
                </div>

                <div className="input-group">
                  <label className="input-label">默认回复</label>
                  <textarea className="input-ios h-20 resize-none" maxLength={1000} placeholder="买家咨询时未命中关键词/卡券时的兜底回复" value={form.item_config.default_reply} onChange={(event) => updateItemConfig({ default_reply: event.target.value })} />
                </div>

                <div className="input-group">
                  <label className="input-label">AI 提示</label>
                  <textarea className="input-ios h-20 resize-none" maxLength={2000} placeholder="AI 客服角色与回复风格提示词" value={form.item_config.ai_prompt} onChange={(event) => updateItemConfig({ ai_prompt: event.target.value })} />
                </div>

                <div className="input-group">
                  <label className="input-label">查询按钮</label>
                  <p className="text-xs text-slate-400 mb-2">配置买家在提货页可点击的查询按钮（{form.item_config.query_buttons.length} 个）</p>
                  <button type="button" className="btn-ios-secondary" onClick={() => setShowQueryModal(true)}>配置查询按钮</button>
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="modal-footer flex-shrink-0"><button type="button" className="btn-ios-secondary" onClick={onClose} disabled={saving}>取消</button><button type="button" className="btn-ios-primary" onClick={handleSave} disabled={saving || uploading}>{saving && <Loader2 className="w-4 h-4 animate-spin" />}{initial ? '保存修改' : '创建素材'}</button></div>
      </div>

      {showCollect && (
        <CollectFromItemModal onClose={() => setShowCollect(false)} onCollect={handleCollect} />
      )}

      {showQueryModal && (
        <ItemQueryConfigModal
          draftMode
          itemName={form.title.trim() || '商品素材'}
          initialButtons={form.item_config.query_buttons}
          onClose={() => setShowQueryModal(false)}
          onSavedButtons={(buttons) => {
            updateItemConfig({ query_buttons: buttons })
            setShowQueryModal(false)
            addToast({ type: 'success', message: '查询按钮已更新，保存素材后生效' })
          }}
        />
      )}
    </div>
  )
}

export default MaterialFormModal
