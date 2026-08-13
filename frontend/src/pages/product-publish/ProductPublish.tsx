/**
 * 单品发布页面。
 * 负责账号、素材导入、图片上传和提交；详细字段由 ProductPublishForm 负责。
 */
import React, { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { CheckCircle, ExternalLink, FolderOpen, Loader2, Send, Trash2, Upload, X, XCircle } from 'lucide-react'
import { getAccountDetails } from '@/api/accounts'
import { getMaterials, publishSingle, type MaterialVideo, type ProductMaterial, uploadProductImages, uploadProductVideos } from '@/api/productPublish'
import { PageLoading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'
import ProductPublishForm from './ProductPublishForm'
import ProductVideoUploader from './ProductVideoUploader'
import { buildSkuKey, findDuplicateSpecificationValue, type ProductSpecification, type PublishForm, type SkuRow } from './publishTypes'

function materialSpecifications(material: ProductMaterial): { specifications: ProductSpecification[]; skuRows: SkuRow[] } {
  const specifications = (material.specifications || []).map((spec, specIndex) => ({
    id: `spec-${specIndex}-${Date.now()}`,
    name: spec.name,
    supportImage: Boolean(spec.support_image),
    values: (spec.values || []).map((value, valueIndex) => ({
      id: `value-${specIndex}-${valueIndex}-${Date.now()}`,
      name: value.name,
      image: value.image || null,
    })),
  }))
  const skuRows = (material.sku_rows || []).map((row) => ({
    key: buildSkuKey(specifications, row.specs || {}),
    specs: row.specs || {},
    price: String(row.price ?? ''),
    stock: row.stock == null ? '' : String(row.stock),
  }))
  return { specifications, skuRows }
}

function MaterialPickerModal({ onSelect, onClose }: { onSelect: (material: ProductMaterial) => void; onClose: () => void }) {
  const [materials, setMaterials] = useState<ProductMaterial[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getMaterials(1, 1000).then((result) => { if (result.success && result.data) setMaterials(result.data.list); setLoading(false) }).catch(() => setLoading(false))
  }, [])

  return (
    <div className="modal-overlay z-50">
      <div className="modal-content max-w-lg">
        <div className="modal-header"><h2 className="modal-title">从素材库选择</h2><button type="button" className="modal-close" title="关闭" onClick={onClose}><X className="w-5 h-5" /></button></div>
        <div className="modal-body">
          {loading ? <div className="flex justify-center py-10"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div> : materials.length === 0 ? <p className="text-center text-slate-400 py-10">素材库为空，请先添加素材</p> : <div className="space-y-1">{materials.map((material) => <button type="button" key={material.id} className="w-full flex items-center gap-3 p-3 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 text-left transition-colors" onClick={() => onSelect(material)}>{material.images?.[0] ? <img src={material.images[0]} alt={material.title} className="w-12 h-12 object-cover rounded-lg flex-shrink-0" /> : <div className="w-12 h-12 bg-slate-100 dark:bg-slate-700 rounded-lg flex items-center justify-center text-slate-400 text-xs flex-shrink-0">无图</div>}<span className="flex-1 min-w-0"><span className="block font-medium text-slate-800 dark:text-slate-100 truncate">{material.title}</span><span className="block text-sm text-amber-600">¥{material.price}</span></span><span className="badge-gray flex-shrink-0">{material.condition}</span></button>)}</div>}
        </div>
      </div>
    </div>
  )
}

export function ProductPublish() {
  const { addToast } = useUIStore()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [accounts, setAccounts] = useState<any[]>([])
  const [loadingAccounts, setLoadingAccounts] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [showPicker, setShowPicker] = useState(false)
  const [categoryLocked, setCategoryLocked] = useState(false)
  const [imagePaths, setImagePaths] = useState<string[]>([])
  const [imagePreviews, setImagePreviews] = useState<string[]>([])
  const [result, setResult] = useState<{ success: boolean; message: string; item_url?: string; sync_status?: 'success' | 'failed' | 'skipped'; sync_message?: string; sync_total_count?: number; sync_saved_count?: number } | null>(null)
  const [form, setForm] = useState<PublishForm>({
    account_id: '', title: '', description: '', price: '', original_price: '', category: '',
    platform_category_id: '', platform_category_name: '', platform_channel_category_id: '', platform_channel_category_name: '', platform_leaf_id: '', platform_tb_category_id: '', platform_category_path: [], platform_attributes: [], category_source: 'manual', videos: [], quantity: 1,
    address: '', delivery_method: 'express', shipping_method: 'free', support_pickup: false, postage: '0', brand: '', condition: '全新', specifications: [], sku_rows: [],
  })

  useEffect(() => {
    getAccountDetails().then((list) => {
      setAccounts(list)
      const defaultAccount = list.find((account) => account.enabled) || list[0]
      if (defaultAccount) setForm((current) => ({ ...current, account_id: defaultAccount.id }))
    }).catch(() => addToast({ type: 'error', message: '加载发布账号失败' })).finally(() => setLoadingAccounts(false))
  }, [addToast])

  const uploadFiles = async (files: File[]) => {
    if (!files.length) return null
    const response = await uploadProductImages(files)
    if (!response.success || !response.data) {
      addToast({ type: 'error', message: response.message || '上传失败' })
      return null
    }
    return response.data
  }

  const handleImageChange = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files || [])
    if (!files.length) return
    if (imagePaths.length + files.length > 9) { addToast({ type: 'warning', message: '最多上传9张图片' }); return }
    setUploading(true)
    try {
      const data = await uploadFiles(files)
      if (data) { setImagePaths((current) => [...current, ...data.paths]); setImagePreviews((current) => [...current, ...data.urls]); addToast({ type: 'success', message: `成功上传 ${data.paths.length} 张图片` }) }
    } catch { addToast({ type: 'error', message: '图片上传失败，请重试' }) } finally { setUploading(false); if (fileInputRef.current) fileInputRef.current.value = '' }
  }

  const handleSpecUpload = async (file: File) => {
    setUploading(true)
    try { const data = await uploadFiles([file]); return data?.urls[0] || null } catch { addToast({ type: 'error', message: '规格图片上传失败，请重试' }); return null } finally { setUploading(false) }
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

  const applyMaterial = (material: ProductMaterial) => {
    const imported = materialSpecifications(material)
    const hasImportedCategory = Boolean(
      material.platform_category_id
        || material.platform_channel_category_id
        || material.platform_tb_category_id
        || material.platform_category_path?.length,
    )
    setCategoryLocked(hasImportedCategory)
    setForm((current) => ({ ...current, title: material.title, description: material.description, price: String(material.price), original_price: material.original_price ? String(material.original_price) : '', category: material.category || '', address: material.address || '', address_expected_text: material.address_expected_text || undefined, platform_category_id: material.platform_category_id || '', platform_category_name: material.platform_category_name || '', platform_channel_category_id: material.platform_channel_category_id || '', platform_channel_category_name: material.platform_channel_category_name || '', platform_leaf_id: material.platform_leaf_id || '', platform_tb_category_id: material.platform_tb_category_id || '', platform_category_path: material.platform_category_path || [], platform_attributes: material.platform_attributes || [], category_source: material.category_source || 'manual', category_confidence: material.category_confidence ?? undefined, videos: material.videos || [], quantity: material.quantity || 1, delivery_method: material.delivery_method || 'express', shipping_method: material.shipping_method || (material.postage > 0 ? 'fixed' : 'free'), support_pickup: Boolean(material.support_pickup), postage: String(material.postage ?? 0), brand: material.brand || '', condition: material.condition || '全新', specifications: imported.specifications, sku_rows: imported.skuRows }))
    setImagePaths(material.images || []); setImagePreviews(material.images || []); setShowPicker(false); addToast({ type: 'success', message: '已从素材库导入' })
  }

  const handlePublish = async () => {
    if (!form.account_id) return addToast({ type: 'warning', message: '请选择发布账号' })
    if (!form.title.trim()) return addToast({ type: 'warning', message: '请填写商品标题' })
    if (!form.description.trim()) return addToast({ type: 'warning', message: '请填写商品描述' })
    if (form.description.length > 1500) return addToast({ type: 'warning', message: '商品描述不能超过1500字' })
    if (!form.price || parseFloat(form.price) <= 0) return addToast({ type: 'warning', message: '请填写有效价格' })
    if (imagePaths.length === 0) return addToast({ type: 'warning', message: '请至少上传一张商品图片' })
    const invalidSpec = form.specifications.find((spec) => !spec.name.trim() || !spec.values.some((value) => value.name.trim()))
    if (invalidSpec) return addToast({ type: 'warning', message: '请完善商品规格类型和规格值' })
    const duplicateSpecValue = findDuplicateSpecificationValue(form.specifications)
    if (duplicateSpecValue) return addToast({ type: 'warning', message: `规格“${duplicateSpecValue.specificationName}”存在重复规格值：${duplicateSpecValue.valueName}` })
    if (form.specifications.length > 0 && form.sku_rows.length === 0) return addToast({ type: 'warning', message: '请等待规格组合生成后再发布' })
    const invalidSku = form.sku_rows.find((row) => !row.price || parseFloat(row.price) <= 0 || !row.stock.trim() || Number(row.stock) < 0)
    if (invalidSku) return addToast({ type: 'warning', message: '请完善所有规格的价格和库存' })
    setSubmitting(true); setResult(null)
    try {
      const response = await publishSingle({
        account_id: form.account_id, title: form.title, description: form.description, price: parseFloat(form.price), original_price: form.original_price ? parseFloat(form.original_price) : undefined, category: form.category || undefined,
        platform_category_id: form.platform_category_id || undefined, platform_category_name: form.platform_category_name || undefined, platform_channel_category_id: form.platform_channel_category_id || undefined, platform_channel_category_name: form.platform_channel_category_name || undefined, platform_leaf_id: form.platform_leaf_id || undefined, platform_tb_category_id: form.platform_tb_category_id || undefined, platform_attributes: form.platform_attributes, platform_category_path: form.platform_category_path, category_source: form.category_source, category_confidence: form.category_confidence,
        images: imagePaths, videos: form.videos, quantity: form.quantity, specifications: form.specifications.map((spec) => ({ name: spec.name, support_image: spec.supportImage, values: spec.values.map((value) => ({ name: value.name, image: value.image || undefined })) })), sku_rows: form.sku_rows.map((row) => ({ specs: row.specs, price: parseFloat(row.price), stock: parseInt(row.stock, 10) || 0 })), stock: form.quantity, address: form.address || undefined, address_expected_text: form.address_expected_text || undefined, delivery_method: form.delivery_method, shipping_method: form.shipping_method, support_pickup: form.support_pickup, postage: parseFloat(form.postage) || 0, brand: form.brand || undefined, condition: form.condition,
      })
      const message = response.message || (response.success ? '商品发布成功' : '发布失败')
      setResult({ success: response.success, message, item_url: response.data?.item_url || undefined, sync_status: response.data?.sync_status || undefined, sync_message: response.data?.sync_message || undefined, sync_total_count: response.data?.sync_total_count || 0, sync_saved_count: response.data?.sync_saved_count || 0 })
      addToast({ type: response.success ? 'success' : 'error', message })
    } catch { addToast({ type: 'error', message: '发布请求失败，请重试' }); setResult({ success: false, message: '网络错误，请重试' }) } finally { setSubmitting(false) }
  }

  if (loadingAccounts) return <PageLoading />
  return (
    <div className="space-y-3 sm:space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3"><div><h1 className="page-title">单品发布</h1><p className="page-description">填写商品信息，通过闲鱼接口发布</p></div><button className="btn-ios-secondary" onClick={() => setShowPicker(true)}><FolderOpen className="w-4 h-4" />从素材库导入</button></div>
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="xl:col-span-2"><ProductPublishForm form={form} setForm={setForm} accounts={accounts} onUploadSpecImage={handleSpecUpload} categoryLocked={categoryLocked} onCategoryEdit={() => setCategoryLocked(false)} /></motion.div>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="space-y-4">
          <div className="vben-card"><div className="vben-card-header"><h2 className="vben-card-title">宝贝图片与视频 <span className="text-red-500 ml-1">*</span></h2><span className="text-xs text-slate-400">{imagePreviews.length}/9 图 · {form.videos.length}/3 视频</span></div><div className="vben-card-body"><div className="flex flex-wrap gap-2">{imagePreviews.map((url, index) => <div key={`${url}-${index}`} className="relative w-20 h-20 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-600 group"><img src={url} alt="" className="w-full h-full object-cover" />{index === 0 && <span className="absolute bottom-0 left-0 right-0 bg-blue-500/80 text-white text-[10px] text-center py-0.5">首图</span>}<button type="button" title="移除图片" onClick={() => { setImagePaths((current) => current.filter((_, itemIndex) => itemIndex !== index)); setImagePreviews((current) => current.filter((_, itemIndex) => itemIndex !== index)) }} className="absolute top-0.5 right-0.5 bg-black/60 hover:bg-red-500 text-white rounded p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"><Trash2 className="w-3 h-3" /></button></div>)}{imagePreviews.length < 9 && <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploading} className="w-20 h-20 border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-lg flex flex-col items-center justify-center text-slate-400 hover:border-blue-400 hover:text-blue-500 transition-colors disabled:opacity-50">{uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}<span className="text-xs mt-1">{uploading ? '上传中' : '添加首图'}</span></button>}</div><input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={handleImageChange} disabled={uploading} /><ProductVideoUploader videos={form.videos} onUploadVideo={handleVideoUpload} onChange={(videos) => setForm((current) => ({ ...current, videos }))} /></div></div>
          <div className="vben-card"><div className="vben-card-body space-y-3"><button className="btn-ios-primary w-full" disabled={submitting || uploading} onClick={handlePublish}>{submitting ? <><Loader2 className="w-4 h-4 animate-spin" />正在调用闲鱼接口...</> : <><Send className="w-4 h-4" />立即发布</>}</button>{submitting && <p className="text-xs text-slate-400 text-center">接口发布中，请勿重复提交</p>}</div></div>
          {result && <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className={`vben-card border-l-4 ${result.success ? 'border-l-green-500' : 'border-l-red-500'}`}><div className="vben-card-body"><div className="flex items-start gap-3">{result.success ? <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" /> : <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />}<div className="flex-1"><p className={`font-medium ${result.success ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}>{result.message}</p>{result.item_url && <a href={result.item_url} target="_blank" rel="noopener noreferrer" className="text-sm text-blue-500 hover:underline flex items-center gap-1 mt-1"><ExternalLink className="w-3 h-3" />查看商品</a>}{(result.sync_status === 'success' || result.sync_status === 'failed') && <p className="text-xs mt-2 text-slate-500 dark:text-slate-300">{result.sync_status === 'success' ? `已自动获取 ${result.sync_total_count || 0} 个商品，入库 ${result.sync_saved_count || 0} 个商品` : result.sync_message}</p>}</div></div></div></motion.div>}
        </motion.div>
      </div>
      {showPicker && <MaterialPickerModal onSelect={applyMaterial} onClose={() => setShowPicker(false)} />}
    </div>
  )
}

export default ProductPublish
