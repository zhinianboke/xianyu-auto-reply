/**
 * 闲鱼黑名单Tab页（仅展示，无操作）
 */
import { useState, useEffect, useCallback, type MutableRefObject } from 'react'
import { getPlatformBlacklist, type PlatformBlacklistItem } from '@/api/blacklist'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { getApiErrorMessage } from '@/utils/request'

interface Props {
  onRefreshRef: MutableRefObject<() => void>
}

export function PlatformBlacklist({ onRefreshRef }: Props) {
  const { addToast } = useUIStore()
  const { _hasHydrated, isAuthenticated, token } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState<PlatformBlacklistItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)

  const totalPages = Math.ceil(total / pageSize)

  const loadData = useCallback(async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    setLoading(true)
    try {
      const res = await getPlatformBlacklist({ page, page_size: pageSize })
      if (res.success) {
        setItems(res.data)
        setTotal(res.total)
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载闲鱼黑名单失败') })
    } finally {
      setLoading(false)
    }
  }, [_hasHydrated, isAuthenticated, token, page, pageSize, addToast])

  useEffect(() => {
    loadData()
  }, [loadData])

  // 暴露刷新方法
  useEffect(() => {
    onRefreshRef.current = loadData
  }, [onRefreshRef, loadData])

  if (loading && items.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* 表格 */}
      <div className="overflow-x-auto bg-white dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 dark:bg-slate-700/50">
            <tr>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">ID</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">拉黑用户</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">买家ID</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">买家昵称</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">创建时间</th>
              <th className="px-3 py-2 text-left font-medium text-slate-600 dark:text-slate-300">更新时间</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-700">
            {items.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-3 py-8 text-center text-slate-400 dark:text-slate-500">
                  暂无数据
                </td>
              </tr>
            ) : (
              items.map((item) => (
                <tr key={item.id} className="hover:bg-slate-50 dark:hover:bg-slate-700/30">
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{item.id}</td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{item.owner_username || item.owner_id}</td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{item.buyer_id}</td>
                  <td className="px-3 py-2 text-slate-700 dark:text-slate-300">{item.buyer_nick || '-'}</td>
                  <td className="px-3 py-2 text-slate-500 dark:text-slate-400 text-xs whitespace-nowrap">
                    {item.created_at ? new Date(item.created_at).toLocaleString() : '-'}
                  </td>
                  <td className="px-3 py-2 text-slate-500 dark:text-slate-400 text-xs whitespace-nowrap">
                    {item.updated_at ? new Date(item.updated_at).toLocaleString() : '-'}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* 分页 */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between">
          <span className="text-sm text-slate-500 dark:text-slate-400">
            共 {total} 条，第 {page}/{totalPages} 页
          </span>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage(Math.max(1, page - 1))}
              disabled={page <= 1}
              className="px-3 py-1 text-sm border border-slate-300 dark:border-slate-600 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300"
            >
              上一页
            </button>
            <button
              onClick={() => setPage(Math.min(totalPages, page + 1))}
              disabled={page >= totalPages}
              className="px-3 py-1 text-sm border border-slate-300 dark:border-slate-600 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300"
            >
              下一页
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
