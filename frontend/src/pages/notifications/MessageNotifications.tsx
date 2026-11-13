import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { motion } from 'framer-motion'
import { Mail, RefreshCw, Plus, Trash2, Power, PowerOff, X, Loader2 } from 'lucide-react'
import { getMessageNotifications, setMessageNotification, getNotificationChannels, deleteMessageNotification } from '@/api/notifications'
import { getAccountDetails } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import type { MessageNotification, NotificationChannel, Account, NotifyType } from '@/types'

// 与「模板管理」里的三个模板一一对应。绑定渠道后可只勾其中几个，
// 只留「账号状态模板」时，买家聊天和发货成功都不会再消耗推送额度。
const NOTIFY_TYPE_LABELS: Record<NotifyType, string> = {
  chat: '聊天消息模板',
  delivery: '自动发货模板',
  account: '账号状态模板',
}
const ALL_NOTIFY_TYPES: NotifyType[] = ['chat', 'delivery', 'account']

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
  const [formNotifyTypes, setFormNotifyTypes] = useState<NotifyType[]>([...ALL_NOTIFY_TYPES])
  const [saving, setSaving] = useState(false)

  // 删除确认弹窗状态
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; notification: MessageNotification | null }>({ open: false, notification: null })
  const [deleting, setDeleting] = useState(false)

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
      const data = await getAccountDetails()
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
      await setMessageNotification(
        notification.cookie_id,
        notification.channel_id,
        !notification.enabled,
        notification.notify_types,
      )
      addToast({ type: 'success', message: notification.enabled ? '通知已禁用' : '通知已启用' })
      loadNotifications()
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  const handleDelete = async (notification: MessageNotification) => {
    setDeleting(true)
    try {
      await deleteMessageNotification(String(notification.id))
      addToast({ type: 'success', message: '通知已删除' })
      setDeleteConfirm({ open: false, notification: null })
      loadNotifications()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setDeleting(false)
    }
  }

  const openAddModal = () => {
    setFormAccountId('')
    setFormChannelId('')
    setFormEnabled(true)
    setFormNotifyTypes([...ALL_NOTIFY_TYPES])
    setIsModalOpen(true)
  }

  const toggleFormNotifyType = (type: NotifyType) => {
    setFormNotifyTypes((prev) => {
      const next = prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
      // 全取消没有意义，回落到全开，避免渠道变成永不触发
      return next.length === 0 ? [...ALL_NOTIFY_TYPES] : next
    })
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
      await setMessageNotification(formAccountId, Number(formChannelId), formEnabled, formNotifyTypes)
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
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">消息通知</h1>
        </div>
        <div className="flex gap-3">
          <button onClick={openAddModal} className="btn-ios-primary ">
            <Plus className="w-4 h-4" />
            添加通知
          </button>
          <button onClick={loadNotifications} className="btn-ios-secondary ">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {/* Notifications List */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="vben-card"
      >
        <div className="vben-card-header 
                      flex items-center justify-between">
          <h2 className="vben-card-title ">
            <Mail className="w-4 h-4" />
            通知规则
          </h2>
          <span className="badge-primary">{notifications.length} 条规则</span>
        </div>
        <div className="overflow-x-auto">
          <table className="table-ios">
            <thead>
              <tr>
                <th>账号ID</th>
                <th>通知渠道</th>
                <th>推送模板</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {notifications.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-gray-500">
                    <div className="flex flex-col items-center gap-2">
                      <Mail className="w-12 h-12 text-gray-300" />
                      <p>暂无消息通知配置</p>
                    </div>
                  </td>
                </tr>
              ) : (
                notifications.map((notification) => (
                  <tr key={`${notification.cookie_id}-${notification.channel_id}`}>
                    <td className="font-medium text-blue-600 dark:text-blue-400">
                      {(() => {
                        const account = accounts.find(acc => acc.id === notification.cookie_id)
                        return account?.note ? `${notification.cookie_id} (${account.note})` : notification.cookie_id
                      })()}
                    </td>
                    <td className="text-sm">
                      {notification.channel_name || `渠道 ${notification.channel_id}`}
                    </td>
                    <td className="text-xs whitespace-nowrap">
                      {(notification.notify_types && notification.notify_types.length > 0
                        ? notification.notify_types
                        : ALL_NOTIFY_TYPES
                      ).map((t) => (
                        <span
                          key={t}
                          className="inline-block mr-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
                        >
                          {NOTIFY_TYPE_LABELS[t] || t}
                        </span>
                      ))}
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
                        <button
                          onClick={() => setDeleteConfirm({ open: true, notification })}
                          className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
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

      {/* 添加通知弹窗 */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg min-h-[400px]">
            <div className="modal-header flex items-center justify-between">
              <h2 className="text-lg font-semibold">添加消息通知</h2>
              <button onClick={closeModal} className="p-1 hover:bg-gray-100 dark:hover:bg-slate-700 rounded-lg">
                <X className="w-4 h-4 text-gray-500" />
              </button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body space-y-4">
                <div className="input-group">
                  <label className="input-label">选择账号 *</label>
                  <Select
                    value={formAccountId}
                    onChange={setFormAccountId}
                    options={[
                      { value: '', label: '请选择账号', key: 'empty' },
                      ...accounts.map((account) => ({
                        value: account.id,
                        label: account.note ? `${account.id} (${account.note})` : account.id,
                        key: account.pk?.toString() || account.id,
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
                <div className="input-group">
                  <label className="input-label">启用哪几个模板</label>
                  <div className="flex flex-wrap gap-2 pt-1">
                    {ALL_NOTIFY_TYPES.map((t) => {
                      const on = formNotifyTypes.includes(t)
                      return (
                        <button
                          key={t}
                          type="button"
                          onClick={() => toggleFormNotifyType(t)}
                          className={`px-3 py-1.5 rounded-lg text-sm border transition-colors ${
                            on
                              ? 'bg-blue-50 border-blue-500 text-blue-600 dark:bg-blue-900/30 dark:text-blue-300'
                              : 'bg-white border-slate-300 text-slate-500 dark:bg-slate-800 dark:border-slate-600'
                          }`}
                        >
                          {NOTIFY_TYPE_LABELS[t]}
                        </button>
                      )
                    })}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    只勾「账号状态模板」时，仅在账号掉线、Cookie 失效、需要重新扫码时推送；
                    买家聊天和每单发货都不会再消耗你的推送额度
                  </p>
                </div>
                <div className="flex items-center justify-between pt-2">
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-200">启用此通知</span>
                  <button
                    type="button"
                    onClick={() => setFormEnabled(!formEnabled)}
                    className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                      formEnabled ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-600'
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        formEnabled ? 'translate-x-6' : 'translate-x-1'
                      }`}
                    />
                  </button>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" onClick={closeModal} className="btn-ios-secondary" disabled={saving}>
                  取消
                </button>
                <button type="submit" className="btn-ios-primary" disabled={saving}>
                  {saving ? (
                    <span className="flex items-center gap-2">
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

      {/* 删除确认弹窗 */}
      <ConfirmModal
        isOpen={deleteConfirm.open}
        title="删除确认"
        message="确定要删除这个消息通知吗？"
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={() => deleteConfirm.notification && handleDelete(deleteConfirm.notification)}
        onCancel={() => setDeleteConfirm({ open: false, notification: null })}
      />
    </div>
  )
}
