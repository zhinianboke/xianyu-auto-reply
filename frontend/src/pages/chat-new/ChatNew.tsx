/**
 * 在线聊天 主页面
 *
 * 三栏布局：左侧账号列表 | 中间会话列表 | 右侧聊天记录
 * 支持多账号切换，基于WebSocket API获取数据
 */
import { useEffect, useState, useRef, useCallback } from 'react'
import { Loader2, LogIn, LogOut, MessageCircle, RefreshCw, User, ChevronUp, X, Send, AlertCircle, Ban, ImagePlus } from 'lucide-react'
import { useUIStore } from '@/store/uiStore'
import {
  getChatAccounts,
  connectAccount,
  disconnectAccount,
  getConversations,
  getMessages,
  sendTextMessage,
  sendImageMessage,
  queryUserInfos,
  getAccountProfile,
  getCustomerOrders,
  getQuickPhrases,
  createQuickPhrase,
  updateQuickPhrase,
  deleteQuickPhrase,
  recallMessage,
  getOfficialBlacklistStatus,
  changeOfficialBlacklist,
  type ChatAccount,
  type Conversation,
  type ChatMessage,
  type CustomerOrder,
  type QuickPhrase,
} from '@/api/chatNew'
import { cancelOrder, fetchXianyuOrders, getOrderDetail, manualDelivery, noLogisticsDelivery, type OrderDetail } from '@/api/orders'
import { useChatNewWs } from './useChatNewWs'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { CustomerOrdersPanel } from './CustomerOrdersPanel'
import { QuickPhrasesPanel } from './QuickPhrasesPanel'
import { OrderDetailModal } from './OrderDetailModal'

/** 检查昵称是否为纯数字（如用户ID），纯数字视为无效昵称 */
const isPureDigits = (name: string) => /^\d+$/.test(name)

const toTimestampMs = (timestamp: number) =>
  timestamp < 1_000_000_000_000 ? timestamp * 1000 : timestamp

const canRecallMessage = (message: ChatMessage) =>
  message.isSelf &&
  !!message.messageId &&
  message.type !== 'system' &&
  Date.now() - toTimestampMs(message.time) >= 0 &&
  Date.now() - toTimestampMs(message.time) <= 120_000

export function ChatNew() {
  const { addToast } = useUIStore()

  // 账号相关（分页加载）
  const [accounts, setAccounts] = useState<ChatAccount[]>([])
  const [activeAccountId, setActiveAccountId] = useState('')
  const [loadingAccounts, setLoadingAccounts] = useState(false)
  const [connectingId, setConnectingId] = useState('')
  const [accountPage, setAccountPage] = useState(1)
  const [accountHasMore, setAccountHasMore] = useState(false)
  const accountListRef = useRef<HTMLDivElement>(null)

  // 会话相关
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loadingConvs, setLoadingConvs] = useState(false)
  const [activeCid, setActiveCid] = useState('')
  const [convHasMore, setConvHasMore] = useState(false)
  const [convCursor, setConvCursor] = useState<number | null>(null)

  // 消息相关
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [loadingMsgs, setLoadingMsgs] = useState(false)
  const [msgHasMore, setMsgHasMore] = useState(false)
  const [msgCursor, setMsgCursor] = useState<number | null>(null)
  const msgContainerRef = useRef<HTMLDivElement>(null)

  // 图片预览
  const [previewImage, setPreviewImage] = useState('')

  // 用户信息缓存（otherUserId -> {avatar, nick}）
  const userInfoCacheRef = useRef<Record<string, { avatar: string; nick: string }>>({})

  // 发送消息
  const [inputText, setInputText] = useState('')
  const [sending, setSending] = useState(false)
  // 发送图片：隐藏的文件选择框引用
  const imageInputRef = useRef<HTMLInputElement>(null)

  // 当前客户订单与快捷短语
  const [customerOrders, setCustomerOrders] = useState<CustomerOrder[]>([])
  const [loadingOrders, setLoadingOrders] = useState(false)
  const [deliveringOrderNo, setDeliveringOrderNo] = useState('')
  const [confirmingOrderNo, setConfirmingOrderNo] = useState('')
  const [cancellingOrderNo, setCancellingOrderNo] = useState('')
  const [orderDetail, setOrderDetail] = useState<OrderDetail | null>(null)
  const [loadingOrderDetail, setLoadingOrderDetail] = useState(false)
  const [blacklisting, setBlacklisting] = useState(false)
  const [isOfficiallyBlocked, setIsOfficiallyBlocked] = useState(false)
  const [recallingMessageId, setRecallingMessageId] = useState('')
  const [confirmDialog, setConfirmDialog] = useState<{
    title: string
    message: string
    confirmText: string
    type: 'warning' | 'danger' | 'info'
  } | null>(null)
  const confirmResolverRef = useRef<((confirmed: boolean) => void) | null>(null)
  const [quickPhrases, setQuickPhrases] = useState<QuickPhrase[]>([])
  const [editingPhraseId, setEditingPhraseId] = useState<number | null>(null)
  const [phraseTitle, setPhraseTitle] = useState('')
  const [phraseContent, setPhraseContent] = useState('')
  const [savingPhrase, setSavingPhrase] = useState(false)

  // 手动管理 WebSocket 连接的账号列表（仅用户显式操作时加入，页面刷新不自动重连）
  const [wsAccountIds, setWsAccountIds] = useState<string[]>([])

  const requestConfirm = useCallback((options: {
    title?: string
    message: string
    confirmText?: string
    type?: 'warning' | 'danger' | 'info'
  }) => new Promise<boolean>((resolve) => {
    confirmResolverRef.current?.(false)
    confirmResolverRef.current = resolve
    setConfirmDialog({
      title: options.title || '确认操作',
      message: options.message,
      confirmText: options.confirmText || '确定',
      type: options.type || 'warning',
    })
  }), [])

  const closeConfirm = (confirmed: boolean) => {
    confirmResolverRef.current?.(confirmed)
    confirmResolverRef.current = null
    setConfirmDialog(null)
  }

  // 用 ref 保存当前选中的账号和会话，供 WebSocket 回调使用（避免闭包问题）
  const activeAccountIdRef = useRef(activeAccountId)
  useEffect(() => { activeAccountIdRef.current = activeAccountId }, [activeAccountId])
  const activeCidRef = useRef(activeCid)
  useEffect(() => { activeCidRef.current = activeCid }, [activeCid])
  const reloadOrdersRef = useRef<() => void>(() => {})

  // ==================== 按账号缓存：切换账号时保留数据 ====================
  /** 每个账号的会话列表缓存 */
  const convsCacheRef = useRef<Record<string, {
    convs: Conversation[]; hasMore: boolean; cursor: number | null
  }>>({})
  /** 每个账号每个会话的消息缓存 */
  const msgsCacheRef = useRef<Record<string, Record<string, {
    msgs: ChatMessage[]; hasMore: boolean; cursor: number | null
  }>>>({})
  /** 记住每个账号上次选中的会话 */
  const activeConvPerAccountRef = useRef<Record<string, string>>({})

  /**
   * 同步当前会话列表到缓存
   * 注意：切换账号时 activeAccountId 已变但 conversations 还是旧账号的，
   * 必须跳过这次同步，否则会把旧数据写到新账号的缓存中
   */
  const convSyncAccountRef = useRef('')
  useEffect(() => {
    if (activeAccountId !== convSyncAccountRef.current) {
      convSyncAccountRef.current = activeAccountId
      return // activeAccountId 刚切换，conversations 还是旧的，跳过
    }
    if (activeAccountId && conversations.length > 0) {
      convsCacheRef.current[activeAccountId] = { convs: conversations, hasMore: convHasMore, cursor: convCursor }
    }
  }, [conversations, convHasMore, convCursor, activeAccountId])
  /** 同步当前消息列表到缓存（同理，切换账号或会话时跳过） */
  const msgSyncKeyRef = useRef('')
  useEffect(() => {
    const key = `${activeAccountId}:${activeCid}`
    if (key !== msgSyncKeyRef.current) {
      msgSyncKeyRef.current = key
      return
    }
    if (activeAccountId && activeCid && messages.length > 0) {
      if (!msgsCacheRef.current[activeAccountId]) msgsCacheRef.current[activeAccountId] = {}
      msgsCacheRef.current[activeAccountId][activeCid] = { msgs: messages, hasMore: msgHasMore, cursor: msgCursor }
    }
  }, [messages, msgHasMore, msgCursor, activeAccountId, activeCid])
  /** 记住每个账号的当前会话（同理跳过） */
  const cidSyncAccountRef = useRef('')
  useEffect(() => {
    if (activeAccountId !== cidSyncAccountRef.current) {
      cidSyncAccountRef.current = activeAccountId
      return
    }
    if (activeAccountId) activeConvPerAccountRef.current[activeAccountId] = activeCid
  }, [activeCid, activeAccountId])

  // ==================== WebSocket 实时推送（多账号） ====================
  /** 更新会话列表的通用逻辑（可作用于 state 数组或缓存数组） */
  const updateConvList = (convs: Conversation[], cid: string, summary: string, msg: ChatMessage, isViewing: boolean): Conversation[] => {
    const exists = convs.some((c) => c.cid === cid)
    if (exists) {
      const updated = convs.map((c) => {
        if (c.cid !== cid) return c
        return { ...c, lastMessageSummary: summary, lastMessageTime: msg.time, unreadCount: isViewing ? 0 : c.unreadCount + 1 }
      })
      const target = updated.find((c) => c.cid === cid)!
      return [target, ...updated.filter((c) => c.cid !== cid)]
    }
    // 新会话
    const newConv: Conversation = {
      cid, rawCid: cid,
      otherUserId: msg.isSelf ? '' : msg.senderId,
      otherUserName: msg.isSelf ? '' : (msg.senderName || ''),
      otherUserAvatar: '', itemTitle: '',
      lastMessageSummary: summary, lastMessageTime: msg.time,
      unreadCount: isViewing ? 0 : 1,
    }
    return [newConv, ...convs]
  }

  /** 追加消息到消息列表（去重自己发的） */
  const appendMsg = (msgs: ChatMessage[], msg: ChatMessage): ChatMessage[] => {
    if (msg.isSelf && msgs.some((m) => m.isSelf && m.text === msg.text && Math.abs(m.time - msg.time) < 5000)) {
      return msgs
    }
    return [...msgs, msg]
  }

  const handleWsNewMessage = useCallback((accountId: string, cid: string, msg: ChatMessage) => {
    const summary = msg.type === 'image' ? '[图片]' : (msg.text || '').slice(0, 50)
    const isActiveAccount = accountId === activeAccountIdRef.current

    if (isActiveAccount) {
      // 活跃账号 → 直接更新 React state
      const isViewingConv = cid === activeCidRef.current
      setConversations((prev) => updateConvList(prev, cid, summary, msg, isViewingConv))
      if (isViewingConv) {
        setMessages((prev) => appendMsg(prev, msg))
        window.setTimeout(() => reloadOrdersRef.current(), 900)
      }
    } else {
      // 后台账号 → 更新缓存（不触发渲染）
      const cached = convsCacheRef.current[accountId]
      if (cached) {
        cached.convs = updateConvList(cached.convs, cid, summary, msg, false)
      }
      // 如果该会话的消息也在缓存中，追加消息
      const msgCache = msgsCacheRef.current[accountId]?.[cid]
      if (msgCache) {
        msgCache.msgs = appendMsg(msgCache.msgs, msg)
      }
    }
  }, [])

  // WebSocket 断连时刷新账号状态（节流：最多每 5 秒刷一次）
  const lastDisconnectRefreshRef = useRef(0)
  const handleWsDisconnect = useCallback((_accountId: string) => {
    const now = Date.now()
    if (now - lastDisconnectRefreshRef.current < 5000) return
    lastDisconnectRefreshRef.current = now
    getChatAccounts(1).then((res) => {
      setAccounts(res.data)
      setAccountPage(1)
      setAccountHasMore(res.hasMore)
    }).catch(() => {})
  }, [])

  // 仅为用户手动操作过的已连接账号建立 WebSocket（页面刷新不自动重连）
  useChatNewWs({
    accountIds: wsAccountIds,
    onNewMessage: handleWsNewMessage,
    onDisconnect: handleWsDisconnect,
  })

  // ==================== 加载账号列表（分页） ====================
  const loadAccounts = useCallback(async (page = 1) => {
    setLoadingAccounts(true)
    try {
      const res = await getChatAccounts(page)
      if (page === 1) {
        setAccounts(res.data)
      } else {
        setAccounts((prev) => [...prev, ...res.data])
      }
      setAccountPage(page)
      setAccountHasMore(res.hasMore)
    } catch (e: any) {
      addToast({ message: e.message || '获取账号列表失败', type: 'error' })
    } finally {
      setLoadingAccounts(false)
    }
  }, [addToast])

  /** 加载更多账号 */
  const loadMoreAccounts = useCallback(() => {
    if (!loadingAccounts && accountHasMore) {
      loadAccounts(accountPage + 1)
    }
  }, [loadingAccounts, accountHasMore, accountPage, loadAccounts])

  useEffect(() => {
    loadAccounts()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ==================== 连接/断开 ====================
  const handleConnect = async (accountId: string) => {
    setConnectingId(accountId)
    try {
      const res = await connectAccount(accountId)
      if (res.success) {
        addToast({ message: '连接成功', type: 'success' })
        await loadAccounts()
        setActiveAccountId(accountId)
        setWsAccountIds((prev) => prev.includes(accountId) ? prev : [...prev, accountId])
      } else {
        addToast({ message: res.message || '连接失败', type: 'error' })
      }
    } catch (e: any) {
      addToast({ message: e.message || '连接失败', type: 'error' })
    } finally {
      setConnectingId('')
    }
  }

  const handleDisconnect = async (accountId: string) => {
    try {
      await disconnectAccount(accountId)
      addToast({ message: '已断开连接', type: 'success' })
      setWsAccountIds((prev) => prev.filter((id) => id !== accountId))
      if (activeAccountId === accountId) {
        setActiveAccountId('')
        setConversations([])
        setActiveCid('')
        setMessages([])
      }
      await loadAccounts()
    } catch (e: any) {
      addToast({ message: e.message || '断开失败', type: 'error' })
    }
  }

  /** 点击账号卡片：已连接则选中，未连接则自动连接 */
  const handleSelectAccount = async (acc: ChatAccount) => {
    if (acc.connected) {
      setActiveAccountId(acc.account_id)
      // 选中已连接账号时也建立 WebSocket（页面刷新后首次选中时触发）
      setWsAccountIds((prev) => prev.includes(acc.account_id) ? prev : [...prev, acc.account_id])
    } else {
      await handleConnect(acc.account_id)
    }
  }

  // ==================== 加载会话列表 ====================
  const loadConversations = useCallback(
    async (accountId: string, append = false) => {
      if (!accountId) return
      if (!append) setLoadingConvs(true)
      try {
        const cursor = append ? convCursor : undefined
        const res = await getConversations(accountId, cursor ?? undefined)
        // 从本地缓存补填已有的头像和昵称，避免刷新后信息消失
        const withCachedAvatar = res.conversations.map((c: Conversation) => {
          const cached = userInfoCacheRef.current[c.otherUserId]
          if (!cached) return c
          const updates: Partial<Conversation> = {}
          if (cached.avatar && !c.otherUserAvatar) updates.otherUserAvatar = cached.avatar
          // 昵称为空或纯数字时用缓存补填
          if (cached.nick && (!c.otherUserName || isPureDigits(c.otherUserName))) updates.otherUserName = cached.nick
          return Object.keys(updates).length > 0 ? { ...c, ...updates } : c
        })
        if (append) {
          setConversations((prev) => [...prev, ...withCachedAvatar])
        } else {
          setConversations(withCachedAvatar)
        }
        setConvHasMore(res.hasMore)
        setConvCursor(res.nextCursor)
        if (!append && withCachedAvatar[0]?.cid) {
          getAccountProfile(accountId, withCachedAvatar[0].cid).then((profile) => {
            if (profile.nick) {
              setAccounts((prev) => prev.map((account) => (
                account.account_id === accountId ? { ...account, display_name: profile.nick } : account
              )))
            }
          }).catch(() => {})
        }
      } catch (e: any) {
        // 首次加载和翻页都提示错误
        addToast({ message: e.message || '获取会话列表失败', type: 'error' })
      } finally {
        setLoadingConvs(false)
      }
    },
    [addToast, convCursor],
  )

  // 用 ref 保持 accounts 最新引用，避免 effect 闭包取到旧值
  const accountsRef = useRef(accounts)
  useEffect(() => { accountsRef.current = accounts }, [accounts])

  // 选中账号时：优先从缓存恢复，无缓存才加载
  useEffect(() => {
    if (!activeAccountId) {
      setConversations([])
      setActiveCid('')
      setMessages([])
      return
    }
    const acc = accountsRef.current.find((a) => a.account_id === activeAccountId)
    if (!acc?.connected) {
      // 未连接的账号，先清空旧数据
      setConversations([])
      setActiveCid('')
      setMessages([])
      setMsgCursor(null)
      setMsgHasMore(false)
      return
    }

    // 1. 恢复会话列表
    const cachedConvs = convsCacheRef.current[activeAccountId]
    if (cachedConvs && cachedConvs.convs.length > 0) {
      setConversations(cachedConvs.convs)
      setConvHasMore(cachedConvs.hasMore)
      setConvCursor(cachedConvs.cursor)
    } else {
      setConversations([])
      setConvCursor(null)
      loadConversations(activeAccountId)
    }

    // 2. 恢复上次选中的会话和消息
    const prevCid = activeConvPerAccountRef.current[activeAccountId] || ''
    setActiveCid(prevCid)
    if (prevCid) {
      const cachedMsgs = msgsCacheRef.current[activeAccountId]?.[prevCid]
      if (cachedMsgs) {
        setMessages(cachedMsgs.msgs)
        setMsgHasMore(cachedMsgs.hasMore)
        setMsgCursor(cachedMsgs.cursor)
      } else {
        setMessages([])
        setMsgCursor(null)
        setMsgHasMore(false)
      }
    } else {
      setMessages([])
      setMsgCursor(null)
      setMsgHasMore(false)
    }
  }, [activeAccountId]) // eslint-disable-line react-hooks/exhaustive-deps


  // ==================== 加载用户信息（头像+昵称） ====================
  // 找出缺少头像或昵称的会话，构建 [{userId, cid}] 查询列表
  const missingInfoConvs = conversations.filter(
    (c) => {
      if (!c.otherUserId || !c.cid) return false
      // 昵称有效（非空且非纯数字）且头像存在时无需查询
      const hasValidName = !!c.otherUserName && !isPureDigits(c.otherUserName)
      if (c.otherUserAvatar && hasValidName) return false
      // 缓存中已有完整信息则跳过
      const cached = userInfoCacheRef.current[c.otherUserId]
      if (cached && cached.avatar && cached.nick) return false
      return true
    },
  )
  // 以 userId 去重后构建依赖 key
  const missingInfoKey = [...new Set(missingInfoConvs.map((c) => c.otherUserId))].sort().join(',')

  useEffect(() => {
    if (!activeAccountId || !missingInfoKey) return

    // 以 userId 去重后构建查询参数
    const seen = new Set<string>()
    const queries: { userId: string; cid: string }[] = []
    for (const c of missingInfoConvs) {
      if (!seen.has(c.otherUserId)) {
        seen.add(c.otherUserId)
        queries.push({ userId: c.otherUserId, cid: c.cid })
      }
    }
    if (queries.length === 0) return

    // 分批查询（每批3个），每批完成立即更新UI
    const BATCH_SIZE = 3
    let cancelled = false

    const applyInfos = (infos: Record<string, { avatar: string; nick: string }>) => {
      for (const [uid, info] of Object.entries(infos)) {
        // 同时缓存 avatar 和 nick
        const prev = userInfoCacheRef.current[uid] || { avatar: '', nick: '' }
        userInfoCacheRef.current[uid] = {
          avatar: info.avatar || prev.avatar,
          nick: info.nick || prev.nick,
        }
      }
      setConversations((prev) =>
        prev.map((c) => {
          const info = infos[c.otherUserId]
          if (!info) return c
          const updates: Partial<Conversation> = {}
          if (info.avatar && !c.otherUserAvatar) updates.otherUserAvatar = info.avatar
          // 昵称为空或纯数字时用 API 返回的昵称覆盖
          if (info.nick && (!c.otherUserName || isPureDigits(c.otherUserName))) updates.otherUserName = info.nick
          return Object.keys(updates).length > 0 ? { ...c, ...updates } : c
        }),
      )
    }

    ;(async () => {
      for (let i = 0; i < queries.length; i += BATCH_SIZE) {
        if (cancelled) break
        const batch = queries.slice(i, i + BATCH_SIZE)
        try {
          const infos = await queryUserInfos(activeAccountId, batch)
          if (!cancelled && infos && Object.keys(infos).length > 0) {
            applyInfos(infos)
          }
        } catch {
          // 单批失败不影响后续批次
        }
      }
    })()

    return () => { cancelled = true }
  }, [activeAccountId, missingInfoKey]) // eslint-disable-line react-hooks/exhaustive-deps

  // ==================== 加载聊天记录 ====================
  const loadMessages = useCallback(
    async (accountId: string, cid: string, append = false) => {
      if (!accountId || !cid) return
      if (!append) setLoadingMsgs(true)
      try {
        const cursor = append ? msgCursor : undefined
        const res = await getMessages(accountId, cid, cursor ?? undefined)
        if (append) {
          // 追加历史消息到前面
          setMessages((prev) => [...res.messages, ...prev])
        } else {
          setMessages(res.messages)
        }
        setMsgHasMore(res.hasMore)
        setMsgCursor(res.nextCursor)
      } catch (e: any) {
        if (!append) {
          addToast({ message: e.message || '获取聊天记录失败', type: 'error' })
        }
      } finally {
        setLoadingMsgs(false)
      }
    },
    [addToast, msgCursor],
  )

  // 选中会话时：优先从缓存恢复消息，无缓存才加载
  const handleSelectConversation = (cid: string) => {
    setActiveCid(cid)
    // 清零该会话的未读数
    setConversations((prev) =>
      prev.map((c) => (c.cid === cid ? { ...c, unreadCount: 0 } : c)),
    )
    // 尝试从缓存恢复消息
    const cachedMsgs = msgsCacheRef.current[activeAccountId]?.[cid]
    if (cachedMsgs && cachedMsgs.msgs.length > 0) {
      setMessages(cachedMsgs.msgs)
      setMsgHasMore(cachedMsgs.hasMore)
      setMsgCursor(cachedMsgs.cursor)
    } else {
      setMessages([])
      setMsgCursor(null)
      setMsgHasMore(false)
      loadMessages(activeAccountId, cid)
    }
  }

  const activeConversation = conversations.find((c) => c.cid === activeCid)

  useEffect(() => {
    let cancelled = false
    setIsOfficiallyBlocked(false)
    if (!activeAccountId || !activeCid) return
    getOfficialBlacklistStatus(activeAccountId, activeCid)
      .then((blocked) => { if (!cancelled) setIsOfficiallyBlocked(blocked) })
      .catch(() => { if (!cancelled) setIsOfficiallyBlocked(false) })
    return () => { cancelled = true }
  }, [activeAccountId, activeCid])

  const loadCustomerOrders = useCallback(async (silent = false) => {
    if (!activeAccountId || !activeConversation?.otherUserId) {
      setCustomerOrders([])
      return
    }
    if (!silent) setLoadingOrders(true)
    try {
      const data = await getCustomerOrders(activeAccountId, activeConversation.otherUserId, activeCid)
      setCustomerOrders(data)
    } catch (e: any) {
      addToast({ message: e.message || '获取客户订单失败', type: 'error' })
    } finally {
      if (!silent) setLoadingOrders(false)
    }
  }, [activeAccountId, activeCid, activeConversation?.otherUserId, addToast])

  useEffect(() => {
    loadCustomerOrders()
  }, [loadCustomerOrders])

  useEffect(() => {
    reloadOrdersRef.current = () => { void loadCustomerOrders(true) }
  }, [loadCustomerOrders])

  useEffect(() => {
    if (!activeCid) return
    const timer = window.setInterval(() => { void loadCustomerOrders(true) }, 15000)
    return () => window.clearInterval(timer)
  }, [activeCid, loadCustomerOrders])

  const loadQuickPhrases = useCallback(async () => {
    try {
      setQuickPhrases(await getQuickPhrases())
    } catch (e: any) {
      addToast({ message: e.message || '获取快捷短语失败', type: 'error' })
    }
  }, [addToast])

  useEffect(() => {
    loadQuickPhrases()
  }, [loadQuickPhrases])

  const resetPhraseForm = () => {
    setEditingPhraseId(null)
    setPhraseTitle('')
    setPhraseContent('')
  }

  const handleSavePhrase = async () => {
    if (!phraseTitle.trim() || !phraseContent.trim() || savingPhrase) return
    setSavingPhrase(true)
    try {
      const payload = { title: phraseTitle.trim(), content: phraseContent.trim(), sort_order: 0 }
      if (editingPhraseId) {
        await updateQuickPhrase(editingPhraseId, payload)
      } else {
        await createQuickPhrase(payload)
      }
      resetPhraseForm()
      await loadQuickPhrases()
      addToast({ message: editingPhraseId ? '快捷短语已更新' : '快捷短语已添加', type: 'success' })
    } catch (e: any) {
      addToast({ message: e.message || '保存快捷短语失败', type: 'error' })
    } finally {
      setSavingPhrase(false)
    }
  }

  const handleDeletePhrase = async (id: number) => {
    if (!(await requestConfirm({ message: '确认删除这条快捷短语吗？', confirmText: '删除', type: 'danger' }))) return
    try {
      await deleteQuickPhrase(id)
      if (editingPhraseId === id) resetPhraseForm()
      await loadQuickPhrases()
    } catch (e: any) {
      addToast({ message: e.message || '删除快捷短语失败', type: 'error' })
    }
  }

  const handleSyncOrders = async () => {
    if (!activeAccountId || loadingOrders) return
    setLoadingOrders(true)
    try {
      const res = await fetchXianyuOrders(activeAccountId)
      addToast({ message: res.message || '订单同步完成', type: res.success ? 'success' : 'error' })
      await loadCustomerOrders()
    } catch (e: any) {
      addToast({ message: e.message || '同步订单失败', type: 'error' })
    } finally {
      setLoadingOrders(false)
    }
  }

  const handleDeliverOrder = async (orderNo: string) => {
    if (!(await requestConfirm({ message: `确认立即发货订单 ${orderNo} 吗？`, confirmText: '发货' }))) return
    setDeliveringOrderNo(orderNo)
    try {
      const res = await manualDelivery(orderNo)
      addToast({ message: res.message || (res.success ? '发货成功' : '发货失败'), type: res.success ? 'success' : 'error' })
      await loadCustomerOrders()
    } catch (e: any) {
      addToast({ message: e.message || '发货失败', type: 'error' })
    } finally {
      setDeliveringOrderNo('')
    }
  }


  // 消息变化时自动滚动到底部
  const handleNoLogisticsDelivery = async (orderNo: string) => {
    if (!(await requestConfirm({ message: `确认将订单 ${orderNo} 标记为无物流发货吗？`, confirmText: '无物流发货' }))) return
    setConfirmingOrderNo(orderNo)
    try {
      const res = await noLogisticsDelivery(orderNo)
      addToast({ message: res.message || (res.success ? '无物流发货成功' : '无物流发货失败'), type: res.success ? 'success' : 'error' })
      await loadCustomerOrders(true)
    } catch (e: any) {
      addToast({ message: e.message || '无物流发货失败', type: 'error' })
    } finally {
      setConfirmingOrderNo('')
    }
  }

  const handleCancelOrder = async (orderNo: string) => {
    if (!(await requestConfirm({ message: `确认取消客户订单 ${orderNo} 吗？取消后无法恢复。`, confirmText: '取消订单', type: 'danger' }))) return
    setCancellingOrderNo(orderNo)
    try {
      const res = await cancelOrder(orderNo)
      addToast({ message: res.message || (res.success ? '订单已取消' : '取消订单失败'), type: res.success ? 'success' : 'error' })
      await loadCustomerOrders(true)
    } catch (e: any) {
      addToast({ message: e.message || '取消订单失败', type: 'error' })
    } finally {
      setCancellingOrderNo('')
    }
  }

  const handleViewOrderDetail = async (orderNo: string) => {
    setLoadingOrderDetail(true)
    try {
      const res = await getOrderDetail(orderNo, true)
      setOrderDetail(res.data)
      await loadCustomerOrders(true)
    } catch (e: any) {
      addToast({ message: e.message || '获取订单详情失败', type: 'error' })
    } finally {
      setLoadingOrderDetail(false)
    }
  }

  const handleBlacklistCustomer = async () => {
    if (!activeConversation || !activeAccountId || blacklisting) return
    const action = isOfficiallyBlocked ? 'remove' : 'add'
    const label = isOfficiallyBlocked ? '解除黑名单' : '加入黑名单'
    if (!(await requestConfirm({
      title: `确认${label}`,
      message: `确认在闲鱼官方${label}客户 ${activeConversation.otherUserName || activeConversation.otherUserId} 吗？`,
      confirmText: label,
      type: isOfficiallyBlocked ? 'warning' : 'danger',
    }))) return
    setBlacklisting(true)
    try {
      const res = await changeOfficialBlacklist(activeAccountId, activeConversation.cid, action)
      if (!res.success) throw new Error(res.message || '黑名单操作失败')
      setIsOfficiallyBlocked(action === 'add')
      addToast({ message: res.message || `${label}成功`, type: 'success' })
    } catch (e: any) {
      addToast({ message: e.message || '加入黑名单失败', type: 'error' })
    } finally {
      setBlacklisting(false)
    }
  }

  const handleRecallMessage = async (msg: ChatMessage) => {
    if (!activeAccountId || !msg.messageId || recallingMessageId) return
    if (!canRecallMessage(msg)) {
      addToast({ message: '消息发送超过两分钟，无法撤回', type: 'error' })
      return
    }
    if (!(await requestConfirm({
      title: '撤回消息',
      message: '确认撤回这条消息吗？撤回仅支持发送后两分钟内操作。',
      confirmText: '撤回',
      type: 'danger',
    }))) return
    setRecallingMessageId(msg.messageId)
    try {
      const res = await recallMessage(activeAccountId, msg.messageId, msg.time)
      if (!res.success) throw new Error(res.message || '撤回失败')
      setMessages((prev) => prev.map((item) => item.messageId === msg.messageId
        ? { ...item, type: 'system', text: '你撤回了一条消息', images: [] }
        : item))
      addToast({ message: res.message || '消息已撤回', type: 'success' })
    } catch (e: any) {
      addToast({ message: e.message || '撤回失败', type: 'error' })
    } finally {
      setRecallingMessageId('')
    }
  }

  const prevMsgCountRef = useRef(0)
  useEffect(() => {
    if (!msgContainerRef.current) return
    const container = msgContainerRef.current
    // 只有新增消息时才滚动（而不是加载历史）
    if (messages.length > prevMsgCountRef.current || prevMsgCountRef.current === 0) {
      container.scrollTop = container.scrollHeight
    }
    prevMsgCountRef.current = messages.length
  }, [messages])

  // ==================== 发送消息 ====================
  const sendMessageText = async (rawText: string, clearInput = false) => {
    if (!rawText.trim() || !activeAccountId || !activeCid || sending) return

    // 获取当前会话的对方用户ID
    const conv = conversations.find((c) => c.cid === activeCid)
    if (!conv) {
      addToast({ message: '未找到当前会话信息', type: 'error' })
      return
    }

    const text = rawText.trim()
    setSending(true)
    try {
      const res = await sendTextMessage(activeAccountId, activeCid, conv.otherUserId, text)
      // 无论成功失败，都把这条消息展示在聊天记录中；
      // 失败时标记 failed + failReason，气泡前显示红色感叹号，点击查看原因
      const sentMsg: ChatMessage = {
        messageId: res.data?.messageId || '',
        senderId: activeAccountId,
        senderName: '',
        isSelf: true,
        type: 'text',
        text,
        images: [],
        time: Date.now(),
        failed: !res.success,
        failReason: res.success ? undefined : (res.message || '发送失败'),
      }
      if (clearInput) setInputText('')
      setMessages((prev) => [...prev, sentMsg])
      if (res.success) {
        // 成功才更新会话列表摘要
        setConversations((prev) =>
          prev.map((c) =>
            c.cid === activeCid
              ? { ...c, lastMessageSummary: text.slice(0, 50), lastMessageTime: sentMsg.time }
              : c,
          ),
        )
      } else {
        addToast({ message: res.message || '发送失败', type: 'error' })
      }
    } catch (e: any) {
      // 网络等异常：同样以失败态展示该条消息
      const failReason = e?.message || '发送失败'
      const sentMsg: ChatMessage = {
        messageId: '',
        senderId: activeAccountId,
        senderName: '',
        isSelf: true,
        type: 'text',
        text,
        images: [],
        time: Date.now(),
        failed: true,
        failReason,
      }
      if (clearInput) setInputText('')
      setMessages((prev) => [...prev, sentMsg])
      addToast({ message: failReason, type: 'error' })
    } finally {
      setSending(false)
    }
  }

  const handleSendMessage = () => sendMessageText(inputText, true)

  // ==================== 发送图片 ====================
  const handlePickImage = () => {
    if (sending) return
    imageInputRef.current?.click()
  }

  const handleImageSelected = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    // 选完即清空 value，保证同一张图片可重复选择触发 onChange
    e.target.value = ''
    if (!file || !activeAccountId || !activeCid || sending) return

    if (!file.type.startsWith('image/')) {
      addToast({ message: '请选择图片文件', type: 'error' })
      return
    }
    if (file.size > 10 * 1024 * 1024) {
      addToast({ message: '图片大小不能超过10MB', type: 'error' })
      return
    }

    const conv = conversations.find((c) => c.cid === activeCid)
    if (!conv) {
      addToast({ message: '未找到当前会话信息', type: 'error' })
      return
    }

    setSending(true)
    const res = await sendImageMessage(activeAccountId, activeCid, conv.otherUserId, file)
    // 成功用CDN地址；失败则用本地预览地址，保证用户都能看到所发图片
    const displayUrl = res.success && res.data?.imageUrl ? res.data.imageUrl : URL.createObjectURL(file)
    // 无论成功失败，都把这条图片消息展示在聊天记录中
    const sentMsg: ChatMessage = {
      messageId: res.data?.messageId || '',
      senderId: activeAccountId,
      senderName: '',
      isSelf: true,
      type: 'image',
      text: '',
      images: [displayUrl],
      time: Date.now(),
      failed: !res.success,
      failReason: res.success ? undefined : (res.message || '发送失败'),
    }
    setMessages((prev) => [...prev, sentMsg])
    if (res.success) {
      setConversations((prev) =>
        prev.map((c) =>
          c.cid === activeCid
            ? { ...c, lastMessageSummary: '[图片]', lastMessageTime: sentMsg.time }
            : c,
        ),
      )
    } else {
      addToast({ message: res.message || '发送失败', type: 'error' })
    }
    setSending(false)
  }

  // ==================== 时间格式化 ====================
  const formatTime = (ts: number) => {
    if (!ts) return ''
    const d = new Date(ts)
    const now = new Date()
    const isToday =
      d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate()
    if (isToday) {
      return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
    }
    return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) +
      ' ' +
      d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
  }

  // ==================== 渲染 ====================
  return (
    <div className="flex h-[calc(100vh-120px)] gap-3">
      {/* 左侧：账号列表 */}
      <div className="w-56 flex-shrink-0 bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col">
        <div className="p-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <span className="font-medium text-sm text-gray-700 dark:text-gray-300">账号列表</span>
          <button
            onClick={() => loadAccounts()}
            className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
            title="刷新"
          >
            <RefreshCw className={`w-4 h-4 text-gray-500 ${loadingAccounts ? 'animate-spin' : ''}`} />
          </button>
        </div>
        <div
          ref={accountListRef}
          className="flex-1 overflow-y-auto p-2 space-y-1"
          onScroll={(e) => {
            const el = e.currentTarget
            if (el.scrollHeight - el.scrollTop - el.clientHeight < 40) {
              loadMoreAccounts()
            }
          }}
        >
          {loadingAccounts && accounts.length === 0 ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
            </div>
          ) : accounts.length === 0 ? (
            <p className="text-center text-sm text-gray-400 py-8">暂无可用账号</p>
          ) : (
            <>
              {accounts.map((acc) => (
                <div
                  key={acc.account_id}
                  className={`p-2 rounded-lg transition-colors text-sm cursor-pointer ${
                    activeAccountId === acc.account_id
                      ? 'bg-blue-50 dark:bg-blue-900/30 border border-blue-200 dark:border-blue-700'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-700/50 border border-transparent'
                  }`}
                  onClick={() => handleSelectAccount(acc)}
                  title={`${acc.display_name || acc.remark || acc.account_id}\n(${acc.account_id})`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <User className="w-4 h-4 flex-shrink-0 text-gray-400" />
                      <div className="min-w-0 flex-1">
                        <span className="block truncate text-gray-700 dark:text-gray-300">
                          {acc.display_name || acc.remark || acc.account_id}
                        </span>
                        {(acc.display_name || acc.remark) && (
                          <span className="block truncate text-xs text-gray-400 dark:text-gray-500">
                            {acc.remark && acc.remark !== acc.display_name ? acc.remark : acc.account_id}
                          </span>
                        )}
                        {acc.owner && (
                          <span className="block truncate text-xs text-blue-400 dark:text-blue-500">
                            {acc.owner}
                          </span>
                        )}
                      </div>
                    </div>
                    {acc.connected ? (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleDisconnect(acc.account_id) }}
                        className="p-1 text-red-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30 rounded"
                        title="断开"
                      >
                        <LogOut className="w-3.5 h-3.5" />
                      </button>
                    ) : (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleConnect(acc.account_id) }}
                        disabled={!!connectingId}
                        className="p-1 text-green-500 hover:text-green-700 hover:bg-green-50 dark:hover:bg-green-900/30 rounded disabled:opacity-50"
                        title="连接"
                      >
                        {connectingId === acc.account_id ? (
                          <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <LogIn className="w-3.5 h-3.5" />
                        )}
                      </button>
                    )}
                  </div>
                  <div className="mt-1 flex items-center gap-1">
                    <span
                      className={`inline-block w-1.5 h-1.5 rounded-full ${
                        acc.connected ? 'bg-green-500' : acc.status !== 'active' ? 'bg-orange-400' : 'bg-gray-300'
                      }`}
                    />
                    <span className="text-xs text-gray-400">
                      {acc.connected ? '已连接' : acc.status !== 'active' ? '已禁用' : '未连接'}
                    </span>
                  </div>
                </div>
              ))}
              {accountHasMore && (
                <button
                  onClick={loadMoreAccounts}
                  disabled={loadingAccounts}
                  className="w-full py-2 text-xs text-blue-500 hover:bg-gray-50 dark:hover:bg-gray-700/30 disabled:opacity-50"
                >
                  {loadingAccounts ? '加载中...' : '加载更多'}
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* 中间：会话列表 */}
      <div className="w-72 flex-shrink-0 bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col">
        <div className="p-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
          <span className="font-medium text-sm text-gray-700 dark:text-gray-300">会话列表</span>
          {activeAccountId && (
            <button
              onClick={() => { setConvCursor(null); loadConversations(activeAccountId) }}
              className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded"
              title="刷新会话"
            >
              <RefreshCw className={`w-4 h-4 text-gray-500 ${loadingConvs ? 'animate-spin' : ''}`} />
            </button>
          )}
        </div>
        <div
          className="flex-1 overflow-y-auto"
          onScroll={(e) => {
            const el = e.currentTarget
            if (el.scrollHeight - el.scrollTop - el.clientHeight < 40 && convHasMore && !loadingConvs && activeAccountId) {
              loadConversations(activeAccountId, true)
            }
          }}
        >
          {!activeAccountId ? (
            <p className="text-center text-sm text-gray-400 py-12">请先选择账号</p>
          ) : loadingConvs && conversations.length === 0 ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
            </div>
          ) : conversations.length === 0 ? (
            <p className="text-center text-sm text-gray-400 py-12">
              {accounts.find((a) => a.account_id === activeAccountId)?.connected
                ? '暂无会话'
                : '请先连接账号'}
            </p>
          ) : (
            <>
              {conversations.map((conv, idx) => (
                <div
                  key={conv.cid || `conv-${idx}`}
                  className={`px-3 py-2.5 cursor-pointer border-b border-gray-100 dark:border-gray-700/50 transition-colors ${
                    activeCid === conv.cid
                      ? 'bg-blue-50 dark:bg-blue-900/20'
                      : 'hover:bg-gray-50 dark:hover:bg-gray-700/30'
                  }`}
                  onClick={() => handleSelectConversation(conv.cid)}
                >
                  <div className="flex items-center gap-2">
                    {conv.otherUserAvatar ? (
                      <img
                        src={conv.otherUserAvatar}
                        className="w-9 h-9 rounded-full flex-shrink-0 object-cover"
                        alt=""
                      />
                    ) : (
                      <div className="w-9 h-9 rounded-full bg-gray-200 dark:bg-gray-600 flex items-center justify-center flex-shrink-0">
                        <User className="w-5 h-5 text-gray-400" />
                      </div>
                    )}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-medium text-gray-800 dark:text-gray-200 truncate">
                          {conv.otherUserName || conv.otherUserId || '未知用户'}
                        </span>
                        <span className="text-xs text-gray-400 flex-shrink-0 ml-2">
                          {formatTime(conv.lastMessageTime)}
                        </span>
                      </div>
                      {conv.itemTitle && (
                        <div className="text-xs text-blue-400 truncate mt-0.5">
                          {conv.itemTitle}
                        </div>
                      )}
                      <div className="flex items-center justify-between mt-0.5">
                        <span className="text-xs text-gray-400 truncate">
                          {conv.lastMessageSummary || '暂无消息'}
                        </span>
                        {conv.unreadCount > 0 && (
                          <span className="ml-2 flex-shrink-0 bg-red-500 text-white text-xs rounded-full px-1.5 min-w-[18px] text-center">
                            {conv.unreadCount > 99 ? '99+' : conv.unreadCount}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
              {convHasMore && (
                <button
                  onClick={() => loadConversations(activeAccountId, true)}
                  disabled={loadingConvs}
                  className="w-full py-2 text-xs text-blue-500 hover:bg-gray-50 dark:hover:bg-gray-700/30 disabled:opacity-50"
                >
                  {loadingConvs ? '加载中...' : '加载更多'}
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* 右侧：聊天记录 */}
      <div className="flex-1 min-w-0 bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col">
        {/* 聊天头部 */}
        <div className="p-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
          <MessageCircle className="w-4 h-4 text-gray-500" />
          <span className="font-medium text-sm text-gray-700 dark:text-gray-300">
            {activeCid
              ? conversations.find((c) => c.cid === activeCid)?.otherUserName || '聊天记录'
              : '聊天记录'}
          </span>
          </div>
          {activeCid && (
            <button onClick={handleBlacklistCustomer} disabled={blacklisting} className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded border border-red-200 text-red-500 hover:bg-red-50 disabled:opacity-40" title={isOfficiallyBlocked ? '解除闲鱼官方黑名单' : '加入闲鱼官方黑名单'}>
              {blacklisting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Ban className="w-3.5 h-3.5" />}
              {isOfficiallyBlocked ? '解除黑名单' : '加入黑名单'}
            </button>
          )}
        </div>
        {/* 消息区域 */}
        <div ref={msgContainerRef} className="flex-1 overflow-y-auto p-4 space-y-3">
          {!activeCid ? (
            <p className="text-center text-sm text-gray-400 py-12">请选择一个会话查看聊天记录</p>
          ) : loadingMsgs && messages.length === 0 ? (
            <div className="flex justify-center py-12">
              <Loader2 className="w-5 h-5 animate-spin text-blue-500" />
            </div>
          ) : (
            <>
              {/* 加载更多历史 */}
              {msgHasMore && (
                <div className="text-center">
                  <button
                    onClick={() => loadMessages(activeAccountId, activeCid, true)}
                    disabled={loadingMsgs}
                    className="inline-flex items-center gap-1 text-xs text-blue-500 hover:underline disabled:opacity-50"
                  >
                    <ChevronUp className="w-3 h-3" />
                    {loadingMsgs ? '加载中...' : '加载更早的消息'}
                  </button>
                </div>
              )}
              {messages.map((msg, idx) => (
                <div
                  key={msg.messageId || idx}
                  className={`flex ${msg.isSelf ? 'justify-end' : 'justify-start'}`}
                >
                  <div className={`max-w-[70%] ${msg.isSelf ? 'order-1' : ''}`}>
                    {/* 发送者名称 */}
                    <div
                      className={`text-xs text-gray-400 mb-1 ${
                        msg.isSelf ? 'text-right' : 'text-left'
                      }`}
                    >
                      {msg.senderName}
                      <span className="ml-2">{formatTime(msg.time)}</span>
                    </div>
                    {/* 消息气泡（失败的本地消息在气泡前显示红色感叹号，点击查看原因） */}
                    <div className={`flex items-center gap-1.5 ${msg.isSelf ? 'flex-row-reverse' : ''}`}>
                      <div
                        className={`rounded-lg px-3 py-2 text-sm break-words ${
                          msg.isSelf
                            ? 'bg-blue-500 text-white'
                            : 'bg-gray-100 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
                        } ${msg.type === 'system' ? '!bg-gray-200 dark:!bg-gray-600 text-center text-gray-500 dark:text-gray-400 text-xs' : ''}`}
                      >
                        {msg.type === 'image' && msg.images.length > 0 ? (
                          <div className="space-y-1">
                            {msg.images.map((url, i) => (
                              <img
                                key={i}
                                src={url}
                                className="max-w-full rounded max-h-48 object-contain cursor-pointer hover:opacity-80 transition-opacity"
                                alt="图片消息"
                                onClick={() => setPreviewImage(url)}
                              />
                            ))}
                          </div>
                        ) : (
                          <span className="whitespace-pre-wrap">{msg.text}</span>
                        )}
                      </div>
                      {msg.isSelf && msg.failed && (
                        <button
                          type="button"
                          title="发送失败，点击查看原因"
                          onClick={() =>
                            addToast({ message: msg.failReason || '发送失败', type: 'error' })
                          }
                          className="flex-shrink-0 text-red-500 hover:text-red-600 transition-colors"
                        >
                          <AlertCircle className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                    {canRecallMessage(msg) && (
                      <div className="mt-1 text-right">
                        <button
                          onClick={() => handleRecallMessage(msg)}
                          disabled={!!recallingMessageId}
                          className="text-xs text-gray-400 hover:text-red-500 disabled:opacity-40"
                        >
                          {recallingMessageId === msg.messageId ? '撤回中...' : '撤回'}
                        </button>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </>
          )}
        </div>
        {/* 底部输入框 */}
        {activeCid && (
          <div className="p-3 border-t border-gray-200 dark:border-gray-700 flex items-center gap-2">
            <input
              ref={imageInputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={handleImageSelected}
            />
            <button
              type="button"
              onClick={handlePickImage}
              disabled={sending}
              title="发送图片"
              className="flex-shrink-0 flex items-center justify-center w-9 h-9 text-gray-500 dark:text-gray-300 border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <ImagePlus className="w-4 h-4" />
            </button>
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSendMessage()
                }
              }}
              placeholder="输入消息..."
              disabled={sending}
              className="flex-1 px-3 py-2 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-800 dark:text-gray-200 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:opacity-50"
            />
            <button
              onClick={handleSendMessage}
              disabled={sending || !inputText.trim()}
              className="flex items-center gap-1 px-4 py-2 text-sm font-medium text-white bg-blue-500 rounded-lg hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {sending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Send className="w-4 h-4" />
              )}
              发送
            </button>
          </div>
        )}
      </div>
      {/* 图片预览弹窗 */}
      {/* 右侧工作区：客户订单 + 快捷短语 */}
      <div className="w-80 flex-shrink-0 flex flex-col gap-3">
        <CustomerOrdersPanel
          activeCid={activeCid}
          orders={customerOrders}
          loading={loadingOrders}
          deliveringOrderNo={deliveringOrderNo}
          confirmingOrderNo={confirmingOrderNo}
          cancellingOrderNo={cancellingOrderNo}
          loadingOrderDetail={loadingOrderDetail}
          onSync={handleSyncOrders}
          onViewDetail={handleViewOrderDetail}
          onCancel={handleCancelOrder}
          onNoLogistics={handleNoLogisticsDelivery}
          onDeliver={handleDeliverOrder}
        />
        <QuickPhrasesPanel
          phrases={quickPhrases}
          activeCid={activeCid}
          sending={sending}
          editingPhraseId={editingPhraseId}
          phraseTitle={phraseTitle}
          phraseContent={phraseContent}
          savingPhrase={savingPhrase}
          onSend={(content) => sendMessageText(content)}
          onEdit={(phrase) => { setEditingPhraseId(phrase.id); setPhraseTitle(phrase.title); setPhraseContent(phrase.content) }}
          onDelete={handleDeletePhrase}
          onReset={resetPhraseForm}
          onTitleChange={setPhraseTitle}
          onContentChange={setPhraseContent}
          onSave={handleSavePhrase}
        />
      </div>
      <OrderDetailModal
        order={orderDetail}
        fallbackBuyerNick={activeConversation?.otherUserName}
        onClose={() => setOrderDetail(null)}
      />
      {previewImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70"
          onClick={() => setPreviewImage('')}
        >
          <button
            className="absolute top-4 right-4 text-white hover:text-gray-300 transition-colors"
            onClick={() => setPreviewImage('')}
          >
            <X className="w-8 h-8" />
          </button>
          <img
            src={previewImage}
            className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg"
            alt="预览"
            onClick={(e) => e.stopPropagation()}
          />
        </div>
      )}
      <ConfirmModal
        isOpen={!!confirmDialog}
        title={confirmDialog?.title}
        message={confirmDialog?.message || ''}
        confirmText={confirmDialog?.confirmText}
        type={confirmDialog?.type}
        onConfirm={() => closeConfirm(true)}
        onCancel={() => closeConfirm(false)}
      />
    </div>
  )
}

export default ChatNew
