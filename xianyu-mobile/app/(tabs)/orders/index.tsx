import { useState, useCallback, useRef } from 'react';
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
  getAutoRateConfig,
  updateAutoRateConfig,
  batchRate,
  getConfirmReceiptConfig,
  updateConfirmReceiptConfig,
  type Order,
  type OrderDetail,
  type AutoRateConfig,
  type ConfirmReceiptConfig,
} from '@/api/wrappers/orders-tab';
import { manualDelivery } from '@/api/wrappers/orders';
import { createPersonalBlacklist } from '@/api/wrappers/blacklist-manage';
import type { AccountOption } from '@/api/wrappers/accounts';
import { useAccountsStore } from '@/stores/accounts';
import { usePagedList } from '@/hooks/usePagedList';

const PAGE_SIZE = 20;

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

// ---------------------------------------------------------------------------

export default function OrdersPage() {
  const scheme = useColorScheme();
  const dark = scheme === 'dark';
  const c: ThemeColors = colors[dark ? 'dark' : 'light'];

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
      const resp = await getOrders(page, limit);
      return { items: resp.data, total: resp.total };
    },
    onError: (e, phase) => {
      console.error('加载订单失败', e);
      if (phase === 'refresh') Alert.alert('加载失败', e.message);
    },
  });

  // 状态筛选 + 搜索（客户端过滤当前已加载订单）
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const filteredOrders = orders.filter((o) => {
    const byStatus = statusFilter === 'all' || groupStatus(o.status) === statusFilter;
    const q = searchQuery.trim();
    const bySearch = !q || o.order_no.includes(q) || (o.item_title || '').includes(q) || (o.buyer_nick || o.buyer_id || '').includes(q);
    return byStatus && bySearch;
  });

  // 订单详情弹窗
  const [detailVisible, setDetailVisible] = useState(false);
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // 账号列表（用于同步与设置）
  const accounts = useAccountsStore((s) => s.options);
  const loadAccountOptions = useAccountsStore((s) => s.load);

  // 同步闲鱼订单
  const [syncPickerVisible, setSyncPickerVisible] = useState(false);
  const [syncing, setSyncing] = useState(false);
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

  // ---- 同步闲鱼订单 ----
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
    async (account: AccountOption) => {
      setSyncPickerVisible(false);
      setSyncing(true);
      // 代际 token：取消时自增使在途作废，避免"取消→立即重 Sync"时旧请求弹 Alert 或提前关遮罩
      const myGen = ++syncGenRef.current;
      try {
        // 120s 超时：账号离线时后端会阻塞，避免无限转圈且模态无法关闭
        await withTimeout(
          fetchXianyuOrders(account.id),
          120000,
          '同步超时，请确认账号在线后重试',
        );
        if (syncGenRef.current !== myGen) return; // 已被取消或被新同步取代
        Alert.alert(
          '同步成功',
          `已同步账号「${account.remark || account.id}」的闲鱼订单`,
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
      const meta = getStatusMeta(item.status);
      const tc = toneColors(meta.tone, dark);
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
              onPress: async () => {
                if (deliveryDisabled) return; // 当前状态不可发货
                try {
                  await manualDelivery(item.order_no);
                  Alert.alert('发货成功', `订单 ${item.order_no} 已手动发货`);
                  refreshOrders();
                } catch (e) {
                  Alert.alert('发货失败', (e as Error).message);
                }
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
          <Card style={styles.orderCard}>
            <View style={styles.titleRow}>
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
        </SwipeableRow>
      );
    },
    [openDetail, refreshOrders, c.text, c.error, c.info, c.surfaceAlt, c.textSecondary, c.textMuted, c.warning, c.primary, dark],
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

      {/* 搜索栏 */}
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
      </View>

      {/* 状态筛选 */}
      <FilterTabs tabs={STATUS_TABS} active={statusFilter} onChange={setStatusFilter} />

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
              正在同步闲鱼订单...
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
