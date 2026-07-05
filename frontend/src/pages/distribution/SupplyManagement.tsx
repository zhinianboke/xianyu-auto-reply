/**
 * 货源广场页面
 * 
 * 功能：展示所有可对接的卡券列表，支持搜索和类型过滤
 * 包含两个Tab：卡券货源（一级分销）和分销商货源（二级分销）
 */
import { useState, useEffect, useCallback, useRef } from 'react'
import { Search, RefreshCw, PackageSearch, Link, Unlink } from 'lucide-react'
import { getSupplyCards, deleteDockRecord } from '@/api/distribution'
import type { SupplyCard } from '@/api/distribution'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { DockModal } from './DockModal'
import { SubSupplyTab } from './SubSupplyTab'
import type { SubSupplyTabRef } from './SubSupplyTab'

// 卡券类型标签
const cardTypeLabels: Record<string, string> = {
  api: 'API',
  text: '文本',
  data: '批量',
  image: '图片',
}

// 卡券类型样式
const cardTypeStyles: Record<string, string> = {
  api: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  text: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  data: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  image: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
}

export function SupplyManagement() {
  const { addToast } = useUIStore()
  const { user } = useAuthStore()
  const [activeTab, setActiveTab] = useState<'card' | 'sub'>('card')
  const [loading, setLoading] = useState(true)
  const [cards, setCards] = useState<SupplyCard[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [totalPages, setTotalPages] = useState(0)
  const [searchText, setSearchText] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [dockModalOpen, setDockModalOpen] = useState(false)
  const [selectedCard, setSelectedCard] = useState<SupplyCard | null>(null)
  const subSupplyRef = useRef<SubSupplyTabRef>(null)

  // 取消对接
  const handleCancelDock = async (card: SupplyCard) => {
    if (!card.dock_record_id) return
    try {
      const result = await deleteDockRecord(card.dock_record_id)
      if (result.success) {
        addToast({ type: 'success', message: '已取消对接' })
        loadData(page, pageSize)
      } else {
        addToast({ type: 'error', message: result.message || '取消对接失败' })
      }
    } catch {
      addToast({ type: 'error', message: '取消对接失败' })
    }
  }

  // 加载数据
  // search / type 显式传参，避免「重置」时闭包读取到旧的 state 值
  const loadData = useCallback(async (
    p: number = page,
    ps: number = pageSize,
    search: string = searchText,
    type: string = typeFilter,
  ) => {
    setLoading(true)
    try {
      const result = await getSupplyCards(p, ps, search, type)
      setCards(result.list)
      setTotal(result.total)
      setPage(result.page)
      setPageSize(result.page_size)
      setTotalPages(result.total_pages)
    } catch {
      addToast({ type: 'error', message: '加载货源列表失败' })
    } finally {
      setLoading(false)
    }
  }, [searchText, typeFilter, page, pageSize, addToast])

  // 首次挂载初始加载
  useEffect(() => {
    loadData(1, pageSize)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 点击「查询」或搜索框回车：使用当前草稿的 searchText + typeFilter 回到第 1 页
  const handleSearch = () => {
    loadData(1, pageSize, searchText, typeFilter)
  }

  // 点击「重置」：清空筛选并立即以空值重载（显式传空，规避旧 state）
  const handleReset = () => {
    setSearchText('')
    setTypeFilter('')
    loadData(1, pageSize, '', '')
  }

  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return
    loadData(newPage, pageSize)
  }

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize)
    loadData(1, newSize)
  }

  return (
    <div className="space-y-4">
      {/* 页头 */}
      <div className="page-header flex-between flex-wrap gap-4">
        <div>
          <h1 className="page-title">货源广场</h1>
          <p className="page-description">浏览所有可对接的卡券货源</p>
        </div>
        <div className="flex items-center gap-2">
          {activeTab === 'card' && (
            <button onClick={() => loadData(page, pageSize)} className="btn-ios-secondary">
              <RefreshCw className="w-4 h-4" />
              刷新
            </button>
          )}
          {activeTab === 'sub' && (
            <button onClick={() => subSupplyRef.current?.refresh()} className="btn-ios-secondary">
              <RefreshCw className="w-4 h-4" />
              刷新
            </button>
          )}
        </div>
      </div>

      {/* Tab 切换 */}
      <div className="flex border-b border-slate-200 dark:border-slate-700">
        <button
          onClick={() => setActiveTab('card')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'card'
              ? 'border-blue-500 text-blue-600 dark:text-blue-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
          }`}
        >
          卡券货源
        </button>
        <button
          onClick={() => setActiveTab('sub')}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
            activeTab === 'sub'
              ? 'border-blue-500 text-blue-600 dark:text-blue-400'
              : 'border-transparent text-gray-500 hover:text-gray-700 dark:hover:text-gray-300'
          }`}
        >
          分销商货源
        </button>
      </div>

      {/* 二级分销货源Tab */}
      {activeTab === 'sub' && <SubSupplyTab ref={subSupplyRef} />}

      {/* 卡券货源Tab - 搜索和过滤 + 表格 + 分页合卡 */}
      {activeTab === 'card' && (<>
      <div
        className="vben-card flex flex-col"
        style={{ height: 'calc(100vh - 260px)', minHeight: '420px' }}
      >
        {/* 卡片头：搜索 + 过滤 */}
        <div className="flex-shrink-0 vben-card-header flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <h2 className="vben-card-title">卡券货源列表</h2>
            <span className="badge-primary">{total} 条货源</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSearch() }}
                className="input-ios pl-9"
                placeholder="搜索卡券名称或描述..."
              />
            </div>
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="input-ios w-auto min-w-[120px]"
            >
              <option value="">全部类型</option>
              <option value="api">API</option>
              <option value="text">文本</option>
              <option value="data">批量</option>
              <option value="image">图片</option>
            </select>
            {/* 查询 / 重置 按钮组：右对齐，重置仅在有筛选值时显示 */}
            <div className="flex items-center gap-2 ml-auto">
              <button onClick={handleSearch} className="btn-ios-primary">
                查询
              </button>
              {(searchText || typeFilter) && (
                <button onClick={handleReset} className="btn-ios-secondary text-red-500">
                  重置
                </button>
              )}
            </div>
          </div>
        </div>

        {/* 表格主体：横向 + 纵向滚动，粘性表头 */}
        <div className="flex-1 overflow-x-auto overflow-y-auto scrollbar-visible">
          {loading ? (
            <PageLoading />
          ) : (
            <table className="table-ios">
              <thead className="sticky top-0 bg-slate-50 dark:bg-slate-700/50 z-10">
                <tr>
                  <th className="whitespace-nowrap">ID</th>
                  <th className="whitespace-nowrap">名称</th>
                  <th className="whitespace-nowrap">类型</th>
                  <th className="whitespace-nowrap">对接价格</th>
                  <th className="whitespace-nowrap">最低售价</th>
                  <th className="whitespace-nowrap">手续费支付方</th>
                  <th className="whitespace-nowrap">规格</th>
                  <th className="whitespace-nowrap">描述</th>
                  <th className="whitespace-nowrap">发布时间</th>
                  <th className="whitespace-nowrap">操作</th>
                </tr>
              </thead>
              <tbody>
                {cards.length === 0 ? (
                  <tr>
                    <td colSpan={10}>
                      <div className="empty-state py-8">
                        <PackageSearch className="empty-state-icon" />
                        <p className="text-gray-500">
                          {searchText || typeFilter ? '没有匹配的货源' : '暂无可对接的货源'}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  cards.map(card => (
                    <tr key={card.id}>
                      <td className="text-sm text-gray-500">{card.id}</td>
                      <td className="font-medium text-gray-900 dark:text-white">
                        {card.name}
                      </td>
                      <td>
                        <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${cardTypeStyles[card.type] || ''}`}>
                          {cardTypeLabels[card.type] || card.type}
                        </span>
                      </td>
                      <td className="text-sm">
                        {card.price ? (
                          <span className="text-amber-600 dark:text-amber-400 font-medium">¥{card.price}</span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td className="text-sm">
                        {card.min_price ? (
                          <span className="text-orange-600 dark:text-orange-400 font-medium">¥{card.min_price}</span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td className="text-sm">
                        {card.fee_payer === 'distributor' ? (
                          <span className="text-blue-600 dark:text-blue-400">分销主支付</span>
                        ) : card.fee_payer === 'dealer' ? (
                          <span className="text-green-600 dark:text-green-400">分销商支付</span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td>
                        {card.is_multi_spec ? (
                          <span className="text-xs text-blue-600">{card.spec_name}: {card.spec_value}</span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td className="max-w-[200px]">
                        <span className="text-xs text-gray-500 truncate block" title={card.description || ''}>
                          {card.description || '-'}
                        </span>
                      </td>
                      <td className="text-xs text-gray-500 whitespace-nowrap">
                        {card.created_at ? new Date(card.created_at).toLocaleString('zh-CN') : '-'}
                      </td>
                      <td>
                        {card.is_docked ? (
                          <button
                            onClick={() => handleCancelDock(card)}
                            className="btn-ios-secondary btn-sm text-red-500 hover:text-red-600"
                          >
                            <Unlink className="w-3.5 h-3.5" />
                            取消对接
                          </button>
                        ) : card.user_id === user?.user_id ? (
                          <span className="text-xs text-gray-400">自己的卡券</span>
                        ) : (
                          <button
                            onClick={() => { setSelectedCard(card); setDockModalOpen(true) }}
                            className="btn-ios-primary btn-sm"
                          >
                            <Link className="w-3.5 h-3.5" />
                            对接
                          </button>
                        )}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}
        </div>

        {/* 分页控件：固定底部 */}
        {total > 0 && (
          <div className="flex-shrink-0 flex flex-col sm:flex-row items-center justify-between px-4 py-3 border-t border-slate-200 dark:border-slate-700 gap-3">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
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
              <span className="text-sm text-slate-500 dark:text-slate-400">
                第 {page} / {totalPages || 1} 页
              </span>
              <button
                onClick={() => handlePageChange(page - 1)}
                disabled={page <= 1 || loading}
                className="btn-ios-secondary btn-sm"
              >
                上一页
              </button>
              <button
                onClick={() => handlePageChange(page + 1)}
                disabled={page >= totalPages || loading}
                className="btn-ios-secondary btn-sm"
              >
                下一页
              </button>
            </div>
          </div>
        )}
      </div>
      {/* 对接弹窗 */}
      <DockModal
        isOpen={dockModalOpen}
        onClose={() => setDockModalOpen(false)}
        onSuccess={() => loadData(page, pageSize)}
        card={selectedCard}
      />
      </>)}
    </div>
  )
}
