import { useState, useCallback, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Switch,
  Modal,
  ScrollView,
  RefreshControl,
  Alert,
  ActivityIndicator,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { withTimeout } from '@/lib/timeout';
import { Button, Card, DetailRow, EmptyState, FilterTabs, SwipeableRow, Input, Loading, FormModal } from '@/components/ui';
import { PackageOpen, Search } from 'lucide-react-native';
import * as Clipboard from 'expo-clipboard';
import { colors, spacing, typography, radius, type ThemeColors } from '@/lib/theme';
import { formatDateTime, getStatusMeta, toneColors } from '@/lib/orderStatus';
import {
  getOrders,
  getOrderDetail,
  deleteOrder,
  fetchXianyuOrders,
  batchDeleteOrders,
  getAutoRateConfig,
  updateAutoRateConfig,
  batchRate,
  getConfirmReceiptConfig,
  updateConfirmReceiptConfig,
  type Order,
  type OrderDetail,
  type FetchXianyuStats,
  type AutoRateConfig,
  type ConfirmReceiptConfig,
} from '@/api/wrappers/orders-tab';
import { manualDelivery } from '@/api/wrappers/orders';
import { createPersonalBlacklist } from '@/api/wrappers/blacklist-manage';
import type { AccountOption } from '@/api/wrappers/accounts';
import { useAccountsStore } from '@/stores/accounts';
import { usePagedList } from '@/hooks/usePagedList';

const PAGE_SIZE = 20;
/** 搜索/筛选草稿 → 生效的防抖间隔 */
const FILTER_DEBOUNCE_MS = 450;
/** 单账号同步超时 */
const SYNC_ONE_TIMEOUT_MS = 120000;
/** 全账号同步超时（账号多时明显更久，对齐 web 的 10 分钟） */
const SYNC_ALL_TIMEOUT_MS = 600000;

/** 把细粒度订单状态归并为筛选 tab 分组 */
function groupStatus(status: string): string {
  if (status === 'pending_payment') return 'pending_payment';
  if (['pending_ship', 'pending', 'paid'].includes(status)) return 'pending_ship';
  if (status === 'shipped') return 'shipped';
  if (status === 'completed') return 'completed';
  if (['refunding', 'refunded'].includes(status)) return 'refund';
  return 'other';
}

const STATUS_TABS = [
  { key: 'all', label: '全部' },
  { key: 'pending_payment', label: '待付款' },
  { key: 'pending_ship', label: '待发货' },
  { key: 'shipped', label: '已发货' },
  { key: 'completed', label: '交易成功' },
  { key: 'refund', label: '退款' },
  { key: 'other', label: '其他' },
];

/** 发货方式服务端筛选 chips（key 对应后端 delivery_method 取值） */
const DELIVERY_FILTERS = [
  { key: '', label: '全部' },
  { key: 'none', label: '未发货' },
  { key: 'manual', label: '手动发货' },
  { key: 'auto', label: '自动发货' },
  { key: 'scheduled', label: '定时发货' },
];

/** 服务端筛选的生效值（防抖后提交给 getOrders 的那一份） */
interface AppliedFilters {
  accountId: string;
  search: string;
  delivery: string;
  startDate: string;
  endDate: string;
}

const INITIAL_FILTERS: AppliedFilters = {
  accountId: '',
  search: '',
  delivery: '',
  startDate: '',
  endDate: '',
};

/** 拼同步统计摘要：获取/新增/更新（+失败） */
function syncStatsSummary(stats: FetchXianyuStats): string {
  let s = `获取 ${stats.total_fetched} 条，新增 ${stats.new_inserted} 条，更新 ${stats.updated} 条`;
  if (stats.failed > 0) s += `，失败 ${stats.failed} 条`;
  return s;
}

/** 拼失败账号提示（最多展示 2 条，避免 Alert 过长） */
function syncErrorsText(stats: FetchXianyuStats): string {
  if (stats.errors.length === 0) return '';
  const head = stats.errors.slice(0, 2).join('；');
  return `\n失败账号：${head}${stats.errors.length > 2 ? ' 等' : ''}`;
}

/** 通用筛选 chip（账号/发货方式共用样式，与自动化设置弹窗一致） */
function FilterChip({
  label,
  active,
  onPress,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
}) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  return (
    <Pressable
      onPress={onPress}
      style={[
        styles.chip,
        {
          borderColor: active ? c.primary : c.border,
          backgroundColor: active ? c.primaryLight : 'transparent',
        },
      ]}
    >
      <Text
        style={[styles.chipText, { color: active ? c.primary : c.textSecondary }]}
        numberOfLines={1}
      >
        {label}
      </Text>
    </Pressable>
  );
}

/** 发货方式 → 中文文案（与 web statusMap 口径一致） */
function deliveryMethodText(m?: string): string {
  if (!m) return '未发货';
  if (m === 'manual') return '手动发货';
  if (m === 'auto') return '自动发货';
  if (m === 'scheduled') return '定时发货';
  return m;
}

/** 消息发送状态 → 中文文案 */
function sendStatusText(s?: string | null): string {
  if (!s) return '';
  if (s === 'success') return '发送成功';
  if (s === 'failed') return '发送失败';
  if (s === 'timeout') return '超时';
  return '待确认';
}

/**
 * 订单卡片主体（普通模式与多选模式共用）。
 * selected 传 undefined 表示非多选态（不渲染勾选框），传 boolean 表示多选态。
 */
function OrderCardBody({ item, selected }: { item: Order; selected?: boolean }) {
  const scheme = useColorScheme();
  const dark = scheme === 'dark';
  const c: ThemeColors = colors[dark ? 'dark' : 'light'];
  const meta = getStatusMeta(item.status);
  const tc = toneColors(meta.tone, dark);
  return (
    <Card style={[styles.orderCard, selected === true && { borderColor: c.primary }]}>
      <View style={styles.titleRow}>
        {selected !== undefined ? (
          <View
            style={[
              styles.checkbox,
              {
                borderColor: selected ? c.primary : c.border,
                backgroundColor: selected ? c.primary : 'transparent',
              },
            ]}
          >
            {selected ? <Text style={styles.checkboxCheck}>✓</Text> : null}
          </View>
        ) : null}
        <Text
          style={[styles.title, { color: c.text, flex: 1 }]}
          numberOfLines={2}
        >
          {item.item_title || '未命名商品'}
        </Text>
        <View style={[styles.tag, { backgroundColor: tc.bg }]}>
          <Text style={[styles.tagText, { color: tc.fg }]}>{meta.label}</Text>
        </View>
      </View>
      <View style={styles.metaRow}>
        <Text style={[styles.amount, { color: c.warning }]}>
          ¥{item.amount || '--'}
        </Text>
        <Text style={[styles.qty, { color: c.textSecondary }]}>
          ×{item.quantity}
        </Text>
        {item.placed_at ? (
          <Text style={[styles.subText, { color: c.textMuted }]}>
            {formatDateTime(item.placed_at)}
          </Text>
        ) : null}
      </View>
      <View style={styles.subRow}>
        <Text
          style={[styles.subText, { color: c.textMuted }]}
          numberOfLines={1}
        >
          买家：{item.buyer_nick || item.buyer_id || '--'}
        </Text>
        <Text style={[styles.orderNo, { color: c.textMuted }]} numberOfLines={1}>
          {item.order_no}
        </Text>
      </View>
    </Card>
  );
}

// ---------------------------------------------------------------------------

export default function OrdersPage() {
  const scheme = useColorScheme();
  const dark = scheme === 'dark';
  const c: ThemeColors = colors[dark ? 'dark' : 'light'];

  // 服务端筛选：草稿输入值（即时响应用户输入）
  const [searchQuery, setSearchQuery] = useState('');
  const [filterAccountId, setFilterAccountId] = useState('');
  const [filterDelivery, setFilterDelivery] = useState('');
  const [filterStartDate, setFilterStartDate] = useState('');
  const [filterEndDate, setFilterEndDate] = useState('');
  const [filtersExpanded, setFiltersExpanded] = useState(false);
  // 防抖后的生效值：真正传给 getOrders 的那一份
  const [appliedFilters, setAppliedFilters] = useState<AppliedFilters>(INITIAL_FILTERS);

  // 订单列表（page 分页）：翻页/竞态序号/跨页去重/hasMore 收口均在 usePagedList 内部处理
  const {
    items: orders,
    loading,
    refreshing,
    loadingMore,
    refresh: refreshOrders,
    loadMore: loadMoreOrders,
  } = usePagedList<Order>({
    mode: 'page',
    pageSize: PAGE_SIZE,
    dedupeBy: (o) => o.order_no,
    fetchPage: async ({ page = 1, limit = PAGE_SIZE }) => {
      const resp = await getOrders(page, limit, {
        cookieId: appliedFilters.accountId || undefined,
        search: appliedFilters.search || undefined,
        deliveryMethod: appliedFilters.delivery || undefined,
        startDate: appliedFilters.startDate || undefined,
        endDate: appliedFilters.endDate || undefined,
      });
      return { items: resp.data, total: resp.total };
    },
    onError: (e, phase) => {
      console.error('加载订单失败', e);
      if (phase === 'refresh') Alert.alert('加载失败', e.message);
    },
  });

  // 草稿 → 防抖 → 生效（450ms 内连续输入只发一次请求）
  useEffect(() => {
    const t = setTimeout(() => {
      setAppliedFilters((prev) => {
        const next: AppliedFilters = {
          accountId: filterAccountId,
          search: searchQuery.trim(),
          delivery: filterDelivery,
          startDate: filterStartDate.trim(),
          endDate: filterEndDate.trim(),
        };
        const same =
          prev.accountId === next.accountId &&
          prev.search === next.search &&
          prev.delivery === next.delivery &&
          prev.startDate === next.startDate &&
          prev.endDate === next.endDate;
        return same ? prev : next;
      });
    }, FILTER_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [filterAccountId, searchQuery, filterDelivery, filterStartDate, filterEndDate]);

  // 筛选生效后回第 1 页重新拉取。首跑（初始空筛选）跳过，交给 usePagedList 挂载首载
  const filterRunSeqRef = useRef(0);
  const appliedKey = `${appliedFilters.accountId}|${appliedFilters.search}|${appliedFilters.delivery}|${appliedFilters.startDate}|${appliedFilters.endDate}`;
  useEffect(() => {
    filterRunSeqRef.current += 1;
    if (filterRunSeqRef.current === 1) return;
    refreshOrders();
  }, [appliedKey, refreshOrders]);

  // 状态筛选（客户端按 tab 分组过滤当前已加载订单，保留原能力；搜索已上移到服务端）
  const [statusFilter, setStatusFilter] = useState('all');
  const filteredOrders = orders.filter(
    (o) => statusFilter === 'all' || groupStatus(o.status) === statusFilter,
  );

  // 多选批量删除
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchDeleting, setBatchDeleting] = useState(false);

  const enterSelectMode = useCallback((firstId: string) => {
    if (!firstId) return;
    setSelectMode(true);
    setSelectedIds(new Set([firstId]));
  }, []);

  const exitSelectMode = useCallback(() => {
    setSelectMode(false);
    setSelectedIds(new Set());
  }, []);

  const toggleSelect = useCallback((id: string) => {
    if (!id) return;
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

  const allSelected =
    filteredOrders.length > 0 &&
    filteredOrders.every((o) => !o.id || selectedIds.has(o.id));

  const toggleSelectAll = () => {
    if (allSelected) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(
        new Set(filteredOrders.map((o) => o.id).filter(Boolean)),
      );
    }
  };

  const doBatchDelete = useCallback(() => {
    const ids = Array.from(selectedIds).filter(Boolean);
    if (ids.length === 0) return;
    Alert.alert(
      '批量删除确认',
      `确定删除选中的 ${ids.length} 个订单吗？删除后无法恢复。`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: async () => {
            setBatchDeleting(true);
            try {
              const res = await batchDeleteOrders(ids);
              Alert.alert(
                '删除完成',
                res.message || `成功 ${res.deleted} 条，失败 ${res.failed} 条`,
              );
              exitSelectMode();
              await refreshOrders();
            } catch (e) {
              Alert.alert('批量删除失败', (e as Error).message);
            } finally {
              setBatchDeleting(false);
            }
          },
        },
      ],
      { cancelable: true },
    );
  }, [selectedIds, exitSelectMode, refreshOrders]);

  // 订单详情弹窗
  const [detailVisible, setDetailVisible] = useState(false);
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 账号列表（用于筛选栏、同步与设置）
  const accounts = useAccountsStore((s) => s.options);
  const loadAccountOptions = useAccountsStore((s) => s.load);

  // 挂载时预取账号（筛选栏 chips 需要；TTL 内复用缓存，不重复请求）
  useEffect(() => {
    loadAccountOptions().catch(() => {
      // 静默失败：筛选栏退化为只有「全部账号」，同步入口会再次尝试加载
    });
  }, [loadAccountOptions]);

  // 同步闲鱼订单
  const [syncPickerVisible, setSyncPickerVisible] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [syncScopeAll, setSyncScopeAll] = useState(false);
  // 同步代际 token：取消时自增使在途作废（per-invocation generation，替代共享布尔）
  const syncGenRef = useRef(0);

  // 自动化设置弹窗
  const [settingsVisible, setSettingsVisible] = useState(false);
  const [settingsTab, setSettingsTab] = useState<'rate' | 'receipt'>('rate');
  const [settingsAccountId, setSettingsAccountId] = useState<string | null>(null);
  // 自动评价
  const [rateConfig, setRateConfig] = useState<AutoRateConfig>({
    enabled: false,
    text: '',
    api_mode: false,
  });
  const [rateLoading, setRateLoading] = useState(false);
  const [rateSaving, setRateSaving] = useState(false);
  const [batchRating, setBatchRating] = useState(false);
  // 确认收货
  const [receiptConfig, setReceiptConfig] = useState<ConfirmReceiptConfig>({
    enabled: false,
    text: '',
    image_url: '',
  });
  const [receiptLoading, setReceiptLoading] = useState(false);
  const [receiptSaving, setReceiptSaving] = useState(false);

  // ---- 订单详情 ----
  const openDetail = useCallback(async (orderNo: string) => {
    setDetailVisible(true);
    setDetail(null);
    setDetailLoading(true);
    try {
      const d = await getOrderDetail(orderNo);
      setDetail(d);
    } catch (e) {
      Alert.alert('获取详情失败', (e as Error).message);
      setDetailVisible(false);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  // ---- 同步闲鱼订单（单账号 / 全部账号共用，完成后展示统计）----
  const runSync = useCallback(
    async (scopeAll: boolean, account: AccountOption | null) => {
      setSyncPickerVisible(false);
      setSyncing(true);
      setSyncScopeAll(scopeAll);
      // 代际 token：取消时自增使在途作废，避免"取消→立即重 Sync"时旧请求弹 Alert 或提前关遮罩
      const myGen = ++syncGenRef.current;
      try {
        const task = scopeAll
          ? fetchXianyuOrders(undefined)
          : fetchXianyuOrders(account!.id);
        // 账号离线时后端会阻塞：单账号 120s、全部账号 600s 超时兜底
        const stats = await withTimeout(
          task,
          scopeAll ? SYNC_ALL_TIMEOUT_MS : SYNC_ONE_TIMEOUT_MS,
          '同步超时，请确认账号在线后重试',
        );
        if (syncGenRef.current !== myGen) return; // 已被取消或被新同步取代
        const summary = syncStatsSummary(stats);
        const errText = syncErrorsText(stats);
        Alert.alert(
          scopeAll ? '同步全部完成' : '同步完成',
          scopeAll
            ? `共处理 ${stats.accounts_processed} 个账号：${summary}${errText}`
            : `账号「${account!.remark || account!.id}」：${summary}${errText}`,
        );
        await refreshOrders();
      } catch (e) {
        if (syncGenRef.current !== myGen) return;
        Alert.alert('同步失败', (e as Error).message);
      } finally {
        // 仅当前代才动 syncing 状态，避免把新同步的遮罩提前关闭
        if (syncGenRef.current === myGen) setSyncing(false);
      }
    },
    [refreshOrders],
  );

  const openSync = useCallback(async () => {
    try {
      await loadAccountOptions();
    } catch (e) {
      Alert.alert('加载账号失败', (e as Error).message);
      return;
    }
    if (useAccountsStore.getState().options.length === 0) {
      Alert.alert('暂无账号', '请先在账号管理中添加账号');
      return;
    }
    setSyncPickerVisible(true);
  }, [loadAccountOptions]);

  const doSync = useCallback(
    (account: AccountOption) => {
      runSync(false, account);
    },
    [runSync],
  );

  const doSyncAll = useCallback(() => {
    runSync(true, null);
  }, [runSync]);

  // ---- 筛选重置 ----
  const resetFilters = useCallback(() => {
    setSearchQuery('');
    setFilterAccountId('');
    setFilterDelivery('');
    setFilterStartDate('');
    setFilterEndDate('');
  }, []);

  const activeFilterCount = [
    filterAccountId,
    filterDelivery,
    filterStartDate.trim(),
    filterEndDate.trim(),
  ].filter(Boolean).length;

  // ---- 自动化设置 ----
  const loadSettingsConfig = useCallback(
    async (accountId: string, tab: 'rate' | 'receipt') => {
      if (tab === 'rate') {
        setRateLoading(true);
        try {
          setRateConfig(await getAutoRateConfig(accountId));
        } catch (e) {
          Alert.alert('加载自动评价配置失败', (e as Error).message);
        } finally {
          setRateLoading(false);
        }
      } else {
        setReceiptLoading(true);
        try {
          setReceiptConfig(await getConfirmReceiptConfig(accountId));
        } catch (e) {
          Alert.alert('加载确认收货配置失败', (e as Error).message);
        } finally {
          setReceiptLoading(false);
        }
      }
    },
    [],
  );

  const openSettings = useCallback(async () => {
    try {
      await loadAccountOptions();
    } catch (e) {
      Alert.alert('加载账号失败', (e as Error).message);
      return;
    }
    const opts = useAccountsStore.getState().options;
    if (opts.length === 0) {
      Alert.alert('暂无账号', '请先在账号管理中添加账号');
      return;
    }
    setSettingsTab('rate');
    setSettingsVisible(true);
    const firstId = opts[0].id;
    setSettingsAccountId(firstId);
    await loadSettingsConfig(firstId, 'rate');
  }, [loadAccountOptions, loadSettingsConfig]);

  const selectSettingsAccount = useCallback(
    (accountId: string) => {
      setSettingsAccountId(accountId);
      loadSettingsConfig(accountId, settingsTab);
    },
    [settingsTab, loadSettingsConfig],
  );

  const switchSettingsTab = useCallback(
    (tab: 'rate' | 'receipt') => {
      setSettingsTab(tab);
      if (settingsAccountId) loadSettingsConfig(settingsAccountId, tab);
    },
    [settingsAccountId, loadSettingsConfig],
  );

  const saveRate = useCallback(async () => {
    if (!settingsAccountId) return;
    setRateSaving(true);
    try {
      await updateAutoRateConfig(settingsAccountId, rateConfig);
      Alert.alert('保存成功', '已更新自动评价配置');
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setRateSaving(false);
    }
  }, [settingsAccountId, rateConfig]);

  const saveReceipt = useCallback(async () => {
    if (!settingsAccountId) return;
    setReceiptSaving(true);
    try {
      await updateConfirmReceiptConfig(settingsAccountId, receiptConfig);
      Alert.alert('保存成功', '已更新确认收货配置');
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setReceiptSaving(false);
    }
  }, [settingsAccountId, receiptConfig]);

  const doBatchRate = useCallback(async () => {
    if (accounts.length === 0) {
      Alert.alert('暂无账号', '请先在账号管理中添加账号');
      return;
    }
    Alert.alert(
      '批量评价确认',
      `将对全部 ${accounts.length} 个账号执行补评价，是否继续？`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '继续',
          onPress: async () => {
            setBatchRating(true);
            try {
              await batchRate(accounts.map((a) => a.id));
              Alert.alert('批量评价完成', `已对 ${accounts.length} 个账号执行补评价`);
            } catch (e) {
              Alert.alert('批量评价失败', (e as Error).message);
            } finally {
              setBatchRating(false);
            }
          },
        },
      ],
      { cancelable: true },
    );
  }, [accounts]);

  // ---- 渲染订单项（useCallback 避免每次渲染重建导致 FlatList 全量重渲染）----
  const renderItem = useCallback(
    ({ item }: { item: Order }) => {
      // 多选模式：整卡可点切换勾选，不再提供滑动操作
      if (selectMode) {
        const selected = !!item.id && selectedIds.has(item.id);
        return (
          <Pressable onPress={() => toggleSelect(item.id)}>
            <OrderCardBody item={item} selected={selected} />
          </Pressable>
        );
      }

      // 发货守卫：已发货/已完成/卡券已发送时禁用（灰色 + 不可点）
      const deliveryDisabled =
        item.status === 'shipped' ||
        item.status === 'completed' ||
        !!item.card_only_delivered;
      return (
        <SwipeableRow
          onPress={() => openDetail(item.order_no)}
          actions={[
            {
              label: '复制单号',
              bg: c.textSecondary,
              onPress: async () => {
                await Clipboard.setStringAsync(item.order_no);
                Alert.alert('已复制', item.order_no);
              },
            },
            {
              label: '手动发货',
              bg: deliveryDisabled ? c.surfaceAlt : c.info,
              fg: deliveryDisabled ? c.textMuted : '#FFFFFF',
              onPress: () => {
                if (deliveryDisabled) return; // 当前状态不可发货
                // 二次确认：手动发货会真实发送卡券给买家，误触代价高
                Alert.alert(
                  '手动发货确认',
                  `确定对订单 ${item.order_no} 手动发货吗？发货后会向买家发送卡券内容。`,
                  [
                    { text: '取消', style: 'cancel' },
                    {
                      text: '确认发货',
                      onPress: async () => {
                        try {
                          await manualDelivery(item.order_no);
                          Alert.alert('发货成功', `订单 ${item.order_no} 已手动发货`);
                          refreshOrders();
                        } catch (e) {
                          Alert.alert('发货失败', (e as Error).message);
                        }
                      },
                    },
                  ],
                  { cancelable: true },
                );
              },
            },
            {
              label: '拉黑',
              bg: c.warning,
              onPress: () => {
                const buyer = item.buyer_id || item.buyer_nick || '';
                if (!buyer) {
                  Alert.alert('无法拉黑', '该订单缺少买家信息');
                  return;
                }
                Alert.alert(
                  '确认拉黑',
                  `确定将买家「${item.buyer_nick || item.buyer_id}」加入黑名单吗？`,
                  [
                    { text: '取消', style: 'cancel' },
                    {
                      text: '拉黑',
                      style: 'destructive',
                      onPress: async () => {
                        try {
                          const res = await createPersonalBlacklist(buyer, undefined, undefined);
                          Alert.alert(
                            '已拉黑',
                            `已将买家「${item.buyer_nick || buyer}」加入黑名单（新增 ${res.count} 条）`,
                          );
                        } catch (e) {
                          Alert.alert('拉黑失败', (e as Error).message);
                        }
                      },
                    },
                  ],
                  { cancelable: true },
                );
              },
            },
            {
              label: '删除',
              bg: c.error,
              onPress: () => {
                if (!item.id) {
                  Alert.alert('无法删除', '该订单缺少主键信息');
                  return;
                }
                Alert.alert(
                  '删除确认',
                  `确定删除订单 ${item.order_no} 吗？删除后无法恢复。`,
                  [
                    { text: '取消', style: 'cancel' },
                    {
                      text: '删除',
                      style: 'destructive',
                      onPress: async () => {
                        try {
                          await deleteOrder(item.id);
                          Alert.alert('删除成功', `订单 ${item.order_no} 已删除`);
                          refreshOrders();
                        } catch (e) {
                          Alert.alert('删除失败', (e as Error).message);
                        }
                      },
                    },
                  ],
                  { cancelable: true },
                );
              },
            },
            { label: '详情', bg: c.primary, onPress: () => openDetail(item.order_no) },
          ]}
        >
          {/* 内层 Pressable 只处理长按（进入多选）；普通点击仍穿透交给外层打开详情 */}
          <Pressable
            onLongPress={() => enterSelectMode(item.id)}
            delayLongPress={400}
          >
            <OrderCardBody item={item} />
          </Pressable>
        </SwipeableRow>
      );
    },
    [selectMode, selectedIds, toggleSelect, enterSelectMode, openDetail, refreshOrders, c.text, c.error, c.info, c.surfaceAlt, c.textSecondary, c.textMuted, c.warning, c.primary, dark],
  );

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
        <Loading label="加载订单..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: c.text }]}>订单管理</Text>
        <View style={{ flexDirection: 'row', gap: spacing.sm }}>
          <Button label="同步闲鱼" onPress={openSync} />
          <Button label="设置" onPress={openSettings} variant="secondary" />
        </View>
      </View>

      {/* 搜索栏（服务端搜索，防抖后生效） */}
      <View style={[styles.searchBar, { backgroundColor: c.surface, borderBottomColor: c.border }]}>
        <Search size={16} stroke={c.textMuted} />
        <TextInput
          value={searchQuery}
          onChangeText={setSearchQuery}
          placeholder="搜索订单号/商品/买家"
          placeholderTextColor={c.textMuted}
          style={[styles.searchInput, { color: c.text }]}
        />
        {searchQuery ? (
          <Pressable onPress={() => setSearchQuery('')} hitSlop={8}>
            <Text style={{ color: c.textMuted, fontSize: 18 }}>×</Text>
          </Pressable>
        ) : null}
        <Pressable
          onPress={() => setFiltersExpanded((v) => !v)}
          hitSlop={8}
          style={styles.filterToggle}
        >
          <Text
            style={[
              styles.filterToggleText,
              { color: activeFilterCount > 0 ? c.primary : c.textSecondary },
            ]}
          >
            筛选{activeFilterCount > 0 ? `(${activeFilterCount})` : ''}
          </Text>
        </Pressable>
      </View>

      {/* 高级筛选面板：账号 / 发货方式 / 日期范围（均为服务端筛选） */}
      {filtersExpanded ? (
        <View
          style={[
            styles.filterPanel,
            { backgroundColor: c.surface, borderBottomColor: c.border },
          ]}
        >
          <Text style={[styles.filterLabel, { color: c.textSecondary }]}>账号</Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.chipsScroll}
          >
            <FilterChip
              label="全部账号"
              active={filterAccountId === ''}
              onPress={() => setFilterAccountId('')}
            />
            {accounts.map((a) => (
              <FilterChip
                key={a.id}
                label={a.remark || a.id}
                active={filterAccountId === a.id}
                onPress={() =>
                  setFilterAccountId((prev) => (prev === a.id ? '' : a.id))
                }
              />
            ))}
          </ScrollView>

          <Text style={[styles.filterLabel, { color: c.textSecondary }]}>
            发货方式
          </Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            contentContainerStyle={styles.chipsScroll}
          >
            {DELIVERY_FILTERS.map((t) => (
              <FilterChip
                key={t.key}
                label={t.label}
                active={filterDelivery === t.key}
                onPress={() => setFilterDelivery(t.key)}
              />
            ))}
          </ScrollView>

          <Text style={[styles.filterLabel, { color: c.textSecondary }]}>
            日期范围（YYYY-MM-DD）
          </Text>
          <View style={styles.dateRow}>
            <Input
              value={filterStartDate}
              onChangeText={setFilterStartDate}
              placeholder="开始 2026-01-01"
              maxLength={10}
              autoCapitalize="none"
              autoCorrect={false}
              style={styles.dateInput}
            />
            <Text style={[styles.dateDivider, { color: c.textMuted }]}>至</Text>
            <Input
              value={filterEndDate}
              onChangeText={setFilterEndDate}
              placeholder="结束 2026-12-31"
              maxLength={10}
              autoCapitalize="none"
              autoCorrect={false}
              style={styles.dateInput}
            />
          </View>

          {activeFilterCount > 0 || searchQuery ? (
            <Pressable onPress={resetFilters} hitSlop={8} style={styles.resetBtn}>
              <Text style={[styles.resetBtnText, { color: c.error }]}>
                重置全部筛选
              </Text>
            </Pressable>
          ) : null}
        </View>
      ) : null}

      {/* 状态筛选 */}
      <FilterTabs tabs={STATUS_TABS} active={statusFilter} onChange={setStatusFilter} />

      {/* 多选模式操作条 */}
      {selectMode ? (
        <View
          style={[
            styles.batchBar,
            { backgroundColor: c.surface, borderBottomColor: c.border },
          ]}
        >
          <Pressable onPress={exitSelectMode} hitSlop={8}>
            <Text style={[styles.batchBarBtn, { color: c.textSecondary }]}>
              取消
            </Text>
          </Pressable>
          <Text style={[styles.batchBarText, { color: c.text }]}>
            已选 {selectedIds.size} 项
          </Text>
          <View style={styles.batchBarActions}>
            <Pressable onPress={toggleSelectAll} hitSlop={8}>
              <Text style={[styles.batchBarBtn, { color: c.primary }]}>
                {allSelected ? '取消全选' : '全选'}
              </Text>
            </Pressable>
            <Button
              label={`删除(${selectedIds.size})`}
              variant="danger"
              onPress={doBatchDelete}
              loading={batchDeleting}
              disabled={batchDeleting || selectedIds.size === 0}
              style={styles.batchDeleteBtn}
            />
          </View>
        </View>
      ) : null}

      <FlatList
        data={filteredOrders}
        keyExtractor={(item) => item.order_no}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={refreshOrders}
            colors={[c.primary]}
            tintColor={c.primary}
          />
        }
        onEndReached={loadMoreOrders}
        onEndReachedThreshold={0.3}
        // 长列表调优：缩小渲染窗口 + 裁剪屏外子视图，降低内存与渲染压力
        windowSize={7}
        removeClippedSubviews
        renderItem={renderItem}
        ListEmptyComponent={
          <EmptyState
            icon={PackageOpen}
            title="暂无订单"
            message="下拉刷新或点击右上角「同步闲鱼」获取订单"
          />
        }
        ListFooterComponent={
          loadingMore ? (
            <Text style={[styles.loadingMore, { color: c.textMuted }]}>
              加载中...
            </Text>
          ) : null
        }
        contentContainerStyle={styles.listContent}
      />

      {/* 订单详情弹窗 */}
      <Modal
        visible={detailVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setDetailVisible(false)}
      >
        <Pressable
          style={styles.modalOverlay}
          onPress={() => setDetailVisible(false)}
        >
          <Pressable
            style={[styles.modalCard, { backgroundColor: c.surface, borderColor: c.border }]}
            onPress={() => {}}
          >
            <View style={[styles.modalHeader, { borderBottomColor: c.border }]}>
              <Text style={[styles.modalTitle, { color: c.text }]}>订单详情</Text>
              <Pressable
                onPress={() => setDetailVisible(false)}
                hitSlop={8}
              >
                <Text style={[styles.closeBtn, { color: c.textSecondary }]}>
                  ✕
                </Text>
              </Pressable>
            </View>

            {detailLoading ? (
              <View style={styles.modalLoading}>
                <Loading label="加载详情..." />
              </View>
            ) : detail ? (
              <ScrollView
                style={styles.modalBody}
                contentContainerStyle={styles.modalBodyContent}
              >
                <Text style={[styles.title, { color: c.text }]} numberOfLines={3}>
                  {detail.item_title || detail.order_no}
                </Text>
                <View style={styles.detailGrid}>
                  <DetailRow
                    label="实收金额"
                    value={`¥${detail.amount || '--'}`}
                    c={c}
                  />
                  <DetailRow label="数量" value={String(detail.quantity)} c={c} />
                  <DetailRow
                    label="订单状态"
                    value={getStatusMeta(detail.status).label}
                    c={c}
                  />
                  <DetailRow
                    label="规格"
                    value={
                      detail.spec_name
                        ? `${detail.spec_name}${detail.spec_value ? '：' + detail.spec_value : ''}`
                        : '无'
                    }
                    c={c}
                  />
                  <DetailRow
                    label="收货人"
                    value={detail.receiver_name || '未获取'}
                    c={c}
                  />
                  <DetailRow
                    label="联系电话"
                    value={detail.receiver_phone || '未获取'}
                    c={c}
                  />
                  <DetailRow
                    label="收货地址"
                    value={detail.receiver_address || '未获取'}
                    c={c}
                  />
                  <DetailRow label="订单号" value={detail.order_no} c={c} />
                  <DetailRow
                    label="账号ID"
                    value={detail.account_id || '未获取'}
                    c={c}
                  />
                  <DetailRow
                    label="买家ID"
                    value={detail.buyer_id || '未获取'}
                    c={c}
                  />
                  <DetailRow
                    label="买家昵称"
                    value={detail.buyer_nick || '无'}
                    c={c}
                  />
                  <DetailRow
                    label="会话ID"
                    value={detail.chat_id || '无'}
                    c={c}
                  />
                  <DetailRow
                    label="订单类型"
                    value={detail.is_agent_order ? '代销' : '自营'}
                    c={c}
                  />
                  <DetailRow
                    label="是否小刀"
                    value={detail.is_bargain ? '是' : '否'}
                    c={c}
                  />
                  <DetailRow
                    label="求小红花"
                    value={detail.is_red_flower ? '是' : '否'}
                    c={c}
                  />
                  <DetailRow
                    label="发货方式"
                    value={deliveryMethodText(detail.delivery_method)}
                    c={c}
                  />
                  {detail.delivery_content ? (
                    <DetailRow
                      label="发货内容"
                      value={detail.delivery_content}
                      c={c}
                    />
                  ) : null}
                  {detail.delivery_fail_reason ? (
                    <DetailRow
                      label="失败原因"
                      value={detail.delivery_fail_reason}
                      c={c}
                    />
                  ) : null}
                  {detail.delivery_send_status ? (
                    <DetailRow
                      label="发送状态"
                      value={sendStatusText(detail.delivery_send_status)}
                      c={c}
                    />
                  ) : null}
                  {detail.delivery_send_fail_reason ? (
                    <DetailRow
                      label="发送失败原因"
                      value={detail.delivery_send_fail_reason}
                      c={c}
                    />
                  ) : null}
                  {detail.placed_at ? (
                    <DetailRow
                      label="下单时间"
                      value={formatDateTime(detail.placed_at)}
                      c={c}
                    />
                  ) : null}
                  {detail.created_at ? (
                    <DetailRow
                      label="创建时间"
                      value={formatDateTime(detail.created_at)}
                      c={c}
                    />
                  ) : null}
                  {detail.updated_at ? (
                    <DetailRow
                      label="更新时间"
                      value={formatDateTime(detail.updated_at)}
                      c={c}
                    />
                  ) : null}
                </View>
              </ScrollView>
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>

      {/* 同步账号选择弹窗 */}
      <Modal
        visible={syncPickerVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setSyncPickerVisible(false)}
      >
        <Pressable
          style={styles.modalOverlay}
          onPress={() => setSyncPickerVisible(false)}
        >
          <Pressable
            style={[styles.modalCard, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>
                选择账号同步
              </Text>
              <Pressable
                onPress={() => setSyncPickerVisible(false)}
                hitSlop={8}
              >
                <Text style={[styles.closeBtn, { color: c.textSecondary }]}>
                  ✕
                </Text>
              </Pressable>
            </View>
            <Text style={[styles.modalHint, { color: c.textSecondary }]}>
              同步闲鱼订单可能耗时较长，请耐心等待
            </Text>
            <FlatList
              data={accounts}
              keyExtractor={(item) => item.id}
              renderItem={({ item }) => (
                <Pressable
                  style={[styles.accountItem, { borderColor: c.border }]}
                  onPress={() => doSync(item)}
                >
                  <Text
                    style={[styles.accountItemText, { color: c.text }]}
                    numberOfLines={1}
                  >
                    {item.remark || item.id}
                  </Text>
                  <Text style={[styles.accountAction, { color: c.primary }]}>
                    同步
                  </Text>
                </Pressable>
              )}
              // 一键同步全部账号：cookie_id 留空由后端遍历所有启用账号
              ListHeaderComponent={
                <Pressable
                  style={[styles.accountItem, { borderColor: c.border }]}
                  onPress={doSyncAll}
                >
                  <Text
                    style={[
                      styles.accountItemText,
                      { color: c.text, fontWeight: '600' },
                    ]}
                    numberOfLines={1}
                  >
                    全部账号（一键同步）
                  </Text>
                  <Text style={[styles.accountAction, { color: c.primary }]}>
                    同步
                  </Text>
                </Pressable>
              }
              style={styles.accountList}
            />
          </Pressable>
        </Pressable>
      </Modal>

      {/* 同步进行中遮罩 */}
      <Modal visible={syncing} transparent animationType="fade" onRequestClose={() => { syncGenRef.current++; setSyncing(false); }}>
        <View style={styles.syncOverlay}>
          <View style={[styles.syncCard, { backgroundColor: c.surface }]}>
            <ActivityIndicator size="large" color={c.primary} />
            <Text style={[styles.syncText, { color: c.text }]}>
              {syncScopeAll ? '正在同步全部账号的订单...' : '正在同步闲鱼订单...'}
            </Text>
            <Text style={[styles.syncHint, { color: c.textMuted }]}>
              该过程可能需要数分钟
            </Text>
            <Pressable
              onPress={() => { syncGenRef.current++; setSyncing(false); }}
              style={({ pressed }) => [
                styles.syncCancelBtn,
                { backgroundColor: pressed ? c.border : c.background, borderColor: c.border },
              ]}
            >
              <Text style={[styles.syncCancelText, { color: c.textSecondary }]}>取消</Text>
            </Pressable>
          </View>
        </View>
      </Modal>

      {/* 自动化设置弹窗 */}
      <FormModal
        visible={settingsVisible}
        onClose={() => setSettingsVisible(false)}
        title="自动化设置"
        contentStyle={{ maxHeight: '85%' }}
      >
        <ScrollView
          style={styles.settingsBody}
          contentContainerStyle={styles.settingsBodyContent}
        >
          {/* 分段切换 */}
          <View style={[styles.segmented, { backgroundColor: c.background }]}>
            <Pressable
              style={[
                styles.segmentBtn,
                settingsTab === 'rate' && { backgroundColor: c.primary },
              ]}
              onPress={() => switchSettingsTab('rate')}
            >
              <Text
                style={[
                  styles.segmentText,
                  {
                    color: settingsTab === 'rate' ? '#FFFFFF' : c.textSecondary,
                  },
                ]}
              >
                自动评价
              </Text>
            </Pressable>
            <Pressable
              style={[
                styles.segmentBtn,
                settingsTab === 'receipt' && { backgroundColor: c.primary },
              ]}
              onPress={() => switchSettingsTab('receipt')}
            >
              <Text
                style={[
                  styles.segmentText,
                  {
                    color:
                      settingsTab === 'receipt' ? '#FFFFFF' : c.textSecondary,
                  },
                ]}
              >
                确认收货
              </Text>
            </Pressable>
          </View>

          {/* 账号选择 */}
          <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
            选择账号
          </Text>
          <ScrollView
            horizontal
            showsHorizontalScrollIndicator={false}
            style={styles.chipsRow}
            contentContainerStyle={{
              gap: spacing.sm,
              paddingVertical: spacing.xs,
            }}
          >
            {accounts.map((a) => {
              const active = settingsAccountId === a.id;
              return (
                <Pressable
                  key={a.id}
                  style={[
                    styles.chip,
                    {
                      borderColor: active ? c.primary : c.border,
                      backgroundColor: active ? c.primaryLight : 'transparent',
                    },
                  ]}
                  onPress={() => selectSettingsAccount(a.id)}
                >
                  <Text
                    style={[
                      styles.chipText,
                      { color: active ? c.primary : c.textSecondary },
                    ]}
                    numberOfLines={1}
                  >
                    {a.remark || a.id}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>

          {/* 自动评价表单 */}
          {settingsTab === 'rate' ? (
            rateLoading ? (
              <View style={styles.inlineLoading}>
                <ActivityIndicator color={c.primary} />
              </View>
            ) : (
              <View style={styles.formGroup}>
                <View style={styles.toggleRow}>
                  <Text style={[styles.toggleLabel, { color: c.text }]}>
                    启用自动评价
                  </Text>
                  <Switch
                    value={rateConfig.enabled}
                    onValueChange={(v) =>
                      setRateConfig((p) => ({ ...p, enabled: v }))
                    }
                    trackColor={{ false: c.border, true: c.primary }}
                  />
                </View>
                <View style={styles.fieldGroup}>
                  <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
                    评价文案
                  </Text>
                  <Input
                    value={rateConfig.text}
                    onChangeText={(v) =>
                      setRateConfig((p) => ({ ...p, text: v }))
                    }
                    placeholder="请输入评价文案"
                    multiline
                  />
                </View>
                <View style={styles.toggleRow}>
                  <Text style={[styles.toggleLabel, { color: c.text }]}>
                    API 模式
                  </Text>
                  <Switch
                    value={rateConfig.api_mode}
                    onValueChange={(v) =>
                      setRateConfig((p) => ({ ...p, api_mode: v }))
                    }
                    trackColor={{ false: c.border, true: c.primary }}
                  />
                </View>
                <View style={styles.formActions}>
                  <Button
                    label="保存"
                    onPress={saveRate}
                    loading={rateSaving}
                    disabled={rateSaving}
                    style={styles.formBtn}
                  />
                  <Button
                    label="批量评价"
                    onPress={doBatchRate}
                    loading={batchRating}
                    disabled={batchRating}
                    variant="secondary"
                    style={styles.formBtn}
                  />
                </View>
              </View>
            )
          ) : receiptLoading ? (
            <View style={styles.inlineLoading}>
              <ActivityIndicator color={c.primary} />
            </View>
          ) : (
            <View style={styles.formGroup}>
              <View style={styles.toggleRow}>
                <Text style={[styles.toggleLabel, { color: c.text }]}>
                  启用确认收货消息
                </Text>
                <Switch
                  value={receiptConfig.enabled}
                  onValueChange={(v) =>
                    setReceiptConfig((p) => ({ ...p, enabled: v }))
                  }
                  trackColor={{ false: c.border, true: c.primary }}
                />
              </View>
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
                  确认收货文案
                </Text>
                <Input
                  value={receiptConfig.text}
                  onChangeText={(v) =>
                    setReceiptConfig((p) => ({ ...p, text: v }))
                  }
                  placeholder="请输入确认收货文案"
                  multiline
                />
              </View>
              <Button
                label="保存"
                onPress={saveReceipt}
                loading={receiptSaving}
                disabled={receiptSaving}
              />
            </View>
          )}
        </ScrollView>
      </FormModal>
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// 样式
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  title: { ...typography.title },
  // 顶部搜索栏
  searchBar: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 16, paddingVertical: 8, borderBottomWidth: 1 },
  searchInput: { flex: 1, fontSize: 14, paddingVertical: 4 },
  filterToggle: { paddingHorizontal: spacing.xs },
  filterToggleText: { ...typography.small, fontWeight: '600' },
  // 高级筛选面板
  filterPanel: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    gap: spacing.xs,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  filterLabel: { ...typography.caption, marginTop: spacing.xs },
  chipsScroll: { gap: spacing.sm, paddingVertical: spacing.xs, alignItems: 'center' },
  dateRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  dateInput: { flex: 1, minHeight: 40, paddingVertical: spacing.xs },
  dateDivider: { ...typography.caption },
  resetBtn: { alignSelf: 'flex-end', paddingVertical: spacing.xs, paddingHorizontal: spacing.sm },
  resetBtnText: { ...typography.small, fontWeight: '600' },
  // 多选操作条
  batchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
  },
  batchBarBtn: { ...typography.body, fontWeight: '600' },
  batchBarText: { ...typography.body, fontWeight: '600', flex: 1 },
  batchBarActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  batchDeleteBtn: { minHeight: 36, paddingHorizontal: spacing.md },
  // 多选勾选框
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
    marginRight: spacing.sm,
  },
  checkboxCheck: { color: '#FFFFFF', fontSize: 13, fontWeight: '700', lineHeight: 16 },
  // 卡片首行：商品名 + 状态徽章
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, marginBottom: 4 },
  // 底部留白避让 tab 栏，避免最后一张订单卡片被遮挡
  listContent: { padding: spacing.lg, gap: spacing.md, paddingBottom: 80 },
  orderCard: { gap: spacing.xs },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  amount: { ...typography.body, fontWeight: '700' },
  qty: { ...typography.caption },
  tag: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    marginLeft: 'auto',
    borderRadius: radius.sm,
  },
  tagText: { ...typography.small, fontWeight: '600' },
  subRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.sm,
  },
  subText: { ...typography.small, flexShrink: 1 },
  orderNo: { ...typography.small },
  empty: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 60,
  },
  emptyText: { ...typography.body },
  loadingMore: { textAlign: 'center', padding: spacing.md },
  // Modal 通用
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.lg,
  },
  modalCard: {
    width: '100%',
    maxWidth: 420,
    maxHeight: '80%',
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  modalTitle: { ...typography.heading, fontSize: 16 },
  closeBtn: { fontSize: 20, paddingHorizontal: spacing.xs },
  modalHint: { ...typography.caption, paddingHorizontal: spacing.lg, paddingVertical: spacing.xs },
  modalLoading: { height: 220 },
  modalBody: {},
  modalBodyContent: { padding: spacing.lg, gap: spacing.sm },
  detailGrid: { gap: spacing.sm },
  // 账号选择列表
  accountList: { maxHeight: 320 },
  accountItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.lg,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  accountItemText: { ...typography.body, flex: 1, marginRight: spacing.md },
  accountAction: { ...typography.body, fontWeight: '600' },
  // 同步遮罩
  syncOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.lg,
  },
  syncCard: {
    width: '100%',
    maxWidth: 280,
    borderRadius: radius.lg,
    padding: spacing.xl,
    alignItems: 'center',
    gap: spacing.md,
  },
  syncText: { ...typography.body, fontWeight: '600' },
  syncHint: { ...typography.small, textAlign: 'center' },
  syncCancelBtn: { marginTop: spacing.md, paddingVertical: spacing.sm, paddingHorizontal: spacing.lg, borderRadius: 8, borderWidth: 1 },
  syncCancelText: { ...typography.caption },
  // 自动化设置
  settingsBody: {},
  settingsBodyContent: { padding: spacing.lg, gap: spacing.md },
  segmented: {
    flexDirection: 'row',
    borderRadius: radius.md,
    padding: 4,
    gap: 4,
  },
  segmentBtn: {
    flex: 1,
    paddingVertical: spacing.sm,
    borderRadius: radius.sm,
    alignItems: 'center',
  },
  segmentText: { ...typography.body, fontWeight: '600' },
  fieldLabel: { ...typography.caption },
  // 横向列表必须给显式高度：默认 flexGrow:1 会撑满整屏；仅 flexGrow:0 时安卓初始测量会把文字压扁
  chipsRow: { flexGrow: 0, minHeight: 36 },
  chip: {
    paddingVertical: spacing.xs,
    paddingHorizontal: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 1,
  },
  chipText: { ...typography.small, fontWeight: '600' },
  formGroup: { gap: spacing.md },
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  toggleLabel: { ...typography.body },
  fieldGroup: { gap: spacing.xs },
  formActions: { flexDirection: 'row', gap: spacing.sm },
  formBtn: { flex: 1 },
  inlineLoading: { paddingVertical: spacing.xl, alignItems: 'center' },
});
