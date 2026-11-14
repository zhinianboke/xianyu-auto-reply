import { get, post, put, del } from '@/utils/request'
import type { ApiResponse, NotificationChannel, MessageNotification, NotifyType } from '@/types'

const CHANNEL_PREFIX = '/api/v1/notification-channels'
const MESSAGE_PREFIX = '/api/v1/message-notifications'

// ========== 通知渠道 ==========

// 后端返回的通知渠道格式
interface BackendChannel {
  id: number
  name: string
  type: string
  config: string | Record<string, unknown> | null
  enabled: boolean
  created_at?: string
  updated_at?: string
}

const normalizeChannelType = (value: string): NotificationChannel['type'] => {
  const aliases: Record<string, NotificationChannel['type']> = {
    ding_talk: 'dingtalk',
    lark: 'feishu',
    wechat_work: 'wechat',
    wecom: 'wechat',
  }
  return aliases[value] || value as NotificationChannel['type']
}

// 将前端的 config 对象/字符串序列化为后端需要的字符串格式
const serializeChannelConfig = (config: NotificationChannel['config'] | unknown): string => {
  if (typeof config === 'string') {
    return config
  }
  return JSON.stringify(config ?? {})
}

// 获取通知渠道列表
const convertChannels = (result: BackendChannel[]): NotificationChannel[] => {
  return result.map((item) => {
    let parsedConfig: Record<string, unknown> | undefined
    let configError: string | undefined
    let candidate: unknown = item.config
    if (typeof item.config === 'string' && item.config.trim()) {
      try {
        candidate = JSON.parse(item.config)
      } catch {
        configError = '历史渠道配置不是有效 JSON，请编辑修复'
      }
    }
    if ((candidate != null && candidate !== '') || (typeof item.config === 'string' && item.config.trim())) {
      if (candidate !== null && typeof candidate === 'object' && !Array.isArray(candidate)) {
        parsedConfig = candidate as Record<string, unknown>
      } else {
        configError ||= '历史渠道配置必须为 JSON 对象，请编辑修复'
      }
    }

    return {
      id: String(item.id),
      name: item.name,
      type: normalizeChannelType(item.type),
      config: parsedConfig,
      config_error: configError,
      raw_config: configError ? (typeof item.config === 'string' ? item.config : JSON.stringify(item.config)) : undefined,
      enabled: item.enabled,
      created_at: item.created_at,
      updated_at: item.updated_at,
    }
  })
}

export const getNotificationChannels = async (): Promise<ApiResponse<NotificationChannel[]>> => {
  const result = await get<BackendChannel[] | ApiResponse<NotificationChannel[]>>(CHANNEL_PREFIX)
  if (!Array.isArray(result)) return result
  return { success: true, code: 200, message: '操作成功', data: convertChannels(result) }
}

export interface NotificationChannelPage {
  items: NotificationChannel[]
  total: number
  pages: number
  page: number
  page_size: number
  type_counts: Record<string, number>
}

export const getNotificationChannelPage = async (page = 1, pageSize = 20): Promise<ApiResponse<NotificationChannelPage>> => {
  const result = await get<ApiResponse<Omit<NotificationChannelPage, 'items'> & { items: BackendChannel[] }>>(
    `${CHANNEL_PREFIX}/page?page=${page}&page_size=${pageSize}`,
  )
  if (!result.success || !result.data) return result as unknown as ApiResponse<NotificationChannelPage>
  const typeCounts: Record<string, number> = {}
  for (const [type, count] of Object.entries(result.data.type_counts)) {
    const canonical = normalizeChannelType(type)
    typeCounts[canonical] = (typeCounts[canonical] || 0) + count
  }
  return { ...result, data: { ...result.data, items: convertChannels(result.data.items), type_counts: typeCounts } }
}

// 添加通知渠道
export const addNotificationChannel = (data: Partial<NotificationChannel>): Promise<ApiResponse> => {
  const payload = {
    ...data,
    // 后端期望 config 为字符串
    config: serializeChannelConfig(data.config),
  }
  return post(CHANNEL_PREFIX, payload)
}

// 更新通知渠道
export const updateNotificationChannel = (channelId: string, data: Partial<NotificationChannel>): Promise<ApiResponse> => {
  const payload: Record<string, unknown> = {
    ...data,
  }

  if ('config' in data) {
    payload.config = serializeChannelConfig(data.config)
  }

  return put(`${CHANNEL_PREFIX}/${channelId}`, payload)
}

// 删除通知渠道
export const deleteNotificationChannel = (channelId: string): Promise<ApiResponse> => {
  return del(`${CHANNEL_PREFIX}/${channelId}`)
}

// 测试通知渠道
export const testNotificationChannel = (channelId: string): Promise<ApiResponse> => {
  return post(`${CHANNEL_PREFIX}/${channelId}/test`)
}

// ========== 消息通知 ==========

// 后端返回格式: { cookie_id: [ { id, channel_id, enabled, channel_name, channel_type, channel_config } ] }
interface BackendNotification {
  id: number
  channel_id: number
  enabled: boolean
  channel_name?: string
  channel_type?: string
  channel_config?: string
  subscription_enabled?: boolean
  channel_enabled?: boolean
  notify_types?: string[]
}

export interface NotificationTypeOption {
  value: NotifyType
  label: string
}

export interface MessageNotificationPage {
  items: MessageNotification[]
  total: number
  page: number
  page_size: number
  pages: number
}

interface BackendNotificationPage {
  items: Array<BackendNotification & { cookie_id: string }>
  total: number
  page: number
  page_size: number
  pages: number
}

// 获取所有消息通知配置
export const getMessageNotifications = async (): Promise<ApiResponse<MessageNotification[]>> => {
  const result = await get<Record<string, BackendNotification[]> | ApiResponse<MessageNotification[]>>(MESSAGE_PREFIX)
  if ('success' in result && typeof result.success === 'boolean') return result as ApiResponse<MessageNotification[]>
  // 将嵌套对象转换为数组
  const notifications: MessageNotification[] = []
  for (const [cookieId, channelList] of Object.entries(result || {})) {
    if (Array.isArray(channelList)) {
      for (const item of channelList) {
        notifications.push({
          id: item.id,
          cookie_id: cookieId,
          channel_id: item.channel_id,
          channel_name: item.channel_name,
          enabled: item.enabled,
          subscription_enabled: item.subscription_enabled ?? item.enabled,
          channel_enabled: item.channel_enabled ?? true,
          notify_types: (item.notify_types as MessageNotification['notify_types']) || undefined,
        })
      }
    }
  }
  return { success: true, code: 200, message: '操作成功', data: notifications }
}

// 获取通知事件类型数据字典，中文名称禁止在页面硬编码
export const getMessageNotificationOptions = (): Promise<ApiResponse<{ notify_types: NotificationTypeOption[] }>> => {
  return get(`${MESSAGE_PREFIX}/options`)
}

// 分页获取消息通知配置；保留原列表接口供旧客户端兼容使用
export const getMessageNotificationPage = async (
  page = 1,
  pageSize = 20,
): Promise<ApiResponse<MessageNotificationPage>> => {
  const result = await get<ApiResponse<BackendNotificationPage>>(
    `${MESSAGE_PREFIX}/page?page=${page}&page_size=${pageSize}`,
  )
  if (!result.success || !result.data) return result as ApiResponse<MessageNotificationPage>
  return {
    ...result,
    data: {
      ...result.data,
      items: result.data.items.map((item) => ({
        id: item.id,
        cookie_id: item.cookie_id,
        channel_id: item.channel_id,
        channel_name: item.channel_name,
        enabled: item.enabled,
        subscription_enabled: item.subscription_enabled ?? item.enabled,
        channel_enabled: item.channel_enabled ?? true,
        notify_types: item.notify_types as MessageNotification['notify_types'],
      })),
    },
  }
}

// 设置消息通知 - 后端接口需要 cookie_id 作为路径参数
export const setMessageNotification = (
  cookieId: string,
  channelId: number,
  enabled: boolean,
  notifyTypes?: string[],
  notificationId?: number,
): Promise<ApiResponse> => {
  const payload: Record<string, unknown> = { channel_id: channelId, enabled }
  // 缺省时新建默认全类型、更新保留原值；显式空数组由后端拒绝。
  if (notifyTypes !== undefined) {
    payload.notify_types = notifyTypes
  }
  if (notificationId !== undefined) payload.notification_id = notificationId
  return post(`${MESSAGE_PREFIX}/account/${encodeURIComponent(cookieId)}`, payload)
}

export const updateMessageNotificationEnabled = (id: number, enabled: boolean): Promise<ApiResponse> => {
  return put(`${MESSAGE_PREFIX}/${id}`, { enabled })
}

// 删除消息通知
export const deleteMessageNotification = (notificationId: string): Promise<ApiResponse> => {
  return del(`${MESSAGE_PREFIX}/${notificationId}`)
}

// 删除账号的所有消息通知
export const deleteAccountNotifications = (cookieId: string): Promise<ApiResponse> => {
  return del(`${MESSAGE_PREFIX}/account/${encodeURIComponent(cookieId)}`)
}
