import { useState, useEffect } from 'react'
import type { FormEvent } from 'react'
import { motion } from 'framer-motion'
import { Bell, RefreshCw, Plus, Edit2, Trash2, Send, Settings, MessageCircle, Mail, Link, Smartphone, X, Loader2 } from 'lucide-react'
import { getNotificationChannels, deleteNotificationChannel, updateNotificationChannel, testNotificationChannel, addNotificationChannel } from '@/api/notifications'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import type { NotificationChannel } from '@/types'

// 所有支持的渠道类型配置
const channelTypes = [
  { type: 'qq', label: 'QQ通知', desc: 'QQ机器人消息', icon: MessageCircle, placeholder: '{"qq_number": "123456789"}' },
  { type: 'dingtalk', label: '钉钉通知', desc: '钉钉机器人消息', icon: Bell, placeholder: '{"webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=..."}' },
  { type: 'feishu', label: '飞书通知', desc: '飞书机器人消息', icon: Send, placeholder: '{"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/..."}' },
  { type: 'bark', label: 'Bark通知', desc: 'iOS推送通知', icon: Smartphone, placeholder: '{"device_key": "xxx", "server_url": "https://api.day.app"}' },
  { type: 'email', label: '邮件通知', desc: 'SMTP邮件发送', icon: Mail, placeholder: '{"smtp_server": "...", "smtp_port": 587, "email_user": "...", "email_password": "...", "recipient_email": "..."}' },
  { type: 'webhook', label: 'Webhook', desc: '自定义HTTP请求', icon: Link, placeholder: '{"webhook_url": "https://..."}' },
  { type: 'wechat', label: '微信通知', desc: '企业微信机器人', icon: MessageCircle, placeholder: '{"webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."}' },
  { type: 'telegram', label: 'Telegram', desc: 'Telegram机器人', icon: Send, placeholder: '{"bot_token": "...", "chat_id": "..."}' },
] as const

type ChannelType = typeof channelTypes[number]['type']

const channelTypeLabels: Record<string, string> = Object.fromEntries(
  channelTypes.map(c => [c.type, c.label])
)

export function NotificationChannels() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [channels, setChannels] = useState<NotificationChannel[]>([])
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingChannel, setEditingChannel] = useState<NotificationChannel | null>(null)
  const [selectedType, setSelectedType] = useState<ChannelType | null>(null)
  const [formName, setFormName] = useState('')
  const [formConfig, setFormConfig] = useState('')
  const [formEnabled, setFormEnabled] = useState(true)
  const [saving, setSaving] = useState(false)

  const loadChannels = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) {
      setLoading(false)
      return
    }
    try {
      setLoading(true)
      const result = await getNotificationChannels()
      if (result.success) {
        setChannels(result.data || [])
      }
    } catch (err) {
      if (err && typeof err === 'object' && 'response' in err) {
        const axiosErr = err as { response?: { status?: number } }
        if (axiosErr.response?.status === 401) {
          return
        }
      }
      addToast({ type: 'error', message: '加载通知渠道失败' })
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

  // 根据类型查找已配置的渠道
  const getChannelByType = (type: string) => {
    return channels.find(c => c.type === type)
  }

  const handleToggleEnabled = async (channel: NotificationChannel) => {
    try {
      await updateNotificationChannel(channel.id, {
        name: channel.name,
        config: channel.config,
        enabled: !channel.enabled,
      })
      addToast({ type: 'success', message: channel.enabled ? '渠道已禁用' : '渠道已启用' })
      loadChannels()
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  const handleTest = async (id: string) => {
    try {
      const result = await testNotificationChannel(id)
      if (result.success) {
        addToast({ type: 'success', message: '测试消息发送成功' })
      } else {
        addToast({ type: 'error', message: result.message || '测试失败' })
      }
    } catch {
      addToast({ type: 'error', message: '测试失败' })
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('确定要删除这个通知渠道吗？')) return
    try {
      await deleteNotificationChannel(id)
      addToast({ type: 'success', message: '删除成功' })
      loadChannels()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    }
  }

  // 打开配置弹窗（新建）
  const openConfigModal = (type: ChannelType) => {
    const typeConfig = channelTypes.find(c => c.type === type)
    setSelectedType(type)
    setEditingChannel(null)
    setFormName(typeConfig?.label || '')
    setFormConfig('')
    setFormEnabled(true)
    setIsModalOpen(true)
  }

  // 打开编辑弹窗
  const openEditModal = (channel: NotificationChannel) => {
    setSelectedType(channel.type as ChannelType)
    setEditingChannel(channel)
    setFormName(channel.name)
    setFormConfig(JSON.stringify(channel.config || {}, null, 2))
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

    setSaving(true)
    try {
      let config = {}
      if (formConfig.trim()) {
        try {
          config = JSON.parse(formConfig)
        } catch {
          addToast({ type: 'error', message: '配置JSON格式错误' })
          setSaving(false)
          return
        }
      }

      const data = {
        name: formName.trim(),
        type: selectedType,
        config,
        enabled: formEnabled,
      }

      if (editingChannel) {
        await updateNotificationChannel(editingChannel.id, data)
        addToast({ type: 'success', message: '渠道已更新' })
      } else {
        await addNotificationChannel(data)
        addToast({ type: 'success', message: '渠道已添加' })
      }

      closeModal()
      loadChannels()
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setSaving(false)
    }
  }

  // 获取当前类型的配置提示
  const getConfigHint = (type: ChannelType) => {
    switch (type) {
      case 'qq': return '需要添加QQ号 3668943488 为好友才能正常接收消息通知'
      case 'bark': return 'Bark是iOS推送通知服务，需要填写设备密钥'
      case 'dingtalk': return '请设置钉钉机器人Webhook URL，可选填加签密钥'
      case 'feishu': return '请设置飞书机器人Webhook URL'
      case 'email': return '需要填写SMTP服务器、端口、发送邮箱、密码和接收邮箱'
      case 'wechat': return '请设置企业微信机器人Webhook URL'
      case 'telegram': return '需要填写Bot Token和Chat ID'
      case 'webhook': return '填写自定义Webhook URL'
      default: return ''
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
          <p className="page-description">管理消息通知渠道，支持QQ通知等多种方式</p>
        </div>
        <button onClick={loadChannels} className="btn-ios-secondary">
          <RefreshCw className="w-4 h-4" />
          刷新
        </button>
      </div>

      {/* 渠道类型网格 */}
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">
            <Settings className="w-4 h-4" />
            选择通知方式
          </h2>
        </div>
        <div className="vben-card-body">
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">点击下方按钮选择您要配置的通知渠道类型</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {channelTypes.map((ct, index) => {
              const existingChannel = getChannelByType(ct.type)
              const Icon = ct.icon
              return (
                <motion.div
                  key={ct.type}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.03 }}
                  className={`relative p-4 rounded-xl border-2 transition-all ${
                    existingChannel
                      ? existingChannel.enabled
                        ? 'border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-900/20'
                        : 'border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/50'
                      : 'border-slate-200 dark:border-slate-700 hover:border-blue-300 dark:hover:border-blue-600'
                  }`}
                >
                  <div className="text-center">
                    <div className={`w-10 h-10 mx-auto mb-2 rounded-lg flex items-center justify-center ${
                      existingChannel?.enabled ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400' : 'bg-slate-100 dark:bg-slate-700 text-slate-500'
                    }`}>
                      <Icon className="w-5 h-5" />
                    </div>
                    <h3 className="font-medium text-slate-900 dark:text-slate-100 text-sm">{ct.label}</h3>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{ct.desc}</p>
                    
                    {existingChannel ? (
                      <div className="mt-3 flex items-center justify-center gap-1">
                        <button
                          onClick={() => openEditModal(existingChannel)}
                          className="text-xs px-2 py-1 rounded bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-800"
                        >
                          编辑
                        </button>
                        <button
                          onClick={() => handleToggleEnabled(existingChannel)}
                          className={`text-xs px-2 py-1 rounded ${
                            existingChannel.enabled
                              ? 'bg-green-100 dark:bg-green-900/50 text-green-600 dark:text-green-400'
                              : 'bg-slate-100 dark:bg-slate-700 text-slate-500'
                          }`}
                        >
                          {existingChannel.enabled ? '已启用' : '已禁用'}
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => openConfigModal(ct.type)}
                        className="mt-3 text-xs px-3 py-1 rounded border border-blue-300 dark:border-blue-600 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30"
                      >
                        <Plus className="w-3 h-3 inline mr-1" />
                        配置
                      </button>
                    )}
                  </div>
                </motion.div>
              )
            })}
          </div>
        </div>
      </div>

      {/* 已配置的渠道列表 */}
      {channels.length > 0 && (
        <div className="vben-card">
          <div className="vben-card-header">
            <h2 className="vben-card-title">
              <Bell className="w-4 h-4" />
              已配置渠道
            </h2>
          </div>
          <div className="vben-card-body">
            <div className="divide-y divide-slate-100 dark:divide-slate-700">
              {channels.map(channel => (
                <div key={channel.id} className="flex items-center justify-between py-3">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                      channel.enabled ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600' : 'bg-slate-100 dark:bg-slate-700 text-slate-500'
                    }`}>
                      <Bell className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="font-medium text-slate-900 dark:text-slate-100">{channel.name}</p>
                      <p className="text-xs text-slate-500">{channelTypeLabels[channel.type] || channel.type}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`text-xs px-2 py-0.5 rounded ${
                      channel.enabled ? 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-400' : 'bg-slate-100 text-slate-500 dark:bg-slate-700'
                    }`}>
                      {channel.enabled ? '启用' : '禁用'}
                    </span>
                    <button
                      onClick={() => handleTest(channel.id)}
                      className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500"
                      title="测试"
                    >
                      <Send className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => openEditModal(channel)}
                      className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500"
                      title="编辑"
                    >
                      <Edit2 className="w-4 h-4" />
                    </button>
                    <button
                      onClick={() => handleDelete(channel.id)}
                      className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/30 text-red-500"
                      title="删除"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 配置弹窗 */}
      {isModalOpen && selectedType && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg">
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
                    {getConfigHint(selectedType)}
                  </p>
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
    </div>
  )
}
