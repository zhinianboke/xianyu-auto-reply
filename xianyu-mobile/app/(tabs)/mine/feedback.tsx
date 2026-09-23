import { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Alert,
  Modal,
  RefreshControl,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { Card, Button, Input, Loading, EmptyState, Badge } from '@/components/ui';
import { MessageCircle, Plus, X, Send, Image as ImageIcon } from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { useAuthStore } from '@/stores/auth';
import {
  getFeedbacks,
  getFeedbackStats,
  getFeedbackDetail,
  createFeedback,
  replyFeedback,
  resolveFeedback,
  unresolveFeedback,
  deleteFeedback,
  uploadFeedbackImage,
  type Feedback,
  type FeedbackDetail,
  type FeedbackType,
  type FeedbackStats,
} from '@/api/wrappers/misc';

/** 反馈类型选项（对齐 web：需求/BUG/其他） */
const TYPE_OPTIONS: { value: FeedbackType; label: string }[] = [
  { value: 'FEATURE', label: '需求' },
  { value: 'BUG', label: 'BUG' },
  { value: 'OTHER', label: '其他' },
];

/** 列表/详情中类型徽章的文案与配色 */
function typeMeta(t: FeedbackType): { label: string; variant: 'warning' | 'danger' | 'info' } {
  switch (t) {
    case 'FEATURE':
      return { label: '需求', variant: 'warning' };
    case 'BUG':
      return { label: 'BUG', variant: 'danger' };
    default:
      return { label: '其他', variant: 'info' };
  }
}

/** 将 ISO 时间字符串格式化为 `YYYY-MM-DD HH:mm` */
function formatTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function FeedbackScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const user = useAuthStore((s) => s.user);
  const isAdmin = !!user?.is_admin;

  const [feedbacks, setFeedbacks] = useState<Feedback[]>([]);
  const [stats, setStats] = useState<FeedbackStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // 创建反馈表单
  const [addVisible, setAddVisible] = useState(false);
  const [formType, setFormType] = useState<FeedbackType>('OTHER');
  const [formTitle, setFormTitle] = useState('');
  const [formContent, setFormContent] = useState('');
  const [formImages, setFormImages] = useState<string[]>([]);
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);

  // 详情（多轮对话）
  const [detailVisible, setDetailVisible] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detail, setDetail] = useState<FeedbackDetail | null>(null);
  const [replyText, setReplyText] = useState('');
  const [replying, setReplying] = useState(false);
  const msgListRef = useRef<FlatList<FeedbackDetail['messages'][number]>>(null);

  const load = useCallback(async () => {
    try {
      setRefreshing(true);
      const [list, s] = await Promise.all([
        getFeedbacks(),
        getFeedbackStats().catch(() => null),
      ]);
      setFeedbacks(list);
      if (s) setStats(s);
    } catch (e) {
      Alert.alert('加载失败', (e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // 新消息到达时滚动到底部
  useEffect(() => {
    if (!detail) return;
    const t = setTimeout(() => msgListRef.current?.scrollToEnd({ animated: true }), 60);
    return () => clearTimeout(t);
  }, [detail?.messages]);

  function openCreate() {
    setFormType('OTHER');
    setFormTitle('');
    setFormContent('');
    setFormImages([]);
    setAddVisible(true);
  }

  async function pickImage() {
    if (formImages.length >= 3) {
      Alert.alert('提示', '最多上传 3 张图片');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: false,
      quality: 0.8,
    });
    if (result.canceled || !result.assets || result.assets.length === 0) return;
    setUploading(true);
    try {
      const url = await uploadFeedbackImage(result.assets[0].uri);
      setFormImages((prev) => [...prev, url]);
    } catch (e) {
      Alert.alert('上传失败', (e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  function removeImage(index: number) {
    setFormImages((prev) => {
      const next = [...prev];
      next.splice(index, 1);
      return next;
    });
  }

  async function handleCreate() {
    if (!formTitle.trim()) {
      Alert.alert('提示', '请输入标题');
      return;
    }
    if (!formContent.trim()) {
      Alert.alert('提示', '请输入反馈内容');
      return;
    }
    setCreating(true);
    try {
      await createFeedback({
        title: formTitle.trim(),
        content: formContent.trim(),
        feedback_type: formType,
        images: formImages.length > 0 ? formImages : undefined,
      });
      setAddVisible(false);
      await load();
    } catch (e) {
      Alert.alert('提交失败', (e as Error).message);
    } finally {
      setCreating(false);
    }
  }

  async function openDetail(item: Feedback) {
    setDetailVisible(true);
    setDetailLoading(true);
    setReplyText('');
    setDetail(null);
    try {
      const d = await getFeedbackDetail(item.id);
      if (d) {
        setDetail(d);
      } else {
        Alert.alert('获取详情失败', '未找到该反馈');
        setDetailVisible(false);
      }
    } catch (e) {
      Alert.alert('获取详情失败', (e as Error).message);
      setDetailVisible(false);
    } finally {
      setDetailLoading(false);
    }
  }

  function closeDetail() {
    setDetailVisible(false);
    setDetail(null);
    setReplyText('');
  }

  async function handleReply() {
    if (!detail) return;
    if (!replyText.trim()) {
      Alert.alert('提示', '请输入回复内容');
      return;
    }
    setReplying(true);
    try {
      await replyFeedback(detail.id, replyText.trim());
      setReplyText('');
      // 重新拉取详情以展示最新消息历史
      const d = await getFeedbackDetail(detail.id);
      if (d) setDetail(d);
      await load();
    } catch (e) {
      Alert.alert('回复失败', (e as Error).message);
    } finally {
      setReplying(false);
    }
  }

  async function handleResolve(item: Feedback, resolved: boolean) {
    try {
      if (resolved) {
        await unresolveFeedback(item.id);
      } else {
        await resolveFeedback(item.id);
      }
      // 若详情打开则同步刷新
      if (detail && detail.id === item.id) {
        const d = await getFeedbackDetail(item.id);
        if (d) setDetail(d);
      }
      await load();
    } catch (e) {
      Alert.alert('操作失败', (e as Error).message);
    }
  }

  function handleDelete(item: Feedback) {
    Alert.alert('确认删除', '确定删除该反馈吗？删除后无法恢复。', [
      { text: '取消' },
      {
        text: '删除',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteFeedback(item.id);
            if (detail && detail.id === item.id) closeDetail();
            await load();
          } catch (e) {
            Alert.alert('删除失败', (e as Error).message);
          }
        },
      },
    ]);
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载反馈..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.actionRow}>
        <Button label="刷新" variant="secondary" onPress={load} style={styles.actionBtn} />
        <Button label="提交反馈" onPress={openCreate} style={styles.actionBtn} />
      </View>

      {stats && (
        <View style={styles.statsRow}>
          <View style={[styles.statCard, { backgroundColor: c.surface, borderColor: c.border }]}>
            <Text style={[styles.statValue, { color: c.text }]}>{stats.total}</Text>
            <Text style={[styles.statLabel, { color: c.textMuted }]}>总数</Text>
          </View>
          <View style={[styles.statCard, { backgroundColor: c.surface, borderColor: c.border }]}>
            <Text style={[styles.statValue, { color: c.warning }]}>{stats.pending}</Text>
            <Text style={[styles.statLabel, { color: c.textMuted }]}>待处理</Text>
          </View>
          <View style={[styles.statCard, { backgroundColor: c.surface, borderColor: c.border }]}>
            <Text style={[styles.statValue, { color: c.success }]}>{stats.resolved}</Text>
            <Text style={[styles.statLabel, { color: c.textMuted }]}>已解决</Text>
          </View>
        </View>
      )}

      <FlatList
        data={feedbacks}
        keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
        renderItem={({ item }) => {
          const tm = typeMeta(item.feedback_type);
          return (
            <Pressable onPress={() => openDetail(item)}>
              <Card style={styles.card}>
                <View style={styles.cardHeader}>
                  <View style={styles.badgeRow}>
                    <Badge label={tm.label} variant={tm.variant} />
                    <Badge
                      label={item.is_resolved ? '已解决' : '待处理'}
                      variant={item.is_resolved ? 'success' : 'warning'}
                    />
                    {item.message_count != null && item.message_count > 1 && (
                      <Badge label={`${item.message_count} 条`} variant="gray" />
                    )}
                  </View>
                  <Text style={[styles.time, { color: c.textMuted }]}>{formatTime(item.created_at)}</Text>
                </View>

                <Text style={[styles.title, { color: c.text }]} numberOfLines={1}>
                  {item.title || '无标题'}
                </Text>
                <Text style={[styles.content, { color: c.textSecondary }]} numberOfLines={2}>
                  {item.content}
                </Text>

                <View style={styles.metaRow}>
                  {item.images && item.images.length > 0 && (
                    <View style={styles.metaItem}>
                      <ImageIcon size={12} color={c.textMuted} />
                      <Text style={[styles.metaText, { color: c.textMuted }]}>{item.images.length} 图</Text>
                    </View>
                  )}
                  {item.cookie_id && (
                    <Text style={[styles.metaText, { color: c.textMuted }]}>账号 {item.cookie_id}</Text>
                  )}
                </View>
              </Card>
            </Pressable>
          );
        }}
        ListEmptyComponent={
          <EmptyState
            icon={MessageCircle}
            title="暂无反馈"
            message="提交需求、BUG 或建议后可在此查看处理进度"
            actionLabel="写反馈"
            onAction={openCreate}
          />
        }
        contentContainerStyle={styles.list}
      />

      {/* 创建反馈（底部抽屉） */}
      <Modal visible={addVisible} transparent animationType="slide" onRequestClose={() => setAddVisible(false)}>
        <KeyboardAvoidingView
          style={styles.sheetOverlay}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <Pressable style={styles.sheetBackdrop} onPress={() => setAddVisible(false)} />
          <View style={[styles.sheet, { backgroundColor: c.surface }]}>
            <View style={[styles.sheetHandle, { backgroundColor: c.border }]} />
            <View style={styles.sheetHeader}>
              <Text style={[styles.sheetTitle, { color: c.text }]}>提交反馈</Text>
              <Pressable onPress={() => setAddVisible(false)} hitSlop={8}>
                <Text style={[styles.sheetClose, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>

            <ScrollView
              style={styles.sheetScroll}
              contentContainerStyle={styles.sheetBody}
              keyboardShouldPersistTaps="handled"
            >
              {/* 反馈类型 */}
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>反馈类型 *</Text>
              <View style={styles.chipRow}>
                {TYPE_OPTIONS.map((o) => {
                  const on = formType === o.value;
                  return (
                    <Pressable
                      key={o.value}
                      onPress={() => setFormType(o.value)}
                      style={[
                        styles.chip,
                        {
                          backgroundColor: on ? c.primary : c.background,
                          borderColor: on ? c.primary : c.border,
                        },
                      ]}
                    >
                      <Text style={[styles.chipText, { color: on ? '#FFFFFF' : c.textSecondary }]}>
                        {o.label}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>

              {/* 标题 */}
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>标题 *</Text>
              <Input
                value={formTitle}
                onChangeText={setFormTitle}
                placeholder="简要描述您的反馈"
                maxLength={100}
                style={styles.titleInput}
              />

              {/* 内容 */}
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>内容 *</Text>
              <Input
                value={formContent}
                onChangeText={setFormContent}
                placeholder="详细描述您的需求或问题..."
                multiline
                style={styles.textarea}
              />

              {/* 图片 */}
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>图片（可选，最多 3 张）</Text>
              <View style={styles.imageGrid}>
                {formImages.map((url, index) => (
                  <View key={`${index}-${url}`} style={styles.imageCell}>
                    <Image source={{ uri: url }} style={styles.thumb} />
                    <Pressable
                      onPress={() => removeImage(index)}
                      style={[styles.imageDel, { backgroundColor: c.error }]}
                      hitSlop={8}
                    >
                      <X color="#FFFFFF" size={12} strokeWidth={3} />
                    </Pressable>
                  </View>
                ))}
                {formImages.length < 3 && (
                  <Pressable
                    onPress={pickImage}
                    style={[styles.imageAdd, { borderColor: c.border }]}
                    disabled={uploading}
                  >
                    {uploading ? (
                      <Text style={[styles.imageAddText, { color: c.textMuted }]}>上传中</Text>
                    ) : (
                      <>
                        <Plus color={c.textMuted} size={22} />
                        <Text style={[styles.imageAddText, { color: c.textMuted }]}>添加图片</Text>
                      </>
                    )}
                  </Pressable>
                )}
              </View>
            </ScrollView>

            <View style={[styles.sheetFooter, { borderTopColor: c.border }]}>
              <Button label="取消" variant="ghost" onPress={() => setAddVisible(false)} style={styles.sheetBtn} />
              <Button
                label="提交"
                onPress={handleCreate}
                loading={creating}
                disabled={creating}
                style={styles.sheetBtn}
              />
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* 反馈详情（多轮对话） */}
      <Modal visible={detailVisible} transparent animationType="slide" onRequestClose={closeDetail}>
        <KeyboardAvoidingView
          style={styles.sheetOverlay}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <Pressable style={styles.sheetBackdrop} onPress={closeDetail} />
          <View style={[styles.sheet, styles.detailSheet, { backgroundColor: c.surface }]}>
            <View style={[styles.sheetHandle, { backgroundColor: c.border }]} />
            {detailLoading ? (
              <View style={styles.detailLoadingWrap}>
                <Loading label="加载详情..." />
              </View>
            ) : detail ? (
              <>
                <View style={styles.sheetHeader}>
                  <View style={styles.detailHeaderLeft}>
                    <Text style={[styles.detailTitle, { color: c.text }]} numberOfLines={1}>
                      {detail.title || '无标题'}
                    </Text>
                    <View style={styles.badgeRow}>
                      <Badge label={typeMeta(detail.feedback_type).label} variant={typeMeta(detail.feedback_type).variant} />
                      <Badge
                        label={detail.is_resolved ? '已解决' : '待处理'}
                        variant={detail.is_resolved ? 'success' : 'warning'}
                      />
                    </View>
                  </View>
                  <Pressable onPress={closeDetail} hitSlop={8}>
                    <Text style={[styles.sheetClose, { color: c.textMuted }]}>✕</Text>
                  </Pressable>
                </View>

                <Text style={[styles.detailMeta, { color: c.textMuted }]}>
                  {formatTime(detail.created_at)}
                  {detail.cookie_id ? ` · 账号 ${detail.cookie_id}` : ''}
                </Text>

                {detail.images && detail.images.length > 0 && (
                  <View style={[styles.detailImages, { borderColor: c.border }]}>
                    {detail.images.map((img, idx) => (
                      <Image
                        key={`${idx}-${img}`}
                        source={{ uri: img }}
                        style={[styles.detailThumb, { borderColor: c.border }]}
                      />
                    ))}
                  </View>
                )}

                {/* 对话消息历史 */}
                <FlatList
                  ref={msgListRef}
                  data={detail.messages}
                  style={styles.msgFlatList}
                  keyExtractor={(m, i) => String(m.id ?? i)}
                  renderItem={({ item: msg }) => {
                    const adminMsg = msg.is_admin;
                    return (
                      <View style={[styles.msgRow, adminMsg ? styles.msgLeft : styles.msgRight]}>
                        <View
                          style={[
                            styles.bubble,
                            { backgroundColor: adminMsg ? c.primaryLight : c.surfaceAlt },
                          ]}
                        >
                          <Text style={[styles.msgSender, { color: adminMsg ? c.primary : c.textSecondary }]}>
                            {adminMsg ? '管理员' : '我'}
                          </Text>
                          <Text style={[styles.msgContent, { color: c.text }]}>{msg.content}</Text>
                          {msg.created_at ? (
                            <Text style={[styles.msgTime, { color: c.textMuted }]}>
                              {formatTime(msg.created_at)}
                            </Text>
                          ) : null}
                        </View>
                      </View>
                    );
                  }}
                  contentContainerStyle={styles.msgList}
                  onContentSizeChange={() => msgListRef.current?.scrollToEnd({ animated: true })}
                />

                {/* 回复输入 */}
                <View style={[styles.replyRow, { borderTopColor: c.border }]}>
                  <Input
                    value={replyText}
                    onChangeText={setReplyText}
                    placeholder="输入回复内容..."
                    style={styles.replyInput}
                    returnKeyType="send"
                    onSubmitEditing={handleReply}
                  />
                  <Button
                    label="发送"
                    onPress={handleReply}
                    loading={replying}
                    disabled={replying || !replyText.trim()}
                    style={styles.replyBtn}
                  />
                </View>

                {/* 管理员操作 */}
                {isAdmin && (
                  <View style={[styles.adminRow, { borderTopColor: c.border }]}>
                    <Button
                      label={detail.is_resolved ? '标记未解决' : '标记已解决'}
                      variant="secondary"
                      onPress={() => handleResolve(detail, detail.is_resolved)}
                      style={styles.adminBtn}
                    />
                    <Button
                      label="删除"
                      variant="danger"
                      onPress={() => handleDelete(detail)}
                      style={styles.adminBtn}
                    />
                  </View>
                )}
              </>
            ) : null}
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  actionRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  actionBtn: { minHeight: 40, paddingHorizontal: spacing.lg },

  statsRow: {
    flexDirection: 'row',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
    gap: spacing.sm,
  },
  statCard: {
    flex: 1,
    borderRadius: radius.md,
    borderWidth: 1,
    paddingVertical: spacing.md,
    alignItems: 'center',
    gap: 2,
  },
  statValue: { ...typography.heading },
  statLabel: { ...typography.small },

  list: { padding: spacing.lg, gap: spacing.md },
  card: { gap: spacing.xs },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.sm,
  },
  badgeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, flexShrink: 1 },
  time: { ...typography.small },
  title: { ...typography.body, fontWeight: '600' },
  content: { ...typography.caption },
  metaRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.md, marginTop: 2 },
  metaItem: { flexDirection: 'row', alignItems: 'center', gap: 3 },
  metaText: { ...typography.small },

  // 底部抽屉通用
  sheetOverlay: { flex: 1, justifyContent: 'flex-end' },
  sheetBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: {
    maxHeight: '88%',
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    overflow: 'hidden',
  },
  sheetHandle: { width: 36, height: 4, borderRadius: 2, alignSelf: 'center', marginTop: spacing.sm },
  sheetHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  sheetTitle: { ...typography.heading },
  sheetClose: { fontSize: 22, paddingHorizontal: spacing.xs },
  sheetScroll: { flex: 1, paddingHorizontal: spacing.lg },
  sheetBody: { paddingBottom: spacing.lg, gap: spacing.xs },
  sheetFooter: { flexDirection: 'row', gap: spacing.sm, padding: spacing.lg, borderTopWidth: 1 },
  sheetBtn: { flex: 1 },

  // 表单
  fieldLabel: { ...typography.caption, fontWeight: '500', marginTop: spacing.xs },
  titleInput: { minHeight: 44 },
  textarea: { minHeight: 100, textAlignVertical: 'top' },
  chipRow: { flexDirection: 'row', gap: spacing.sm },
  chip: {
    flex: 1,
    height: 36,
    borderRadius: radius.full,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipText: { fontSize: 13, fontWeight: '500' },

  // 图片网格
  imageGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.xs },
  imageCell: { width: 84, height: 84, position: 'relative' },
  thumb: { width: '100%', height: '100%', borderRadius: radius.md },
  imageDel: {
    position: 'absolute',
    top: -6,
    right: -6,
    width: 22,
    height: 22,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
  },
  imageAdd: {
    width: 84,
    height: 84,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'dashed',
    alignItems: 'center',
    justifyContent: 'center',
  },
  imageAddText: { ...typography.small, marginTop: 2 },

  // 详情
  detailSheet: { maxHeight: '92%' },
  detailLoadingWrap: { paddingVertical: 40 },
  detailHeaderLeft: { flex: 1, gap: spacing.xs, paddingRight: spacing.sm },
  detailTitle: { ...typography.body, fontWeight: '600' },
  detailMeta: { ...typography.small, paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  detailImages: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    marginHorizontal: spacing.lg,
    padding: spacing.sm,
    borderWidth: 1,
    borderRadius: radius.md,
    marginBottom: spacing.sm,
  },
  detailThumb: { width: 64, height: 64, borderRadius: radius.sm, borderWidth: 1 },

  // 对话消息
  msgFlatList: { flex: 1 },
  msgList: { padding: spacing.lg, gap: spacing.sm },
  msgRow: { flexDirection: 'row' },
  msgLeft: { justifyContent: 'flex-start' },
  msgRight: { justifyContent: 'flex-end' },
  bubble: {
    maxWidth: '82%',
    borderRadius: radius.lg,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    gap: 2,
  },
  msgSender: { ...typography.small, fontWeight: '600' },
  msgContent: { ...typography.caption },
  msgTime: { ...typography.micro, marginTop: 2 },

  // 回复输入
  replyRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.lg,
    borderTopWidth: 1,
  },
  replyInput: { flex: 1, minHeight: 44 },
  replyBtn: { minHeight: 44, paddingHorizontal: spacing.lg },

  // 管理员操作
  adminRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    padding: spacing.lg,
    borderTopWidth: 1,
  },
  adminBtn: { flex: 1, minHeight: 40 },
});
