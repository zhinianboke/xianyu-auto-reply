import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { RefreshCw, X, Loader2 } from 'lucide-react'
import { getNotificationChannelPage, deleteNotificationChannel, updateNotificationChannel, testNotificationChannel, addNotificationChannel } from '@/api/notifications'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { Pager } from '@/components/common/Pager'
import { getApiErrorMessage } from '@/utils/request'
import { useNotificationTypeOptions } from './useNotificationTypeOptions'
import { NotificationChannelList } from './NotificationChannelList'
import { channelTypeLabels, channelTypes, defaultTemplates, getChannelConfigHint, getTemplateValidationError, notifyTypeHints, parseNotifyTypes, splitTemplateConfig, templateConfigKeys, templateVariables } from './notificationChannelConfig'
import type { ChannelType } from './notificationChannelConfig'
import type { NotificationChannel, NotifyType } from '@/types'

export function NotificationChannels() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const canLoad = _hasHydrated && isAuthenticated && Boolean(token)
  const { options: notifyTypeOptions, loading: notifyTypesLoading, error: notifyTypesError, reload: reloadNotifyTypes } = useNotificationTypeOptions(canLoad)
  const allNotifyTypes = notifyTypeOptions.map((option) => option.value)
  const [loading, setLoading] = useState(true)
  const [channels, setChannels] = useState<NotificationChannel[]>([])
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [typeCounts, setTypeCounts] = useState<Record<string, number>>({})
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingChannel, setEditingChannel] = useState<NotificationChannel | null>(null)
  const [selectedType, setSelectedType] = useState<ChannelType | null>(null)
  const [formName, setFormName] = useState('')
  const [formConfig, setFormConfig] = useState('')
  const [formTemplates, setFormTemplates] = useState<Record<NotifyType, string>>({ ...defaultTemplates })
  const [formNotifyTypes, setFormNotifyTypes] = useState<NotifyType[]>([])
  const [formEnabled, setFormEnabled] = useState(true)
  const [saving, setSaving] = useState(false)
  const [operatingChannelId, setOperatingChannelId] = useState<string | null>(null)

  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; id: string | null }>({ open: false, id: null })
  const [deleting, setDeleting] = useState(false)

  const loadChannels = async (targetPage = page, targetPageSize = pageSize) => {
    if (!_hasHydrated || !isAuthenticated || !token) {
      setLoading(false)
      return
    }
    try {
      setLoading(true)
      const result = await getNotificationChannelPage(targetPage, targetPageSize)
      if (!result.success || !result.data) {
        addToast({ type: 'error', message: result.message || '加载通知渠道失败' })
        return
      }
      setChannels(result.data.items)
      setPage(result.data.page)
      setPageSize(result.data.page_size)
      setTotal(result.data.total)
      setTypeCounts(result.data.type_counts)
    } catch (reason) {
      addToast({ type: 'error', message: getApiErrorMessage(reason, '加载通知渠道失败') })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated) return
    if (!isAuthenticated || !token) {
      setLoading(false)
      return
    }
    loadChannels()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [_hasHydrated, isAuthenticated, token])

  const handleToggleEnabled = async (channel: NotificationChannel) => {
    setOperatingChannelId(channel.id)
    try {
      const result = await updateNotificationChannel(channel.id, {
        enabled: !channel.enabled,
      })
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '操作失败' })
        return
      }
      addToast({ type: 'success', message: channel.enabled ? '渠道已禁用' : '渠道已启用' })
      void loadChannels()
    } catch (reason) {
      addToast({ type: 'error', message: getApiErrorMessage(reason, '操作失败') })
    } finally {
      setOperatingChannelId(null)
    }
  }

  const handleTest = async (id: string) => {
    setOperatingChannelId(id)
    try {
      const result = await testNotificationChannel(id)
      if (result.success) {
        addToast({ type: 'success', message: '测试消息发送成功' })
      } else {
        addToast({ type: 'error', message: result.message || '测试失败' })
      }
    } catch (reason) {
      addToast({ type: 'error', message: getApiErrorMessage(reason, '测试失败') })
    } finally {
      setOperatingChannelId(null)
    }
  }

  const handleDelete = async (id: string) => {
    setDeleting(true)
    try {
      const result = await deleteNotificationChannel(id)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '删除失败' })
        return
      }
      addToast({ type: 'success', message: '删除成功' })
      setDeleteConfirm({ open: false, id: null })
      void loadChannels()
    } catch (reason) {
      addToast({ type: 'error', message: getApiErrorMessage(reason, '删除失败') })
    } finally {
      setDeleting(false)
    }
  }

  const openConfigModal = (type: ChannelType) => {
    if (notifyTypesError || allNotifyTypes.length === 0) {
      addToast({ type: 'error', message: notifyTypesError || '通知类型尚未加载完成' })
      return
    }
    const typeConfig = channelTypes.find(c => c.type === type)
    setSelectedType(type)
    setEditingChannel(null)
    // 同类型已存在时，默认名称追加序号以便区分
    const count = typeCounts[type] || 0
    const baseName = typeConfig?.label || ''
    setFormName(count > 0 ? `${baseName} ${count + 1}` : baseName)
    // 新建时默认填充样例配置
    if (typeConfig?.defaultConfig) {
      setFormConfig(JSON.stringify(typeConfig.defaultConfig, null, 2))
    } else {
      setFormConfig('')
    }
    setFormTemplates({ ...defaultTemplates })
    setFormNotifyTypes([...allNotifyTypes])
    setFormEnabled(true)
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

  const openEditModal = (channel: NotificationChannel) => {
    if (notifyTypesError || allNotifyTypes.length === 0) {
      addToast({ type: 'error', message: notifyTypesError || '通知类型尚未加载完成' })
      return
    }
    setSelectedType(channel.type as ChannelType)
    setEditingChannel(channel)
    setFormName(channel.name)
    // 历史异常原文保留在编辑器中供用户修复，禁止用示例配置覆盖。
    const { templates, channelConfig } = splitTemplateConfig(channel.config)
    if (channel.config_error) {
      setFormConfig(channel.raw_config || '')
      addToast({ type: 'warning', message: channel.config_error })
    } else if (Object.keys(channelConfig).length > 0) {
      setFormConfig(JSON.stringify(channelConfig, null, 2))
    } else {
      setFormConfig('{}')
    }
    setFormTemplates(templates)
    setFormNotifyTypes(parseNotifyTypes(channel.config?.notify_types, allNotifyTypes))
    setFormEnabled(channel.enabled)
    setIsModalOpen(true)
  }

  const closeModal = () => {
    setIsModalOpen(false)
    setEditingChannel(null)
    setSelectedType(null)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!formName.trim()) {
      addToast({ type: 'warning', message: '请输入渠道名称' })
      return
    }
    if (!selectedType) return
    if (formNotifyTypes.length === 0) {
      addToast({ type: 'warning', message: '请至少选择一种通知类型' })
      return
    }

    setSaving(true)
    try {
      let config: Record<string, unknown> = {}
      if (formConfig.trim()) {
        try {
          config = JSON.parse(formConfig)
        } catch {
          addToast({ type: 'error', message: '配置JSON格式错误' })
          setSaving(false)
          return
        }
      }

      if (!config || typeof config !== 'object' || Array.isArray(config)) {
        addToast({ type: 'error', message: '渠道配置必须为 JSON 对象' })
        return
      }

      for (const definition of notifyTypeOptions) {
        delete config[templateConfigKeys[definition.value]]
        const template = formTemplates[definition.value]
        const validationError = getTemplateValidationError(template, definition.value)
        if (validationError) {
          addToast({ type: 'error', message: `${definition.label}${validationError}` })
          return
        }
        if (template.trim() && template !== defaultTemplates[definition.value]) {
          config[templateConfigKeys[definition.value]] = template
        }
      }

      // 显式保存全选，区分“用户选择全类型”和“旧客户端未提交字段”。
      config.notify_types = [...formNotifyTypes]

      const data = {
        name: formName.trim(),
        type: selectedType,
        config,
        enabled: formEnabled,
      }

      const result = editingChannel
        ? await updateNotificationChannel(editingChannel.id, data)
        : await addNotificationChannel(data)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '保存失败' })
        return
      }
      addToast({ type: 'success', message: editingChannel ? '渠道已更新' : '渠道已添加' })

      closeModal()
      void loadChannels(editingChannel ? page : 1)
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
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">通知渠道</h1>
          <p className="page-description">管理消息通知渠道，支持钉钉、飞书、邮件等多种方式</p>
        </div>
        <button onClick={() => void loadChannels()} className="btn-ios-secondary">
          <RefreshCw className="w-4 h-4" />
          刷新
        </button>
      </div>

      {notifyTypesError && (
        <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-800 dark:bg-red-900/20 dark:text-red-300 flex flex-wrap items-center justify-between gap-3">
          <span>{notifyTypesError}</span>
          <button type="button" onClick={() => void reloadNotifyTypes()} className="btn-ios-secondary">
            重新加载
          </button>
        </div>
      )}

      <NotificationChannelList
        channels={channels}
        typeCounts={typeCounts}
        notifyTypesUnavailable={notifyTypesLoading || Boolean(notifyTypesError)}
        operatingChannelId={operatingChannelId}
        onCreate={openConfigModal}
        onToggle={handleToggleEnabled}
        onTest={handleTest}
        onEdit={openEditModal}
        onDelete={(id) => setDeleteConfirm({ open: true, id })}
      />
      <Pager page={page} pageSize={pageSize} total={total} loading={loading}
        onPageChange={(next) => void loadChannels(next)}
        onPageSizeChange={(size) => void loadChannels(1, size)} />

      {/* 配置弹窗 */}
      {isModalOpen && selectedType && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg max-h-[90vh] overflow-y-auto">
            <div className="modal-header flex items-center justify-between">
              <h2 className="text-lg font-semibold">
                {editingChannel ? '编辑' : '配置'}{channelTypeLabels[selectedType]}
              </h2>
              <button onClick={closeModal} className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg">
                <X className="w-4 h-4 text-slate-500" />
              </button>
            </div>
            <form onSubmit={handleSubmit}>
              <div className="modal-body space-y-4">
                <div>
                  <label className="input-label">渠道名称</label>
                  <input
                    type="text"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    className="input-ios"
                    placeholder={`如：我的${channelTypeLabels[selectedType]}`}
                  />
                </div>
                <div>
                  <label className="input-label">配置 (JSON)</label>
                  <textarea
                    value={formConfig}
                    onChange={(e) => setFormConfig(e.target.value)}
                    className="input-ios h-32 resize-none font-mono text-sm"
                    placeholder={channelTypes.find(c => c.type === selectedType)?.placeholder}
                  />
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    {getChannelConfigHint(selectedType)}
                  </p>
                </div>
                <div className="border-t border-slate-200 dark:border-slate-700 pt-4 space-y-4">
                  <div>
                    <p className="input-label">通知正文模板</p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      预填为系统默认正文；修改后才会保存为自定义模板，留空可恢复系统默认正文。支持英文占位符，例如 {'{{buyer_nick}}'}。
                    </p>
                  </div>
                  {notifyTypeOptions.map((definition) => {
                    const typeOn = formNotifyTypes.includes(definition.value)
                    return (
                    <div key={definition.value}>
                      <div className="flex items-center justify-between gap-3">
                        <label className="input-label mb-0">{definition.label}</label>
                        <div className="flex items-center gap-2">
                          <span className={`text-xs ${typeOn ? 'text-blue-600 dark:text-blue-400' : 'text-slate-400 dark:text-slate-500'}`}>
                            {typeOn ? '推送' : '不推送'}
                          </span>
                          <button
                            type="button"
                            onClick={() => toggleFormNotifyType(definition.value)}
                            title={notifyTypeHints[definition.value]}
                            className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                              typeOn ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-600'
                            }`}
                          >
                            <span
                              className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                                typeOn ? 'translate-x-6' : 'translate-x-1'
                              }`}
                            />
                          </button>
                        </div>
                      </div>
                      <textarea
                        value={formTemplates[definition.value]}
                        onChange={(event) => setFormTemplates((templates) => ({
                          ...templates,
                          [definition.value]: event.target.value,
                        }))}
                        className="input-ios h-32 resize-y font-mono text-sm"
                      />
                      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 break-words">
                        可用变量：{templateVariables[definition.value].map(({ name, label }) => `{{${name}}}（${label}）`).join('、')}
                      </p>
                    </div>
                    )
                  })}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium text-slate-700 dark:text-slate-200">启用此渠道</span>
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
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      保存中...
                    </>
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
        message="确定要删除这个通知渠道吗？删除后将停止推送，历史配置会保留。"
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={() => deleteConfirm.id && handleDelete(deleteConfirm.id)}
        onCancel={() => setDeleteConfirm({ open: false, id: null })}
      />
    </div>
  )
}
