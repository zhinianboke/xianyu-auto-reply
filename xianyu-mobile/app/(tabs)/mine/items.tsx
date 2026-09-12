import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import {
  Alert,
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  Pressable,
  ScrollView,
  Image,
  ActivityIndicator,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Card, EmptyState, Badge, Loading, Input } from '@/components/ui';
import {
  Package,
  Ticket,
  Search,
  X,
  CheckCircle2,
  Circle,
} from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getXianyuItems,
  syncXianyuItemsFromAccount,
  batchOfflineXianyuItems,
  batchDeleteItemRecords,
  type XianyuItem,
} from '@/api/wrappers/items';
import { batchDeleteItems } from '@/api/wrappers/item-edit';
import { batchClearItemRelations } from '@/api/wrappers/card-relation';
import { getAccountOptions, type AccountOption } from '@/api/wrappers/accounts';
import { ItemCardRelationModal } from '@/components/card-relation/ItemCardRelationModal';

const PAGE_SIZE = 20;

/** 列表筛选 chips 定义（对应 GET /paginated 的布尔筛选参数） */
const FILTER_CHIPS: Array<{
  key: 'polished' | 'multiSpec' | 'multiQty';
  label: string;
}> = [
  { key: 'polished', label: '已擦亮' },
  { key: 'multiSpec', label: '多规格' },
  { key: 'multiQty', label: '多数量发货' },
];

type BatchAction = '' | 'offline' | 'delete' | 'clear';

export default function ItemsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();

  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [items, setItems] = useState<XianyuItem[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // 关联卡券弹窗：当前正在关联卡券的商品，非空即表示弹窗打开
  const [relationItem, setRelationItem] = useState<XianyuItem | null>(null);

  // 搜索与筛选（keyword 输入防抖后生效）
  const [keywordInput, setKeywordInput] = useState('');
  const [keyword, setKeyword] = useState('');
  const [filterPolished, setFilterPolished] = useState(false);
  const [filterMultiSpec, setFilterMultiSpec] = useState(false);
  const [filterMultiQty, setFilterMultiQty] = useState(false);

  // 批量选择模式：selectedKeys 以 cookie_id::item_id 为键
  const [selectMode, setSelectMode] = useState(false);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  const [batchBusy, setBatchBusy] = useState<BatchAction>('');

  // 商品同步：'one'=当前选中账号，'all'=全部账号
  const [syncing, setSyncing] = useState<'' | 'one' | 'all'>('');

  // 切换账号会触发两次 loadItems（useEffect 依赖变更 + selectedAccountId 传入），
  // 用 ref 记录最新请求序号，丢弃过期响应
  const reqSeqRef = useRef(0);

  // loadItems 通过 ref 读取最新筛选条件，避免筛选状态变化时重建回调导致拉取中断
  const filtersRef = useRef({ keyword: '', polished: false, multiSpec: false, multiQty: false });
  filtersRef.current = {
    keyword,
    polished: filterPolished,
    multiSpec: filterMultiSpec,
    multiQty: filterMultiQty,
  };

  // 搜索关键字 500ms 防抖
  useEffect(() => {
    const t = setTimeout(() => setKeyword(keywordInput.trim()), 500);
    return () => clearTimeout(t);
  }, [keywordInput]);

  const loadAccounts = useCallback(async () => {
    try {
      const opts = await getAccountOptions();
      setAccounts(opts);
    } catch {
      // 账号加载失败不阻塞商品列表（仍可看"全部"）
    }
  }, []);

  const loadItems = useCallback(
    async (accountId: string, opts?: { append?: boolean; fromPage?: number }) => {
      const append = opts?.append ?? false;
      const targetPage = opts?.fromPage ?? 1;
      const seq = ++reqSeqRef.current;
      const f = filtersRef.current;

      if (append) {
        setLoadingMore(true);
      } else if (opts?.fromPage == null) {
        setRefreshing(true);
      }
      setError(null);
      try {
        const res = await getXianyuItems(targetPage, PAGE_SIZE, accountId || undefined, {
          keyword: f.keyword || undefined,
          isPolished: f.polished || undefined,
          isMultiSpec: f.multiSpec || undefined,
          multiQuantityDelivery: f.multiQty || undefined,
        });
        if (seq !== reqSeqRef.current) return; // 已被后续请求覆盖
        console.log('[ITEMS] API返回', res.items.length, '条, item_ids:', res.items.map(i => i.item_id));
        setItems((prev) => {
          // 去重：按 item_id（后端可能返回同 item_id 不同 DB id 的重复行）
          const seen = new Set(prev.map((i) => i.item_id));
          const newItems = res.items.filter((i) => {
            if (seen.has(i.item_id)) return false;
            seen.add(i.item_id);
            return true;
          });
          console.log('[ITEMS] 去重后', newItems.length, '条');
          return append ? [...prev, ...newItems] : newItems;
        });
        // total 也按去重后的数量修正
        setItems((cur) => {
          setTotal(cur.length);
          return cur;
        });
        setPage(res.page);
        setTotalPages(res.total_pages);
        setTotal(res.total);
      } catch (e) {
        if (seq !== reqSeqRef.current) return;
        setError((e as Error).message || '加载商品失败');
      } finally {
        if (seq !== reqSeqRef.current) return;
        if (append) setLoadingMore(false);
        else if (opts?.fromPage == null) setRefreshing(false);
        setLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  useEffect(() => {
    setLoading(true);
    loadItems(selectedAccountId);
  }, [selectedAccountId, keyword, filterPolished, filterMultiSpec, filterMultiQty, loadItems]);

  const handleRefresh = useCallback(() => {
    loadItems(selectedAccountId);
  }, [selectedAccountId, loadItems]);

  const handleLoadMore = useCallback(() => {
    if (loadingMore || refreshing || loading) return;
    if (total === 0) return;
    if (totalPages > 0 && page >= totalPages) return;
    loadItems(selectedAccountId, { append: true, fromPage: page + 1 });
  }, [loadingMore, refreshing, loading, total, totalPages, page, selectedAccountId, loadItems]);

  // ==================== 商品同步 ====================

  const handleSync = useCallback(
    async (scope: 'one' | 'all') => {
      if (syncing) return;
      if (scope === 'one' && !selectedAccountId) {
        Alert.alert('提示', '请先在顶部选择要同步的账号');
        return;
      }
      setSyncing(scope);
      try {
        const res = await syncXianyuItemsFromAccount(scope === 'one' ? selectedAccountId : undefined);
        const failed = res.failed_accounts ?? [];
        const lines: string[] = [`获取 ${res.total_count} 件商品，新增/更新 ${res.saved_count} 件`];
        if (scope === 'all' && res.account_count != null) {
          lines.push(
            `账号：成功 ${res.success_account_count ?? 0}/${res.account_count} 个`,
          );
        }
        if (failed.length > 0) {
          const preview = failed.slice(0, 5).join('\n');
          lines.push(
            `失败账号 ${failed.length} 个：\n${preview}${failed.length > 5 ? `\n...等共 ${failed.length} 个` : ''}`,
          );
        }
        Alert.alert('同步完成', lines.join('\n'));
        loadItems(selectedAccountId);
      } catch (e) {
        Alert.alert('同步失败', (e as Error).message || '未知错误');
      } finally {
        setSyncing('');
      }
    },
    [syncing, selectedAccountId, loadItems],
  );

  // ==================== 批量选择 ====================

  const itemKey = useCallback(
    (it: XianyuItem) => `${it.cookie_id}::${it.item_id}`,
    [],
  );

  const selectedItems = useMemo(
    () => items.filter((it) => selectedKeys.has(itemKey(it))),
    [items, selectedKeys, itemKey],
  );

  const allSelected = items.length > 0 && selectedItems.length === items.length;

  const exitSelectMode = useCallback(() => {
    setSelectMode(false);
    setSelectedKeys(new Set());
  }, []);

  const toggleSelectMode = useCallback(() => {
    if (selectMode) exitSelectMode();
    else setSelectMode(true);
  }, [selectMode, exitSelectMode]);

  const toggleItem = useCallback((it: XianyuItem) => {
    setSelectedKeys((prev) => {
      const key = `${it.cookie_id}::${it.item_id}`;
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const enterSelectWith = useCallback((it: XianyuItem) => {
    setSelectMode(true);
    setSelectedKeys(new Set([`${it.cookie_id}::${it.item_id}`]));
  }, []);

  const toggleSelectAll = useCallback(() => {
    setSelectedKeys(
      allSelected ? new Set() : new Set(items.map((it) => `${it.cookie_id}::${it.item_id}`)),
    );
  }, [allSelected, items]);

  const handleEdit = useCallback(
    (item: XianyuItem) => {
      router.push({
        pathname: '/(tabs)/mine/item-edit',
        params: { cookieId: item.cookie_id, itemId: item.item_id },
      });
    },
    [router],
  );

  const handleDelete = useCallback(
    (item: XianyuItem) => {
      Alert.alert(
        '删除商品',
        `确定删除「${item.title || '无标题'}」吗？此操作不可撤销。`,
        [
          { text: '取消', style: 'cancel' },
          {
            text: '删除',
            style: 'destructive',
            onPress: async () => {
              try {
                await batchDeleteItems(item.cookie_id, [item.item_id]);
                loadItems(selectedAccountId);
              } catch (e) {
                Alert.alert('删除失败', (e as Error).message || '未知错误');
              }
            },
          },
        ],
      );
    },
    [loadItems, selectedAccountId],
  );

  const handleLongPress = useCallback(
    (item: XianyuItem) => {
      Alert.alert(item.title || '无标题', undefined, [
        { text: '编辑', onPress: () => handleEdit(item) },
        { text: '删除', style: 'destructive', onPress: () => handleDelete(item) },
        { text: '批量选择', onPress: () => enterSelectWith(item) },
        { text: '取消', style: 'cancel' },
      ]);
    },
    [handleEdit, handleDelete, enterSelectWith],
  );

  // ==================== 批量操作 ====================

  /** 批量下架：按归属账号分组，逐账号用其 Cookie 调闲鱼接口 */
  const handleBatchOffline = useCallback(() => {
    const targets = selectedItems;
    if (targets.length === 0 || batchBusy) return;
    const groups = new Map<string, string[]>();
    let orphan = 0;
    for (const it of targets) {
      if (!it.cookie_id) {
        orphan += 1;
        continue;
      }
      const arr = groups.get(it.cookie_id);
      if (arr) arr.push(it.item_id);
      else groups.set(it.cookie_id, [it.item_id]);
    }
    Alert.alert(
      '批量下架',
      `将通过各账号 Cookie 下架选中的 ${targets.length} 件商品（涉及 ${groups.size} 个账号）${orphan ? `，${orphan} 件未指定账号无法下架` : ''}。下架不会删除本地记录，确定继续吗？`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '下架',
          style: 'destructive',
          onPress: async () => {
            setBatchBusy('offline');
            try {
              let suc = 0;
              let fail = 0;
              const failedIds: string[] = [];
              const errors: string[] = [];
              for (const [cookieId, ids] of groups) {
                try {
                  const r = await batchOfflineXianyuItems(cookieId, ids);
                  suc += r.suc_count;
                  fail += r.fail_count;
                  failedIds.push(...r.failed_item_ids);
                } catch (e) {
                  errors.push(`账号 ${cookieId}：${(e as Error).message || '下架失败'}`);
                }
              }
              const lines = [`成功下架 ${suc} 件${fail ? `，失败 ${fail} 件` : ''}`];
              if (orphan) lines.push(`已跳过 ${orphan} 件未指定账号的商品`);
              if (failedIds.length > 0) {
                lines.push(
                  `失败商品：${failedIds.slice(0, 5).join('、')}${failedIds.length > 5 ? ` 等共 ${failedIds.length} 个` : ''}`,
                );
              }
              if (errors.length > 0) lines.push(errors.slice(0, 3).join('\n'));
              Alert.alert(suc > 0 ? '下架完成' : '下架失败', lines.join('\n'));
              setSelectedKeys(new Set());
              loadItems(selectedAccountId);
            } finally {
              setBatchBusy('');
            }
          },
        },
      ],
    );
  }, [selectedItems, batchBusy, selectedAccountId, loadItems]);

  /** 批量删除本地记录（不影响闲鱼平台） */
  const handleBatchDeleteRecords = useCallback(() => {
    const targets = selectedItems;
    if (targets.length === 0 || batchBusy) return;
    Alert.alert(
      '批量删除本地记录',
      `将删除选中的 ${targets.length} 件商品的本地记录（不影响闲鱼平台在售商品），确定继续吗？`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: async () => {
            setBatchBusy('delete');
            try {
              const res = await batchDeleteItemRecords(
                targets.map((it) => ({ cookie_id: it.cookie_id || null, item_id: it.item_id })),
              );
              Alert.alert('删除完成', res.message || `已删除 ${targets.length} 条本地记录`);
              setSelectedKeys(new Set());
              loadItems(selectedAccountId);
            } catch (e) {
              Alert.alert('删除失败', (e as Error).message || '未知错误');
            } finally {
              setBatchBusy('');
            }
          },
        },
      ],
    );
  }, [selectedItems, batchBusy, selectedAccountId, loadItems]);

  /** 批量清空选中商品的卡券关联（不删除卡券本身） */
  const handleBatchClearRelations = useCallback(() => {
    const targets = selectedItems;
    if (targets.length === 0 || batchBusy) return;
    const itemIds = Array.from(new Set(targets.map((it) => it.item_id)));
    Alert.alert(
      '批量清空关联卡券',
      `将清空选中 ${targets.length} 件商品的卡券关联（不删除卡券本身），确定继续吗？`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '清空',
          style: 'destructive',
          onPress: async () => {
            setBatchBusy('clear');
            try {
              await batchClearItemRelations(itemIds);
              Alert.alert('操作完成', `已清空 ${targets.length} 件商品的卡券关联`);
              setSelectedKeys(new Set());
              loadItems(selectedAccountId);
            } catch (e) {
              Alert.alert('操作失败', (e as Error).message || '未知错误');
            } finally {
              setBatchBusy('');
            }
          },
        },
      ],
    );
  }, [selectedItems, batchBusy, loadItems, selectedAccountId]);

  const accountLabel = (acc: AccountOption) => acc.remark || acc.id;

  const renderItem = ({ item }: { item: XianyuItem }) => {
    const key = itemKey(item);
    const checked = selectedKeys.has(key);
    return (
      <Pressable
        onPress={() => (selectMode ? toggleItem(item) : handleEdit(item))}
        onLongPress={() => (selectMode ? toggleItem(item) : handleLongPress(item))}
        style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })}
      >
        <Card style={[styles.card, selectMode && checked && { borderColor: c.primary, borderWidth: 1 }]}>
          <View style={styles.cardRow}>
            {selectMode ? (
              <View style={styles.checkWrap}>
                {checked ? (
                  <CheckCircle2 size={22} stroke={c.primary} />
                ) : (
                  <Circle size={22} stroke={c.border} />
                )}
              </View>
            ) : null}
            {item.image ? (
              <Image
                source={{ uri: item.image }}
                style={[styles.thumb, { backgroundColor: c.surfaceAlt }]}
              />
            ) : (
              <View style={[styles.thumb, { backgroundColor: c.surfaceAlt }]}>
                <Package size={24} stroke={c.textMuted} />
              </View>
            )}
            <View style={styles.body}>
              <Text
                style={[styles.title, { color: c.text }]}
                numberOfLines={2}
              >
                {item.title || '无标题'}
              </Text>
              <View style={styles.metaRow}>
                <Text style={[styles.price, { color: c.warning }]} numberOfLines={1}>
                  {item.price ? `¥${item.price}` : '价格未知'}
                </Text>
                {item.status ? (
                  <Badge label={item.status} variant="info" />
                ) : null}
                {item.quantity !== null && item.quantity !== '' && item.quantity !== undefined ? (
                  <Text style={[styles.qty, { color: c.textMuted }]} numberOfLines={1}>
                    库存 {item.quantity}
                  </Text>
                ) : null}
              </View>
            </View>
          </View>
          {!selectMode ? (
            <Pressable
              onPress={() => setRelationItem(item)}
              style={({ pressed }) => [
                styles.actionRow,
                { borderColor: c.borderLight, opacity: pressed ? 0.6 : 1 },
              ]}
            >
              <Ticket size={14} stroke={c.primary} />
              <Text style={[styles.actionText, { color: c.primary }]}>关联卡券</Text>
            </Pressable>
          ) : null}
        </Card>
      </Pressable>
    );
  };

  /** 顶部工具条小按钮（同步/批量） */
  const renderToolChip = (opts: {
    label: string;
    onPress: () => void;
    disabled?: boolean;
    loading?: boolean;
    active?: boolean;
  }) => (
    <Pressable
      onPress={opts.onPress}
      disabled={opts.disabled || opts.loading}
      style={[
        styles.toolChip,
        {
          borderColor: opts.active ? c.primary : c.border,
          backgroundColor: opts.active ? c.primary : c.surface,
          opacity: opts.disabled && !opts.loading ? 0.4 : 1,
        },
      ]}
    >
      {opts.loading ? (
        <ActivityIndicator size="small" color={opts.active ? '#FFFFFF' : c.primary} />
      ) : (
        <Text
          style={[
            styles.toolChipText,
            { color: opts.active ? '#FFFFFF' : c.text },
          ]}
          numberOfLines={1}
        >
          {opts.label}
        </Text>
      )}
    </Pressable>
  );

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载商品..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      {/* 账号选择（胶囊横滑） */}
      <View style={[styles.accountBar, { borderBottomColor: c.borderLight }]}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRowScroll}>
          <Pressable
            onPress={() => setSelectedAccountId('')}
            style={[
              styles.chip,
              {
                borderColor: selectedAccountId === '' ? c.primary : c.border,
                backgroundColor: selectedAccountId === '' ? c.primary : c.surface,
              },
            ]}
          >
            <Text style={[styles.chipText, { color: selectedAccountId === '' ? '#FFFFFF' : c.text }]}>
              全部
            </Text>
          </Pressable>
          {accounts.map((acc) => {
            const selected = selectedAccountId === acc.id;
            return (
              <Pressable
                key={acc.id}
                onPress={() => setSelectedAccountId(acc.id)}
                style={[
                  styles.chip,
                  {
                    borderColor: selected ? c.primary : c.border,
                    backgroundColor: selected ? c.primary : c.surface,
                  },
                ]}
              >
                <Text style={[styles.chipText, { color: selected ? '#FFFFFF' : c.text }]} numberOfLines={1}>
                  {accountLabel(acc)}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>
        <Text style={[styles.countText, { color: c.textMuted }]}>
          共 {total} 件
        </Text>

        {/* 同步 / 批量工具条 */}
        <View style={styles.toolbar}>
          {renderToolChip({
            label: '同步本账号',
            onPress: () => handleSync('one'),
            disabled: !selectedAccountId || syncing !== '',
            loading: syncing === 'one',
          })}
          {renderToolChip({
            label: '同步全部',
            onPress: () => handleSync('all'),
            disabled: syncing !== '',
            loading: syncing === 'all',
          })}
          {renderToolChip({
            label: selectMode ? '退出批量' : '批量选择',
            onPress: toggleSelectMode,
            active: selectMode,
          })}
        </View>

        {/* 搜索框 */}
        <View style={[styles.searchRow, { borderColor: c.border }]}>
          <Search size={16} stroke={c.textMuted} />
          <Input
            value={keywordInput}
            onChangeText={setKeywordInput}
            placeholder="搜索商品ID / 标题 / 详情"
            placeholderTextColor={c.textMuted}
            style={styles.searchInput}
            returnKeyType="search"
          />
          {keywordInput ? (
            <Pressable onPress={() => setKeywordInput('')} hitSlop={8}>
              <X size={16} stroke={c.textMuted} />
            </Pressable>
          ) : null}
        </View>

        {/* 筛选 chips */}
        <View style={styles.filterRow}>
          {FILTER_CHIPS.map((chip) => {
            const active =
              chip.key === 'polished'
                ? filterPolished
                : chip.key === 'multiSpec'
                  ? filterMultiSpec
                  : filterMultiQty;
            const setActive = (v: boolean) => {
              if (chip.key === 'polished') setFilterPolished(v);
              else if (chip.key === 'multiSpec') setFilterMultiSpec(v);
              else setFilterMultiQty(v);
            };
            return (
              <Pressable
                key={chip.key}
                onPress={() => setActive(!active)}
                style={[
                  styles.filterChip,
                  {
                    borderColor: active ? c.primary : c.border,
                    backgroundColor: active ? c.primary : c.surface,
                  },
                ]}
              >
                <Text style={[styles.filterChipText, { color: active ? '#FFFFFF' : c.text }]}>
                  {chip.label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        {/* 批量操作条（仅选择模式显示） */}
        {selectMode ? (
          <View style={styles.selectBar}>
            <Text style={[styles.selectCount, { color: c.text }]}>
              已选 {selectedKeys.size} 件
            </Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.selectActions}>
              {renderToolChip({
                label: allSelected ? '取消全选' : '全选',
                onPress: toggleSelectAll,
              })}
              {renderToolChip({
                label: '下架',
                onPress: handleBatchOffline,
                loading: batchBusy === 'offline',
                disabled: batchBusy !== '' && batchBusy !== 'offline',
              })}
              {renderToolChip({
                label: '删记录',
                onPress: handleBatchDeleteRecords,
                loading: batchBusy === 'delete',
                disabled: batchBusy !== '' && batchBusy !== 'delete',
              })}
              {renderToolChip({
                label: '清关联',
                onPress: handleBatchClearRelations,
                loading: batchBusy === 'clear',
                disabled: batchBusy !== '' && batchBusy !== 'clear',
              })}
              {renderToolChip({ label: '退出', onPress: exitSelectMode })}
            </ScrollView>
          </View>
        ) : null}
      </View>

      <FlatList
        data={items}
        keyExtractor={(item) => `${item.cookie_id}-${item.item_id}-${item.id}`}
        renderItem={renderItem}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
        contentContainerStyle={styles.list}
        keyboardShouldPersistTaps="handled"
        onEndReached={handleLoadMore}
        onEndReachedThreshold={0.5}
        ListEmptyComponent={
          error ? (
            <EmptyState
              icon={Package}
              title="加载失败"
              message={error}
              error
              onRetry={handleRefresh}
            />
          ) : (
            <EmptyState
              icon={Package}
              title="暂无商品"
              message={
                keyword || filterPolished || filterMultiSpec || filterMultiQty
                  ? '没有符合条件的商品，试试调整搜索或筛选'
                  : selectedAccountId
                    ? '该账号暂无已发布商品'
                    : '暂无已发布商品'
              }
            />
          )
        }
        ListFooterComponent={
          loadingMore ? (
            <View style={styles.footer}>
              <ActivityIndicator size="small" color={c.primary} />
            </View>
          ) : items.length > 0 && page >= totalPages && totalPages > 0 ? (
            <Text style={[styles.footerText, { color: c.textMuted }]}>没有更多了</Text>
          ) : null
        }
      />

      {/* 商品 → 关联卡券弹窗 */}
      <ItemCardRelationModal
        itemId={relationItem?.item_id ?? ''}
        itemName={relationItem?.title ?? ''}
        visible={!!relationItem}
        onClose={() => setRelationItem(null)}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  accountBar: {
    borderBottomWidth: 1,
    paddingBottom: spacing.sm,
  },
  chipRowScroll: { gap: spacing.sm, paddingHorizontal: spacing.lg, paddingVertical: 2 },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
    borderWidth: 1,
    maxWidth: 160,
  },
  chipText: { ...typography.small },
  countText: {
    ...typography.small,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xs,
  },
  toolbar: {
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
  },
  toolChip: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 36,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    borderWidth: 1,
  },
  toolChipText: { ...typography.small, fontWeight: '600' },
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    marginHorizontal: spacing.lg,
    marginTop: spacing.sm,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
    borderRadius: radius.md,
  },
  searchInput: {
    flex: 1,
    minHeight: 40,
    borderWidth: 0,
    paddingHorizontal: 0,
    paddingVertical: spacing.xs,
  },
  filterRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
  },
  filterChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    borderWidth: 1,
  },
  filterChipText: { ...typography.small },
  selectBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
  },
  selectCount: { ...typography.small, fontWeight: '600' },
  selectActions: { gap: spacing.sm, paddingVertical: 2 },
  list: { padding: spacing.lg, paddingBottom: 80, gap: spacing.md },
  card: { padding: spacing.md },
  cardRow: { flexDirection: 'row', gap: spacing.md },
  checkWrap: { alignItems: 'center', justifyContent: 'center' },
  thumb: {
    width: 56,
    height: 56,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: { flex: 1, gap: spacing.xs, justifyContent: 'space-between' },
  title: { ...typography.caption, fontWeight: '600', lineHeight: 20 },
  metaRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flexWrap: 'wrap' },
  price: { ...typography.caption, fontWeight: '700' },
  qty: { ...typography.small },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    marginTop: spacing.sm,
    paddingTop: spacing.sm,
    borderTopWidth: 1,
    alignSelf: 'flex-end',
    paddingHorizontal: spacing.xs,
  },
  actionText: { ...typography.small, fontWeight: '600' },
  footer: { paddingVertical: spacing.lg, alignItems: 'center' },
  footerText: { ...typography.small, textAlign: 'center', paddingVertical: spacing.md },
});
