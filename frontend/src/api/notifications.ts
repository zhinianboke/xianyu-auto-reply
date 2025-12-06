import { del, get, post, put } from '@/utils/request'
import type { ApiResponse, MessageNotification, NotificationChannel } from '@/types'

// ========== 通知渠道 ==========

// 后端返回的通知渠道格式
interface BackendChannel {
  id: number
  name: string
  type: string
  config: string
  enabled: boolean
  created_at?: string
  updated_at?: string
}

// 将前端的 config 对象/字符串序列化为后端需要的字符串格式
const serializeChannelConfig = (config: NotificationChannel['config'] | unknown): string => {
  if (typeof config === 'string') {
    return config
  }
  if (config && typeof config === 'object') {
    try {
      return JSON.stringify(config)
    } catch {
      return '{}'
    }
  }
  return '{}'
}

// 获取通知渠道列表
export const getNotificationChannels = async (): Promise<{ success: boolean; data?: NotificationChannel[] }> => {
  const result = await get<BackendChannel[]>('/notification-channels')
  // 后端直接返回数组，需要转换格式
  const channels: NotificationChannel[] = (result || []).map((item) => {
    let parsedConfig: Record<string, unknown> | undefined

    if (item.config) {
      if (typeof item.config === 'string') {
        try {
          parsedConfig = JSON.parse(item.config)
        } catch {
          // 兼容旧数据或非法 JSON，避免单条配置导致整个列表加载失败
          parsedConfig = undefined
        }
      } else if (typeof item.config === 'object') {
        parsedConfig = item.config as unknown as Record<string, unknown>
      }
    }

    return {
      id: String(item.id),
      name: item.name,
      type: item.type as NotificationChannel['type'],
      config: parsedConfig,
      enabled: item.enabled,
      created_at: item.created_at,
      updated_at: item.updated_at,
    }
  })
  return { success: true, data: channels }
}

// 添加通知渠道
export const addNotificationChannel = (data: Partial<NotificationChannel>): Promise<ApiResponse> => {
  const payload = {
    ...data,
    // 后端期望 config 为字符串
    config: serializeChannelConfig(data.config),
  }
  return post('/notification-channels', payload)
}

// 更新通知渠道
export const updateNotificationChannel = (channelId: string, data: Partial<NotificationChannel>): Promise<ApiResponse> => {
  const payload: Record<string, unknown> = {
    ...data,
  }

  if ('config' in data) {
    payload.config = serializeChannelConfig(data.config)
  }

  return put(`/notification-channels/${channelId}`, payload)
}

// 删除通知渠道
export const deleteNotificationChannel = (channelId: string): Promise<ApiResponse> => {
  return del(`/notification-channels/${channelId}`)
}

// 测试通知渠道 - 后端暂未实现此接口
export const testNotificationChannel = async (_channelId: string): Promise<ApiResponse> => {
  // TODO: 后端暂未实现 POST /notification-channels/{id}/test 接口
  return { success: false, message: '通知渠道测试功能暂未实现' }
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
}

// 获取所有消息通知配置
export const getMessageNotifications = async (): Promise<{ success: boolean; data?: MessageNotification[] }> => {
  const result = await get<Record<string, BackendNotification[]>>('/message-notifications')
  // 将嵌套对象转换为数组
  const notifications: MessageNotification[] = []
  for (const [cookieId, channelList] of Object.entries(result || {})) {
    if (Array.isArray(channelList)) {
      for (const item of channelList) {
        notifications.push({
          cookie_id: cookieId,
          channel_id: item.channel_id,
          channel_name: item.channel_name,
          enabled: item.enabled,
        })
      }
    }
  }
  return { success: true, data: notifications }
}

// 设置消息通知 - 后端接口需要 cookie_id 作为路径参数
export const setMessageNotification = (cookieId: string, channelId: number, enabled: boolean): Promise<ApiResponse> => {
  return post(`/message-notifications/${cookieId}`, { channel_id: channelId, enabled })
}

// 删除消息通知
export const deleteMessageNotification = (notificationId: string): Promise<ApiResponse> => {
  return del(`/message-notifications/${notificationId}`)
}

// 删除账号的所有消息通知
export const deleteAccountNotifications = (cookieId: string): Promise<ApiResponse> => {
  return del(`/message-notifications/account/${cookieId}`)
}
