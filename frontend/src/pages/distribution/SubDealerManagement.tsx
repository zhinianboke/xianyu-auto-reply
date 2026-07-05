/**
 * 下级分销商管理页面
 * 
 * 功能：一级分销商查看和管理自己的二级分销商列表
 */
import { useState, useEffect, useCallback } from 'react'
import { Search, RefreshCw, Users, Eye } from 'lucide-react'
import { getSubDealers } from '@/api/distribution'
import type { Dealer } from '@/api/distribution'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import { SubDealerDetailModal } from './SubDealerDetailModal'

export function SubDealerManagement() {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [dealers, setDealers] = useState<Dealer[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [totalPages, setTotalPages] = useState(0)
  const [searchText, setSearchText] = useState('')
  const [detailModalOpen, setDetailModalOpen] = useState(false)
  const [selectedDealer, setSelectedDealer] = useState<Dealer | null>(null)

  // 加载数据
  const loadData = useCallback(async (p: number = page, ps: number = pageSize) => {
    setLoading(true)
    try {
      const result = await getSubDealers(p, ps, searchText)
      setDealers(result.list)
      setTotal(result.total)
      setPage(result.page)
      setPageSize(result.page_size)
      setTotalPages(result.total_pages)
    } catch {
      addToast({ type: 'error', message: '加载下级分销商列表失败' })
    } finally {
      setLoading(false)
    }
  }, [searchText, page, pageSize, addToast])

  useEffect(() => {
    loadData(1, pageSize)
  }, [])

  // 点击查询/回车时以当前搜索条件回到第1页
  const handleSearch = () => {
    loadData(1, pageSize)
  }

  // 查看对接明细
  const handleViewDetails = (dealer: Dealer) => {
    setSelectedDealer(dealer)
    setDetailModalOpen(true)
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
          <h1 className="page-title">下级分销商</h1>
          <p className="page-description">管理对接了您的卡券的二级分销商</p>
        </div>
        <button onClick={() => loadData(page, pageSize)} className="btn-ios-secondary">
          <RefreshCw className="w-4 h-4" />
          刷新
        </button>
      </div>

      {/* 搜索 */}
      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative flex-1 min-w-[200px] max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
              <input
                type="text"
                value={searchText}
                onChange={(e) => setSearchText(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSearch() }}
                className="input-ios pl-9"
                placeholder="搜索用户名..."
              />
            </div>
            <span className="text-sm text-gray-500">
              共 {total} 位下级分销商
            </span>
            <button onClick={handleSearch} className="btn-ios-primary ml-auto">
              <Search className="w-4 h-4" />
              查询
            </button>
          </div>
        </div>
      </div>

      {/* 表格 */}
      <div className="vben-card">
        <div className="vben-card-body p-0">
          {loading ? (
            <PageLoading />
          ) : (
            <div className="table-ios-container">
              <table className="table-ios">
                <thead>
                  <tr>
                    <th className="whitespace-nowrap">用户ID</th>
                    <th className="whitespace-nowrap">用户名</th>
                    <th className="whitespace-nowrap">邮箱</th>
                    <th className="whitespace-nowrap">对接数量</th>
                    <th className="whitespace-nowrap">最近对接时间</th>
                    <th className="whitespace-nowrap">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {dealers.length === 0 ? (
                    <tr>
                      <td colSpan={6}>
                        <div className="empty-state py-8">
                          <Users className="empty-state-icon" />
                          <p className="text-gray-500">
                            {searchText ? '没有匹配的下级分销商' : '暂无下级分销商，请先在对接商品中开放二级对接'}
                          </p>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    dealers.map(dealer => (
                      <tr key={dealer.user_id}>
                        <td className="text-sm text-gray-500">{dealer.user_id}</td>
                        <td className="font-medium text-gray-900 dark:text-white">
                          {dealer.username}
                        </td>
                        <td className="text-sm text-gray-500">{dealer.email || '-'}</td>
                        <td>
                          <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                            {dealer.dock_count} 个卡券
                          </span>
                        </td>
                        <td className="text-xs text-gray-500 whitespace-nowrap">
                          {dealer.last_dock_time ? new Date(dealer.last_dock_time).toLocaleString('zh-CN') : '-'}
                        </td>
                        <td>
                          <button
                            onClick={() => handleViewDetails(dealer)}
                            className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 hover:bg-blue-100 dark:hover:bg-blue-900/40 transition-colors"
                            title="查看对接明细"
                          >
                            <Eye className="w-3.5 h-3.5" />
                            查看明细
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}

          {/* 分页 */}
          {total > 0 && (
            <div className="flex flex-wrap items-center justify-between gap-3 p-4 border-t border-slate-200 dark:border-slate-700">
              <div className="flex items-center gap-2 text-sm text-gray-500">
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
              <div className="flex items-center gap-1">
                <button
                  onClick={() => handlePageChange(page - 1)}
                  disabled={page <= 1}
                  className="btn-ios-secondary btn-sm"
                >
                  上一页
                </button>
                <span className="px-3 text-sm text-gray-600 dark:text-gray-400">
                  {page} / {totalPages}
                </span>
                <button
                  onClick={() => handlePageChange(page + 1)}
                  disabled={page >= totalPages}
                  className="btn-ios-secondary btn-sm"
                >
                  下一页
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
      {/* 对接明细弹窗 */}
      <SubDealerDetailModal
        isOpen={detailModalOpen}
        onClose={() => setDetailModalOpen(false)}
        dealer={selectedDealer}
        onDataChange={() => loadData(page, pageSize)}
      />
    </div>
  )
}
