/**
 * 单品发布页面
 *
 * 功能：
 * 1. 选择闲鱼账号
 * 2. 填写商品信息（标题/描述/价格/分类/成色/发货方式等）
 * 3. 上传商品图片（最多9张，文件上传方式）
 * 4. 或从素材库快速导入
 * 5. 提交后调用后端 Playwright 自动发布（同步等待）
 */
import React, { useState, useEffect, useRef } from 'react'
import { motion } from 'framer-motion'
import { Send, FolderOpen, Loader2, CheckCircle, XCircle, ExternalLink, Upload, Trash2, X } from 'lucide-react'
import { useUIStore } from '@/store/uiStore'
import { publishSingle, getMaterials, uploadProductImages, type ProductMaterial } from '@/api/productPublish'
import { getAccountDetails } from '@/api/accounts'
import { PageLoading } from '@/components/common/Loading'

const CATEGORIES = ['数码家电', '服饰鞋包', '家居日用', '图书音像', '美妆个护', '母婴用品', '运动户外', '食品生鲜', '虚拟商品', '其他']
const CONDITIONS = ['全新', '99新', '95新', '9成新', '8成新', '7成新以下']

interface PublishForm {
  account_id: string
  title: string
  description: string
  price: string
  original_price: string
  category: string
  address: string
  delivery_method: 'express' | 'pickup'
  postage: string
  brand: string
  condition: string
}

/** 从素材库选择弹窗 */
function MaterialPickerModal({ onSelect, onClose }: { onSelect: (m: ProductMaterial) => void; onClose: () => void }) {
  const [materials, setMaterials] = useState<ProductMaterial[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    getMaterials(1, 1000)
      .then(res => { if (res.success) setMaterials(res.data.list); setLoading(false) })
      .catch(() => { setLoading(false) })
  }, [])

  return (
    <div className="modal-overlay">
      <div className="modal-content max-w-lg">
        <div className="modal-header">
          <h2 className="modal-title">从素材库选择</h2>
          <button className="modal-close" onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <div className="modal-body">
          {loading ? (
            <div className="flex justify-center py-10"><Loader2 className="w-8 h-8 animate-spin text-blue-500" /></div>
          ) : materials.length === 0 ? (
            <p className="text-center text-slate-400 py-10">素材库为空，请先在「素材库」页面添加素材</p>
          ) : (
            <div className="space-y-1">
              {materials.map(m => (
                <div key={m.id}
                  className="flex items-center gap-3 p-3 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-700 cursor-pointer transition-colors"
                  onClick={() => onSelect(m)}>
                  {m.images?.[0] ? (
                    <img src={m.images[0]} alt={m.title} className="w-12 h-12 object-cover rounded-lg flex-shrink-0" />
                  ) : (
                    <div className="w-12 h-12 bg-slate-100 dark:bg-slate-700 rounded-lg flex items-center justify-center text-slate-400 text-xs flex-shrink-0">无图</div>
                  )}
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-slate-800 dark:text-slate-100 truncate">{m.title}</p>
                    <p className="text-sm text-amber-600">{m.price}</p>
                  </div>
                  <span className="badge-gray flex-shrink-0">{m.condition}</span>
                </div>
              ))}
            </div>
          )}
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
  const [result, setResult] = useState<{
    success: boolean
    message: string
    item_url?: string
    sync_status?: 'success' | 'failed' | 'skipped'
    sync_message?: string
    sync_total_count?: number
    sync_saved_count?: number
  } | null>(null)
  const [imagePaths, setImagePaths] = useState<string[]>([])
  const [imagePreviews, setImagePreviews] = useState<string[]>([])
  const [form, setForm] = useState<PublishForm>({
    account_id: '', title: '', description: '', price: '', original_price: '',
    category: '', address: '', delivery_method: 'express', postage: '0', brand: '', condition: '全新',
  })

  useEffect(() => {
    getAccountDetails()
      .then(list => { setAccounts(list); if (list.length > 0) setForm(f => ({ ...f, account_id: list[0].id })) })
      .catch(() => {})
      .finally(() => setLoadingAccounts(false))
  }, [])

  /** 处理图片上传 */
  const handleImageChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || [])
    if (!files.length) return
    if (imagePaths.length + files.length > 9) { addToast({ type: 'warning', message: '最多上传9张图片' }); return }
    setUploading(true)
    try {
      const res = await uploadProductImages(files)
      if (res.success && res.data) {
        setImagePaths(prev => [...prev, ...res.data!.paths])
        setImagePreviews(prev => [...prev, ...res.data!.urls])
        addToast({ type: 'success', message: `成功上传 ${res.data.paths.length} 张图片` })
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

  /** 移除图片 */
  const removeImage = (idx: number) => {
    setImagePaths(prev => prev.filter((_, i) => i !== idx))
    setImagePreviews(prev => prev.filter((_, i) => i !== idx))
  }

  /** 从素材库导入 */
  const applyMaterial = (m: ProductMaterial) => {
    setForm(f => ({
      ...f, title: m.title, description: m.description, price: String(m.price),
      original_price: m.original_price ? String(m.original_price) : '',
      category: m.category || '', address: m.address || '',
      delivery_method: (m.delivery_method as 'express' | 'pickup') || 'express',
      postage: String(m.postage ?? 0), brand: m.brand || '', condition: m.condition || '全新',
    }))
    const urls = m.images || []
    setImagePaths(urls)
    setImagePreviews(urls)
    setShowPicker(false)
    addToast({ type: 'success', message: '已从素材库导入' })
  }

  /** 发布商品 */
  const handlePublish = async () => {
    if (!form.account_id) { addToast({ type: 'warning', message: '请选择发布账号' }); return }
    if (!form.title.trim()) { addToast({ type: 'warning', message: '请填写商品标题' }); return }
    if (!form.description.trim()) { addToast({ type: 'warning', message: '请填写商品描述' }); return }
    if (!form.price || parseFloat(form.price) <= 0) { addToast({ type: 'warning', message: '请填写有效价格' }); return }
    if (imagePaths.length === 0) { addToast({ type: 'warning', message: '请至少上传一张商品图片' }); return }
    setSubmitting(true)
    setResult(null)
    try {
      const res = await publishSingle({
        account_id: form.account_id, title: form.title, description: form.description,
        price: parseFloat(form.price),
        original_price: form.original_price ? parseFloat(form.original_price) : undefined,
        category: form.category || undefined, images: imagePaths, address: form.address || undefined,
        delivery_method: form.delivery_method, postage: parseFloat(form.postage) || 0,
        brand: form.brand || undefined, condition: form.condition,
      })
      const message = res.message || (res.success ? '商品发布成功' : '发布失败')
      setResult({
        success: res.success,
        message,
        item_url: res.data?.item_url || undefined,
        sync_status: res.data?.sync_status || undefined,
        sync_message: res.data?.sync_message || undefined,
        sync_total_count: res.data?.sync_total_count || 0,
        sync_saved_count: res.data?.sync_saved_count || 0,
      })
      if (res.success) {
        addToast({
          type: res.data?.sync_status === 'failed' ? 'warning' : 'success',
          message,
        })
      }
      else addToast({ type: 'error', message })
    } catch {
      addToast({ type: 'error', message: '发布请求失败，请重试' })
      setResult({ success: false, message: '网络错误，请重试' })
    } finally {
      setSubmitting(false)
    }
  }

  if (loadingAccounts) return <PageLoading />

  return (
    <div className="space-y-3 sm:space-y-4">
      {/* 标题栏 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="page-title">单品发布</h1>
          <p className="page-description">填写商品信息，通过 Playwright 自动发布到闲鱼</p>
        </div>
        <button className="btn-ios-secondary" onClick={() => setShowPicker(true)}>
          <FolderOpen className="w-4 h-4" />从素材库导入
        </button>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
        {/* 左侧：表单 */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          className="xl:col-span-2 vben-card">
          <div className="vben-card-header">
            <h2 className="vben-card-title"><Send className="w-4 h-4" />商品信息</h2>
          </div>
          <div className="vben-card-body space-y-4">
            {/* 账号 */}
            <div className="input-group">
              <label className="input-label">发布账号 <span className="text-red-500">*</span></label>
              <select className="input-ios" value={form.account_id}
                onChange={e => setForm(f => ({ ...f, account_id: e.target.value }))}>
                <option value="">-- 请选择账号 --</option>
                {accounts.map((a: any) => (
                  <option key={a.id} value={a.id}>{a.note ? `${a.note} (${a.id})` : a.id}</option>
                ))}
              </select>
            </div>
            {/* 标题 */}
            <div className="input-group">
              <label className="input-label">
                商品标题 <span className="text-red-500">*</span>
                <span className="text-xs text-slate-400 ml-2 font-normal">{form.title.length}/30</span>
              </label>
              <input className="input-ios" maxLength={30} placeholder="请输入商品标题（最多30字）"
                value={form.title} onChange={e => setForm(f => ({ ...f, title: e.target.value }))} />
            </div>
            {/* 描述 */}
            <div className="input-group">
              <label className="input-label">商品描述 <span className="text-red-500">*</span></label>
              <textarea className="input-ios" rows={4} placeholder="请详细描述商品信息"
                value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))} />
            </div>
            {/* 价格 */}
            <div className="grid grid-cols-2 gap-4">
              <div className="input-group">
                <label className="input-label">售价（元）<span className="text-red-500">*</span></label>
                <input type="number" className="input-ios" placeholder="0.00" min="0" step="0.01"
                  value={form.price} onChange={e => setForm(f => ({ ...f, price: e.target.value }))} />
              </div>
              <div className="input-group">
                <label className="input-label">原价（元，选填）</label>
                <input type="number" className="input-ios" placeholder="0.00" min="0" step="0.01"
                  value={form.original_price} onChange={e => setForm(f => ({ ...f, original_price: e.target.value }))} />
              </div>
            </div>
            {/* 分类 + 品牌 */}
            <div className="grid grid-cols-2 gap-4">
              <div className="input-group">
                <label className="input-label">商品分类</label>
                <select className="input-ios" value={form.category}
                  onChange={e => setForm(f => ({ ...f, category: e.target.value }))}>
                  <option value="">请选择分类</option>
                  {CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">品牌（选填）</label>
                <input className="input-ios" placeholder="品牌名称"
                  value={form.brand} onChange={e => setForm(f => ({ ...f, brand: e.target.value }))} />
              </div>
            </div>
            {/* 成色 */}
            <div className="input-group">
              <label className="input-label">新旧程度</label>
              <div className="flex flex-wrap gap-2 mt-1">
                {CONDITIONS.map(c => (
                  <button key={c} type="button" onClick={() => setForm(f => ({ ...f, condition: c }))}
                    className={`px-3 py-1.5 rounded-lg border text-sm transition-colors ${
                      form.condition === c
                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400'
                        : 'border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:border-blue-400'
                    }`}>
                    {c}
                  </button>
                ))}
              </div>
            </div>
            {/* 发货 + 邮费 */}
            <div className="grid grid-cols-2 gap-4">
              <div className="input-group">
                <label className="input-label">发货方式</label>
                <select className="input-ios" value={form.delivery_method}
                  onChange={e => setForm(f => ({ ...f, delivery_method: e.target.value as 'express' | 'pickup' }))}>
                  <option value="express">快递发货</option>
                  <option value="pickup">自提</option>
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">邮费（元，0=包邮）</label>
                <input type="number" className="input-ios" placeholder="0" min="0" step="0.01"
                  value={form.postage} onChange={e => setForm(f => ({ ...f, postage: e.target.value }))} />
              </div>
            </div>
            {/* 所在地 */}
            <div className="input-group">
              <label className="input-label">宝贝所在地</label>
              <input className="input-ios" placeholder="如：北京市朝阳区；填写后本次发布也会自动改为随机地址"
                value={form.address} onChange={e => setForm(f => ({ ...f, address: e.target.value }))} />
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                当前发布策略会忽略这里填写的地址，实际发布时统一从随机地址库自动分配宝贝所在地。
              </p>
            </div>
          </div>
        </motion.div>

        {/* 右侧：图片 + 发布 */}
        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.05 }} className="space-y-4">
          {/* 图片上传 */}
          <div className="vben-card">
            <div className="vben-card-header">
              <h2 className="vben-card-title">商品图片 <span className="text-red-500 ml-1">*</span></h2>
              <span className="text-xs text-slate-400">{imagePreviews.length}/9</span>
            </div>
            <div className="vben-card-body">
              <div className="flex flex-wrap gap-2">
                {imagePreviews.map((url, idx) => (
                  <div key={idx} className="relative w-20 h-20 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-600 group">
                    <img src={url} alt="" className="w-full h-full object-cover" />
                    {idx === 0 && (
                      <span className="absolute bottom-0 left-0 right-0 bg-blue-500/80 text-white text-[10px] text-center py-0.5">封面</span>
                    )}
                    <button type="button" onClick={() => removeImage(idx)}
                      className="absolute top-0.5 right-0.5 bg-black/60 hover:bg-red-500 text-white rounded p-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                      <Trash2 className="w-3 h-3" />
                    </button>
                  </div>
                ))}
                {imagePreviews.length < 9 && (
                  <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploading}
                    className="w-20 h-20 border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-lg flex flex-col items-center justify-center text-slate-400 hover:border-blue-400 hover:text-blue-500 transition-colors disabled:opacity-50">
                    {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}
                    <span className="text-xs mt-1">{uploading ? '上传中' : '添加'}</span>
                  </button>
                )}
              </div>
              <input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden"
                onChange={handleImageChange} disabled={uploading} />
            </div>
          </div>

          {/* 发布操作 */}
          <div className="vben-card">
            <div className="vben-card-body space-y-3">
              <button className="btn-ios-primary w-full" disabled={submitting || uploading} onClick={handlePublish}>
                {submitting
                  ? <><Loader2 className="w-4 h-4 animate-spin" />正在发布（约 30-60 秒）...</>
                  : <><Send className="w-4 h-4" />立即发布</>}
              </button>
              {submitting && (
                <p className="text-xs text-slate-400 text-center">Playwright 发布中，请勿关闭页面</p>
              )}
            </div>
          </div>

          {/* 发布结果 */}
          {result && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              className={`vben-card border-l-4 ${result.success ? 'border-l-green-500' : 'border-l-red-500'}`}>
              <div className="vben-card-body">
                <div className="flex items-start gap-3">
                  {result.success
                    ? <CheckCircle className="w-5 h-5 text-green-500 flex-shrink-0 mt-0.5" />
                    : <XCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />}
                  <div className="flex-1">
                    <p className={`font-medium ${result.success ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}>
                      {result.message}
                    </p>
                    {result.item_url && (
                      <a href={result.item_url} target="_blank" rel="noopener noreferrer"
                        className="text-sm text-blue-500 hover:underline flex items-center gap-1 mt-1">
                        <ExternalLink className="w-3 h-3" />查看商品
                      </a>
                    )}
                    {(result.sync_status === 'success' || result.sync_status === 'failed') && (
                      <p className={`text-xs mt-2 ${result.sync_status === 'success' ? 'text-slate-500 dark:text-slate-300' : 'text-amber-600 dark:text-amber-400'}`}>
                        {result.sync_status === 'success'
                          ? `已自动获取 ${result.sync_total_count || 0} 个商品，入库 ${result.sync_saved_count || 0} 个商品`
                          : result.sync_message}
                      </p>
                    )}
                  </div>
                </div>
              </div>
            </motion.div>
          )}
        </motion.div>
      </div>

      {showPicker && <MaterialPickerModal onSelect={applyMaterial} onClose={() => setShowPicker(false)} />}
    </div>
  )
}

export default ProductPublish