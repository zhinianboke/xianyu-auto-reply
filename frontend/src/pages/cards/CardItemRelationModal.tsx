/**
 * 卡券关联商品弹窗组件
 *
 * 功能：左右双栏布局，左侧待选商品列表（服务端分页 + 搜索 + 滚动加载更多），
 * 右侧已选商品列表；勾选/取消勾选自动同步两侧显示，保存时写入关联表。
 *
 * 性能：商品可达上万条，左侧改为服务端真分页（滚动到底逐页加载），搜索走后端
 * （防抖）；已选商品数据用 itemCache 累积，供右侧渲染，无需一次性拉取全部。
 * 选中态以 getCardItemIds 为准（含已删除商品的孤儿关联），保存时不丢失。
 */
import { useState, useEffect, useMemo, useRef, type UIEvent } from 'react'
import { X, Loader2, Search, CheckSquare, Square, Package } from 'lucide-react'
import { getItemsPaginated, getAllSelectableItemKeys, getItemsByCardId, type SelectableItem } from '@/api/items'
import { getCardItemIds, updateCardItems } from '@/api/cards'
import { useUIStore } from '@/store/uiStore'
import type { Item } from '@/types'

// 选择项轻量结构（左右列表 + 缓存统一使用）
interface LightItem {
  item_id: string
  title: string
  price: string | null
}

// 每次向后端请求的行数
const REQUEST_PAGE_SIZE = 50
// 右侧已选列表每次渲染的行数（前端分批渲染，避免选中过多时 DOM 过重）
const RIGHT_PAGE_SIZE = 60
// 搜索防抖时长（毫秒）
const SEARCH_DEBOUNCE = 300

// 完整商品(Item) → 轻量项
const itemToLight = (it: Item): LightItem => ({
  item_id: it.item_id,
  title: it.title || it.item_title || it.item_id,
  price: (it.price || it.item_price || null) as string | null,
})

// 后端轻量商品项 → 轻量项
const selectableToLight = (s: SelectableItem): LightItem => ({
  item_id: s.item_id,
  title: s.title || s.item_id,
  price: s.price ?? null,
})

interface CardItemRelationModalProps {
  /** 卡券ID */
  cardId: number
  /** 卡券名称（用于弹窗标题） */
  cardName: string
  /** 关闭回调 */
  onClose: () => void
  /** 保存成功回调 */
  onSaved: () => void
  /** 是否只读模式（仅查看，不可编辑） */
  readonly?: boolean
}

export function CardItemRelationModal({ cardId, cardName, onClose, onSaved, readonly = false }: CardItemRelationModalProps) {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  // 左侧：服务端分页列表
  const [leftItems, setLeftItems] = useState<LightItem[]>([])
  const [leftPage, setLeftPage] = useState(1)
  const [leftTotal, setLeftTotal] = useState(0)
  const [leftLoadingMore, setLeftLoadingMore] = useState(false)
  const loadingMoreRef = useRef(false)

  // 选中态与已选商品数据缓存（累积：已关联 + 已加载页 + 全选结果）
  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(new Set())
  const [itemCache, setItemCache] = useState<Map<string, LightItem>>(new Map())

  // 搜索：leftSearch 为输入值，appliedSearch 为防抖后真正生效的查询词
  const [leftSearch, setLeftSearch] = useState('')
  const [appliedSearch, setAppliedSearch] = useState('')
  const [rightSearch, setRightSearch] = useState('')
  const [rightVisibleCount, setRightVisibleCount] = useState(RIGHT_PAGE_SIZE)
  const [selectAllLoading, setSelectAllLoading] = useState(false)

  // 合并一批商品进缓存
  const mergeCache = (items: LightItem[]) => {
    if (items.length === 0) return
    setItemCache(prev => {
      const next = new Map(prev)
      for (const it of items) next.set(it.item_id, it)
      return next
    })
  }

  // 首次加载：已关联商品（右侧展示 + 初始选中态）
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

  // 加载卡券已关联商品：选中态以 getCardItemIds 为准，详情喂缓存供右侧展示
  const loadAssociated = async () => {
    try {
      const [idsResult, detailResult] = await Promise.all([
        getCardItemIds(cardId),
        getItemsByCardId(cardId),
      ])
      const existingIds = idsResult?.data?.item_ids || []
      setSelectedItemIds(new Set(existingIds))
      mergeCache((detailResult?.list || []).map(selectableToLight))
    } catch {
      addToast({ type: 'error', message: '加载已关联商品失败' })
    }
  }

  // 加载/重置到第一页
  const loadFirstPage = async (search: string) => {
    setLoading(true)
    try {
      const res = await getItemsPaginated(1, REQUEST_PAGE_SIZE, undefined, { keyword: search || null })
      const items = (res.data || []).map(itemToLight)
      setLeftItems(items)
      setLeftPage(1)
      setLeftTotal(res.total || 0)
      mergeCache(items)
    } catch {
      addToast({ type: 'error', message: '加载商品失败' })
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
      const res = await getItemsPaginated(nextPage, REQUEST_PAGE_SIZE, undefined, { keyword: appliedSearch || null })
      const items = (res.data || []).map(itemToLight)
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
      setRightVisibleCount(prev => (prev < selectedItems.length ? prev + RIGHT_PAGE_SIZE : prev))
    }
  }

  // 切换商品选中状态
  const toggleItem = (itemId: string) => {
    setSelectedItemIds(prev => {
      const next = new Set(prev)
      if (next.has(itemId)) {
        next.delete(itemId)
      } else {
        next.add(itemId)
      }
      return next
    })
  }

  // 全选/取消全选当前筛选结果（拉取全部匹配项，避免只操作已加载的部分）
  const handleSelectAll = async (select: boolean) => {
    setSelectAllLoading(true)
    try {
      const res = await getAllSelectableItemKeys(appliedSearch)
      const items = (res.list || []).map(selectableToLight)
      mergeCache(items)
      const ids = items.map(i => i.item_id)
      setSelectedItemIds(prev => {
        const next = new Set(prev)
        if (select) {
          ids.forEach(id => next.add(id))
        } else {
          ids.forEach(id => next.delete(id))
        }
        return next
      })
    } catch {
      addToast({ type: 'error', message: '全选加载失败' })
    } finally {
      setSelectAllLoading(false)
    }
  }

  // 右侧已选商品列表（从缓存按选中ID取，缺失则用ID兜底展示，保证孤儿关联可见可移除）
  const selectedItems = useMemo(() => {
    const items: LightItem[] = []
    for (const id of selectedItemIds) {
      items.push(itemCache.get(id) || { item_id: id, title: id, price: null })
    }
    if (!rightSearch) return items
    const kw = rightSearch.toLowerCase()
    return items.filter(item =>
      (item.title || '').toLowerCase().includes(kw) ||
      item.item_id.toLowerCase().includes(kw)
    )
  }, [selectedItemIds, itemCache, rightSearch])

  // 左侧「全选」按钮：以当前已加载项是否全部选中作为标签依据
  const allLoadedSelected = leftItems.length > 0 && leftItems.every(i => selectedItemIds.has(i.item_id))

  // 保存
  const handleSave = async () => {
    setSaving(true)
    try {
      await updateCardItems(cardId, Array.from(selectedItemIds))
      addToast({ type: 'success', message: '关联商品保存成功' })
      onSaved()
      onClose()
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" style={{ zIndex: 60 }}>
      <div className="modal-content max-w-5xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="modal-header flex items-center justify-between flex-shrink-0">
          <h2 className="text-lg font-semibold">
            {readonly ? '查看关联商品' : '关联商品'} - {cardName}
          </h2>
          <button onClick={onClose} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-800 rounded-lg">
            <X className="w-4 h-4 text-gray-500" />
          </button>
        </div>

        <div className="modal-body flex-1 overflow-hidden p-0">
          <div className="grid grid-cols-2 gap-0 h-full" style={{ height: '60vh' }}>
            {/* 左侧：商品列表 */}
            <div className="flex flex-col overflow-hidden border-r border-gray-200 dark:border-gray-700">
              <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-medium text-gray-900 dark:text-white text-sm">待选商品</h3>
                  <div className="flex items-center gap-2">
                    {!readonly && (
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
                    )}
                    <span className="text-xs text-gray-500">共 {leftTotal} 个</span>
                  </div>
                </div>
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                  <input
                    type="text"
                    value={leftSearch}
                    onChange={e => setLeftSearch(e.target.value)}
                    placeholder="搜索商品名称或ID..."
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
                    <Package className="w-8 h-8 mb-2" />
                    <p className="text-sm">暂无商品</p>
                  </div>
                ) : (
                  <>
                    {leftItems.map(item => {
                      const checked = selectedItemIds.has(item.item_id)
                      return (
                        <div
                          key={item.item_id}
                          onClick={() => !readonly && toggleItem(item.item_id)}
                          className={`flex items-center gap-3 px-4 py-2.5 border-b border-gray-100 dark:border-gray-800 transition-colors ${readonly ? '' : 'cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/20'} ${checked ? 'bg-blue-50 dark:bg-blue-900/20' : ''}`}
                        >
                          {checked ? (
                            <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400 flex-shrink-0" />
                          ) : (
                            <Square className="w-4 h-4 text-gray-400 flex-shrink-0" />
                          )}
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                              {item.title}
                            </p>
                            <p className="text-xs text-gray-500 truncate">
                              ID: {item.item_id}
                              {item.price ? ` | ¥${item.price}` : ''}
                            </p>
                          </div>
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

            {/* 右侧：已选商品 */}
            <div className="flex overflow-hidden flex-col">
              <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-green-50 dark:bg-green-900/20">
                <div className="flex items-center justify-between mb-2">
                  <h3 className="font-medium text-green-700 dark:text-green-400 text-sm">{readonly ? '已关联商品' : '已选商品'}</h3>
                  <span className="text-xs text-green-600 dark:text-green-500 font-medium">{selectedItemIds.size} 个</span>
                </div>
                <div className="relative">
                  <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                  <input
                    type="text"
                    value={rightSearch}
                    onChange={e => setRightSearch(e.target.value)}
                    placeholder="搜索已选商品..."
                    className="input-ios text-sm pl-8 py-1.5"
                  />
                </div>
              </div>
              <div className="flex-1 overflow-y-auto" onScroll={handleRightScroll}>
                {selectedItems.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-8 text-gray-400">
                    <Package className="w-8 h-8 mb-2" />
                    <p className="text-sm">{selectedItemIds.size === 0 ? '请在左侧勾选商品' : '无匹配结果'}</p>
                  </div>
                ) : (
                  <>
                    {selectedItems.slice(0, rightVisibleCount).map(item => (
                      <div
                        key={item.item_id}
                        className="flex items-center gap-3 px-4 py-2.5 border-b border-gray-100 dark:border-gray-800"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                            {item.title}
                          </p>
                          <p className="text-xs text-gray-500 truncate">
                            ID: {item.item_id}
                            {item.price ? ` | ¥${item.price}` : ''}
                          </p>
                        </div>
                        {!readonly && (
                          <button
                            onClick={() => toggleItem(item.item_id)}
                            className="text-red-500 hover:text-red-600 p-1 hover:bg-red-50 rounded transition-colors flex-shrink-0"
                            title="移除"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        )}
                      </div>
                    ))}
                    {selectedItems.length > rightVisibleCount && (
                      <div className="py-2 text-center text-xs text-gray-400">
                        向下滚动加载更多（剩余 {selectedItems.length - rightVisibleCount} 个）
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="modal-footer flex-shrink-0">
          <button onClick={onClose} className="btn-ios-secondary" disabled={saving}>
            {readonly ? '关闭' : '取消'}
          </button>
          {!readonly && (
            <button onClick={handleSave} className="btn-ios-primary" disabled={saving || loading}>
              {saving ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  保存中...
                </span>
              ) : (
                `保存 (${selectedItemIds.size} 个商品)`
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
