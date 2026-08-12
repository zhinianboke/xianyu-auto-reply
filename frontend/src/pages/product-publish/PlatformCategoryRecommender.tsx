/**
 * 商品描述联动的平台分类组件。
 * 分类和属性卡完全由闲鱼推荐接口返回，切换分类时按抓包携带完整卡片状态。
 */
import { useEffect, useRef, useState } from 'react'
import { Loader2, RefreshCw } from 'lucide-react'
import {
  recommendPlatformCategory,
  type PlatformCategoryCandidate,
  type PlatformCategoryCardData,
  type PlatformCategoryCardValue,
  type PlatformCategoryProperty,
  type PlatformMaterialAttribute,
} from '@/api/productPublish'
import type { PublishForm } from './publishTypes'
import PlatformAttributesEditor, { PlatformOptionField } from './PlatformAttributesEditor'

interface PlatformCategoryRecommenderProps {
  form: PublishForm
  onChange: (patch: Partial<PublishForm>) => void
  categoryLocked?: boolean
  onReselectCategory?: () => void
}

interface CategorySelectionRequest {
  current_card_list: PlatformCategoryCardData[]
  selected_list: Record<string, unknown>[]
  cat_id: string
  cat_name: string
  channel_cat_id: string
}

const emptyCategory = {
  category: '',
  platform_category_id: '',
  platform_category_name: '',
  platform_channel_category_id: '',
  platform_channel_category_name: '',
  platform_leaf_id: '',
  platform_tb_category_id: '',
  platform_category_path: [],
  platform_attributes: [],
  category_source: 'manual' as const,
  category_confidence: undefined,
}

function asText(value: unknown) {
  return typeof value === 'string' || typeof value === 'number' ? String(value) : ''
}

function candidateLabel(candidate: PlatformCategoryCandidate) {
  return candidate.cat_name || candidate.channel_cat_name || candidate.path.at(-1)?.name || '未命名分类'
}

function candidatePatch(candidate: PlatformCategoryCandidate): Partial<PublishForm> {
  return {
    category: candidateLabel(candidate),
    platform_category_id: candidate.cat_id || '',
    platform_category_name: candidate.cat_name || '',
    platform_channel_category_id: candidate.channel_cat_id || '',
    platform_channel_category_name: candidate.channel_cat_name || '',
    platform_leaf_id: candidate.leaf_id || '',
    platform_tb_category_id: candidate.tb_cat_id || '',
    platform_category_path: candidate.path || [],
    category_source: 'recommendation',
    category_confidence: typeof candidate.score === 'number' ? candidate.score : undefined,
  }
}

function candidateFromForm(form: PublishForm): PlatformCategoryCandidate | null {
  const hasCategory = Boolean(
    form.category
      || form.platform_category_id
      || form.platform_channel_category_id
      || form.platform_tb_category_id,
  )
  if (!hasCategory) return null
  return {
    cat_id: form.platform_category_id || null,
    cat_name: form.platform_category_name || form.category || null,
    channel_cat_id: form.platform_channel_category_id || null,
    channel_cat_name: form.platform_channel_category_name || form.category || null,
    leaf_id: form.platform_leaf_id || null,
    tb_cat_id: form.platform_tb_category_id || null,
    path: form.platform_category_path || [],
    score: typeof form.category_confidence === 'number' ? form.category_confidence : null,
    is_selected: true,
  }
}

function propertiesFromAttributes(attributes: PlatformMaterialAttribute[]): PlatformCategoryProperty[] {
  const groups = new Map<string, PlatformMaterialAttribute[]>()
  for (const attribute of attributes) {
    const propertyId = attribute.property_id || ''
    const propertyName = attribute.property_name || ''
    if (!propertyId || !propertyName || propertyId === '-10000') continue
    const current = groups.get(propertyId) || []
    current.push(attribute)
    groups.set(propertyId, current)
  }

  return Array.from(groups.entries()).map(([propertyId, values]) => ({
    property_id: propertyId,
    property_name: values[0].property_name || propertyId,
    input_word: null,
    is_multiple: values.length > 1,
    is_decisive_property: false,
    options: values.map((attribute) => ({
      property_id: propertyId,
      property_name: values[0].property_name || propertyId,
      value_id: attribute.value_id || null,
      value_name: attribute.value_name || attribute.text || '',
      channel_cat_id: null,
      tb_cat_id: null,
    })).filter((option) => option.value_name),
  }))
}

function samePath(left: PublishForm['platform_category_path'], right: PlatformCategoryCandidate['path']) {
  return left.length === right.length && left.every((item, index) => item.id === right[index]?.id && item.name === right[index]?.name)
}

function sameCandidate(left: PlatformCategoryCandidate | undefined, right: PlatformCategoryCandidate) {
  if (!left) return false
  if (left.channel_cat_id && right.channel_cat_id) return left.channel_cat_id === right.channel_cat_id
  if (left.tb_cat_id && right.tb_cat_id) return left.tb_cat_id === right.tb_cat_id
  if (left.path?.length && right.path?.length) return samePath(left.path, right.path)
  // catId 在闲鱼接口中可能被多个频道末级分类复用，只有没有更具体 ID 时才能兜底比较。
  return Boolean(
    !left.channel_cat_id
      && !right.channel_cat_id
      && !left.tb_cat_id
      && !right.tb_cat_id
      && left.cat_id
      && right.cat_id
      && left.cat_id === right.cat_id,
  )
}

function transportData(value: PlatformCategoryCardValue) {
  const transport = value.transportData
  return transport && typeof transport === 'object' && !Array.isArray(transport)
    ? transport as Record<string, unknown>
    : {}
}

function candidateMatchesCardValue(candidate: PlatformCategoryCandidate, value: PlatformCategoryCardValue) {
  const transport = transportData(value)
  const channelCatId = asText(value.channelCatId) || asText(transport.channelCateId)
  const tbCatId = asText(value.tbCatId) || asText(transport.tbCatId)
  const catName = asText(value.catName) || asText(transport.valueName)
  if (candidate.channel_cat_id && channelCatId) return candidate.channel_cat_id === channelCatId
  if (candidate.tb_cat_id && tbCatId) return candidate.tb_cat_id === tbCatId
  if (candidate.channel_cat_id || candidate.tb_cat_id) return false
  if (candidate.cat_id && asText(value.catId)) return candidate.cat_id === asText(value.catId)
  return Boolean(candidate.cat_name && candidate.cat_name === catName)
}

function buildCategorySelection(cards: PlatformCategoryCardData[], candidate: PlatformCategoryCandidate): CategorySelectionRequest {
  const categoryName = candidate.cat_name || candidate.channel_cat_name || ''
  const channelCategoryId = candidate.channel_cat_id || ''
  let selectedLabel: Record<string, unknown> | null = null

  const currentCardList = cards.map((card) => {
    if (card.propertyId !== '-10000' || !Array.isArray(card.valuesList)) return card

    const valuesList = card.valuesList.map((value) => {
      const selected = candidateMatchesCardValue(candidate, value)
      const transport = transportData(value)
      const valueChannelId = asText(value.channelCatId) || asText(transport.channelCateId) || channelCategoryId
      const valueCategoryName = asText(value.catName) || asText(value.channelCatName) || categoryName
      const properties = valueChannelId ? `-10000##分类:${valueChannelId}##${valueCategoryName}` : asText(value.properties)

      const nextTransport = {
        ...transport,
        channelCateName: asText(value.channelCatName) || asText(transport.channelCateName) || candidate.channel_cat_name || categoryName,
        valueId: null,
        channelCateId: valueChannelId,
        valueName: null,
        tbCatId: asText(value.tbCatId) || asText(transport.tbCatId) || candidate.tb_cat_id || null,
        subPropertyId: null,
        labelType: asText(transport.labelType) || 'common',
        subValueId: null,
        labelId: null,
        propertyName: '分类',
        isUserClick: selected ? '1' : '0',
        isUserCancel: null,
        from: 'newPublishChoice',
        propertyId: '-10000',
        labelFrom: 'newPublish',
        properties,
        ...(selected ? { text: valueCategoryName } : {}),
      }

      if (selected) selectedLabel = nextTransport
      return {
        ...value,
        isClicked: selected ? '1' : '0',
        isUserClick: selected ? '1' : '0',
        isUserCancel: null,
        transportData: nextTransport,
      }
    })
    return { ...card, valuesList }
  })

  return {
    current_card_list: currentCardList,
    selected_list: selectedLabel ? [selectedLabel] : [],
    cat_id: candidate.cat_id || '',
    cat_name: categoryName,
    channel_cat_id: channelCategoryId,
  }
}

function selectedProperty(attributes: PlatformMaterialAttribute[], propertyId: string) {
  return attributes.find((attribute) => attribute.property_id === propertyId)
}

export function PlatformCategoryRecommender({ form, onChange, categoryLocked = false, onReselectCategory }: PlatformCategoryRecommenderProps) {
  const [candidates, setCandidates] = useState<PlatformCategoryCandidate[]>([])
  const [properties, setProperties] = useState<PlatformCategoryProperty[]>([])
  const [cardList, setCardList] = useState<PlatformCategoryCardData[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [retryNonce, setRetryNonce] = useState(0)
  const inputKeyRef = useRef('')
  const requestVersion = useRef(0)

  useEffect(() => {
    const title = form.title.trim()
    const description = form.description.trim()
    const key = `${title}\u0000${description}\u0000${form.account_id}\u0000${categoryLocked ? 'locked' : 'recommend'}\u0000${retryNonce}`
    if (inputKeyRef.current === key) return
    inputKeyRef.current = key
    const version = ++requestVersion.current

    if (categoryLocked) {
      const importedCandidate = candidateFromForm(form)
      setCandidates(importedCandidate ? [importedCandidate] : [])
      setProperties(propertiesFromAttributes(form.platform_attributes))
      setCardList([])
      setError('')
      setLoading(false)
      return
    }

    if (!title && !description) {
      setCandidates([])
      setProperties([])
      setCardList([])
      setError('')
      setLoading(false)
      onChange(emptyCategory)
      return
    }

    setLoading(true)
    setError('')
    let requestStarted = false
    const timer = window.setTimeout(async () => {
      requestStarted = true
      setCandidates([])
      setProperties([])
      setCardList([])
      onChange(emptyCategory)
      try {
        const response = await recommendPlatformCategory({
          title: title || description.slice(0, 200),
          description: description || title,
          account_id: form.account_id || undefined,
        })
        if (version !== requestVersion.current) return
        if (!response.success || !response.data?.candidates?.length) {
          setError(response.message || '接口未返回可用的商品分类')
          return
        }

        const returnedCandidates = response.data.candidates
        const preferredCandidate = returnedCandidates.find((candidate) => candidate.is_selected && candidate.channel_cat_id && candidate.tb_cat_id)
          || returnedCandidates.find((candidate) => sameCandidate({
            cat_id: form.platform_category_id,
            channel_cat_id: form.platform_channel_category_id,
            tb_cat_id: form.platform_tb_category_id,
            path: form.platform_category_path,
          }, candidate) && candidate.channel_cat_id && candidate.tb_cat_id)
          || returnedCandidates.find((candidate) => candidate.channel_cat_id && candidate.tb_cat_id)

        setCandidates(returnedCandidates)
        setProperties(response.data.properties || [])
        setCardList(response.data.card_list || [])
        if (!preferredCandidate) {
          setError('接口返回的分类缺少发布所需的分类 ID，请点击重试')
          return
        }
        onChange({ ...candidatePatch(preferredCandidate), platform_attributes: [], brand: '', condition: '全新' })
      } catch {
        if (version !== requestVersion.current) return
        setError('分类推荐请求失败，请稍后重试')
      } finally {
        if (version === requestVersion.current) setLoading(false)
      }
    }, 650)

    return () => {
      window.clearTimeout(timer)
      // React 严格模式会立即清理首次副作用；若此时请求尚未发出，允许下一次副作用重新调度。
      if (!requestStarted && inputKeyRef.current === key) inputKeyRef.current = ''
    }
  }, [form.title, form.description, form.account_id, categoryLocked, retryNonce])

  const selectCandidate = async (candidate: PlatformCategoryCandidate) => {
    const title = form.title.trim()
    const description = form.description.trim()
    const selection = buildCategorySelection(cardList, candidate)
    const version = ++requestVersion.current
    setLoading(true)
    setError('')
    setProperties([])
    onChange({ ...candidatePatch(candidate), platform_attributes: [], brand: '', condition: '全新' })

    try {
      const response = await recommendPlatformCategory({
        title: title || description.slice(0, 200),
        description: description || title,
        account_id: form.account_id || undefined,
        ...selection,
      })
      if (version !== requestVersion.current) return
      if (!response.success || !response.data?.candidates?.length) {
        setError(response.message || '接口未返回当前分类的平台属性')
        return
      }

      const refreshedCandidates = response.data.candidates
      const refreshedCandidate = refreshedCandidates.find((item) => sameCandidate(item, candidate)) || candidate
      setCandidates(refreshedCandidates)
      setProperties(response.data.properties || [])
      setCardList(response.data.card_list || selection.current_card_list)
      onChange({ ...candidatePatch(refreshedCandidate), platform_attributes: [], brand: '', condition: '全新' })
    } catch {
      if (version === requestVersion.current) setError('分类切换请求失败，请点击重试')
    } finally {
      if (version === requestVersion.current) setLoading(false)
    }
  }

  const retryRecommendation = () => {
    inputKeyRef.current = ''
    setError('')
    setCandidates([])
    setProperties([])
    setCardList([])
    setRetryNonce((value) => value + 1)
  }

  const selectedCandidate = candidates.find((candidate) => sameCandidate({
    cat_id: form.platform_category_id,
    channel_cat_id: form.platform_channel_category_id,
    tb_cat_id: form.platform_tb_category_id,
    path: form.platform_category_path,
  }, candidate))
  const selectedIndex = selectedCandidate ? String(candidates.indexOf(selectedCandidate)) : ''

  const updateAttributes = (platformAttributes: PlatformMaterialAttribute[]) => {
    const patch: Partial<PublishForm> = { platform_attributes: platformAttributes }
    if (properties.some((property) => property.property_id === '20000')) {
      patch.brand = selectedProperty(platformAttributes, '20000')?.value_name || ''
    }
    if (properties.some((property) => property.property_id === '20879')) {
      patch.condition = selectedProperty(platformAttributes, '20879')?.value_name || '全新'
    }
    onChange(patch)
  }

  return (
    <section className="space-y-3">
      {error && (
        <div className="flex items-center justify-between gap-2 rounded-md border border-red-100 bg-red-50 px-3 py-2 text-xs text-red-600 dark:border-red-900/60 dark:bg-red-950/20 dark:text-red-300">
          <span className="break-words">{error}</span>
          <button
            type="button"
            title="重新推荐分类"
            className="inline-flex flex-shrink-0 items-center justify-center rounded border border-red-200 p-1.5 text-red-600 hover:bg-red-100 dark:border-red-800 dark:text-red-300 dark:hover:bg-red-900/40"
            onClick={retryRecommendation}
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
      )}

      {loading && (
        <div className="flex items-center gap-1.5 text-xs text-slate-400">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />正在更新分类属性
        </div>
      )}

      {candidates.length > 0 && (
        <div className="space-y-2">
          {categoryLocked && onReselectCategory && (
            <div className="flex justify-end">
              <button
                type="button"
                className="inline-flex items-center gap-1.5 text-xs text-blue-600 transition-colors hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
                onClick={onReselectCategory}
              >
                <RefreshCw className="h-3.5 w-3.5" />重新选择分类
              </button>
            </div>
          )}
          <div className="grid grid-cols-1 gap-x-3 gap-y-3 sm:grid-cols-2 lg:grid-cols-4">
            <PlatformOptionField
              label={<><span>分类</span> <span className="text-red-500">*</span></>}
              placeholder="请选择分类"
              value={selectedIndex}
              disabled={loading || categoryLocked}
              options={candidates.map((candidate, index) => ({
                value: String(index),
                label: candidateLabel(candidate),
                disabled: !candidate.channel_cat_id || !candidate.tb_cat_id,
              }))}
              onSelect={(value) => {
                const candidate = candidates[Number(value)]
                if (!categoryLocked && candidate?.channel_cat_id && candidate.tb_cat_id) void selectCandidate(candidate)
              }}
            />
            <PlatformAttributesEditor
              properties={properties}
              attributes={form.platform_attributes}
              candidate={selectedCandidate}
              onChange={updateAttributes}
            />
          </div>
        </div>
      )}
    </section>
  )
}

export default PlatformCategoryRecommender
