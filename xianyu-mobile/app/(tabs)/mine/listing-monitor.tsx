import { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Switch,
  Alert,
  Modal,
  ScrollView,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button, Input, Loading, EmptyState } from '@/components/ui';
import { Eye } from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getListingTasks,
  getListingOverview,
  getMonitoredItems,
  getListingCategories,
  createListingTask,
  updateListingTaskStatus,
  runListingTask,
  deleteListingTask,
  type ListingTask,
  type ListingOverview,
  type ListingCategory,
  type MonitoredItem,
} from '@/api/wrappers/products';

/** 监控类型 → 展示文案 */
function monitorTypeLabel(type: string | undefined): string {
  return type === 'price_drop' ? '降价监控' : '上新监控';
}

/** 价格区间展示文案，未配置时返回 null */
function priceRangeText(task: ListingTask): string | null {
  const hasMin = task.price_min != null;
  const hasMax = task.price_max != null;
  if (!hasMin && !hasMax) return null;
  if (hasMin && hasMax) return `¥${task.price_min} - ¥${task.price_max}`;
  return hasMin ? `≥ ¥${task.price_min}` : `≤ ¥${task.price_max}`;
}

export default function ListingMonitorScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [tasks, setTasks] = useState<ListingTask[]>([]);
  const [overview, setOverview] = useState<ListingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [itemsMap, setItemsMap] = useState<Record<number, MonitoredItem[]>>({});
  const [itemsLoading, setItemsLoading] = useState<Record<number, boolean>>({});
  const [toggling, setToggling] = useState<Record<number, boolean>>({});
  const [running, setRunning] = useState<Record<number, boolean>>({});

  const [categories, setCategories] = useState<ListingCategory[]>([]);

  // 新建任务表单
  const [modalVisible, setModalVisible] = useState(false);
  const [saving, setSaving] = useState(false);
  const [keyword, setKeyword] = useState('');
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [categoryText, setCategoryText] = useState('');
  const [priceMin, setPriceMin] = useState('');
  const [priceMax, setPriceMax] = useState('');
  const [intervalText, setIntervalText] = useState('30');
  const [createEnabled, setCreateEnabled] = useState(true);

  const loadOverview = useCallback(async () => {
    try {
      setOverview(await getListingOverview());
    } catch {
      // 概览刷新失败不打断主流程，下拉刷新会再次尝试
    }
  }, []);

  const loadCategories = useCallback(async () => {
    try {
      setCategories(await getListingCategories());
    } catch (e) {
      Alert.alert('加载分类失败', (e as Error).message);
    }
  }, []);

  const loadTasks = useCallback(async () => {
    setRefreshing(true);
    try {
      setTasks(await getListingTasks());
    } catch (e) {
      Alert.alert('加载失败', (e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadTasks();
    loadOverview();
    loadCategories();
  }, [loadTasks, loadOverview, loadCategories]);

  const categoryName = useCallback(
    (id?: number): string | null => {
      if (id == null) return null;
      return categories.find((cat) => cat.id === id)?.name ?? null;
    },
    [categories],
  );

  const toggleExpand = useCallback(
    async (task: ListingTask) => {
      if (expandedId === task.id) {
        setExpandedId(null);
        return;
      }
      setExpandedId(task.id);
      // 首次展开时拉取该任务的采集商品，已缓存则直接复用
      if (itemsMap[task.id]) return;
      setItemsLoading((prev) => ({ ...prev, [task.id]: true }));
      try {
        const items = await getMonitoredItems(task.id);
        setItemsMap((prev) => ({ ...prev, [task.id]: items }));
      } catch (e) {
        Alert.alert('加载商品失败', (e as Error).message);
      } finally {
        setItemsLoading((prev) => ({ ...prev, [task.id]: false }));
      }
    },
    [expandedId, itemsMap],
  );

  /** 启用/停用：先乐观更新本地状态，失败时回滚 */
  const handleToggle = useCallback(
    async (task: ListingTask, value: boolean) => {
      const nextStatus = value ? 'active' : 'inactive';
      setTasks((prev) =>
        prev.map((t) =>
          t.id === task.id ? { ...t, is_enabled: value, status: nextStatus } : t,
        ),
      );
      setToggling((prev) => ({ ...prev, [task.id]: true }));
      try {
        await updateListingTaskStatus(task.id, value);
        await loadOverview();
      } catch (e) {
        setTasks((prev) =>
          prev.map((t) =>
            t.id === task.id
              ? { ...t, is_enabled: !value, status: value ? 'inactive' : 'active' }
              : t,
          ),
        );
        Alert.alert('操作失败', (e as Error).message);
      } finally {
        setToggling((prev) => ({ ...prev, [task.id]: false }));
      }
    },
    [loadOverview],
  );

  const handleRun = useCallback(
    async (task: ListingTask) => {
      setRunning((prev) => ({ ...prev, [task.id]: true }));
      try {
        await runListingTask(task.id);
        // 采集结果已变化，清掉展开缓存以便重新拉取
        setItemsMap((prev) => {
          const next = { ...prev };
          delete next[task.id];
          return next;
        });
        await loadOverview();
        Alert.alert('执行成功', '采集任务已触发，稍后下拉刷新查看结果');
      } catch (e) {
        Alert.alert('执行失败', (e as Error).message);
      } finally {
        setRunning((prev) => ({ ...prev, [task.id]: false }));
      }
    },
    [loadOverview],
  );

  const confirmDelete = useCallback((task: ListingTask) => {
    const label = task.keyword || task.name || `任务 #${task.id}`;
    Alert.alert('删除任务', `确定删除「${label}」吗？此操作不可恢复。`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: () => {
          deleteListingTask(task.id)
            .then(() => {
              if (expandedId === task.id) setExpandedId(null);
              return Promise.all([loadTasks(), loadOverview()]);
            })
            .catch((e: unknown) =>
              Alert.alert('删除失败', (e as Error).message),
            );
        },
      },
    ]);
  }, [expandedId, loadTasks, loadOverview]);

  function openCreate() {
    setKeyword('');
    setCategoryId(null);
    setCategoryText('');
    setPriceMin('');
    setPriceMax('');
    setIntervalText('30');
    setCreateEnabled(true);
    setModalVisible(true);
    // 分类列表可能在首次加载时失败，打开表单时兜底重试
    if (categories.length === 0) loadCategories();
  }

  async function save() {
    const kw = keyword.trim();
    if (!kw) {
      Alert.alert('提示', '请输入监控关键词');
      return;
    }
    if (categoryId == null) {
      Alert.alert('提示', '请选择所属分类');
      return;
    }
    const interval = Math.floor(Number(intervalText));
    if (!Number.isFinite(interval) || interval < 1) {
      Alert.alert('提示', '执行间隔需为不小于 1 的分钟数');
      return;
    }
    const min = priceMin.trim() === '' ? undefined : Number(priceMin);
    const max = priceMax.trim() === '' ? undefined : Number(priceMax);
    if (min != null && (!Number.isFinite(min) || min < 0)) {
      Alert.alert('提示', '最低价需为不小于 0 的数字');
      return;
    }
    if (max != null && (!Number.isFinite(max) || max < 0)) {
      Alert.alert('提示', '最高价需为不小于 0 的数字');
      return;
    }
    if (min != null && max != null && min > max) {
      Alert.alert('提示', '最低价不能高于最高价');
      return;
    }
    setSaving(true);
    try {
      await createListingTask({
        keyword: kw,
        categoryId,
        intervalMinutes: interval,
        priceMin: min,
        priceMax: max,
        enabled: createEnabled,
      });
      setModalVisible(false);
      await Promise.all([loadTasks(), loadOverview()]);
    } catch (e) {
      Alert.alert('创建失败', (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载监控任务..." />
      </SafeAreaView>
    );
  }

  const statsHeader = (
    <View style={[styles.statsCard, { backgroundColor: c.surface }]}>
      <View style={styles.statBlock}>
        <Text style={[styles.statValue, { color: c.text }]}>
          {overview?.total_tasks ?? 0}
        </Text>
        <Text style={[styles.statLabel, { color: c.textMuted }]}>总任务</Text>
      </View>
      <View style={[styles.statDivider, { backgroundColor: c.border }]} />
      <View style={styles.statBlock}>
        <Text style={[styles.statValue, { color: c.success }]}>
          {overview?.active_tasks ?? 0}
        </Text>
        <Text style={[styles.statLabel, { color: c.textMuted }]}>已启用</Text>
      </View>
      <View style={[styles.statDivider, { backgroundColor: c.border }]} />
      <View style={styles.statBlock}>
        <Text style={[styles.statValue, { color: c.info }]}>
          {overview?.today_run_total ?? 0}
        </Text>
        <Text style={[styles.statLabel, { color: c.textMuted }]}>今日执行</Text>
      </View>
    </View>
  );

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <Button label="+ 新建" onPress={openCreate} variant="secondary" />
      </View>

      <FlatList
        data={tasks}
        keyExtractor={(item) => String(item.id)}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={loadTasks} />
        }
        contentContainerStyle={styles.list}
        ListHeaderComponent={statsHeader}
        ListEmptyComponent={
          <EmptyState
            icon={Eye}
            title="暂无监控任务"
            message="新建任务后即可监控商品降价与上新"
            actionLabel="新建监控任务"
            onAction={openCreate}
          />
        }
        renderItem={({ item }) => {
          const expanded = expandedId === item.id;
          const enabled = item.is_enabled ?? item.status === 'active';
          const items = itemsMap[item.id];
          const busyToggling = !!toggling[item.id];
          const busyRunning = !!running[item.id];
          const range = priceRangeText(item);
          const catLabel = categoryName(item.category_id) ?? `分类 #${item.category_id ?? '?'}`;
          return (
            <Card style={styles.card}>
              <View style={styles.taskHeader}>
                <Pressable
                  style={styles.taskInfo}
                  onPress={() => toggleExpand(item)}
                  onLongPress={() => confirmDelete(item)}
                >
                  <Text style={[styles.taskName, { color: c.text }]} numberOfLines={1}>
                    {item.keyword || item.name || `任务 #${item.id}`}
                  </Text>
                  <View style={styles.taskMeta}>
                    <View style={[styles.badge, { backgroundColor: c.primaryLight }]}>
                      <Text style={[styles.badgeText, { color: c.primary }]}>
                        {monitorTypeLabel(item.monitor_type)}
                      </Text>
                    </View>
                    <Text style={[styles.metaText, { color: c.textMuted }]} numberOfLines={1}>
                      {catLabel}
                      {item.interval_minutes != null
                        ? ` · 每 ${item.interval_minutes} 分钟`
                        : ''}
                      {range ? ` · ${range}` : ''}
                    </Text>
                  </View>
                </Pressable>
                <Switch
                  value={enabled}
                  onValueChange={(value) => handleToggle(item, value)}
                  disabled={busyToggling}
                  trackColor={{ false: c.border, true: c.primary }}
                />
              </View>

              <View style={styles.taskActions}>
                <Button
                  label="执行"
                  variant="secondary"
                  onPress={() => handleRun(item)}
                  loading={busyRunning}
                  // 后端拒绝执行停用中的任务，这里直接禁用
                  disabled={!enabled || busyRunning}
                  style={styles.runBtn}
                />
                <Text style={[styles.expandHint, { color: c.textMuted }]}>
                  {expanded ? '收起商品列表 ▲' : '点击查看采集商品 ▼'}
                </Text>
              </View>

              {expanded && (
                <View
                  style={[styles.itemsWrap, { borderTopColor: c.border, borderTopWidth: 1 }]}
                >
                  {itemsLoading[item.id] ? (
                    <Text style={[styles.hint, { color: c.textMuted }]}>加载商品中...</Text>
                  ) : items && items.length > 0 ? (
                    items.map((it) => (
                      <View
                        key={it.item_id}
                        style={[styles.itemRow, { borderBottomColor: c.border }]}
                      >
                        <Text style={[styles.itemTitle, { color: c.text }]} numberOfLines={1}>
                          {it.title}
                        </Text>
                        <Text style={[styles.itemPrice, { color: c.primary }]}>¥{it.price}</Text>
                      </View>
                    ))
                  ) : (
                    <Text style={[styles.hint, { color: c.textMuted }]}>暂无采集商品</Text>
                  )}
                </View>
              )}
            </Card>
          );
        }}
      />

      {/* 新建任务 Modal */}
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
              <Text style={[styles.modalTitle, { color: c.text }]}>新建监控任务</Text>
              <Pressable onPress={() => setModalVisible(false)} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>

            <ScrollView style={styles.modalScroll} keyboardShouldPersistTaps="handled">
              <Text style={[styles.label, { color: c.textSecondary }]}>监控关键词</Text>
              <Input
                value={keyword}
                onChangeText={setKeyword}
                placeholder="如：iPhone 16 Pro"
                maxLength={200}
                autoFocus
              />

              <Text style={[styles.label, { color: c.textSecondary }]}>所属分类</Text>
              {categories.length > 0 ? (
                <View style={styles.chipWrap}>
                  {categories.map((cat) => {
                    const selected = categoryId === cat.id;
                    return (
                      <Pressable
                        key={cat.id}
                        onPress={() => setCategoryId(cat.id)}
                        style={[
                          styles.chip,
                          {
                            borderColor: selected ? c.primary : c.border,
                            backgroundColor: selected ? c.primary : 'transparent',
                          },
                        ]}
                      >
                        <Text
                          style={[styles.chipText, { color: selected ? '#FFF' : c.text }]}
                          numberOfLines={1}
                        >
                          {cat.name}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              ) : (
                <Input
                  value={categoryText}
                  onChangeText={(text) => {
                    setCategoryText(text);
                    setCategoryId(Math.floor(Number(text)) || null);
                  }}
                  placeholder="分类列表加载失败，请输入分类ID"
                  keyboardType="number-pad"
                />
              )}

              <Text style={[styles.label, { color: c.textSecondary }]}>价格区间（可选）</Text>
              <View style={styles.priceRow}>
                <Input
                  value={priceMin}
                  onChangeText={setPriceMin}
                  placeholder="最低价"
                  keyboardType="decimal-pad"
                  style={styles.priceInput}
                />
                <Text style={[styles.priceSep, { color: c.textMuted }]}>-</Text>
                <Input
                  value={priceMax}
                  onChangeText={setPriceMax}
                  placeholder="最高价"
                  keyboardType="decimal-pad"
                  style={styles.priceInput}
                />
              </View>

              <Text style={[styles.label, { color: c.textSecondary }]}>执行间隔（分钟）</Text>
              <Input
                value={intervalText}
                onChangeText={setIntervalText}
                placeholder="30"
                keyboardType="number-pad"
              />

              <View style={styles.switchRow}>
                <View style={styles.switchInfo}>
                  <Text style={[styles.label, { color: c.textSecondary }]}>创建后立即启用</Text>
                  <Text style={[styles.switchHint, { color: c.textMuted }]}>
                    停用后可在列表中随时开启
                  </Text>
                </View>
                <Switch
                  value={createEnabled}
                  onValueChange={setCreateEnabled}
                  trackColor={{ false: c.border, true: c.primary }}
                />
              </View>
            </ScrollView>

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
  // 统计卡片
  statsCard: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radius.lg,
    paddingVertical: spacing.lg,
    marginBottom: spacing.md,
  },
  statBlock: { flex: 1, alignItems: 'center', gap: spacing.xs },
  statValue: { ...typography.title, fontSize: 24 },
  statLabel: { ...typography.small },
  statDivider: { width: 1, height: 32 },
  // 任务卡片
  card: { gap: spacing.sm },
  taskHeader: { flexDirection: 'row', alignItems: 'center' },
  taskInfo: { flex: 1, marginRight: spacing.sm, gap: spacing.xs },
  taskName: { ...typography.body, fontWeight: '600' },
  taskMeta: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  badge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  badgeText: { ...typography.small, fontWeight: '600' },
  metaText: { ...typography.small, flexShrink: 1 },
  taskActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  runBtn: { minHeight: 40, paddingHorizontal: spacing.xl },
  expandHint: { ...typography.small },
  itemsWrap: { paddingTop: spacing.sm, marginTop: spacing.xs, gap: 0 },
  itemRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  itemTitle: { ...typography.caption, flex: 1, marginRight: spacing.sm },
  itemPrice: { ...typography.caption, fontWeight: '600' },
  hint: { ...typography.small, paddingVertical: spacing.sm },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  // 新建 Modal
  overlay: {
    flex: 1,
    justifyContent: 'center',
    padding: spacing.lg,
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  modal: { borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  modalTitle: { ...typography.heading },
  closeBtn: { fontSize: 22, paddingHorizontal: spacing.xs },
  modalScroll: { maxHeight: '70%' },
  label: { ...typography.caption, marginTop: spacing.sm, marginBottom: spacing.xs },
  chipWrap: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
    borderWidth: 1,
    maxWidth: '100%',
  },
  chipText: { ...typography.small },
  priceRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  priceInput: { flex: 1 },
  priceSep: { ...typography.body },
  switchRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.md,
    marginTop: spacing.md,
  },
  switchInfo: { flex: 1, gap: 2 },
  switchHint: { ...typography.small },
  modalActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  modalBtn: { flex: 1 },
});
