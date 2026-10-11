import { useState, useCallback, useEffect, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  ScrollView,
  Alert,
  Modal,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button, Input, Loading, EmptyState, DetailRow } from '@/components/ui';
import { PackageSearch } from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { usePagedList } from '@/hooks/usePagedList';
import {
  getMonitorItems,
  getMonitorTaskOptions,
  getMonitorItemDetail,
  resetMonitorItemsDm,
  isEndpointMissing,
  type MonitorItem,
  type MonitorTaskOption,
} from '@/api/wrappers/monitor';

const PAGE_SIZE = 20;

/** 私信状态筛选项（value 与后端 dm_state 枚举一致） */
const DM_STATE_FILTERS: { value: string; label: string }[] = [
  { value: '', label: '私信全部' },
  { value: 'not_sent', label: '未私信' },
  { value: 'waiting', label: '等待重试' },
  { value: 'pending', label: '已发待确认' },
  { value: 'success', label: '私信成功' },
  { value: 'failed', label: '私信失败' },
];

/** 下单状态筛选项（value 与后端 order_state 枚举一致） */
const ORDER_STATE_FILTERS: { value: string; label: string }[] = [
  { value: '', label: '下单全部' },
  { value: 'not_ordered', label: '未下单' },
  { value: 'ordered', label: '已下单' },
  { value: 'failed', label: '下单失败' },
  { value: 'no_account', label: '无可用账号' },
  { value: 'duplicate', label: '重复跳过' },
];

/** 是否已获取详情筛选项 */
const HAS_DETAIL_FILTERS: { value: string; label: string }[] = [
  { value: '', label: '详情全部' },
  { value: 'true', label: '已获取详情' },
  { value: 'false', label: '未获取详情' },
];

type BadgeTone = 'ok' | 'warn' | 'err' | 'info' | 'muted';

/** 由原始字段派生私信状态展示信息（对齐 web MonitorItems 的判定顺序） */
function dmStatusInfo(item: MonitorItem): { label: string; tone: BadgeTone } {
  if (item.dm_status === 'failed') {
    return {
      label: item.dm_attempts >= 3 ? '私信失败(已放弃)' : '私信失败(重试中)',
      tone: 'err',
    };
  }
  if (item.is_dm_sent) {
    return item.dm_status === 'success'
      ? { label: '私信成功', tone: 'ok' }
      : { label: '已发待确认', tone: 'info' };
  }
  if (item.dm_status === 'waiting') return { label: '等待重试', tone: 'warn' };
  return { label: '未私信', tone: 'muted' };
}

/** 由原始字段派生下单状态展示信息 */
function orderStatusInfo(item: MonitorItem): { label: string; tone: BadgeTone } {
  if (item.order_status === 'duplicate') return { label: '重复跳过', tone: 'info' };
  if (item.is_ordered) return { label: '已下单', tone: 'ok' };
  if (item.order_status === 'no_account') return { label: '无可用账号', tone: 'warn' };
  if (item.order_status === 'failed') {
    return {
      label: item.order_attempts >= 3 ? '下单失败(已放弃)' : '下单失败(重试中)',
      tone: 'err',
    };
  }
  return { label: '未下单', tone: 'muted' };
}

function toneColor(tone: BadgeTone, c: (typeof colors)['light']): { bg: string; fg: string } {
  switch (tone) {
    case 'ok':
      return { bg: c.success, fg: '#FFFFFF' };
    case 'warn':
      return { bg: c.warning, fg: '#FFFFFF' };
    case 'err':
      return { bg: c.error, fg: '#FFFFFF' };
    case 'info':
      return { bg: c.info, fg: '#FFFFFF' };
    default:
      return { bg: c.border, fg: c.textSecondary };
  }
}

/** ISO 时间 → 可读字符串，无法解析时原样返回 */
function formatDateTime(iso?: string | null): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(
    d.getHours(),
  )}:${p(d.getMinutes())}`;
}

export default function MonitorItemsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  // 筛选：任务/私信/下单/详情 chips 即时生效；文本条件由「查询」提交
  const [taskFilter, setTaskFilter] = useState<number | null>(null);
  const [dmState, setDmState] = useState('');
  const [orderState, setOrderState] = useState('');
  const [hasDetail, setHasDetail] = useState('');
  const [taskOptions, setTaskOptions] = useState<MonitorTaskOption[]>([]);
  // 文本输入（未提交）
  const [keywordInput, setKeywordInput] = useState('');
  const [areaInput, setAreaInput] = useState('');
  const [sellerNickInput, setSellerNickInput] = useState('');
  const [itemIdInput, setItemIdInput] = useState('');
  // 已提交的文本条件
  const [keyword, setKeyword] = useState('');
  const [area, setArea] = useState('');
  const [sellerNick, setSellerNick] = useState('');
  const [itemId, setItemId] = useState('');
  const [searchToken, setSearchToken] = useState(0);
  // 更多筛选展开
  const [moreExpanded, setMoreExpanded] = useState(false);

  // 多选模式 + 批量重置私信失败
  const [selectMode, setSelectMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [resetting, setResetting] = useState(false);

  // 详情弹窗
  const [detailPk, setDetailPk] = useState<number | null>(null);
  const [detailItem, setDetailItem] = useState<MonitorItem | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const list = usePagedList<MonitorItem>({
    mode: 'page',
    pageSize: PAGE_SIZE,
    auto: false, // 由筛选 effect 统一触发首次加载
    dedupeBy: (it) => it.id,
    fetchPage: async ({ page = 1 }) => {
      const resp = await getMonitorItems({
        page,
        pageSize: PAGE_SIZE,
        monitorTaskId: taskFilter ?? undefined,
        keyword: keyword.trim() || undefined,
        area: area.trim() || undefined,
        sellerNick: sellerNick.trim() || undefined,
        itemId: itemId.trim() || undefined,
        dmState: dmState || undefined,
        orderState: orderState || undefined,
        hasDetail: hasDetail === '' ? undefined : hasDetail === 'true',
      });
      return { items: resp.list, total: resp.total };
    },
    onError: (e, phase) => {
      if (phase !== 'refresh') return;
      if (isEndpointMissing(e)) {
        Alert.alert('功能不可用', '采集商品需要后端新版支持，请升级后端服务');
      } else {
        Alert.alert('加载失败', e.message);
      }
    },
  });

  // 挂载与筛选变化时回到第一页重新加载（effect 在渲染后执行，fetchPage 闭包取到最新筛选）
  useEffect(() => {
    list.refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskFilter, dmState, orderState, hasDetail, searchToken]);

  useEffect(() => {
    getMonitorTaskOptions()
      .then(setTaskOptions)
      .catch(() => {
        // 任务选项加载失败不阻塞列表，仅无法按任务筛选
      });
  }, []);

  /** 「查询」：提交文本筛选并回到第一页（state 提交后由 effect 触发加载） */
  const handleSearch = useCallback(() => {
    setKeyword(keywordInput);
    setArea(areaInput);
    setSellerNick(sellerNickInput);
    setItemId(itemIdInput);
    setSearchToken((t) => t + 1);
  }, [keywordInput, areaInput, sellerNickInput, itemIdInput]);

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
      const items = list.items;
      const allSelected = items.length > 0 && items.every((it) => prev.has(it.id));
      return allSelected ? new Set() : new Set(items.map((it) => it.id));
    });
  }, [list.items]);

  const selectedArr = useMemo(() => Array.from(selectedIds), [selectedIds]);

  /** 打开详情弹窗并加载数据库中采集到的完整信息 */
  const openDetail = useCallback((pk: number) => {
    setDetailPk(pk);
    setDetailItem(null);
    setDetailLoading(true);
    getMonitorItemDetail(pk)
      .then(setDetailItem)
      .catch((e: unknown) => {
        Alert.alert('加载详情失败', (e as Error).message);
        setDetailPk(null);
      })
      .finally(() => setDetailLoading(false));
  }, []);

  /** 批量重置「私信失败」为未私信，等待定时任务重试 */
  const handleResetDm = useCallback(() => {
    if (selectedArr.length === 0) {
      Alert.alert('提示', '请先勾选要重置的采集商品');
      return;
    }
    Alert.alert(
      '重置私信失败状态',
      `已选中 ${selectedArr.length} 条数据，仅其中「私信失败」的商品会被重置为「未私信」，并等待定时任务重新发送私信。是否继续？`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '确定重置',
          onPress: () => {
            setResetting(true);
            resetMonitorItemsDm(selectedArr)
              .then((r) => {
                if (r.success_count === 0) {
                  Alert.alert('提示', '选中的数据中没有可重置的「私信失败」商品');
                  return;
                }
                Alert.alert('成功', `已重置 ${r.success_count} 条私信失败商品，等待定时任务重试`);
                setSelectedIds(new Set());
                return list.refresh();
              })
              .catch((e: unknown) => Alert.alert('重置失败', (e as Error).message))
              .finally(() => setResetting(false));
          },
        },
      ],
    );
  }, [selectedArr, list]);

  const taskKeyword = useCallback(
    (item: MonitorItem): string => {
      if (item.monitor_task_keyword) return item.monitor_task_keyword;
      if (item.monitor_task_id != null) {
        return (
          taskOptions.find((t) => t.id === item.monitor_task_id)?.keyword ||
          `任务 #${item.monitor_task_id}`
        );
      }
      return '未知任务';
    },
    [taskOptions],
  );

  /** 详情弹窗行数据（仅展示有值字段，避免整屏 "-"） */
  const detailRows = useMemo(() => {
    if (!detailItem) return [];
    const rows: { label: string; value: string }[] = [
      { label: '商品ID', value: detailItem.item_id || '-' },
      { label: '商品标题', value: detailItem.title || '-' },
      { label: '价格', value: detailItem.price ? `¥${detailItem.price}` : '-' },
      { label: '地区', value: detailItem.area || '-' },
      { label: '卖家昵称', value: detailItem.seller_nick || '-' },
      { label: '卖家真实ID', value: detailItem.seller_user_id || '-' },
      { label: '想要数', value: detailItem.want_count > 0 ? String(detailItem.want_count) : '-' },
      { label: '营销标签', value: detailItem.tags || '-' },
      { label: '发布时间', value: formatDateTime(detailItem.publish_time) },
      { label: '私信状态', value: dmStatusInfo(detailItem).label },
      { label: '私信账号', value: detailItem.dm_account_id || '-' },
      { label: '私信失败原因', value: detailItem.dm_fail_reason || '-' },
      { label: '下单状态', value: orderStatusInfo(detailItem).label },
      { label: '订单ID', value: detailItem.order_id || '-' },
      { label: '下单账号', value: detailItem.order_account_id || '-' },
      { label: '下单失败原因', value: detailItem.order_fail_reason || '-' },
      { label: '是否获取详情', value: detailItem.has_detail ? '已获取' : '未获取' },
      { label: '最近采集', value: formatDateTime(detailItem.last_seen_at) },
      { label: '采集时间', value: formatDateTime(detailItem.created_at) },
      { label: '更新时间', value: formatDateTime(detailItem.updated_at) },
    ];
    return rows;
  }, [detailItem]);

  if (list.loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载采集商品..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        {selectMode ? (
          <>
            <Button
              label={`重置私信失败 (${selectedIds.size})`}
              onPress={handleResetDm}
              loading={resetting}
              disabled={resetting || selectedIds.size === 0}
            />
            <Button label="全选/取消" onPress={toggleSelectAll} variant="secondary" />
            <Button label="取消" onPress={exitSelectMode} variant="ghost" />
          </>
        ) : (
          <>
            <Button label="批量重置" onPress={() => setSelectMode(true)} variant="secondary" />
            <Button label="刷新" onPress={() => list.refresh()} loading={list.refreshing} />
          </>
        )}
      </View>

      {/* 筛选区：任务 chips / 搜索框 / 状态 chips / 更多筛选 */}
      <View style={styles.filterSection}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={styles.chipRow}>
            <Pressable
              onPress={() => setTaskFilter(null)}
              style={[
                styles.chip,
                {
                  borderColor: taskFilter == null ? c.primary : c.border,
                  backgroundColor: taskFilter == null ? c.primary : 'transparent',
                },
              ]}
            >
              <Text style={[styles.chipText, { color: taskFilter == null ? '#FFF' : c.text }]}>
                全部任务
              </Text>
            </Pressable>
            {taskOptions.map((t) => {
              const selected = taskFilter === t.id;
              return (
                <Pressable
                  key={t.id}
                  onPress={() => setTaskFilter(t.id)}
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
                    {t.keyword || `任务 #${t.id}`}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </ScrollView>

        <View style={styles.searchRow}>
          <Input
            value={keywordInput}
            onChangeText={setKeywordInput}
            placeholder="搜索商品标题"
            style={styles.searchInput}
            returnKeyType="search"
            onSubmitEditing={handleSearch}
          />
          <Button label="查询" onPress={handleSearch} style={styles.searchBtn} />
          <Button
            label={moreExpanded ? '收起' : '更多'}
            variant="secondary"
            onPress={() => setMoreExpanded((v) => !v)}
            style={styles.searchBtn}
          />
        </View>

        {moreExpanded && (
          <View style={[styles.morePanel, { backgroundColor: c.surface, borderColor: c.borderLight }]}>
            <Text style={[styles.moreLabel, { color: c.textSecondary }]}>地区</Text>
            <Input value={areaInput} onChangeText={setAreaInput} placeholder="如：江苏" />
            <Text style={[styles.moreLabel, { color: c.textSecondary }]}>卖家昵称</Text>
            <Input value={sellerNickInput} onChangeText={setSellerNickInput} placeholder="输入卖家昵称" />
            <Text style={[styles.moreLabel, { color: c.textSecondary }]}>商品ID（精确）</Text>
            <Input value={itemIdInput} onChangeText={setItemIdInput} placeholder="输入商品ID" />
            <Button label="应用筛选" variant="secondary" onPress={handleSearch} style={styles.applyBtn} />
          </View>
        )}

        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={styles.chipRow}>
            {DM_STATE_FILTERS.map((f) => {
              const selected = dmState === f.value;
              return (
                <Pressable
                  key={f.value || 'all'}
                  onPress={() => setDmState(f.value)}
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
        </ScrollView>

        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={styles.chipRow}>
            {ORDER_STATE_FILTERS.map((f) => {
              const selected = orderState === f.value;
              return (
                <Pressable
                  key={f.value || 'all'}
                  onPress={() => setOrderState(f.value)}
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
        </ScrollView>

        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={styles.chipRow}>
            {HAS_DETAIL_FILTERS.map((f) => {
              const selected = hasDetail === f.value;
              return (
                <Pressable
                  key={f.value || 'all'}
                  onPress={() => setHasDetail(f.value)}
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
        </ScrollView>
      </View>

      <FlatList
        data={list.items}
        keyExtractor={(item) => String(item.id)}
        refreshControl={
          <RefreshControl refreshing={list.refreshing} onRefresh={list.refresh} />
        }
        onEndReached={list.loadMore}
        onEndReachedThreshold={0.3}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <EmptyState
            icon={PackageSearch}
            title="暂无采集商品"
            message="监控任务采集到商品后会展示在这里"
          />
        }
        ListFooterComponent={
          list.loadingMore ? (
            <Text style={[styles.loadingMore, { color: c.textMuted }]}>加载中...</Text>
          ) : null
        }
        renderItem={({ item }) => {
          const dm = dmStatusInfo(item);
          const order = orderStatusInfo(item);
          const dmTone = toneColor(dm.tone, c);
          const orderTone = toneColor(order.tone, c);
          const checked = selectedIds.has(item.id);
          return (
            <Pressable
              onPress={() => (selectMode ? toggleSelect(item.id) : openDetail(item.id))}
            >
              <Card style={[styles.card, selectMode && checked && { borderColor: c.primary, borderWidth: 1 }]}>
                <View style={styles.cardHeader}>
                  <View style={styles.badgeRow}>
                    {selectMode && (
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
                    )}
                    <View style={[styles.statusBadge, { backgroundColor: dmTone.bg }]}>
                      <Text style={[styles.statusText, { color: dmTone.fg }]}>{dm.label}</Text>
                    </View>
                    <View style={[styles.statusBadge, { backgroundColor: orderTone.bg }]}>
                      <Text style={[styles.statusText, { color: orderTone.fg }]}>{order.label}</Text>
                    </View>
                    {item.has_detail ? (
                      <View style={[styles.statusBadge, { backgroundColor: c.primaryLight }]}>
                        <Text style={[styles.statusText, { color: c.primary }]}>有详情</Text>
                      </View>
                    ) : null}
                  </View>
                  <Text style={[styles.price, { color: c.primary }]}>
                    {item.price ? `¥${item.price}` : '-'}
                  </Text>
                </View>

                <Text style={[styles.title, { color: c.text }]} numberOfLines={2}>
                  {item.title || item.item_id || '（无标题）'}
                </Text>

                <Text style={[styles.meta, { color: c.textMuted }]} numberOfLines={1}>
                  {taskKeyword(item)}
                  {item.area ? ` · ${item.area}` : ''}
                  {item.seller_nick ? ` · ${item.seller_nick}` : ''}
                </Text>
                <Text style={[styles.meta, { color: c.textMuted }]}>
                  采集于 {formatDateTime(item.created_at)}
                </Text>
                {!selectMode && (
                  <Text style={[styles.detailHint, { color: c.primary }]}>点击查看详情</Text>
                )}
              </Card>
            </Pressable>
          );
        }}
      />

      {/* 采集商品详情弹窗 */}
      <Modal
        visible={detailPk != null}
        transparent
        animationType="fade"
        onRequestClose={() => setDetailPk(null)}
      >
        <Pressable style={styles.overlay} onPress={() => setDetailPk(null)}>
          <Pressable style={[styles.modal, { backgroundColor: c.surface }]} onPress={() => {}}>
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>采集商品详情</Text>
              <Pressable onPress={() => setDetailPk(null)} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>
            {detailLoading ? (
              <Loading label="加载详情..." />
            ) : (
              <ScrollView style={styles.detailScroll} keyboardShouldPersistTaps="handled">
                {detailRows.map((row) => (
                  <DetailRow key={row.label} label={row.label} value={row.value} c={c} />
                ))}
              </ScrollView>
            )}
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
    flexWrap: 'wrap',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  filterSection: { gap: spacing.sm, paddingBottom: spacing.sm },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'nowrap',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    borderWidth: 1,
    maxWidth: 160,
  },
  chipText: { ...typography.small },
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  searchInput: { flex: 1, minHeight: 40 },
  searchBtn: { minHeight: 40, paddingHorizontal: spacing.md },
  morePanel: {
    marginHorizontal: spacing.lg,
    padding: spacing.md,
    borderRadius: radius.lg,
    borderWidth: 1,
    gap: spacing.xs,
  },
  moreLabel: { ...typography.small, marginTop: spacing.xs },
  applyBtn: { minHeight: 40, marginTop: spacing.sm },
  list: { padding: spacing.lg, paddingTop: spacing.sm, gap: spacing.md, paddingBottom: 80 },
  card: { gap: spacing.xs },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.sm,
  },
  badgeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    flexShrink: 1,
    flexWrap: 'wrap',
  },
  statusBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  statusText: { ...typography.micro },
  checkBoxInner: {
    width: 20,
    height: 20,
    borderRadius: radius.sm,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkMark: { fontSize: 13, fontWeight: '700', color: '#FFF', lineHeight: 15 },
  price: { ...typography.body, fontWeight: '700' },
  title: { ...typography.caption, fontWeight: '600' },
  meta: { ...typography.small },
  detailHint: { ...typography.small },
  loadingMore: { textAlign: 'center', padding: spacing.md },
  // 详情弹窗
  overlay: {
    flex: 1,
    justifyContent: 'center',
    padding: spacing.lg,
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  modal: {
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
    maxHeight: '80%',
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  modalTitle: { ...typography.heading },
  closeBtn: { fontSize: 22, paddingHorizontal: spacing.xs },
  detailScroll: { maxHeight: 420, gap: spacing.xs },
});
