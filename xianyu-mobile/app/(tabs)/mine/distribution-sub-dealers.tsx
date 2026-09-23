import { useState, useCallback, useEffect } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, TextInput, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button, Loading } from '@/components/ui';
import { colors, spacing, typography } from '@/lib/theme';
import {
  getSubDealers,
  getSubDealerDetails,
  type SubDealer,
  type SubDealerDockRecord,
} from '@/api/wrappers/distribution';

export default function DistributionSubDealersScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [dealers, setDealers] = useState<SubDealer[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  // 详情展开：user_id -> 明细列表 / 加载中 / 错误信息（懒加载，展开时才请求）
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [detailsMap, setDetailsMap] = useState<Record<number, SubDealerDockRecord[]>>({});
  const [detailLoadingId, setDetailLoadingId] = useState<number | null>(null);
  const [detailErrors, setDetailErrors] = useState<Record<number, string>>({});

  const loadDealers = useCallback(async (search: string) => {
    setRefreshing(true);
    setError(null);
    try {
      setDealers(await getSubDealers({ search }));
    } catch (e) {
      setError((e as Error).message || '加载失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadDealers(appliedSearch);
  }, [appliedSearch, loadDealers]);

  function handleSearch() {
    setAppliedSearch(searchInput.trim());
    setExpandedId(null);
  }

  function handleClearSearch() {
    setSearchInput('');
    if (appliedSearch) setAppliedSearch('');
    setExpandedId(null);
  }

  async function toggleExpand(dealer: SubDealer) {
    if (expandedId === dealer.user_id) {
      setExpandedId(null);
      return;
    }
    setExpandedId(dealer.user_id);
    if (detailsMap[dealer.user_id] || detailErrors[dealer.user_id]) return;
    setDetailLoadingId(dealer.user_id);
    try {
      const details = await getSubDealerDetails(dealer.user_id);
      setDetailsMap((prev) => ({ ...prev, [dealer.user_id]: details }));
    } catch (e) {
      setDetailErrors((prev) => ({ ...prev, [dealer.user_id]: (e as Error).message || '加载失败' }));
    } finally {
      setDetailLoadingId(null);
    }
  }

  const refreshControl = (
    <RefreshControl refreshing={refreshing} onRefresh={() => loadDealers(appliedSearch)} />
  );

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载下级分销商..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>

      <View style={styles.searchRow}>
        <TextInput
          value={searchInput}
          onChangeText={setSearchInput}
          onSubmitEditing={handleSearch}
          returnKeyType="search"
          placeholder="搜索分销商用户名"
          placeholderTextColor={c.textMuted}
          style={[styles.searchInput, { backgroundColor: c.surface, color: c.text, borderColor: c.border }]}
        />
        {searchInput.length > 0 && (
          <Pressable onPress={handleClearSearch} hitSlop={8}>
            <Text style={[styles.searchClear, { color: c.textMuted }]}>清除</Text>
          </Pressable>
        )}
        <Button label="搜索" variant="secondary" onPress={handleSearch} style={styles.searchBtn} />
      </View>

      <FlatList
        data={dealers}
        keyExtractor={(item) => String(item.user_id)}
        refreshControl={refreshControl}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: c.textMuted }]}>{error ?? '暂无下级分销商'}</Text>
          </View>
        }
        renderItem={({ item }) => {
          const expanded = expandedId === item.user_id;
          const details = detailsMap[item.user_id];
          const detailError = detailErrors[item.user_id];
          return (
            <Card style={styles.card}>
              <Pressable style={styles.cardRow} onPress={() => toggleExpand(item)}>
                <View style={styles.dealerInfo}>
                  <Text style={[styles.name, { color: c.text }]} numberOfLines={1}>
                    {item.username}
                  </Text>
                  {item.email ? (
                    <Text style={[styles.meta, { color: c.textMuted }]} numberOfLines={1}>
                      {item.email}
                    </Text>
                  ) : null}
                </View>
                <View style={[styles.badge, { backgroundColor: c.primaryLight }]}>
                  <Text style={[styles.badgeText, { color: c.primary }]}>
                    对接 {item.dock_count} 项
                  </Text>
                </View>
              </Pressable>

              {item.last_dock_time ? (
                <Text style={[styles.meta, { color: c.textMuted }]}>
                  最近对接: {item.last_dock_time}
                </Text>
              ) : null}

              {expanded && (
                <View style={styles.detailArea}>
                  {detailLoadingId === item.user_id && (
                    <Text style={[styles.meta, { color: c.textMuted }]}>加载明细中...</Text>
                  )}
                  {detailError && (
                    <Text style={[styles.meta, { color: c.error }]}>明细加载失败: {detailError}</Text>
                  )}
                  {details && details.length === 0 && (
                    <Text style={[styles.meta, { color: c.textMuted }]}>暂无对接明细</Text>
                  )}
                  {details && details.length > 0 && (
                    <View style={styles.detailList}>
                      <View style={[styles.detailHeaderRow, { borderBottomColor: c.borderLight }]}>
                        <Text style={[styles.detailHead, { color: c.textSecondary }]}>对接名称</Text>
                        <Text style={[styles.detailHead, { color: c.textSecondary }]}>价格</Text>
                        <Text style={[styles.detailHead, { color: c.textSecondary }]}>状态</Text>
                      </View>
                      {details.map((d) => (
                        <View key={d.id} style={styles.detailRow}>
                          <View style={styles.detailNameCol}>
                            <Text style={[styles.detailName, { color: c.text }]} numberOfLines={1}>
                              {d.dock_name || d.card_name}
                            </Text>
                            {d.card_name && d.dock_name ? (
                              <Text style={[styles.meta, { color: c.textMuted }]} numberOfLines={1}>
                                {d.card_name}
                              </Text>
                            ) : null}
                          </View>
                          <Text style={[styles.detailPrice, { color: c.primary }]}>¥{d.price}</Text>
                          <Text style={[styles.detailStatus, { color: d.status ? c.success : c.error }]}>
                            {d.status ? '启用' : '停用'}
                          </Text>
                        </View>
                      ))}
                    </View>
                  )}
                </View>
              )}
            </Card>
          );
        }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  searchInput: {
    flex: 1,
    ...typography.body,
    minHeight: 40,
    borderRadius: 8,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
  },
  searchClear: { ...typography.caption },
  searchBtn: { minHeight: 40 },
  list: { padding: spacing.lg, gap: spacing.md },
  card: { gap: spacing.xs },
  cardRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  dealerInfo: { flex: 1, marginRight: spacing.sm, gap: 2 },
  name: { ...typography.body, fontWeight: '600' },
  meta: { ...typography.caption },
  badge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: 4 },
  badgeText: { ...typography.small, fontWeight: '600' },
  detailArea: { marginTop: spacing.xs },
  detailList: { gap: spacing.xs },
  detailHeaderRow: {
    flexDirection: 'row',
    paddingBottom: spacing.xs,
    borderBottomWidth: 1,
  },
  detailHead: { ...typography.small, flex: 1 },
  detailRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  detailNameCol: { flex: 1, gap: 1 },
  detailName: { ...typography.caption, fontWeight: '600' },
  detailPrice: { ...typography.small, fontWeight: '600', minWidth: 56, textAlign: 'right' },
  detailStatus: { ...typography.small, fontWeight: '600', minWidth: 32, textAlign: 'right' },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
});
