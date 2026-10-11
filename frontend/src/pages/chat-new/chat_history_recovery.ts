/** 聊天断线补偿：冻结旧范围，分页填补缺口，未完成时保存继续拉取的位置。 */
import type { ChatMessage, Conversation } from '@/api/chatNew'
import { mergeConversations, mergeMessages } from './chat_history_merge'

export interface MessageCache {
  msgs: ChatMessage[]
  hasMore: boolean
  cursor: number | null
}

export interface ConversationCache {
  convs: Conversation[]
  hasMore: boolean
  cursor: number | null
}

export interface RecoveryBoundary<T> {
  cache: T
  nextCursor: number | null
}

/** 边界与可变缓存分开保存，实时推送、重复断线均不能覆盖尚未补齐的旧边界。 */
export class ChatHistoryRecovery {
  readonly messages = new Map<string, Map<string, RecoveryBoundary<MessageCache>>>()
  readonly conversations = new Map<string, RecoveryBoundary<ConversationCache>>()
  private readonly generations = new Map<string, number>()

  generation(accountId: string): number { return this.generations.get(accountId) ?? 0 }

  message(accountId: string, cid: string) { return this.messages.get(accountId)?.get(cid) }

  ensureMessage(accountId: string, cid: string, cache: MessageCache) {
    let account = this.messages.get(accountId)
    if (!account) { account = new Map(); this.messages.set(accountId, account) }
    if (!account.has(cid)) account.set(cid, { cache: { ...cache, msgs: [...cache.msgs] }, nextCursor: null })
    return account.get(cid)!
  }

  ensureConversations(accountId: string, cache: ConversationCache) {
    if (!this.conversations.has(accountId)) {
      this.conversations.set(accountId, { cache: { ...cache, convs: [...cache.convs] }, nextCursor: null })
    }
    return this.conversations.get(accountId)!
  }

  /** 在任何异步刷新和 HTTP 节流前调用，保存所有已访问会话的消息边界。 */
  prepare(accountId: string, conversations: ConversationCache | undefined,
    messages: Record<string, MessageCache>, disconnected = false) {
    if (disconnected) {
      this.generations.set(accountId, this.generation(accountId) + 1)
      // 再次断线需重新从最新页拉取，但仍以第一次未补齐的边界为终点。
      const pending = this.conversations.get(accountId)
      if (pending) pending.nextCursor = null
      this.messages.get(accountId)?.forEach((boundary) => { boundary.nextCursor = null })
    }
    if (conversations) this.ensureConversations(accountId, conversations)
    for (const [cid, cache] of Object.entries(messages)) this.ensureMessage(accountId, cid, cache)
  }
}

interface Page<T> { items: T[]; hasMore: boolean; nextCursor: number | null }
interface Recovered<T> { items: T[]; hasMore: boolean; cursor: number | null; complete: boolean }
const MAX_RECOVERY_PAGES = 20

/** 校验可继续翻页的位置，异常由调用方直接展示，边界保持待补偿。 */
function checkCursor<T>(page: Page<T>, cursor: number | null) {
  if (page.hasMore && (page.nextCursor === null || (cursor !== null && page.nextCursor >= cursor))) {
    throw new Error('聊天分页游标异常，请重试补偿')
  }
}

/** 从补偿游标拉到冻结的旧消息 ID；达到上限时返回缺口内游标供继续加载。 */
export async function recoverMessages(
  fetchPage: (cursor: number | undefined, limit: number) => Promise<Page<ChatMessage>>,
  boundary: RecoveryBoundary<MessageCache>,
  isCurrent: () => boolean,
): Promise<Recovered<ChatMessage> | null> {
  const knownIds = new Set(boundary.cache.msgs.map((message) => message.messageId).filter(Boolean))
  let cursor = boundary.nextCursor
  let items: ChatMessage[] = []
  for (let pageIndex = 0; pageIndex < MAX_RECOVERY_PAGES; pageIndex++) {
    if (!isCurrent()) return null
    const page = await fetchPage(cursor ?? undefined, 100)
    if (!isCurrent()) return null
    items = mergeMessages(page.items, items)
    const reachedOldRange = page.items.some((message) => knownIds.has(message.messageId))
    if (!page.hasMore || reachedOldRange || boundary.cache.msgs.length === 0) {
      return { items, complete: true,
        hasMore: reachedOldRange && page.hasMore ? boundary.cache.hasMore : page.hasMore,
        cursor: reachedOldRange && page.hasMore ? boundary.cache.cursor : page.nextCursor }
    }
    checkCursor(page, cursor)
    cursor = page.nextCursor
  }
  return { items, hasMore: true, cursor, complete: false }
}

/** 补齐从最新会话到旧列表末端的范围；仅命中旧会话 ID 不能证明中间没有缺口。 */
export async function recoverConversations(
  fetchPage: (cursor: number | undefined) => Promise<Page<Conversation>>,
  boundary: RecoveryBoundary<ConversationCache>,
  isCurrent: () => boolean,
): Promise<Recovered<Conversation> | null> {
  let cursor = boundary.nextCursor
  let items: Conversation[] = []
  for (let pageIndex = 0; pageIndex < MAX_RECOVERY_PAGES; pageIndex++) {
    if (!isCurrent()) return null
    const page = await fetchPage(cursor ?? undefined)
    if (!isCurrent()) return null
    items = mergeConversations(page.items, items)
    const reachedOldRange = boundary.cache.cursor !== null && page.nextCursor !== null &&
      page.nextCursor <= boundary.cache.cursor
    if (!page.hasMore || reachedOldRange || boundary.cache.convs.length === 0) {
      return { items, complete: true,
        hasMore: reachedOldRange && page.hasMore ? boundary.cache.hasMore : page.hasMore,
        cursor: reachedOldRange && page.hasMore ? boundary.cache.cursor : page.nextCursor }
    }
    checkCursor(page, cursor)
    cursor = page.nextCursor
  }
  return { items, hasMore: true, cursor, complete: false }
}
