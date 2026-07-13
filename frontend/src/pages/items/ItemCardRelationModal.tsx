/**
 * 商品关联卡券选择弹窗组件
 *
 * 功能：左右双栏布局，左侧待选卡券列表（服务端分页 + 搜索 + 滚动加载更多），
 * 右侧已选卡券列表；勾选/取消勾选自动同步两侧显示，保存时写入关联表。
 *
 * 性能：卡券可达上万条，左侧改为服务端真分页（滚动到底逐页加载），搜索走后端
 * （防抖）；已选卡券数据用 cardCache 累积，供右侧渲染，无需一次性拉取全部。
 */
import { useState, useEffect, useMemo, useRef, type UIEvent } from 'react'
import { X, Loader2, Search, CheckSquare, Square, Ticket, Eye } from 'lucide-react'
import {
  getCard,
  getCardsByItemId,
  getSelectableCards,
  getAllSelectableCardKeys,
  updateItemCards,
  type CardData,
  type CardRelationItem,
  type SelectableCard,
} from '@/api/cards'
import { CardDetailModal } from '@/pages/cards/CardDetailModal'
import { useUIStore } from '@/store/uiStore'

// 统一卡券项（自有卡券 + 对接记录）
interface UnifiedCardItem {
  id?: number
  name: string
  type: string
  source: 'own' | 'dock_l1' | 'dock_l2'
  dockName?: string
  dockRecordId?: number
  is_multi_spec?: boolean
  spec_name?: string
  spec_value?: string
  enabled?: boolean
  price?: string | null
  uniqueKey: string  // 'own_{cardId}' | 'dock_{dockRecordId}'
}

// 卡券类型标签
const cardTypeLabels: Record<string, string> = {
  api: 'API',
  text: '文本',
  data: '批量',
  image: '图片',
  yifan_api: '亦凡API',
}

// 左侧每次向后端请求的行数
const REQUEST_PAGE_SIZE = 50
// 右侧已选列表每次渲染的行数（前端分批渲染，避免选中过多时 DOM 过重）
const RIGHT_PAGE_SIZE = 60
// 搜索防抖时长（毫秒）
const SEARCH_DEBOUNCE = 300

// SelectableCard → UnifiedCardItem
const toUnified = (sc: SelectableCard): UnifiedCardItem => ({
  id: sc.id,
  name: sc.name,
  type: sc.type,
  source: sc.source,
  dockName: sc.dock_name ?? undefined,
  dockRecordId: sc.dock_record_id ?? undefined,
  is_multi_spec: sc.is_multi_spec,
  spec_name: sc.spec_name,
  spec_value: sc.spec_value,
  enabled: sc.enabled,
  price: sc.price ?? null,
  uniqueKey: sc.unique_key,
})

interface ItemCardRelationModalProps {
  /** 商品ID */
  itemId: string
  /** 商品名称（用于弹窗标题） */
  itemName: string
  /** 关闭回调 */
  onClose: () => void
  /** 保存成功回调 */
  onSaved: () => void
}

export function ItemCardRelationModal({ itemId, itemName, onClose, onSaved }: ItemCardRelationModalProps) {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // 左侧：服务端分页列表
  const [leftItems, setLeftItems] = useState<UnifiedCardItem[]>([])
  const [leftPage, setLeftPage] = useState(1)
  const [leftTotal, setLeftTotal] = useState(0)
  const [leftLoadingMore, setLeftLoadingMore] = useState(false)
  const loadingMoreRef = useRef(false)  // 防止滚动触发并发加载

  // 选中状态与已选卡券数据缓存（累积：已关联 + 已加载页 + 全选结果）
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const [cardCache, setCardCache] = useState<Map<string, UnifiedCardItem>>(new Map())

  // 搜索：leftSearch 为输入值，appliedSearch 为防抖后真正生效的查询词
  const [leftSearch, setLeftSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [rightSearch, setRightSearch] = useState('')
  const [rightVisibleCount, setRightVisibleCount] = useState(RIGHT_PAGE_SIZE)

  const [viewingCard, setViewingCard] = useState<CardData | null>(null)
  const [detailLoadingKey, setDetailLoadingKey] = useState<string | null>(null)
  const [selectAllLoading, setSelectAllLoading] = useState(false)

  // 合并一批卡券进缓存
  const mergeCache = (items: UnifiedCardItem[]) => {
    if (items.length === 0) return
    setCardCache(prev => {
      const next = new Map(prev)
      for (const it of items) next.set(it.uniqueKey, it)
      return next
    })
  }

  // 首次加载：已关联卡券（右侧展示 + 初始选中态）
  useEffect(() => {
    loadAssociated()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 搜索输入防抖 → 生效查询词
  useEffect(() => {
    const t = setTimeout(() => setAppliedSearch(leftSearch.trim()), SEARCH_DEBOUNCE)
    return () => clearTimeout(t)
  }, [leftSearch])

  // 生效查询词变化（含首次挂载）→ 重置并加载第一页
  useEffect(() => {
    loadFirstPage(appliedSearch)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [appliedSearch])

  // 右侧搜索变化时重置已渲染行数
  useEffect(() => {
    setRightVisibleCount(RIGHT_PAGE_SIZE)
  }, [rightSearch])

  // 加载商品已关联的卡券：喂给缓存并作为初始选中项
  const loadAssociated = async () => {
    try {
      const relResult = await getCardsByItemId(itemId)
      const existing: CardData[] = relResult?.data || []
      const keys = new Set<string>()
      const cacheItems: UnifiedCardItem[] = []
      for (const ec of existing) {
        if (ec.id === undefined) continue
        let key: string
        let source: UnifiedCardItem['source']
        if (ec.card_source && ec.card_source !== 'own' && ec.dock_record_id) {
          key = `dock_${ec.dock_record_id}`
          source = ec.card_source
        } else {
          key = `own_${ec.id}`
          source = 'own'
        }
        keys.add(key)
        cacheItems.push({
          id: ec.id,
          name: ec.name,
          type: ec.type,
          source,
          dockRecordId: ec.dock_record_id ?? undefined,
          is_multi_spec: ec.is_multi_spec,
          spec_name: ec.spec_name,
          spec_value: ec.spec_value,
          enabled: ec.enabled,
          price: ec.price ?? null,
          uniqueKey: key,
        })
      }
      mergeCache(cacheItems)
      setSelectedKeys(keys)
    } catch {
      addToast({ type: 'error', message: '加载已关联卡券失败' })
    }
  }

  // 加载/重置到第一页
  const loadFirstPage = async (search: string) => {
    setLoading(true)
    try {
      const res = await getSelectableCards(itemId, 1, REQUEST_PAGE_SIZE, search)
      const items = (res.list || []).map(toUnified)
      setLeftItems(items)
      setLeftPage(1)
      setLeftTotal(res.total || 0)
      mergeCache(items)
    } catch {
      addToast({ type: 'error', message: '加载卡券失败' })
    } finally {
      setLoading(false)
    }
  }

  // 滚动到底部：加载下一页并追加
  const loadMore = async () => {
    if (loadingMoreRef.current || loading) return
    if (leftItems.length >= leftTotal) return
    loadingMoreRef.current = true
    setLeftLoadingMore(true)
    try {
      const nextPage = leftPage + 1
      const res = await getSelectableCards(itemId, nextPage, REQUEST_PAGE_SIZE, appliedSearch)
      const items = (res.list || []).map(toUnified)
      setLeftItems(prev => [...prev, ...items])
      setLeftPage(nextPage)
      setLeftTotal(res.total || 0)
      mergeCache(items)
    } catch {
      addToast({ type: 'error', message: '加载更多失败' })
    } finally {
      loadingMoreRef.current = false
      setLeftLoadingMore(false)
    }
  }

  const handleLeftScroll = (e: UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 200) {
      loadMore()
    }
  }

  const handleRightScroll = (e: UIEvent<HTMLDivElement>) => {
    const el = e.currentTarget
    if (el.scrollHeight - el.scrollTop - el.clientHeight < 200) {
      setRightVisibleCount(prev => (prev < selectedCards.length ? prev + RIGHT_PAGE_SIZE : prev))
    }
  }

  // 切换卡券选中状态
  const toggleCard = (key: string) => {
    setSelectedKeys(prev => {
      const next = new Set(prev)
      if (next.has(key)) {
        next.delete(key)
      } else {
        next.add(key)
      }
      return next
    })
  }

  // 全选/取消全选当前筛选结果（拉取全部匹配项，避免只操作已加载的部分）
  const handleSelectAll = async (select: boolean) => {
    setSelectAllLoading(true)
    try {
      const res = await getAllSelectableCardKeys(appliedSearch)
      const items = (res.list || []).map(toUnified)
      mergeCache(items)
      const keys = items.map(i => i.uniqueKey)
      setSelectedKeys(prev => {
        const next = new Set(prev)
        if (select) {
          keys.forEach(k => next.add(k))
        } else {
          keys.forEach(k => next.delete(k))
        }
        return next
      })
    } catch {
      addToast({ type: 'error', message: '全选加载失败' })
    } finally {
      setSelectAllLoading(false)
    }
  }

  // 按需拉取卡券完整详情后再打开详情弹窗
  const openCardDetail = async (card: UnifiedCardItem) => {
    if (card.id === undefined) return
    setDetailLoadingKey(card.uniqueKey)
    try {
      const full = await getCard(card.id)
      setViewingCard(full)
    } catch {
      addToast({ type: 'error', message: '加载卡券详情失败' })
    } finally {
      setDetailLoadingKey(null)
    }
  }

  // 右侧已选卡券列表（从缓存按选中键取，按右侧搜索本地过滤）
  const selectedCards = useMemo(() => {
    const cards: UnifiedCardItem[] = []
    for (const key of selectedKeys) {
      const c = cardCache.get(key)
      if (c) cards.push(c)
    }
    if (!rightSearch) return cards
    const kw = rightSearch.toLowerCase()
    return cards.filter(card =>
      (card.name || '').toLowerCase().includes(kw) ||
      (card.type || '').toLowerCase().includes(kw)
    )
  }, [selectedKeys, cardCache, rightSearch])

  // 左侧「全选」按钮：以当前已加载项是否全部选中作为标签依据
  const allLoadedSelected = leftItems.length > 0 && leftItems.every(c => selectedKeys.has(c.uniqueKey))

  // 保存
  const handleSave = async () => {
    setSaving(true)
    try {
      const cardItems: CardRelationItem[] = []
      for (const key of selectedKeys) {
        const card = cardCache.get(key)
        if (card && card.id !== undefined) {
          cardItems.push({
            card_id: card.id,
            source: card.source,
            dock_record_id: card.dockRecordId ?? null,
          })
        }
      }
      const result = await updateItemCards(itemId, cardItems)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '关联卡券保存成功' })
        onSaved()
        onClose()
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setSaving(false)
    }
  }

  // 卡券来源标签
  const sourceBadge = (source: UnifiedCardItem['source']) => {
    if (source === 'own') {
      return <span className="inline-block px-1 py-0.5 mr-1 rounded text-[10px] font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">自有</span>
    }
    if (source === 'dock_l1') {
      return <span className="inline-block px-1 py-0.5 mr-1 rounded text-[10px] font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">一级对接</span>
    }
    return <span className="inline-block px-1 py-0.5 mr-1 rounded text-[10px] font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">二级对接</span>
  }

  // 卡券副标题（来源标签 + 类型/对接名 + 规格 + 禁用）
  const cardSubtitle = (card: UnifiedCardItem, showDisabled: boolean) => (
    <>
      {sourceBadge(card.source)}
      {card.source === 'own' && (cardTypeLabels[card.type] || card.type)}
      {card.source !== 'own' && card.dockName && card.dockName}
      {card.is_multi_spec && ` | ${card.spec_name}: ${card.spec_value}`}
      {showDisabled && !card.enabled && ' | 已禁用'}
    </>
  )

  return (
    <div className="modal-overlay" style={{ zIndex: 60 }}>
      <div className="modal-content max-w-5xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="modal-header flex items-center justify-between flex-shrink-0">
          <div>
            <h2 className="text-lg font-semibold flex items-center gap-2">
              <Ticket className="w-5 h-5 text-blue-500" />
              关联卡券
            </h2>
            <p className="text-sm text-gray-500 mt-1">商品: {itemName}</p>
          </div>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg">
            <X className="w-4 h-4 text-gray-500" />
          </button>
        </div>

        <div className="modal-body flex-1 overflow-hidden p-0">
          <div className="grid grid-cols-2 gap-0 h-full" style={{ height: '60vh' }}>
            {/* 左侧：卡券列表 */}
            <div className="flex flex-col border-r border-gray-200 dark:border-gray-700 overflow-hidden">
              <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-medium text-gray-900 dark:text-white text-sm">待选卡券</h3>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleSelectAll(!allLoadedSelected)}
                      disabled={selectAllLoading || leftTotal === 0}
                      className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-colors disabled:opacity-50 ${
                        allLoadedSelected
                          ? 'bg-orange-100 text-orange-700 hover:bg-orange-200 dark:bg-orange-900/30 dark:text-orange-400'
                          : 'bg-blue-100 text-blue-700 hover:bg-blue-200 dark:bg-blue-900/30 dark:text-blue-400'
                      }`}
                    >
                      {selectAllLoading ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : allLoadedSelected ? (
                        <CheckSquare className="w-3.5 h-3.5" />
                      ) : (
                        <Square className="w-3.5 h-3.5" />
                      )}
                      {allLoadedSelected ? '取消全选' : '全选'}
                    </button>
                    <span className="text-xs text-gray-500">共 {leftTotal} 个</span>
                  </div>
                </div>
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                  <input
                    type="text"
                    value={leftSearch}
                    onChange={e => setLeftSearch(e.target.value)}
                    placeholder="搜索卡券名称、类型或对接名..."
                    className="input-ios text-sm pl-8 py-1.5"
                  />
                </div>
              </div>
              <div className="flex-1 overflow-y-auto" onScroll={handleLeftScroll}>
                {loading ? (
                  <div className="flex items-center justify-center py-16">
                    <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                    <span className="ml-2 text-gray-500 text-sm">加载中...</span>
                  </div>
                ) : leftItems.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-gray-400">
                    <Ticket className="w-8 h-8 mb-2" />
                    <p className="text-sm">暂无卡券</p>
                  </div>
                ) : (
                  <>
                    {leftItems.map(card => {
                      const checked = selectedKeys.has(card.uniqueKey)
                      return (
                        <div
                          key={card.uniqueKey}
                          onClick={() => toggleCard(card.uniqueKey)}
                          className={`flex items-center gap-3 px-4 py-2.5 border-b border-gray-100 dark:border-gray-800 cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors ${checked ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}
                        >
                          {checked ? (
                            <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400 flex-shrink-0" />
                          ) : (
                            <Square className="w-4 h-4 text-gray-400 flex-shrink-0" />
                          )}
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                              {card.name}
                            </p>
                            <p className="text-xs text-gray-500 truncate">
                              {cardSubtitle(card, true)}
                            </p>
                          </div>
                          {card.source === 'own' && (
                          <button
                            onClick={(e) => { e.stopPropagation(); openCardDetail(card) }}
                            disabled={detailLoadingKey === card.uniqueKey}
                            className="p-1 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded transition-colors flex-shrink-0 disabled:opacity-50"
                            title="查看详情"
                          >
                            {detailLoadingKey === card.uniqueKey ? (
                              <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
                            ) : (
                              <Eye className="w-4 h-4 text-blue-500" />
                            )}
                          </button>
                          )}
                        </div>
                      )
                    })}
                    {leftLoadingMore && (
                      <div className="py-3 flex items-center justify-center text-gray-400">
                        <Loader2 className="w-4 h-4 animate-spin mr-2" />
                        <span className="text-xs">加载中...</span>
                      </div>
                    )}
                    {!leftLoadingMore && leftItems.length < leftTotal && (
                      <div className="py-2 text-center text-xs text-gray-400">
                        向下滚动加载更多（剩余 {leftTotal - leftItems.length} 个）
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>

            {/* 右侧：已选卡券 */}
            <div className="flex flex-col overflow-hidden">
              <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-green-50 dark:bg-green-900/20">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-medium text-green-700 dark:text-green-400 text-sm">已选卡券</h3>
                  <span className="text-xs text-green-600 dark:text-green-500 font-medium">{selectedKeys.size} 个</span>
                </div>
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                  <input
                    type="text"
                    value={rightSearch}
                    onChange={e => setRightSearch(e.target.value)}
                    placeholder="搜索已选卡券..."
                    className="input-ios text-sm pl-8 py-1.5"
                  />
                </div>
              </div>
              <div className="flex-1 overflow-y-auto" onScroll={handleRightScroll}>
                {selectedCards.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-gray-400">
                    <Ticket className="w-8 h-8 mb-2" />
                    <p className="text-sm">{selectedKeys.size === 0 ? '请在左侧勾选卡券' : '无匹配结果'}</p>
                  </div>
                ) : (
                  <>
                    {selectedCards.slice(0, rightVisibleCount).map(card => (
                      <div
                        key={card.uniqueKey}
                        className="flex items-center gap-3 px-4 py-2.5 border-b border-gray-100 dark:border-gray-800"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                            {card.name}
                          </p>
                          <p className="text-xs text-gray-500 truncate">
                            {cardSubtitle(card, false)}
                          </p>
                        </div>
                        {card.source === 'own' && (
                        <button
                          onClick={() => openCardDetail(card)}
                          disabled={detailLoadingKey === card.uniqueKey}
                          className="p-1 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded transition-colors flex-shrink-0 disabled:opacity-50"
                          title="查看详情"
                        >
                          {detailLoadingKey === card.uniqueKey ? (
                            <Loader2 className="w-4 h-4 text-blue-500 animate-spin" />
                          ) : (
                            <Eye className="w-4 h-4 text-blue-500" />
                          )}
                        </button>
                        )}
                        <button
                          onClick={() => toggleCard(card.uniqueKey)}
                          className="text-red-500 hover:text-red-600 p-1 hover:bg-red-50 rounded transition-colors flex-shrink-0"
                          title="移除"
                        >
                          <X className="w-4 h-4" />
                        </button>
                      </div>
                    ))}
                    {selectedCards.length > rightVisibleCount && (
                      <div className="py-2 text-center text-xs text-gray-400">
                        向下滚动加载更多（剩余 {selectedCards.length - rightVisibleCount} 个）
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* 卡券详情弹窗 */}
        {viewingCard && (
          <CardDetailModal
            card={viewingCard}
            onClose={() => setViewingCard(null)}
            zIndex={70}
          />
        )}

        <div className="modal-footer flex-shrink-0">
          <button onClick={onClose} className="btn-ios-secondary" disabled={saving}>
            取消
          </button>
          <button onClick={handleSave} className="btn-ios-primary" disabled={saving || loading}>
            {saving ? (
              <span className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                保存中...
              </span>
            ) : (
              `保存 (${selectedKeys.size} 个卡券)`
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
