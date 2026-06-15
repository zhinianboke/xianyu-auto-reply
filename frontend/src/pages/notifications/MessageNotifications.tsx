import { useState, useEffect, type FormEvent } from 'react'
import { Button, Modal, Popconfirm, Select, Space, Switch } from '@arco-design/web-react'
import { Mail, RefreshCw, Plus, Trash2, Power, PowerOff, Loader2 } from 'lucide-react'
import { getMessageNotifications, setMessageNotification, getNotificationChannels } from '@/api/notifications'
import { getAccounts } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import type { MessageNotification, NotificationChannel, Account } from '@/types'

export function MessageNotifications() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [notifications, setNotifications] = useState<MessageNotification[]>([])
  const [channels, setChannels] = useState<NotificationChannel[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [formAccountId, setFormAccountId] = useState('')
  const [formChannelId, setFormChannelId] = useState('')
  const [formEnabled, setFormEnabled] = useState(true)
  const [saving, setSaving] = useState(false)

  const loadNotifications = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getMessageNotifications()
      if (result.success) {
        setNotifications(result.data || [])
      }
    } catch {
      addToast({ type: 'error', message: '加载消息通知失败' })
    } finally {
      setLoading(false)
    }
  }

  const loadChannels = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const result = await getNotificationChannels()
      if (result.success) {
        setChannels(result.data || [])
      }
    } catch {
      // ignore
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
    loadChannels()
    loadAccounts()
    loadNotifications()
  }, [_hasHydrated, isAuthenticated, token])

  const handleToggleEnabled = async (notification: MessageNotification) => {
    try {
      await setMessageNotification(notification.cookie_id, notification.channel_id, !notification.enabled)
      addToast({ type: 'success', message: notification.enabled ? '通知已禁用' : '通知已启用' })
      loadNotifications()
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  const handleDelete = async (notification: MessageNotification) => {
    try {
      await setMessageNotification(notification.cookie_id, notification.channel_id, false)
      addToast({ type: 'success', message: '通知已禁用' })
      loadNotifications()
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  const openAddModal = () => {
    setFormAccountId('')
    setFormChannelId('')
    setFormEnabled(true)
    setIsModalOpen(true)
  }

  const closeModal = () => {
    setIsModalOpen(false)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!formAccountId) {
      addToast({ type: 'warning', message: '请选择账号' })
      return
    }
    if (!formChannelId) {
      addToast({ type: 'warning', message: '请选择通知渠道' })
      return
    }

    setSaving(true)
    try {
      await setMessageNotification(formAccountId, Number(formChannelId), formEnabled)
      addToast({ type: 'success', message: '通知已添加' })
      closeModal()
      loadNotifications()
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Notifications List */}
      <div
        className="vben-card"
      >
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div className="accounts-page-intro">
            <h1 className="page-title">消息通知</h1>
            <p className="page-description">配置关键词触发的消息通知</p>
          </div>
          <div className="accounts-toolbar">
            <div className="accounts-filter-row accounts-filter-row--lined">
              <div className="accounts-action-row">
                <Space className="accounts-toolbar-right">
                  <Button
                    type="primary"
                    onClick={openAddModal} className="accounts-header-btn">
                    <Plus />
                    添加通知
                  </Button>
                  <Button onClick={loadNotifications} className="accounts-header-btn">
                    <RefreshCw />
                    刷新
                  </Button>
                </Space>
              </div>
            </div>
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="table-ios">
            <thead>
              <tr>
                <th>账号ID</th>
                <th>通知渠道</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {notifications.length === 0 ? (
                <tr>
                  <td colSpan={4} className="text-center py-8 text-gray-500">
                    <div className="flex flex-col items-center gap-2">
                      <Mail className="w-12 h-12 text-gray-300" />
                      <p>暂无消息通知配置</p>
                    </div>
                  </td>
                </tr>
              ) : (
                notifications.map((notification) => (
                  <tr key={`${notification.cookie_id}-${notification.channel_id}`}>
                    <td className="font-medium text-blue-600 dark:text-blue-400">{notification.cookie_id}</td>
                    <td className="text-sm">
                      {notification.channel_name || `渠道 ${notification.channel_id}`}
                    </td>
                    <td>
                      {notification.enabled ? (
                        <span className="badge-success">启用</span>
                      ) : (
                        <span className="badge-danger">禁用</span>
                      )}
                    </td>
                    <td>
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleToggleEnabled(notification)}
                          className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-slate-700 transition-colors"
                          title={notification.enabled ? '禁用' : '启用'}
                        >
                          {notification.enabled ? (
                            <PowerOff className="w-4 h-4 text-amber-500" />
                          ) : (
                            <Power className="w-4 h-4 text-emerald-500" />
                          )}
                        </button>
                        <Popconfirm
                          title="确定要删除这个消息通知吗？"
                          okText="删除"
                          cancelText="取消"
                          okButtonProps={{ status: 'danger' }}
                          onOk={() => handleDelete(notification)}
                        >
                          <button
                            className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                            title="删除"
                          >
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </button>
                        </Popconfirm>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      <Modal
        visible={isModalOpen}
        title="添加消息通知"
        onCancel={closeModal}
        footer={null}
        unmountOnExit
        style={{ width: 520 }}
      >
        <form onSubmit={handleSubmit}>
          <div className="space-y-4">
            <div className="input-group">
              <label className="input-label">选择账号 *</label>
              <Select
                value={formAccountId}
                onChange={setFormAccountId}
                options={[
                  { value: '', label: '请选择账号' },
                  ...accounts.map((account) => ({
                    value: account.id,
                    label: account.id,
                  })),
                ]}
                placeholder="请选择账号"
              />
            </div>
            <div className="input-group">
              <label className="input-label">选择通知渠道 *</label>
              <Select
                value={formChannelId}
                onChange={setFormChannelId}
                options={[
                  { value: '', label: '请选择通知渠道' },
                  ...channels.map((channel) => ({
                    value: String(channel.id),
                    label: channel.name || channel.channel_name || `渠道 ${channel.id}`,
                  })),
                ]}
                placeholder="请选择通知渠道"
              />
            </div>
            <div className="flex items-center justify-between pt-2">
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">启用此通知</span>
              <Switch checked={formEnabled} onChange={setFormEnabled} />
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
