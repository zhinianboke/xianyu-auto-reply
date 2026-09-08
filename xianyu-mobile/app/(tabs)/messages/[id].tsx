import { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TextInput,
  Pressable,
  KeyboardAvoidingView,
  Platform,
  Image,
  Modal,
  TouchableOpacity,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams } from 'expo-router';
import { useColorScheme } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import {
  Image as ImageIcon,
  MessageSquareText,
  Plus,
  ShoppingBag,
  Trash2,
  X,
} from 'lucide-react-native';
import { OrdersPanel } from '@/components/OrdersPanel';
import { BlacklistButton } from '@/components/BlacklistButton';
import { Loading, Button, Input } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { wsManager } from '@/lib/ws';
import {
  getMessages,
  sendMessage,
  sendImageMessage,
  recallMessage,
  getQuickPhrases,
  createQuickPhrase,
  updateQuickPhrase,
  deleteQuickPhrase,
  type ChatMessage,
  type QuickPhrase,
} from '@/api/wrappers/chat';

/** 消息撤回时间窗口（2 分钟） */
const RECALL_WINDOW_MS = 2 * 60 * 1000;

export default function ChatDetailScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const { id, account_id, name, buyer_id } = useLocalSearchParams<{
    id: string;
    account_id: string;
    name: string;
    buyer_id: string;
  }>();

  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputText, setInputText] = useState('');
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [showOrders, setShowOrders] = useState(false);

  // 快捷短语
  const [phrases, setPhrases] = useState<QuickPhrase[]>([]);
  const [phrasesLoading, setPhrasesLoading] = useState(false);
  const [showPhrases, setShowPhrases] = useState(false);
  const [phraseModalVisible, setPhraseModalVisible] = useState(false);
  const [editingPhrase, setEditingPhrase] = useState<QuickPhrase | null>(null);
  const [phraseTitle, setPhraseTitle] = useState('');
  const [phraseContent, setPhraseContent] = useState('');
  const [savingPhrase, setSavingPhrase] = useState(false);

  // 消息撤回操作菜单
  const [recallTarget, setRecallTarget] = useState<ChatMessage | null>(null);
  const [recalling, setRecalling] = useState(false);

  const listRef = useRef<FlatList>(null);
  // 头部插入历史消息时保持阅读位置（onContentSizeChange 不滚到底部）
  const prependingRef = useRef(false);
  const cursorRef = useRef<number | null>(null);
  const hasMoreRef = useRef(true);
  // 头部插入历史消息的并发锁（同步 ref，state 异步更新拦不住快速二次触发）
  const loadingMoreRef = useRef(false);

  const loadMessages = useCallback(
    async (append: boolean) => {
      if (!account_id || !id) return;
      if (append && !hasMoreRef.current) return;
      // 头部插入防抖：用同步 ref 拦截并发，避免在 cursor 更新前重复触发导致同一页历史被预插两遍
      if (append && loadingMoreRef.current) return;

      try {
        if (!append) setLoading(true);
        else {
          setLoadingMore(true);
          loadingMoreRef.current = true;
          // 标记本次是头部插入历史消息，onContentSizeChange 时保持阅读位置不滚底
          prependingRef.current = true;
        }

        const resp = await getMessages(
          account_id,
          id,
          append ? cursorRef.current : null,
        );

        if (append) {
          setMessages((prev) => [...resp.messages, ...prev]);
        } else {
          setMessages(resp.messages);
        }
        cursorRef.current = resp.nextCursor;
        hasMoreRef.current = resp.hasMore;
      } catch (e) {
        console.error('加载消息失败', e);
        prependingRef.current = false; // 出错时复位，避免卡死
      } finally {
        // 复位 loadingMore 同步锁
        loadingMoreRef.current = false;
        setLoading(false);
        setLoadingMore(false);
        // prependingRef 仅在"头部插入且响应为空"时在此复位（onContentSizeChange 不会触发）；
        // 非空时交由 onContentSizeChange 复位以保持阅读位置；加 400ms 兜底定时器防卡死
        if (append) {
          setTimeout(() => { prependingRef.current = false; }, 400);
        }
      }
    },
    [account_id, id],
  );

  useEffect(() => {
    loadMessages(false);
  }, [loadMessages]);

  // 设置当前活跃会话（用于 WS 消息时判断是否计未读）
  useEffect(() => {
    wsManager.setActiveCid(id);
    return () => wsManager.setActiveCid(null);
  }, [id]);

  // 订阅 WebSocket 实时消息
  useEffect(() => {
    if (!account_id || !id) return;
    const unsub = wsManager.onMessage((accountId, cid, message) => {
      if (accountId !== account_id || cid !== id) return;
      // 去重：自己发的消息可能已通过乐观更新添加
      setMessages((prev) => {
        if (prev.some((m) => m.messageId === message.messageId)) return prev;
        return [...prev, message];
      });
    });
    return unsub;
  }, [account_id, id]);

  // 加载快捷短语
  const loadPhrases = useCallback(async () => {
    setPhrasesLoading(true);
    try {
      const list = await getQuickPhrases();
      setPhrases(list);
    } catch (e) {
      console.error('加载快捷短语失败', e);
    } finally {
      setPhrasesLoading(false);
    }
  }, []);

  useEffect(() => {
    loadPhrases();
  }, [loadPhrases]);

  /** 标记某条乐观消息为发送失败 */
  function markFailed(messageId: string, reason: string) {
    setMessages((prev) =>
      prev.map((m) =>
        m.messageId === messageId ? { ...m, failed: true, failReason: reason } : m,
      ),
    );
  }

  async function handleSend() {
    if (!inputText.trim() || !account_id || !id || !buyer_id || sending) return;
    const text = inputText.trim();
    setInputText('');
    setSending(true);

    const optimisticMsg: ChatMessage = {
      messageId: `local-${Date.now()}`,
      senderId: 'self',
      senderName: '我',
      isSelf: true,
      type: 'text',
      text,
      images: [],
      time: Date.now(),
    };
    setMessages((prev) => [...prev, optimisticMsg]);

    try {
      const res = await sendMessage(account_id, id, buyer_id, text);
      if (!res.success) markFailed(optimisticMsg.messageId, res.message || '发送失败');
    } catch (e) {
      markFailed(optimisticMsg.messageId, (e as Error).message);
    } finally {
      setSending(false);
    }
  }

  /** 发送一条文本内容（用于快捷短语） */
  async function handleSendPhrase(content: string) {
    const text = content.trim();
    if (!text || !account_id || !id || !buyer_id || sending) return;
    setSending(true);

    const optimisticMsg: ChatMessage = {
      messageId: `local-${Date.now()}`,
      senderId: 'self',
      senderName: '我',
      isSelf: true,
      type: 'text',
      text,
      images: [],
      time: Date.now(),
    };
    setMessages((prev) => [...prev, optimisticMsg]);

    try {
      const res = await sendMessage(account_id, id, buyer_id, text);
      if (!res.success) markFailed(optimisticMsg.messageId, res.message || '发送失败');
    } catch (e) {
      markFailed(optimisticMsg.messageId, (e as Error).message);
    } finally {
      setSending(false);
    }
  }

  /** 选择并发送图片 */
  async function handleImagePick() {
    if (!account_id || !id || !buyer_id || sending) return;

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: false,
      quality: 0.8,
    });
    if (result.canceled || !result.assets || result.assets.length === 0) return;

    const asset = result.assets[0];
    const uri = asset.uri;
    setSending(true);

    const optimisticMsg: ChatMessage = {
      messageId: `local-img-${Date.now()}`,
      senderId: 'self',
      senderName: '我',
      isSelf: true,
      type: 'image',
      text: '',
      images: [uri],
      time: Date.now(),
    };
    setMessages((prev) => [...prev, optimisticMsg]);

    try {
      await sendImageMessage(account_id, id, buyer_id, uri);
    } catch (e) {
      markFailed(optimisticMsg.messageId, (e as Error).message);
    } finally {
      setSending(false);
    }
  }

  /** 长按自己的消息：弹出撤回操作菜单 */
  function handleMessageLongPress(message: ChatMessage) {
    // 仅自己发送的、非系统、未失败的消息可撤回
    if (!message.isSelf || message.type === 'system' || message.failed) return;
    if (Date.now() - message.time >= RECALL_WINDOW_MS) {
      Alert.alert('提示', '该消息已超过 2 分钟，无法撤回');
      return;
    }
    setRecallTarget(message);
  }

  /** 执行撤回 */
  async function handleRecall() {
    const target = recallTarget;
    if (!target || !account_id || recalling) return;
    setRecalling(true);
    try {
      await recallMessage(account_id, target.messageId, target.time);
      setMessages((prev) =>
        prev.map((m) =>
          m.messageId === target.messageId
            ? { ...m, type: 'system', text: '你撤回了一条消息', images: [] }
            : m,
        ),
      );
      setRecallTarget(null);
    } catch (e) {
      Alert.alert('撤回失败', (e as Error).message);
    } finally {
      setRecalling(false);
    }
  }

  /** 打开快捷短语编辑/新建弹窗 */
  function openPhraseEditor(phrase?: QuickPhrase) {
    setEditingPhrase(phrase ?? null);
    setPhraseTitle(phrase?.title ?? '');
    setPhraseContent(phrase?.content ?? '');
    setPhraseModalVisible(true);
  }

  /** 长按快捷短语：编辑/删除菜单 */
  function handlePhraseLongPress(phrase: QuickPhrase) {
    Alert.alert(phrase.title, undefined, [
      { text: '编辑', onPress: () => openPhraseEditor(phrase) },
      {
        text: '删除',
        style: 'destructive',
        onPress: () => handleDeletePhrase(phrase),
      },
      { text: '取消', style: 'cancel' },
    ]);
  }

  /** 保存（新建或更新）快捷短语 */
  async function savePhrase() {
    const title = phraseTitle.trim();
    const content = phraseContent.trim();
    if (!title || !content || savingPhrase) return;
    setSavingPhrase(true);
    try {
      if (editingPhrase) {
        await updateQuickPhrase(editingPhrase.id, title, content);
      } else {
        await createQuickPhrase(title, content);
      }
      setPhraseModalVisible(false);
      await loadPhrases();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setSavingPhrase(false);
    }
  }

  /** 删除快捷短语 */
  async function handleDeletePhrase(phrase: QuickPhrase) {
    Alert.alert('删除快捷短语', `确定删除"${phrase.title}"吗？`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteQuickPhrase(phrase.id);
            await loadPhrases();
          } catch (e) {
            Alert.alert('删除失败', (e as Error).message);
          }
        },
      },
    ]);
  }

  function formatTime(ts: number): string {
    if (!ts) return '';
    const d = new Date(ts);
    return `${d.getHours().toString().padStart(2, '0')}:${d
      .getMinutes()
      .toString()
      .padStart(2, '0')}`;
  }

  // 消息项渲染（useCallback 稳定引用，避免 WS 高频消息导致全列表重渲染）
  const renderMessage = useCallback(
    ({ item }: { item: ChatMessage }) => (
      <Pressable
        onLongPress={() => handleMessageLongPress(item)}
        delayLongPress={400}
        style={[styles.msgRow, item.isSelf ? styles.msgRowSelf : styles.msgRowOther]}
      >
        {!item.isSelf && (
          <View style={[styles.msgAvatar, { backgroundColor: c.primary }]}>
            <Text style={styles.msgAvatarText}>{(name || '?').charAt(0)}</Text>
          </View>
        )}
        <View
          style={[
            styles.msgBubble,
            {
              backgroundColor: item.isSelf ? c.primary : c.surface,
              borderColor: c.border,
            },
          ]}
        >
          {item.type === 'text' && (
            <Text style={[styles.msgText, { color: item.isSelf ? '#FFF' : c.text }]}>
              {item.text}
            </Text>
          )}
          {item.type === 'image' && item.images.length > 0 && (
            <TouchableOpacity
              onPress={() => item.images[0] && setPreviewImage(item.images[0])}
            >
              <Image
                source={{ uri: item.images[0] }}
                style={styles.msgImage}
                resizeMode="cover"
              />
            </TouchableOpacity>
          )}
          {item.type === 'system' && (
            <Text style={[styles.msgSystem, { color: c.textMuted }]}>{item.text}</Text>
          )}
          {item.failed && (
            <Text style={[styles.msgFailed, { color: c.error }]}>
              ⚠ {item.failReason || '发送失败'}
            </Text>
          )}
        </View>
      </Pressable>
    ),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [id, account_id, name, c.primary, c.surface, c.border, c.text, c.textMuted, c.error, recalling],
  );

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
        <Loading label="加载消息..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['bottom']}>
      <KeyboardAvoidingView
        style={styles.container}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        keyboardVerticalOffset={90}
      >
        {/* 聊天头部：买家名 + 黑名单 */}
        <View style={[styles.chatHeader, { backgroundColor: c.surface, borderBottomColor: c.border }]}>
          <Text style={[styles.chatHeaderName, { color: c.text }]} numberOfLines={1}>
            {name || '聊天'}
          </Text>
          {account_id && id && (
            <BlacklistButton accountId={account_id} cid={id} />
          )}
        </View>

        {hasMoreRef.current && messages.length > 0 && (
          <Pressable
            onPress={() => loadMessages(true)}
            style={styles.loadMoreBar}
          >
            <Text style={[styles.loadMoreText, { color: c.primary }]}>
              {loadingMore ? '加载中...' : '加载更早的消息'}
            </Text>
          </Pressable>
        )}

        <FlatList
          ref={listRef}
          data={messages}
          keyExtractor={(item) => item.messageId}
          renderItem={renderMessage}
          // 聊天消息频繁追加，保留稍大的渲染窗口保证滚动流畅
          windowSize={11}
          contentContainerStyle={styles.msgList}
          onContentSizeChange={() => {
            if (prependingRef.current) {
              // 历史消息头部插入完成，保持当前阅读位置
              prependingRef.current = false;
              return;
            }
            listRef.current?.scrollToEnd({ animated: true });
          }}
          ListEmptyComponent={
            <View style={styles.empty}>
              <Text style={[styles.emptyText, { color: c.textMuted }]}>
                暂无消息，发送第一条消息吧
              </Text>
            </View>
          }
        />

        {/* 快捷短语面板 */}
        {showPhrases && (
          <View
            style={[styles.phrasePanel, { backgroundColor: c.surface, borderTopColor: c.border }]}
          >
            {phrasesLoading && phrases.length === 0 ? (
              <Text style={[styles.phraseEmpty, { color: c.textMuted }]}>加载中...</Text>
            ) : phrases.length === 0 ? (
              <Pressable
                style={[styles.phraseAddFirst, { borderColor: c.border }]}
                onPress={() => openPhraseEditor()}
              >
                <Plus size={16} color={c.primary} />
                <Text style={[styles.phraseAddFirstText, { color: c.primary }]}>
                  添加快捷短语
                </Text>
              </Pressable>
            ) : (
              <FlatList
                horizontal
                style={styles.phraseScroll}
                data={phrases}
                keyExtractor={(p) => String(p.id)}
                showsHorizontalScrollIndicator={false}
                contentContainerStyle={styles.phraseList}
                ListFooterComponent={
                  <Pressable
                    style={[styles.phraseAddChip, { borderColor: c.border }]}
                    onPress={() => openPhraseEditor()}
                  >
                    <Plus size={16} color={c.textSecondary} />
                  </Pressable>
                }
                renderItem={({ item: p }) => (
                  <TouchableOpacity
                    style={[styles.phraseChip, { backgroundColor: c.background, borderColor: c.border }]}
                    onPress={() => handleSendPhrase(p.content)}
                    onLongPress={() => handlePhraseLongPress(p)}
                    delayLongPress={400}
                  >
                    <Text style={[styles.phraseChipTitle, { color: c.text }]} numberOfLines={1}>
                      {p.title}
                    </Text>
                    <Text style={[styles.phraseChipContent, { color: c.textMuted }]} numberOfLines={1}>
                      {p.content}
                    </Text>
                  </TouchableOpacity>
                )}
              />
            )}
          </View>
        )}

        <View style={[styles.inputBar, { backgroundColor: c.surface, borderTopColor: c.border }]}>
          {/* 图片发送按钮 */}
          <Pressable
            onPress={handleImagePick}
            disabled={sending}
            style={({ pressed }) => [
              styles.iconBtn,
              { opacity: pressed || sending ? 0.5 : 1 },
            ]}
          >
            <ImageIcon size={24} color={c.text} />
          </Pressable>

          {/* 快捷短语展开/收起 */}
          <Pressable
            onPress={() => setShowPhrases((v) => !v)}
            style={({ pressed }) => [
              styles.iconBtn,
              {
                backgroundColor: showPhrases ? c.primaryLight : 'transparent',
                opacity: pressed ? 0.6 : 1,
              },
            ]}
          >
            <MessageSquareText size={24} color={showPhrases ? c.primary : c.text} />
          </Pressable>

          {/* 客户订单面板 */}
          <Pressable
            onPress={() => setShowOrders(true)}
            style={({ pressed }) => [
              styles.iconBtn,
              { opacity: pressed ? 0.6 : 1 },
            ]}
          >
            <ShoppingBag size={24} color={c.text} />
          </Pressable>

          <TextInput
            value={inputText}
            onChangeText={setInputText}
            placeholder="输入消息..."
            placeholderTextColor={c.textMuted}
            style={[styles.input, { color: c.text, backgroundColor: c.background }]}
            multiline
            maxLength={500}
            editable={!sending}
          />
          <Pressable
            onPress={handleSend}
            disabled={!inputText.trim() || sending}
            style={[styles.sendBtn, { backgroundColor: inputText.trim() ? c.primary : c.border }]}
          >
            {sending ? (
              <ActivityIndicator color="#FFF" />
            ) : (
              <Text style={styles.sendBtnText}>发送</Text>
            )}
          </Pressable>
        </View>
      </KeyboardAvoidingView>

      {/* 图片预览 */}
      <Modal visible={previewImage !== null} transparent onRequestClose={() => setPreviewImage(null)}>
        <View style={styles.previewOverlay}>
          <TouchableOpacity style={styles.previewClose} onPress={() => setPreviewImage(null)}>
            <Text style={styles.previewCloseText}>✕</Text>
          </TouchableOpacity>
          {previewImage && (
            <Image
              source={{ uri: previewImage }}
              style={styles.previewImage}
              resizeMode="contain"
            />
          )}
        </View>
      </Modal>

      {/* 客户订单面板 */}
      <Modal visible={showOrders} animationType="slide" onRequestClose={() => setShowOrders(false)}>
        <View style={[styles.ordersModal, { backgroundColor: c.background }]}>
          <View style={[styles.ordersHeader, { backgroundColor: c.surface, borderBottomColor: c.border }]}>
            <Text style={[styles.ordersTitle, { color: c.text }]}>客户订单</Text>
            <Pressable onPress={() => setShowOrders(false)} style={styles.ordersClose}>
              <X size={24} color={c.text} />
            </Pressable>
          </View>
          {account_id && buyer_id ? (
            <OrdersPanel accountId={account_id} buyerId={buyer_id} />
          ) : (
            <View style={styles.empty}><Text style={{ color: c.textMuted }}>无订单信息</Text></View>
          )}
        </View>
      </Modal>

      {/* 消息撤回操作菜单 */}
      <Modal
        visible={recallTarget !== null}
        transparent
        animationType="slide"
        onRequestClose={() => (recalling ? undefined : setRecallTarget(null))}
      >
        <Pressable style={styles.sheetOverlay} onPress={() => (recalling ? undefined : setRecallTarget(null))}>
          <Pressable style={[styles.sheet, { backgroundColor: c.surface }]} onPress={() => {}}>
            <View style={[styles.sheetHandle, { backgroundColor: c.border }]} />
            <Pressable
              style={[styles.sheetItem, styles.sheetItemBorder, { borderColor: c.border }]}
              onPress={handleRecall}
              disabled={recalling}
            >
              {recalling ? (
                <ActivityIndicator color={c.error} />
              ) : (
                <Text style={[styles.sheetItemText, { color: c.error }]}>撤回</Text>
              )}
            </Pressable>
            <Pressable
              style={styles.sheetItem}
              onPress={() => setRecallTarget(null)}
              disabled={recalling}
            >
              <Text style={[styles.sheetItemText, { color: c.text }]}>取消</Text>
            </Pressable>
          </Pressable>
        </Pressable>
      </Modal>

      {/* 快捷短语编辑/新建弹窗 */}
      <Modal
        visible={phraseModalVisible}
        transparent
        animationType="slide"
        onRequestClose={() => setPhraseModalVisible(false)}
      >
        <Pressable style={styles.sheetOverlay} onPress={() => setPhraseModalVisible(false)}>
          <Pressable
            style={[styles.sheet, styles.phraseEditorSheet, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            <View style={styles.phraseEditorHeader}>
              <Text style={[styles.phraseEditorTitle, { color: c.text }]}>
                {editingPhrase ? '编辑短语' : '新建短语'}
              </Text>
              <Pressable onPress={() => setPhraseModalVisible(false)} disabled={savingPhrase}>
                <X size={20} color={c.text} />
              </Pressable>
            </View>

            <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>标题</Text>
            <Input
              value={phraseTitle}
              onChangeText={setPhraseTitle}
              placeholder="短语标题（如：包邮）"
              maxLength={20}
              editable={!savingPhrase}
            />

            <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>内容</Text>
            <Input
              value={phraseContent}
              onChangeText={setPhraseContent}
              placeholder="短语内容（如：亲，这款包邮哦~）"
              multiline
              maxLength={200}
              editable={!savingPhrase}
              style={styles.phraseContentInput}
            />

            <View style={styles.phraseEditorActions}>
              {editingPhrase && (
                <Pressable
                  style={[styles.editorDangerBtn, { borderColor: c.error }]}
                  onPress={() => {
                    const target = editingPhrase;
                    setPhraseModalVisible(false);
                    if (target) handleDeletePhrase(target);
                  }}
                  disabled={savingPhrase}
                >
                  <Trash2 size={16} color={c.error} />
                  <Text style={[styles.editorDangerText, { color: c.error }]}>删除</Text>
                </Pressable>
              )}
              <View style={{ flex: 1 }} />
              <Button
                label="取消"
                variant="ghost"
                onPress={() => setPhraseModalVisible(false)}
                disabled={savingPhrase}
              />
              <Button
                label={savingPhrase ? '保存中...' : '保存'}
                onPress={savePhrase}
                disabled={savingPhrase || !phraseTitle.trim() || !phraseContent.trim()}
              />
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  loadMoreBar: { paddingVertical: spacing.sm, alignItems: 'center' },
  chatHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderBottomWidth: 1 },
  chatHeaderName: { ...typography.heading, flex: 1, marginRight: spacing.sm },
  loadMoreText: { ...typography.caption },
  msgList: { padding: spacing.md, gap: spacing.sm },
  msgRow: { flexDirection: 'row', gap: spacing.sm, maxWidth: '100%' },
  msgRowSelf: { justifyContent: 'flex-end' },
  msgRowOther: { justifyContent: 'flex-start' },
  msgAvatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  msgAvatarText: { color: '#FFF', fontSize: 14, fontWeight: '600' },
  msgBubble: {
    maxWidth: '75%',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  msgText: { ...typography.body },
  msgImage: { width: 200, height: 200, borderRadius: radius.sm },
  msgSystem: { ...typography.caption, textAlign: 'center' },
  msgFailed: { ...typography.small, marginTop: spacing.xs },
  // 快捷短语面板
  phrasePanel: {
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
  },
  // 横向列表必须给显式高度：默认 flexGrow:1 会撑满整屏；仅 flexGrow:0 时安卓初始测量会把文字压扁
  phraseScroll: { flexGrow: 0, minHeight: 64 },
  phraseList: { paddingHorizontal: spacing.md, gap: spacing.sm, alignItems: 'center' },
  phraseEmpty: { ...typography.body, textAlign: 'center', paddingVertical: spacing.md },
  phraseAddFirst: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.xs,
    marginHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'dashed',
  },
  phraseAddFirstText: { ...typography.body, fontWeight: '600' },
  phraseChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.lg,
    borderWidth: 1,
    minWidth: 88,
    maxWidth: 160,
  },
  phraseChipTitle: { ...typography.caption, fontWeight: '600', marginBottom: 2 },
  phraseChipContent: { ...typography.small },
  phraseAddChip: {
    width: 40,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.lg,
    borderWidth: 1,
    borderStyle: 'dashed',
  },
  // 输入栏
  inputBar: {
    flexDirection: 'row',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    gap: spacing.sm,
    borderTopWidth: 1,
    alignItems: 'flex-end',
  },
  iconBtn: {
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.md,
  },
  input: {
    ...typography.body,
    flex: 1,
    minHeight: 36,
    maxHeight: 100,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  sendBtn: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    minHeight: 36,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendBtnText: { color: '#FFF', fontWeight: '600' },
  empty: { alignItems: 'center', justifyContent: 'center', paddingVertical: 60 },
  emptyText: { ...typography.body },
  // 图片预览
  previewOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.9)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  previewClose: { position: 'absolute', top: 50, right: 20, zIndex: 1 },
  previewCloseText: { color: '#FFF', fontSize: 28 },
  previewImage: { width: '90%', height: '70%' },
  // 操作菜单（底部弹窗）
  sheetOverlay: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  sheet: {
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    paddingBottom: spacing.xl,
  },
  sheetHandle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    alignSelf: 'center',
    marginTop: spacing.sm,
    marginBottom: spacing.xs,
  },
  sheetItem: {
    paddingVertical: spacing.lg,
    alignItems: 'center',
  },
  sheetItemBorder: {
    borderTopWidth: 0,
    borderBottomWidth: 1,
  },
  sheetItemText: { ...typography.body, fontWeight: '600' },
  // 快捷短语编辑弹窗
  phraseEditorSheet: {
    padding: spacing.lg,
    maxHeight: '80%',
  },
  phraseEditorHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.md,
  },
  phraseEditorTitle: { ...typography.heading },
  fieldLabel: {
    ...typography.small,
    marginTop: spacing.sm,
    marginBottom: spacing.xs,
  },
  phraseContentInput: {
    minHeight: 72,
    maxHeight: 120,
    textAlignVertical: 'top',
  },
  phraseEditorActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginTop: spacing.lg,
  },
  editorDangerBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  editorDangerText: { ...typography.body, fontWeight: '600' },
  ordersModal: { flex: 1, marginTop: 50 },
  ordersHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: spacing.lg, paddingVertical: spacing.md, borderBottomWidth: 1 },
  ordersTitle: { ...typography.title },
  ordersClose: { padding: spacing.sm },
});
