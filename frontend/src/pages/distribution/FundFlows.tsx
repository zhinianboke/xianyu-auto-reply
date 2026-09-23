/**
 * 资金流水页面
 * 
 * 功能：展示当前用户的资金流水记录，管理员可查看所有用户的流水
 * 支持按类型、用户名、描述筛选和后端分页
 */
import { useState, useEffect, useCallback } from 'react'
import { RefreshCw, Wallet } from 'lucide-react'
import { getFundFlows } from '@/api/distribution'
import type { FundFlow } from '@/api/distribution'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'

/** 流水类型中文映射 */
const FLOW_TYPE_MAP: Record<string, string> = {
  income: '收入',
  expense: '支出',
  fee: '手续费',
}

interface FundFlowFilters {
  flowType: string
  username: string
  description: string
}

const EMPTY_FILTERS: FundFlowFilters = {
  flowType: '',
  username: '',
  description: '',
}

export function FundFlows() {
  const { addToast } = useUIStore()
  const { user } = useAuthStore()
  const isAdmin = Boolean(user?.is_admin)
  const [loading, setLoading] = useState(true)
  const [flows, setFlows] = useState<FundFlow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [totalPages, setTotalPages] = useState(0)
  const [flowType, setFlowType] = useState('')
  // 用户名查询草稿（仅管理员使用）
  const [username, setUsername] = useState('')
  const [description, setDescription] = useState('')
  const [appliedFilters, setAppliedFilters] = useState<FundFlowFilters>(EMPTY_FILTERS)

  // 加载数据
  const loadData = useCallback(async (
    p: number,
    ps: number,
    filters: FundFlowFilters,
  ) => {
    setLoading(true)
    try {
      const result = await getFundFlows(
        p,
        ps,
        filters.flowType,
        filters.username,
        filters.description,
      )
      setFlows(result.list)
      setTotal(result.total)
      setPage(result.page)
      setPageSize(result.page_size)
      setTotalPages(result.total_pages)
    } catch {
      addToast({ type: 'error', message: '加载资金流水失败' })
    } finally {
      setLoading(false)
    }
  }, [addToast])

  useEffect(() => {
    loadData(1, 20, EMPTY_FILTERS)
  }, [loadData])

  // 类型筛选变化：仅更新草稿，不即时查询
  const handleTypeChange = (type: string) => {
    setFlowType(type)
  }

  // 查询：以当前选中的条件回到第 1 页
  const handleSearch = () => {
    const filters = {
      flowType,
      username: username.trim(),
      description: description.trim(),
    }
    setAppliedFilters(filters)
    loadData(1, pageSize, filters)
  }

  // 重置：清空所有筛选并以空值重新查询第 1 页
  const handleReset = () => {
    setFlowType('')
    setUsername('')
    setDescription('')
    setAppliedFilters(EMPTY_FILTERS)
    loadData(1, pageSize, EMPTY_FILTERS)
  }

  // 分页切换
  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return
    loadData(newPage, pageSize, appliedFilters)
  }

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize)
    loadData(1, newSize, appliedFilters)
  }

  return (
    <div className="space-y-4">
      {/* 页头 */}
      <div className="page-header flex-between flex-wrap gap-4">
        <div>
          <h1 className="page-title">资金流水</h1>
          <p className="page-description">查看资金变动明细记录</p>
        </div>
        <button onClick={() => loadData(page, pageSize, appliedFilters)} className="btn-ios-secondary">
          <RefreshCw className="w-4 h-4" />
          刷新
        </button>
      </div>

      {/* 筛选 */}
      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600 dark:text-gray-400">流水类型：</span>
              <select
                value={flowType}
                onChange={(e) => handleTypeChange(e.target.value)}
                className="input-ios w-auto py-1.5 px-3 text-sm"
              >
                <option value="">全部</option>
                <option value="income">收入</option>
                <option value="expense">支出</option>
                <option value="fee">手续费</option>
              </select>
            </div>
            {isAdmin && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-600 dark:text-gray-400">用户名：</span>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') handleSearch() }}
                  placeholder="按用户名筛选"
                  className="input-ios w-auto py-1.5 px-3 text-sm"
                />
              </div>
            )}
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-600 dark:text-gray-400">描述：</span>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                onKeyDown={(e) => { if (e.key === 'Enter') handleSearch() }}
                maxLength={500}
                placeholder="按描述模糊查询"
                className="input-ios w-auto py-1.5 px-3 text-sm"
              />
            </div>
            <span className="text-sm text-gray-500">
              共 {total} 条记录
            </span>
            <div className="ml-auto flex items-center gap-2">
              <button onClick={handleSearch} className="btn-ios-primary">
                查询
              </button>
              {(flowType || username || description) && (
                <button onClick={handleReset} className="btn-ios-secondary text-red-500">
                  重置
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 表格 */}
      <div className="vben-card flex min-h-0 flex-col">
        <div className="vben-card-body flex min-h-0 flex-1 flex-col p-0">
          {loading ? (
            <PageLoading />
          ) : (
            <div className="table-scroll h-[60vh] min-h-[320px] max-h-[720px]">
              <table className="table-ios">
                <thead>
                  <tr>
                    <th className="whitespace-nowrap">ID</th>
                    <th className="whitespace-nowrap">用户</th>
                    <th className="whitespace-nowrap">类型</th>
                    <th className="whitespace-nowrap">发生额</th>
                    <th className="whitespace-nowrap">发生前余额</th>
                    <th className="whitespace-nowrap">发生后余额</th>
                    <th className="whitespace-nowrap">关联订单</th>
                    <th className="whitespace-nowrap">关联对接记录</th>
                    <th className="whitespace-nowrap">描述</th>
                    <th className="whitespace-nowrap">发生时间</th>
                  </tr>
                </thead>
                <tbody>
                  {flows.length === 0 ? (
                    <tr>
                      <td colSpan={10}>
                        <div className="empty-state py-8">
                          <Wallet className="empty-state-icon" />
                          <p className="text-gray-500">暂无资金流水记录</p>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    flows.map(flow => (
                      <tr key={flow.id}>
                        <td className="text-sm text-gray-500">{flow.id}</td>
                        <td className="text-sm text-gray-700 dark:text-gray-300 whitespace-nowrap">
                          {flow.username || '-'}
                        </td>
                        <td>
                          <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                            flow.type === 'income'
                              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                              : flow.type === 'fee'
                              ? 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                              : 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                          }`}>
                            {FLOW_TYPE_MAP[flow.type] || flow.type}
                          </span>
                        </td>
                        <td className="text-sm font-medium">
                          <span className={flow.type === 'income' ? 'text-green-600' : flow.type === 'fee' ? 'text-orange-600' : 'text-red-600'}>
                            {flow.type === 'income' ? '+' : '-'}{flow.amount}
                          </span>
                        </td>
                        <td className="text-sm text-gray-600 dark:text-gray-400">
                          ¥{flow.balance_before}
                        </td>
                        <td className="text-sm text-gray-600 dark:text-gray-400">
                          ¥{flow.balance_after}
                        </td>
                        <td className="text-sm text-gray-500">
                          {flow.order_id || '-'}
                        </td>
                        <td className="text-sm text-gray-500">
                          {flow.dock_record_id || '-'}
                        </td>
                        <td className="max-w-[200px]" title={flow.description || ''}>
                          <span className="text-sm text-gray-500 truncate block">
                            {flow.description || '-'}
                          </span>
                        </td>
                        <td className="text-sm text-gray-500 whitespace-nowrap">
                          {flow.created_at
                            ? new Date(flow.created_at).toLocaleString('zh-CN')
                            : '-'}
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
    </div>
  )
}
