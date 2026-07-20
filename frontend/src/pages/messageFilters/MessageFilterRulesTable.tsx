import { ChevronLeft, ChevronRight, Edit2, Filter, ToggleLeft, ToggleRight, Trash2 } from 'lucide-react'
import type { MessageFilter } from '@/types'

interface MessageFilterRulesTableProps {
  loading: boolean
  filters: MessageFilter[]
  paginatedFilters: MessageFilter[]
  selectedIds: number[]
  batchDeleting: boolean
  currentPage: number
  pageSize: number
  totalPages: number
  getFilterTypeLabel: (filterType: string) => string
  onToggleSelect: (id: number) => void
  onToggleSelectAll: () => void
  onOpenBatchDeleteConfirm: () => void
  onToggle: (filter: MessageFilter) => void
  onEdit: (filter: MessageFilter) => void
  onDelete: (filter: MessageFilter) => void
  onPageChange: (page: number) => void
  onPageSizeChange: (pageSize: number) => void
}

export function MessageFilterRulesTable({
  loading,
  filters,
  paginatedFilters,
  selectedIds,
  batchDeleting,
  currentPage,
  pageSize,
  totalPages,
  getFilterTypeLabel,
  onToggleSelect,
  onToggleSelectAll,
  onOpenBatchDeleteConfirm,
  onToggle,
  onEdit,
  onDelete,
  onPageChange,
  onPageSizeChange,
}: MessageFilterRulesTableProps) {
  const getFilterTypeClassName = (filterType: string) => {
    if (filterType === 'skip_reply') return 'badge-primary'
    if (filterType === 'skip_notify') return 'badge-warning'
    return 'badge-danger'
  }

  return (
    <div
      className="vben-card flex flex-col"
      style={{ height: 'calc(100vh - 280px)', minHeight: '400px' }}
    >
      <div className="vben-card-header flex-shrink-0">
        <h2 className="vben-card-title flex items-center gap-2">
          <Filter className="w-4 h-4" />
          过滤规则列表
        </h2>
        <div className="flex items-center gap-2">
          {selectedIds.length > 0 && (
            <button
              onClick={onOpenBatchDeleteConfirm}
              disabled={batchDeleting}
              className="btn-ios-danger text-sm"
            >
              <Trash2 className="w-4 h-4" />
              {batchDeleting ? '删除中...' : `删除选中 (${selectedIds.length})`}
            </button>
          )}
          <span className="badge-primary">{filters.length} 条规则</span>
        </div>
      </div>
      <div className="flex-1 overflow-auto">
        <table className="table-ios">
          <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
            <tr>
              <th className="w-10">
                <input
                  type="checkbox"
                  checked={filters.length > 0 && selectedIds.length === filters.length}
                  onChange={onToggleSelectAll}
                  className="w-4 h-4 rounded border-gray-300"
                />
              </th>
              <th>账号</th>
              <th>关键词</th>
              <th>过滤类型</th>
              <th>状态</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={7} className="text-center py-8 text-gray-500">
                  加载中...
                </td>
              </tr>
            ) : filters.length === 0 ? (
              <tr>
                <td colSpan={7} className="text-center py-8 text-gray-500">
                  <div className="flex flex-col items-center gap-2">
                    <Filter className="w-12 h-12 text-gray-300" />
                    <p>暂无过滤规则，点击上方按钮添加</p>
                  </div>
                </td>
              </tr>
            ) : (
              paginatedFilters.map((filter) => (
                <tr key={filter.id}>
                  <td>
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(filter.id)}
                      onChange={() => onToggleSelect(filter.id)}
                      className="w-4 h-4 rounded border-gray-300"
                    />
                  </td>
                  <td>
                    <span className="text-xs text-slate-500 dark:text-slate-400">{filter.account_id}</span>
                  </td>
                  <td className="font-medium">
                    <code className="bg-orange-50 dark:bg-orange-900/30 text-orange-600 dark:text-orange-400 px-2 py-1 rounded">
                      {filter.keyword}
                    </code>
                  </td>
                  <td>
                    <span className={getFilterTypeClassName(filter.filter_type)}>
                      {getFilterTypeLabel(filter.filter_type)}
                    </span>
                  </td>
                  <td>
                    <span className={filter.enabled ? 'badge-success' : 'badge-gray'}>
                      {filter.enabled ? '已启用' : '已禁用'}
                    </span>
                  </td>
                  <td className="text-sm text-gray-500">{filter.created_at || '-'}</td>
                  <td>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => onToggle(filter)}
                        className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                        title={filter.enabled ? '禁用' : '启用'}
                      >
                        {filter.enabled ? (
                          <ToggleRight className="w-4 h-4 text-green-500" />
                        ) : (
                          <ToggleLeft className="w-4 h-4 text-gray-400" />
                        )}
                      </button>
                      <button
                        onClick={() => onEdit(filter)}
                        className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                        title="编辑"
                      >
                        <Edit2 className="w-4 h-4 text-blue-500 dark:text-blue-400" />
                      </button>
                      <button
                        onClick={() => onDelete(filter)}
                        className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
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
      </div>
      {filters.length > 0 && (
        <div className="flex-shrink-0 flex flex-col sm:flex-row items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700 gap-3">
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <span>每页</span>
            <select
              value={pageSize}
              onChange={(event) => onPageSizeChange(Number(event.target.value))}
              className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <option value={10}>10</option>
              <option value={20}>20</option>
              <option value={50}>50</option>
              <option value={100}>100</option>
            </select>
            <span>条，共 {filters.length} 条</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500">
              第 {currentPage} / {totalPages || 1} 页
            </span>
            <button
              onClick={() => onPageChange(currentPage - 1)}
              disabled={currentPage <= 1}
              className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-5 h-5" />
            </button>
            <button
              onClick={() => onPageChange(currentPage + 1)}
              disabled={currentPage >= totalPages}
              className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ChevronRight className="w-5 h-5" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
