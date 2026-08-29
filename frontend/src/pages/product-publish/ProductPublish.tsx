/**
 * 单品发布页面。
 * 负责账号、素材导入、图片上传和提交；详细字段由 ProductPublishForm 负责。
 */
import React, { useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { CheckCircle, ExternalLink, FolderOpen, Loader2, RefreshCw, Send, Trash2, Upload, XCircle } from 'lucide-react'
import { getAccountDetails } from '@/api/accounts'
import { getPublishAccountCapability, publishSingle, type MaterialVideo, type ProductMaterial, type PublishAccountCapability, uploadProductImages, uploadProductVideos } from '@/api/productPublish'
import { PageLoading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import ProductPublishForm from './ProductPublishForm'
import ProductVideoUploader from './ProductVideoUploader'
import MaterialPickerModal from './MaterialPickerModal'
import { buildSkuKey, findDuplicateSpecificationValue, type ProductSpecification, type PublishForm, type SkuRow } from './publishTypes'

const PERSONAL_SELLER_DEFAULT_STOCK = 1

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

export function ProductPublish() {
  const { addToast } = useUIStore()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const capabilityRequestRef = useRef(0)
  const [accounts, setAccounts] = useState<any[]>([])
  const [loadingAccounts, setLoadingAccounts] = useState(true)
  const [capabilityLoading, setCapabilityLoading] = useState(false)
  const [accountCapability, setAccountCapability] = useState<PublishAccountCapability | null>(null)
  // 能力检测失败（如鱼小铺后台配置暂时取不到）时保留错误文案，并提供「重新检测」入口：
  // 检测失败会禁用发布按钮，若只弹一次 Toast，用户重选同一账号不会触发重新请求而被卡住
  const [capabilityError, setCapabilityError] = useState('')
  const [capabilityRetryToken, setCapabilityRetryToken] = useState(0)
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
  const supportsVideo = accountCapability?.is_fish_shop === true

  useEffect(() => {
    getAccountDetails().then((list) => {
      setAccounts(list)
      const defaultAccount = list.find((account) => account.enabled) || list[0]
      if (defaultAccount) setForm((current) => ({ ...current, account_id: defaultAccount.id }))
    }).catch(() => addToast({ type: 'error', message: '加载发布账号失败' })).finally(() => setLoadingAccounts(false))
  }, [addToast])

  useEffect(() => {
    const accountId = form.account_id
    const requestId = capabilityRequestRef.current + 1
    capabilityRequestRef.current = requestId
    setAccountCapability(null)
    setCapabilityError('')
    if (!accountId) {
      setCapabilityLoading(false)
      return
    }

    setCapabilityLoading(true)
    getPublishAccountCapability(accountId).then((response) => {
      if (capabilityRequestRef.current !== requestId) return
      if (!response.success || !response.data) {
        const message = response.message || '账号发布能力检测失败'
        setCapabilityError(message)
        addToast({ type: 'error', message })
        return
      }
      setAccountCapability(response.data)
    }).catch((error) => {
      if (capabilityRequestRef.current !== requestId) return
      const message = getApiErrorMessage(error, '账号发布能力检测失败')
      setCapabilityError(message)
      addToast({ type: 'error', message })
    }).finally(() => {
      if (capabilityRequestRef.current === requestId) setCapabilityLoading(false)
    })
  }, [addToast, form.account_id, capabilityRetryToken])

  useEffect(() => {
    if (accountCapability?.is_fish_shop !== false) return
    setForm((current) => (
      current.videos.length === 0 && current.quantity === PERSONAL_SELLER_DEFAULT_STOCK
        ? current
        : { ...current, videos: [], quantity: PERSONAL_SELLER_DEFAULT_STOCK }
    ))
    if (form.videos.length > 0) {
      addToast({ type: 'warning', message: '普通卖家账号不支持上传视频，已移除当前视频' })
    }
  }, [accountCapability?.is_fish_shop, addToast, form.videos.length])

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
    if (!supportsVideo) {
      addToast({ type: 'warning', message: '普通卖家账号不支持上传视频' })
      return null
    }
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
    const personalAccount = accountCapability?.is_fish_shop === false
    const personalSpecConflict = personalAccount && (imported.specifications.length > 0 || imported.skuRows.length > 0)
    const personalTemplateConflict = personalAccount && material.shipping_method === 'template'
    const personalVideoConflict = personalAccount && (material.videos?.length || 0) > 0
    const hasImportedCategory = Boolean(
      material.platform_category_id
        || material.platform_channel_category_id
        || material.platform_tb_category_id
        || material.platform_category_path?.length,
    )
    setCategoryLocked(hasImportedCategory)
    setForm((current) => {
      const importedShippingMethod = material.shipping_method || (material.postage > 0 ? 'fixed' : 'free')
      return { ...current, title: material.title, description: material.description, price: String(material.price), original_price: material.original_price ? String(material.original_price) : '', category: material.category || '', address: material.address || '', address_expected_text: material.address_expected_text || undefined, platform_category_id: material.platform_category_id || '', platform_category_name: material.platform_category_name || '', platform_channel_category_id: material.platform_channel_category_id || '', platform_channel_category_name: material.platform_channel_category_name || '', platform_leaf_id: material.platform_leaf_id || '', platform_tb_category_id: material.platform_tb_category_id || '', platform_category_path: material.platform_category_path || [], platform_attributes: material.platform_attributes || [], category_source: material.category_source || 'manual', category_confidence: material.category_confidence ?? undefined, videos: personalAccount ? [] : material.videos || [], quantity: personalAccount ? PERSONAL_SELLER_DEFAULT_STOCK : material.quantity || 1, delivery_method: material.delivery_method || 'express', shipping_method: importedShippingMethod, support_pickup: Boolean(material.support_pickup), postage: String(material.postage ?? 0), brand: material.brand || '', condition: material.condition || '全新', specifications: imported.specifications, sku_rows: imported.skuRows }
    })
    setImagePaths(material.images || []); setImagePreviews(material.images || []); setShowPicker(false)
    if (personalSpecConflict) addToast({ type: 'warning', message: '当前普通卖家账号不支持该素材的多规格，请改用无规格素材或鱼小铺账号' })
    else if (personalTemplateConflict) addToast({ type: 'warning', message: '当前普通卖家账号不支持该素材的运费模板，请重新选择发货方式' })
    else if (personalVideoConflict) addToast({ type: 'warning', message: '普通卖家账号不支持上传视频，已忽略素材中的视频' })
    else addToast({ type: 'success', message: '已从素材库导入' })
  }

  const handlePublish = async () => {
    if (!form.account_id) return addToast({ type: 'warning', message: '请选择发布账号' })
    if (capabilityLoading) return addToast({ type: 'warning', message: '正在检测账号发布能力，请稍候' })
    if (!accountCapability || accountCapability.account_id !== form.account_id) return addToast({ type: 'error', message: '账号发布能力尚未确认，请重新选择账号' })
    if (!form.title.trim()) return addToast({ type: 'warning', message: '请填写商品标题' })
    if (!form.description.trim()) return addToast({ type: 'warning', message: '请填写商品描述' })
    if (form.description.length > 1500) return addToast({ type: 'warning', message: '商品描述不能超过1500字' })
    if (!form.price || parseFloat(form.price) <= 0) return addToast({ type: 'warning', message: '请填写有效价格' })
    if (imagePaths.length === 0) return addToast({ type: 'warning', message: '请至少上传一张商品图片' })
    if (!accountCapability.is_fish_shop && (form.specifications.length > 0 || form.sku_rows.length > 0)) return addToast({ type: 'warning', message: '普通卖家账号不能发布多规格和独立库存商品，请改用无规格素材或鱼小铺账号' })
    if (!accountCapability.is_fish_shop && form.shipping_method === 'template') return addToast({ type: 'warning', message: '普通卖家账号不支持运费模板，请重新选择发货方式' })
    if (accountCapability.is_fish_shop) {
      const invalidSpec = form.specifications.find((spec) => !spec.name.trim() || !spec.values.some((value) => value.name.trim()))
      if (invalidSpec) return addToast({ type: 'warning', message: '请完善商品规格类型和规格值' })
      const duplicateSpecValue = findDuplicateSpecificationValue(form.specifications)
      if (duplicateSpecValue) return addToast({ type: 'warning', message: `规格“${duplicateSpecValue.specificationName}”存在重复规格值：${duplicateSpecValue.valueName}` })
      if (form.specifications.length > 0 && form.sku_rows.length === 0) return addToast({ type: 'warning', message: '请等待规格组合生成后再发布' })
      const invalidSku = form.sku_rows.find((row) => !row.price || parseFloat(row.price) <= 0 || !row.stock.trim() || Number(row.stock) < 0)
      if (invalidSku) return addToast({ type: 'warning', message: '请完善所有规格的价格和库存' })
    }
    setSubmitting(true); setResult(null)
    try {
      const response = await publishSingle({
        account_id: form.account_id, title: form.title, description: form.description, price: parseFloat(form.price), original_price: form.original_price ? parseFloat(form.original_price) : undefined, category: form.category || undefined,
        platform_category_id: form.platform_category_id || undefined, platform_category_name: form.platform_category_name || undefined, platform_channel_category_id: form.platform_channel_category_id || undefined, platform_channel_category_name: form.platform_channel_category_name || undefined, platform_leaf_id: form.platform_leaf_id || undefined, platform_tb_category_id: form.platform_tb_category_id || undefined, platform_attributes: form.platform_attributes, platform_category_path: form.platform_category_path, category_source: form.category_source, category_confidence: form.category_confidence,
        images: imagePaths, videos: accountCapability.is_fish_shop ? form.videos : [], quantity: accountCapability.is_fish_shop ? form.quantity : PERSONAL_SELLER_DEFAULT_STOCK, specifications: form.specifications.map((spec) => ({ name: spec.name, support_image: spec.supportImage, values: spec.values.map((value) => ({ name: value.name, image: value.image || undefined })) })), sku_rows: form.sku_rows.map((row) => ({ specs: row.specs, price: parseFloat(row.price), stock: parseInt(row.stock, 10) || 0 })), stock: accountCapability.is_fish_shop ? form.quantity : PERSONAL_SELLER_DEFAULT_STOCK, address: form.address || undefined, address_expected_text: form.address_expected_text || undefined, delivery_method: form.delivery_method, shipping_method: form.shipping_method, support_pickup: form.support_pickup, postage: parseFloat(form.postage) || 0, brand: form.brand || undefined, condition: form.condition,
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
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="xl:col-span-2"><ProductPublishForm form={form} setForm={setForm} accounts={accounts} onUploadSpecImage={handleSpecUpload} categoryLocked={categoryLocked} onCategoryEdit={() => setCategoryLocked(false)} accountCapability={accountCapability} capabilityLoading={capabilityLoading} /></motion.div>
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.05 }} className="space-y-4">
          <div className="vben-card"><div className="vben-card-header"><h2 className="vben-card-title">{supportsVideo ? '宝贝图片与视频' : '宝贝图片'} <span className="text-red-500 ml-1">*</span></h2><span className="text-xs text-slate-400">{imagePreviews.length}/9 图{supportsVideo ? ` · ${form.videos.length}/3 视频` : ''}</span></div><div className="vben-card-body"><div className="flex flex-wrap gap-2">{imagePreviews.map((url, index) => <div key={`${url}-${index}`} className="relative w-20 h-20 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-600 group"><img src={url} alt="" className="w-full h-full object-cover" />{index === 0 && <span className="absolute bottom-0 left-0 right-0 bg-blue-500/80 text-white text-[10px] text-center py-0.5">首图</span>}<button type="button" title="移除图片" onClick={() => { setImagePaths((current) => current.filter((_, itemIndex) => itemIndex !== index)); setImagePreviews((current) => current.filter((_, itemIndex) => itemIndex !== index)) }} className="absolute top-0.5 right-0.5 bg-black/60 hover:bg-red-500 text-white rounded p-0.5 opacity-0 group-hover:opacity-100 transition-opacity"><Trash2 className="w-3 h-3" /></button></div>)}{imagePreviews.length < 9 && <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploading} className="w-20 h-20 border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-lg flex flex-col items-center justify-center text-slate-400 hover:border-blue-400 hover:text-blue-500 transition-colors disabled:opacity-50">{uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}<span className="text-xs mt-1">{uploading ? '上传中' : '添加首图'}</span></button>}</div><input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={handleImageChange} disabled={uploading} />{supportsVideo && <ProductVideoUploader videos={form.videos} onUploadVideo={handleVideoUpload} onChange={(videos) => setForm((current) => ({ ...current, videos }))} />}</div></div>
          <div className="vben-card"><div className="vben-card-body space-y-3">{capabilityError && !capabilityLoading && <div className="rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300"><p>{capabilityError}</p><button type="button" className="btn-ios-secondary mt-2 w-full" onClick={() => setCapabilityRetryToken((current) => current + 1)}><RefreshCw className="w-4 h-4" />重新检测账号能力</button></div>}{!capabilityError && !capabilityLoading && !accountCapability && <p className="text-sm text-amber-600 dark:text-amber-400">{accounts.length === 0 ? '当前没有可用的闲鱼账号，请先到「账号管理」添加账号后再发布' : '请先在左侧选择发布账号，选定后会自动检测该账号的发布能力'}</p>}<button className="btn-ios-primary w-full" disabled={submitting || uploading || capabilityLoading || !accountCapability} onClick={handlePublish}>{submitting ? <><Loader2 className="w-4 h-4 animate-spin" />正在调用闲鱼接口...</> : capabilityLoading ? <><Loader2 className="w-4 h-4 animate-spin" />检测账号能力...</> : <><Send className="w-4 h-4" />立即发布</>}</button>{submitting && <p className="text-xs text-slate-400 text-center">接口发布中，请勿重复提交</p>}</div></div>
          {result && <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className={`vben-card border-l-4 ${result.success ? 'border-l-green-500' : 'border-l-red-500'}`}><div className="vben-card-body"><div className="flex items-start gap-3">{result.success ? <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" /> : <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />}<div className="flex-1"><p className={`font-medium ${result.success ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}>{result.message}</p>{result.item_url && <a href={result.item_url} target="_blank" rel="noopener noreferrer" className="text-sm text-blue-500 hover:underline flex items-center gap-1 mt-1"><ExternalLink className="w-3 h-3" />查看商品</a>}{(result.sync_status === 'success' || result.sync_status === 'failed') && <p className="text-xs mt-2 text-slate-500 dark:text-slate-300">{result.sync_status === 'success' ? `已自动获取 ${result.sync_total_count || 0} 个商品，入库 ${result.sync_saved_count || 0} 个商品` : result.sync_message}</p>}</div></div></div></motion.div>}
        </motion.div>
      </div>
      {showPicker && <MaterialPickerModal onSelect={applyMaterial} onClose={() => setShowPicker(false)} />}
    </div>
  )
}

export default ProductPublish
