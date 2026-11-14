/**
 * 通知渠道页面公共配置。
 *
 * 功能：
 * 1. 集中维护渠道类型、默认配置和通知模板变量
 * 2. 提供模板校验与渠道配置拆分方法
 * 3. 页面中文通知类型名称由后端数据字典提供，本文件不维护枚举中文映射
 */
import { Bell, Link, Mail, MessageCircle, Send, Smartphone } from 'lucide-react'
import type { NotifyType } from '@/types'

export const channelTypes = [
  {
    type: 'dingtalk',
    label: '钉钉通知',
    desc: '钉钉机器人消息',
    icon: Bell,
    placeholder: '{"webhook_url": "https://oapi.dingtalk.com/robot/send?access_token=..."}',
    defaultConfig: {
      webhook_url: 'https://oapi.dingtalk.com/robot/send?access_token=你的access_token',
      secret: '',
    },
  },
  {
    type: 'feishu',
    label: '飞书通知',
    desc: '飞书机器人消息',
    icon: Send,
    placeholder: '{"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/..."}',
    defaultConfig: {
      webhook_url: 'https://open.feishu.cn/open-apis/bot/v2/hook/你的hook_id',
    },
  },
  {
    type: 'bark',
    label: 'Bark通知',
    desc: 'iOS推送通知',
    icon: Smartphone,
    placeholder: '{"device_key": "xxx", "server_url": "https://api.day.app"}',
    defaultConfig: {
      device_key: '你的设备密钥',
      server_url: 'https://api.day.app',
    },
  },
  {
    type: 'email',
    label: '邮件通知',
    desc: 'SMTP邮件发送',
    icon: Mail,
    placeholder: '{"smtp_server": "...", "smtp_port": 587, "email_user": "...", "email_password": "...", "recipient_email": "..."}',
    defaultConfig: {
      smtp_server: 'smtp.qq.com',
      smtp_port: 587,
      email_user: '你的邮箱@qq.com',
      email_password: '你的授权码',
      recipient_email: '接收邮箱@example.com',
    },
  },
  {
    type: 'webhook',
    label: 'Webhook',
    desc: '自定义HTTP请求',
    icon: Link,
    placeholder: '{"webhook_url": "https://..."}',
    defaultConfig: {
      webhook_url: 'https://你的webhook地址',
      method: 'POST',
      headers: {},
    },
  },
  {
    type: 'wechat',
    label: '微信通知',
    desc: '企业微信机器人',
    icon: MessageCircle,
    placeholder: '{"webhook_url": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=..."}',
    defaultConfig: {
      webhook_url: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=你的key',
    },
  },
  {
    type: 'telegram',
    label: 'Telegram',
    desc: 'Telegram机器人',
    icon: Send,
    placeholder: '{"bot_token": "...", "chat_id": "..."}',
    defaultConfig: {
      bot_token: '你的Bot_Token',
      chat_id: '你的Chat_ID',
    },
  },
  {
    type: 'pushplus',
    label: 'PushPlus',
    desc: '微信公众号推送',
    icon: MessageCircle,
    placeholder: '{"token": "...", "topic": "", "template": "txt"}',
    defaultConfig: {
      token: '你的token',
      topic: '',
      template: 'txt',
    },
  },
] as const

export type ChannelType = typeof channelTypes[number]['type']

export const templateConfigKeys: Record<NotifyType, string> = {
  chat: 'chat_template',
  delivery: 'delivery_template',
  account: 'account_template',
}

export const templateVariables: Record<NotifyType, Array<{ name: string; label: string }>> = {
  chat: [
    { name: 'account', label: '闲鱼账号' },
    { name: 'account_id', label: '账号 ID' },
    { name: 'account_remark', label: '账号备注' },
    { name: 'buyer_nick', label: '买家昵称' },
    { name: 'buyer_id', label: '买家 ID' },
    { name: 'message', label: '消息内容' },
    { name: 'item_id', label: '商品 ID' },
    { name: 'chat_id', label: '聊天 ID' },
    { name: 'time', label: '通知时间' },
  ],
  delivery: [
    { name: 'account', label: '闲鱼账号' },
    { name: 'account_id', label: '账号 ID' },
    { name: 'account_remark', label: '账号备注' },
    { name: 'buyer_nick', label: '买家昵称' },
    { name: 'buyer_id', label: '买家 ID' },
    { name: 'message', label: '消息内容' },
    { name: 'item_id', label: '商品 ID' },
    { name: 'chat_id', label: '聊天 ID' },
    { name: 'time', label: '通知时间' },
    { name: 'order_id', label: '订单 ID' },
    { name: 'amount', label: '订单金额' },
    { name: 'quantity', label: '购买数量' },
    { name: 'result', label: '发货结果' },
  ],
  account: [
    { name: 'account', label: '闲鱼账号' },
    { name: 'account_id', label: '账号 ID' },
    { name: 'account_remark', label: '账号备注' },
    { name: 'title', label: '通知标题' },
    { name: 'notification_type', label: '通知类型' },
    { name: 'detail', label: '详细说明' },
    { name: 'chat_id', label: '聊天 ID' },
    { name: 'verification_url', label: '验证链接' },
    { name: 'verification_info', label: '验证信息' },
    { name: 'time', label: '通知时间' },
  ],
}

export const defaultTemplates: Record<NotifyType, string> = {
  chat: `【闲鱼消息】
闲鱼账号: {{account}}
发送者: {{buyer_nick}}
消息: {{message}}
商品ID: {{item_id}}
时间: {{time}}`,
  delivery: `🚨 自动发货通知

闲鱼账号: {{account}}
买家: {{buyer_nick}} (ID: {{buyer_id}})
订单金额: {{amount}}
购买数量: {{quantity}}
商品ID: {{item_id}}
聊天ID: {{chat_id}}
结果: {{result}}
时间: {{time}}

请及时处理！`,
  account: `{{title}}

闲鱼账号: {{account}}
时间: {{time}}
详情: {{detail}}

请检查账号状态。`,
}

export const notifyTypeHints: Record<NotifyType, string> = {
  chat: '买家每发一条消息都推送，使用频率较高',
  delivery: '每次自动发货结果推送一次',
  account: '账号掉线、Cookie 到期或 Token 刷新失败时推送',
}

export const channelTypeLabels: Record<string, string> = Object.fromEntries(
  channelTypes.map((channel) => [channel.type, channel.label]),
)

export function getChannelConfigHint(type: ChannelType): string {
  const hints: Record<ChannelType, string> = {
    bark: 'Bark是iOS推送通知服务，需要填写设备密钥',
    dingtalk: '请设置钉钉机器人Webhook URL，可选填加签密钥',
    feishu: '请设置飞书机器人Webhook URL',
    email: '需要填写SMTP服务器、端口、发送邮箱、密码和接收邮箱',
    wechat: '请设置企业微信机器人Webhook URL',
    telegram: '需要填写Bot Token和Chat ID',
    pushplus: '需要填写PushPlus的token，topic为群组编码（可选）',
    webhook: '填写自定义Webhook URL',
  }
  return hints[type]
}

export function parseNotifyTypes(raw: unknown, allowedTypes: NotifyType[]): NotifyType[] {
  if (raw === undefined || raw === null) return [...allowedTypes]
  if (!Array.isArray(raw) && typeof raw !== 'string') return [...allowedTypes]
  const items = Array.isArray(raw) ? raw : raw.split(',')
  if (items.some((value) => typeof value !== 'string')) return [...allowedTypes]
  const selected = new Set(items.map((value) => String(value).trim()).filter(Boolean))
  if ([...selected].some((value) => !allowedTypes.includes(value as NotifyType))) return [...allowedTypes]
  const picked = allowedTypes.filter((type) => selected.has(type))
  // 历史异常值按全类型兼容，避免升级后已有渠道停止通知。
  return picked.length > 0 ? picked : [...allowedTypes]
}

export function getTemplateValidationError(template: string, templateType: NotifyType): string | null {
  if (!template.trim()) return null
  const placeholderPattern = /{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}/g
  const placeholders = [...template.matchAll(placeholderPattern)]
  const remaining = template.replace(placeholderPattern, '')
  if (remaining.includes('{{') || remaining.includes('}}')) {
    return '占位符必须使用 {{variable}} 格式'
  }
  const knownVariables = new Set(templateVariables[templateType].map((variable) => variable.name))
  const unknownVariables = [...new Set(
    placeholders.map((match) => match[1]).filter((name) => !knownVariables.has(name)),
  )]
  return unknownVariables.length > 0 ? `不支持的占位符: ${unknownVariables.join(', ')}` : null
}

export function splitTemplateConfig(config?: Record<string, unknown>) {
  const templates: Record<NotifyType, string> = { ...defaultTemplates }
  const channelConfig: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(config || {})) {
    if (key === 'notify_types') continue
    const templateType = (Object.keys(templateConfigKeys) as NotifyType[])
      .find((type) => templateConfigKeys[type] === key)
    if (templateType) {
      if (typeof value === 'string' && value.trim()) templates[templateType] = value
    } else {
      channelConfig[key] = value
    }
  }
  return { templates, channelConfig }
}
