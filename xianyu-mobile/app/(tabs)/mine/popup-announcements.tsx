import { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Alert,
  RefreshControl,
  Switch,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Image } from 'lucide-react-native';
import { Card, Button, Input, Loading, EmptyState, FormModal } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { useAuthStore } from '@/stores/auth';
import {
  getPopupAnnouncements,
  createPopupAnnouncement,
  updatePopupAnnouncement,
  togglePopupAnnouncement,
  deletePopupAnnouncement,
  type PopupAnnouncement,
} from '@/api/wrappers/popup-announcements';

/** 将 ISO/字符串时间格式化为简洁的可读形式，失败则原样返回 */
function formatTime(raw?: string): string {
  if (!raw) return '';
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export default function PopupAnnouncementsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const isAdmin = useAuthStore((s) => s.user?.is_admin ?? false);

  const [items, setItems] = useState<PopupAnnouncement[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [togglingId, setTogglingId] = useState<number | null>(null);

  // 新增/编辑 Modal 共用
  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<PopupAnnouncement | null>(null);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [link, setLink] = useState('');
  const [enabled, setEnabled] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const list = await getPopupAnnouncements();
      setItems(list);
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

  function openCreate() {
    setEditing(null);
    setTitle('');
    setContent('');
    setLink('');
    setEnabled(true);
    setModalVisible(true);
  }

  function openEdit(item: PopupAnnouncement) {
    setEditing(item);
    setTitle(item.title);
    setContent(item.content);
    setLink(item.link ?? '');
    setEnabled(item.is_enabled);
    setModalVisible(true);
  }

  async function handleSave() {
    const t = title.trim();
    const ct = content.trim();
    if (!t) { Alert.alert('提示', '请输入公告标题'); return; }
    if (!ct) { Alert.alert('提示', '请输入公告内容'); return; }
    setSaving(true);
    try {
      const payload = { title: t, content: ct, link: link.trim(), is_enabled: enabled };
      if (editing) await updatePopupAnnouncement(editing.id, payload);
      else await createPopupAnnouncement(payload);
      setModalVisible(false);
      setEditing(null);
      await load();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function handleToggle(item: PopupAnnouncement) {
    setTogglingId(item.id);
    try {
      const next = await togglePopupAnnouncement(item.id);
      setItems((prev) => prev.map((a) => (a.id === item.id ? { ...a, is_enabled: next } : a)));
    } catch (e) {
      Alert.alert('操作失败', (e as Error).message);
    } finally {
      setTogglingId(null);
    }
  }

  function handleDelete(item: PopupAnnouncement) {
    Alert.alert('确认删除', `删除弹窗公告「${item.title}」？此操作不可恢复。`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: async () => {
          try {
            await deletePopupAnnouncement(item.id);
            setItems((prev) => prev.filter((a) => a.id !== item.id));
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
        <Loading label="加载弹窗公告..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <Text style={[styles.headerHint, { color: c.textMuted }]}>启用中的公告会在用户登录后弹窗展示</Text>
        {isAdmin && <Button label="发布公告" onPress={openCreate} variant="secondary" style={styles.createBtn} />}
      </View>

      <FlatList
        data={items}
        keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
        renderItem={({ item }) => (
          <Pressable onLongPress={() => handleDelete(item)} delayLongPress={400}>
            <Card style={[styles.card, { borderColor: c.border }]}>
              <View style={styles.cardTop}>
                <View style={styles.cardTexts}>
                  <View style={styles.titleRow}>
                    <Text style={[styles.cardTitle, { color: c.text }]} numberOfLines={1}>{item.title}</Text>
                    {item.source === 'remote' && (
                      <View style={[styles.sourceBadge, { backgroundColor: c.surfaceAlt }]}>
                        <Text style={[styles.sourceText, { color: c.textMuted }]}>远程</Text>
                      </View>
                    )}
                  </View>
                  <Text style={[styles.cardContent, { color: c.textSecondary }]} numberOfLines={3}>
                    {item.content || '(无内容)'}
                  </Text>
                  {item.link ? (
                    <Text style={[styles.cardLink, { color: c.primary }]} numberOfLines={1}>{item.link}</Text>
                  ) : null}
                </View>
                {isAdmin && item.source !== 'remote' && (
                  <Switch
                    value={item.is_enabled}
                    onValueChange={() => handleToggle(item)}
                    disabled={togglingId === item.id}
                    trackColor={{ false: c.border, true: c.primary }}
                  />
                )}
              </View>
              <View style={styles.cardFooter}>
                <Text style={[styles.time, { color: c.textMuted }]}>
                  {item.is_enabled ? '启用中 · ' : '已停用 · '}{formatTime(item.created_at)}
                </Text>
                {isAdmin && item.source !== 'remote' && (
                  <View style={styles.cardActions}>
                    <Button label="编辑" variant="secondary" onPress={() => openEdit(item)} style={styles.btn} />
                    <Button label="删除" variant="danger" onPress={() => handleDelete(item)} style={styles.btn} />
                  </View>
                )}
              </View>
            </Card>
          </Pressable>
        )}
        ListEmptyComponent={
          <EmptyState
            icon={Image}
            title="暂无弹窗公告"
            message="发布的弹窗公告将在用户登录后展示"
            actionLabel={isAdmin ? '发布公告' : undefined}
            onAction={openCreate}
          />
        }
        contentContainerStyle={styles.list}
      />

      {/* 新增/编辑 Modal */}
      <FormModal
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        title={editing ? '编辑弹窗公告' : '发布弹窗公告'}
      >
        <View style={styles.fieldGroup}>
          <Text style={[styles.label, { color: c.textSecondary }]}>标题</Text>
          <Input
            value={title}
            onChangeText={setTitle}
            placeholder="请输入公告标题"
            maxLength={100}
          />
        </View>
        <View style={styles.fieldGroup}>
          <Text style={[styles.label, { color: c.textSecondary }]}>内容</Text>
          <Input
            value={content}
            onChangeText={setContent}
            placeholder="请输入公告内容"
            multiline
            style={styles.contentInput}
          />
        </View>
        <View style={styles.fieldGroup}>
          <Text style={[styles.label, { color: c.textSecondary }]}>跳转链接（可选）</Text>
          <Input
            value={link}
            onChangeText={setLink}
            placeholder="https://..."
            autoCapitalize="none"
          />
        </View>
        <View style={[styles.switchRow, { borderColor: c.borderLight }]}>
          <View style={styles.switchTexts}>
            <Text style={[styles.label, { color: c.text }]}>启用</Text>
            <Text style={[styles.hint, { color: c.textMuted }]}>停用后不再向用户弹窗展示</Text>
          </View>
          <Switch value={enabled} onValueChange={setEnabled} trackColor={{ false: c.border, true: c.primary }} />
        </View>
        <View style={styles.modalActions}>
          <Button label="取消" variant="ghost" onPress={() => setModalVisible(false)} style={styles.modalBtn} />
          <Button
            label={editing ? '保存' : '发布'}
            onPress={handleSave}
            loading={saving}
            disabled={saving}
            style={styles.modalBtn}
          />
        </View>
      </FormModal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: spacing.md,
  },
  headerHint: { ...typography.small, flex: 1 },
  createBtn: { minHeight: 40 },
  list: { padding: spacing.lg, gap: spacing.md, paddingBottom: 80 },
  card: { gap: spacing.sm, borderWidth: 1 },
  cardTop: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' },
  cardTexts: { flex: 1, marginRight: spacing.md, gap: spacing.xs },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  cardTitle: { ...typography.heading, flexShrink: 1 },
  sourceBadge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: 4 },
  sourceText: { ...typography.small, fontWeight: '600' },
  cardContent: { ...typography.body, lineHeight: 22 },
  cardLink: { ...typography.small },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.xs,
  },
  time: { ...typography.small, flex: 1 },
  cardActions: { flexDirection: 'row', gap: spacing.xs },
  btn: { minHeight: 36 },
  // 表单弹层
  fieldGroup: { gap: spacing.xs },
  label: { ...typography.caption },
  contentInput: { minHeight: 100, textAlignVertical: 'top' },
  switchRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    borderBottomWidth: 1,
  },
  switchTexts: { flex: 1, marginRight: spacing.md, gap: 2 },
  hint: { ...typography.small },
  modalActions: { flexDirection: 'row', gap: spacing.sm },
  modalBtn: { flex: 1 },
});
