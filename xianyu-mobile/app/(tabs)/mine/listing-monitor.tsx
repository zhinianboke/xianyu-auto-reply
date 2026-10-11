import { useState, useCallback, useEffect, useMemo } from 'react';
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
  getListingOverview,
  getMonitoredItems,
  getListingCategories,
  updateListingTaskStatus,
  runListingTask,
  type ListingOverview,
  type ListingCategory,
  type MonitoredItem,
} from '@/api/wrappers/products';
import {
  getMonitorTasksFull,
  createMonitorTask,
  updateMonitorTask,
  batchDeleteMonitorTasks,
  batchUpdateMonitorAccounts,
  batchUpdateMonitorCategory,
  batchUpdateMonitorDmContent,
  type MonitorTaskFull,
  type MonitorTaskPayload,
} from '@/api/wrappers/monitor';
import { getAccountOptions, type AccountOption } from '@/api/wrappers/accounts';

/** 监控类型选项（value 与后端一致） */
const MONITOR_TYPES: { value: string; label: string }[] = [
  { value: 'listing', label: '上新监控' },
  { value: 'price_drop', label: '降价监控' },
];

/** 上新天数筛选选项（仅上新监控展示；''=最新不限天数） */
const PUBLISH_DAYS: { value: string; label: string }[] = [
  { value: '', label: '最新' },
  { value: '1', label: '1天内' },
  { value: '3', label: '3天内' },
  { value: '7', label: '7天内' },
  { value: '14', label: '14天内' },
];

/** 任务表单状态（字段对齐 web ListingMonitorFormModal） */
interface TaskFormState {
  monitorType: string;
  categoryId: number | null;
  keyword: string;
  priceMin: string;
  priceMax: string;
  publishDays: string;
  intervalText: string;
  collectPagesText: string;
  proxyUrl: string;
  accountIds: string[];
  orderAccountIds: string[];
  dmContent: string;
  dmBatchSizeText: string;
  orderBatchSizeText: string;
  directOrder: boolean;
  enabled: boolean;
}

/** 新建表单初始值（默认值对齐 web：间隔 5 分钟、采集 1 页、批量 5） */
const EMPTY_FORM: TaskFormState = {
  monitorType: 'listing',
  categoryId: null,
  keyword: '',
  priceMin: '',
  priceMax: '',
  publishDays: '',
  intervalText: '5',
  collectPagesText: '1',
  proxyUrl: '',
  accountIds: [],
  orderAccountIds: [],
  dmContent: '',
  dmBatchSizeText: '5',
  orderBatchSizeText: '5',
  directOrder: false,
  enabled: true,
};

/** 编辑表单：由任务完整字段回填 */
function formFromTask(task: MonitorTaskFull): TaskFormState {
  return {
    monitorType: task.monitor_type || 'listing',
    categoryId: task.category_id ?? null,
    keyword: task.keyword || '',
    priceMin: task.price_min != null ? String(task.price_min) : '',
    priceMax: task.price_max != null ? String(task.price_max) : '',
    publishDays: task.publish_days != null ? String(task.publish_days) : '',
    intervalText: task.interval_minutes != null ? String(task.interval_minutes) : '5',
    collectPagesText: task.collect_pages != null ? String(task.collect_pages) : '1',
    proxyUrl: task.proxy_url || '',
    accountIds: [...(task.account_ids || [])],
    orderAccountIds: [...(task.order_account_ids || [])],
    dmContent: task.dm_content || '',
    dmBatchSizeText: task.dm_batch_size != null ? String(task.dm_batch_size) : '5',
    orderBatchSizeText: task.order_batch_size != null ? String(task.order_batch_size) : '5',
    directOrder: Boolean(task.direct_order),
    enabled: task.is_enabled,
  };
}

/** 监控类型 → 展示文案 */
function monitorTypeLabel(type: string | undefined): string {
  return type === 'price_drop' ? '降价监控' : '上新监控';
}

/** 价格区间展示文案，未配置时返回 null */
function priceRangeText(task: MonitorTaskFull): string | null {
  const hasMin = task.price_min != null;
  const hasMax = task.price_max != null;
  if (!hasMin && !hasMax) return null;
  if (hasMin && hasMax) return `¥${task.price_min} - ¥${task.price_max}`;
  return hasMin ? `≥ ¥${task.price_min}` : `≤ ¥${task.price_max}`;
}

/** 账号展示名：备注（ID）优先，退化为纯 ID */
function accountLabel(a: AccountOption): string {
  return a.remark ? `${a.remark}（${a.id}）` : a.id;
}

/** 多选账号选择器（表单内嵌 chips，勾选高亮） */
function AccountPicker({
  options,
  selected,
  onToggle,
  c,
}: {
  options: AccountOption[];
  selected: string[];
  onToggle: (id: string) => void;
  c: (typeof colors)['light'];
}) {
  if (options.length === 0) {
    return <Text style={[styles.hint, { color: c.textMuted }]}>暂无启用账号</Text>;
  }
  return (
    <View style={styles.chipWrap}>
      {options.map((a) => {
        const checked = selected.includes(a.id);
        return (
          <Pressable
            key={a.id}
            onPress={() => onToggle(a.id)}
            style={[
              styles.chip,
              {
                borderColor: checked ? c.primary : c.border,
                backgroundColor: checked ? c.primary : 'transparent',
              },
            ]}
          >
            <Text
              style={[styles.chipText, { color: checked ? '#FFF' : c.text }]}
              numberOfLines={1}
            >
              {checked ? '✓ ' : ''}
              {accountLabel(a)}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export default function ListingMonitorScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [tasks, setTasks] = useState<MonitorTaskFull[]>([]);
  const [overview, setOverview] = useState<ListingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [itemsMap, setItemsMap] = useState<Record<number, MonitoredItem[]>>({});
  const [itemsLoading, setItemsLoading] = useState<Record<number, boolean>>({});
  const [toggling, setToggling] = useState<Record<number, boolean>>({});
  const [running, setRunning] = useState<Record<number, boolean>>({});

  const [categories, setCategories] = useState<ListingCategory[]>([]);
  const [accounts, setAccounts] = useState<AccountOption[]>([]);

  // 任务表单（新建/编辑共用）
  const [modalVisible, setModalVisible] = useState(false);
  const [editingTask, setEditingTask] = useState<MonitorTaskFull | null>(null);
  const [form, setForm] = useState<TaskFormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);

  // 批量多选模式
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [batchBusy, setBatchBusy] = useState(false);
  /** 批量操作弹窗类型：accounts-批量改账号，category-批量改分类，dm-批量改私信内容 */
  const [batchModal, setBatchModal] = useState<'accounts' | 'category' | 'dm' | null>(null);
  const [batchField, setBatchField] = useState<'account_ids' | 'order_account_ids'>('account_ids');
  const [batchAccountIds, setBatchAccountIds] = useState<string[]>([]);
  const [batchCategoryId, setBatchCategoryId] = useState<number | null>(null);
  const [batchDmContent, setBatchDmContent] = useState('');

  // 启用账号（下单账号仅允许启用账号，与 web 一致）
  const enabledAccounts = useMemo(() => accounts.filter((a) => a.enabled), [accounts]);

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

  const loadAccounts = useCallback(async () => {
    try {
      setAccounts(await getAccountOptions());
    } catch {
      // 账号列表加载失败不阻塞页面，仅账号选择为空
    }
  }, []);

  const loadTasks = useCallback(async () => {
    setRefreshing(true);
    try {
      setTasks(await getMonitorTasksFull());
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
    loadAccounts();
  }, [loadTasks, loadOverview, loadCategories, loadAccounts]);

  const categoryName = useCallback(
    (id?: number | null): string => {
      if (id == null) return '未分类';
      return categories.find((cat) => cat.id === id)?.name ?? `分类 #${id}`;
    },
    [categories],
  );

  const toggleExpand = useCallback(
    async (task: MonitorTaskFull) => {
      if (selectMode) return; // 多选模式下点击卡片为勾选
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
    [expandedId, itemsMap, selectMode],
  );

  /** 启用/停用：先乐观更新本地状态，失败时回滚 */
  const handleToggle = useCallback(
    async (task: MonitorTaskFull, value: boolean) => {
      const nextStatus = value ? 'active' : 'inactive';
      setTasks((prev) =>
        prev.map((t) =>
          t.id === task.id ? { ...t, is_enabled: value } : t,
        ),
      );
      setToggling((prev) => ({ ...prev, [task.id]: true }));
      try {
        await updateListingTaskStatus(task.id, value);
        await loadOverview();
      } catch (e) {
        setTasks((prev) =>
          prev.map((t) =>
            t.id === task.id ? { ...t, is_enabled: !value } : t,
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
    async (task: MonitorTaskFull) => {
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

  const confirmDelete = useCallback((task: MonitorTaskFull) => {
    const label = task.keyword || `任务 #${task.id}`;
    Alert.alert('删除任务', `确定删除「${label}」吗？此操作不可恢复。`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: () => {
          batchDeleteMonitorTasks([task.id])
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

  /** 长按任务卡片弹出操作菜单（编辑/删除） */
  const showTaskMenu = useCallback((task: MonitorTaskFull) => {
    const label = task.keyword || `任务 #${task.id}`;
    Alert.alert(label, undefined, [
      { text: '编辑', onPress: () => openEdit(task) },
      { text: '删除', style: 'destructive', onPress: () => confirmDelete(task) },
      { text: '取消', style: 'cancel' },
    ]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [confirmDelete]);

  function openCreate() {
    setEditingTask(null);
    setForm(EMPTY_FORM);
    setModalVisible(true);
    // 分类列表可能在首次加载时失败，打开表单时兜底重试
    if (categories.length === 0) loadCategories();
  }

  function openEdit(task: MonitorTaskFull) {
    setEditingTask(task);
    setForm(formFromTask(task));
    setModalVisible(true);
    if (categories.length === 0) loadCategories();
    if (accounts.length === 0) loadAccounts();
  }

  /** 表单 → 后端 payload（对齐 web：publish_days 仅上新监控生效） */
  function buildPayload(): MonitorTaskPayload | null {
    const kw = form.keyword.trim();
    if (!kw) {
      Alert.alert('提示', '请输入商品监控关键词');
      return null;
    }
    if (form.categoryId == null) {
      Alert.alert('提示', '请选择所属分类');
      return null;
    }
    const interval = Math.floor(Number(form.intervalText));
    if (!Number.isFinite(interval) || interval < 1) {
      Alert.alert('提示', '任务间隔需为不小于 1 的整数分钟');
      return null;
    }
    const pages = Math.floor(Number(form.collectPagesText));
    if (!Number.isFinite(pages) || pages < 1) {
      Alert.alert('提示', '采集页数需为不小于 1 的整数');
      return null;
    }
    const min = form.priceMin.trim() === '' ? null : Number(form.priceMin);
    const max = form.priceMax.trim() === '' ? null : Number(form.priceMax);
    if (min != null && (!Number.isFinite(min) || min < 0)) {
      Alert.alert('提示', '最低价需为不小于 0 的数字');
      return null;
    }
    if (max != null && (!Number.isFinite(max) || max < 0)) {
      Alert.alert('提示', '最高价需为不小于 0 的数字');
      return null;
    }
    if (min != null && max != null && min > max) {
      Alert.alert('提示', '最低价不能高于最高价');
      return null;
    }
    if (
      form.orderAccountIds.length > 0 &&
      !form.dmContent.trim() &&
      !form.directOrder
    ) {
      Alert.alert('提示', '配置了下单账号后，私信内容必填（或开启采集后直接下单）');
      return null;
    }
    if (form.directOrder && form.orderAccountIds.length === 0) {
      Alert.alert('提示', '开启采集后直接下单需先配置下单账号');
      return null;
    }
    const dmBatch = Math.floor(Number(form.dmBatchSizeText));
    if (!Number.isInteger(dmBatch) || dmBatch < 1 || dmBatch > 100) {
      Alert.alert('提示', '每次私信处理条数需为 1~100 的整数');
      return null;
    }
    const orderBatch = Math.floor(Number(form.orderBatchSizeText));
    if (!Number.isInteger(orderBatch) || orderBatch < 1 || orderBatch > 100) {
      Alert.alert('提示', '每次下单处理条数需为 1~100 的整数');
      return null;
    }
    return {
      monitor_type: form.monitorType,
      category_id: form.categoryId,
      keyword: kw,
      price_min: min,
      price_max: max,
      publish_days:
        form.monitorType === 'listing'
          ? form.publishDays === ''
            ? null
            : Math.floor(Number(form.publishDays))
          : null,
      interval_minutes: interval,
      collect_pages: pages,
      proxy_url: form.proxyUrl.trim() || null,
      account_ids: form.accountIds,
      order_account_ids: form.orderAccountIds,
      dm_content: form.dmContent.trim() || null,
      dm_batch_size: dmBatch,
      order_batch_size: orderBatch,
      direct_order: form.directOrder,
      is_enabled: form.enabled,
    };
  }

  async function save() {
    const payload = buildPayload();
    if (!payload) return;
    setSaving(true);
    try {
      if (editingTask) {
        // 编辑不传 is_enabled，启停由列表开关单独控制（与 web 一致）
        const { is_enabled: _ignored, ...updateBody } = payload;
        await updateMonitorTask(editingTask.id, updateBody);
      } else {
        await createMonitorTask(payload);
      }
      setModalVisible(false);
      setEditingTask(null);
      // 任务字段可能已变化，清空展开缓存
      setItemsMap({});
      await Promise.all([loadTasks(), loadOverview()]);
    } catch (e) {
      Alert.alert(editingTask ? '保存失败' : '创建失败', (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  // ---------------------------------------------------------------------------
  // 批量操作
  // ---------------------------------------------------------------------------

  const exitSelectMode = useCallback(() => {
    setSelectMode(false);
    setSelectedIds(new Set());
  }, []);

  const toggleSelect = useCallback((id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const toggleSelectAll = useCallback(() => {
    setSelectedIds((prev) => {
      const allSelected = tasks.length > 0 && tasks.every((t) => prev.has(t.id));
      return allSelected ? new Set() : new Set(tasks.map((t) => t.id));
    });
  }, [tasks]);

  const selectedArr = useMemo(() => Array.from(selectedIds), [selectedIds]);

  const handleBatchDelete = useCallback(() => {
    if (selectedArr.length === 0) return;
    Alert.alert(
      '批量删除',
      `确定删除选中的 ${selectedArr.length} 个监控任务吗？此操作不可恢复。`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: () => {
            setBatchBusy(true);
            batchDeleteMonitorTasks(selectedArr)
              .then((r) => {
                Alert.alert('成功', `已删除 ${r.success_count} 个监控任务`);
                setSelectedIds(new Set());
                return Promise.all([loadTasks(), loadOverview()]);
              })
              .catch((e: unknown) => Alert.alert('批量删除失败', (e as Error).message))
              .finally(() => setBatchBusy(false));
          },
        },
      ],
    );
  }, [selectedArr, loadTasks, loadOverview]);

  const openBatchModal = useCallback(
    (kind: 'accounts' | 'category' | 'dm') => {
      if (selectedArr.length === 0) {
        Alert.alert('提示', '请先勾选要操作的任务');
        return;
      }
      if (kind === 'accounts') {
        setBatchField('account_ids');
        setBatchAccountIds([]);
      } else if (kind === 'category') {
        setBatchCategoryId(null);
      } else {
        setBatchDmContent('');
      }
      if (categories.length === 0) loadCategories();
      if (accounts.length === 0) loadAccounts();
      setBatchModal(kind);
    },
    [selectedArr, categories.length, accounts.length, loadCategories, loadAccounts],
  );

  const submitBatchModal = useCallback(async () => {
    setBatchBusy(true);
    try {
      if (batchModal === 'accounts') {
        const r = await batchUpdateMonitorAccounts(
          selectedArr,
          batchField,
          batchAccountIds,
        );
        Alert.alert(
          '成功',
          `已为 ${r.success_count} 个任务修改${batchField === 'account_ids' ? '采集账号' : '下单账号'}`,
        );
      } else if (batchModal === 'category') {
        if (batchCategoryId == null) {
          Alert.alert('提示', '请选择目标分类');
          return;
        }
        const r = await batchUpdateMonitorCategory(selectedArr, batchCategoryId);
        Alert.alert('成功', `已为 ${r.success_count} 个任务修改分类`);
      } else if (batchModal === 'dm') {
        const content = batchDmContent.trim();
        if (!content) {
          Alert.alert('提示', '请输入私信内容');
          return;
        }
        const r = await batchUpdateMonitorDmContent(selectedArr, content);
        Alert.alert('成功', `已为 ${r.success_count} 个任务修改私信内容`);
      }
      setBatchModal(null);
      await loadTasks();
    } catch (e) {
      Alert.alert('批量操作失败', (e as Error).message);
    } finally {
      setBatchBusy(false);
    }
  }, [batchModal, batchField, batchAccountIds, batchCategoryId, batchDmContent, selectedArr, loadTasks]);

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

  /** 通用小段标题（表单内） */
  const label = (text: string, required?: boolean) => (
    <Text style={[styles.label, { color: c.textSecondary }]}>
      {text}
      {required ? <Text style={{ color: c.error }}> *</Text> : null}
    </Text>
  );

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        {selectMode ? (
          <>
            <Button label="全选/取消" onPress={toggleSelectAll} variant="secondary" />
            <Button label="退出多选" onPress={exitSelectMode} variant="ghost" />
          </>
        ) : (
          <>
            <Button label="批量管理" onPress={() => setSelectMode(true)} variant="secondary" />
            <Button label="+ 新建" onPress={openCreate} />
          </>
        )}
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
          const enabled = item.is_enabled;
          const items = itemsMap[item.id];
          const busyToggling = !!toggling[item.id];
          const busyRunning = !!running[item.id];
          const range = priceRangeText(item);
          const checked = selectedIds.has(item.id);
          return (
            <Card style={[styles.card, selectMode && checked && { borderColor: c.primary, borderWidth: 1 }]}>
              <View style={styles.taskHeader}>
                {selectMode && (
                  <Pressable onPress={() => toggleSelect(item.id)} hitSlop={8} style={styles.checkBox}>
                    <View
                      style={[
                        styles.checkBoxInner,
                        {
                          borderColor: checked ? c.primary : c.border,
                          backgroundColor: checked ? c.primary : 'transparent',
                        },
                      ]}
                    >
                      {checked && <Text style={styles.checkMark}>✓</Text>}
                    </View>
                  </Pressable>
                )}
                <Pressable
                  style={styles.taskInfo}
                  onPress={() => (selectMode ? toggleSelect(item.id) : toggleExpand(item))}
                  onLongPress={() => (selectMode ? toggleSelect(item.id) : showTaskMenu(item))}
                >
                  <View style={styles.taskNameRow}>
                    <Text style={[styles.taskName, { color: c.text }]} numberOfLines={1}>
                      {item.keyword || `任务 #${item.id}`}
                    </Text>
                    {item.dm_content || (item.order_account_ids?.length ?? 0) > 0 ? (
                      <View style={[styles.badge, { backgroundColor: c.primaryLight }]}>
                        <Text style={[styles.badgeText, { color: c.primary }]}>自动私信</Text>
                      </View>
                    ) : null}
                  </View>
                  <View style={styles.taskMeta}>
                    <View style={[styles.badge, { backgroundColor: c.primaryLight }]}>
                      <Text style={[styles.badgeText, { color: c.primary }]}>
                        {monitorTypeLabel(item.monitor_type)}
                      </Text>
                    </View>
                    <Text style={[styles.metaText, { color: c.textMuted }]} numberOfLines={1}>
                      {categoryName(item.category_id)}
                      {item.interval_minutes != null
                        ? ` · 每 ${item.interval_minutes} 分钟`
                        : ''}
                      {range ? ` · ${range}` : ''}
                      {(item.account_ids?.length ?? 0) > 0
                        ? ` · 采集账号 ${item.account_ids.length} 个`
                        : ''}
                    </Text>
                  </View>
                </Pressable>
                {!selectMode && (
                  <Switch
                    value={enabled}
                    onValueChange={(value) => handleToggle(item, value)}
                    disabled={busyToggling}
                    trackColor={{ false: c.border, true: c.primary }}
                  />
                )}
              </View>

              {!selectMode && (
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
                  <Button
                    label="编辑"
                    variant="secondary"
                    onPress={() => openEdit(item)}
                    style={styles.runBtn}
                  />
                  <Text style={[styles.expandHint, { color: c.textMuted }]}>
                    {expanded ? '收起商品列表 ▲' : '点击查看采集商品 ▼'}
                  </Text>
                </View>
              )}

              {expanded && !selectMode && (
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

      {/* 批量操作栏 */}
      {selectMode && selectedArr.length > 0 && (
        <View style={[styles.batchBar, { backgroundColor: c.surface, borderTopColor: c.border }]}>
          <Text style={[styles.batchCount, { color: c.textSecondary }]}>
            已选 {selectedArr.length}
          </Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.batchActions}>
            <Button label="删除" variant="danger" onPress={handleBatchDelete} loading={batchBusy} disabled={batchBusy} style={styles.batchBtn} />
            <Button label="改账号" variant="secondary" onPress={() => openBatchModal('accounts')} disabled={batchBusy} style={styles.batchBtn} />
            <Button label="改分类" variant="secondary" onPress={() => openBatchModal('category')} disabled={batchBusy} style={styles.batchBtn} />
            <Button label="改私信" variant="secondary" onPress={() => openBatchModal('dm')} disabled={batchBusy} style={styles.batchBtn} />
          </ScrollView>
        </View>
      )}

      {/* 新建/编辑任务 Modal */}
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
                {editingTask ? '编辑监控任务' : '新建监控任务'}
              </Text>
              <Pressable onPress={() => setModalVisible(false)} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>

            <ScrollView style={styles.modalScroll} keyboardShouldPersistTaps="handled">
              {label('监控类型', true)}
              <View style={styles.chipWrap}>
                {MONITOR_TYPES.map((t) => {
                  const selected = form.monitorType === t.value;
                  return (
                    <Pressable
                      key={t.value}
                      onPress={() => setForm((p) => ({ ...p, monitorType: t.value }))}
                      style={[
                        styles.chip,
                        {
                          borderColor: selected ? c.primary : c.border,
                          backgroundColor: selected ? c.primary : 'transparent',
                        },
                      ]}
                    >
                      <Text style={[styles.chipText, { color: selected ? '#FFF' : c.text }]}>
                        {t.label}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>

              {label('所属分类', true)}
              {categories.length > 0 ? (
                <View style={styles.chipWrap}>
                  {categories.map((cat) => {
                    const selected = form.categoryId === cat.id;
                    return (
                      <Pressable
                        key={cat.id}
                        onPress={() => setForm((p) => ({ ...p, categoryId: cat.id }))}
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
                  value={form.categoryId != null ? String(form.categoryId) : ''}
                  onChangeText={(text) => {
                    const id = Math.floor(Number(text));
                    setForm((p) => ({ ...p, categoryId: Number.isFinite(id) && id > 0 ? id : null }));
                  }}
                  placeholder="分类列表加载失败，请输入分类ID"
                  keyboardType="number-pad"
                />
              )}

              {label('商品关键词', true)}
              <Input
                value={form.keyword}
                onChangeText={(text) => setForm((p) => ({ ...p, keyword: text }))}
                placeholder="如：iPhone 16 Pro"
                maxLength={200}
              />

              {label('价格区间（可选）')}
              <View style={styles.priceRow}>
                <Input
                  value={form.priceMin}
                  onChangeText={(text) => setForm((p) => ({ ...p, priceMin: text }))}
                  placeholder="最低价"
                  keyboardType="decimal-pad"
                  style={styles.priceInput}
                />
                <Text style={[styles.priceSep, { color: c.textMuted }]}>-</Text>
                <Input
                  value={form.priceMax}
                  onChangeText={(text) => setForm((p) => ({ ...p, priceMax: text }))}
                  placeholder="最高价"
                  keyboardType="decimal-pad"
                  style={styles.priceInput}
                />
              </View>

              {form.monitorType === 'listing' && (
                <>
                  {label('上新天数（按发布时间筛选）')}
                  <View style={styles.chipWrap}>
                    {PUBLISH_DAYS.map((d) => {
                      const selected = form.publishDays === d.value;
                      return (
                        <Pressable
                          key={`${d.value}-${d.label}`}
                          onPress={() => setForm((p) => ({ ...p, publishDays: d.value }))}
                          style={[
                            styles.chip,
                            {
                              borderColor: selected ? c.primary : c.border,
                              backgroundColor: selected ? c.primary : 'transparent',
                            },
                          ]}
                        >
                          <Text style={[styles.chipText, { color: selected ? '#FFF' : c.text }]}>
                            {d.label}
                          </Text>
                        </Pressable>
                      );
                    })}
                  </View>
                </>
              )}

              <View style={styles.twoColRow}>
                <View style={styles.twoColItem}>
                  {label('任务间隔（分钟）', true)}
                  <Input
                    value={form.intervalText}
                    onChangeText={(text) => setForm((p) => ({ ...p, intervalText: text }))}
                    placeholder="5"
                    keyboardType="number-pad"
                  />
                </View>
                <View style={styles.twoColItem}>
                  {label('采集页数', true)}
                  <Input
                    value={form.collectPagesText}
                    onChangeText={(text) => setForm((p) => ({ ...p, collectPagesText: text }))}
                    placeholder="1"
                    keyboardType="number-pad"
                  />
                </View>
              </View>

              {label('代理API地址（选填）')}
              <Input
                value={form.proxyUrl}
                onChangeText={(text) => setForm((p) => ({ ...p, proxyUrl: text }))}
                placeholder="留空不使用代理"
                autoCapitalize="none"
              />

              {label('采集账号（可多选，留空回退兜底账号）')}
              <AccountPicker
                options={enabledAccounts}
                selected={form.accountIds}
                onToggle={(id) =>
                  setForm((p) => ({
                    ...p,
                    accountIds: p.accountIds.includes(id)
                      ? p.accountIds.filter((x) => x !== id)
                      : [...p.accountIds, id],
                  }))
                }
                c={c}
              />

              {label('下单账号（可多选，私信与下单共用）')}
              <AccountPicker
                options={enabledAccounts}
                selected={form.orderAccountIds}
                onToggle={(id) =>
                  setForm((p) => ({
                    ...p,
                    orderAccountIds: p.orderAccountIds.includes(id)
                      ? p.orderAccountIds.filter((x) => x !== id)
                      : [...p.orderAccountIds, id],
                  }))
                }
                c={c}
              />

              {label(form.orderAccountIds.length > 0 ? '私信内容（必填）' : '私信内容（配置下单账号后必填）')}
              <Input
                value={form.dmContent}
                onChangeText={(text) => setForm((p) => ({ ...p, dmContent: text }))}
                placeholder="命中商品后向卖家发送的私信内容"
                multiline
                maxLength={1000}
              />

              <View style={styles.twoColRow}>
                <View style={styles.twoColItem}>
                  {label('每次私信条数', true)}
                  <Input
                    value={form.dmBatchSizeText}
                    onChangeText={(text) => setForm((p) => ({ ...p, dmBatchSizeText: text }))}
                    placeholder="5"
                    keyboardType="number-pad"
                  />
                </View>
                <View style={styles.twoColItem}>
                  {label('每次下单条数', true)}
                  <Input
                    value={form.orderBatchSizeText}
                    onChangeText={(text) => setForm((p) => ({ ...p, orderBatchSizeText: text }))}
                    placeholder="5"
                    keyboardType="number-pad"
                  />
                </View>
              </View>

              <View style={styles.switchRow}>
                <View style={styles.switchInfo}>
                  <Text style={[styles.label, { color: c.textSecondary, marginTop: 0 }]}>
                    采集后直接下单
                  </Text>
                  <Text style={[styles.switchHint, { color: c.textMuted }]}>
                    开启后新采集商品跳过私信立即下单，需配置下单账号
                  </Text>
                </View>
                <Switch
                  value={form.directOrder}
                  onValueChange={(value) => setForm((p) => ({ ...p, directOrder: value }))}
                  trackColor={{ false: c.border, true: c.primary }}
                />
              </View>

              <View style={styles.switchRow}>
                <View style={styles.switchInfo}>
                  <Text style={[styles.label, { color: c.textSecondary, marginTop: 0 }]}>
                    创建后立即启用
                  </Text>
                  <Text style={[styles.switchHint, { color: c.textMuted }]}>
                    停用后可在列表中随时开启
                  </Text>
                </View>
                <Switch
                  value={form.enabled}
                  onValueChange={(value) => setForm((p) => ({ ...p, enabled: value }))}
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
                label={editingTask ? '保存修改' : '确认新建'}
                onPress={save}
                loading={saving}
                disabled={saving}
                style={styles.modalBtn}
              />
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      {/* 批量改账号 Modal */}
      <Modal
        visible={batchModal === 'accounts'}
        transparent
        animationType="fade"
        onRequestClose={() => setBatchModal(null)}
      >
        <Pressable style={styles.overlay} onPress={() => setBatchModal(null)}>
          <Pressable style={[styles.modal, styles.batchModal, { backgroundColor: c.surface }]} onPress={() => {}}>
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>批量修改账号</Text>
              <Pressable onPress={() => setBatchModal(null)} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>
            <View style={styles.chipWrap}>
              {[
                { value: 'account_ids', label: '采集账号' },
                { value: 'order_account_ids', label: '下单账号' },
              ].map((f) => {
                const selected = batchField === f.value;
                return (
                  <Pressable
                    key={f.value}
                    onPress={() => {
                      setBatchField(f.value as 'account_ids' | 'order_account_ids');
                      setBatchAccountIds([]);
                    }}
                    style={[
                      styles.chip,
                      {
                        borderColor: selected ? c.primary : c.border,
                        backgroundColor: selected ? c.primary : 'transparent',
                      },
                    ]}
                  >
                    <Text style={[styles.chipText, { color: selected ? '#FFF' : c.text }]}>
                      {f.label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            {label(batchField === 'account_ids' ? '选择采集账号（覆盖所选任务）' : '选择下单账号（覆盖所选任务）')}
            <ScrollView style={styles.batchPickerScroll}>
              <AccountPicker
                options={enabledAccounts}
                selected={batchAccountIds}
                onToggle={(id) =>
                  setBatchAccountIds((prev) =>
                    prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
                  )
                }
                c={c}
              />
            </ScrollView>
            <View style={styles.modalActions}>
              <Button label="取消" variant="ghost" onPress={() => setBatchModal(null)} style={styles.modalBtn} />
              <Button label="保存" onPress={submitBatchModal} loading={batchBusy} disabled={batchBusy} style={styles.modalBtn} />
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      {/* 批量改分类 Modal */}
      <Modal
        visible={batchModal === 'category'}
        transparent
        animationType="fade"
        onRequestClose={() => setBatchModal(null)}
      >
        <Pressable style={styles.overlay} onPress={() => setBatchModal(null)}>
          <Pressable style={[styles.modal, styles.batchModal, { backgroundColor: c.surface }]} onPress={() => {}}>
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>批量修改分类</Text>
              <Pressable onPress={() => setBatchModal(null)} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>
            {label('目标分类', true)}
            <ScrollView style={styles.batchPickerScroll}>
              {categories.length > 0 ? (
                <View style={styles.chipWrap}>
                  {categories.map((cat) => {
                    const selected = batchCategoryId === cat.id;
                    return (
                      <Pressable
                        key={cat.id}
                        onPress={() => setBatchCategoryId(cat.id)}
                        style={[
                          styles.chip,
                          {
                            borderColor: selected ? c.primary : c.border,
                            backgroundColor: selected ? c.primary : 'transparent',
                          },
                        ]}
                      >
                        <Text style={[styles.chipText, { color: selected ? '#FFF' : c.text }]} numberOfLines={1}>
                          {cat.name}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              ) : (
                <Text style={[styles.hint, { color: c.textMuted }]}>分类列表加载失败，请稍后重试</Text>
              )}
            </ScrollView>
            <View style={styles.modalActions}>
              <Button label="取消" variant="ghost" onPress={() => setBatchModal(null)} style={styles.modalBtn} />
              <Button label="保存" onPress={submitBatchModal} loading={batchBusy} disabled={batchBusy} style={styles.modalBtn} />
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      {/* 批量改私信内容 Modal */}
      <Modal
        visible={batchModal === 'dm'}
        transparent
        animationType="fade"
        onRequestClose={() => setBatchModal(null)}
      >
        <Pressable style={styles.overlay} onPress={() => setBatchModal(null)}>
          <Pressable style={[styles.modal, styles.batchModal, { backgroundColor: c.surface }]} onPress={() => {}}>
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>批量修改私信内容</Text>
              <Pressable onPress={() => setBatchModal(null)} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>
            {label('私信内容', true)}
            <Input
              value={batchDmContent}
              onChangeText={setBatchDmContent}
              placeholder="输入新的私信内容（覆盖所选任务）"
              multiline
              maxLength={1000}
            />
            <View style={styles.modalActions}>
              <Button label="取消" variant="ghost" onPress={() => setBatchModal(null)} style={styles.modalBtn} />
              <Button label="保存" onPress={submitBatchModal} loading={batchBusy} disabled={batchBusy} style={styles.modalBtn} />
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
    gap: spacing.sm,
  },
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.md, paddingBottom: 80 },
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
  taskNameRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  taskName: { ...typography.body, fontWeight: '600', flexShrink: 1 },
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
  // 多选勾选框
  checkBox: { marginRight: spacing.sm },
  checkBoxInner: {
    width: 22,
    height: 22,
    borderRadius: radius.sm,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkMark: { fontSize: 14, fontWeight: '700', color: '#FFF', lineHeight: 16 },
  // 批量操作栏
  batchBar: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
    gap: spacing.sm,
  },
  batchCount: { ...typography.small },
  batchActions: { flex: 1 },
  batchBtn: { minHeight: 38, paddingHorizontal: spacing.md, marginRight: spacing.sm },
  // 表单 Modal
  overlay: {
    flex: 1,
    justifyContent: 'center',
    padding: spacing.lg,
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  modal: { borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  batchModal: { maxHeight: '80%' },
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
  twoColRow: { flexDirection: 'row', gap: spacing.sm },
  twoColItem: { flex: 1 },
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
  batchPickerScroll: { maxHeight: 260 },
});
