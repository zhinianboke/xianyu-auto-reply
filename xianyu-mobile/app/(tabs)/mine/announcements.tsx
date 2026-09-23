import { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Modal,
  Alert,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button, Input, Loading, EmptyState } from '@/components/ui';
import { Megaphone } from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { useAuthStore } from '@/stores/auth';
import {
  getAnnouncements,
  createAnnouncement,
  updateAnnouncement,
  deleteAnnouncement,
  type Announcement,
} from '@/api/wrappers/dashboard';

/** 将 ISO/字符串时间格式化为简洁的可读形式，失败则原样返回 */
function formatTime(raw: string): string {
  if (!raw) return '';
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export default function AnnouncementsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const isAdmin = useAuthStore((s) => s.user?.is_admin ?? false);

  const [items, setItems] = useState<Announcement[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // 新增/编辑 Modal 共用
  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<Announcement | null>(null);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const list = await getAnnouncements();
      setItems(list);
    } catch (e) {
      console.error('加载公告失败', e);
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
    setModalVisible(true);
  }

  function openEdit(item: Announcement) {
    setEditing(item);
    setTitle(item.title);
    setContent(item.content);
    setModalVisible(true);
  }

  async function handleSave() {
    const t = title.trim();
    const ct = content.trim();
    if (!t) {
      Alert.alert('提示', '请输入标题');
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await updateAnnouncement(editing.id, t, ct);
      } else {
        await createAnnouncement(t, ct);
      }
      setModalVisible(false);
      setEditing(null);
      setTitle('');
      setContent('');
      await load();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function handleDelete(item: Announcement) {
    Alert.alert(
      '确认删除',
      `删除公告「${item.title || '无标题'}」？此操作不可恢复。`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteAnnouncement(item.id);
              setItems((prev) => prev.filter((a) => a.id !== item.id));
            } catch (e) {
              Alert.alert('删除失败', (e as Error).message);
            }
          },
        },
      ],
      { cancelable: true },
    );
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载公告..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        {isAdmin && (
          <Button label="发布公告" onPress={openCreate} variant="secondary" />
        )}
      </View>

      <FlatList
        data={items}
        keyExtractor={(item) => String(item.id)}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={load} />
        }
        renderItem={({ item }) => (
          <Card style={[styles.card, { borderColor: c.border }]}>
            <Text style={[styles.cardTitle, { color: c.text }]}>{item.title}</Text>
            <Text style={[styles.cardContent, { color: c.textSecondary }]}>
              {item.content || '(无内容)'}
            </Text>
            <View style={styles.cardFooter}>
              <Text style={[styles.time, { color: c.textMuted }]}>
                {formatTime(item.created_at)}
              </Text>
              {isAdmin && (
                <View style={styles.cardActions}>
                  <Button
                    label="编辑"
                    variant="secondary"
                    onPress={() => openEdit(item)}
                    style={styles.btn}
                  />
                  <Button
                    label="删除"
                    variant="danger"
                    onPress={() => handleDelete(item)}
                    style={styles.btn}
                  />
                </View>
              )}
            </View>
          </Card>
        )}
        ListEmptyComponent={
          <EmptyState
            icon={Megaphone}
            title="暂无公告"
            message="发布公告后将展示给所有用户"
            actionLabel={isAdmin ? '发布公告' : undefined}
            onAction={openCreate}
          />
        }
        contentContainerStyle={styles.list}
      />

      {/* 新增/编辑 Modal */}
      <Modal
        visible={modalVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setModalVisible(false)}
      >
        <Pressable style={styles.overlay} onPress={() => setModalVisible(false)}>
          <Pressable
            style={[styles.modal, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>
                {editing ? '编辑公告' : '发布公告'}
              </Text>
              <Pressable onPress={() => setModalVisible(false)} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>

            <View style={styles.fieldGroup}>
              <Text style={[styles.label, { color: c.textSecondary }]}>标题</Text>
              <Input
                value={title}
                onChangeText={setTitle}
                placeholder="请输入公告标题"
                maxLength={100}
                autoFocus
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

            <View style={styles.modalActions}>
              <Button
                label="取消"
                variant="ghost"
                onPress={() => setModalVisible(false)}
                style={styles.modalBtn}
              />
              <Button
                label={editing ? '保存' : '发布'}
                onPress={handleSave}
                loading={saving}
                disabled={saving}
                style={styles.modalBtn}
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
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  list: { padding: spacing.lg, gap: spacing.md },
  card: { gap: spacing.sm, borderWidth: 1 },
  cardTitle: { ...typography.heading },
  cardContent: { ...typography.body, lineHeight: 22 },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.xs,
  },
  time: { ...typography.small },
  cardActions: { flexDirection: 'row', gap: spacing.xs },
  btn: { minHeight: 36 },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  // Modal
  overlay: {
    flex: 1,
    justifyContent: 'center',
    padding: spacing.lg,
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  modal: {
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.md,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  modalTitle: { ...typography.heading },
  closeBtn: { fontSize: 22, paddingHorizontal: spacing.xs },
  fieldGroup: { gap: spacing.xs },
  label: { ...typography.caption },
  contentInput: { minHeight: 100, textAlignVertical: 'top' },
  modalActions: { flexDirection: 'row', gap: spacing.sm },
  modalBtn: { flex: 1 },
});
