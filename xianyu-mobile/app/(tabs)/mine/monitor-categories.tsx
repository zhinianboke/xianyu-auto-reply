import { useState, useCallback, useEffect, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Alert,
  Modal,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button, Input, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getListingTasks,
  getListingCategories,
  type ListingTask,
} from '@/api/wrappers/products';
import {
  createListingCategory,
  updateListingCategory,
  deleteListingCategory,
  isEndpointMissing,
  type ListingCategory,
} from '@/api/wrappers/monitor';

/** 分类名称与后端一致限制在 100 字内 */
const NAME_MAX_LENGTH = 100;

export default function MonitorCategoriesScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [categories, setCategories] = useState<ListingCategory[]>([]);
  const [tasks, setTasks] = useState<ListingTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // 新建/编辑表单（editingId 为 null 表示新建）
  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<ListingCategory | null>(null);
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    setRefreshing(true);
    try {
      // 任务列表用于在分类卡片上展示关联任务数（后端分类接口不返回该统计）
      const [cats, ts] = await Promise.all([
        getListingCategories(),
        getListingTasks().catch(() => [] as ListingTask[]),
      ]);
      setCategories(cats);
      setTasks(ts);
    } catch (e) {
      if (isEndpointMissing(e)) {
        Alert.alert('功能不可用', '分类管理需要后端新版支持，请升级后端服务');
      } else {
        Alert.alert('加载失败', (e as Error).message);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  /** 分类 → 关联监控任务数（按 category_id 统计，列表加载失败时降级为 0） */
  const taskCountMap = useMemo(() => {
    const map = new Map<number, number>();
    for (const t of tasks) {
      if (t.category_id == null) continue;
      map.set(t.category_id, (map.get(t.category_id) ?? 0) + 1);
    }
    return map;
  }, [tasks]);

  function openCreate() {
    setEditing(null);
    setName('');
    setModalVisible(true);
  }

  function openEdit(cat: ListingCategory) {
    setEditing(cat);
    setName(cat.name);
    setModalVisible(true);
  }

  async function save() {
    const trimmed = name.trim();
    if (!trimmed) {
      Alert.alert('提示', '请输入分类名称');
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await updateListingCategory(editing.id, trimmed);
      } else {
        await createListingCategory(trimmed);
      }
      setModalVisible(false);
      await loadData();
    } catch (e) {
      // 重名、超长等业务错误直接展示后端 message
      Alert.alert(editing ? '修改失败' : '创建失败', (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function confirmDelete(cat: ListingCategory) {
    Alert.alert('删除分类', `确定删除「${cat.name}」吗？有关联任务或兜底配置时将无法删除。`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: () => {
          deleteListingCategory(cat.id)
            .then(loadData)
            .catch((e: unknown) => Alert.alert('删除失败', (e as Error).message));
        },
      },
    ]);
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载监控分类..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <Button label="+ 新建分类" onPress={openCreate} variant="secondary" />
      </View>

      <FlatList
        data={categories}
        keyExtractor={(item) => String(item.id)}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={loadData} />
        }
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: c.textMuted }]}>
              暂无分类，点击右上角新建
            </Text>
          </View>
        }
        renderItem={({ item }) => {
          const count = taskCountMap.get(item.id) ?? 0;
          return (
            <Card style={styles.card}>
              <Pressable
                onPress={() => openEdit(item)}
                onLongPress={() => confirmDelete(item)}
              >
                <View style={styles.row}>
                  <View style={styles.info}>
                    <Text style={[styles.catName, { color: c.text }]} numberOfLines={1}>
                      {item.name}
                    </Text>
                    <Text style={[styles.meta, { color: c.textMuted }]}>
                      {count > 0 ? `${count} 个关联任务` : '无关联任务'} · 点击编辑，长按删除
                    </Text>
                  </View>
                  <View
                    style={[styles.countBadge, { backgroundColor: c.primaryLight }]}
                  >
                    <Text style={[styles.countText, { color: c.primary }]}>{count}</Text>
                  </View>
                </View>
              </Pressable>
            </Card>
          );
        }}
      />

      {/* 新建/编辑分类 Modal */}
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
            <Text style={[styles.modalTitle, { color: c.text }]}>
              {editing ? '编辑分类' : '新建分类'}
            </Text>
            <Text style={[styles.label, { color: c.textSecondary }]}>分类名称</Text>
            <Input
              value={name}
              onChangeText={setName}
              placeholder="如：数码产品"
              maxLength={NAME_MAX_LENGTH}
              autoFocus
            />
            <View style={styles.modalActions}>
              <Button
                label="取消"
                variant="ghost"
                onPress={() => setModalVisible(false)}
                style={styles.modalBtn}
              />
              <Button
                label="保存"
                onPress={save}
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
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.md },
  card: { paddingVertical: spacing.md },
  row: { flexDirection: 'row', alignItems: 'center' },
  info: { flex: 1, marginRight: spacing.sm, gap: spacing.xs },
  catName: { ...typography.body, fontWeight: '600' },
  meta: { ...typography.small },
  countBadge: {
    minWidth: 36,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    alignItems: 'center',
  },
  countText: { ...typography.small, fontWeight: '700' },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  overlay: {
    flex: 1,
    justifyContent: 'center',
    padding: spacing.lg,
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  modal: { borderRadius: radius.lg, padding: spacing.lg, gap: spacing.xs },
  modalTitle: { ...typography.heading, marginBottom: spacing.xs },
  label: { ...typography.caption, marginTop: spacing.sm, marginBottom: spacing.xs },
  modalActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  modalBtn: { flex: 1 },
});
