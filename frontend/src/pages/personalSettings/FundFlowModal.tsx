/**
 * 个人资金流水弹窗
 *
 * 功能：在个人设置页的余额管理模块中，以弹窗形式展示当前用户的资金流水记录
 * 支持类型、描述筛选和后端分页
 */
import { useState, useEffect, useCallback } from 'react'
import { Loader2, RefreshCw, Wallet, X } from 'lucide-react'
import { getFundFlows } from '@/api/distribution'
import type { FundFlow } from '@/api/distribution'
import { useUIStore } from '@/store/uiStore'

/** 流水类型中文映射 */
const FLOW_TYPE_MAP: Record<string, string> = {
  income: '收入',
  expense: '支出',
  fee: '手续费',
}

interface FundFlowFilters {
  flowType: string
  description: string
}

const EMPTY_FILTERS: FundFlowFilters = {
  flowType: '',
  description: '',
}

interface Props {
  visible: boolean
  onClose: () => void
}

export function FundFlowModal({ visible, onClose }: Props) {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [flows, setFlows] = useState<FundFlow[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [totalPages, setTotalPages] = useState(0)
  const [flowType, setFlowType] = useState('')
  const [description, setDescription] = useState('')
  const [appliedFilters, setAppliedFilters] = useState<FundFlowFilters>(EMPTY_FILTERS)

  // 加载数据
  const loadData = useCallback(async (p: number, ps: number, filters: FundFlowFilters) => {
    setLoading(true)
    try {
      const result = await getFundFlows(p, ps, filters.flowType, '', filters.description)
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

  // 弹窗打开时加载数据
  useEffect(() => {
    if (visible) {
      setFlowType('')
      setDescription('')
      setAppliedFilters(EMPTY_FILTERS)
      setPage(1)
      setPageSize(20)
      loadData(1, 20, EMPTY_FILTERS)
    }
  }, [visible, loadData])

  // 类型筛选仅更新查询草稿
  const handleTypeChange = (type: string) => {
    setFlowType(type)
  }

  // 查询：提交当前筛选条件并回到第 1 页
  const handleSearch = () => {
    const filters = {
      flowType,
      description: description.trim(),
    }
    setAppliedFilters(filters)
    loadData(1, pageSize, filters)
  }

  // 重置筛选条件并重新查询
  const handleReset = () => {
    setFlowType('')
    setDescription('')
    setAppliedFilters(EMPTY_FILTERS)
    loadData(1, pageSize, EMPTY_FILTERS)
  }

  // 分页
  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return
    loadData(newPage, pageSize, appliedFilters)
  }

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize)
    loadData(1, newSize, appliedFilters)
  }

  if (!visible) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div className="flex h-[80vh] w-full max-w-5xl flex-col rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900">
        {/* 弹窗头部 */}
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">资金流水</h3>
            <p className="text-xs text-slate-500 dark:text-slate-400">查看资金变动明细记录</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              title="关闭"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        </div>

        {/* 筛选 */}
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <select
            value={flowType}
            onChange={(e) => handleTypeChange(e.target.value)}
            className="input-ios w-auto py-1.5 px-3 text-sm"
          >
            <option value="">全部类型</option>
            <option value="income">收入</option>
            <option value="expense">支出</option>
            <option value="fee">手续费</option>
          </select>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleSearch() }}
            maxLength={500}
            placeholder="按描述模糊查询"
            className="input-ios min-w-0 flex-1 py-1.5 px-3 text-sm sm:max-w-64"
          />
          <span className="text-sm text-gray-500">共 {total} 条</span>
          <div className="ml-auto flex items-center gap-2">
            <button onClick={handleSearch} className="btn-ios-primary text-sm" disabled={loading}>
              查询
            </button>
            {(flowType || description) && (
              <button onClick={handleReset} className="btn-ios-secondary text-sm text-red-500" disabled={loading}>
                重置
              </button>
            )}
            <button
              onClick={() => loadData(page, pageSize, appliedFilters)}
              className="btn-ios-secondary text-sm"
              disabled={loading}
            >
              <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
              刷新
            </button>
          </div>
        </div>

        {/* 表格 */}
        <div className="flex-1 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
          <div className="table-scroll h-full">
            <table className="table-ios">
              <thead>
                <tr>
                  <th className="whitespace-nowrap">ID</th>
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
                {loading ? (
                  <tr>
                    <td colSpan={9}>
                      <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-500">
                        <Loader2 className="h-5 w-5 animate-spin" />
                        <span>加载中...</span>
                      </div>
                    </td>
                  </tr>
                ) : flows.length === 0 ? (
                  <tr>
                    <td colSpan={9}>
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
                      <td className="text-sm text-gray-600 dark:text-gray-400">¥{flow.balance_before}</td>
                      <td className="text-sm text-gray-600 dark:text-gray-400">¥{flow.balance_after}</td>
                      <td className="text-sm text-gray-500">{flow.order_id || '-'}</td>
                      <td className="text-sm text-gray-500">{flow.dock_record_id || '-'}</td>
                      <td className="max-w-[200px]" title={flow.description || ''}>
                        <span className="text-sm text-gray-500 truncate block">{flow.description || '-'}</span>
                      </td>
                      <td className="text-sm text-gray-500 whitespace-nowrap">
                        {flow.created_at ? new Date(flow.created_at).toLocaleString('zh-CN') : '-'}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* 分页 */}
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4 dark:border-slate-700">
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
              disabled={page <= 1 || loading}
              className="btn-ios-secondary btn-sm"
            >
              上一页
            </button>
            <span className="px-3 text-sm text-gray-600 dark:text-gray-400">
              {page} / {totalPages || 1}
            </span>
            <button
              onClick={() => handlePageChange(page + 1)}
              disabled={page >= totalPages || loading || totalPages === 0}
              className="btn-ios-secondary btn-sm"
            >
              下一页
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
