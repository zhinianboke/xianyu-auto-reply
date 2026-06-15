import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { MessageCircle, RefreshCw, Plus, Loader2 } from 'lucide-react'
import { getItemReplies, deleteItemReply, addItemReply, updateItemReply } from '@/api/items'
import { Button, Empty, Form, Input, Modal, Popconfirm, Select as ArcoSelect, Space, Table, type TableColumnProps } from '@arco-design/web-react'
import { getAccounts } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import type { ItemReply, Account } from '@/types'

interface ItemReplyTableRow extends ItemReply {
  key: string | number
}

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
        reply_content: formReply.trim(),  // 后端期望的字段名是 reply_content
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

  const columns: TableColumnProps<ItemReplyTableRow>[] = [
    {
      title: '账号ID',
      dataIndex: 'cookie_id',
      width: 140,
      render: (cookieId: string) => (
        <span className="text-slate-700 dark:text-slate-200">{cookieId}</span>
      ),
    },
    {
      title: '商品ID',
      dataIndex: 'item_id',
      width: 160,
      render: (itemId: string) => <span className="text-sm">{itemId}</span>,
    },
    {
      title: '商品标题',
      dataIndex: 'title',
      width: 180,
      render: (title?: string) => (
        <span className="block max-w-[160px] truncate">{title || '-'}</span>
      ),
    },
    {
      title: '回复内容',
      dataIndex: 'reply',
      width: 260,
      render: (reply: string) => (
        <span className="block max-w-[240px] truncate text-gray-500">{reply}</span>
      ),
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      width: 180,
      render: (createdAt?: string) => (
        <span className="text-gray-500 text-sm">
          {createdAt ? new Date(createdAt).toLocaleString() : '-'}
        </span>
      ),
    },
    {
      title: '操作',
      dataIndex: 'operation',
      width: 120,
      fixed: 'right',
      render: (_value, reply) => (
        <Space size={4}>
          <Button type="text" size="mini" onClick={() => openEditModal(reply)}>
            编辑
          </Button>
          <Popconfirm
            title="确定要删除这条商品回复吗？"
            okText="删除"
            cancelText="取消"
            okButtonProps={{ status: 'danger' }}
            onOk={() => handleDelete(reply)}
          >
            <Button
              type="text"
              size="mini"
              className="!text-red-500 hover:!text-red-500"
            >
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const tableData: ItemReplyTableRow[] = replies.map((reply) => ({
    ...reply,
    key: reply.id,
  }))

  if (loading && replies.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Replies List */}
      <div
        className="vben-card"
      >
        {/* 标题区 */}
        <div className="accounts-page-intro">
          <h1 className="page-title">指定商品回复</h1>
          <p className="page-description">为特定商品设置自动回复内容</p>
        </div>

        {/* 操作区 */}
        <div className="table-toolbar">
          <div className="table-filter-row table-filter-row--lined">
            <Form layout="inline" className="table-filter-form">
              <Form.Item label="筛选账号">
                <ArcoSelect
                  allowClear
                  value={selectedAccount || undefined}
                  onChange={(value) => setSelectedAccount(value || '')}
                  placeholder="所有账号"
                  style={{ width: 180 }}
                  options={[
                    { value: '', label: '所有账号' },
                    ...accounts.map((account) => ({
                      value: account.id,
                      label: account.id,
                    })),
                  ]}
                />
              </Form.Item>
            </Form>

            {/* 按钮区 */}
            <div className="flex gap-3">
              <Button
                type="primary"
                onClick={openAddModal} className="accounts-header-btn">
                <Plus />
                添加回复
              </Button>
              <Button onClick={loadReplies} className="accounts-header-btn">
                <RefreshCw />
                刷新
              </Button>
            </div>
          </div>
        </div>
        <Table
          rowKey="key"
          columns={columns}
          data={tableData}
          pagination={false}
          border={false}
          scroll={{ x: 1040 }}
          className="accounts-arco-table table-main"
          noDataElement={(
            <Empty
              icon={<MessageCircle className="w-12 h-12 text-gray-300" />}
              description="暂无商品回复数据"
            />
          )}
        />
      </div>

      <Modal
        visible={isModalOpen}
        title={editingReply ? '编辑商品回复' : '添加商品回复'}
        onCancel={closeModal}
        footer={null}
        unmountOnExit
        style={{ width: 640 }}
      >
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div>
              <label className="input-label">所属账号</label>
              <Input
                value={editingReply?.cookie_id || selectedAccount}
                disabled
              />
            </div>
            <div>
              <label className="input-label">商品ID</label>
              <Input
                value={formItemId}
                onChange={setFormItemId}
                placeholder="请输入商品ID"
              />
            </div>
            <div>
              <label className="input-label">商品标题（可选）</label>
              <Input
                value={formTitle}
                onChange={setFormTitle}
                placeholder="用于备注商品名称"
              />
            </div>
            <div>
              <label className="input-label">回复内容</label>
              <Input.TextArea
                value={formReply}
                onChange={setFormReply}
                placeholder="请输入自动回复内容"
                autoSize={{ minRows: 5, maxRows: 8 }}
              />
            </div>
          </div>
          <div className="mt-6 flex justify-end gap-3">
            <Button onClick={closeModal} disabled={saving}>
              取消
            </Button>
            <Button htmlType="submit" type="primary" disabled={saving}>
              {saving ? (
                <span className="flex items-center gap-2">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  保存中...
                </span>
              ) : (
                '保存'
              )}
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  )
}
