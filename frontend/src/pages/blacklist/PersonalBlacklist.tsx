/**
 * 个人黑名单Tab页
 */
import { useState, useEffect, useCallback, useRef, type MutableRefObject } from 'react'
import { Button, Empty, Form, Input, Pagination, Space, Table, Tag, type TableColumnProps } from '@arco-design/web-react'
import { Ban, Plus, Trash2, ToggleLeft, ToggleRight, Download, Upload } from 'lucide-react'
import { getPersonalBlacklist, deletePersonalBlacklist, batchDeletePersonalBlacklist, togglePersonalBlacklist, exportPersonalBlacklist, importPersonalBlacklist, type PersonalBlacklistItem } from '@/api/blacklist'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { getApiErrorMessage } from '@/utils/request'
import { PersonalBlacklistFormModal } from './PersonalBlacklistFormModal'

interface Props {
  onRefreshRef: MutableRefObject<() => void>
}

export function PersonalBlacklist({ onRefreshRef }: Props) {
  const { addToast } = useUIStore()
  const { _hasHydrated, isAuthenticated, token } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [items, setItems] = useState<PersonalBlacklistItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(20)

  // 筛选输入
  const [filterBuyerId, setFilterBuyerId] = useState('')
  const [filterBuyerNick, setFilterBuyerNick] = useState('')

  // 已提交的筛选条件（点击搜索后才更新）
  const [appliedBuyerId, setAppliedBuyerId] = useState('')
  const [appliedBuyerNick, setAppliedBuyerNick] = useState('')

  // 新建弹窗
  const [showCreateModal, setShowCreateModal] = useState(false)

  // 勾选状态
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set())

  // 删除确认
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; item: PersonalBlacklistItem | null }>({ open: false, item: null })
  const [batchDeleteConfirm, setBatchDeleteConfirm] = useState(false)

  // 导入文件输入
  const fileInputRef = useRef<HTMLInputElement>(null)

  const totalPages = Math.ceil(total / pageSize)

  const loadData = useCallback(async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    setLoading(true)
    try {
      const res = await getPersonalBlacklist({
        buyer_id: appliedBuyerId || undefined,
        buyer_nick: appliedBuyerNick || undefined,
        page,
        page_size: pageSize,
      })
      if (res.success) {
        setItems(res.data)
        setTotal(res.total)
        setSelectedIds(new Set())
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载黑名单失败') })
    } finally {
      setLoading(false)
    }
  }, [_hasHydrated, isAuthenticated, token, appliedBuyerId, appliedBuyerNick, page, pageSize, addToast])

  useEffect(() => {
    loadData()
  }, [loadData])

  // 暴露刷新方法
  useEffect(() => {
    onRefreshRef.current = loadData
  }, [onRefreshRef, loadData])

  const handleSearch = () => {
    setAppliedBuyerId(filterBuyerId)
    setAppliedBuyerNick(filterBuyerNick)
    setPage(1)
  }

  const handleReset = () => {
    setFilterBuyerId('')
    setFilterBuyerNick('')
    setAppliedBuyerId('')
    setAppliedBuyerNick('')
    setPage(1)
  }

  const handleDelete = async () => {
    if (!deleteConfirm.item) return
    try {
      const res = await deletePersonalBlacklist(deleteConfirm.item.id)
      if (res.success) {
        addToast({ type: 'success', message: '删除成功' })
        loadData()
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '删除失败') })
    } finally {
      setDeleteConfirm({ open: false, item: null })
    }
  }

  const handleBatchDelete = async () => {
    const ids = Array.from(selectedIds)
    try {
      const res = await batchDeletePersonalBlacklist(ids)
      if (res.success) {
        addToast({ type: 'success', message: res.message || `成功删除 ${ids.length} 条` })
        setSelectedIds(new Set())
        loadData()
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '批量删除失败') })
    } finally {
      setBatchDeleteConfirm(false)
    }
  }

  const handleToggle = async (item: PersonalBlacklistItem) => {
    try {
      const res = await togglePersonalBlacklist(item.id, !item.is_enabled)
      if (res.success) {
        addToast({ type: 'success', message: item.is_enabled ? '已禁用' : '已启用' })
        loadData()
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '操作失败') })
    }
  }

  const handleCreateSuccess = () => {
    setShowCreateModal(false)
    loadData()
  }

  const handleExport = async () => {
    try {
      const blob = await exportPersonalBlacklist()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `个人黑名单_${new Date().toLocaleDateString()}.xlsx`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      addToast({ type: 'success', message: '导出成功' })
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '导出失败') })
    }
  }

  const handleImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      const res = await importPersonalBlacklist(file)
      if (res.success) {
        addToast({ type: 'success', message: res.message || '导入成功' })
        loadData()
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '导入失败') })
    } finally {
      // 清空文件输入，允许重复选择同一文件
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  if (loading && items.length === 0) {
    return <PageLoading />
  }

  const columns: TableColumnProps<PersonalBlacklistItem>[] = [
    { title: 'ID', dataIndex: 'id', width: 80 },
    { title: '用户ID', dataIndex: 'owner_id', width: 110 },
    { title: '账号ID', dataIndex: 'account_id', width: 160, render: (value?: string) => value || '-' },
    { title: '买家ID', dataIndex: 'buyer_id', width: 160 },
    { title: '买家昵称', dataIndex: 'buyer_nick', width: 160, render: (value?: string) => value || '-' },
    { title: '商品ID', dataIndex: 'item_id', width: 160, render: (value?: string) => value || '-' },
    {
      title: '拉黑原因',
      dataIndex: 'reason',
      width: 220,
      render: (value?: string) => (
        <span className="line-clamp-1" title={value || ''}>{value || '-'}</span>
      ),
    },
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
    {
      title: '状态',
      dataIndex: 'is_enabled',
      width: 100,
      render: (enabled: boolean) => (
        <Tag color={enabled ? 'green' : 'gray'} style={{ borderRadius: 4 }}>
          {enabled ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '操作',
      dataIndex: 'operation',
      width: 150,
      fixed: 'right',
      render: (_value, item) => (
        <Space size={8}>
          <Button type="text" className="accounts-table-action-btn" onClick={() => handleToggle(item)}>
            {item.is_enabled ? <ToggleRight /> : <ToggleLeft />}
            {item.is_enabled ? '禁用' : '启用'}
          </Button>
          <Button
            type="text"
            className="accounts-table-action-btn !text-red-500 hover:!text-red-500"
            onClick={() => setDeleteConfirm({ open: true, item })}
          >
            删除
          </Button>
        </Space>
      ),
    },
  ]

  return (
    <div className="space-y-4">
      <div className="table-toolbar">
        <div className="table-filter-row table-filter-row--lined">
          <Form layout="inline" className="table-filter-form">
            <Form.Item label="买家ID">
              <Input
                allowClear
                value={filterBuyerId}
                onChange={setFilterBuyerId}
                onPressEnter={handleSearch}
                placeholder="输入买家ID"
                style={{ width: 185 }}
              />
            </Form.Item>
            <Form.Item label="买家昵称">
              <Input
                allowClear
                value={filterBuyerNick}
                onChange={setFilterBuyerNick}
                onPressEnter={handleSearch}
                placeholder="输入买家昵称"
                style={{ width: 185 }}
              />
            </Form.Item>
            <Space className="table-filter-actions">
              <Button type="primary" onClick={handleSearch}>搜索</Button>
              <Button onClick={handleReset}>重置</Button>
            </Space>
          </Form>
          <Space className="table-toolbar-right">
            <Button onClick={handleExport} className="accounts-header-btn">
              <Download />
              导出
            </Button>
            <Button onClick={() => fileInputRef.current?.click()} className="accounts-header-btn">
              <Upload />
              导入
            </Button>
            <input
              ref={fileInputRef}
              type="file"
              accept=".xlsx,.xls"
              onChange={handleImport}
              className="hidden"
            />
            <Button type="primary" onClick={() => setShowCreateModal(true)} className="accounts-header-btn">
              <Plus />
              新建
            </Button>
          </Space>
        </div>
        {selectedIds.size > 0 && (
          <div className="flex items-center">
            <Button
              status="danger"
              onClick={() => setBatchDeleteConfirm(true)}
              className="accounts-header-btn"
            >
              <Trash2 />
              删除选中({selectedIds.size})
            </Button>
          </div>
        )}
      </div>

      <Table
        rowKey="id"
        columns={columns}
        data={items}
        loading={loading}
        border={false}
        scroll={{ x: 1510 }}
        className="accounts-arco-table table-main"
        rowSelection={{
          type: 'checkbox',
          selectedRowKeys: Array.from(selectedIds),
          onChange: (selectedRowKeys) => {
            setSelectedIds(new Set(selectedRowKeys.map((key) => Number(key))))
          },
        }}
        pagination={false}
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

      {/* 新建弹窗 */}
      {showCreateModal && (
        <PersonalBlacklistFormModal
          onClose={() => setShowCreateModal(false)}
          onSuccess={handleCreateSuccess}
        />
      )}

      {/* 单条删除确认 */}
      <ConfirmModal
        isOpen={deleteConfirm.open}
        title="确认删除"
        message={`确定要删除买家 ${deleteConfirm.item?.buyer_id || ''} 的黑名单记录吗？`}
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm({ open: false, item: null })}
      />

      {/* 批量删除确认 */}
      <ConfirmModal
        isOpen={batchDeleteConfirm}
        title="批量删除确认"
        message={`确定要删除选中的 ${selectedIds.size} 条黑名单记录吗？删除后无法恢复。`}
        type="danger"
        onConfirm={handleBatchDelete}
        onCancel={() => setBatchDeleteConfirm(false)}
      />
    </div>
  )
}
