import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { motion } from 'framer-motion'
import { MessageCircle, RefreshCw, Plus, Edit2, Trash2, X, Loader2 } from 'lucide-react'
import { getItemReplies, deleteItemReply, addItemReply, updateItemReply } from '@/api/items'
import { getAccounts } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import type { ItemReply, Account } from '@/types'

export function ItemReplies() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [replies, setReplies] = useState<ItemReply[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingReply, setEditingReply] = useState<ItemReply | null>(null)
  const [formItemId, setFormItemId] = useState('')
  const [formTitle, setFormTitle] = useState('')
  const [formReply, setFormReply] = useState('')
  const [saving, setSaving] = useState(false)

  const loadReplies = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getItemReplies(selectedAccount || undefined)
      if (result.success) {
        setReplies(result.data || [])
      }
    } catch {
      addToast({ type: 'error', message: '加载商品回复列表失败' })
    } finally {
      setLoading(false)
    }
  }

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const data = await getAccounts()
      setAccounts(data)
    } catch {
      // ignore
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadAccounts()
    loadReplies()
  }, [_hasHydrated, isAuthenticated, token])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadReplies()
  }, [_hasHydrated, isAuthenticated, token, selectedAccount])

  const handleDelete = async (reply: ItemReply) => {
    if (!confirm('确定要删除这条商品回复吗？')) return
    try {
      await deleteItemReply(reply.cookie_id, reply.item_id)
      addToast({ type: 'success', message: '删除成功' })
      loadReplies()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    }
  }

  const openAddModal = () => {
    if (!selectedAccount) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }
    setEditingReply(null)
    setFormItemId('')
    setFormTitle('')
    setFormReply('')
    setIsModalOpen(true)
  }

  const openEditModal = (reply: ItemReply) => {
    setEditingReply(reply)
    setFormItemId(reply.item_id)
    setFormTitle(reply.title || '')
    setFormReply(reply.reply)
    setIsModalOpen(true)
  }

  const closeModal = () => {
    setIsModalOpen(false)
    setEditingReply(null)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!formItemId.trim()) {
      addToast({ type: 'warning', message: '请输入商品ID' })
      return
    }
    if (!formReply.trim()) {
      addToast({ type: 'warning', message: '请输入回复内容' })
      return
    }

    setSaving(true)
    try {
      const data = {
        cookie_id: editingReply?.cookie_id || selectedAccount,
        item_id: formItemId.trim(),
        title: formTitle.trim() || undefined,
        reply: formReply.trim(),
      }

      if (editingReply) {
        await updateItemReply(editingReply.cookie_id, editingReply.item_id, data)
        addToast({ type: 'success', message: '回复已更新' })
      } else {
        await addItemReply(selectedAccount, formItemId.trim(), data)
        addToast({ type: 'success', message: '回复已添加' })
      }

      closeModal()
      loadReplies()
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setSaving(false)
    }
  }

  if (loading && replies.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">指定商品回复</h1>
          <p className="page-description">为特定商品设置自动回复内容</p>
        </div>
        <div className="flex gap-3">
          <button onClick={openAddModal} className="btn-ios-primary ">
            <Plus className="w-4 h-4" />
            添加回复
          </button>
          <button onClick={loadReplies} className="btn-ios-secondary ">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {/* Filter */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="vben-card"
      >
        <div className="vben-card-body">
          <div className="max-w-xs">
            <label className="input-label">筛选账号</label>
            <Select
              value={selectedAccount}
              onChange={setSelectedAccount}
              options={[
                { value: '', label: '所有账号' },
                ...accounts.map((account) => ({
                  value: account.id,
                  label: account.id,
                })),
              ]}
              placeholder="选择账号"
            />
          </div>
        </div>
      </motion.div>

      {/* Replies List */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
        className="vben-card"
      >
        <div className="vben-card-header 
                      flex items-center justify-between">
          <h2 className="vben-card-title ">
            <MessageCircle className="w-4 h-4" />
            商品回复列表
          </h2>
          <span className="badge-primary">{replies.length} 条回复</span>
        </div>
        <div className="overflow-x-auto">
          <table className="table-ios">
            <thead>
              <tr>
                <th>账号ID</th>
                <th>商品ID</th>
                <th>商品标题</th>
                <th>回复内容</th>
                <th>创建时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {replies.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-8 text-gray-500">
                    <div className="flex flex-col items-center gap-2">
                      <MessageCircle className="w-12 h-12 text-gray-300" />
                      <p>暂无商品回复数据</p>
                    </div>
                  </td>
                </tr>
              ) : (
                replies.map((reply) => (
                  <tr key={reply.id}>
                    <td className="font-medium text-blue-600 dark:text-blue-400">{reply.cookie_id}</td>
                    <td className="text-sm">{reply.item_id}</td>
                    <td className="max-w-[150px] truncate">{reply.title || '-'}</td>
                    <td className="max-w-[200px] truncate text-gray-500">{reply.reply}</td>
                    <td className="text-gray-500 text-sm">
                      {reply.created_at ? new Date(reply.created_at).toLocaleString() : '-'}
                    </td>
                    <td>
                      <div className="">
                        <button
                          onClick={() => openEditModal(reply)}
                          className="p-2 rounded-lg hover:bg-gray-100 transition-colors"
                          title="编辑"
                        >
                          <Edit2 className="w-4 h-4 text-blue-500 dark:text-blue-400" />
                        </button>
                        <button
                          onClick={() => handleDelete(reply)}
                          className="p-2 rounded-lg hover:bg-red-50 transition-colors"
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
      </motion.div>

      {/* 添加/编辑弹窗 */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg">
            <div className="modal-header flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                {editingReply ? '编辑商品回复' : '添加商品回复'}
              </h2>
              <button onClick={closeModal} className="p-1 hover:bg-gray-100 rounded-lg">
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body space-y-4">
                <div>
                  <label className="input-label">所属账号</label>
                  <input
                    type="text"
                    value={editingReply?.cookie_id || selectedAccount}
                    disabled
                    className="input-ios bg-gray-100 cursor-not-allowed"
                  />
                </div>
                <div>
                  <label className="input-label">商品ID</label>
                  <input
                    type="text"
                    value={formItemId}
                    onChange={(e) => setFormItemId(e.target.value)}
                    className="input-ios"
                    placeholder="请输入商品ID"
                  />
                </div>
                <div>
                  <label className="input-label">商品标题（可选）</label>
                  <input
                    type="text"
                    value={formTitle}
                    onChange={(e) => setFormTitle(e.target.value)}
                    className="input-ios"
                    placeholder="用于备注商品名称"
                  />
                </div>
                <div>
                  <label className="input-label">回复内容</label>
                  <textarea
                    value={formReply}
                    onChange={(e) => setFormReply(e.target.value)}
                    className="input-ios h-28 resize-none"
                    placeholder="请输入自动回复内容"
                  />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" onClick={closeModal} className="btn-ios-secondary" disabled={saving}>
                  取消
                </button>
                <button type="submit" className="btn-ios-primary" disabled={saving}>
                  {saving ? (
                    <span className="">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      保存中...
                    </span>
                  ) : (
                    '保存'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
