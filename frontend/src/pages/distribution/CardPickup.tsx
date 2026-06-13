/**
 * 分销卡券页面
 *
 * 功能：
 * 1. 选择卡券商 + 搜索，查询上游卡券商品列表（后端分页）
 * 2. 展开商品查看各规格库存并提货
 * 3. 查看商品详情（含使用说明）
 * 4. 提货后返回订单号与卡密，支持复制
 *
 * 说明：API 密钥由后台从系统设置（分销设置-对接卡密秘钥）统一读取，本页面无需输入密钥。
 */
import { useState, useEffect, useCallback, Fragment } from 'react'
import { Search, RefreshCw, Gift, ChevronRight, ChevronDown, Eye, Copy, X } from 'lucide-react'
import {
  getCardSources,
  getCardGoods,
  getCardGoodsDetail,
  getCardGoodsStock,
  purchaseCard,
  getCardPurchaseUrl,
  type CardSource,
  type CardGoods,
  type CardSub,
  type CardGoodsDetail,
  type CardStockSub,
  type CardPurchaseResult,
} from '@/api/cardDock'
import { useUIStore } from '@/store/uiStore'
import { ButtonLoading } from '@/components/common/Loading'
import { SafeHtml } from '@/components/common/SafeHtml'

// 取成本价（优先对接价）
const costPriceText = (item: { docking_price?: string | number; price?: string | number }): string => {
  const value = item.docking_price ?? item.price
  return value === undefined || value === null || value === '' ? '-' : `¥${value}`
}

export function CardPickup() {
  const { addToast } = useUIStore()

  // 卡券商
  const [sources, setSources] = useState<CardSource[]>([])
  const [sourcesLoading, setSourcesLoading] = useState(false)
  const [sourceCode, setSourceCode] = useState('')

  // 商品查询
  const [search, setSearch] = useState('')
  const [goodsList, setGoodsList] = useState<CardGoods[]>([])
  const [goodsLoading, setGoodsLoading] = useState(false)
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(20)
  const [queried, setQueried] = useState(false)

  // 展开行库存：goodsId -> (subId -> stock)
  const [expandedIds, setExpandedIds] = useState<number[]>([])
  const [stockMap, setStockMap] = useState<Record<number, Record<number, number | string>>>({})
  const [stockLoadingIds, setStockLoadingIds] = useState<number[]>([])

  // 详情弹窗
  const [detailVisible, setDetailVisible] = useState(false)
  const [detailLoading, setDetailLoading] = useState(false)
  const [detailData, setDetailData] = useState<CardGoodsDetail | null>(null)
  const [detailStock, setDetailStock] = useState<CardStockSub[]>([])

  // 提货弹窗
  const [purchaseVisible, setPurchaseVisible] = useState(false)
  const [purchaseLoading, setPurchaseLoading] = useState(false)
  const [purchaseTarget, setPurchaseTarget] = useState<{ goodsId: number; subId: number; subName: string } | null>(null)
  const [purchaseQty, setPurchaseQty] = useState(1)
  const [purchaseResult, setPurchaseResult] = useState<CardPurchaseResult | null>(null)
  const [purchaseError, setPurchaseError] = useState('')

  const totalPages = Math.max(1, Math.ceil(total / perPage))

  // 加载卡券商
  const loadSources = useCallback(async () => {
    setSourcesLoading(true)
    try {
      const res = await getCardSources()
      if (res.success) {
        setSources(res.data || [])
      } else {
        addToast({ type: 'error', message: res.message || '获取卡券商失败' })
        setSources([])
      }
    } finally {
      setSourcesLoading(false)
    }
  }, [addToast])

  useEffect(() => {
    loadSources()
  }, [loadSources])

  // 查询商品
  const loadGoods = useCallback(async (targetPage: number, targetPerPage: number) => {
    if (!sourceCode) {
      addToast({ type: 'warning', message: '请先选择卡券商' })
      return
    }
    setGoodsLoading(true)
    try {
      const res = await getCardGoods(sourceCode, targetPage, targetPerPage, search.trim())
      if (res.success) {
        const data = res.data || { data: [], total: 0, current_page: targetPage }
        setGoodsList(data.data || [])
        setTotal(Number(data.total) || 0)
        setPage(Number(data.current_page) || targetPage)
        setQueried(true)
        setExpandedIds([])
        setStockMap({})
      } else {
        addToast({ type: 'error', message: res.message || '查询商品失败' })
      }
    } finally {
      setGoodsLoading(false)
    }
  }, [sourceCode, search, addToast])

  const handleQuery = () => {
    setPage(1)
    loadGoods(1, perPage)
  }

  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages || goodsLoading) return
    loadGoods(newPage, perPage)
  }

  const handlePerPageChange = (newPerPage: number) => {
    setPerPage(newPerPage)
    setPage(1)
    if (queried) {
      loadGoods(1, newPerPage)
    }
  }

  // 展开/收起商品行，展开时按需加载规格库存
  const toggleExpand = async (record: CardGoods) => {
    const isExpanded = expandedIds.includes(record.id)
    if (isExpanded) {
      setExpandedIds((prev) => prev.filter((id) => id !== record.id))
      return
    }
    setExpandedIds((prev) => [...prev, record.id])
    if (stockMap[record.id] || stockLoadingIds.includes(record.id)) {
      return
    }
    setStockLoadingIds((prev) => [...prev, record.id])
    try {
      const res = await getCardGoodsStock(sourceCode, record.id)
      if (res.success) {
        const subStock: Record<number, number | string> = {}
        ;(res.data?.subs || []).forEach((sub) => {
          subStock[sub.sub_id] = sub.stock ?? '-'
        })
        setStockMap((prev) => ({ ...prev, [record.id]: subStock }))
      }
    } finally {
      setStockLoadingIds((prev) => prev.filter((id) => id !== record.id))
    }
  }

  // 查看详情
  const handleViewDetail = async (record: CardGoods) => {
    setDetailVisible(true)
    setDetailLoading(true)
    setDetailData(null)
    setDetailStock([])
    try {
      const [detailRes, stockRes] = await Promise.all([
        getCardGoodsDetail(sourceCode, record.id),
        getCardGoodsStock(sourceCode, record.id),
      ])
      if (detailRes.success) {
        setDetailData(detailRes.data || null)
      } else {
        addToast({ type: 'error', message: detailRes.message || '获取商品详情失败' })
      }
      if (stockRes.success) {
        setDetailStock(stockRes.data?.subs || [])
      }
    } finally {
      setDetailLoading(false)
    }
  }

  // 打开提货弹窗
  const openPurchase = (goodsId: number, sub: CardSub) => {
    setPurchaseTarget({ goodsId, subId: sub.id, subName: sub.name })
    setPurchaseQty(1)
    setPurchaseResult(null)
    setPurchaseError('')
    setPurchaseVisible(true)
  }

  // 复制提货api地址（含 api_key，可直接 GET 调用）
  const handleCopyPurchaseApi = async (goodsId: number, subId: number) => {
    const res = await getCardPurchaseUrl(sourceCode, goodsId, subId, 1)
    if (!res.success || !res.data?.url) {
      addToast({ type: 'error', message: res.message || '获取提货地址失败' })
      return
    }
    navigator.clipboard.writeText(res.data.url).then(() => {
      addToast({ type: 'success', message: '提货API地址已复制到剪贴板' })
    }).catch(() => {
      addToast({ type: 'error', message: '复制失败，请手动复制' })
    })
  }

  // 执行提货
  const handleDoPurchase = async () => {
    if (!purchaseTarget) return
    if (!purchaseQty || purchaseQty < 1) {
      addToast({ type: 'warning', message: '请输入购买数量' })
      return
    }
    setPurchaseLoading(true)
    setPurchaseError('')
    try {
      const res = await purchaseCard(sourceCode, purchaseTarget.goodsId, purchaseTarget.subId, purchaseQty)
      if (res.success) {
        addToast({ type: 'success', message: res.message || '提货成功' })
        setPurchaseResult(res.data || {})
      } else {
        setPurchaseError(res.message || '提货失败')
      }
    } finally {
      setPurchaseLoading(false)
    }
  }

  // 复制卡密
  const handleCopyCards = () => {
    const cards = purchaseResult?.cards || ''
    if (!cards) return
    navigator.clipboard.writeText(cards).then(() => {
      addToast({ type: 'success', message: '卡密已复制到剪贴板' })
    }).catch(() => {
      addToast({ type: 'error', message: '复制失败，请手动复制' })
    })
  }

  return (
    <div className="space-y-4">
      {/* 顶部红色加粗提醒 */}
      <div className="text-red-600 font-bold text-center">
        以下商品均为对接商品，无售后，请谨慎对接或购买
      </div>

      {/* 页头 */}
      <div className="page-header flex-between flex-wrap gap-4">
        <div>
          <h1 className="page-title">分销卡券</h1>
          <p className="page-description">通过对接的上游卡券系统查询商品并提货</p>
        </div>
        <button onClick={loadSources} className="btn-ios-secondary" disabled={sourcesLoading}>
          <RefreshCw className={`w-4 h-4 ${sourcesLoading ? 'animate-spin' : ''}`} />
          刷新卡券商
        </button>
      </div>

      <div
        className="vben-card flex flex-col"
        style={{ height: 'calc(100vh - 220px)', minHeight: '420px' }}
      >
        {/* 工具栏 */}
        <div className="vben-card-header flex-shrink-0 flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <h2 className="vben-card-title">卡券商品</h2>
            {queried && <span className="badge-primary">{total} 件商品</span>}
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            <select
              value={sourceCode}
              onChange={(e) => { setSourceCode(e.target.value); setGoodsList([]); setTotal(0); setQueried(false) }}
              className="input-ios w-full sm:w-52"
            >
              <option value="">{sourcesLoading ? '加载中...' : '请选择卡券商'}</option>
              {sources.map((item) => (
                <option key={item.source_code} value={item.source_code}>{item.source_name}</option>
              ))}
            </select>
            <div className="relative w-full sm:w-60">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleQuery() }}
                className="input-ios pl-9"
                placeholder="商品搜索关键词..."
              />
            </div>
            <button onClick={handleQuery} className="btn-ios-primary" disabled={goodsLoading}>
              {goodsLoading ? <ButtonLoading /> : <Search className="w-4 h-4" />}
              查询
            </button>
          </div>
        </div>

        {/* 商品表格 */}
        <div className="flex-1 overflow-x-auto overflow-y-auto scrollbar-visible">
          {goodsLoading ? (
            <div className="flex justify-center py-8">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : (
            <table className="table-ios min-w-[900px]">
              <thead className="bg-slate-50 dark:bg-slate-700/50">
                <tr>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10 w-10"></th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">商品ID</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">图片</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">商品名称</th>
                  <th className="sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">商品描述</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">成本价</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">销量</th>
                  <th className="whitespace-nowrap sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">规格类型</th>
                  <th className="whitespace-nowrap sticky top-0 right-0 bg-slate-50 dark:bg-slate-700/50 z-20">操作</th>
                </tr>
              </thead>
              <tbody>
                {goodsList.length === 0 ? (
                  <tr>
                    <td colSpan={9}>
                      <div className="empty-state py-12">
                        <Gift className="empty-state-icon" />
                        <p className="text-slate-500 dark:text-slate-400">
                          {queried ? '暂无商品数据' : '请选择卡券商后点击查询'}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  goodsList.map((record) => {
                    const isExpanded = expandedIds.includes(record.id)
                    const hasSubs = Array.isArray(record.subs) && record.subs.length > 0
                    const subStock = stockMap[record.id] || {}
                    const loadingStock = stockLoadingIds.includes(record.id)
                    return (
                      <Fragment key={record.id}>
                        <tr
                          className={hasSubs ? 'cursor-pointer' : ''}
                          onClick={() => hasSubs && toggleExpand(record)}
                        >
                          <td className="whitespace-nowrap text-slate-400">
                            {hasSubs ? (isExpanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />) : null}
                          </td>
                          <td className="whitespace-nowrap text-sm text-slate-500 dark:text-slate-400">{record.id}</td>
                          <td className="whitespace-nowrap">
                            {record.picture ? (
                              <img src={record.picture} alt="" className="w-10 h-10 rounded object-cover" />
                            ) : <span className="text-slate-400">-</span>}
                          </td>
                          <td className="whitespace-nowrap font-medium text-slate-900 dark:text-white max-w-[200px] truncate" title={record.name}>
                            {record.name}
                          </td>
                          <td className="text-sm text-slate-500 dark:text-slate-400 max-w-[260px] truncate" title={record.description || ''}>
                            {record.description || '-'}
                          </td>
                          <td className="whitespace-nowrap text-sm text-rose-600 dark:text-rose-400 font-medium">
                            {costPriceText(record)}
                          </td>
                          <td className="whitespace-nowrap text-sm text-slate-600 dark:text-slate-300">
                            {record.sales_volume ?? 0}
                          </td>
                          <td className="whitespace-nowrap text-sm">
                            {record.type_name ? (
                              <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                                {record.type_name}
                              </span>
                            ) : <span className="text-slate-400">-</span>}
                          </td>
                          <td className="whitespace-nowrap sticky right-0 bg-white dark:bg-slate-900 z-10">
                            <button
                              onClick={(e) => { e.stopPropagation(); handleViewDetail(record) }}
                              className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 text-sm hover:underline"
                            >
                              <Eye className="w-4 h-4" />
                              详情
                            </button>
                          </td>
                        </tr>
                        {isExpanded && hasSubs && (
                          <tr key={`${record.id}-subs`}>
                            <td colSpan={9} className="bg-slate-50 dark:bg-slate-800/40 p-0">
                              <div className="px-4 py-3">
                                {/* 规格表头：用 grid 固定列宽，保证表头与内容对齐 */}
                                <div className="grid grid-cols-[80px_minmax(160px,1fr)_120px_120px_220px] gap-2 px-3 py-2 text-xs font-medium text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
                                  <span>规格ID</span>
                                  <span>规格名称</span>
                                  <span>成本价</span>
                                  <span>库存</span>
                                  <span>操作</span>
                                </div>
                                {(record.subs || []).map((sub) => (
                                  <div
                                    key={sub.id}
                                    className="grid grid-cols-[80px_minmax(160px,1fr)_120px_120px_220px] gap-2 px-3 py-2 items-center text-sm border-b border-slate-100 dark:border-slate-700/50 last:border-0"
                                  >
                                    <span className="text-slate-500">{sub.id}</span>
                                    <span className="text-slate-700 dark:text-slate-200 truncate" title={sub.name}>{sub.name}</span>
                                    <span className="text-rose-600 dark:text-rose-400">{costPriceText(sub)}</span>
                                    <span className="text-slate-600 dark:text-slate-300">
                                      {loadingStock ? '...' : (subStock[sub.id] ?? '-')}
                                    </span>
                                    <span className="flex items-center gap-2">
                                      <button
                                        onClick={(e) => { e.stopPropagation(); openPurchase(record.id, sub) }}
                                        className="btn-ios-primary btn-sm"
                                      >
                                        提货
                                      </button>
                                      <button
                                        onClick={(e) => { e.stopPropagation(); handleCopyPurchaseApi(record.id, sub.id) }}
                                        className="btn-ios-secondary btn-sm"
                                        title="复制可直接调用的提货API地址"
                                      >
                                        <Copy className="w-3.5 h-3.5" />
                                        复制提货api
                                      </button>
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    )
                  })
                )}
              </tbody>
            </table>
          )}
        </div>

        {/* 分页 */}
        {total > 0 && (
          <div className="flex-shrink-0 flex flex-col sm:flex-row items-center justify-between px-4 py-3 border-t border-slate-200 dark:border-slate-700 gap-3">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <span>每页</span>
              <select
                value={perPage}
                onChange={(e) => handlePerPageChange(Number(e.target.value))}
                className="input-ios w-auto py-1 px-2 text-sm"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>条，共 {total} 条</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-slate-500 dark:text-slate-400">第 {page} / {totalPages} 页</span>
              <button onClick={() => handlePageChange(page - 1)} disabled={page <= 1 || goodsLoading} className="btn-ios-secondary btn-sm">上一页</button>
              <button onClick={() => handlePageChange(page + 1)} disabled={page >= totalPages || goodsLoading} className="btn-ios-secondary btn-sm">下一页</button>
            </div>
          </div>
        )}
      </div>

      {/* 详情弹窗 */}
      {detailVisible && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" />
          <div className="relative w-full max-w-2xl mx-4 bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-h-[80vh] flex flex-col">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700 flex-shrink-0">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white">商品详情</h3>
              <button onClick={() => setDetailVisible(false)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <div className="px-6 py-5 overflow-y-auto">
              {detailLoading ? (
                <div className="flex justify-center py-12">
                  <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
                </div>
              ) : detailData ? (
                <div className="space-y-4">
                  <div className="flex gap-4 items-start">
                    {detailData.picture && (
                      <img src={detailData.picture} alt="" className="w-20 h-20 rounded-lg object-cover flex-shrink-0" />
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="text-base font-semibold text-slate-900 dark:text-white mb-2">{detailData.name || '-'}</div>
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-rose-600 dark:text-rose-400 font-semibold">成本价 {costPriceText(detailData)}</span>
                        {detailData.type_name && (
                          <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">{detailData.type_name}</span>
                        )}
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${detailData.require_login ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400' : 'bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300'}`}>
                          {detailData.require_login ? '需要登录' : '无需登录'}
                        </span>
                      </div>
                      {detailData.description && (
                        <div className="text-sm text-slate-500 dark:text-slate-400 mt-2">{detailData.description}</div>
                      )}
                    </div>
                  </div>

                  <div>
                    <div className="text-sm font-medium text-slate-700 dark:text-slate-200 mb-2">商品详情</div>
                    {detailData.detail
                      ? <SafeHtml html={detailData.detail} className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed break-words" />
                      : <span className="text-sm text-slate-400">暂无</span>}
                  </div>

                  <div>
                    <div className="text-sm font-medium text-slate-700 dark:text-slate-200 mb-2">使用说明</div>
                    {detailData.usage_instructions
                      ? <SafeHtml html={detailData.usage_instructions} className="text-sm text-slate-600 dark:text-slate-300 leading-relaxed break-words" />
                      : <span className="text-sm text-slate-400">暂无</span>}
                  </div>

                  <div>
                    <div className="text-sm font-medium text-slate-700 dark:text-slate-200 mb-2">规格库存</div>
                    <table className="table-ios w-full">
                      <thead>
                        <tr>
                          <th>规格ID</th>
                          <th>规格名称</th>
                          <th>成本价</th>
                          <th>库存</th>
                        </tr>
                      </thead>
                      <tbody>
                        {detailStock.length === 0 ? (
                          <tr><td colSpan={4} className="text-center text-slate-400 py-4">暂无库存信息</td></tr>
                        ) : detailStock.map((sub) => (
                          <tr key={sub.sub_id}>
                            <td className="text-sm text-slate-500">{sub.sub_id}</td>
                            <td className="text-sm text-slate-700 dark:text-slate-200">{sub.sub_name}</td>
                            <td className="text-sm text-rose-600 dark:text-rose-400">{costPriceText(sub)}</td>
                            <td className="text-sm text-slate-600 dark:text-slate-300">{sub.stock ?? '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="text-center text-slate-400 py-12">暂无商品详情</div>
              )}
            </div>
            <div className="px-6 py-4 border-t border-slate-200 dark:border-slate-700 flex justify-end flex-shrink-0">
              <button onClick={() => setDetailVisible(false)} className="btn-ios-secondary">关闭</button>
            </div>
          </div>
        </div>
      )}

      {/* 提货弹窗 */}
      {purchaseVisible && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" />
          <div className="relative w-full max-w-lg mx-4 bg-white dark:bg-slate-800 rounded-xl shadow-2xl">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white">提货</h3>
              <button onClick={() => setPurchaseVisible(false)} className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700">
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>
            <div className="px-6 py-5 space-y-4">
              <div className="text-sm">
                <span className="text-slate-500 dark:text-slate-400">规格：</span>
                <span className="font-medium text-slate-900 dark:text-white">{purchaseTarget?.subName || '-'}</span>
              </div>
              <div className="input-group">
                <label className="input-label">购买数量</label>
                <input
                  type="number"
                  min={1}
                  value={purchaseQty}
                  onChange={(e) => setPurchaseQty(Math.max(1, Math.floor(Number(e.target.value) || 1)))}
                  disabled={!!purchaseResult}
                  className="input-ios w-40"
                />
              </div>

              {purchaseError && !purchaseResult && (
                <div className="px-4 py-3 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 text-sm text-red-600 dark:text-red-400">
                  {purchaseError}
                </div>
              )}

              {purchaseResult && (
                <div className="space-y-3">
                  <div className="flex items-center gap-3 flex-wrap text-sm">
                    <span>订单号：<b className="text-slate-900 dark:text-white">{purchaseResult.order_sn || '-'}</b></span>
                    <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                      {purchaseResult.status_text || '已完成'}
                    </span>
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-sm text-slate-500 dark:text-slate-400">卡密：</span>
                      <button onClick={handleCopyCards} className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 text-sm hover:underline">
                        <Copy className="w-4 h-4" />
                        复制
                      </button>
                    </div>
                    <textarea
                      value={purchaseResult.cards || ''}
                      readOnly
                      className="input-ios min-h-[120px] resize-y font-mono text-sm break-all"
                    />
                  </div>
                </div>
              )}
            </div>
            <div className="px-6 py-4 border-t border-slate-200 dark:border-slate-700 flex justify-end gap-3">
              {purchaseResult ? (
                <button onClick={() => setPurchaseVisible(false)} className="btn-ios-primary">完成</button>
              ) : (
                <>
                  <button onClick={() => setPurchaseVisible(false)} className="btn-ios-secondary">取消</button>
                  <button onClick={handleDoPurchase} disabled={purchaseLoading} className="btn-ios-primary">
                    {purchaseLoading ? <ButtonLoading /> : null}
                    确认提货
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default CardPickup
