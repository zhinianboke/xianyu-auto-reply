/** 聊天历史合并：消息 ID 优先，只有无 ID 的本地发送占位允许按内容对齐。 */
import type { ChatMessage, Conversation } from '@/api/chatNew'

export const toTimestampMs = (timestamp: number) =>
  timestamp < 1_000_000_000_000 ? timestamp * 1000 : timestamp

/** failed=false 是本地发送结果的标记；服务端历史消息没有该字段。 */
const isLocalPlaceholder = (message: ChatMessage) =>
  !message.messageId && message.isSelf && message.failed === false

const matchesPlaceholder = (message: ChatMessage, placeholder: ChatMessage) =>
  message.isSelf && message.type === placeholder.type &&
  message.text === placeholder.text &&
  message.images.length === placeholder.images.length &&
  message.images.every((url, index) => url === placeholder.images[index]) &&
  Math.abs(toTimestampMs(message.time) - toTimestampMs(placeholder.time)) < 5000

/** 合并两组消息，优先保留 latest 中同 ID 的记录，保留不同 ID 的真实消息。 */
export function mergeMessages(latest: ChatMessage[], existing: ChatMessage[]): ChatMessage[] {
  const identified = new Map<string, ChatMessage>()
  const unidentified = new Set<ChatMessage>()
  for (const message of [...latest, ...existing]) {
    if (message.messageId) {
      if (!identified.has(message.messageId)) identified.set(message.messageId, message)
    } else {
      unidentified.add(message)
    }
  }
  const merged = [...identified.values()]
  const matchedIds = new Set<string>()
  for (const message of unidentified) {
    const match = isLocalPlaceholder(message) && merged.find((candidate) =>
      candidate.messageId && !matchedIds.has(candidate.messageId) &&
      matchesPlaceholder(candidate, message),
    )
    if (match) {
      // 一条服务端消息只能替换一个本地占位，不能吞掉连续发送的相同内容。
      matchedIds.add(match.messageId)
    } else {
      merged.push(message)
    }
  }
  return merged.sort((a, b) => toTimestampMs(a.time) - toTimestampMs(b.time))
}

/** 实时推送和发送结果使用同一套去重规则，回填占位消息的真实 ID。 */
export const appendMsg = (messages: ChatMessage[], message: ChatMessage) =>
  mergeMessages([message], messages)

/** 按会话 ID 合并，并保留 HTTP 请求期间收到的更新实时摘要。 */
export function mergeConversations(latest: Conversation[], existing: Conversation[]): Conversation[] {
  const merged = new Map(existing.map((conversation) => [conversation.cid, conversation]))
  for (const conversation of latest) {
    const previous = merged.get(conversation.cid)
    merged.set(conversation.cid, previous &&
      toTimestampMs(previous.lastMessageTime) > toTimestampMs(conversation.lastMessageTime)
      ? { ...conversation, lastMessageTime: previous.lastMessageTime,
        lastMessageSummary: previous.lastMessageSummary, unreadCount: previous.unreadCount }
      : conversation)
  }
  return [...merged.values()].sort((a, b) =>
    toTimestampMs(b.lastMessageTime) - toTimestampMs(a.lastMessageTime),
  )
}
