/**
 * 卡券管理页面
 * 
 * 功能：
 * 1. 展示所有卡券列表（分页）
 * 2. 支持启用/禁用卡券
 * 3. 支持删除卡券（单个和批量）
 * 4. 支持搜索过滤
 * 5. 界面风格与商品管理页面保持一致
 */
import { useState, useEffect } from 'react'
import {
  Ticket, RefreshCw, Trash2, Search, Power, PowerOff, Image,
  ChevronLeft, ChevronRight, CheckSquare, Square, Edit2, Copy, Eye, Plus, Link
} from 'lucide-react'
import { getCards, updateCard, deleteCard, batchDeleteCards, type CardData, type CardPaginatedResult } from '@/api/cards'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { CardDetailModal } from './CardDetailModal'
import { CardFormModal, cardToFormData, cardToCopyFormData, emptyCardFormData } from './CardFormModal'
import { CardItemRelationModal } from './CardItemRelationModal'

// 卡券类型标签（与发货配置一致）
const cardTypeLabels: Record<string, string> = {
  api: 'API',
  text: '文本',
  data: '批量',
  image: '图片',
}

// 卡券类型标签样式（与发货配置一致）
const cardTypeBadge: Record<string, string> = {
  api: 'badge-info',
  text: 'badge-success',
  data: 'badge-warning',
  image: 'badge-purple',
}

export function Cards() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [cards, setCards] = useState<CardData[]>([])
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)
  // 已应用的查询条件（仅在点「查询」或回车时更新，用于实际发起请求）
  const [searchText, setSearchText] = useState('')
  const [typeFilter, setTypeFilter] = useState<string>('')
  // 草稿状态：承接输入框/下拉的即时输入，不触发查询
  const [searchDraft, setSearchDraft] = useState('')
  const [typeDraft, setTypeDraft] = useState<string>('')
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; card: CardData | null }>({ open: false, card: null })
  const [batchDeleteConfirm, setBatchDeleteConfirm] = useState(false)
  const [isImagePreviewOpen, setIsImagePreviewOpen] = useState(false)
  const [previewImageUrl, setPreviewImageUrl] = useState('')
  // 查看明细弹窗
  const [detailCard, setDetailCard] = useState<CardData | null>(null)
  // 编辑/复制弹窗
  const [showFormModal, setShowFormModal] = useState(false)
  const [editingCardId, setEditingCardId] = useState<number | null>(null)
  const [formInitialData, setFormInitialData] = useState(emptyCardFormData)

  // 关联商品弹窗
  const [relationCard, setRelationCard] = useState<CardData | null>(null)
  const [relationReadonly, setRelationReadonly] = useState(false)

  // 分页状态
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  // 加载卡券列表（后端分页）
  const loadCards = async (p?: number, ps?: number, s?: string, t?: string) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    const currentPage = p ?? page
    const currentPageSize = ps ?? pageSize
    const currentSearch = s ?? searchText
    const currentType = t ?? typeFilter
    try {
      setLoading(true)
      const result: CardPaginatedResult = await getCards({
        page: currentPage,
        page_size: currentPageSize,
        search: currentSearch || undefined,
        type: currentType || undefined,
      })
      setCards(result.list || [])
      setTotal(result.total || 0)
      setTotalPages(result.total_pages || 0)
    } catch {
      addToast({ type: 'error', message: '加载卡券列表失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadCards()
  }, [_hasHydrated, isAuthenticated, token])

  // 点击「查询」或搜索框回车：将草稿值应用为查询条件并从第 1 页加载
  const handleSearch = () => {
    setSearchText(searchDraft)
    setTypeFilter(typeDraft)
    setPage(1)
    loadCards(1, pageSize, searchDraft, typeDraft)
  }

  // 重置筛选：清空草稿与已应用条件，并从第 1 页重新加载
  const handleResetFilter = () => {
    setSearchDraft('')
    setTypeDraft('')
    setSearchText('')
    setTypeFilter('')
    setPage(1)
    loadCards(1, pageSize, '', '')
  }

  // 当前页数据即后端返回的列表
  const pagedCards = cards

  // 切换启用/禁用
  const handleToggleEnabled = async (card: CardData) => {
    if (!card.id) return
    try {
      await updateCard(String(card.id), { enabled: !card.enabled })
      addToast({ type: 'success', message: `卡券已${card.enabled ? '禁用' : '启用'}` })
      loadCards()
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  // 删除卡券
  const handleDelete = async () => {
    if (!deleteConfirm.card?.id) return
    try {
      await deleteCard(String(deleteConfirm.card.id))
      addToast({ type: 'success', message: '卡券已删除' })
      setDeleteConfirm({ open: false, card: null })
      loadCards()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    }
  }

  // 批量删除
  const handleBatchDelete = async () => {
    try {
      await batchDeleteCards(Array.from(selectedIds))
      addToast({ type: 'success', message: `成功删除 ${selectedIds.size} 张卡券` })
      setSelectedIds(new Set())
      setBatchDeleteConfirm(false)
      loadCards()
    } catch {
      addToast({ type: 'error', message: '批量删除失败' })
    }
  }

  // 打开新建弹窗
  const openCreateModal = () => {
    setEditingCardId(null)
    setFormInitialData(emptyCardFormData)
    setShowFormModal(true)
  }

  // 打开编辑弹窗
  const openEditModal = (card: CardData) => {
    setEditingCardId(card.id ?? null)
    setFormInitialData(cardToFormData(card))
    setShowFormModal(true)
  }

  // 打开复制弹窗
  const openCopyModal = (card: CardData) => {
    setEditingCardId(null)
    setFormInitialData(cardToCopyFormData(card))
    setShowFormModal(true)
    addToast({ type: 'info', message: '已复制卡券配置，请填写新的卡券名称' })
  }

  // 关闭编辑/复制弹窗
  const closeFormModal = () => {
    setShowFormModal(false)
    setEditingCardId(null)
    setFormInitialData(emptyCardFormData)
  }

  // 全选/取消全选
  const handleSelectAll = () => {
    if (selectedIds.size === pagedCards.length) {
      setSelectedIds(new Set())
    } else {
      setSelectedIds(new Set(pagedCards.map(c => c.id!).filter(Boolean)))
    }
  }

  // 单选
  const handleSelect = (id: number) => {
    const newSet = new Set(selectedIds)
    if (newSet.has(id)) {
      newSet.delete(id)
    } else {
      newSet.add(id)
    }
    setSelectedIds(newSet)
  }

  if (loading && cards.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* 页头（与商品管理一致） */}
      <div className="page-header flex-between flex-wrap gap-4">
        <div>
          <h1 className="page-title">卡券管理</h1>
          <p className="page-description">管理所有卡券信息</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {selectedIds.size > 0 && (
            <button onClick={() => setBatchDeleteConfirm(true)} className="btn-ios-danger">
              <Trash2 className="w-4 h-4" />
              删除选中 ({selectedIds.size})
            </button>
          )}
          {selectedIds.size === 1 && (
            <button
              onClick={() => {
                const card = cards.find(c => selectedIds.has(c.id!))
                if (card) { setRelationReadonly(false); setRelationCard(card) }
              }}
              className="btn-ios-secondary"
            >
              <Link className="w-4 h-4" />
              关联商品
            </button>
          )}
          <button onClick={openCreateModal} className="btn-ios-primary">
            <Plus className="w-4 h-4" />
            新建卡券
          </button>
          <button onClick={() => loadCards()} className="btn-ios-secondary">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {/* 筛选区域（与商品管理一致） */}
      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-end gap-4">
            <div className="input-group">
              <label className="input-label">搜索卡券</label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                <input
                  type="text"
                  value={searchDraft}
                  onChange={e => setSearchDraft(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') handleSearch() }}
                  placeholder="搜索卡券名称或描述..."
                  className="input-ios pl-9"
                />
              </div>
            </div>
            <div className="input-group">
              <label className="input-label">卡券类型</label>
              <select
                value={typeDraft}
                onChange={e => setTypeDraft(e.target.value)}
                className="input-ios"
              >
                <option value="">全部</option>
                <option value="text">文本卡券</option>
                <option value="api">API卡券</option>
                <option value="data">批量数据</option>
                <option value="image">图片卡券</option>
              </select>
            </div>
            <div className="flex items-end gap-2 ml-auto">
              <button onClick={handleSearch} className="btn-ios-primary">
                <Search className="w-4 h-4" />
                查询
              </button>
              {(searchDraft || typeDraft) && (
                <button onClick={handleResetFilter} className="btn-ios-secondary text-red-500">
                  重置筛选
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 卡券列表（与商品管理表格一致） */}
      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 320px)', minHeight: '400px' }}>
        <div className="vben-card-header flex-shrink-0">
          <h2 className="vben-card-title">
            <Ticket className="w-4 h-4" />
            卡券列表
          </h2>
          <span className="badge-primary">{total} 张卡券</span>
        </div>
        <div className="flex-1 overflow-auto">
          {loading ? (
            <div className="flex justify-center py-8">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : (
            <table className="table-ios min-w-[1080px]">
              <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
                <tr>
                  <th className="w-10 whitespace-nowrap">
                    <button
                      onClick={handleSelectAll}
                      className="p-1 hover:bg-gray-100 rounded"
                      title={selectedIds.size === pagedCards.length ? '取消全选' : '全选'}
                    >
                      {selectedIds.size === pagedCards.length && pagedCards.length > 0 ? (
                        <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                      ) : (
                        <Square className="w-4 h-4 text-gray-400" />
                      )}
                    </button>
                  </th>
                  <th className="whitespace-nowrap w-16">ID</th>
                  <th className="whitespace-nowrap min-w-[250px]">名称</th>
                  <th className="whitespace-nowrap">类型</th>
                  <th className="whitespace-nowrap min-w-[300px]">内容预览</th>
                  <th className="whitespace-nowrap">发货设置</th>
                  <th className="whitespace-nowrap">对接信息</th>
                  <th className="whitespace-nowrap">状态</th>
                  <th className="whitespace-nowrap">时间</th>
                  <th className="whitespace-nowrap sticky right-0 bg-slate-50 dark:bg-slate-800">操作</th>
                </tr>
              </thead>
              <tbody>
                {pagedCards.length === 0 ? (
                  <tr>
                    <td colSpan={10}>
                      <div className="empty-state py-8">
                        <Ticket className="empty-state-icon" />
                        <p className="text-gray-500">{searchText || typeFilter ? '没有匹配的卡券' : '暂无卡券数据'}</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  pagedCards.map(card => (
                    <tr key={card.id} className={selectedIds.has(card.id!) ? 'bg-blue-50' : ''}>
                      <td>
                        <button
                          onClick={() => card.id && handleSelect(card.id)}
                          className="p-1 hover:bg-gray-100 rounded"
                        >
                          {selectedIds.has(card.id!) ? (
                            <CheckSquare className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                          ) : (
                            <Square className="w-4 h-4 text-gray-400" />
                          )}
                        </button>
                      </td>
                      <td className="text-xs text-gray-500 align-top">{card.id}</td>
                      {/* 名称列：主名称 + 可选的规格/备注副标题 */}
                      <td className="align-top min-w-[200px] max-w-[280px]">
                        <div className="flex flex-col gap-0.5">
                          <span className="font-medium text-slate-900 dark:text-slate-100 break-words" title={card.name}>
                            {card.name}
                          </span>
                          {card.is_multi_spec && (card.spec_name || card.spec_value) && (
                            <span className="text-[11px] text-blue-600 dark:text-blue-400">
                              规格：{card.spec_name} = {card.spec_value}
                            </span>
                          )}
                          {card.description && (
                            <span
                              className="text-[11px] text-slate-500 dark:text-slate-400 truncate max-w-[260px]"
                              title={card.description}
                            >
                              备注：{card.description}
                            </span>
                          )}
                        </div>
                      </td>
                      {/* 类型徽章 */}
                      <td className="align-top">
                        <span className={`${cardTypeBadge[card.type] || 'badge-gray'} text-xs`}>
                          {cardTypeLabels[card.type] || card.type}
                        </span>
                      </td>
                      {/* 内容预览 */}
                      <td className="max-w-[220px] align-top">
                        {card.type === 'image' ? (
                          card.image_url ? (
                            <button
                              onClick={() => {
                                setPreviewImageUrl(card.image_url || '')
                                setIsImagePreviewOpen(true)
                              }}
                              className="px-2 py-1 text-xs font-medium bg-purple-100 text-purple-700 hover:bg-purple-200 dark:bg-purple-900/30 dark:text-purple-400 rounded transition-colors inline-flex items-center gap-1"
                            >
                              <Image className="w-3 h-3" />
                              查看原图
                            </button>
                          ) : (
                            <span className="text-gray-400 text-sm">暂无图片</span>
                          )
                        ) : (
                          <code className="text-xs bg-gray-100 dark:bg-gray-800 px-2 py-1 rounded truncate block max-w-[220px]">
                            {card.type === 'text' && (card.text_content || '-')}
                            {card.type === 'data' && (card.data_content ? `剩余 ${card.data_content.split('\n').filter((line: string) => line.trim()).length} 条` : '-')}
                            {card.type === 'api' && (card.api_config?.url || '-')}
                            {!['text', 'data', 'api', 'image'].includes(card.type) && '-'}
                          </code>
                        )}
                      </td>
                      {/* 发货设置：发货次数 + 延时 */}
                      <td className="align-top text-xs">
                        <div className="flex flex-col gap-0.5">
                          <span className="text-slate-700 dark:text-slate-300">
                            已发货 <span className="font-medium">{card.delivery_count || 0}</span> 次
                          </span>
                          <span className="text-slate-500 dark:text-slate-400">
                            延时 {card.delay_seconds || 0} 秒
                          </span>
                        </div>
                      </td>
                      {/* 对接信息：可对接时展示价格；不可对接则灰色显示 */}
                      <td className="align-top text-xs">
                        {card.is_dockable ? (
                          <div className="flex flex-col gap-0.5">
                            <span className="text-slate-700 dark:text-slate-300">
                              对接价：
                              {card.price ? (
                                <span className="text-amber-600 dark:text-amber-400 font-medium">¥{card.price}</span>
                              ) : (
                                <span className="text-gray-400">-</span>
                              )}
                            </span>
                            <span className="text-slate-500 dark:text-slate-400">
                              最低价：
                              {card.min_price ? (
                                <span className="text-orange-600 dark:text-orange-400 font-medium">¥{card.min_price}</span>
                              ) : (
                                <span className="text-gray-400">-</span>
                              )}
                            </span>
                            {card.fee_payer === 'distributor' ? (
                              <span className="text-blue-600 dark:text-blue-400">手续费：分销主支付</span>
                            ) : card.fee_payer === 'dealer' ? (
                              <span className="text-green-600 dark:text-green-400">手续费：分销商支付</span>
                            ) : null}
                          </div>
                        ) : (
                          <span className="badge-gray text-xs">不对接</span>
                        )}
                      </td>
                      {/* 状态 */}
                      <td className="align-top">
                        {card.enabled ? (
                          <span className="badge-success text-xs">启用</span>
                        ) : (
                          <span className="badge-gray text-xs">禁用</span>
                        )}
                      </td>
                      {/* 时间：创建 + 更新（副标题） */}
                      <td className="align-top text-gray-500 text-[11px] whitespace-nowrap">
                        <div className="flex flex-col gap-0.5">
                          <span title="创建时间">
                            创建：{card.created_at ? new Date(card.created_at).toLocaleString('zh-CN') : '-'}
                          </span>
                          <span className="text-gray-400" title="更新时间">
                            更新：{card.updated_at ? new Date(card.updated_at).toLocaleString('zh-CN') : '-'}
                          </span>
                        </div>
                      </td>
                      <td className="sticky right-0 bg-white dark:bg-slate-900">
                        <div className="flex gap-1">
                          <button
                            onClick={() => setDetailCard(card)}
                            className="table-action-btn hover:!bg-blue-50"
                            title="查看明细"
                          >
                            <Eye className="w-4 h-4 text-blue-500" />
                          </button>
                          <button
                            onClick={() => openEditModal(card)}
                            className="table-action-btn hover:!bg-blue-50"
                            title="编辑"
                          >
                            <Edit2 className="w-4 h-4 text-blue-500" />
                          </button>
                          <button
                            onClick={() => openCopyModal(card)}
                            className="table-action-btn hover:!bg-cyan-50"
                            title="复制"
                          >
                            <Copy className="w-4 h-4 text-cyan-500" />
                          </button>
                          <button
                            onClick={() => { setRelationReadonly(false); setRelationCard(card) }}
                            className="table-action-btn hover:!bg-green-50"
                            title="管理关联商品"
                          >
                            <Link className="w-4 h-4 text-green-500" />
                          </button>
                          <button
                            onClick={() => handleToggleEnabled(card)}
                            className="table-action-btn hover:!bg-blue-50"
                            title={card.enabled ? '禁用' : '启用'}
                          >
                            {card.enabled ? (
                              <Power className="w-4 h-4 text-green-500" />
                            ) : (
                              <PowerOff className="w-4 h-4 text-gray-400" />
                            )}
                          </button>
                          <button
                            onClick={() => setDeleteConfirm({ open: true, card })}
                            className="table-action-btn hover:!bg-red-50"
                            title="删除"
                          >
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}
        </div>

        {/* 分页控件（与商品管理一致） */}
        {total > 0 && (
          <div className="flex-shrink-0 flex flex-col sm:flex-row items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700 gap-3">
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={e => { const newSize = Number(e.target.value); setPageSize(newSize); setPage(1); loadCards(1, newSize) }}
                className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>条，共 {total} 条</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">
                第 {page} / {totalPages} 页
              </span>
              <button
                onClick={() => { const p = Math.max(1, page - 1); setPage(p); loadCards(p) }}
                disabled={page <= 1}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <button
                onClick={() => { const p = Math.min(totalPages, page + 1); setPage(p); loadCards(p) }}
                disabled={page >= totalPages}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 关联商品弹窗 */}
      {relationCard && (
        <CardItemRelationModal
          cardId={relationCard.id!}
          cardName={relationCard.name}
          onClose={() => { setRelationCard(null); setRelationReadonly(false) }}
          onSaved={loadCards}
          readonly={relationReadonly}
        />
      )}

      {/* 查看明细弹窗 */}
      {detailCard && (
        <CardDetailModal card={detailCard} onClose={() => setDetailCard(null)} />
      )}

      {/* 编辑/复制弹窗 */}
      {showFormModal && (
        <CardFormModal
          cardId={editingCardId}
          initialData={formInitialData}
          onClose={closeFormModal}
          onSaved={loadCards}
        />
      )}

      {/* 图片预览弹窗 */}
      {isImagePreviewOpen && (
        <div className="modal-overlay">
          <div className="modal-content max-w-2xl">
            <div className="modal-header">
              <h2 className="modal-title">图片预览</h2>
              <button onClick={() => setIsImagePreviewOpen(false)} className="modal-close">&times;</button>
            </div>
            <div className="modal-body flex items-center justify-center">
              <img src={previewImageUrl} alt="卡券图片" className="max-w-full max-h-[60vh] object-contain rounded" />
            </div>
          </div>
        </div>
      )}

      {/* 删除确认弹窗 */}
      <ConfirmModal
        isOpen={deleteConfirm.open}
        title="删除卡券"
        message={`确定要删除卡券"${deleteConfirm.card?.name}"吗？此操作不可恢复。`}
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm({ open: false, card: null })}
      />
      <ConfirmModal
        isOpen={batchDeleteConfirm}
        title="批量删除卡券"
        message={`确定要删除选中的 ${selectedIds.size} 张卡券吗？此操作不可恢复。`}
        onConfirm={handleBatchDelete}
        onCancel={() => setBatchDeleteConfirm(false)}
      />
    </div>
  )
}
