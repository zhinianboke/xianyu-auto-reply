/**
 * 商品关联卡券选择弹窗组件
 * 
 * 功能：左右双栏布局，左侧待选卡券列表，右侧已选卡券列表
 * 勾选/取消勾选自动同步两侧显示，保存时写入关联表
 */
import { useState, useEffect, useMemo } from 'react'
import { X, Loader2, Search, CheckSquare, Square, Ticket, Eye } from 'lucide-react'
import { getAllCards, getCardsByItemId, updateItemCards, type CardData, type CardRelationItem } from '@/api/cards'
import { getDockRecords } from '@/api/distribution'
import type { DockRecord } from '@/api/distribution'
import { CardDetailModal } from '@/pages/cards/CardDetailModal'
import { useUIStore } from '@/store/uiStore'

// 统一卡券项（自有卡券 + 对接记录）
interface UnifiedCardItem extends CardData {
  source: 'own' | 'dock_l1' | 'dock_l2'
  dockName?: string
  dockRecordId?: number
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
  const [allCards, setAllCards] = useState<UnifiedCardItem[]>([])
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set())
  const [leftSearch, setLeftSearch] = useState('')
  const [rightSearch, setRightSearch] = useState('')
  const [viewingCard, setViewingCard] = useState<CardData | null>(null)

  // 加载卡券列表和已关联的卡券
  useEffect(() => {
    loadData()
  }, [])

  const loadData = async () => {
    setLoading(true)
    try {
      const [cardsData, relResult, dockResult] = await Promise.all([
        getAllCards(),
        getCardsByItemId(itemId),
        getDockRecords(1, 9999),
      ])

      // 自有卡券
      const ownCards: UnifiedCardItem[] = (cardsData || []).map(c => ({
        ...c,
        source: 'own' as const,
        uniqueKey: `own_${c.id}`,
      }))
      const ownCardIds = new Set(ownCards.map(c => c.id).filter((id): id is number => id !== undefined))

      // 对接记录转化为统一项（去除已在自有卡券中存在的 card_id）
      const dockRecords: DockRecord[] = dockResult?.list || []
      const dockCards: UnifiedCardItem[] = dockRecords
        .filter(r => r.status && !ownCardIds.has(r.card_id))
        .map(r => ({
          id: r.card_id,
          name: r.card_name || r.dock_name,
          type: 'api' as const,
          source: r.level === 2 ? 'dock_l2' as const : 'dock_l1' as const,
          dockName: r.dock_name,
          dockRecordId: r.id,
          is_multi_spec: r.is_multi_spec,
          spec_name: r.spec_name,
          spec_value: r.spec_value,
          enabled: r.status,
          price: r.card_price,
          uniqueKey: `dock_${r.id}`,
        }))

      const merged = [...ownCards, ...dockCards]
      setAllCards(merged)

      // 解析已关联的卡券 → 通过 card_source + dock_record_id 精准匹配回 uniqueKey
      const existingCards: CardData[] = relResult?.data || []
      const initialKeys = new Set<string>()
      for (const ec of existingCards) {
        if (ec.id === undefined) continue
        if (ec.card_source && ec.card_source !== 'own' && ec.dock_record_id) {
          // 对接卡券：通过 dock_record_id 匹配
          const key = `dock_${ec.dock_record_id}`
          if (merged.some(c => c.uniqueKey === key)) {
            initialKeys.add(key)
            continue
          }
        }
        // 自有卡券或回退匹配
        const key = `own_${ec.id}`
        if (merged.some(c => c.uniqueKey === key)) {
          initialKeys.add(key)
        }
      }
      setSelectedKeys(initialKeys)
    } catch {
      addToast({ type: 'error', message: '加载数据失败' })
    } finally {
      setLoading(false)
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

  // 左侧过滤后的卡券列表
  const filteredLeftCards = useMemo(() => {
    if (!leftSearch) return allCards
    const kw = leftSearch.toLowerCase()
    return allCards.filter(card =>
      (card.name || '').toLowerCase().includes(kw) ||
      (card.type || '').toLowerCase().includes(kw) ||
      String(card.id).includes(kw)
    )
  }, [allCards, leftSearch])

  // 右侧已选卡券列表
  const selectedCards = useMemo(() => {
    const cards = allCards.filter(card => selectedKeys.has(card.uniqueKey))
    if (!rightSearch) return cards
    const kw = rightSearch.toLowerCase()
    return cards.filter(card =>
      (card.name || '').toLowerCase().includes(kw) ||
      (card.type || '').toLowerCase().includes(kw)
    )
  }, [allCards, selectedKeys, rightSearch])

  // 保存
  const handleSave = async () => {
    setSaving(true)
    try {
      // 构建卡券关联列表
      const cardItems: CardRelationItem[] = []
      for (const card of allCards) {
        if (card.id !== undefined && selectedKeys.has(card.uniqueKey)) {
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

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
            <span className="ml-2 text-gray-500">加载中...</span>
          </div>
        ) : (
          <div className="modal-body flex-1 overflow-hidden p-0">
            <div className="grid grid-cols-2 gap-0 h-full" style={{ height: '60vh' }}>
              {/* 左侧：卡券列表 */}
              <div className="flex flex-col border-r border-gray-200 dark:border-gray-700 overflow-hidden">
                <div className="flex-shrink-0 px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-medium text-gray-900 dark:text-white text-sm">待选卡券</h3>
                    <div className="flex items-center gap-2">
                      {filteredLeftCards.length > 0 && (
                        <button
                          onClick={() => {
                            const allFilteredKeys = filteredLeftCards.map(c => c.uniqueKey)
                            const allSelected = allFilteredKeys.every(k => selectedKeys.has(k))
                            if (allSelected) {
                              setSelectedKeys(prev => {
                                const next = new Set(prev)
                                allFilteredKeys.forEach(k => next.delete(k))
                                return next
                              })
                            } else {
                              setSelectedKeys(prev => {
                                const next = new Set(prev)
                                allFilteredKeys.forEach(k => next.add(k))
                                return next
                              })
                            }
                          }}
                          className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                            filteredLeftCards.every(c => selectedKeys.has(c.uniqueKey))
                              ? 'bg-orange-100 text-orange-700 hover:bg-orange-200 dark:bg-orange-900/30 dark:text-orange-400'
                              : 'bg-blue-100 text-blue-700 hover:bg-blue-200 dark:bg-blue-900/30 dark:text-blue-400'
                          }`}
                        >
                          {filteredLeftCards.every(c => selectedKeys.has(c.uniqueKey)) ? (
                            <><CheckSquare className="w-3.5 h-3.5" /> 取消全选</>
                          ) : (
                            <><Square className="w-3.5 h-3.5" /> 全选</>
                          )}
                        </button>
                      )}
                      <span className="text-xs text-gray-500">共 {allCards.length} 个</span>
                    </div>
                  </div>
                  <div className="relative">
                    <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                    <input
                      type="text"
                      value={leftSearch}
                      onChange={e => setLeftSearch(e.target.value)}
                      placeholder="搜索卡券名称或类型..."
                      className="input-ios text-sm pl-8 py-1.5"
                    />
                  </div>
                </div>
                <div className="flex-1 overflow-y-auto">
                  {filteredLeftCards.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-gray-400">
                      <Ticket className="w-8 h-8 mb-2" />
                      <p className="text-sm">暂无卡券</p>
                    </div>
                  ) : (
                    filteredLeftCards.map(card => {
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
                              {card.source === 'own' ? (
                                <span className="inline-block px-1 py-0.5 mr-1 rounded text-[10px] font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">自有</span>
                              ) : card.source === 'dock_l1' ? (
                                <span className="inline-block px-1 py-0.5 mr-1 rounded text-[10px] font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">一级对接</span>
                              ) : (
                                <span className="inline-block px-1 py-0.5 mr-1 rounded text-[10px] font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">二级对接</span>
                              )}
                              {card.source === 'own' && (cardTypeLabels[card.type] || card.type)}
                              {card.source !== 'own' && card.dockName && card.dockName}
                              {card.is_multi_spec && ` | ${card.spec_name}: ${card.spec_value}`}
                              {!card.enabled && ' | 已禁用'}
                            </p>
                          </div>
                          {card.source === 'own' && (
                          <button
                            onClick={(e) => { e.stopPropagation(); setViewingCard(card) }}
                            className="p-1 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded transition-colors flex-shrink-0"
                            title="查看详情"
                          >
                            <Eye className="w-4 h-4 text-blue-500" />
                          </button>
                          )}
                        </div>
                      )
                    })
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
                <div className="flex-1 overflow-y-auto">
                  {selectedCards.length === 0 ? (
                    <div className="flex flex-col items-center justify-center py-8 text-gray-400">
                      <Ticket className="w-8 h-8 mb-2" />
                      <p className="text-sm">{selectedKeys.size === 0 ? '请在左侧勾选卡券' : '无匹配结果'}</p>
                    </div>
                  ) : (
                    selectedCards.map(card => (
                      <div
                        key={card.uniqueKey}
                        className="flex items-center gap-3 px-4 py-2.5 border-b border-gray-100 dark:border-gray-800"
                      >
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                            {card.name}
                          </p>
                          <p className="text-xs text-gray-500 truncate">
                            {card.source === 'own' ? (
                              <span className="inline-block px-1 py-0.5 mr-1 rounded text-[10px] font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">自有</span>
                            ) : card.source === 'dock_l1' ? (
                              <span className="inline-block px-1 py-0.5 mr-1 rounded text-[10px] font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">一级对接</span>
                            ) : (
                              <span className="inline-block px-1 py-0.5 mr-1 rounded text-[10px] font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">二级对接</span>
                            )}
                            {card.source === 'own' && (cardTypeLabels[card.type] || card.type)}
                            {card.source !== 'own' && card.dockName && card.dockName}
                            {card.is_multi_spec && ` | ${card.spec_name}: ${card.spec_value}`}
                          </p>
                        </div>
                        {card.source === 'own' && (
                        <button
                          onClick={() => setViewingCard(card)}
                          className="p-1 hover:bg-blue-100 dark:hover:bg-blue-900/30 rounded transition-colors flex-shrink-0"
                          title="查看详情"
                        >
                          <Eye className="w-4 h-4 text-blue-500" />
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
                    ))
                  )}
                </div>
              </div>
            </div>
          </div>
        )}

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
