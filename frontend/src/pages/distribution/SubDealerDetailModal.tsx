/**
 * 下级分销商对接明细弹窗
 * 
 * 功能：展示某个二级分销商对接了当前一级分销商哪些卡券的详细记录，支持分页
 */
import { useState, useEffect, useCallback } from 'react'
import { X } from 'lucide-react'
import { getSubDealerDetails, disableSubDealer, enableSubDealer } from '@/api/distribution'
import type { DockRecord, Dealer } from '@/api/distribution'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'

interface SubDealerDetailModalProps {
  /** 是否显示弹窗 */
  isOpen: boolean
  /** 关闭弹窗回调 */
  onClose: () => void
  /** 当前查看的下级分销商 */
  dealer: Dealer | null
  /** 数据变更回调 */
  onDataChange?: () => void
}

export function SubDealerDetailModal({ isOpen, onClose, dealer, onDataChange }: SubDealerDetailModalProps) {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [records, setRecords] = useState<DockRecord[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [totalPages, setTotalPages] = useState(0)

  // 加载对接明细数据
  const loadData = useCallback(async (p: number = 1, ps: number = 20) => {
    if (!dealer) return
    setLoading(true)
    try {
      const result = await getSubDealerDetails(dealer.user_id, p, ps)
      setRecords(result.list)
      setTotal(result.total)
      setPage(result.page)
      setPageSize(result.page_size)
      setTotalPages(result.total_pages)
    } catch {
      addToast({ type: 'error', message: '加载对接明细失败' })
    } finally {
      setLoading(false)
    }
  }, [dealer, addToast])

  // 弹窗打开时加载数据
  useEffect(() => {
    if (isOpen && dealer) {
      loadData(1, pageSize)
    }
  }, [isOpen, dealer])

  // 分页切换
  const handlePageChange = (newPage: number) => {
    if (newPage < 1 || newPage > totalPages) return
    loadData(newPage, pageSize)
  }

  const handlePageSizeChange = (newSize: number) => {
    setPageSize(newSize)
    loadData(1, newSize)
  }

  // 禁用对接记录
  const handleDisable = async (record: DockRecord) => {
    try {
      const result = await disableSubDealer(record.id, '一级分销商禁用')
      if (result.success) {
        addToast({ type: 'success', message: '已禁用' })
        loadData(page, pageSize)
        onDataChange?.()
      } else {
        addToast({ type: 'error', message: result.message || '操作失败' })
      }
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  // 启用（恢复）对接记录
  const handleEnable = async (record: DockRecord) => {
    try {
      const result = await enableSubDealer(record.id)
      if (result.success) {
        addToast({ type: 'success', message: '已启用' })
        loadData(page, pageSize)
        onDataChange?.()
      } else {
        addToast({ type: 'error', message: result.message || '操作失败' })
      }
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  if (!isOpen || !dealer) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* 遮罩 */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* 弹窗内容 */}
      <div className="relative w-full max-w-7xl mx-4 bg-white dark:bg-slate-800 rounded-xl shadow-2xl max-h-[90vh] flex flex-col">
        {/* 头部 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700">
          <div>
            <h3 className="text-lg font-semibold text-slate-900 dark:text-white">
              下级分销商对接明细
            </h3>
            <p className="text-sm text-gray-500 mt-0.5">
              分销商：{dealer.username}，共对接 {total} 张卡券
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
          >
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>

        {/* 表格内容 */}
        <div className="flex-1 overflow-auto">
          {loading ? (
            <PageLoading />
          ) : (
            <div className="table-ios-container">
              <table className="table-ios">
                <thead>
                  <tr>
                    <th className="whitespace-nowrap">记录ID</th>
                    <th className="whitespace-nowrap">层级</th>
                    <th className="whitespace-nowrap">对接名称</th>
                    <th className="whitespace-nowrap">卡券ID</th>
                    <th className="whitespace-nowrap">卡券名称</th>
                    <th className="whitespace-nowrap">规格</th>
                    <th className="whitespace-nowrap">对接价格</th>
                    <th className="whitespace-nowrap">最低售价</th>
                    <th className="whitespace-nowrap">发货次数</th>
                    <th className="whitespace-nowrap">状态</th>
                    <th className="whitespace-nowrap">禁用原因</th>
                    <th className="whitespace-nowrap">备注</th>
                    <th className="whitespace-nowrap">对接时间</th>
                    <th className="whitespace-nowrap">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {records.length === 0 ? (
                    <tr>
                      <td colSpan={14}>
                        <div className="empty-state py-8">
                          <p className="text-gray-500">该下级分销商暂无对接记录</p>
                        </div>
                      </td>
                    </tr>
                  ) : (
                    records.map(record => (
                      <tr key={record.id}>
                        <td className="text-sm text-gray-500">{record.id}</td>
                        <td>
                          <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                            record.level === 1
                              ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
                              : 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400'
                          }`}>
                            {record.level === 1 ? '一级' : record.level === 2 ? '二级' : `-`}
                          </span>
                        </td>
                        <td className="font-medium text-gray-900 dark:text-white">
                          {record.dock_name}
                        </td>
                        <td className="text-sm text-gray-500">{record.card_id}</td>
                        <td className="text-sm text-gray-600 dark:text-gray-400">
                          {record.card_name || '-'}
                        </td>
                        <td className="text-sm">
                          {record.is_multi_spec ? (
                            <span className="text-xs text-blue-600">{record.spec_name}: {record.spec_value}</span>
                          ) : (
                            <span className="text-gray-400">-</span>
                          )}
                        </td>
                        <td className="text-sm">
                          {record.card_price ? (
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
                        <td className="text-sm">
                          <span className="font-medium text-gray-700 dark:text-gray-300">
                            {record.delivery_count || 0}
                          </span>
                        </td>
                        <td>
                          <span className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                            record.status
                              ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
                              : 'bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400'
                          }`}>
                            {record.status ? '已启用' : '已停用'}
                          </span>
                        </td>
                        <td className="text-sm">
                          {record.disable_reason ? (
                            <span className="text-red-500 dark:text-red-400">{record.disable_reason}</span>
                          ) : (
                            <span className="text-gray-400">-</span>
                          )}
                        </td>
                        <td className="max-w-[150px]">
                          <span className="text-sm text-gray-500 truncate block">
                            {record.remark || '-'}
                          </span>
                        </td>
                        <td className="text-sm text-gray-500 whitespace-nowrap">
                          {record.created_at ? new Date(record.created_at).toLocaleString('zh-CN') : '-'}
                        </td>
                        <td>
                          {record.status ? (
                            <button
                              onClick={() => handleDisable(record)}
                              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20 hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors"
                              title="禁用此对接记录"
                            >
                              禁用
                            </button>
                          ) : (
                            <button
                              onClick={() => handleEnable(record)}
                              className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20 hover:bg-green-100 dark:hover:bg-green-900/40 transition-colors"
                              title="启用此对接记录"
                            >
                              启用
                            </button>
                          )}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          )}
        </div>

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

        {/* 底部关闭按钮 */}
        <div className="flex items-center justify-end px-6 py-4 border-t border-slate-200 dark:border-slate-700">
          <button onClick={onClose} className="btn-ios-secondary">
            关闭
          </button>
        </div>
      </div>
    </div>
  )
}
