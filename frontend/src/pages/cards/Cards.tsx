import { useState, useEffect, useRef, FormEvent, ChangeEvent } from 'react'
import { Button, Checkbox, Input, InputNumber, Modal, Popconfirm, Select, Tag } from '@arco-design/web-react'

import { Ticket, RefreshCw, Plus, Loader2, Image } from 'lucide-react'
import { getCards, deleteCard, createCard, updateCard, type CardData } from '@/api/cards'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import { useAuthStore } from '@/store/authStore'
import { post } from '@/utils/request'

type ModalType = 'add' | 'edit' | null

// 卡券类型选项
const cardTypeOptions = [
  { value: '', label: '请选择类型' },
  { value: 'api', label: 'API接口' },
  { value: 'text', label: '固定文字' },
  { value: 'data', label: '批量数据' },
  { value: 'image', label: '图片' },
]

// 请求方法选项
const apiMethodOptions = [
  { value: 'GET', label: 'GET' },
  { value: 'POST', label: 'POST' },
]

// 卡券类型标签文本
const cardTypeLabels: Record<string, string> = {
  api: 'API',
  text: '文本',
  data: '批量',
  image: '图片',
}

const cardTypeTagColors: Record<CardData['type'], string> = {
  api: 'arcoblue',
  text: 'green',
  data: 'orange',
  image: 'purple',
}

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

interface CardFormData {
  name: string
  type: 'api' | 'text' | 'data' | 'image' | ''
  // API 配置
  apiUrl: string
  apiMethod: 'GET' | 'POST'
  apiTimeout: number
  apiHeaders: string
  apiParams: string
  // 文本配置
  textContent: string
  // 批量数据配置
  dataContent: string
  // 图片配置
  imageFile: File | null
  imageUrl: string
  // 通用配置
  delaySeconds: number
  description: string
  // 多规格配置
  isMultiSpec: boolean
  specName: string
  specValue: string
}

const initialFormData: CardFormData = {
  name: '',
  type: '',
  apiUrl: '',
  apiMethod: 'GET',
  apiTimeout: 10,
  apiHeaders: '',
  apiParams: '',
  textContent: '',
  dataContent: '',
  imageFile: null,
  imageUrl: '',
  delaySeconds: 0,
  description: '',
  isMultiSpec: false,
  specName: '',
  specValue: '',
}

const getDataStockInfo = (card: CardData) => {
  const remaining = card.data_content
    ? card.data_content.split('\n').filter((line: string) => line.trim()).length
    : 0
  const total = Math.max(card.data_total_count || remaining, remaining)
  const ratio = total > 0 ? remaining / total : 0

  if (ratio <= 0.2) {
    return {
      remaining,
      total,
      percent: ratio * 100,
      fillClass: 'bg-red-100 dark:bg-red-900/40',
      textClass: 'text-red-700 dark:text-red-200',
    }
  }

  if (ratio <= 0.5) {
    return {
      remaining,
      total,
      percent: ratio * 100,
      fillClass: 'bg-orange-100 dark:bg-orange-900/40',
      textClass: 'text-orange-700 dark:text-orange-200',
    }
  }

  return {
    remaining,
    total,
    percent: ratio * 100,
    fillClass: 'bg-green-100 dark:bg-green-900/40',
    textClass: 'text-green-700 dark:text-green-200',
  }
}

export function Cards() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [cards, setCards] = useState<CardData[]>([])
  const [activeModal, setActiveModal] = useState<ModalType>(null)
  const [editingCardId, setEditingCardId] = useState<number | null>(null)
  const [formData, setFormData] = useState<CardFormData>(initialFormData)
  const [submitting, setSubmitting] = useState(false)
  const [imagePreview, setImagePreview] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // 图片预览弹窗状态
  const [isImagePreviewOpen, setIsImagePreviewOpen] = useState(false)
  const [previewImageUrl, setPreviewImageUrl] = useState('')

  const loadCards = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getCards()
      if (result.success) {
        setCards(result.data || [])
      }
    } catch {
      addToast({ type: 'error', message: '加载卡券列表失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadCards()
  }, [_hasHydrated, isAuthenticated, token])

  const handleDelete = async (id: number) => {
    try {
      await deleteCard(String(id))
      addToast({ type: 'success', message: '删除成功' })
      loadCards()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    }
  }

  const handleToggleEnabled = async (card: CardData) => {
    try {
      await updateCard(String(card.id), { enabled: !card.enabled })
      addToast({ type: 'success', message: card.enabled ? '已禁用' : '已启用' })
      loadCards()
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  const handleEdit = (card: CardData) => {
    setEditingCardId(card.id ?? null)
    setFormData({
      name: card.name || '',
      type: card.type || '',
      apiUrl: card.api_config?.url || '',
      apiMethod: (card.api_config?.method as 'GET' | 'POST') || 'GET',
      apiTimeout: card.api_config?.timeout || 10,
      apiHeaders: card.api_config?.headers || '',
      apiParams: card.api_config?.params || '',
      textContent: card.text_content || '',
      dataContent: card.data_content || '',
      imageFile: null,
      imageUrl: card.image_url || '',
      delaySeconds: card.delay_seconds || 0,
      description: card.description || '',
      isMultiSpec: card.is_multi_spec || false,
      specName: card.spec_name || '',
      specValue: card.spec_value || '',
    })
    if (card.image_url) {
      setImagePreview(card.image_url)
    }
    setActiveModal('edit')
  }

  const closeModal = () => {
    setActiveModal(null)
    setEditingCardId(null)
    setFormData(initialFormData)
    setImagePreview(null)
    setSubmitting(false)
  }

  const updateFormField = <K extends keyof CardFormData>(field: K, value: CardFormData[K]) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }

  const handleImageChange = (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      if (file.size > 5 * 1024 * 1024) {
        addToast({ type: 'error', message: '图片大小不能超过5MB' })
        return
      }
      updateFormField('imageFile', file)
      const reader = new FileReader()
      reader.onload = (e) => {
        setImagePreview(e.target?.result as string)
      }
      reader.readAsDataURL(file)
    }
  }

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
    updateFormField('apiParams', JSON.stringify(jsonObj, null, 2))
    addToast({ type: 'success', message: `已添加参数 ${paramName}` })
  }

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
    if (formData.type === 'image' && !formData.imageFile && !formData.imageUrl) {
      addToast({ type: 'warning', message: '请选择图片' })
      return false
    }
    if (formData.isMultiSpec && (!formData.specName.trim() || !formData.specValue.trim())) {
      addToast({ type: 'warning', message: '多规格卡券必须填写规格名称和规格值' })
      return false
    }
    // 验证 JSON 格式
    if (formData.apiHeaders.trim()) {
      try {
        JSON.parse(formData.apiHeaders)
      } catch {
        addToast({ type: 'warning', message: '请求头格式错误，请输入有效的JSON' })
        return false
      }
    }
    if (formData.apiParams.trim()) {
      try {
        JSON.parse(formData.apiParams)
      } catch {
        addToast({ type: 'warning', message: '请求参数格式错误，请输入有效的JSON' })
        return false
      }
    }
    return true
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!validateForm()) return

    setSubmitting(true)
    try {
      let imageUrl = formData.imageUrl

      // 如果是图片类型且有新文件，先上传图片
      if (formData.type === 'image' && formData.imageFile) {
        const formDataUpload = new FormData()
        formDataUpload.append('image', formData.imageFile)
        const uploadResult = await post<{ image_url: string }>('/upload-image', formDataUpload, {
          headers: { 'Content-Type': 'multipart/form-data' }
        })
        imageUrl = uploadResult.image_url
      }

      const cardData: Parameters<typeof createCard>[0] = {
        name: formData.name.trim(),
        type: formData.type as 'api' | 'text' | 'data' | 'image',
        description: formData.description.trim() || undefined,
        enabled: true,
        delay_seconds: formData.delaySeconds,
        is_multi_spec: formData.isMultiSpec,
        spec_name: formData.isMultiSpec ? formData.specName.trim() : undefined,
        spec_value: formData.isMultiSpec ? formData.specValue.trim() : undefined,
      }

      // 根据类型设置内容
      if (formData.type === 'api') {
        cardData.api_config = {
          url: formData.apiUrl.trim(),
          method: formData.apiMethod,
          timeout: formData.apiTimeout,
          headers: formData.apiHeaders.trim() || undefined,
          params: formData.apiParams.trim() || undefined,
        }
      } else if (formData.type === 'text') {
        cardData.text_content = formData.textContent.trim()
      } else if (formData.type === 'data') {
        cardData.data_content = formData.dataContent.trim()
      } else if (formData.type === 'image') {
        cardData.image_url = imageUrl
      }

      if (editingCardId) {
        await updateCard(String(editingCardId), cardData)
        addToast({ type: 'success', message: '卡券更新成功' })
      } else {
        await createCard(cardData)
        addToast({ type: 'success', message: '卡券创建成功' })
      }
      closeModal()
      loadCards()
    } catch (error) {
      addToast({ type: 'error', message: editingCardId ? '更新卡券失败' : '创建卡券失败' })
    } finally {
      setSubmitting(false)
    }
  }

  if (loading && cards.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Cards List */}
      <div className="vben-card">
        {/* 标题区 */}
        <div className="accounts-page-intro">
          <h1 className="page-title">卡券管理</h1>
          <p className="page-description">管理自动发货的卡密信息</p>
        </div>
        <div className="overflow-x-auto">
          <div className="table-toolbar">
            <div className="cards-toolbar-line">
              <div className="cards-summary-inline">
                <div className="cards-summary-item">
                  <span className="cards-summary-label">总卡券数</span>
                  <span className="cards-summary-value text-blue-600">{cards.length}</span>
                </div>

                <span className="cards-summary-divider" />

                <div className="cards-summary-item">
                  <span className="cards-summary-label">API类型</span>
                  <span className="cards-summary-value text-cyan-600">
                    {cards.filter(c => c.type === 'api').length}
                  </span>
                </div>

                <span className="cards-summary-divider" />

                <div className="cards-summary-item">
                  <span className="cards-summary-label">固定文字</span>
                  <span className="cards-summary-value text-green-600">
                    {cards.filter(c => c.type === 'text').length}
                  </span>
                </div>

                <span className="cards-summary-divider" />

                <div className="cards-summary-item">
                  <span className="cards-summary-label">批量数据</span>
                  <span className="cards-summary-value text-amber-600">
                    {cards.filter(c => c.type === 'data').length}
                  </span>
                </div>
              </div>
              <div className="table-toolbar-right">
                <Button
                  type="primary"
                  onClick={() => setActiveModal('add')}
                  className="accounts-header-btn"
                >
                  <Plus />
                  添加卡券
                </Button>

                <Button onClick={loadCards} className="accounts-header-btn">
                  <RefreshCw className="w-4 h-4" />
                  刷新
                </Button>
              </div>
            </div>
            <div className="table-filter-row table-filter-row--lined"></div>
          </div>
          <table className="table-ios">
            <thead>
              <tr>
                <th>名称</th>
                <th>类型</th>
                <th>内容预览</th>
                <th>延时</th>
                <th>规格</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {cards.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-gray-500">
                    <div className="flex flex-col items-center gap-2">
                      <Ticket className="w-12 h-12 text-gray-300" />
                      <p>暂无卡券数据</p>
                    </div>
                  </td>
                </tr>
              ) : (
                cards.map((card) => (
                  <tr key={card.id}>
                    <td className="font-medium">{card.name}</td>
                    <td>
                      <Tag color={cardTypeTagColors[card.type] || 'gray'}>
                        {cardTypeLabels[card.type] || card.type}
                      </Tag>
                    </td>
                    <td>
                      {card.type === 'image' ? (
                        card.image_url ? (
                          <button
                            onClick={() => {
                              setPreviewImageUrl(card.image_url || '')
                              setIsImagePreviewOpen(true)
                            }}
                            className="px-2 py-1 text-xs font-medium bg-purple-100 text-purple-700 hover:bg-purple-200 dark:bg-purple-900/30 dark:text-purple-400 rounded transition-colors flex items-center gap-1"
                          >
                            <Image />
                            查看原图
                          </button>
                        ) : (
                          <span className="text-gray-400 text-sm">暂无图片</span>
                        )
                      ) : card.type === 'data' ? (
                        (() => {
                          const stock = getDataStockInfo(card)

                          return (
                            <div className="w-[180px]">
                              <div className="relative h-6 overflow-hidden rounded-[4px] bg-slate-100 dark:bg-slate-800">
                                <div
                                  className={`h-full rounded-[4px] transition-all ${stock.fillClass}`}
                                  style={{ width: `${stock.percent}%` }}
                                />
                                <div className={`absolute inset-0 flex items-center px-2 text-xs font-semibold ${stock.textClass}`}>
                                  剩余 {stock.remaining} / {stock.total} 条
                                </div>
                              </div>
                            </div>
                          )
                        })()
                      ) : (
                        <code className="text-xs bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded max-w-[200px] truncate block">
                          {card.type === 'text' && (card.text_content || '-')}
                          {card.type === 'api' && (card.api_config?.url || '-')}
                          {!['text', 'data', 'api', 'image'].includes(card.type) && '-'}
                        </code>
                      )}
                    </td>
                    <td>{card.delay_seconds || 0}秒</td>
                    <td>
                      {card.is_multi_spec ? (
                        <span className="text-xs text-blue-600">{card.spec_name}: {card.spec_value}</span>
                      ) : (
                        <span className="text-gray-400">-</span>
                      )}
                    </td>
                    <td>
                      <Tag color={card.enabled ? 'green' : 'gray'}>
                        {card.enabled ? '启用' : '禁用'}
                      </Tag>
                    </td>
                    <td>
                      <div className="flex items-center gap-2">
                        <Button
                          type="text"
                          size="mini"
                          onClick={() => handleEdit(card)}
                          className="accounts-table-action-btn"
                        >
                          编辑
                        </Button>
                        <Button
                          type="text"
                          size="mini"
                          onClick={() => handleToggleEnabled(card)}
                          className="accounts-table-action-btn"
                        >
                          {card.enabled ? '禁用' : '启用'}
                        </Button>
                        <Popconfirm
                          title="确定要删除这张卡券吗？"
                          okText="删除"
                          cancelText="取消"
                          okButtonProps={{ status: 'danger' }}
                          onOk={() => {
                            if (card.id) {
                              return handleDelete(card.id)
                            }
                          }}
                        >
                          <Button
                            type="text"
                            size="mini"
                            className="accounts-table-action-btn !text-red-500 hover:!text-red-500"
                          >
                            删除
                          </Button>
                        </Popconfirm>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Modal
        visible={Boolean(activeModal)}
        title={editingCardId ? '编辑卡券' : '添加卡券'}
        onCancel={closeModal}
        footer={null}
        unmountOnExit
        style={{ width: 960 }}
      >
        <form onSubmit={handleSubmit}>
          <div className="space-y-4 max-h-[70vh] overflow-y-auto pr-1">
            {/* 基本信息 */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="input-label">卡券名称 <span className="text-red-500">*</span></label>
                <Input
                  value={formData.name}
                  onChange={(value) => updateFormField('name', value)}
                  placeholder="例如：游戏点卡、会员卡等"
                />
              </div>
              <div>
                <label className="input-label">卡券类型 <span className="text-red-500">*</span></label>
                <Select
                  value={formData.type}
                  onChange={(v) => updateFormField('type', v as CardFormData['type'])}
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
                  <Input
                    value={formData.apiUrl}
                    onChange={(value) => updateFormField('apiUrl', value)}
                    placeholder="https://api.example.com/get-card"
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="input-label">请求方法</label>
                    <Select
                      value={formData.apiMethod}
                      onChange={(v) => updateFormField('apiMethod', v as 'GET' | 'POST')}
                      options={apiMethodOptions}
                    />
                  </div>
                  <div>
                    <label className="input-label">超时时间(秒)</label>
                    <InputNumber
                      value={formData.apiTimeout}
                      onChange={(value) => updateFormField('apiTimeout', Number(value) || 10)}
                      min={1}
                      max={60}
                      className="w-full"
                    />
                  </div>
                </div>
                <div>
                  <label className="input-label">请求头 (JSON格式)</label>
                  <Input.TextArea
                    value={formData.apiHeaders}
                    onChange={(value) => updateFormField('apiHeaders', value)}
                    placeholder='{"Authorization": "Bearer token"}'
                    autoSize={{ minRows: 3, maxRows: 6 }}
                  />
                </div>
                <div>
                  <label className="input-label">请求参数 (JSON格式)</label>
                  <Input.TextArea
                    value={formData.apiParams}
                    onChange={(value) => updateFormField('apiParams', value)}
                    placeholder='{"type": "card", "count": 1}'
                    autoSize={{ minRows: 3, maxRows: 6 }}
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
              </div>
            )}

            {/* 固定文字配置 */}
            {formData.type === 'text' && (
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <h3 className="font-medium text-gray-900 dark:text-white mb-3">固定文字配置</h3>
                <div>
                  <label className="input-label">固定文字内容</label>
                  <Input.TextArea
                    value={formData.textContent}
                    onChange={(value) => updateFormField('textContent', value)}
                    placeholder="请输入要发送的固定文字内容..."
                    autoSize={{ minRows: 5, maxRows: 8 }}
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
                  <Input.TextArea
                    value={formData.dataContent}
                    onChange={(value) => updateFormField('dataContent', value)}
                    placeholder="请输入数据，每行一个：&#10;卡号1:密码1&#10;卡号2:密码2&#10;或者&#10;兑换码1&#10;兑换码2"
                    autoSize={{ minRows: 6, maxRows: 10 }}
                  />
                  <p className="text-xs text-gray-500 mt-1">支持格式：卡号:密码 或 单独的兑换码</p>
                </div>
              </div>
            )}

            {/* 图片配置 */}
            {formData.type === 'image' && (
              <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
                <h3 className="font-medium text-gray-900 dark:text-white mb-3">图片配置</h3>
                <div>
                  <label className="input-label">选择图片 <span className="text-red-500">*</span></label>
                  <Button onClick={() => fileInputRef.current?.click()}>选择图片</Button>
                  <input
                    ref={fileInputRef}
                    type="file"
                    onChange={handleImageChange}
                    accept="image/*"
                    className="hidden"
                  />
                  <p className="text-xs text-gray-500 mt-1">支持JPG、PNG、GIF格式，最大5MB</p>
                </div>
                {imagePreview && (
                  <div className="mt-3">
                    <label className="input-label">图片预览</label>
                    <img
                      src={imagePreview}
                      alt="预览"
                      className="max-w-full max-h-48 rounded-lg border border-gray-200 dark:border-gray-700"
                    />
                  </div>
                )}
              </div>
            )}

            {/* 延时发货时间 */}
            <div>
              <label className="input-label">延时发货时间</label>
              <div className="flex items-center gap-2">
                <InputNumber
                  value={formData.delaySeconds}
                  onChange={(value) => updateFormField('delaySeconds', Number(value) || 0)}
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
              <Input.TextArea
                value={formData.description}
                onChange={(value) => updateFormField('description', value)}
                placeholder="可选的备注信息，支持变量替换：&#10;{DELIVERY_CONTENT} - 发货内容"
                autoSize={{ minRows: 3, maxRows: 6 }}
              />
              <p className="text-xs text-gray-500 mt-1">
                备注内容会与发货内容一起发送。使用 <code className="bg-gray-100 dark:bg-gray-800 px-1 rounded">{'{DELIVERY_CONTENT}'}</code> 变量可以在备注中插入实际的发货内容。
              </p>
            </div>

            {/* 多规格设置 */}
            <div className="border border-gray-200 dark:border-gray-700 rounded-lg p-4">
              <div className="flex items-center gap-3 mb-3">
                <Checkbox
                  id="isMultiSpec"
                  checked={formData.isMultiSpec}
                  onChange={(checked) => updateFormField('isMultiSpec', checked)}
                />
                <label htmlFor="isMultiSpec" className="font-medium text-gray-900 dark:text-white">
                  多规格卡券
                </label>
              </div>
              <p className="text-xs text-gray-500 mb-3">开启后可以为同一商品的不同规格创建不同的卡券</p>

              {formData.isMultiSpec && (
                <>
                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="input-label">规格名称 <span className="text-red-500">*</span></label>
                      <Input
                        value={formData.specName}
                        onChange={(value) => updateFormField('specName', value)}
                        placeholder="例如：套餐类型、颜色、尺寸"
                      />
                    </div>
                    <div>
                      <label className="input-label">规格值 <span className="text-red-500">*</span></label>
                      <Input
                        value={formData.specValue}
                        onChange={(value) => updateFormField('specValue', value)}
                        placeholder="例如：30天、红色、XL"
                      />
                    </div>
                  </div>
                  <div className="mt-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm text-blue-600 dark:text-blue-400">
                    <strong>多规格说明：</strong>
                    <ul className="list-disc list-inside mt-1 space-y-1">
                      <li>同一卡券名称可以创建多个不同规格的卡券</li>
                      <li>卡券名称+规格名称+规格值必须唯一</li>
                      <li>自动发货时会优先匹配精确规格，找不到时使用普通卡券兜底</li>
                    </ul>
                  </div>
                </>
              )}
            </div>
          </div>
          <div className="mt-6 flex justify-end gap-3">
            <Button onClick={closeModal} disabled={submitting}>
              取消
            </Button>
            <Button htmlType="submit" type="primary" disabled={submitting}>
              {submitting ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {editingCardId ? '更新中...' : '创建中...'}
                </span>
              ) : (
                editingCardId ? '更新卡券' : '保存卡券'
              )}
            </Button>
          </div>
        </form>
      </Modal>

      <Modal
        visible={isImagePreviewOpen}
        title="图片预览"
        onCancel={() => setIsImagePreviewOpen(false)}
        footer={null}
        unmountOnExit
        style={{ width: 960 }}
      >
        <div className="flex justify-center">
          <img
            src={previewImageUrl}
            alt="预览"
            className="max-w-full max-h-[70vh] object-contain rounded-lg"
          />
        </div>
      </Modal>
    </div>
  )
}
