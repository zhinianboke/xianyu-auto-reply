/**
 * 消息过滤规则管理页面
 * 
 * 功能：
 * - 查询账号下所有消息过滤规则
 * - 新建规则（支持filter_type多选）
 * - 修改规则
 * - 删除规则
 * - 启用/禁用规则
 */
import { useState, useEffect } from 'react'
import { motion } from 'framer-motion'
import { RefreshCw, Plus } from 'lucide-react'
import { getMessageFilters, createMessageFilter, createMessageFiltersBatch, updateMessageFilter, deleteMessageFilter, batchDeleteMessageFilters, toggleMessageFilter } from '@/api/messageFilters'
import { getAccountDetails } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import { useAuthStore } from '@/store/authStore'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { getApiErrorMessage } from '@/utils/request'
import { MessageFilterFormModal, type MessageFilterFormMode, type MessageFilterFormValues } from './MessageFilterFormModal'
import { MessageFilterRulesTable } from './MessageFilterRulesTable'
import type { MessageFilter, Account, MessageFilterType } from '@/types'

// 过滤类型选项
const FILTER_TYPE_OPTIONS: Array<{ value: MessageFilterType; label: string }> = [
  { value: 'skip_reply', label: '跳过自动回复' },
  { value: 'skip_notify', label: '跳过消息通知' },
  { value: 'skip_ai_reply_output', label: 'AI回复黑名单' },
]

export function MessageFilters() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState<MessageFilter[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')
  
  // 新建/编辑弹窗状态
  const [modalMode, setModalMode] = useState<MessageFilterFormMode | null>(null)
  const [editingFilter, setEditingFilter] = useState<MessageFilter | null>(null)

  // 多选删除状态
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [batchDeleting, setBatchDeleting] = useState(false)

  // 删除确认弹窗状态
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; filter: MessageFilter | null }>({ open: false, filter: null })
  const [batchDeleteConfirm, setBatchDeleteConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // 前端分页状态
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)

  // 计算分页数据
  const totalPages = Math.ceil(filters.length / pageSize)
  const paginatedFilters = filters.slice((currentPage - 1) * pageSize, currentPage * pageSize)

  // 分页切换
  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setCurrentPage(newPage)
    }
  }

  // 每页条数切换
  const handlePageSizeChange = (newPageSize: number) => {
    setPageSize(newPageSize)
    setCurrentPage(1)
  }

  // 加载账号列表
  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const data = await getAccountDetails()
      setAccounts(data)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载账号列表失败') })
    }
  }

  // 加载过滤规则
  const loadFilters = async (accountIdOverride?: string) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const targetAccountId = accountIdOverride !== undefined ? accountIdOverride : selectedAccount
      const data = await getMessageFilters(targetAccountId || undefined)
      setFilters(Array.isArray(data) ? data : [])
      setSelectedIds([]) // 重置选中状态
    } catch (error) {
      setFilters([])
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载过滤规则失败') })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadAccounts()
  }, [_hasHydrated, isAuthenticated, token])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadFilters()
  }, [_hasHydrated, isAuthenticated, token, selectedAccount])

  // 打开新建弹窗
  const openAddModal = () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    setEditingFilter(null)
    setModalMode('create')
  }

  const openBatchModal = () => {
    if (accounts.length === 0) {
      addToast({ type: 'warning', message: '暂无可选账号' })
      return
    }
    setEditingFilter(null)
    setModalMode('batch')
  }

  // 打开编辑弹窗
  const openEditModal = (filter: MessageFilter) => {
    setEditingFilter(filter)
    setModalMode('edit')
  }

  // 提交表单
  const handleSubmit = async ({ accountId, accountIds, keyword, filterTypes }: MessageFilterFormValues) => {
    if (modalMode === 'edit') {
      if (!editingFilter) {
        return { success: false, message: '过滤规则不存在' }
      }
      const result = await updateMessageFilter(editingFilter.id, {
        keyword,
        filter_type: filterTypes[0],
      })
      if (result.success) {
        await loadFilters()
      }
      return result
    }

    if (modalMode === 'batch') {
      const normalizedAccountIds = Array.from(new Set((accountIds || []).map((id) => id.trim()).filter((id) => id)))
      const expectedCombinationCount = normalizedAccountIds.length * filterTypes.length
      const result = await createMessageFiltersBatch({
        account_ids: normalizedAccountIds,
        keyword,
        filter_types: filterTypes,
      })
      if (result.success) {
        const nextSelectedAccount = normalizedAccountIds.length > 1 ? '' : (normalizedAccountIds[0] || selectedAccount)
        setCurrentPage(1)
        if (nextSelectedAccount !== selectedAccount) {
          setSelectedAccount(nextSelectedAccount)
        } else {
          await loadFilters(nextSelectedAccount)
        }
      }
      return {
        ...result,
        message: result.success
          ? `已选择${normalizedAccountIds.length}个账号 × ${filterTypes.length}种类型，共${expectedCombinationCount}个组合；新增${result.data?.created_count || 0}条，跳过${result.data?.failed_count || 0}条。`
          : result.message,
      }
    }

    const targetAccountId = accountId || selectedAccount
    if (!targetAccountId) {
      return { success: false, message: '请先选择账号' }
    }

    const result = await createMessageFilter({
      account_id: targetAccountId,
      keyword,
      filter_types: filterTypes,
    })
    if (result.success) {
      await loadFilters()
    }
    return result
  }

  const closeModal = () => {
    setModalMode(null)
    setEditingFilter(null)
  }

  // 删除规则
  const handleDelete = async (filter: MessageFilter) => {
    setDeleting(true)
    try {
      const result = await deleteMessageFilter(filter.id)
      if (result.success) {
        addToast({ type: 'success', message: '删除成功' })
        setDeleteConfirm({ open: false, filter: null })
        loadFilters()
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '删除失败') })
    } finally {
      setDeleting(false)
    }
  }

  // 切换启用状态
  const handleToggle = async (filter: MessageFilter) => {
    try {
      const result = await toggleMessageFilter(filter.id)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '操作成功' })
        loadFilters()
      } else {
        addToast({ type: 'error', message: result.message || '操作失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '操作失败') })
    }
  }

  // 切换单个选中
  const toggleSelect = (id: number) => {
    setSelectedIds(prev => 
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    )
  }

  // 全选/取消全选
  const toggleSelectAll = () => {
    if (selectedIds.length === filters.length) {
      setSelectedIds([])
    } else {
      setSelectedIds(filters.map(f => f.id))
    }
  }

  // 批量删除
  const handleBatchDelete = async () => {
    if (selectedIds.length === 0) {
      addToast({ type: 'warning', message: '请先选择要删除的规则' })
      return
    }
    
    try {
      setBatchDeleting(true)
      const result = await batchDeleteMessageFilters(selectedIds)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '删除成功' })
        setBatchDeleteConfirm(false)
        loadFilters()
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '删除失败') })
    } finally {
      setBatchDeleting(false)
    }
  }

  // 获取过滤类型显示文本
  const getFilterTypeLabel = (type: string) => {
    const option = FILTER_TYPE_OPTIONS.find(o => o.value === type)
    return option?.label || type
  }

  if (loading && accounts.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* 页面标题 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">消息过滤</h1>
          <p className="page-description">管理消息过滤规则，支持跳过自动回复、消息通知和AI回复黑名单</p>
        </div>
        <div className="flex flex-wrap gap-3">
          <button type="button" onClick={openAddModal} className="btn-ios-primary">
            <Plus className="w-4 h-4" />
            新建规则
          </button>
          <button type="button" onClick={openBatchModal} className="btn-ios-secondary">
            <Plus className="w-4 h-4" />
            批量维护
          </button>
          <button type="button" onClick={() => void loadFilters()} className="btn-ios-secondary">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {/* 账号选择 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="vben-card"
      >
        <div className="vben-card-body">
          <div className="max-w-md">
            <label className="input-label">选择账号</label>
            <Select
              value={selectedAccount}
              onChange={setSelectedAccount}
              options={
                accounts.length === 0
                  ? [{ value: '', label: '暂无账号', key: 'empty' }]
                  : [
                      { value: '', label: '全部账号', key: 'all' },
                      ...accounts.map((account) => ({
                        value: account.id,
                        label: account.note ? `${account.id} (${account.note})` : account.id,
                        key: account.pk?.toString() || account.id,
                      }))
                    ]
              }
              placeholder="选择账号"
            />
          </div>
        </div>
      </motion.div>

      {/* 规则列表 */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <MessageFilterRulesTable
          loading={loading}
          filters={filters}
          paginatedFilters={paginatedFilters}
          selectedIds={selectedIds}
          batchDeleting={batchDeleting}
          currentPage={currentPage}
          pageSize={pageSize}
          totalPages={totalPages}
          getFilterTypeLabel={getFilterTypeLabel}
          onToggleSelect={toggleSelect}
          onToggleSelectAll={toggleSelectAll}
          onOpenBatchDeleteConfirm={() => setBatchDeleteConfirm(true)}
          onToggle={handleToggle}
          onEdit={openEditModal}
          onDelete={(filter) => setDeleteConfirm({ open: true, filter })}
          onPageChange={handlePageChange}
          onPageSizeChange={handlePageSizeChange}
        />
      </motion.div>

      {/* 新建/编辑弹窗 */}
      {modalMode && (
        <MessageFilterFormModal
          mode={modalMode}
          accounts={accounts}
          selectedAccount={selectedAccount}
          initialFilter={editingFilter}
          filterTypeOptions={FILTER_TYPE_OPTIONS}
          onClose={closeModal}
          onSubmit={handleSubmit}
        />
      )}

      {/* 删除确认弹窗 */}
      <ConfirmModal
        isOpen={deleteConfirm.open}
        title="删除确认"
        message="确定要删除这条过滤规则吗？删除后无法恢复。"
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={() => deleteConfirm.filter && handleDelete(deleteConfirm.filter)}
        onCancel={() => setDeleteConfirm({ open: false, filter: null })}
      />

      {/* 批量删除确认弹窗 */}
      <ConfirmModal
        isOpen={batchDeleteConfirm}
        title="批量删除确认"
        message={`确定要删除选中的 ${selectedIds.length} 条规则吗？删除后无法恢复。`}
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={batchDeleting}
        onConfirm={handleBatchDelete}
        onCancel={() => setBatchDeleteConfirm(false)}
      />
    </div>
  )
}
