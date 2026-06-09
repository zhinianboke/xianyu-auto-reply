/**
 * 在线聊天(新) API接口
 *
 * 提供账号连接管理、会话列表、聊天记录等接口，
 * 以及 WebSocket 实时消息推送连接
 */
import { get, post } from '@/utils/request'

const PREFIX = '/api/v1/chat-new'


// ==================== 类型定义 ====================

/** 可用账号 */
export interface ChatAccount {
  account_id: string
  remark: string
  connected: boolean
  status: string
  /** 所属用户（管理员查看时返回） */
  owner?: string
}

/** 会话 */
export interface Conversation {
  cid: string
  rawCid: string
  otherUserId: string
  otherUserName: string
  otherUserAvatar: string
  itemTitle: string
  lastMessageSummary: string
  lastMessageTime: number
  unreadCount: number
}

/** 聊天消息 */
export interface ChatMessage {
  senderId: string
  senderName: string
  isSelf: boolean
  type: 'text' | 'image' | 'system' | 'card'
  text: string
  images: string[]
  time: number
  /** 发送是否失败（仅本地发送的消息可能为 true） */
  failed?: boolean
  /** 发送失败原因（如被安全拦截的明文文案），用于点击感叹号查看 */
  failReason?: string
}

// ==================== 接口方法 ====================

/** 账号列表分页响应 */
export interface ChatAccountsPage {
  data: ChatAccount[]
  total: number
  hasMore: boolean
}

/** 获取账号列表（分页） */
export const getChatAccounts = async (page = 1, pageSize = 20): Promise<ChatAccountsPage> => {
  const res = await get<{ success: boolean; data: ChatAccount[]; total: number; hasMore: boolean }>(
    `${PREFIX}/accounts?page=${page}&page_size=${pageSize}`,
  )
  return { data: res.data || [], total: res.total || 0, hasMore: res.hasMore ?? false }
}

/** 连接指定账号的IM */
export const connectAccount = (accountId: string) => {
  return post<{ success: boolean; message: string }>(`${PREFIX}/connect/${accountId}`)
}

/** 断开指定账号的IM */
export const disconnectAccount = (accountId: string) => {
  return post<{ success: boolean; message: string }>(`${PREFIX}/disconnect/${accountId}`)
}

/** 获取会话列表 */
export const getConversations = async (
  accountId: string,
  cursor?: number,
  limit: number = 20,
): Promise<{ conversations: Conversation[]; hasMore: boolean; nextCursor: number | null }> => {
  const params = new URLSearchParams()
  if (cursor !== undefined && cursor !== null) params.append('cursor', String(cursor))
  params.append('limit', String(limit))

  const res = await get<{
    success: boolean
    message?: string
    data: { conversations: Conversation[]; hasMore: boolean; nextCursor: number | null }
  }>(`${PREFIX}/conversations/${accountId}?${params.toString()}`)
  if (!res.success) throw new Error(res.message || '获取会话列表失败')
  const data = res.data || { conversations: [], hasMore: false, nextCursor: null }
  // 后端 hasMore 可能返回数字 0/1，强制转为布尔值避免 React 渲染出 "0"
  data.hasMore = !!data.hasMore
  return data
}

/** 发送文本消息 */
export const sendTextMessage = async (
  accountId: string,
  cid: string,
  toUserId: string,
  text: string,
): Promise<{ success: boolean; message: string }> => {
  return post<{ success: boolean; message: string }>(`${PREFIX}/send-message/${accountId}`, {
    cid,
    toUserId,
    text,
  })
}

/** 用户信息查询结果 */
export interface UserInfoResult {
  avatar: string
  nick: string
}

/** 批量查询对方用户信息（头像+昵称，需要传会话ID用于调API） */
export const queryUserInfos = async (
  accountId: string,
  queries: { userId: string; cid: string }[],
): Promise<Record<string, UserInfoResult>> => {
  const res = await post<{ success: boolean; data: Record<string, UserInfoResult> }>(
    `${PREFIX}/avatars/${accountId}`,
    { queries },
  )
  return res.data || {}
}

/** 获取聊天记录 */
export const getMessages = async (
  accountId: string,
  cid: string,
  cursor?: number,
  limit: number = 20,
): Promise<{ messages: ChatMessage[]; hasMore: boolean; nextCursor: number | null }> => {
  const params = new URLSearchParams()
  if (cursor !== undefined && cursor !== null) params.append('cursor', String(cursor))
  params.append('limit', String(limit))

  const res = await get<{
    success: boolean
    message?: string
    data: { messages: ChatMessage[]; hasMore: boolean; nextCursor: number | null }
  }>(`${PREFIX}/messages/${accountId}/${cid}?${params.toString()}`)
  if (!res.success) throw new Error(res.message || '获取聊天记录失败')
  return res.data || { messages: [], hasMore: false, nextCursor: null }
}

// ==================== WebSocket 实时推送 ====================

/** WebSocket 推送消息（新消息事件） */
export interface WsPushMessage {
  event: 'new_message' | 'connected' | 'pong'
  cid?: string
  account_id?: string
  message?: ChatMessage
}

/**
 * 获取在线聊天(新) WebSocket 基础地址
 *
 * 使用当前页面同源地址，通过代理转发到backend-web：
 * - 开发环境：Vite proxy (ws:true) 代理到 localhost:8089
 * - 生产环境：Nginx 反代到 backend-web:8089
 */
function getChatNewWsBaseUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return `${protocol}//${host}`
}

/**
 * 创建在线聊天(新) WebSocket 连接
 *
 * 连接后会实时接收 IM 推送的新消息
 */
export function createChatNewWebSocket(accountId: string): WebSocket {
  const wsBase = getChatNewWsBaseUrl()
  return new WebSocket(`${wsBase}/api/v1/chat-new/ws/${accountId}`)
}
