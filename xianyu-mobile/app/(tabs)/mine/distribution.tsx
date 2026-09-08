import { useState, useCallback, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { useRouter } from 'expo-router';
import { Card, Button, Loading } from '@/components/ui';
import { colors, spacing, typography } from '@/lib/theme';
import {
  getDealers,
  getAgentOrders,
  getDistributionFundFlows,
  getDockRecords,
  type Dealer,
  type AgentOrder,
  type FundFlow,
  type DockRecord,
} from '@/api/wrappers/distribution';

type TabKey = 'dealers' | 'orders' | 'flows' | 'records';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'dealers', label: '经销商' },
  { key: 'orders', label: '我的订单' },
  { key: 'flows', label: '资金流水' },
  { key: 'records', label: '对接记录' },
];

/** 分销扩展子页面快捷入口 */
const QUICK_LINKS: { label: string; href: string }[] = [
  { label: '货源广场', href: '/(tabs)/mine/distribution-supply' },
  { label: '分销卡券', href: '/(tabs)/mine/distribution-pickup' },
  { label: '下级分销商', href: '/(tabs)/mine/distribution-sub-dealers' },
];

export default function DistributionScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();

  const [activeTab, setActiveTab] = useState<TabKey>('dealers');
  const [dealers, setDealers] = useState<Dealer[]>([]);
  const [orders, setOrders] = useState<AgentOrder[]>([]);
  const [flows, setFlows] = useState<FundFlow[]>([]);
  const [records, setRecords] = useState<DockRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const loadedTabs = useRef<Set<TabKey>>(new Set());

  const loadTab = useCallback(async (tab: TabKey) => {
    setRefreshing(true);
    setError(null);
    try {
      if (tab === 'dealers') setDealers(await getDealers());
      else if (tab === 'orders') setOrders(await getAgentOrders());
      else if (tab === 'flows') setFlows(await getDistributionFundFlows());
      else setRecords(await getDockRecords());
      loadedTabs.current.add(tab);
    } catch (e) {
      setError((e as Error).message || '加载失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadTab(activeTab);
  }, [activeTab, loadTab]);

  function handleChangeTab(tab: TabKey) {
    if (tab === activeTab) return;
    setActiveTab(tab);
    // 仅首次进入某 Tab 时展示全屏 Loading，再次切回只做后台刷新
    if (!loadedTabs.current.has(tab)) setLoading(true);
  }

  /** 由状态文案派生展示色：成功/进行中/失败/其它 */
  function statusColor(status: string): string {
    const s = status.toLowerCase();
    if (
      ['success', 'completed', 'active', 'paid', 'delivered', 'confirmed', 'done'].some((k) =>
        s.includes(k),
      )
    )
      return c.success;
    if (
      ['pending', 'waiting', 'processing', 'running', 'started', 'ongoing'].some((k) =>
        s.includes(k),
      )
    )
      return c.warning;
    if (
      ['fail', 'error', 'reject', 'cancel', 'stopped', 'closed', 'timeout', 'expired'].some((k) =>
        s.includes(k),
      )
    )
      return c.error;
    return c.textMuted;
  }

  const refreshControl = (
    <RefreshControl refreshing={refreshing} onRefresh={() => loadTab(activeTab)} />
  );

  const empty = (
    <View style={styles.empty}>
      <Text style={[styles.emptyText, { color: c.textMuted }]}>
        {error ?? '暂无数据'}
      </Text>
    </View>
  );

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载中..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.quickNav}>
        {QUICK_LINKS.map((link) => (
          <Button
            key={link.href}
            label={link.label}
            variant="secondary"
            onPress={() => router.push(link.href as Parameters<typeof router.push>[0])}
            style={styles.quickBtn}
          />
        ))}
      </View>

      <View style={[styles.tabBar, { borderColor: c.border }]}>
        {TABS.map((t) => {
          const active = t.key === activeTab;
          return (
            <Pressable
              key={t.key}
              onPress={() => handleChangeTab(t.key)}
              style={[
                styles.tab,
                active && { borderBottomColor: c.primary, borderBottomWidth: 2 },
              ]}
            >
              <Text
                style={[
                  styles.tabText,
                  { color: active ? c.primary : c.textSecondary },
                ]}
              >
                {t.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {activeTab === 'dealers' && (
        <FlatList
          data={dealers}
          keyExtractor={(item) => String(item.id)}
          refreshControl={refreshControl}
          contentContainerStyle={styles.list}
          ListEmptyComponent={empty}
          renderItem={({ item }) => (
            <Card style={styles.card}>
              <View style={styles.cardRow}>
                <Text style={[styles.name, { color: c.text }]} numberOfLines={1}>
                  {item.username}
                </Text>
                <View style={[styles.badge, { backgroundColor: c.primaryLight }]}>
                  <Text style={[styles.badgeText, { color: c.primary }]}>
                    {item.level}
                  </Text>
                </View>
              </View>
              <View style={styles.cardRow}>
                <Text style={[styles.label, { color: c.textSecondary }]}>余额</Text>
                <Text style={[styles.balance, { color: c.text }]}>¥{item.balance}</Text>
              </View>
            </Card>
          )}
        />
      )}

      {activeTab === 'orders' && (
        <FlatList
          data={orders}
          keyExtractor={(item) => String(item.id)}
          refreshControl={refreshControl}
          contentContainerStyle={styles.list}
          ListEmptyComponent={empty}
          renderItem={({ item }) => (
            <Card style={styles.card}>
              <View style={styles.cardRow}>
                <Text style={[styles.name, { color: c.text }]} numberOfLines={1}>
                  {item.order_no}
                </Text>
                <Text style={[styles.status, { color: statusColor(item.status) }]}>
                  {item.status}
                </Text>
              </View>
              <View style={styles.cardRow}>
                <Text style={[styles.amount, { color: c.primary }]}>¥{item.amount}</Text>
                <Text style={[styles.time, { color: c.textMuted }]}>
                  {item.created_at}
                </Text>
              </View>
            </Card>
          )}
        />
      )}

      {activeTab === 'flows' && (
        <FlatList
          data={flows}
          keyExtractor={(item) => String(item.id)}
          refreshControl={refreshControl}
          contentContainerStyle={styles.list}
          ListEmptyComponent={empty}
          renderItem={({ item }) => {
            const amt = Number(item.amount);
            const positive = Number.isFinite(amt) && amt >= 0;
            return (
              <Card style={styles.card}>
                <View style={styles.cardRow}>
                  <Text style={[styles.name, { color: c.text }]}>{item.type}</Text>
                  <Text
                    style={[styles.amount, { color: positive ? c.success : c.error }]}
                  >
                    {positive ? '+' : ''}
                    {item.amount}
                  </Text>
                </View>
                {item.description ? (
                  <Text
                    style={[styles.desc, { color: c.textSecondary }]}
                    numberOfLines={2}
                  >
                    {item.description}
                  </Text>
                ) : null}
                <Text style={[styles.time, { color: c.textMuted }]}>
                  {item.created_at}
                </Text>
              </Card>
            );
          }}
        />
      )}

      {activeTab === 'records' && (
        <FlatList
          data={records}
          keyExtractor={(item) => String(item.id)}
          refreshControl={refreshControl}
          contentContainerStyle={styles.list}
          ListEmptyComponent={empty}
          renderItem={({ item }) => (
            <Card style={styles.card}>
              <View style={styles.cardRow}>
                <Text style={[styles.name, { color: c.text }]} numberOfLines={1}>
                  {item.card_key}
                </Text>
                <Text style={[styles.status, { color: statusColor(item.status) }]}>
                  {item.status}
                </Text>
              </View>
              <Text style={[styles.time, { color: c.textMuted }]}>
                {item.created_at}
              </Text>
            </Card>
          )}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  quickNav: {
    flexDirection: 'row',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
    gap: spacing.sm,
  },
  quickBtn: { flex: 1, minHeight: 36 },
  tabBar: { flexDirection: 'row', borderBottomWidth: 1 },
  tab: { flex: 1, paddingVertical: spacing.md, alignItems: 'center' },
  tabText: { ...typography.body, fontWeight: '600' },
  list: { padding: spacing.lg, gap: spacing.md },
  card: { gap: spacing.xs },
  cardRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  name: { ...typography.body, fontWeight: '600', flex: 1, marginRight: spacing.sm },
  label: { ...typography.caption },
  balance: { ...typography.body, fontWeight: '600' },
  amount: { ...typography.body, fontWeight: '600' },
  status: { ...typography.caption, fontWeight: '600' },
  desc: { ...typography.caption },
  time: { ...typography.small },
  badge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: 4 },
  badgeText: { ...typography.small, fontWeight: '600' },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
});
