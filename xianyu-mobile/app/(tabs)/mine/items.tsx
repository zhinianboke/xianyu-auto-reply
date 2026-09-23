import { useState, useCallback, useEffect, useRef } from 'react';
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
import { Card, EmptyState, Badge, Loading } from '@/components/ui';
import { Package, Ticket } from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { getXianyuItems, type XianyuItem } from '@/api/wrappers/items';
import { batchDeleteItems } from '@/api/wrappers/item-edit';
import { getAccountOptions, type AccountOption } from '@/api/wrappers/accounts';
import { ItemCardRelationModal } from '@/components/card-relation/ItemCardRelationModal';

const PAGE_SIZE = 20;

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

  // 切换账号会触发两次 loadItems（useEffect 依赖变更 + selectedAccountId 传入），
  // 用 ref 记录最新请求序号，丢弃过期响应
  const reqSeqRef = useRef(0);

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

      if (append) {
        setLoadingMore(true);
      } else if (opts?.fromPage == null) {
        setRefreshing(true);
      }
      setError(null);
      try {
        const res = await getXianyuItems(targetPage, PAGE_SIZE, accountId || undefined);
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
  }, [selectedAccountId, loadItems]);

  const handleRefresh = useCallback(() => {
    loadItems(selectedAccountId);
  }, [selectedAccountId, loadItems]);

  const handleLoadMore = useCallback(() => {
    if (loadingMore || refreshing || loading) return;
    if (totalPages > 0 && page >= totalPages) return;
    loadItems(selectedAccountId, { append: true, fromPage: page + 1 });
  }, [loadingMore, refreshing, loading, totalPages, page, selectedAccountId, loadItems]);

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
        { text: '取消', style: 'cancel' },
      ]);
    },
    [handleEdit, handleDelete],
  );

  const accountLabel = (acc: AccountOption) => acc.remark || acc.id;

  const renderItem = ({ item }: { item: XianyuItem }) => (
    <Pressable
      onPress={() => handleEdit(item)}
      onLongPress={() => handleLongPress(item)}
      style={({ pressed }) => ({ opacity: pressed ? 0.6 : 1 })}
    >
      <Card style={styles.card}>
        <View style={styles.cardRow}>
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
      </Card>
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
              message={selectedAccountId ? '该账号暂无已发布商品' : '暂无已发布商品'}
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
  list: { padding: spacing.lg, gap: spacing.md },
  card: { padding: spacing.md },
  cardRow: { flexDirection: 'row', gap: spacing.md },
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
