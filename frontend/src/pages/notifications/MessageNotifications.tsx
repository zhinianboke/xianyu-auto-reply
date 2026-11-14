import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { motion } from 'framer-motion'
import { Edit2, Mail, RefreshCw, Plus, Trash2, X, Loader2 } from 'lucide-react'
import { getMessageNotificationPage, setMessageNotification, updateMessageNotificationEnabled, getNotificationChannels, deleteMessageNotification } from '@/api/notifications'
import { getAccountDetails } from '@/api/accounts'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { Pager } from '@/components/common/Pager'
import { getApiErrorMessage } from '@/utils/request'
import { useNotificationTypeOptions } from './useNotificationTypeOptions'
import type { MessageNotification, NotificationChannel, Account, NotifyType } from '@/types'

export function MessageNotifications() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const canLoad = _hasHydrated && isAuthenticated && Boolean(token)
  const { options: notifyTypeOptions, loading: notifyTypesLoading, error: notifyTypesError, reload: reloadNotifyTypes } = useNotificationTypeOptions(canLoad)
  const allNotifyTypes = notifyTypeOptions.map((option) => option.value)
  const notifyTypeLabels = Object.fromEntries(
    notifyTypeOptions.map((option) => [option.value, option.label]),
  ) as Partial<Record<NotifyType, string>>
  const [loading, setLoading] = useState(true)
  const [notifications, setNotifications] = useState<MessageNotification[]>([])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [channels, setChannels] = useState<NotificationChannel[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingNotification, setEditingNotification] = useState<MessageNotification | null>(null)
  const [formAccountId, setFormAccountId] = useState('')
  const [formChannelId, setFormChannelId] = useState('')
  const [formEnabled, setFormEnabled] = useState(true)
  const [formNotifyTypes, setFormNotifyTypes] = useState<NotifyType[]>([])
  const [saving, setSaving] = useState(false)
  const [operatingId, setOperatingId] = useState<number | null>(null)

  // 删除确认弹窗状态
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; notification: MessageNotification | null }>({ open: false, notification: null })
  const [deleting, setDeleting] = useState(false)

  const loadNotifications = async (targetPage = page, targetPageSize = pageSize) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getMessageNotificationPage(targetPage, targetPageSize)
      if (!result.success || !result.data) {
        addToast({ type: 'error', message: result.message || '加载消息通知失败' })
        return
      }
      setNotifications(result.data.items)
      setPage(result.data.page)
      setPageSize(result.data.page_size)
      setTotal(result.data.total)
      setPages(result.data.pages)
    } catch (reason) {
      addToast({ type: 'error', message: getApiErrorMessage(reason, '加载消息通知失败') })
    } finally {
      setLoading(false)
    }
  }

  const loadChannels = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const result = await getNotificationChannels()
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '加载通知渠道失败' })
        return
      }
      setChannels(result.data || [])
    } catch (reason) {
      addToast({ type: 'error', message: getApiErrorMessage(reason, '加载通知渠道失败') })
    }
  }

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const data = await getAccountDetails()
      setAccounts(data)
    } catch (reason) {
      addToast({ type: 'error', message: getApiErrorMessage(reason, '加载账号列表失败') })
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadChannels()
    loadAccounts()
    loadNotifications()
  }, [_hasHydrated, isAuthenticated, token])

  const handleToggleEnabled = async (notification: MessageNotification) => {
    const subscriptionEnabled = notification.subscription_enabled ?? notification.enabled
    setOperatingId(notification.id)
    try {
      const result = await updateMessageNotificationEnabled(notification.id, !subscriptionEnabled)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '操作失败' })
        return
      }
      addToast({ type: 'success', message: subscriptionEnabled ? '通知绑定已禁用' : '通知绑定已启用' })
      void loadNotifications()
    } catch (reason) {
      addToast({ type: 'error', message: getApiErrorMessage(reason, '操作失败') })
    } finally {
      setOperatingId(null)
    }
  }

  const handleDelete = async (notification: MessageNotification) => {
    setDeleting(true)
    try {
      const result = await deleteMessageNotification(String(notification.id))
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '删除失败' })
        return
      }
      addToast({ type: 'success', message: '通知已删除' })
      setDeleteConfirm({ open: false, notification: null })
      const nextPage = notifications.length === 1 && page > 1 ? page - 1 : page
      void loadNotifications(nextPage)
    } catch (reason) {
      addToast({ type: 'error', message: getApiErrorMessage(reason, '删除失败') })
    } finally {
      setDeleting(false)
    }
  }

  const openAddModal = () => {
    if (notifyTypesError || allNotifyTypes.length === 0) {
      addToast({ type: 'error', message: notifyTypesError || '通知类型尚未加载完成' })
      return
    }
    setEditingNotification(null)
    setFormAccountId('')
    setFormChannelId('')
    setFormEnabled(true)
    setFormNotifyTypes([...allNotifyTypes])
    setIsModalOpen(true)
  }

  const openEditModal = (notification: MessageNotification) => {
    if (notifyTypesError || allNotifyTypes.length === 0) {
      addToast({ type: 'error', message: notifyTypesError || '通知类型尚未加载完成' })
      return
    }
    setEditingNotification(notification)
    setFormAccountId(notification.cookie_id)
    setFormChannelId(String(notification.channel_id))
    setFormEnabled(notification.subscription_enabled ?? notification.enabled)
    setFormNotifyTypes(
      notification.notify_types?.filter((type) => allNotifyTypes.includes(type)) || [...allNotifyTypes],
    )
    setIsModalOpen(true)
  }

  const toggleFormNotifyType = (type: NotifyType) => {
    setFormNotifyTypes((prev) => {
      if (prev.includes(type) && prev.length === 1) {
        addToast({ type: 'warning', message: '请至少保留一种通知类型' })
        return prev
      }
      const next = prev.includes(type) ? prev.filter((t) => t !== type) : [...prev, type]
      return next
    })
  }

  const closeModal = () => {
    setIsModalOpen(false)
    setEditingNotification(null)
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
    if (formNotifyTypes.length === 0) {
      addToast({ type: 'warning', message: '请至少选择一种通知类型' })
      return
    }

    setSaving(true)
    try {
      const result = await setMessageNotification(formAccountId, Number(formChannelId), formEnabled, formNotifyTypes, editingNotification?.id)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '保存失败' })
        return
      }
      addToast({ type: 'success', message: editingNotification ? '通知已更新' : '通知已添加' })
      closeModal()
      void loadNotifications(editingNotification ? page : 1)
    } catch (reason) {
      addToast({ type: 'error', message: getApiErrorMessage(reason, '保存失败') })
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
          <button onClick={openAddModal} className="btn-ios-primary" disabled={notifyTypesLoading || Boolean(notifyTypesError)}>
            <Plus className="w-4 h-4" />
            添加通知
          </button>
          <button onClick={() => void loadNotifications()} className="btn-ios-secondary">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {notifyTypesError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300 flex flex-wrap items-center justify-between gap-3">
          <span>{notifyTypesError}</span>
          <button type="button" onClick={() => void reloadNotifyTypes()} className="btn-ios-secondary">
            重新加载
          </button>
        </div>
      )}

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
          <span className="badge-primary">{total} 条规则</span>
        </div>
        <div className="table-scroll">
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
                        : allNotifyTypes
                      ).map((t) => (
                        <span
                          key={t}
                          className="inline-block mr-1 px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300"
                        >
                          {notifyTypeLabels[t] || t}
                        </span>
                      ))}
                    </td>
                    <td>
                      {notification.channel_enabled === false ? (
                        <span className="badge-warning">渠道已禁用</span>
                      ) : (notification.subscription_enabled ?? notification.enabled) ? (
                        <span className="badge-success">启用</span>
                      ) : (
                        <span className="badge-danger">禁用</span>
                      )}
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={() => handleToggleEnabled(notification)}
                          disabled={operatingId === notification.id}
                          className="text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          {operatingId === notification.id
                            ? '处理中...'
                            : (notification.subscription_enabled ?? notification.enabled)
                              ? '禁用绑定'
                              : '启用绑定'}
                        </button>
                        <button
                          onClick={() => openEditModal(notification)}
                          className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 hover:underline"
                        >
                          <Edit2 className="w-3.5 h-3.5" />
                          编辑
                        </button>
                        <button
                          onClick={() => setDeleteConfirm({ open: true, notification })}
                          className="inline-flex items-center gap-1 text-red-600 dark:text-red-400 hover:underline"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          删除
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
        <Pager
          page={page}
          pageSize={pageSize}
          total={total}
          totalPages={pages}
          loading={loading}
          onPageChange={(nextPage) => void loadNotifications(nextPage)}
          onPageSizeChange={(nextPageSize) => void loadNotifications(1, nextPageSize)}
        />
      </motion.div>

      {/* 添加通知弹窗 */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg min-h-[400px]">
            <div className="modal-header flex items-center justify-between">
              <h2 className="text-lg font-semibold">{editingNotification ? '编辑消息通知' : '添加消息通知'}</h2>
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
                    disabled={Boolean(editingNotification)}
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
                    disabled={Boolean(editingNotification)}
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
                    {notifyTypeOptions.map(({ value: t, label }) => {
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
                          {label}
                        </button>
                      )
                    })}
                  </div>
                  <p className="text-xs text-slate-500 mt-1">
                    只勾「{notifyTypeLabels.account || 'account'}」时，仅在账号掉线、Cookie 失效、需要重新扫码时推送；
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
        message="确定要删除这个消息通知吗？删除后将停止推送，历史配置会保留。"
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
