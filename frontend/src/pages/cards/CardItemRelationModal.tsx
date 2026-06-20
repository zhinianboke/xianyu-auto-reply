/**
 * 卡券关联商品弹窗组件
 * 
 * 功能：左右双栏布局，左侧待选商品列表，右侧已选商品列表
 * 勾选/取消勾选自动同步两侧显示，保存时写入关联表
 */
import { useState, useEffect, useMemo } from 'react'
import { X, Loader2, Search, CheckSquare, Square, Package } from 'lucide-react'
import { getItems } from '@/api/items'
import { getCardItemIds, updateCardItems } from '@/api/cards'
import { useUIStore } from '@/store/uiStore'
import type { Item } from '@/types'

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
  const [allItems, setAllItems] = useState<Item[]>([])
  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(new Set())
  const [leftSearch, setLeftSearch] = useState('')
  const [rightSearch, setRightSearch] = useState('')

  // 加载商品列表和已关联的商品ID
  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [itemsResult, relResult] = await Promise.all([
        getItems(),
        getCardItemIds(cardId),
      ])
      setAllItems(itemsResult.data || [])
      // 解析已关联的商品ID
      const existingIds = relResult?.data?.item_ids || []
      setSelectedItemIds(new Set(existingIds))
    } catch {
      addToast({ type: 'error', message: '加载数据失败' })
    } finally {
      setLoading(false)
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

  // 左侧过滤后的商品列表
  const filteredLeftItems = useMemo(() => {
    if (!leftSearch) return allItems
    const kw = leftSearch.toLowerCase()
    return allItems.filter(item =>
      (item.title || item.item_title || '').toLowerCase().includes(kw) ||
      item.item_id.toLowerCase().includes(kw)
    )
  }, [allItems, leftSearch])

  // 右侧已选商品列表
  const selectedItems = useMemo(() => {
    const items = allItems.filter(item => selectedItemIds.has(item.item_id))
    if (!rightSearch) return items
    const kw = rightSearch.toLowerCase()
    return items.filter(item =>
      (item.title || item.item_title || '').toLowerCase().includes(kw) ||
      item.item_id.toLowerCase().includes(kw)
    )
  }, [allItems, selectedItemIds, rightSearch])

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

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
            <span className="ml-2 text-gray-500">加载中...</span>
          </div>
        ) : (
          <div className="modal-body flex-1 overflow-hidden p-0">
            <div className="grid grid-cols-2 gap-0 h-full" style={{ height: '60vh' }}>
              {/* 左侧：商品列表 */}
              <div className="flex flex-col overflow-hidden border-r border-gray-200 dark:border-gray-700">
                <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-medium text-gray-900 dark:text-white text-sm">待选商品</h3>
                    <div className="flex items-center gap-2">
                      {!readonly && filteredLeftItems.length > 0 && (
                        <button
                          onClick={() => {
                            const allFilteredIds = filteredLeftItems.map(i => i.item_id)
                            const allSelected = allFilteredIds.every(id => selectedItemIds.has(id))
                            if (allSelected) {
                              setSelectedItemIds(prev => {
                                const next = new Set(prev)
                                allFilteredIds.forEach(id => next.delete(id))
                                return next
                              })
                            } else {
                              setSelectedItemIds(prev => {
                                const next = new Set(prev)
                                allFilteredIds.forEach(id => next.add(id))
                                return next
                              })
                            }
                          }}
                          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                            filteredLeftItems.every(i => selectedItemIds.has(i.item_id))
                              ? 'bg-orange-100 text-orange-700 hover:bg-orange-200 dark:bg-orange-900/30 dark:text-orange-400'
                              : 'bg-blue-100 text-blue-700 hover:bg-blue-200 dark:bg-blue-900/30 dark:text-blue-400'
                          }`}
                        >
                          {filteredLeftItems.every(i => selectedItemIds.has(i.item_id)) ? (
                            <><CheckSquare className="w-3.5 h-3.5" /> 取消全选</>
                          ) : (
                            <><Square className="w-3.5 h-3.5" /> 全选</>
                          )}
                        </button>
                      )}
                      <span className="text-xs text-gray-500">共 {allItems.length} 个</span>
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
                <div className="flex-1 overflow-y-auto">
                  {filteredLeftItems.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-gray-400">
                      <Package className="w-8 h-8 mb-2" />
                      <p className="text-sm">暂无商品</p>
                    </div>
                  ) : (
                    filteredLeftItems.map(item => {
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
                              {item.title || item.item_title || item.item_id}
                            </p>
                            <p className="text-xs text-gray-500 truncate">
                              ID: {item.item_id}
                              {item.price || item.item_price ? ` | ¥${item.price || item.item_price}` : ''}
                            </p>
                          </div>
                        </div>
                      )
                    })
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
                <div className="flex-1 overflow-y-auto">
                  {selectedItems.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-gray-400">
                      <Package className="w-8 h-8 mb-2" />
                      <p className="text-sm">{selectedItemIds.size === 0 ? '请在左侧勾选商品' : '无匹配结果'}</p>
                    </div>
                  ) : (
                    selectedItems.map(item => (
                      <div
                        key={item.item_id}
                        className="flex items-center gap-3 px-4 py-2.5 border-b border-gray-100 dark:border-gray-800"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                            {item.title || item.item_title || item.item_id}
                          </p>
                          <p className="text-xs text-gray-500 truncate">
                            ID: {item.item_id}
                            {item.price || item.item_price ? ` | ¥${item.price || item.item_price}` : ''}
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
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

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
