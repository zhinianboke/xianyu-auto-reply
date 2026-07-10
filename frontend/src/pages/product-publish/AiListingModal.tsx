import React, { useEffect, useRef, useState } from 'react'
import { Bot, Loader2, Pencil, Plus, Save, Search, Trash2, Upload, X } from 'lucide-react'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { useUIStore } from '@/store/uiStore'
import {
  createAiListingConfig,
  deleteAiListingConfig,
  getAiListingConfigs,
  startAiListingGeneration,
  updateAiListingConfig,
  uploadProductImages,
  type AiListingConfig,
  type AiListingConfigParams,
  type ProductDeliveryMethod,
} from '@/api/productPublish'

const CONDITIONS = ['全新', '99新', '95新', '9成新', '8成新', '7成新以下']
const CATEGORIES = ['数码家电', '服饰鞋包', '家居日用', '图书音像', '美妆个护', '母婴用品', '运动户外', '食品生鲜', '虚拟商品', '其他']

const defaultForm: AiListingConfigParams = {
  name: '',
  prompt: '',
  reference_text: '',
  price_mode: 'fixed',
  fixed_price: null,
  price_min: null,
  price_max: null,
  text_api_url: 'https://api.openai.com/v1',
  text_api_key: '',
  text_model: '',
  image_mode: 'random',
  image_api_url: 'https://api.openai.com/v1',
  image_api_key: '',
  image_model: '',
  image_prompt: '',
  image_polish_enabled: false,
  image_polish_sequential: false,
  random_images: [],
  random_image_count: 1,
  material_defaults: {
    category: '',
    condition: '全新',
    brand: '',
    delivery_method: 'free_shipping',
    support_pickup: false,
    postage: 0,
    address: '',
    remark: '',
  },
}

interface Props {
  onClose: () => void
  onTaskStarted: (taskId: string, total: number, configId: number, configName: string) => void
}

export function AiListingModal({ onClose, onTaskStarted }: Props) {
  const { addToast } = useUIStore()
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [configs, setConfigs] = useState<AiListingConfig[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [form, setForm] = useState<AiListingConfigParams>(defaultForm)
  const [searchText, setSearchText] = useState('')
  const [draftMode, setDraftMode] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [generateCount, setGenerateCount] = useState(1)
  const [concurrency, setConcurrency] = useState(1)
  const [starting, setStarting] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<AiListingConfig | null>(null)

  const selectedConfig = configs.find(item => item.id === selectedId) || null
  const hasSelection = draftMode || Boolean(selectedConfig)
  const isEditing = draftMode || (selectedId !== null && editingId === selectedId)
  const canStart = Boolean(selectedId && selectedConfig && !isEditing)
  const forceImagePolish = form.image_mode === 'ai' && form.random_image_count > 1
  const effectiveImagePolishEnabled = forceImagePolish || Boolean(form.image_polish_enabled)
  const filteredConfigs = configs.filter(item =>
    item.name.toLowerCase().includes(searchText.trim().toLowerCase())
  )

  const loadConfigs = async () => {
    setLoading(true)
    try {
      const res = await getAiListingConfigs()
      if (res.success && res.data) {
        setConfigs(res.data)
        if (selectedId && !res.data.some(item => item.id === selectedId)) {
          setSelectedId(null)
          setEditingId(null)
        }
      } else {
        addToast({ type: 'error', message: res.message || '加载配置失败' })
      }
    } catch {
      addToast({ type: 'error', message: '加载配置失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadConfigs() }, [])

  const applyConfig = (config: AiListingConfig) => {
    setSelectedId(config.id)
    setDraftMode(false)
    setEditingId(null)
    setForm({
      name: config.name,
      prompt: config.prompt,
      reference_text: config.reference_text || '',
      price_mode: config.price_mode,
      fixed_price: config.fixed_price ?? null,
      price_min: config.price_min ?? null,
      price_max: config.price_max ?? null,
      text_api_url: config.text_api_url,
      text_api_key: config.text_api_key,
      text_model: config.text_model,
      image_mode: config.image_mode,
      image_api_url: config.image_api_url || 'https://api.openai.com/v1',
      image_api_key: config.image_api_key || '',
      image_model: config.image_model || '',
      image_prompt: config.image_prompt || '',
      image_polish_enabled: Boolean(config.image_polish_enabled) || (config.image_mode === 'ai' && (config.random_image_count || 1) > 1),
      image_polish_sequential: Boolean(config.image_polish_sequential),
      random_images: config.random_images || [],
      random_image_count: config.random_image_count || 1,
      material_defaults: {
        ...defaultForm.material_defaults,
        ...(config.material_defaults || {}),
      },
    })
  }

  const createNew = () => {
    setSelectedId(null)
    setDraftMode(true)
    setEditingId(null)
    setForm({
      ...defaultForm,
      material_defaults: { ...defaultForm.material_defaults },
    })
  }

  const startEdit = (config: AiListingConfig) => {
    applyConfig(config)
    setEditingId(config.id)
  }

  const updateDefaults = (patch: Partial<AiListingConfigParams['material_defaults']>) => {
    setForm(prev => ({ ...prev, material_defaults: { ...prev.material_defaults, ...patch } }))
  }

  const validateForm = () => {
    if (!form.name.trim()) return '请填写配置名称'
    if (!form.prompt.trim()) return '请填写商品生成提示词'
    if (!form.text_api_url.trim() || !form.text_api_key.trim() || !form.text_model.trim()) return '请填写文案AI配置'
    if (form.price_mode === 'fixed' && (!form.fixed_price || form.fixed_price <= 0)) return '请填写有效固定价格'
    if (form.price_mode === 'range') {
      if (!form.price_min || !form.price_max || form.price_min <= 0 || form.price_max <= 0) return '请填写有效价格范围'
      if (form.price_max < form.price_min) return '最高价格不能小于最低价格'
    }
    if (form.image_mode === 'random') {
      if (form.random_images.length === 0) return '请先上传随机图库'
      if (form.random_image_count > form.random_images.length) return '随机选图数量不能大于图库数量'
      if (form.random_image_count > 9) return '每个素材最多选择9张图片'
    }
    if (form.image_mode === 'ai' && (!form.image_api_url?.trim() || !form.image_api_key?.trim() || !form.image_model?.trim())) {
      return '请填写图片AI配置'
    }
    if (form.image_mode === 'ai' && !(form.image_prompt || '').trim()) {
      return '请填写图片提示词'
    }
    if (form.image_mode === 'ai' && forceImagePolish && !effectiveImagePolishEnabled) {
      return 'AI多图生成必须开启图片提示词AI润色'
    }
    if (form.image_mode === 'ai' && form.image_polish_sequential && !effectiveImagePolishEnabled) {
      return '多图保持关联需要先开启图片提示词AI润色'
    }
    return ''
  }

  const handleSave = async () => {
    const error = validateForm()
    if (error) { addToast({ type: 'warning', message: error }); return }
    setSaving(true)
    try {
      const payload = {
        ...form,
        image_polish_enabled: effectiveImagePolishEnabled,
        random_image_count: Math.max(1, Math.min(Number(form.random_image_count || 1), 9)),
        material_defaults: {
          ...form.material_defaults,
          postage: form.material_defaults.delivery_method === 'fixed_fee' ? Number(form.material_defaults.postage || 0) : 0,
        },
      }
      const res = selectedId
        ? await updateAiListingConfig(selectedId, payload)
        : await createAiListingConfig(payload)
      if (!res.success || !res.data) {
        addToast({ type: 'error', message: res.message || '保存配置失败' })
        return
      }
      addToast({ type: 'success', message: selectedId ? '配置已保存' : '配置已创建' })
      await loadConfigs()
      applyConfig(res.data)
    } catch {
      addToast({ type: 'error', message: '保存配置失败' })
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteConfig = async (config: AiListingConfig) => {
    setDeleteTarget(config)
  }

  const confirmDeleteConfig = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      const res = await deleteAiListingConfig(deleteTarget.id)
      if (res.success) {
        addToast({ type: 'success', message: '配置已删除' })
        if (selectedId === deleteTarget.id) {
          setSelectedId(null)
          setEditingId(null)
          setDraftMode(false)
          setForm(defaultForm)
        }
        setDeleteTarget(null)
        await loadConfigs()
      } else {
        addToast({ type: 'error', message: res.message || '删除配置失败' })
      }
    } catch {
      addToast({ type: 'error', message: '删除配置失败' })
    } finally {
      setDeleting(false)
    }
  }

  const handleUploadImages = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!isEditing) return
    const files = Array.from(e.target.files || [])
    if (!files.length) return
    setUploading(true)
    try {
      const urls: string[] = []
      for (let index = 0; index < files.length; index += 9) {
        const batch = files.slice(index, index + 9)
        const res = await uploadProductImages(batch)
        if (res.success && res.data) {
          urls.push(...res.data.urls)
        } else {
          addToast({ type: 'error', message: res.message || '上传失败' })
          return
        }
      }
      setForm(prev => ({ ...prev, random_images: [...prev.random_images, ...urls] }))
    } catch {
      addToast({ type: 'error', message: '图片上传失败' })
    } finally {
      setUploading(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  const removeRandomImage = (index: number) => {
    if (!isEditing) return
    setForm(prev => ({ ...prev, random_images: prev.random_images.filter((_, i) => i !== index) }))
  }

  const startGenerate = async () => {
    if (!selectedId || !selectedConfig) { addToast({ type: 'warning', message: '请先选择已保存的配置' }); return }
    if (isEditing) { addToast({ type: 'warning', message: '请先保存配置再开始铺货' }); return }
    setStarting(true)
    try {
      const res = await startAiListingGeneration(selectedId, generateCount, concurrency)
      if (res.success && res.data) {
        addToast({ type: 'success', message: 'AI铺货任务已在后台开始' })
        onTaskStarted(res.data.task_id, res.data.total, selectedId, selectedConfig.name)
        onClose()
      } else {
        addToast({ type: 'error', message: res.message || '启动任务失败' })
      }
    } catch {
      addToast({ type: 'error', message: '启动任务失败' })
    } finally {
      setStarting(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content max-w-6xl h-[90vh] max-h-[90vh] flex flex-col">
        <div className="modal-header">
          <h2 className="modal-title flex items-center gap-2"><Bot className="w-5 h-5" />AI铺货</h2>
          <button className="modal-close" onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <div className="modal-body flex-1 overflow-hidden min-h-0">
          <div className="grid grid-cols-1 lg:grid-cols-[300px_1fr] gap-4 h-full min-h-0">
            <div className="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden flex flex-col min-h-0">
              <div className="p-3 border-b border-slate-200 dark:border-slate-700 flex items-center justify-between">
                <span className="font-medium text-slate-700 dark:text-slate-200">铺货配置列表</span>
                <button className="btn-ios-secondary btn-sm" onClick={createNew}><Plus className="w-3.5 h-3.5" />新增</button>
              </div>
              <div className="p-2 border-b border-slate-200 dark:border-slate-700">
                <div className="relative">
                  <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                  <input
                    className="input-ios pl-9"
                    placeholder="搜索配置"
                    value={searchText}
                    onChange={e => setSearchText(e.target.value)}
                  />
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-2 space-y-1">
                {loading ? (
                  <div className="py-8 text-center text-slate-400"><Loader2 className="w-5 h-5 animate-spin mx-auto" /></div>
                ) : configs.length === 0 && !draftMode ? (
                  <div className="py-8 text-center text-sm text-slate-400">暂无配置</div>
                ) : (
                  <>
                    {draftMode && (
                      <div className="flex items-center gap-2 px-2 py-2 rounded-md bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-200">
                        <input type="radio" checked readOnly className="w-4 h-4" />
                        <button className="flex-1 text-left min-w-0" onClick={createNew}>
                          <span className="block truncate text-sm">{form.name || '未保存配置'}</span>
                          <span className="block text-xs text-slate-400 mt-0.5">编辑中</span>
                        </button>
                        <button className="table-action-btn" title="保存" onClick={handleSave} disabled={saving}>
                          {saving ? <Loader2 className="w-4 h-4 animate-spin text-blue-500" /> : <Save className="w-4 h-4 text-blue-500" />}
                        </button>
                        <button className="table-action-btn" title="删除" onClick={() => { setDraftMode(false); setForm(defaultForm) }}>
                          <Trash2 className="w-4 h-4 text-red-500" />
                        </button>
                      </div>
                    )}
                    {filteredConfigs.map(config => {
                      const active = selectedId === config.id && !draftMode
                      const editing = editingId === config.id && !draftMode
                      return (
                        <div
                          key={config.id}
                          onClick={() => applyConfig(config)}
                          className={`flex items-center gap-2 px-2 py-2 rounded-md transition-colors ${
                            active
                              ? 'bg-blue-50 text-blue-700 dark:bg-blue-900/30 dark:text-blue-200'
                              : 'hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200'
                          }`}
                        >
                          <input type="radio" checked={active} readOnly className="w-4 h-4" />
                          <button className="flex-1 text-left min-w-0" onClick={() => applyConfig(config)}>
                            <span className="block truncate text-sm">{config.name}</span>
                            <span className="block text-xs text-slate-400 mt-0.5">{config.image_mode === 'ai' ? 'AI生成图片' : '随机选图'}</span>
                          </button>
                          <button
                            className="table-action-btn"
                            title={editing ? '保存' : '编辑'}
                            onClick={e => {
                              e.stopPropagation()
                              if (editing) {
                                handleSave()
                              } else {
                                startEdit(config)
                              }
                            }}
                            disabled={saving}
                          >
                            {editing && saving ? <Loader2 className="w-4 h-4 animate-spin text-blue-500" /> : editing ? <Save className="w-4 h-4 text-blue-500" /> : <Pencil className="w-4 h-4 text-blue-500" />}
                          </button>
                          <button
                            className="table-action-btn"
                            title="删除"
                            onClick={e => {
                              e.stopPropagation()
                              handleDeleteConfig(config)
                            }}
                          >
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </button>
                        </div>
                      )
                    })}
                  </>
                )}
              </div>
            </div>

            <div className="overflow-y-auto pr-1 min-h-0">
              {!hasSelection ? (
                <div className="h-full flex flex-col items-center justify-center text-center text-slate-500 dark:text-slate-400">
                  <div className="w-14 h-14 rounded-lg bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center mb-3">
                    <Bot className="w-7 h-7 text-blue-500" />
                  </div>
                  <div className="text-base font-medium text-slate-700 dark:text-slate-200">请在配置列表添加并填写铺货配置</div>
                  <div className="text-sm mt-1">保存配置后即可在底部开始 AI 铺货</div>
                </div>
              ) : (
              <div className="space-y-5">
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="input-group">
                    <label className="input-label">配置名称</label>
                    <input className="input-ios" disabled={!isEditing} value={form.name} onChange={e => setForm(f => ({ ...f, name: e.target.value }))} />
                  </div>
                  <div className="input-group">
                    <label className="input-label">文案模型</label>
                    <input className="input-ios" disabled={!isEditing} placeholder="如：gpt-4o-mini" value={form.text_model} onChange={e => setForm(f => ({ ...f, text_model: e.target.value }))} />
                  </div>
                  <div className="input-group">
                    <label className="input-label">文案 API URL</label>
                    <input
                      className="input-ios"
                      disabled={!isEditing}
                      placeholder="如：https://api.openai.com/v1 或 https://example.com/v2"
                      value={form.text_api_url}
                      onChange={e => setForm(f => ({ ...f, text_api_url: e.target.value }))}
                    />
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                      填写到 /vx 为止即可，例如 https://api.openai.com/v1，如未填写版本号会自动补为 /v1，末尾不要加 /
                    </p>
                  </div>
                  <div className="input-group">
                    <label className="input-label">文案 API Key</label>
                    <input className="input-ios" disabled={!isEditing} type="password" value={form.text_api_key} onChange={e => setForm(f => ({ ...f, text_api_key: e.target.value }))} />
                  </div>
                  <div className="input-group md:col-span-2">
                    <label className="input-label">商品生成提示词</label>
                    <textarea className="input-ios" disabled={!isEditing} rows={3} value={form.prompt} onChange={e => setForm(f => ({ ...f, prompt: e.target.value }))} />
                  </div>
                  <div className="input-group md:col-span-2">
                    <label className="input-label">参考文案</label>
                    <textarea className="input-ios" disabled={!isEditing} rows={3} value={form.reference_text || ''} onChange={e => setForm(f => ({ ...f, reference_text: e.target.value }))} />
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="input-group">
                    <label className="input-label">价格模式</label>
                    <select className="input-ios" disabled={!isEditing} value={form.price_mode} onChange={e => setForm(f => ({ ...f, price_mode: e.target.value as 'fixed' | 'range' }))}>
                      <option value="fixed">固定价格</option>
                      <option value="range">范围随机</option>
                    </select>
                  </div>
                  {form.price_mode === 'fixed' ? (
                    <div className="input-group">
                      <label className="input-label">固定价格</label>
                      <input type="number" className="input-ios" disabled={!isEditing} min="0" step="0.01" value={form.fixed_price || ''} onChange={e => setForm(f => ({ ...f, fixed_price: parseFloat(e.target.value) || null }))} />
                    </div>
                  ) : (
                    <>
                      <div className="input-group">
                        <label className="input-label">最低价格</label>
                        <input type="number" className="input-ios" disabled={!isEditing} min="0" step="0.01" value={form.price_min || ''} onChange={e => setForm(f => ({ ...f, price_min: parseFloat(e.target.value) || null }))} />
                      </div>
                      <div className="input-group">
                        <label className="input-label">最高价格</label>
                        <input type="number" className="input-ios" disabled={!isEditing} min="0" step="0.01" value={form.price_max || ''} onChange={e => setForm(f => ({ ...f, price_max: parseFloat(e.target.value) || null }))} />
                      </div>
                    </>
                  )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="input-group">
                    <label className="input-label">图片模式</label>
                    <select className="input-ios" disabled={!isEditing} value={form.image_mode} onChange={e => setForm(f => ({ ...f, image_mode: e.target.value as 'ai' | 'random' }))}>
                      <option value="random">随机选图</option>
                      <option value="ai">AI生成</option>
                    </select>
                  </div>
                  <div className="input-group">
                    <label className="input-label">每个素材图片数量</label>
                    <input
                      type="number"
                      className="input-ios"
                      disabled={!isEditing}
                      min="1"
                      max="9"
                      value={form.random_image_count}
                      onChange={e => setForm(f => {
                        const nextCount = parseInt(e.target.value) || 1
                        const shouldForce = f.image_mode === 'ai' && nextCount > 1
                        return {
                          ...f,
                          random_image_count: nextCount,
                          image_polish_enabled: shouldForce ? true : f.image_polish_enabled,
                        }
                      })}
                    />
                    {form.image_mode === 'random' ? (
                      <p className="text-xs text-slate-500 mt-1">当选图数量等于图库总数时，每个商品会使用同一组图片</p>
                    ) : (
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">AI生成时最多支持 9 张图，数量大于 1 时会强制开启图片提示词AI润色</p>
                    )}
                  </div>
                  {form.image_mode === 'ai' ? (
                    <>
                      <div className="input-group">
                        <label className="input-label">图片 API URL</label>
                        <input
                          className="input-ios"
                          disabled={!isEditing}
                          placeholder="如：https://api.openai.com/v1 或 https://example.com/v2"
                          value={form.image_api_url || ''}
                          onChange={e => setForm(f => ({ ...f, image_api_url: e.target.value }))}
                        />
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                          填写到 /vx 为止即可，例如 https://api.openai.com/v1，如未填写版本号会自动补为 /v1，末尾不要加 /
                        </p>
                      </div>
                      <div className="input-group">
                        <label className="input-label">图片 API Key</label>
                        <input type="password" className="input-ios" disabled={!isEditing} value={form.image_api_key || ''} onChange={e => setForm(f => ({ ...f, image_api_key: e.target.value }))} />
                      </div>
                      <div className="input-group">
                        <label className="input-label">图片模型</label>
                        <input className="input-ios" disabled={!isEditing} value={form.image_model || ''} onChange={e => setForm(f => ({ ...f, image_model: e.target.value }))} />
                      </div>
                      <div className="input-group md:col-span-2">
                        <label className="input-label">图片提示词</label>
                        <textarea
                          className="input-ios"
                          disabled={!isEditing}
                          rows={4}
                          placeholder="可使用 {title} {description} {price}"
                          value={form.image_prompt || ''}
                          onChange={e => setForm(f => ({ ...f, image_prompt: e.target.value }))}
                        />
                        <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                          只有你主动填写的变量才会注入到提示词中，可用变量有 {'{title}'} {'{description}'} {'{price}'}
                        </p>
                      </div>
                      <div className="input-group rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2">
                        <label className="input-label">图片提示词AI润色</label>
                        <label className="switch-ios mt-2">
                          <input
                            type="checkbox"
                            disabled={!isEditing || forceImagePolish}
                            checked={effectiveImagePolishEnabled}
                            onChange={e => setForm(f => ({
                              ...f,
                              image_polish_enabled: e.target.checked,
                              image_polish_sequential: e.target.checked ? f.image_polish_sequential : false,
                            }))}
                          />
                          <span className="switch-slider"></span>
                        </label>
                        <p className={`text-xs mt-1 ${forceImagePolish ? 'text-blue-600 dark:text-blue-300' : 'text-slate-500 dark:text-slate-400'}`}>
                          {forceImagePolish
                            ? '当前为多图生成，图片提示词AI润色已自动开启，且会复用文案模型输出对应数量的提示词数组'
                            : '开启后会先将图片提示词润色为更稳定的生图文本'}
                        </p>
                      </div>
                      <div className="input-group rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2">
                        <label className="input-label">多图保持关联</label>
                        <label className="switch-ios mt-2">
                          <input
                            type="checkbox"
                            disabled={!isEditing || !effectiveImagePolishEnabled}
                            checked={Boolean(form.image_polish_sequential)}
                            onChange={e => setForm(f => ({ ...f, image_polish_sequential: e.target.checked }))}
                          />
                          <span className="switch-slider"></span>
                        </label>
                        <p
                          className={`text-xs mt-1 ${
                            effectiveImagePolishEnabled
                              ? 'text-slate-500 dark:text-slate-400'
                              : 'text-slate-400 dark:text-slate-500'
                          }`}
                        >
                          {effectiveImagePolishEnabled
                            ? '开启后多张商品图会共用同一主体设定，仅调整构图和展示角度'
                            : '请先开启图片提示词AI润色后再使用'}
                        </p>
                      </div>
                    </>
                  ) : (
                    <div className="input-group md:col-span-2">
                      <label className="input-label">随机图库</label>
                      <div className="flex flex-wrap gap-2">
                        {form.random_images.map((url, index) => (
                          <div key={`${url}-${index}`} className="relative w-16 h-16 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-600 group">
                            <img src={url} alt="" className="w-full h-full object-cover" />
                            {isEditing && (
                              <button type="button" onClick={() => removeRandomImage(index)} className="absolute top-0.5 right-0.5 bg-black/60 hover:bg-red-500 text-white rounded p-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                                <Trash2 className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                        ))}
                        {isEditing && (
                          <button type="button" className="w-16 h-16 border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-lg flex items-center justify-center text-slate-400 hover:border-blue-400 hover:text-blue-500" disabled={uploading} onClick={() => fileInputRef.current?.click()}>
                            {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}
                          </button>
                        )}
                      </div>
                      <input ref={fileInputRef} type="file" accept="image/*" multiple className="hidden" onChange={handleUploadImages} />
                    </div>
                  )}
                </div>

                <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                  <div className="input-group">
                    <label className="input-label">商品分类</label>
                    <select className="input-ios" disabled={!isEditing} value={form.material_defaults.category || ''} onChange={e => updateDefaults({ category: e.target.value })}>
                      <option value="">请选择分类</option>
                      {CATEGORIES.map(item => <option key={item} value={item}>{item}</option>)}
                    </select>
                  </div>
                  <div className="input-group">
                    <label className="input-label">成色</label>
                    <select className="input-ios" disabled={!isEditing} value={form.material_defaults.condition || '全新'} onChange={e => updateDefaults({ condition: e.target.value })}>
                      {CONDITIONS.map(item => <option key={item} value={item}>{item}</option>)}
                    </select>
                  </div>
                  <div className="input-group">
                    <label className="input-label">品牌</label>
                    <input className="input-ios" disabled={!isEditing} value={form.material_defaults.brand || ''} onChange={e => updateDefaults({ brand: e.target.value })} />
                  </div>
                  <div className="input-group">
                    <label className="input-label">发货方式</label>
                    <select className="input-ios" disabled={!isEditing} value={form.material_defaults.delivery_method || 'free_shipping'} onChange={e => updateDefaults({ delivery_method: e.target.value as ProductDeliveryMethod, postage: e.target.value === 'fixed_fee' ? form.material_defaults.postage : 0 })}>
                      <option value="free_shipping">包邮</option>
                      <option value="distance_billing">按距离计费</option>
                      <option value="fixed_fee">一口价</option>
                      <option value="no_shipping">无需邮寄</option>
                    </select>
                  </div>
                  {form.material_defaults.delivery_method === 'fixed_fee' && (
                    <div className="input-group">
                      <label className="input-label">运费</label>
                      <input type="number" className="input-ios" disabled={!isEditing} min="0" step="0.01" value={form.material_defaults.postage || ''} onChange={e => updateDefaults({ postage: parseFloat(e.target.value) || 0 })} />
                    </div>
                  )}
                  <div className="input-group">
                    <label className="input-label">支持自提</label>
                    <label className="switch-ios mt-2">
                      <input type="checkbox" disabled={!isEditing} checked={Boolean(form.material_defaults.support_pickup)} onChange={e => updateDefaults({ support_pickup: e.target.checked })} />
                      <span className="switch-slider"></span>
                    </label>
                  </div>
                  <div className="input-group md:col-span-3">
                    <label className="input-label">宝贝所在地</label>
                    <input className="input-ios" disabled={!isEditing} value={form.material_defaults.address || ''} onChange={e => updateDefaults({ address: e.target.value })} />
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                      这里填写的地址仅做素材记录，实际发布时会自动从随机地址库分配宝贝所在地
                    </p>
                  </div>
                  <div className="input-group md:col-span-3">
                    <label className="input-label">备注</label>
                    <input className="input-ios" disabled={!isEditing} value={form.material_defaults.remark || ''} onChange={e => updateDefaults({ remark: e.target.value })} />
                  </div>
                </div>
              </div>
              )}
            </div>
          </div>
        </div>
        <div className="modal-footer items-end">
          <div className="flex-1 min-w-0">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-[180px_180px_1fr] gap-4 items-end">
              <div className="input-group">
                <label className="input-label">创建素材数量</label>
                <input type="number" min="1" max="200" className="input-ios" value={generateCount} onChange={e => setGenerateCount(Math.max(1, Math.min(parseInt(e.target.value) || 1, 200)))} />
              </div>
              <div className="input-group">
                <label className="input-label">并发创建数</label>
                <input type="number" min="1" max="10" className="input-ios" value={concurrency} onChange={e => setConcurrency(Math.max(1, Math.min(parseInt(e.target.value) || 1, 10)))} />
              </div>
              <div className="text-sm text-slate-500 pb-2">
                {selectedConfig ? '点击后将在后台生成，进度会显示在素材库页面' : '请选择已保存的配置'}
              </div>
            </div>
          </div>
          <button className="btn-ios-primary" onClick={startGenerate} disabled={!canStart || starting}>
            {starting && <Loader2 className="w-4 h-4 animate-spin" />}
            开始后台铺货
          </button>
        </div>
      </div>
      <ConfirmModal
        isOpen={Boolean(deleteTarget)}
        title="确认删除"
        message={deleteTarget ? `确认删除配置「${deleteTarget.name}」？` : ''}
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={confirmDeleteConfig}
        onCancel={() => {
          if (deleting) return
          setDeleteTarget(null)
        }}
      />
    </div>
  )
}

export default AiListingModal
