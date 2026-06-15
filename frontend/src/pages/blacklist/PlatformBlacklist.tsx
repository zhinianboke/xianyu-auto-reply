/**
 * 闲鱼黑名单Tab页（仅展示，无操作）
 */
import { useState, useEffect, useCallback, type MutableRefObject } from 'react'
import { Empty, Pagination, Table, type TableColumnProps } from '@arco-design/web-react'
import { Ban } from 'lucide-react'
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

  const columns: TableColumnProps<PlatformBlacklistItem>[] = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    {
      title: '拉黑用户',
      dataIndex: 'owner_username',
      width: 160,
      render: (_value, item) => item.owner_username || item.owner_id,
    },
    { title: '买家ID', dataIndex: 'buyer_id', width: 180 },
    { title: '买家昵称', dataIndex: 'buyer_nick', width: 180, render: (value?: string) => value || '-' },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (value?: string) => (
        <span className="text-xs text-slate-500">{value ? new Date(value).toLocaleString() : '-'}</span>
      ),
    },
    {
      title: '更新时间',
      dataIndex: 'updated_at',
      width: 180,
      render: (value?: string) => (
        <span className="text-xs text-slate-500">{value ? new Date(value).toLocaleString() : '-'}</span>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <Table
        rowKey="id"
        columns={columns}
        data={items}
        loading={loading}
        border={false}
        scroll={{ x: 960 }}
        pagination={false}
        className="accounts-arco-table table-main"
        noDataElement={(
          <Empty
            icon={<Ban className="w-12 h-12 text-gray-300" />}
            description="暂无黑名单数据"
          />
        )}
      />

      {totalPages > 1 && (
        <div className="flex justify-end">
          <Pagination
            total={total}
            current={page}
            pageSize={pageSize}
            sizeCanChange={false}
            showTotal
            onChange={setPage}
          />
        </div>
      )}
    </div>
  )
}
