import { useState, useCallback, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  RefreshControl,
  Pressable,
  ScrollView,
  Image,
  ActivityIndicator,
  Alert,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { CheckSquare, Square, Package } from 'lucide-react-native';
import { EmptyState, Button, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { getXianyuItems, type XianyuItem } from '@/api/wrappers/items';
import { getAccountOptions, type AccountOption } from '@/api/wrappers/accounts';
import {
  getCardItemIds,
  updateCardItems,
} from '@/api/wrappers/card-relation';

const PAGE_SIZE = 20;

export default function CardItemRelationScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();
  const params = useLocalSearchParams<{ cardId: string; cardName: string }>();
  const cardId = Number(params.cardId);
  const cardName = params.cardName || `卡券 #${cardId}`;

  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');
  const [items, setItems] = useState<XianyuItem[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);

  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [saving, setSaving] = useState(false);

  // 选中态以 getCardItemIds 为准（含已删除商品的孤儿关联），保存时不丢失
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  // 切换账号/分页会触发重复请求，用序号丢弃过期响应
  const reqSeqRef = useRef(0);

  const loadAccounts = useCallback(async () => {
    try {
      const opts = await getAccountOptions();
      setAccounts(opts);
    } catch {
      // 账号加载失败不阻塞商品列表
    }
  }, []);

  const loadAssociated = useCallback(async () => {
    if (!Number.isFinite(cardId) || cardId <= 0) return;
    try {
      const ids = await getCardItemIds(cardId);
      setSelectedIds(new Set(ids));
    } catch {
      // 已关联加载失败不阻塞列表
    }
  }, [cardId]);

  const loadItems = useCallback(
    async (accountId: string, opts?: { append?: boolean; fromPage?: number }) => {
      const append = opts?.append ?? false;
      const targetPage = opts?.fromPage ?? 1;
      const seq = ++reqSeqRef.current;
      if (append) setLoadingMore(true);
      else if (opts?.fromPage == null) setRefreshing(true);
      try {
        const res = await getXianyuItems(targetPage, PAGE_SIZE, accountId || undefined);
        if (seq !== reqSeqRef.current) return;
        setItems((prev) => (append ? [...prev, ...res.items] : res.items));
        setPage(res.page);
        setTotalPages(res.total_pages);
        setTotal(res.total);
      } catch (e) {
        if (seq !== reqSeqRef.current) return;
        Alert.alert('加载失败', (e as Error).message);
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
    loadAssociated();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    setLoading(true);
    loadItems(selectedAccountId);
  }, [selectedAccountId, loadItems]);

  const handleRefresh = useCallback(() => {
    loadItems(selectedAccountId);
  }, [selectedAccountId, loadItems]);

  const handleLoadMore = useCallback(() => {
    if (loadingMore || refreshing || loading) return;
    if (totalPages > 0 && page >= totalPages) return;
    loadItems(selectedAccountId, { append: true, fromPage: page + 1 });
  }, [loadingMore, refreshing, loading, totalPages, page, selectedAccountId, loadItems]);

  const toggle = useCallback((itemId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(itemId)) next.delete(itemId);
      else next.add(itemId);
      return next;
    });
  }, []);

  const allLoadedSelected =
    items.length > 0 && items.every((x) => selectedIds.has(x.item_id));

  const handleSelectAll = useCallback(() => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allLoadedSelected) {
        items.forEach((x) => next.delete(x.item_id));
      } else {
        items.forEach((x) => next.add(x.item_id));
      }
      return next;
    });
  }, [allLoadedSelected, items]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      await updateCardItems(cardId, Array.from(selectedIds));
      Alert.alert('已保存', `已关联 ${selectedIds.size} 个商品`, [
        { text: '好的', onPress: () => router.back() },
      ]);
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setSaving(false);
    }
  }, [cardId, selectedIds, router]);

  const accountLabel = (acc: AccountOption) => acc.remark || acc.id;

  const renderItem = ({ item }: { item: XianyuItem }) => {
    const checked = selectedIds.has(item.item_id);
    return (
      <Pressable
        onPress={() => toggle(item.item_id)}
        style={({ pressed }) => [
          styles.cardRow,
          { backgroundColor: checked ? c.primaryLight : c.surface, opacity: pressed ? 0.9 : 1 },
        ]}
      >
        {checked ? (
          <CheckSquare size={18} stroke={c.primary} />
        ) : (
          <Square size={18} stroke={c.textMuted} />
        )}
        {item.image ? (
          <Image source={{ uri: item.image }} style={[styles.thumb, { backgroundColor: c.surfaceAlt }]} />
        ) : (
          <View style={[styles.thumb, { backgroundColor: c.surfaceAlt }]}>
            <Package size={20} stroke={c.textMuted} />
          </View>
        )}
        <View style={styles.body}>
          <Text style={[styles.title, { color: c.text }]} numberOfLines={2}>
            {item.title || '无标题'}
          </Text>
          <Text style={[styles.meta, { color: c.textMuted }]} numberOfLines={1}>
            {item.price ? `¥${item.price}` : '价格未知'}
            {item.quantity !== null && item.quantity !== '' && item.quantity !== undefined
              ? ` · 库存 ${item.quantity}`
              : ''}
          </Text>
        </View>
      </Pressable>
    );
  };

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
      </View>

      {/* 工具栏：标题 + 全选 + 计数 */}
      <View style={[styles.toolbar, { borderBottomColor: c.borderLight, backgroundColor: c.surfaceAlt }]}>
        <View style={styles.toolbarLeft}>
          <Text style={[styles.toolbarTitle, { color: c.text }]} numberOfLines={1}>
            {cardName}
          </Text>
          <Text style={[styles.count, { color: c.textMuted }]}>
            共 {total} 个 · 已选 {selectedIds.size}
          </Text>
        </View>
        <Pressable
          onPress={handleSelectAll}
          disabled={items.length === 0}
          style={({ pressed }) => [
            styles.selectAll,
            { backgroundColor: allLoadedSelected ? c.primaryLight : c.surface, opacity: pressed ? 0.7 : 1 },
          ]}
        >
          {allLoadedSelected ? (
            <CheckSquare size={13} stroke={c.primary} />
          ) : (
            <Square size={13} stroke={c.textMuted} />
          )}
          <Text style={[styles.selectAllText, { color: allLoadedSelected ? c.primary : c.textSecondary }]}>
            {allLoadedSelected ? '取消全选' : '全选'}
          </Text>
        </Pressable>
      </View>

      <FlatList
        data={items}
        keyExtractor={(item) => `${item.cookie_id}-${item.item_id}-${item.id}`}
        renderItem={renderItem}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />}
        contentContainerStyle={styles.list}
        onEndReached={handleLoadMore}
        onEndReachedThreshold={0.3}
        ListEmptyComponent={
          <EmptyState
            icon={Package}
            title="暂无商品"
            message={selectedAccountId ? '该账号暂无已发布商品' : '暂无已发布商品'}
          />
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

      <View style={[styles.footerBar, { backgroundColor: c.surface, borderTopColor: c.borderLight }]}>
        <Button
          label="取消"
          variant="ghost"
          onPress={() => router.back()}
          style={styles.footerBtn}
        />
        <Button
          label={`保存 (${selectedIds.size} 个商品)`}
          onPress={handleSave}
          loading={saving}
          disabled={saving}
          style={styles.footerBtn}
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  accountBar: { borderBottomWidth: 1, paddingBottom: spacing.sm },
  chipRowScroll: { gap: spacing.sm, paddingHorizontal: spacing.lg, paddingVertical: 2 },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
    borderWidth: 1,
    maxWidth: 160,
  },
  chipText: { ...typography.small },
  toolbar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
  },
  toolbarLeft: { flex: 1, gap: 2 },
  toolbarTitle: { ...typography.caption, fontWeight: '600' },
  count: { ...typography.small },
  selectAll: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  selectAllText: { ...typography.small, fontWeight: '600' },
  list: { padding: spacing.lg, gap: spacing.sm },
  cardRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    padding: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  thumb: {
    width: 44,
    height: 44,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: { flex: 1, gap: 2, justifyContent: 'space-between' },
  title: { ...typography.small, fontWeight: '600', lineHeight: 18 },
  meta: { ...typography.micro },
  footer: { paddingVertical: spacing.lg, alignItems: 'center' },
  footerText: { ...typography.small, textAlign: 'center', paddingVertical: spacing.md },
  footerBar: {
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
  },
  footerBtn: { flex: 1 },
});
