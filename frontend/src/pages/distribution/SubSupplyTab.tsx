/**
 * 二级分销货源Tab组件
 * 
 * 功能：展示一级分销商开放的可对接记录列表，供二级分销商对接
 */
import { useState, useEffect, useCallback, forwardRef, useImperativeHandle } from 'react'
import { Search, PackageSearch, Link } from 'lucide-react'
import { getSubSupplyRecords } from '@/api/distribution'
import type { SubSupplyRecord } from '@/api/distribution'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import { SubDockModal } from './SubDockModal'

export interface SubSupplyTabRef {
  refresh: () => void
}

export const SubSupplyTab = forwardRef<SubSupplyTabRef>(function SubSupplyTab(_props, ref) {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [records, setRecords] = useState<SubSupplyRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [totalPages, setTotalPages] = useState(0)
  const [searchText, setSearchText] = useState('')
  const [dockModalOpen, setDockModalOpen] = useState(false)
  const [selectedRecord, setSelectedRecord] = useState<SubSupplyRecord | null>(null)

  // 加载数据
  const loadData = useCallback(async (p: number = page, ps: number = pageSize) => {
    setLoading(true)
    try {
      const result = await getSubSupplyRecords(p, ps, searchText)
      setRecords(result.list)
      setTotal(result.total)
      setPage(result.page)
      setPageSize(result.page_size)
      setTotalPages(result.total_pages)
    } catch {
      addToast({ type: 'error', message: '加载分销商货源失败' })
    } finally {
      setLoading(false)
    }
  }, [searchText, page, pageSize, addToast])

  useImperativeHandle(ref, () => ({
    refresh: () => loadData(page, pageSize),
  }), [loadData, page, pageSize])

  useEffect(() => {
    loadData(1, pageSize)
  }, [])

  // 点击「查询」或回车时才发起查询，回到第 1 页
  const handleSearch = () => {
    loadData(1, pageSize)
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
    <>
      <div
        className="vben-card flex flex-col"
        style={{ height: 'calc(100vh - 260px)', minHeight: '420px' }}
      >
        {/* 卡片头：搜索 */}
        <div className="flex-shrink-0 vben-card-header flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <h2 className="vben-card-title">分销商货源列表</h2>
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
                placeholder="搜索对接名称或卡券名称..."
              />
            </div>
            <button onClick={handleSearch} className="btn-ios-primary btn-sm">
              <Search className="w-4 h-4" />
              查询
            </button>
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
                  <th className="whitespace-nowrap">上级分销商</th>
                  <th className="whitespace-nowrap">卡券名称</th>
                  <th className="whitespace-nowrap">对接名称</th>
                  <th className="whitespace-nowrap">对接价格</th>
                  <th className="whitespace-nowrap">最低售价</th>
                  <th className="whitespace-nowrap">规格</th>
                  <th className="whitespace-nowrap">操作</th>
                </tr>
              </thead>
              <tbody>
                {records.length === 0 ? (
                  <tr>
                    <td colSpan={8}>
                      <div className="empty-state py-8">
                        <PackageSearch className="empty-state-icon" />
                        <p className="text-gray-500">
                          {searchText ? '没有匹配的分销商货源' : '暂无可对接的分销商货源'}
                        </p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  records.map(record => (
                    <tr key={record.id}>
                      <td className="text-sm text-gray-500">{record.id}</td>
                      <td className="font-medium text-gray-900 dark:text-white">
                        {record.source_username}
                      </td>
                      <td className="text-sm text-gray-600 dark:text-gray-400">
                        {record.card_name}
                      </td>
                      <td className="text-sm">{record.dock_name}</td>
                      <td className="text-sm">
                        {record.sub_dock_price ? (
                          <span className="text-amber-600 dark:text-amber-400 font-medium">¥{record.sub_dock_price}</span>
                        ) : record.card_price ? (
                          <span className="text-amber-600 dark:text-amber-400 font-medium">¥{record.card_price}</span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td className="text-sm">
                        {record.min_price ? (
                          <span className="text-orange-600 dark:text-orange-400 font-medium">¥{record.min_price}</span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td>
                        {record.is_multi_spec ? (
                          <span className="text-xs text-blue-600">{record.spec_name}: {record.spec_value}</span>
                        ) : (
                          <span className="text-gray-400">-</span>
                        )}
                      </td>
                      <td>
                        {record.is_docked ? (
                          <span className="inline-block px-2 py-0.5 rounded text-xs font-medium bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400">
                            已对接
                          </span>
                        ) : (
                          <button
                            onClick={() => { setSelectedRecord(record); setDockModalOpen(true) }}
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

      {/* 二级对接弹窗 */}
      <SubDockModal
        isOpen={dockModalOpen}
        onClose={() => setDockModalOpen(false)}
        onSuccess={() => loadData(page, pageSize)}
        record={selectedRecord}
      />
    </>
  )
})
