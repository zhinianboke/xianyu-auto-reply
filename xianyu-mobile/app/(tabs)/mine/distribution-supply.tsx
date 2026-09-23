import { useState, useCallback, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, TextInput, Alert, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button, Loading } from '@/components/ui';
import { colors, spacing, typography } from '@/lib/theme';
import {
  getSupplyCards,
  getSubSupplyRecords,
  createDockRecord,
  createSubDockRecord,
  type SupplyCard,
  type SubSupplyRecord,
} from '@/api/wrappers/distribution';

type TabKey = 'card' | 'sub';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'card', label: '卡券货源' },
  { key: 'sub', label: '分销商货源' },
];

export default function DistributionSupplyScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [activeTab, setActiveTab] = useState<TabKey>('card');
  const [cards, setCards] = useState<SupplyCard[]>([]);
  const [subRecords, setSubRecords] = useState<SubSupplyRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchInput, setSearchInput] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');
  const [dockingId, setDockingId] = useState<string | null>(null);
  const loadedTabs = useRef<Set<TabKey>>(new Set());

  const loadTab = useCallback(
    async (tab: TabKey, search: string) => {
      setRefreshing(true);
      setError(null);
      try {
        if (tab === 'card') setCards(await getSupplyCards({ search }));
        else setSubRecords(await getSubSupplyRecords({ search }));
        loadedTabs.current.add(tab);
      } catch (e) {
        setError((e as Error).message || '加载失败');
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [],
  );

  useEffect(() => {
    loadTab(activeTab, appliedSearch);
  }, [activeTab, appliedSearch, loadTab]);

  function handleChangeTab(tab: TabKey) {
    if (tab === activeTab) return;
    setActiveTab(tab);
    if (!loadedTabs.current.has(tab)) setLoading(true);
  }

  function handleSearch() {
    setAppliedSearch(searchInput.trim());
  }

  function handleClearSearch() {
    setSearchInput('');
    if (appliedSearch) setAppliedSearch('');
  }

  /** 一级对接：以卡券名作为对接名称 */
  function handleDockCard(item: SupplyCard) {
    Alert.alert('确认对接', `对接货源「${item.name}」？`, [
      { text: '取消' },
      {
        text: '对接',
        onPress: async () => {
          setDockingId(`card-${item.id}`);
          try {
            await createDockRecord(item.id, item.name);
            Alert.alert('成功', '对接成功');
            await loadTab(activeTab, appliedSearch);
          } catch (e) {
            Alert.alert('对接失败', (e as Error).message);
          } finally {
            setDockingId(null);
          }
        },
      },
    ]);
  }

  /** 二级对接：对接上级分销商的对接记录 */
  function handleDockSub(item: SubSupplyRecord) {
    Alert.alert('确认对接', `对接「${item.source_username}」的货源「${item.dock_name}」？`, [
      { text: '取消' },
      {
        text: '对接',
        onPress: async () => {
          setDockingId(`sub-${item.id}`);
          try {
            await createSubDockRecord(item.id, item.dock_name || item.card_name);
            Alert.alert('成功', '对接成功');
            await loadTab(activeTab, appliedSearch);
          } catch (e) {
            Alert.alert('对接失败', (e as Error).message);
          } finally {
            setDockingId(null);
          }
        },
      },
    ]);
  }

  const refreshControl = (
    <RefreshControl refreshing={refreshing} onRefresh={() => loadTab(activeTab, appliedSearch)} />
  );

  const empty = (
    <View style={styles.empty}>
      <Text style={[styles.emptyText, { color: c.textMuted }]}>{error ?? '暂无货源'}</Text>
    </View>
  );

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载货源..." />
      </SafeAreaView>
    );
  }

  function renderDockButton(
    key: string,
    docked: boolean,
    onPress: () => void,
  ) {
    return (
      <Button
        label={docked ? '已对接' : '对接'}
        variant={docked ? 'secondary' : 'primary'}
        disabled={docked}
        loading={dockingId === key}
        onPress={onPress}
        style={styles.dockBtn}
      />
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>

      <View style={[styles.tabBar, { borderColor: c.border }]}>
        {TABS.map((t) => {
          const active = t.key === activeTab;
          return (
            <Pressable
              key={t.key}
              onPress={() => handleChangeTab(t.key)}
              style={[styles.tab, active && { borderBottomColor: c.primary, borderBottomWidth: 2 }]}
            >
              <Text style={[styles.tabText, { color: active ? c.primary : c.textSecondary }]}>
                {t.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <View style={styles.searchRow}>
        <TextInput
          value={searchInput}
          onChangeText={setSearchInput}
          onSubmitEditing={handleSearch}
          returnKeyType="search"
          placeholder="搜索货源名称/描述"
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

      {activeTab === 'card' && (
        <FlatList
          data={cards}
          keyExtractor={(item) => String(item.id)}
          refreshControl={refreshControl}
          contentContainerStyle={styles.list}
          ListEmptyComponent={empty}
          renderItem={({ item }) => (
            <Card style={styles.card}>
              <View style={styles.cardRow}>
                <Text style={[styles.name, { color: c.text }]} numberOfLines={1}>
                  {item.name}
                </Text>
                <View style={[styles.badge, { backgroundColor: c.primaryLight }]}>
                  <Text style={[styles.badgeText, { color: c.primary }]}>{item.type}</Text>
                </View>
              </View>
              {item.description ? (
                <Text style={[styles.desc, { color: c.textSecondary }]} numberOfLines={2}>
                  {item.description}
                </Text>
              ) : null}
              {item.is_multi_spec && item.spec_value ? (
                <Text style={[styles.desc, { color: c.textMuted }]} numberOfLines={1}>
                  {item.spec_name || '规格'}: {item.spec_value}
                </Text>
              ) : null}
              <View style={styles.cardRow}>
                <Text style={[styles.price, { color: c.primary }]}>¥{item.price}</Text>
                {renderDockButton(`card-${item.id}`, item.is_docked, () => handleDockCard(item))}
              </View>
            </Card>
          )}
        />
      )}

      {activeTab === 'sub' && (
        <FlatList
          data={subRecords}
          keyExtractor={(item) => String(item.id)}
          refreshControl={refreshControl}
          contentContainerStyle={styles.list}
          ListEmptyComponent={empty}
          renderItem={({ item }) => (
            <Card style={styles.card}>
              <View style={styles.cardRow}>
                <Text style={[styles.name, { color: c.text }]} numberOfLines={1}>
                  {item.dock_name || item.card_name}
                </Text>
                <View style={[styles.badge, { backgroundColor: c.warning }]}>
                  <Text style={styles.badgeText}>{item.source_username || '分销商'}</Text>
                </View>
              </View>
              <Text style={[styles.desc, { color: c.textSecondary }]} numberOfLines={1}>
                卡券: {item.card_name}
              </Text>
              {item.is_multi_spec && item.spec_value ? (
                <Text style={[styles.desc, { color: c.textMuted }]} numberOfLines={1}>
                  {item.spec_name || '规格'}: {item.spec_value}
                </Text>
              ) : null}
              <View style={styles.cardRow}>
                <Text style={[styles.price, { color: c.primary }]}>
                  ¥{item.sub_dock_price || item.card_price}
                </Text>
                {renderDockButton(`sub-${item.id}`, item.is_docked, () => handleDockSub(item))}
              </View>
            </Card>
          )}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  tabBar: { flexDirection: 'row', borderBottomWidth: 1 },
  tab: { flex: 1, paddingVertical: spacing.md, alignItems: 'center' },
  tabText: { ...typography.body, fontWeight: '600' },
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
  name: { ...typography.body, fontWeight: '600', flex: 1, marginRight: spacing.sm },
  desc: { ...typography.caption },
  price: { ...typography.body, fontWeight: '600' },
  badge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: 4 },
  badgeText: { color: '#FFF', fontSize: 11, fontWeight: '600' },
  dockBtn: { minHeight: 36, minWidth: 80 },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
});
