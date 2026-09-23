import { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  RefreshControl,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, useFocusEffect } from 'expo-router';
import { useColorScheme } from 'react-native';
import { EmptyState, Loading, SwipeableRow } from '@/components/ui';
import { MessageCircle, UserX, Search } from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { useConfigStore } from '@/stores/config';
import { useAuthStore } from '@/stores/auth';
import { getServerUrl, getToken } from '@/lib/config';
import { wsManager } from '@/lib/ws';
import {
  getChatAccounts,
  getConversations,
  connectAccount,
  type ChatAccount,
  type Conversation,
  type ChatMessage,
} from '@/api/wrappers/chat';

export default function MessagesScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();
  const serverUrl = useConfigStore((s) => s.serverUrl);
  const token = useAuthStore((s) => s.token);

  const [accounts, setAccounts] = useState<ChatAccount[]>([]);
  const [selectedAccount, setSelectedAccount] = useState<ChatAccount | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const cursorRef = useRef<number | null>(null);
  const hasMoreRef = useRef(true);
  // 会话请求序号：切账号并发时丢弃过期响应
  const convSeqRef = useRef(0);

  const loadAccounts = useCallback(async () => {
    try {
      const list = await getChatAccounts();
      setAccounts(list);
      setSelectedAccount((prev) => {
        if (prev) return prev; // 已有选中账号，不覆盖
        return list.length > 0 ? list[0] : null;
      });
    } catch (e) {
      console.error('加载账号失败', e);
    }
  }, []);

  const loadConversations = useCallback(
    async (append: boolean) => {
      if (!selectedAccount) return;
      if (append && !hasMoreRef.current) return;
      // 请求序号：快速切账号 A→B 时丢弃 A 的过期响应，避免 A 的会话显示在 B 名下
      const seq = ++convSeqRef.current;
      const targetAccountId = selectedAccount.account_id;

      try {
        if (!append) setRefreshing(true);
        else setLoadingMore(true);

        const resp = await getConversations(
          targetAccountId,
          append ? cursorRef.current : null,
        );
        if (convSeqRef.current !== seq) return; // 已切到别的账号，丢弃本次响应

        if (append) {
          setConversations((prev) => [...prev, ...resp.conversations]);
        } else {
          setConversations(resp.conversations);
        }
        cursorRef.current = resp.nextCursor;
        hasMoreRef.current = resp.hasMore;
      } catch (e) {
        if (convSeqRef.current === seq) console.error('加载会话失败', e);
      } finally {
        if (convSeqRef.current === seq) {
          setLoading(false);
          setRefreshing(false);
          setLoadingMore(false);
        }
      }
    },
    [selectedAccount],
  );

  // 配置并连接 WebSocket
  useEffect(() => {
    if (!serverUrl || !token) return;
    const url = serverUrl;
    wsManager.configure(url, token);
  }, [serverUrl, token]);

  // 选中账号时连接 WS
  useEffect(() => {
    if (!selectedAccount || !serverUrl || !token) return;
    setWsConnected(false);
    wsManager.connect(selectedAccount.account_id);

    const unsub = wsManager.onStatusChange((accountId, connected) => {
      if (accountId === selectedAccount.account_id) {
        setWsConnected(connected);
      }
    });
    return () => {
      unsub();
      wsManager.disconnect(selectedAccount.account_id);
    };
  }, [selectedAccount, serverUrl, token]);

  // 监听 WS 新消息 → 更新会话列表
  useEffect(() => {
    const unsub = wsManager.onMessage((accountId, cid, message) => {
      if (!selectedAccount || accountId !== selectedAccount.account_id) return;

      setConversations((prev) => {
        const idx = prev.findIndex((conv) => conv.cid === cid);
        if (idx < 0) {
          // 新会话：在消息列表中不存在，创建一条最小化会话条目
          const newConv: Conversation = {
            cid,
            rawCid: cid,
            otherUserId: message.senderId || '',
            otherUserName: message.senderName || message.senderId || '未知用户',
            otherUserAvatar: '',
            itemTitle: '',
            lastMessageSummary:
              message.type === 'image' ? '[图片]' :
              message.type === 'card' ? '[卡片]' :
              message.text,
            lastMessageTime: message.time,
            unreadCount: cid === wsManager.getActiveCid() ? 0 : 1,
          };
          return [newConv, ...prev];
        }

        const conv = prev[idx];
        const updated: Conversation = {
          ...conv,
          lastMessageSummary:
            message.type === 'image' ? '[图片]' :
            message.type === 'card' ? '[卡片]' :
            message.text,
          lastMessageTime: message.time,
          unreadCount: cid === wsManager.getActiveCid() ? 0 : conv.unreadCount + 1,
        };
        // 移到最前
        return [updated, ...prev.filter((_, i) => i !== idx)];
      });
    });
    return unsub;
  }, [selectedAccount]);

  // 切回消息 tab 时重新加载账号列表（用户可能在账号管理添加了新账号）
  useFocusEffect(useCallback(() => { loadAccounts(); }, [loadAccounts]));

  useEffect(() => {
    if (selectedAccount) {
      setLoading(true);
      cursorRef.current = null;
      hasMoreRef.current = true;
      loadConversations(false);
    } else {
      // 无聊天账号时收口 loading，否则新用户卡在"加载会话..."转圈、空态引导不可达
      setLoading(false);
    }
  }, [selectedAccount, loadConversations]);

  async function handleSelectAccount(acc: ChatAccount) {
    if (!acc.connected) {
      try {
        await connectAccount(acc.account_id);
      } catch (e) {
        console.error('连接失败', e);
        return;
      }
    }
    // 先断开旧账号 WS
    if (selectedAccount) {
      wsManager.disconnect(selectedAccount.account_id);
    }
    setSelectedAccount(acc);
  }

  function handleOpenConversation(conv: Conversation) {
    // 清除该会话未读
    setConversations((prev) =>
      prev.map((c) => (c.cid === conv.cid ? { ...c, unreadCount: 0 } : c)),
    );
    wsManager.setActiveCid(conv.cid);

    router.push({
      pathname: '/(tabs)/messages/[id]',
      params: {
        id: conv.cid,
        account_id: selectedAccount?.account_id ?? '',
        name: conv.otherUserName || conv.otherUserId,
        buyer_id: conv.otherUserId,
      },
    });
  }

  function formatTime(ts: number): string {
    if (!ts) return '';
    const d = new Date(ts);
    const now = new Date();
    const diff = now.getTime() - d.getTime();
    if (diff < 60000) return '刚刚';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
    if (d.toDateString() === now.toDateString()) {
      return `${d.getHours().toString().padStart(2, '0')}:${d
        .getMinutes()
        .toString()
        .padStart(2, '0')}`;
    }
    return `${d.getMonth() + 1}/${d.getDate()}`;
  }

  // 会话项渲染（useCallback 稳定引用，避免 WS 高频消息导致全列表重渲染）
  const renderConversation = useCallback(
    ({ item }: { item: Conversation }) => {
      const unread = item.unreadCount > 0;
      return (
        <SwipeableRow
          onPress={() => handleOpenConversation(item)}
          actions={[
            { label: '已读', bg: c.info, onPress: () => setConversations((prev) => prev.map((cv) => (cv.cid === item.cid ? { ...cv, unreadCount: 0 } : cv))) },
            { label: '删除', bg: c.error, onPress: () => setConversations((prev) => prev.filter((cv) => cv.cid !== item.cid)) },
          ]}
        >
          <View style={[styles.convItem, { backgroundColor: c.surface }]}>
            <View style={{ width: 3, alignSelf: 'stretch', backgroundColor: unread ? c.primary : 'transparent', marginRight: spacing.xs }} />
            <View style={styles.convAvatar}>
              <Text style={styles.convAvatarText}>
                {(item.otherUserName || item.otherUserId || '?').charAt(0)}
              </Text>
            </View>
            <View style={styles.convContent}>
              <View style={styles.convHeader}>
                <Text style={[styles.convName, { color: c.text }, unread && { fontWeight: '700' }]} numberOfLines={1}>
                  {item.otherUserName || item.otherUserId}
                </Text>
                <Text style={[styles.convTime, { color: unread ? c.primary : c.textMuted }]}>
                  {formatTime(item.lastMessageTime)}
                </Text>
              </View>
              <View style={styles.convFooter}>
                <Text style={[styles.convPreview, { color: c.textSecondary }]} numberOfLines={1}>
                  {item.itemTitle ? `[${item.itemTitle}] ` : ''}
                  {item.lastMessageSummary || '暂无消息'}
                </Text>
                {unread && (
                  <View style={[styles.unreadBadge, { backgroundColor: c.primary }]}>
                    <Text style={styles.unreadText}>
                      {item.unreadCount > 99 ? '99+' : item.unreadCount}
                    </Text>
                  </View>
                )}
              </View>
            </View>
          </View>
        </SwipeableRow>
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [selectedAccount?.account_id, c.primary, c.primaryLight, c.surface, c.text, c.textMuted, c.textSecondary, c.error, c.info],
  );

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
        <Loading label="加载会话..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: c.text }]}>消息</Text>
      </View>
      {/* 搜索栏 */}
      <View style={[styles.searchBar, { backgroundColor: c.surface, borderBottomColor: c.border }]}>
        <Search size={16} stroke={c.textMuted} />
        <TextInput
          value={searchQuery}
          onChangeText={setSearchQuery}
          placeholder="搜索会话/买家"
          placeholderTextColor={c.textMuted}
          style={[styles.searchInput, { color: c.text }]}
        />
        {searchQuery ? (
          <Pressable onPress={() => setSearchQuery('')} hitSlop={8}>
            <Text style={{ color: c.textMuted, fontSize: 18 }}>×</Text>
          </Pressable>
        ) : null}
      </View>
      {accounts.length > 0 && (
        <>
        <FlatList
          horizontal
          style={styles.accountScroll}
          data={accounts}
          keyExtractor={(item) => item.account_id}
          renderItem={({ item }) => (
            <Pressable
              onPress={() => handleSelectAccount(item)}
              style={[
                styles.accountChip,
                {
                  backgroundColor:
                    selectedAccount?.account_id === item.account_id ? c.primary : c.surface,
                  borderColor: c.border,
                },
              ]}
            >
              <Text
                style={[
                  styles.accountChipText,
                  {
                    color:
                      selectedAccount?.account_id === item.account_id ? '#FFF' : c.text,
                  },
                ]}
                numberOfLines={1}
              >
                {item.remark || item.display_name || item.account_id}
              </Text>
              <View
                style={[
                  styles.statusDot,
                  { backgroundColor: item.connected ? c.success : c.textMuted },
                ]}
              />
            </Pressable>
          )}
          contentContainerStyle={styles.accountList}
          showsHorizontalScrollIndicator={false}
        />
        {selectedAccount && (
          <View style={[styles.wsBar, { backgroundColor: c.surface, borderBottomColor: c.border }]}>
            <View style={[styles.wsDot, { backgroundColor: wsConnected ? c.success : c.textMuted }]} />
            <Text style={[styles.wsText, { color: c.textSecondary }]}>
              {wsConnected ? '实时连接中' : '离线（消息需手动刷新）'}
            </Text>
          </View>
        )}
        </>
      )}

      <FlatList
        data={searchQuery.trim()
          ? conversations.filter((c) => (c.otherUserName || c.otherUserId || '').includes(searchQuery.trim()) || (c.lastMessageSummary || '').includes(searchQuery.trim()))
          : conversations}
        keyExtractor={(item) => item.cid}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadConversations(false)} />}
        onEndReached={() => loadConversations(true)}
        onEndReachedThreshold={0.3}
        renderItem={renderConversation}
        ListEmptyComponent={
          accounts.length === 0 ? (
            <EmptyState
              icon={UserX}
              title="没有可用账号"
              message="请先在「我的」页面添加并连接闲鱼账号"
            />
          ) : (
            <EmptyState
              icon={MessageCircle}
              title="暂无会话"
              message="收到新消息后会显示在这里"
            />
          )
        }
        ListFooterComponent={
          loadingMore ? (
            <Text style={[styles.loadingMore, { color: c.textMuted }]}>加载中...</Text>
          ) : null
        }
        contentContainerStyle={conversations.length === 0 ? styles.emptyList : styles.convList}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  title: { ...typography.title },
  // 搜索栏
  searchBar: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingVertical: 8, borderBottomWidth: 1 },
  searchInput: { flex: 1, fontSize: 14, paddingVertical: 4 },
  // 横向列表必须给显式高度：默认 flexGrow:1 会撑满整屏；仅 flexGrow:0 时安卓初始测量会把文字压扁
  accountScroll: { flexGrow: 0, minHeight: 54 },
  accountList: { padding: spacing.sm, gap: spacing.sm, alignItems: 'center' },
  accountChip: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.xl,
    borderWidth: 1,
    gap: spacing.xs,
  },
  accountChipText: { ...typography.caption, maxWidth: 120 },
  statusDot: { width: 6, height: 6, borderRadius: 3 },
  wsBar: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingHorizontal: spacing.lg, paddingVertical: spacing.xs, borderBottomWidth: 1 },
  wsDot: { width: 8, height: 8, borderRadius: 4 },
  wsText: { ...typography.small },
  convItem: {
    flexDirection: 'row',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    alignItems: 'center',
  },
  convAvatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: '#3B82F6',
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.md,
  },
  convAvatarText: { color: '#FFF', fontSize: 18, fontWeight: '600' },
  convContent: { flex: 1, gap: spacing.xs },
  convHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  convName: { ...typography.body, fontWeight: '600', flex: 1, marginRight: spacing.sm },
  convTime: { ...typography.small },
  convFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  convPreview: { ...typography.caption, flex: 1, marginRight: spacing.sm },
  unreadBadge: {
    minWidth: 18,
    height: 18,
    borderRadius: 9,
    paddingHorizontal: 5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  unreadText: { color: '#FFF', fontSize: 10, fontWeight: '600' },
  empty: { alignItems: 'center', justifyContent: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  emptyList: { flex: 1, justifyContent: 'center' },
  // 底部留白避让 tab 栏，避免最后一条会话被遮挡
  convList: { paddingBottom: 80 },
  loadingMore: { textAlign: 'center', padding: spacing.md },
});
