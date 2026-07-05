/**
 * 分销商管理页面
 * 
 * 功能：展示对接了当前用户卡券的分销商列表，支持查看对接卡券明细
 */
import { useState, useEffect, useCallback } from 'react'
import { Search, RefreshCw, Users, Eye } from 'lucide-react'
import { getDealers } from '@/api/distribution'
import type { Dealer } from '@/api/distribution'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import { DealerDetailModal } from './DealerDetailModal'

export function DealerManagement() {
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

  // 加载分销商列表数据（search 传入时覆盖当前 searchText，避免闭包旧值问题）
  const loadData = useCallback(async (p: number = page, ps: number = pageSize, search: string = searchText) => {
    setLoading(true)
    try {
      const result = await getDealers(p, ps, search)
      setDealers(result.list)
      setTotal(result.total)
      setPage(result.page)
      setPageSize(result.page_size)
      setTotalPages(result.total_pages)
    } catch {
      addToast({ type: 'error', message: '加载分销商列表失败' })
    } finally {
      setLoading(false)
    }
  }, [searchText, page, pageSize, addToast])

  useEffect(() => {
    loadData(1, pageSize)
  }, [])

  // 点击查询或回车后发起查询，回到第 1 页
  const handleSearch = () => {
    loadData(1, pageSize)
  }

  // 重置搜索条件并重新查询
  const handleReset = () => {
    setSearchText('')
    loadData(1, pageSize, '')
  }

  // 查看对接明细
  const handleViewDetails = (dealer: Dealer) => {
    setSelectedDealer(dealer)
    setDetailModalOpen(true)
  }

  // 分页切换
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
          <h1 className="page-title">分销商管理</h1>
          <p className="page-description">查看对接了您卡券的分销商及其对接详情</p>
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
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                className="input-ios pl-9"
                placeholder="搜索用户名..."
              />
            </div>
            <span className="text-sm text-gray-500">
              共 {total} 个分销商
            </span>
            <div className="flex items-center gap-2 ml-auto">
              <button onClick={handleSearch} className="btn-ios-primary">
                <Search className="w-4 h-4" />
                查询
              </button>
              <button onClick={handleReset} className="btn-ios-secondary">
                重置
              </button>
            </div>
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
                    <th className="whitespace-nowrap">层级</th>
                    <th className="whitespace-nowrap">对接卡券数</th>
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
                            {searchText ? '没有匹配的分销商' : '暂无分销商对接您的卡券'}
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
                        <td className="text-sm">
                          <div className="flex items-center gap-1">
                            {(dealer.level_1_count ?? 0) > 0 && (
                              <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                                一级
                              </span>
                            )}
                            {(dealer.level_2_count ?? 0) > 0 && (
                              <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400">
                                二级
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="text-sm">
                          <span className="inline-block px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400">
                            {dealer.dock_count} 张
                          </span>
                        </td>
                        <td className="text-sm text-gray-500 whitespace-nowrap">
                          {dealer.last_dock_time
                            ? new Date(dealer.last_dock_time).toLocaleString('zh-CN')
                            : '-'}
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
      <DealerDetailModal
        isOpen={detailModalOpen}
        onClose={() => setDetailModalOpen(false)}
        dealer={selectedDealer}
      />
    </div>
  )
}
