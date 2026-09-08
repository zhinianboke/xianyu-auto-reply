import { useState, useEffect, useCallback, useRef } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, Switch, ScrollView, Alert, Modal, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button, Input, Loading, EmptyState } from '@/components/ui';
import { ShieldBan } from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getPersonalBlacklist,
  createPersonalBlacklist,
  deletePersonalBlacklist,
  getPlatformBlacklist,
  type PersonalBlacklistItem,
  type PlatformBlacklistItem,
} from '@/api/wrappers/blacklist-manage';
import { useAccountsStore } from '@/stores/accounts';
import { usePagedList } from '@/hooks/usePagedList';

type TabKey = 'personal' | 'platform';

const TABS: [TabKey, string][] = [
  ['personal', '个人黑名单'],
  ['platform', '平台黑名单'],
];

/** 个人黑名单每页条数（对齐原 getPersonalBlacklist 默认值） */
const PERSONAL_PAGE_SIZE = 50;

/** "2026-01-01T12:34:56" -> "2026-01-01 12:34" */
function formatDate(value?: string): string {
  if (!value) return '';
  return value.replace('T', ' ').slice(0, 16);
}

export default function BlacklistScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [tab, setTab] = useState<TabKey>('personal');
  const [platformItems, setPlatformItems] = useState<PlatformBlacklistItem[]>([]);
  const accounts = useAccountsStore((s) => s.options);
  const loadAccountOptions = useAccountsStore((s) => s.load);
  const [accountId, setAccountId] = useState<string | null>(null);
  // 个人黑名单（offset 分页）：后端为 page 语义，在 fetchPage 内按 offset 换算页码
  const {
    items: personalItems,
    loading,
    refreshing: personalRefreshing,
    loadingMore: personalLoadingMore,
    refresh: refreshPersonal,
    loadMore: loadMorePersonal,
  } = usePagedList<PersonalBlacklistItem>({
    mode: 'offset',
    pageSize: PERSONAL_PAGE_SIZE,
    fetchPage: ({ offset = 0, limit = PERSONAL_PAGE_SIZE }) =>
      getPersonalBlacklist(Math.floor(offset / limit) + 1, limit),
    onError: (e) => Alert.alert('加载失败', e.message),
  });
  // 平台黑名单下拉刷新状态（不走 usePagedList）
  const [platformRefreshing, setPlatformRefreshing] = useState(false);
  const [addVisible, setAddVisible] = useState(false);
  const [newBuyerIds, setNewBuyerIds] = useState('');
  const [newReason, setNewReason] = useState('');
  // 平台黑名单请求序号：防止快速切换账号时旧响应覆盖新数据
  const platformSeq = useRef(0);

  const fetchPlatform = useCallback(async (id: string) => {
    const seq = ++platformSeq.current;
    try {
      const items = await getPlatformBlacklist(id);
      if (seq !== platformSeq.current) return;
      setPlatformItems(items);
    } catch (e) {
      if (seq === platformSeq.current) Alert.alert('加载平台黑名单失败', (e as Error).message);
    }
  }, []);

  const loadAccounts = useCallback(async () => {
    try {
      await loadAccountOptions();
      const opts = useAccountsStore.getState().options;
      // 默认选中第一个账号并预加载其平台黑名单
      if (opts.length > 0) {
        setAccountId(opts[0].id);
        await fetchPlatform(opts[0].id);
      }
    } catch (e) { Alert.alert('加载账号失败', (e as Error).message); }
  }, [fetchPlatform, loadAccountOptions]);

  // 个人黑名单首页由 usePagedList 的 auto 挂载拉取，这里只负责账号与平台黑名单
  useEffect(() => { loadAccounts(); }, [loadAccounts]);

  async function handleSelectAccount(id: string) {
    setAccountId(id);
    await fetchPlatform(id);
  }

  async function handleRefresh() {
    if (tab === 'personal') { await refreshPersonal(); return; }
    setPlatformRefreshing(true);
    if (accountId) await fetchPlatform(accountId);
    setPlatformRefreshing(false);
  }

  async function handleAdd() {
    if (!newBuyerIds.trim()) { Alert.alert('提示', '请输入买家ID，多个用逗号分隔'); return; }
    try {
      const res = await createPersonalBlacklist(newBuyerIds.trim(), newReason.trim() || undefined);
      setNewBuyerIds(''); setNewReason(''); setAddVisible(false);
      const extra = res.skipped > 0 ? `，跳过重复 ${res.skipped} 条` : '';
      Alert.alert('添加成功', res.message ?? `已加入黑名单 ${res.count} 条${extra}`);
      await refreshPersonal();
    } catch (e) { Alert.alert('添加失败', (e as Error).message); }
  }

  function handleDelete(item: PersonalBlacklistItem) {
    Alert.alert('确认删除', `将买家 ${item.buyer_id} 移出个人黑名单？`, [
      { text: '取消' },
      { text: '删除', style: 'destructive', onPress: async () => {
        try { await deletePersonalBlacklist(item.id); await refreshPersonal(); }
        catch (e) { Alert.alert('删除失败', (e as Error).message); }
      } },
    ]);
  }

  if (loading) {
    return (<SafeAreaView style={[styles.container, { backgroundColor: c.background }]}><Loading label="加载黑名单..." /></SafeAreaView>);
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        {tab === 'personal' && <Button label="添加" onPress={() => setAddVisible(true)} variant="secondary" />}
      </View>

      <View style={[styles.tabBar, { backgroundColor: c.surface, borderBottomColor: c.borderLight }]}>
        {TABS.map(([key, label]) => (
          <Pressable key={key} style={styles.tabItem} onPress={() => setTab(key)}>
            <Text style={[styles.tabText, { color: tab === key ? c.primary : c.textSecondary }, tab === key && styles.tabTextActive]}>{label}</Text>
            {tab === key && <View style={[styles.tabIndicator, { backgroundColor: c.primary }]} />}
          </Pressable>
        ))}
      </View>

      {tab === 'personal' ? (
        <FlatList
          data={personalItems}
          keyExtractor={(item) => String(item.id)}
          refreshControl={<RefreshControl refreshing={personalRefreshing} onRefresh={handleRefresh} />}
          onEndReached={loadMorePersonal}
          onEndReachedThreshold={0.3}
          ListFooterComponent={
            personalLoadingMore ? (
              <Text style={[styles.loadingMore, { color: c.textMuted }]}>加载中...</Text>
            ) : null
          }
          renderItem={({ item }) => (
            <Pressable onLongPress={() => handleDelete(item)} delayLongPress={400}>
              <Card style={styles.card}>
                <View style={styles.cardRow}>
                  <View style={styles.cardContent}>
                    <Text style={[styles.buyerId, { color: c.text }]} numberOfLines={1}>{item.buyer_id}</Text>
                    {item.reason ? <Text style={[styles.reason, { color: c.textSecondary }]} numberOfLines={2}>{item.reason}</Text> : null}
                    <Text style={[styles.time, { color: c.textMuted }]}>{formatDate(item.created_at)}</Text>
                  </View>
                  {/* API 暂无启用开关接口，此处仅作状态展示 */}
                  <Switch
                    value={item.is_enabled}
                    disabled
                    trackColor={{ false: c.border, true: c.primary }}
                  />
                </View>
              </Card>
            </Pressable>
          )}
          ListEmptyComponent={<EmptyState icon={ShieldBan} title="暂无黑名单记录" message="长按列表项可删除" actionLabel="添加黑名单" onAction={() => setAddVisible(true)} />}
          contentContainerStyle={styles.list}
        />
      ) : (
        <FlatList
          data={platformItems}
          keyExtractor={(item) => item.id || item.buyer_id}
          refreshControl={<RefreshControl refreshing={platformRefreshing} onRefresh={handleRefresh} />}
          ListHeaderComponent={
            accounts.length === 0 ? (
              <View style={styles.accountBar}><Text style={[styles.accountEmpty, { color: c.textMuted }]}>暂无可用账号</Text></View>
            ) : (
              <View style={styles.accountBar}>
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.accountChips}>
                  {accounts.map((a) => (
                    <Pressable key={a.id} onPress={() => handleSelectAccount(a.id)}
                      style={[styles.chip, { backgroundColor: accountId === a.id ? c.primary : c.surface, borderColor: accountId === a.id ? c.primary : c.border }]}>
                      <Text style={[styles.chipText, { color: accountId === a.id ? '#FFF' : c.text }]} numberOfLines={1}>{a.remark || a.id}</Text>
                    </Pressable>
                  ))}
                </ScrollView>
              </View>
            )
          }
          renderItem={({ item }) => (
            <Card style={styles.card}>
              <View style={styles.cardContent}>
                <View style={styles.platformRow}>
                  <Text style={[styles.buyerId, { color: c.text }]} numberOfLines={1}>{item.buyer_id}</Text>
                  {item.buyer_nick ? <Text style={[styles.buyerNick, { color: c.textSecondary }]} numberOfLines={1}>{item.buyer_nick}</Text> : null}
                </View>
                {item.remark ? <Text style={[styles.reason, { color: c.textSecondary }]} numberOfLines={2}>{item.remark}</Text> : null}
              </View>
            </Card>
          )}
          ListEmptyComponent={<EmptyState icon={ShieldBan} title="该账号暂无平台黑名单" />}
          contentContainerStyle={styles.list}
        />
      )}

      <Modal visible={addVisible} transparent animationType="fade" onRequestClose={() => setAddVisible(false)}>
        <Pressable style={styles.overlay} onPress={() => setAddVisible(false)}>
          <Pressable style={[styles.modal, { backgroundColor: c.surface }]} onPress={() => {}}>
            <Text style={[styles.modalTitle, { color: c.text }]}>添加黑名单</Text>
            <Text style={[styles.label, { color: c.textSecondary }]}>买家ID（支持逗号分隔批量）</Text>
            <Input
              value={newBuyerIds}
              onChangeText={setNewBuyerIds}
              placeholder="如: tb12345, tb67890"
              autoCapitalize="none"
              autoCorrect={false}
              style={styles.input}
            />
            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.sm }]}>原因（可选）</Text>
            <Input
              value={newReason}
              onChangeText={setNewReason}
              placeholder="拉黑原因"
              autoCapitalize="none"
              autoCorrect={false}
              style={styles.input}
            />
            <View style={styles.modalActions}>
              <Button label="取消" variant="secondary" onPress={() => setAddVisible(false)} style={styles.modalBtn} />
              <Button label="添加" onPress={handleAdd} style={styles.modalBtn} />
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  list: { padding: spacing.lg, gap: spacing.md },
  loadingMore: { textAlign: 'center', padding: spacing.md },
  tabBar: { flexDirection: 'row', borderBottomWidth: 1 },
  tabItem: { flex: 1, alignItems: 'center', paddingVertical: spacing.md, position: 'relative' },
  tabText: { ...typography.body },
  tabTextActive: { fontWeight: '600' },
  tabIndicator: { position: 'absolute', bottom: 0, width: 32, height: 3, borderRadius: radius.full },
  card: { gap: spacing.xs },
  cardRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardContent: { flex: 1, marginRight: spacing.md, gap: spacing.xs },
  buyerId: { ...typography.body, fontWeight: '600' },
  reason: { ...typography.caption },
  time: { ...typography.small },
  platformRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  buyerNick: { ...typography.caption, flex: 1 },
  accountBar: { paddingHorizontal: spacing.lg, paddingTop: spacing.md },
  accountChips: { gap: spacing.sm },
  chip: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.full, borderWidth: 1, maxWidth: 160 },
  chipText: { ...typography.caption },
  accountEmpty: { ...typography.caption, paddingVertical: spacing.sm },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  overlay: { flex: 1, justifyContent: 'center', padding: spacing.lg, backgroundColor: 'rgba(0,0,0,0.5)' },
  modal: { borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  modalTitle: { ...typography.heading, textAlign: 'center' },
  label: { ...typography.caption },
  input: { marginTop: spacing.xs },
  modalActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  modalBtn: { flex: 1 },
});
