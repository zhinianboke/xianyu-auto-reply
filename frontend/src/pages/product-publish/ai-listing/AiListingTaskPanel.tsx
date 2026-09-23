/**
 * AI 铺货任务面板
 *
 * 功能：
 * 1. 填写生成参数并启动任务（配置、主题、条数、价格模式、素材默认值、兜底图片）
 * 2. 展示当前任务进度与失败明细，支持取消任务
 * 3. 任务进行中禁止重复提交
 */
import { useRef, useState } from 'react'
import { Image as ImageIcon, Loader2, Sparkles, Upload, X } from 'lucide-react'
import {
  cancelAiListingTask,
  createAiListingTask,
  type AiListingConfig,
  type AiListingTaskDetail,
  type AiListingTaskParams,
} from '@/api/aiListing'
import { uploadProductImages } from '@/api/productPublish'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { clampNumberInput } from '@/utils/number'

/** 成色选项，与素材库保持一致 */
const CONDITIONS = ['全新', '几乎全新', '轻微使用痕迹', '明显使用痕迹', '重度使用痕迹']

/** 运费方式选项，与商品发布表单保持一致 */
const SHIPPING_OPTIONS = [
  { value: 'free', label: '包邮' },
  { value: 'distance', label: '按距离计费' },
  { value: 'fixed', label: '一口价' },
  { value: 'template', label: '运费模板' },
  { value: 'none', label: '无需邮寄' },
]

/** 任务状态对应的中文与徽章样式 */
const STATUS_META: Record<string, { label: string; className: string }> = {
  pending: { label: '等待中', className: 'badge-info' },
  running: { label: '生成中', className: 'badge-info' },
  success: { label: '已完成', className: 'badge-success' },
  partial: { label: '部分成功', className: 'badge-warning' },
  failed: { label: '失败', className: 'badge-danger' },
  canceled: { label: '已取消', className: 'badge-gray' },
}

interface AiListingTaskPanelProps {
  configs: AiListingConfig[]
  task: AiListingTaskDetail | null
  onStartTracking: (taskId: string) => Promise<void>
  onResetTask: () => void
}

export function AiListingTaskPanel({ configs, task, onStartTracking, onResetTask }: AiListingTaskPanelProps) {
  const { addToast } = useUIStore()
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [configId, setConfigId] = useState<number>(configs[0]?.id || 0)
  const [keyword, setKeyword] = useState('')
  const [count, setCount] = useState(5)
  const [priceMode, setPriceMode] = useState<'fixed' | 'range'>('fixed')
  const [price, setPrice] = useState(9.9)
  const [priceMin, setPriceMin] = useState(9.9)
  const [priceMax, setPriceMax] = useState(99.9)
  const [category, setCategory] = useState('')
  const [condition, setCondition] = useState('全新')
  const [brand, setBrand] = useState('')
  const [quantity, setQuantity] = useState(1)
  const [shippingMethod, setShippingMethod] = useState('free')
  const [fallbackImages, setFallbackImages] = useState<string[]>([])
  const [uploading, setUploading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [canceling, setCanceling] = useState(false)

  const selectedConfig = configs.find(item => item.id === configId)
  const imageEnabled = Boolean(selectedConfig?.image_enabled)
  const running = Boolean(task && !task.finished)

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    setUploading(true)
    try {
      const res = await uploadProductImages(Array.from(files))
      if (!res.success || !res.data) {
        addToast({ type: 'error', message: res.message || '图片上传失败' })
        return
      }
      setFallbackImages(prev => [...prev, ...res.data!.urls].slice(0, 9))
      addToast({ type: 'success', message: `已上传 ${res.data.urls.length} 张图片` })
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '图片上传失败') })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const handleSubmit = async () => {
    if (!configId) {
      addToast({ type: 'warning', message: '请先选择一套 AI 配置' })
      return
    }
    if (!keyword.trim()) {
      addToast({ type: 'warning', message: '请填写生成主题' })
      return
    }
    if (priceMode === 'range' && priceMin > priceMax) {
      addToast({ type: 'warning', message: '价格区间下限不能大于上限' })
      return
    }
    if (!imageEnabled && fallbackImages.length === 0) {
      addToast({ type: 'warning', message: '当前配置未启用AI图片生成，请先上传至少1张兜底图片' })
      return
    }

    const params: AiListingTaskParams = {
      config_id: configId,
      keyword: keyword.trim(),
      count,
      price_mode: priceMode,
      price: priceMode === 'fixed' ? price : undefined,
      price_min: priceMode === 'range' ? priceMin : undefined,
      price_max: priceMode === 'range' ? priceMax : undefined,
      material_defaults: {
        category: category.trim() || undefined,
        condition,
        brand: brand.trim() || undefined,
        quantity,
        delivery_method: 'express',
        shipping_method: shippingMethod as AiListingTaskParams['material_defaults']['shipping_method'],
        support_pickup: false,
        postage: 0,
        images: fallbackImages,
      },
    }

    setSubmitting(true)
    try {
      const res = await createAiListingTask(params)
      if (!res.success || !res.data) {
        addToast({ type: 'error', message: res.message || '启动任务失败' })
        return
      }
      addToast({ type: 'success', message: res.message || '任务已开始执行' })
      await onStartTracking(res.data.task_id)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '启动任务失败') })
    } finally {
      setSubmitting(false)
    }
  }

  const handleCancel = async () => {
    if (!task) return
    setCanceling(true)
    try {
      const res = await cancelAiListingTask(task.task_id)
      addToast({
        type: res.success ? 'success' : 'warning',
        message: res.message || (res.success ? '任务已取消' : '任务不存在或已结束'),
      })
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '取消任务失败') })
    } finally {
      setCanceling(false)
    }
  }

  const failedItems = (task?.items || []).filter(item => item.status === 'failed')
  const statusMeta = task ? STATUS_META[task.status] || STATUS_META.pending : null

  return (
    <div className="space-y-4">
      {configs.length === 0 && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-400">
          还没有 AI 配置，请先到「配置管理」新增一套配置。
        </div>
      )}

      {/* 当前任务进度 */}
      {task && statusMeta && (
        <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-3 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-sm font-medium text-slate-900 dark:text-slate-100 truncate">
                {task.keyword}
              </span>
              <span className={statusMeta.className}>{statusMeta.label}</span>
              {running && <Loader2 className="w-3.5 h-3.5 animate-spin text-blue-500" />}
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              {running && (
                <button className="btn-ios-secondary btn-sm" onClick={handleCancel} disabled={canceling}>
                  {canceling ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <X className="w-3.5 h-3.5" />}
                  取消任务
                </button>
              )}
              {!running && (
                <button className="btn-ios-secondary btn-sm" onClick={onResetTask}>
                  <X className="w-3.5 h-3.5" />清除
                </button>
              )}
            </div>
          </div>

          <div className="w-full bg-slate-200 dark:bg-slate-700 rounded-full h-2">
            <div
              className="bg-blue-500 h-2 rounded-full transition-all duration-500"
              style={{ width: `${task.progress_percent}%` }}
            />
          </div>
          <div className="flex flex-wrap justify-between gap-2 text-xs text-slate-500 dark:text-slate-400">
            <span>进度 {task.progress_percent}%（成功 {task.success} 条 / 失败 {task.failed} 条 / 共 {task.total} 条）</span>
            <span>任务 {task.task_id.slice(0, 8)}</span>
          </div>

          {task.error_message && (
            <div className="text-xs text-red-500">{task.error_message}</div>
          )}

          {failedItems.length > 0 && (
            <div className="max-h-32 overflow-y-auto rounded-lg bg-slate-50 dark:bg-slate-800/60 p-2 space-y-1">
              {failedItems.map(item => (
                <div key={item.seq} className="text-xs text-slate-500 dark:text-slate-400">
                  第 {item.seq} 条失败：{item.error_message || '未知原因'}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* 生成参数 */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <div className="input-group">
          <label className="input-label">AI 配置</label>
          <select
            className="input-ios"
            value={configId}
            onChange={e => setConfigId(Number(e.target.value))}
          >
            <option value={0}>请选择配置</option>
            {configs.map(config => (
              <option key={config.id} value={config.id}>
                {config.name}（{config.text_model}）
              </option>
            ))}
          </select>
          <span className="input-hint">
            {selectedConfig
              ? imageEnabled ? '该配置已启用 AI 图片生成' : '该配置未启用 AI 图片生成，需要上传兜底图片'
              : '选择一套配置后开始生成'}
          </span>
        </div>
        <div className="input-group">
          <label className="input-label">生成主题</label>
          <input
            className="input-ios"
            placeholder="如：二手蓝牙耳机"
            value={keyword}
            onChange={e => setKeyword(e.target.value)}
          />
        </div>
        <div className="input-group">
          <label className="input-label">生成条数（1~50）</label>
          <input
            type="number" min="1" max="50" className="input-ios"
            value={count}
            onChange={e => setCount(clampNumberInput(e.target.value, 1, 50, 1))}
          />
        </div>
        <div className="input-group">
          <label className="input-label">价格模式</label>
          <div className="flex gap-2">
            <select
              className="input-ios w-28"
              value={priceMode}
              onChange={e => setPriceMode(e.target.value as 'fixed' | 'range')}
            >
              <option value="fixed">固定价</option>
              <option value="range">价格区间</option>
            </select>
            {priceMode === 'fixed' ? (
              <input
                type="number" min="0.01" step="0.01" className="input-ios flex-1"
                value={price}
                onChange={e => setPrice(clampNumberInput(e.target.value, 0.01, 999999, 0.01))}
              />
            ) : (
              <div className="flex items-center gap-1 flex-1">
                <input
                  type="number" min="0.01" step="0.01" className="input-ios"
                  value={priceMin}
                  onChange={e => setPriceMin(clampNumberInput(e.target.value, 0.01, 999999, 0.01))}
                />
                <span className="text-slate-400">~</span>
                <input
                  type="number" min="0.01" step="0.01" className="input-ios"
                  value={priceMax}
                  onChange={e => setPriceMax(clampNumberInput(e.target.value, 0.01, 999999, 0.01))}
                />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 素材默认值 */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="input-group">
          <label className="input-label">本地分类</label>
          <input
            className="input-ios" placeholder="可空"
            value={category}
            onChange={e => setCategory(e.target.value)}
          />
        </div>
        <div className="input-group">
          <label className="input-label">成色</label>
          <select className="input-ios" value={condition} onChange={e => setCondition(e.target.value)}>
            {CONDITIONS.map(item => <option key={item} value={item}>{item}</option>)}
          </select>
        </div>
        <div className="input-group">
          <label className="input-label">品牌</label>
          <input
            className="input-ios" placeholder="可空"
            value={brand}
            onChange={e => setBrand(e.target.value)}
          />
        </div>
        <div className="input-group">
          <label className="input-label">发布数量</label>
          <input
            type="number" min="1" className="input-ios"
            value={quantity}
            onChange={e => setQuantity(clampNumberInput(e.target.value, 1, 999999, 1))}
          />
        </div>
        <div className="input-group col-span-2">
          <label className="input-label">运费方式</label>
          <select className="input-ios" value={shippingMethod} onChange={e => setShippingMethod(e.target.value)}>
            {SHIPPING_OPTIONS.map(option => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
        </div>
      </div>

      {/* 兜底图片 */}
      <div className="input-group">
        <label className="input-label">
          兜底图片
          <span className="input-hint">
            {imageEnabled ? '（已启用AI图片生成，此处可留空）' : '（未启用AI图片生成，必须上传至少1张）'}
          </span>
        </label>
        <div className="flex flex-wrap items-center gap-2">
          {fallbackImages.map((url, index) => (
            <div key={url} className="relative w-16 h-16 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-700">
              <img src={url} alt={`兜底图片${index + 1}`} className="w-full h-full object-cover" />
              <button
                className="absolute top-0 right-0 bg-black/50 text-white p-0.5"
                title="移除"
                onClick={() => setFallbackImages(prev => prev.filter(item => item !== url))}
              >
                <X className="w-3 h-3" />
              </button>
            </div>
          ))}
          {fallbackImages.length < 9 && (
            <button
              className="w-16 h-16 rounded-lg border border-dashed border-slate-300 dark:border-slate-600 flex flex-col items-center justify-center text-slate-400 hover:border-blue-400 hover:text-blue-500 transition-colors"
              onClick={() => fileInputRef.current?.click()}
              disabled={uploading}
            >
              {uploading
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <><Upload className="w-4 h-4" /><span className="text-[10px] mt-0.5">上传</span></>}
            </button>
          )}
          {fallbackImages.length === 0 && !uploading && (
            <span className="text-xs text-slate-400 flex items-center gap-1">
              <ImageIcon className="w-3.5 h-3.5" />生成的素材会使用这些图片
            </span>
          )}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          multiple
          className="hidden"
          onChange={e => void handleUpload(e.target.files)}
        />
      </div>

      <div className="flex justify-end">
        <button
          className="btn-ios-primary"
          onClick={handleSubmit}
          disabled={submitting || running || configs.length === 0}
        >
          {submitting
            ? <><Loader2 className="w-4 h-4 animate-spin" />提交中...</>
            : running
              ? <><Loader2 className="w-4 h-4 animate-spin" />任务进行中...</>
              : <><Sparkles className="w-4 h-4" />开始生成</>}
        </button>
      </div>
    </div>
  )
}

export default AiListingTaskPanel





