/**
 * 卡券编辑/复制弹窗组件
 * 
 * 功能：编辑卡券或复制卡券（预填数据，新建模式）
 * 参照商品管理中的发货配置编辑弹窗
 */
import { useState, useEffect } from 'react'
import type { FormEvent, ChangeEvent } from 'react'
import { X, Loader2, ImagePlus } from 'lucide-react'
import { updateCard, createCard, uploadCardImage, type CardData } from '@/api/cards'
import { useUIStore } from '@/store/uiStore'
import { Select } from '@/components/common/Select'
import { getSystemSettings } from '@/api/settings'

// 卡券类型选项
const cardTypeOptions = [
  { value: 'text', label: '固定文字' },
  { value: 'data', label: '批量数据' },
  { value: 'api', label: 'API接口' },
  { value: 'image', label: '图片' },
]

// 请求方法选项
const apiMethodOptions = [
  { value: 'GET', label: 'GET' },
  { value: 'POST', label: 'POST' },
]

// POST 请求可用参数
const postParams = [
  { name: 'order_id', desc: '订单编号' },
  { name: 'item_id', desc: '商品编号' },
  { name: 'item_detail', desc: '商品详情' },
  { name: 'order_amount', desc: '订单金额' },
  { name: 'order_quantity', desc: '订单数量' },
  { name: 'spec_name', desc: '规格名称' },
  { name: 'spec_value', desc: '规格值' },
  { name: 'cookie_id', desc: 'cookies账号id' },
  { name: 'buyer_id', desc: '买家id' },
]

// 卡券表单数据类型
interface CardFormData {
  name: string
  type: 'api' | 'text' | 'data' | 'image' | ''
  apiUrl: string
  apiMethod: 'GET' | 'POST'
  apiTimeout: number
  apiHeaders: string
  apiParams: string
  apiResponseField: string
  textContent: string
  dataContent: string
  imageUrls: string[]
  delaySeconds: number
  price: string
  isDockable: boolean
  feePayer: string
  minPrice: string
  dockVisibility: string
  description: string
  isMultiSpec: boolean
  specName: string
  specValue: string
}

interface CardFormModalProps {
  /** 编辑模式时传入卡券ID，复制/新建模式为null */
  cardId: number | null
  /** 初始表单数据 */
  initialData: CardFormData
  /** 关闭弹窗回调 */
  onClose: () => void
  /** 保存成功后回调 */
  onSaved: () => void
}

/** 从CardData生成表单初始数据（编辑模式） */
export function cardToFormData(card: CardData): CardFormData {
  let imageUrlsList: string[] = []
  if (card.image_urls && card.image_urls.length > 0) {
    imageUrlsList = card.image_urls
  } else if (card.image_url) {
    imageUrlsList = [card.image_url]
  }
  return {
    name: card.name || '',
    type: card.type || '',
    apiUrl: card.api_config?.url || '',
    apiMethod: (card.api_config?.method as 'GET' | 'POST') || 'GET',
    apiTimeout: card.api_config?.timeout || 60,
    apiHeaders: card.api_config?.headers || '',
    apiParams: card.api_config?.params || '',
    apiResponseField: card.api_config?.response_field || '',
    textContent: card.text_content || '',
    dataContent: card.data_content || '',
    imageUrls: imageUrlsList,
    delaySeconds: card.delay_seconds || 0,
    price: card.price || '',
    isDockable: card.is_dockable || false,
    feePayer: card.fee_payer || '',
    minPrice: card.min_price || '',
    dockVisibility: card.dock_visibility || 'public',
    description: card.description || '',
    isMultiSpec: card.is_multi_spec || false,
    specName: card.spec_name || '',
    specValue: card.spec_value || '',
  }
}

/** 从CardData生成表单初始数据（复制模式，名称为空） */
export function cardToCopyFormData(card: CardData): CardFormData {
  const data = cardToFormData(card)
  data.name = ''
  return data
}

/** 空表单初始数据 */
export const emptyCardFormData: CardFormData = {
  name: '',
  type: 'text',
  apiUrl: '',
  apiMethod: 'GET',
  apiTimeout: 60,
  apiHeaders: '',
  apiParams: '',
  apiResponseField: '',
  textContent: '',
  dataContent: '',
  imageUrls: [],
  delaySeconds: 0,
  price: '',
  isDockable: false,
  feePayer: '',
  minPrice: '',
  dockVisibility: 'public',
  description: '',
  isMultiSpec: false,
  specName: '',
  specValue: '',
}

export function CardFormModal({ cardId, initialData, onClose, onSaved }: CardFormModalProps) {
  const { addToast } = useUIStore()
  const [formData, setFormData] = useState<CardFormData>(initialData)
  const [saving, setSaving] = useState(false)
  const [feeRate, setFeeRate] = useState('')
  const [feeType, setFeeType] = useState('fixed')

  // 获取系统设置中的分销手续费
  useEffect(() => {
    getSystemSettings().then(res => {
      if (res.success && res.data) {
        setFeeRate(res.data['distribution.fee_rate'] as string || '0')
        setFeeType(res.data['distribution.fee_type'] as string || 'fixed')
      }
    })
  }, [])

  const isEditMode = cardId !== null

  // 更新表单字段
  const updateField = <K extends keyof CardFormData>(field: K, value: CardFormData[K]) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  // 插入POST参数
  const insertParam = (paramName: string) => {
    const currentParams = formData.apiParams.trim()
    let jsonObj: Record<string, string> = {}
    if (currentParams && currentParams !== '{}') {
      try {
        jsonObj = JSON.parse(currentParams)
      } catch {
        // 解析失败，使用空对象
      }
    }
    jsonObj[paramName] = `{${paramName}}`
    updateField('apiParams', JSON.stringify(jsonObj, null, 2))
    addToast({ type: 'success', message: `已添加参数 ${paramName}` })
  }

  // 验证表单
  const validateForm = (): boolean => {
    if (!formData.name.trim()) {
      addToast({ type: 'warning', message: '请输入卡券名称' })
      return false
    }
    if (!formData.type) {
      addToast({ type: 'warning', message: '请选择卡券类型' })
      return false
    }
    if (formData.type === 'api' && !formData.apiUrl.trim()) {
      addToast({ type: 'warning', message: '请输入API地址' })
      return false
    }
    if (formData.type === 'text' && !formData.textContent.trim()) {
      addToast({ type: 'warning', message: '请输入固定文字内容' })
      return false
    }
    if (formData.type === 'data' && !formData.dataContent.trim()) {
      addToast({ type: 'warning', message: '请输入批量数据' })
      return false
    }
    if (formData.isMultiSpec && (!formData.specName.trim() || !formData.specValue.trim())) {
      addToast({ type: 'warning', message: '多规格卡券必须填写规格名称和规格值' })
      return false
    }
    // 对接价格校验
    if (formData.isDockable) {
      if (!formData.price.trim()) {
        addToast({ type: 'warning', message: '勾选可对接时，对接价格必填' })
        return false
      }
      if (!formData.feePayer) {
        addToast({ type: 'warning', message: '勾选可对接时，手续费支付方式必选' })
        return false
      }
      if (!formData.dockVisibility) {
        addToast({ type: 'warning', message: '勾选可对接时，对接类型必选' })
        return false
      }
    }
    if (formData.price.trim()) {
      const priceVal = Number(formData.price.trim())
      if (isNaN(priceVal) || priceVal <= 0) {
        addToast({ type: 'warning', message: '对接价格必须是大于0的数字' })
        return false
      }
      if (!/^\d+(\.\d{1,2})?$/.test(formData.price.trim())) {
        addToast({ type: 'warning', message: '对接价格最多保留两位小数' })
        return false
      }
    }
    // 最低售价校验（可为空，有值时必须大于0、最多2位小数）
    if (formData.minPrice.trim()) {
      const minPriceVal = Number(formData.minPrice.trim())
      if (isNaN(minPriceVal) || minPriceVal <= 0) {
        addToast({ type: 'warning', message: '最低售价必须是大于0的数字' })
        return false
      }
      if (!/^\d+(\.\d{1,2})?$/.test(formData.minPrice.trim())) {
        addToast({ type: 'warning', message: '最低售价最多保留两位小数' })
        return false
      }
    }
    // 非图片类型卡券填写备注时，{DELIVERY_CONTENT} 为必填变量，其他变量可选
    if (formData.type !== 'image' && formData.description.trim()) {
      if (!formData.description.includes('{DELIVERY_CONTENT}')) {
        addToast({ type: 'warning', message: '非图片类型卡券的备注中必须包含 {DELIVERY_CONTENT} 变量' })
        return false
      }
    }
    if (formData.apiHeaders.trim()) {
      try { JSON.parse(formData.apiHeaders) } catch {
        addToast({ type: 'warning', message: '请求头格式错误，请输入有效的JSON' })
        return false
      }
    }
    if (formData.apiParams.trim()) {
      try { JSON.parse(formData.apiParams) } catch {
        addToast({ type: 'warning', message: '请求参数格式错误，请输入有效的JSON' })
        return false
      }
    }
    return true
  }

  // 提交表单
  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!validateForm()) return

    setSaving(true)
    try {
      const cardData: Partial<CardData> = {
        name: formData.name.trim(),
        type: formData.type as 'api' | 'text' | 'data' | 'image',
        description: formData.description.trim() || undefined,
        enabled: true,
        delay_seconds: formData.delaySeconds,
        price: formData.price.trim() || null,
        is_dockable: formData.isDockable,
        fee_payer: formData.isDockable ? formData.feePayer : null,
        min_price: formData.isDockable ? (formData.minPrice.trim() || null) : null,
        dock_visibility: formData.isDockable ? formData.dockVisibility : null,
        is_multi_spec: formData.isMultiSpec,
        spec_name: formData.isMultiSpec ? formData.specName.trim() : undefined,
        spec_value: formData.isMultiSpec ? formData.specValue.trim() : undefined,
      }

      if (formData.type === 'api') {
        cardData.api_config = {
          url: formData.apiUrl.trim(),
          method: formData.apiMethod,
          timeout: formData.apiTimeout,
          headers: formData.apiHeaders.trim() || undefined,
          params: formData.apiParams.trim() || undefined,
          response_field: formData.apiResponseField.trim() || undefined,
        }
      } else if (formData.type === 'text') {
        cardData.text_content = formData.textContent.trim()
      } else if (formData.type === 'data') {
        cardData.data_content = formData.dataContent.trim()
      }

      if (formData.imageUrls.length > 0) {
        cardData.image_urls = formData.imageUrls
      }

      if (isEditMode) {
        await updateCard(String(cardId), cardData)
        addToast({ type: 'success', message: '卡券更新成功' })
      } else {
        await createCard(cardData as Parameters<typeof createCard>[0])
        addToast({ type: 'success', message: '卡券创建成功' })
      }

      onSaved()
      onClose()
    } catch {
      addToast({ type: 'error', message: isEditMode ? '更新卡券失败' : '创建卡券失败' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" style={{ zIndex: 60 }}>
      <div className="modal-content max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="modal-header flex items-center justify-between sticky top-0 bg-white dark:bg-gray-900 z-10">
          <h2 className="text-lg font-semibold">{isEditMode ? '编辑卡券' : '新建卡券'}</h2>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg">
            <X className="w-4 h-4 text-gray-500" />
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body space-y-4">
            {/* 基本信息 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="input-label">卡券名称 <span className="text-red-500">*</span></label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => updateField('name', e.target.value)}
                  className="input-ios"
                  placeholder="例如：游戏点卡、会员卡等"
                />
              </div>
              <div>
                <label className="input-label">卡券类型 <span className="text-red-500">*</span></label>
                <Select
                  value={formData.type}
                  onChange={(v) => updateField('type', v as CardFormData['type'])}
                  options={cardTypeOptions}
                />
              </div>
            </div>

            {/* API 配置 */}
            {formData.type === 'api' && (
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 space-y-4">
                <h3 className="font-medium text-gray-900 dark:text-white">API配置</h3>
                <div>
                  <label className="input-label">API地址</label>
                  <input
                    type="url"
                    value={formData.apiUrl}
                    onChange={(e) => updateField('apiUrl', e.target.value)}
                    className="input-ios"
                    placeholder="https://api.example.com/get-card"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="input-label">请求方法</label>
                    <Select
                      value={formData.apiMethod}
                      onChange={(v) => updateField('apiMethod', v as 'GET' | 'POST')}
                      options={apiMethodOptions}
                    />
                  </div>
                  <div>
                    <label className="input-label">超时时间(秒)</label>
                    <input
                      type="number"
                      value={formData.apiTimeout}
                      onChange={(e) => updateField('apiTimeout', parseInt(e.target.value) || 60)}
                      className="input-ios"
                      min={1}
                    />
                  </div>
                </div>
                <div>
                  <label className="input-label">请求头 (JSON格式)</label>
                  <textarea
                    value={formData.apiHeaders}
                    onChange={(e) => updateField('apiHeaders', e.target.value)}
                    className="input-ios h-20 font-mono text-sm"
                    placeholder='{"Authorization": "Bearer token"}'
                  />
                </div>
                <div>
                  <label className="input-label">请求参数 (JSON格式)</label>
                  <textarea
                    value={formData.apiParams}
                    onChange={(e) => updateField('apiParams', e.target.value)}
                    className="input-ios h-20 font-mono text-sm"
                    placeholder='{"type": "card", "count": 1}'
                  />
                  {formData.apiMethod === 'POST' && (
                    <div className="mt-2 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                      <p className="text-sm text-blue-600 dark:text-blue-400 mb-2 font-medium">POST请求可用参数（点击添加）：</p>
                      <div className="flex flex-wrap gap-2">
                        {postParams.map(p => (
                          <button
                            key={p.name}
                            type="button"
                            onClick={() => insertParam(p.name)}
                            className="px-2 py-1 bg-white dark:bg-gray-800 border border-blue-200 dark:border-blue-800 rounded text-xs hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
                            title={p.desc}
                          >
                            <code>{p.name}</code>
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
                <div>
                  <label className="input-label">响应取值字段（选填）</label>
                  <input
                    type="text"
                    value={formData.apiResponseField}
                    onChange={(e) => updateField('apiResponseField', e.target.value)}
                    className="input-ios"
                    placeholder="data.cards[0].key"
                  />
                  <div className="text-xs text-slate-500 dark:text-slate-400 mt-1 space-y-1 leading-relaxed">
                    <p>当卡密藏在 JSON 的某一层里时，填写路径精确取出该值。</p>
                    <p>
                      写法：用点号进入对象、用中括号取数组下标，例如
                      <code className="mx-1 px-1 rounded bg-slate-100 dark:bg-slate-700">data.cards[0].key</code>、
                      <code className="mx-1 px-1 rounded bg-slate-100 dark:bg-slate-700">result.card</code>。
                      数组下标只能用 <code className="px-1 rounded bg-slate-100 dark:bg-slate-700">[0]</code>，区分大小写。
                    </p>
                    <p>
                      <span className="text-amber-600 dark:text-amber-400 font-medium">以下情况请留空：</span>
                      接口直接返回纯文本卡密、或想要整个返回内容。留空时会自动按
                      <code className="mx-1 px-1 rounded bg-slate-100 dark:bg-slate-700">data → content → card</code>
                      取值，取不到则返回整个内容。
                    </p>
                    <p className="text-amber-600 dark:text-amber-400">
                      注意：接口返回纯文本时若填写本字段，会因无法解析而取值失败，请务必留空。
                    </p>
                  </div>
                </div>
              </div>
            )}

            {/* 固定文字配置 */}
            {formData.type === 'text' && (
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <h3 className="font-medium text-gray-900 dark:text-white mb-3">固定文字配置</h3>
                <div>
                  <label className="input-label">固定文字内容</label>
                  <textarea
                    value={formData.textContent}
                    onChange={(e) => updateField('textContent', e.target.value)}
                    className="input-ios h-32"
                    placeholder="请输入要发送的固定文字内容..."
                  />
                </div>
              </div>
            )}

            {/* 批量数据配置 */}
            {formData.type === 'data' && (
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <h3 className="font-medium text-gray-900 dark:text-white mb-3">批量数据配置</h3>
                <div>
                  <label className="input-label">数据内容 (一行一个)</label>
                  <textarea
                    value={formData.dataContent}
                    onChange={(e) => updateField('dataContent', e.target.value)}
                    className="input-ios h-40 font-mono text-sm"
                    placeholder="请输入数据，每行一个：&#10;卡号1:密码1&#10;卡号2:密码2&#10;或者&#10;兑换码1&#10;兑换码2"
                  />
                  <p className="text-xs text-gray-500 mt-1">支持格式：卡号:密码 或 单独的兑换码</p>
                </div>
              </div>
            )}

            {/* 图片配置 */}
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
              <h3 className="font-medium text-gray-900 dark:text-white mb-3">图片配置（可选，最多3张）</h3>
              <div className="space-y-4">
                <div className="flex flex-wrap gap-3">
                  {formData.imageUrls.map((url, index) => (
                    <div key={index} className="relative group">
                      <img
                        src={url}
                        alt={`图片${index + 1}`}
                        className="w-24 h-24 object-cover rounded-lg border border-gray-200 dark:border-gray-700"
                      />
                      <button
                        type="button"
                        onClick={() => {
                          const newUrls = [...formData.imageUrls]
                          newUrls.splice(index, 1)
                          updateField('imageUrls', newUrls)
                        }}
                        className="absolute -top-2 -right-2 w-6 h-6 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600 opacity-0 group-hover:opacity-100 transition-opacity"
                      >
                        <X className="w-3 h-3" />
                      </button>
                      <span className="absolute bottom-1 left-1 bg-black/50 text-white text-xs px-1 rounded">
                        {index + 1}
                      </span>
                    </div>
                  ))}
                  {formData.imageUrls.length < 3 && (
                    <label className="w-24 h-24 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg flex flex-col items-center justify-center cursor-pointer hover:border-blue-500 dark:hover:border-blue-400 transition-colors">
                      <input
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={async (e: ChangeEvent<HTMLInputElement>) => {
                          const file = e.target.files?.[0]
                          if (!file) return
                          if (file.size > 5 * 1024 * 1024) {
                            addToast({ type: 'error', message: '图片大小不能超过5MB' })
                            return
                          }
                          try {
                            const result = await uploadCardImage(file)
                            if (result.success && result.image_url) {
                              const newUrls = [...formData.imageUrls, result.image_url]
                              updateField('imageUrls', newUrls)
                              addToast({ type: 'success', message: '图片上传成功' })
                            } else {
                              addToast({ type: 'error', message: result.message || '图片上传失败' })
                            }
                          } catch {
                            addToast({ type: 'error', message: '图片上传失败' })
                          }
                          e.target.value = ''
                        }}
                      />
                      <ImagePlus className="w-6 h-6 text-gray-400" />
                      <span className="text-xs text-gray-400 mt-1">添加图片</span>
                    </label>
                  )}
                </div>
                <p className="text-xs text-gray-500">支持JPG、PNG、GIF格式，最大5MB，最多上传3张图片（可选）</p>
              </div>
            </div>

            {/* 对接信息 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="input-label">
                  对接价格 {formData.isDockable && <span className="text-red-500">*</span>}
                </label>
                <input
                  type="text"
                  value={formData.price}
                  onChange={(e) => {
                    const val = e.target.value
                    // 只允许输入数字和小数点，最多2位小数
                    if (val === '' || /^\d*\.?\d{0,2}$/.test(val)) {
                      updateField('price', val)
                    }
                  }}
                  className="input-ios"
                  placeholder="例如：9.90"
                />
              </div>
              <div className="flex items-end">
                <label className="flex items-center gap-2 h-[42px] cursor-pointer">
                  <input
                    type="checkbox"
                    checked={formData.isDockable}
                    onChange={(e) => {
                      updateField('isDockable', e.target.checked)
                      if (!e.target.checked) {
                        updateField('feePayer', '')
                        updateField('minPrice', '')
                        updateField('dockVisibility', 'public')
                      }
                    }}
                    className="w-4 h-4 rounded border-gray-300"
                  />
                  <span className="text-sm font-medium text-gray-900 dark:text-white">是否可对接</span>
                </label>
              </div>
            </div>

            {/* 对接类型 - 勾选可对接时显示 */}
            {formData.isDockable && (
              <div>
                <label className="input-label">对接类型 <span className="text-red-500">*</span></label>
                <Select
                  value={formData.dockVisibility}
                  onChange={(v) => updateField('dockVisibility', v)}
                  options={[
                    { value: 'public', label: '所有人可见' },
                    { value: 'dealer_only', label: '仅分销商可见' },
                  ]}
                />
                <p className="text-xs text-gray-500 mt-1">
                  {formData.dockVisibility === 'public' ? '所有用户都可以在货源广场看到并对接此卡券' : '仅已对接过您卡券的分销商可以看到此卡券'}
                </p>
              </div>
            )}

            {/* 手续费支付方式 - 勾选可对接时显示 */}
            {formData.isDockable && (
              <div>
                <label className="input-label">手续费支付方式 <span className="text-red-500">*</span></label>
                <Select
                  value={formData.feePayer}
                  onChange={(v) => updateField('feePayer', v)}
                  options={[
                    { value: 'distributor', label: '分销主支付' },
                    { value: 'dealer', label: '分销商支付' },
                  ]}
                />
                {formData.feePayer === 'distributor' && (
                  <p className="text-sm text-amber-600 dark:text-amber-400 mt-1">
                    {feeType === 'percent'
                      ? `每笔订单您需要支付订单金额的 ${feeRate}% 作为手续费`
                      : `每笔订单您需要支付 ${feeRate} 元手续费`}
                  </p>
                )}
                {formData.feePayer === 'dealer' && (
                  <p className="text-sm text-amber-600 dark:text-amber-400 mt-1">
                    {feeType === 'percent'
                      ? `每笔订单您的代理需要支付订单金额的 ${feeRate}% 作为手续费`
                      : `每笔订单您的代理需要支付 ${feeRate} 元手续费`}
                  </p>
                )}
              </div>
            )}

            {/* 最低售价 - 勾选可对接时显示 */}
            {formData.isDockable && (
              <div>
                <label className="input-label">最低售价</label>
                <input
                  type="text"
                  value={formData.minPrice}
                  onChange={(e) => {
                    const val = e.target.value
                    // 允许清空，或输入大于0的数字（最多2位小数）
                    if (val === '' || /^\d*\.?\d{0,2}$/.test(val)) {
                      updateField('minPrice', val)
                    }
                  }}
                  className="input-ios"
                  placeholder="可选，例如：5.00"
                />
                <p className="text-xs text-gray-500 mt-1">设置最低售价后，分销商的售价不能低于此价格（可为空）</p>
              </div>
            )}

            {/* 延时发货时间 */}
            <div>
              <label className="input-label">延时发货时间</label>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  value={formData.delaySeconds}
                  onChange={(e) => updateField('delaySeconds', parseInt(e.target.value) || 0)}
                  className="input-ios w-32"
                  min={0}
                  max={3600}
                />
                <span className="text-gray-500">秒</span>
              </div>
              <p className="text-xs text-gray-500 mt-1">设置自动发货的延时时间，0表示立即发货，最大3600秒(1小时)</p>
            </div>

            {/* 备注信息 */}
            <div>
              <label className="input-label">备注信息</label>
              <textarea
                value={formData.description}
                onChange={(e) => updateField('description', e.target.value)}
                className="input-ios h-24"
                placeholder={formData.type === 'image'
                  ? "可选的备注信息，图片发送后会发送此内容\n支持变量：{order_id} {item_id} {item_title} {buyer_name} {buyer_id} {seller_name}\n使用 ###### 分隔符可拆分为多条消息发送"
                  : "可选的备注信息，填写后必须包含 {DELIVERY_CONTENT} 变量（必填）\n可选变量：{order_id} {item_id} {item_title} {buyer_name} {buyer_id} {seller_name}\n使用 ###### 分隔符可拆分为多条消息发送"
                }
              />
              <div className="text-xs text-gray-500 mt-1 space-y-1">
                {formData.type === 'image' ? (
                  <>
                    <p>
                      图片类型卡券的备注会在图片发送后作为文字内容发送。<span className="text-amber-600 dark:text-amber-400">注意：图片类型不支持 {'{DELIVERY_CONTENT}'} 变量替换。</span>
                    </p>
                    <p>
                      支持变量：<code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{'{order_id}'}</code> 订单ID、
                      <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{'{item_id}'}</code> 商品ID、
                      <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{'{item_title}'}</code> 商品标题、
                      <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{'{buyer_name}'}</code> 买家昵称、
                      <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{'{buyer_id}'}</code> 买家ID、
                      <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{'{seller_name}'}</code> 卖家昵称
                    </p>
                  </>
                ) : (
                  <>
                    <p>
                      备注内容会与发货内容一起发送。<span className="text-red-500 font-medium">非图片类型卡券填写备注时，必须包含 {'{DELIVERY_CONTENT}'} 变量。</span>
                    </p>
                    <p>
                      必填变量：<code className="bg-gray-100 dark:bg-gray-800 px-1 rounded text-red-600 dark:text-red-400">{'{DELIVERY_CONTENT}'}</code> 发货内容。可选变量：
                      <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{'{order_id}'}</code> 订单ID、
                      <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{'{item_id}'}</code> 商品ID、
                      <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{'{item_title}'}</code> 商品标题、
                      <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{'{buyer_name}'}</code> 买家昵称、
                      <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{'{buyer_id}'}</code> 买家ID、
                      <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{'{seller_name}'}</code> 卖家昵称
                    </p>
                  </>
                )}
                <p className="text-amber-600 dark:text-amber-400">
                  使用 <code className="bg-amber-100 dark:bg-amber-900/30 px-1 rounded">######</code> 分隔符可将内容拆分为多条消息依次发送，每条消息间隔0.5秒。
                </p>
              </div>
            </div>

            {/* 多规格设置 */}
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
              <div className="flex items-center gap-3 mb-3">
                <input
                  type="checkbox"
                  id="cardFormIsMultiSpec"
                  checked={formData.isMultiSpec}
                  onChange={(e) => updateField('isMultiSpec', e.target.checked)}
                  className="w-4 h-4 rounded border-gray-300"
                />
                <label htmlFor="cardFormIsMultiSpec" className="font-medium text-gray-900 dark:text-white">
                  多规格卡券
                </label>
              </div>
              <p className="text-xs text-gray-500 mb-3">
                开启后可以为同一商品的不同规格创建不同的卡券。
                <span className="text-blue-500">不知道怎么填写？先下一单，在订单管理中可以看到规格信息。</span>
              </p>
              {formData.isMultiSpec && (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="input-label">规格名称 <span className="text-red-500">*</span></label>
                      <input
                        type="text"
                        value={formData.specName}
                        onChange={(e) => updateField('specName', e.target.value)}
                        className="input-ios"
                        placeholder="例如：套餐类型、颜色、尺寸"
                      />
                    </div>
                    <div>
                      <label className="input-label">规格值 <span className="text-red-500">*</span></label>
                      <input
                        type="text"
                        value={formData.specValue}
                        onChange={(e) => updateField('specValue', e.target.value)}
                        className="input-ios"
                        placeholder="例如：30天、红色、XL"
                      />
                    </div>
                  </div>
                  <div className="mt-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm text-blue-600 dark:text-blue-400">
                    <strong>多规格说明：</strong>
                    <ul className="list-disc list-inside mt-1 space-y-1">
                      <li>同一卡券名称可以创建多个不同规格的卡券</li>
                      <li>卡券名称+规格名称+规格值必须唯一</li>
                      <li>自动发货时会精确匹配订单规格，规格不匹配则不发货</li>
                    </ul>
                  </div>
                </>
              )}
            </div>
          </div>

          <div className="modal-footer sticky bottom-0 bg-white dark:bg-gray-900">
            <button type="button" onClick={onClose} className="btn-ios-secondary" disabled={saving}>
              取消
            </button>
            <button type="submit" className="btn-ios-primary" disabled={saving}>
              {saving ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  保存中...
                </span>
              ) : (
                '保存'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
