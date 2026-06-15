import { useState, useEffect } from 'react'
import {
  Button,
  Card,
  Empty,
  Input,
  Modal,
  Space,
  Switch,
  Tag,
  Typography,
} from '@arco-design/web-react'
import { Bell, CheckCircle, PlayCircle, Plus, Edit2, Send, MessageCircle, Mail, Link, Smartphone, Power, Users } from 'lucide-react'
import { getNotificationChannels, updateNotificationChannel, testNotificationChannel, addNotificationChannel, deleteNotificationChannel } from '@/api/notifications'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import type { NotificationChannel } from '@/types'

const { Text } = Typography

// 所有支持的渠道类型配置
const channelTypes = [
  { type: 'dingtalk', label: '钉钉通知', desc: '钉钉机器人消息', icon: Bell, placeholder: '{"webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=..."}' },
  { type: 'feishu', label: '飞书通知', desc: '飞书机器人消息', icon: Send, placeholder: '{"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/..."}' },
  { type: 'bark', label: 'Bark通知', desc: 'iOS推送通知', icon: Smartphone, placeholder: '{"device_key": "xxx", "server_url": "https://api.day.app"}' },
  { type: 'email', label: '邮件通知', desc: 'SMTP邮件发送', icon: Mail, placeholder: '{"smtp_server": "...", "smtp_port": 587, "email_user": "...", "email_password": "...", "recipient_email": "..."}' },
  { type: 'webhook', label: 'Webhook', desc: '自定义HTTP请求', icon: Link, placeholder: '{"webhook_url": "https://..."}' },
  { type: 'wechat', label: '微信通知', desc: '企业微信机器人', icon: MessageCircle, placeholder: '{"webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."}' },
  { type: 'telegram', label: 'Telegram', desc: 'Telegram机器人', icon: Send, placeholder: '{"bot_token": "...", "chat_id": "..."}' },
] as const

type ChannelType = typeof channelTypes[number]['type']
type ChannelFilter = 'all' | 'configured' | 'unconfigured' | 'enabled' | 'disabled'

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
  const [activeFilter, setActiveFilter] = useState<ChannelFilter>('all')
  const [selectedChannelId, setSelectedChannelId] = useState<string | null>(null)

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

  const handleDeleteChannel = (channel: NotificationChannel) => {
    Modal.confirm({
      title: '删除通知配置',
      content: `确定要删除「${channel.name || channelTypeLabels[channel.type]}」吗？删除后该渠道会恢复为未配置状态。`,
      okText: '删除',
      cancelText: '取消',
      okButtonProps: { status: 'danger' },
      onOk: async () => {
        try {
          await deleteNotificationChannel(channel.id)
          addToast({ type: 'success', message: '通知配置已删除' })
          setSelectedChannelId(null)
          await loadChannels()
        } catch {
          addToast({ type: 'error', message: '删除失败' })
        }
      },
    })
  }

  const handleDeleteSelectedChannel = () => {
    const selectedChannel = channels.find(channel => channel.id === selectedChannelId)
    if (!selectedChannel) {
      addToast({ type: 'warning', message: '请先选择要删除的通知配置' })
      return
    }
    handleDeleteChannel(selectedChannel)
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

  const handleSubmit = async () => {
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

  const configuredCount = channels.length
  const enabledCount = channels.filter(channel => channel.enabled).length
  const filteredChannelTypes = channelTypes.filter((ct) => {
    const existingChannel = getChannelByType(ct.type)
    if (activeFilter === 'configured') return Boolean(existingChannel)
    if (activeFilter === 'unconfigured') return !existingChannel
    if (activeFilter === 'enabled') return Boolean(existingChannel?.enabled)
    if (activeFilter === 'disabled') return Boolean(existingChannel && !existingChannel.enabled)
    return true
  })
  const filters: Array<{ key: ChannelFilter; label: string }> = [
    { key: 'all', label: '全部' },
    { key: 'configured', label: '已配置' },
    { key: 'unconfigured', label: '未配置' },
    { key: 'enabled', label: '已启用' },
    { key: 'disabled', label: '已禁用' },
  ]

  return (
    <div className="notification-channel-page">
      <Card
        className="xianyu-arco-page-card notification-channel-shell"
        bordered={false}
      >
        <div className="accounts-page-intro">
          <h1>通知渠道管理</h1>
          <p>统一管理各类通知渠道的配置、测试与启停状态</p>
        </div>
        {/* <div className="notification-channel-hero">
          <Button
            className="notification-refresh-btn"
            onClick={loadChannels}>
            <RefreshCw className="w-4 h-4 shrink-0" />
            刷新
          </Button>
        </div> */}

        <div className="notification-channel-stats">
          <div className="notification-stat-pill">
            <Users className="w-4 h-4" />
            <span>共 {channelTypes.length} 种渠道</span>
          </div>
          <div className="notification-stat-pill">
            <CheckCircle className="w-4 h-4" />
            <span>已配置 {configuredCount}</span>
          </div>
          <div className="notification-stat-pill">
            <PlayCircle className="w-4 h-4" />
            <span>已启用 {enabledCount}</span>
          </div>
        </div>

        <div className="notification-filter-row">
          <div className="notification-filter-tabs">
            {filters.map((item) => (
              <button
                key={item.key}
                type="button"
                className={activeFilter === item.key ? 'is-active' : ''}
                onClick={() => setActiveFilter(item.key)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <Button
            className="notification-delete-config-btn"
            status="danger"
            onClick={handleDeleteSelectedChannel}
          >
            删除配置
          </Button>
        </div>

        <div className="notification-channel-grid">
          {filteredChannelTypes.map((ct) => {
            const existingChannel = getChannelByType(ct.type)
            const Icon = ct.icon
            return (
              <Card
                key={ct.type}
                hoverable
                className={[
                  'notification-channel-card',
                  existingChannel?.enabled ? 'is-enabled' : '',
                  existingChannel?.id === selectedChannelId ? 'is-selected' : '',
                ].filter(Boolean).join(' ')}
                onClick={() => setSelectedChannelId(existingChannel?.id || null)}
              >
                <div className="notification-channel-card-main">
                  <div className="notification-channel-icon">
                    <Icon className="w-7 h-7" />
                  </div>
                  <div>
                    <div className="notification-channel-title">{ct.label}</div>
                    <Text type="secondary" className="notification-channel-desc">{ct.desc}</Text>
                    <Tag className="notification-status-tag" color={existingChannel ? (existingChannel.enabled ? 'green' : 'gray') : 'gray'}>
                      {existingChannel ? (existingChannel.enabled ? '已启用' : '已禁用') : '未配置'}
                    </Tag>
                  </div>
                </div>

                <div className="notification-channel-actions">
                  {existingChannel ? (
                    <>
                      <Button
                        className="notification-action-btn"
                        type="outline"
                        onClick={() => openEditModal(existingChannel)}
                      >
                        <Edit2 />
                        <span>编辑</span>
                      </Button>
                      <Button
                        className="notification-action-btn"
                        onClick={() => handleTest(existingChannel.id)}
                      >
                        <Send />
                        <span>测试</span>
                      </Button>
                      <Button
                        className="notification-action-btn"
                        status={existingChannel.enabled ? 'danger' : 'success'}
                        type="outline"
                        onClick={() => handleToggleEnabled(existingChannel)}
                      >
                        {existingChannel.enabled ? <Power /> : <PlayCircle />}
                        <span>{existingChannel.enabled ? '禁用' : '启用'}</span>
                      </Button>
                    </>
                  ) : (
                    <Button
                      type="outline"
                      className="notification-config-btn"
                      onClick={() => openConfigModal(ct.type)}>
                      <Plus className="w-4 h-4" />
                      配置
                    </Button>
                  )}
                </div>
              </Card>
            )
          })}
        </div>
        {!filteredChannelTypes.length && (
          <Empty className="notification-empty" description="当前筛选下暂无通知渠道" />
        )}
      </Card>

      {/* 配置弹窗 */}
      <Modal
        visible={isModalOpen && Boolean(selectedType)}
        title={selectedType ? `${editingChannel ? '编辑' : '配置'}${channelTypeLabels[selectedType]}` : ''}
        okText="保存"
        cancelText="取消"
        confirmLoading={saving}
        onCancel={closeModal}
        onOk={handleSubmit}
        style={{ width: 560 }}
      >
        {selectedType && (
          <Space direction="vertical" size={16} className="w-full">
            <div>
              <Text className="notification-form-label">渠道名称</Text>
              <Input
                value={formName}
                onChange={setFormName}
                placeholder={`如：我的${channelTypeLabels[selectedType]}`}
              />
            </div>
            <div>
              <Text className="notification-form-label">配置 (JSON)</Text>
              <Input.TextArea
                value={formConfig}
                onChange={setFormConfig}
                autoSize={{ minRows: 5, maxRows: 8 }}
                placeholder={channelTypes.find(c => c.type === selectedType)?.placeholder}
              />
              <Text type="secondary" className="notification-form-hint">
                {getConfigHint(selectedType)}
              </Text>
            </div>
            <div className="notification-form-switch">
              <Text>启用此渠道</Text>
              <Switch checked={formEnabled} onChange={setFormEnabled} />
            </div>
          </Space>
        )}
      </Modal>
    </div>
  )
}
