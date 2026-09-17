import { useState, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, RefreshControl, Alert, Pressable } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { useRouter } from 'expo-router';
import {
  MessageCircle,
  ShoppingBag,
  Wifi,
  Users,
  TrendingUp,
  Package,
  Clock,
  CheckCircle,
  DollarSign,
} from 'lucide-react-native';
import { Card, StatCard, Loading } from '@/components/ui';
import { colors, spacing, typography } from '@/lib/theme';
import {
  getCookieStats,
  getOrderTrend,
  getOrderSummary,
  type CookieStats,
  type OrderTrendPoint,
  type OrderStatusSummary,
} from '@/api/wrappers/dashboard';
import { useAccountsStore } from '@/stores/accounts';

const EMPTY_STATS: CookieStats = {
  total_accounts: 0,
  active_accounts: 0,
  total_keywords: 0,
  total_orders: 0,
  today_reply_count: 0,
  yesterday_reply_count: 0,
  account_limit: null,
  used_account_count: 0,
  remaining_account_count: null,
};

const EMPTY_SUMMARY: OrderStatusSummary = {
  pending_ship: { count: 0, amount: 0 },
  pending_confirm: { count: 0, amount: 0 },
  pending_rate: { count: 0, amount: 0 },
  total_amount: 0,
};

/** 金额展示：0 显示 0，保留两位小数 */
function formatAmount(n: number): string {
  return `¥${n.toFixed(2)}`;
}

type TrendMode = 'amount' | 'count';

export default function DashboardScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();

  const accounts = useAccountsStore((s) => s.options);
  const loadAccounts = useAccountsStore((s) => s.load);
  // 真实数据源：GET /api/v1/cookies/stats + /stats/order-trend + /stats/order-summary
  const [stats, setStats] = useState<CookieStats>(EMPTY_STATS);
  const [trend, setTrend] = useState<OrderTrendPoint[]>([]);
  const [orderSummary, setOrderSummary] = useState<OrderStatusSummary>(EMPTY_SUMMARY);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [trendMode, setTrendMode] = useState<TrendMode>('amount');
  const [trendDays, setTrendDays] = useState<7 | 30>(7);

  // force=true 用于下拉刷新绕过 60s TTL
  const load = useCallback(
    async (force = false) => {
      setRefreshing(true);
      try {
        await loadAccounts(force);
        const days = trendDays;
        const [statsRes, trendRes, summaryRes] = await Promise.all([
          getCookieStats(),
          getOrderTrend(days).catch(() => [] as OrderTrendPoint[]),
          getOrderSummary().catch(() => EMPTY_SUMMARY),
        ]);
        setStats(statsRes);
        setTrend(trendRes);
        setOrderSummary(summaryRes);
      } catch (e) {
        console.error('加载仪表盘失败', e);
        Alert.alert('加载失败', (e as Error).message);
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [loadAccounts, trendDays],
  );

  // 切换天数时重新拉取趋势
  const reloadTrend = useCallback(
    async (days: 7 | 30) => {
      setTrendDays(days);
      try {
        const trendRes = await getOrderTrend(days);
        setTrend(trendRes);
      } catch {
        // ignore
      }
    },
    [],
  );

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <SafeAreaView
        style={[styles.container, { backgroundColor: c.background }]}
        edges={['left', 'right', 'bottom']}
      >
        <Loading label="加载仪表盘..." />
      </SafeAreaView>
    );
  }

  // 上方统计卡只放可操作的高价值指标；账号明细见下方"账号概览"卡。
  const statCards: {
    label: string;
    value: number;
    icon: typeof MessageCircle;
    accent: string;
    onPress: () => void;
  }[] = [
    {
      label: '今日回复',
      value: stats.today_reply_count,
      icon: MessageCircle,
      accent: c.info,
      onPress: () => router.push('/(tabs)/messages'),
    },
    {
      label: '总订单',
      value: stats.total_orders,
      icon: ShoppingBag,
      accent: c.primary,
      onPress: () => router.push('/(tabs)/orders'),
    },
    {
      label: '启用账号',
      value: stats.active_accounts,
      icon: Wifi,
      accent: c.success,
      onPress: () => router.push('/(tabs)/mine/accounts'),
    },
    {
      label: '账号总数',
      value: stats.total_accounts,
      icon: Users,
      accent: c.warning,
      onPress: () => router.push('/(tabs)/mine/accounts'),
    },
  ];

  // 订单状态概况卡片
  const statusCards = [
    {
      label: '待发货',
      count: orderSummary.pending_ship.count,
      amount: orderSummary.pending_ship.amount,
      icon: Package,
      color: c.primary,
    },
    {
      label: '待确认',
      count: orderSummary.pending_confirm.count,
      amount: orderSummary.pending_confirm.amount,
      icon: Clock,
      color: c.warning,
    },
    {
      label: '待评价',
      count: orderSummary.pending_rate.count,
      amount: orderSummary.pending_rate.amount,
      icon: CheckCircle,
      color: '#a855f7',
    },
  ];

  // 趋势数据
  const maxAmount = trend.reduce((m, p) => Math.max(m, p.amount), 0);
  const maxCount = trend.reduce((m, p) => Math.max(m, p.count), 0);
  const trendTotalCount = trend.reduce((sum, p) => sum + p.count, 0);
  const trendTotalAmount = trend.reduce((sum, p) => sum + p.amount, 0);
  const maxVal = trendMode === 'amount' ? maxAmount : maxCount;

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: c.background }]}
      edges={['left', 'right', 'bottom']}
    >
      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} />
        }
      >
        <View style={styles.grid}>
          {[0, 2].map((start) => (
            <View key={start} style={styles.gridRow}>
              {statCards.slice(start, start + 2).map((s) => (
                <StatCard
                  key={s.label}
                  label={s.label}
                  value={s.value}
                  icon={s.icon}
                  accent={s.accent}
                  onPress={s.onPress}
                />
              ))}
            </View>
          ))}
        </View>

        {/* 订单概况卡片 */}
        <Card style={styles.infoCard}>
          <View style={styles.trendHeader}>
            <TrendingUp size={16} stroke={c.primary} />
            <Text style={[styles.infoTitle, { color: c.text }]}>订单概况</Text>
          </View>

          {statusCards.map((s, idx) => {
            const Icon = s.icon;
            return (
              <View
                key={s.label}
                style={[
                  styles.statusRow,
                  idx > 0 && { borderTopColor: c.border, borderTopWidth: 1 },
                ]}
              >
                <View style={styles.statusLeft}>
                  <Icon size={16} stroke={s.color} />
                  <Text style={[styles.infoLabel, { color: c.textSecondary }]}>
                    {s.label}
                  </Text>
                </View>
                <View style={styles.statusRight}>
                  <Text style={[styles.statusCount, { color: c.text }]}>
                    {s.count} 笔
                  </Text>
                  <Text style={[styles.statusAmount, { color: s.color }]}>
                    {formatAmount(s.amount)}
                  </Text>
                </View>
              </View>
            );
          })}

          <View
            style={[styles.totalRow, { borderTopColor: c.border, borderTopWidth: 1 }]}
          >
            <View style={styles.statusLeft}>
              <DollarSign size={16} stroke={c.success} />
              <Text style={[styles.infoLabel, { color: c.textSecondary, fontWeight: '600' }]}>
                金额汇总
              </Text>
            </View>
            <Text style={[styles.totalAmount, { color: c.success }]}>
              {formatAmount(orderSummary.total_amount)}
            </Text>
          </View>
        </Card>

        <Card style={styles.infoCard}>
          <Text style={[styles.infoTitle, { color: c.text }]}>账号概览</Text>
          <View style={styles.infoRow}>
            <Text style={[styles.infoLabel, { color: c.textSecondary }]}>
              账号总数
            </Text>
            <Text style={[styles.infoValue, { color: c.text }]}>
              {stats.total_accounts}
            </Text>
          </View>
          <View
            style={[styles.infoRow, { borderTopColor: c.border, borderTopWidth: 1 }]}
          >
            <Text style={[styles.infoLabel, { color: c.textSecondary }]}>
              启用账号
            </Text>
            <Text style={[styles.infoValue, { color: c.success }]}>
              {stats.active_accounts}
            </Text>
          </View>
          <View
            style={[styles.infoRow, { borderTopColor: c.border, borderTopWidth: 1 }]}
          >
            <Text style={[styles.infoLabel, { color: c.textSecondary }]}>
              停用账号
            </Text>
            <Text style={[styles.infoValue, { color: c.textMuted }]}>
              {Math.max(0, stats.total_accounts - stats.active_accounts)}
            </Text>
          </View>
          <View
            style={[styles.infoRow, { borderTopColor: c.border, borderTopWidth: 1 }]}
          >
            <Text style={[styles.infoLabel, { color: c.textSecondary }]}>
              关键词总数
            </Text>
            <Text style={[styles.infoValue, { color: c.text }]}>
              {stats.total_keywords}
            </Text>
          </View>
          <View
            style={[styles.infoRow, { borderTopColor: c.border, borderTopWidth: 1 }]}
          >
            <Text style={[styles.infoLabel, { color: c.textSecondary }]}>
              昨日回复
            </Text>
            <Text style={[styles.infoValue, { color: c.text }]}>
              {stats.yesterday_reply_count}
            </Text>
          </View>
          <View
            style={[styles.infoRow, { borderTopColor: c.border, borderTopWidth: 1 }]}
          >
            <Text style={[styles.infoLabel, { color: c.textSecondary }]}>
              剩余额度
            </Text>
            <Text style={[styles.infoValue, { color: c.text }]}>
              {stats.remaining_account_count == null
                ? '不限'
                : `${stats.remaining_account_count} / 限 ${stats.account_limit ?? '—'}`}
            </Text>
          </View>
        </Card>

        {/* 订单趋势折线图（横向条形图，支持金额/笔数切换 + 7日/30日切换） */}
        <Card style={styles.trendCard}>
          <View style={[styles.trendHeader, styles.trendHeaderSpace]}>
            <View style={styles.trendHeaderLeft}>
              <TrendingUp size={16} stroke={c.primary} />
              <Text style={[styles.infoTitle, { color: c.text }]}>
                订单趋势
              </Text>
            </View>
            <View style={styles.trendToggles}>
              {/* 金额/笔数切换 */}
              <View
                style={[styles.segControl, { backgroundColor: c.surfaceAlt }]}
              >
                <Pressable
                  onPress={() => setTrendMode('amount')}
                  style={[
                    styles.segBtn,
                    trendMode === 'amount' && {
                      backgroundColor: c.background,
                    },
                  ]}
                >
                  <Text
                    style={[
                      styles.segText,
                      {
                        color: trendMode === 'amount' ? c.primary : c.textMuted,
                        fontWeight: trendMode === 'amount' ? '600' : '400',
                      },
                    ]}
                  >
                    金额
                  </Text>
                </Pressable>
                <Pressable
                  onPress={() => setTrendMode('count')}
                  style={[
                    styles.segBtn,
                    trendMode === 'count' && {
                      backgroundColor: c.background,
                    },
                  ]}
                >
                  <Text
                    style={[
                      styles.segText,
                      {
                        color: trendMode === 'count' ? c.success : c.textMuted,
                        fontWeight: trendMode === 'count' ? '600' : '400',
                      },
                    ]}
                  >
                    笔数
                  </Text>
                </Pressable>
              </View>
              {/* 7日/30日切换 */}
              <View
                style={[styles.segControl, { backgroundColor: c.surfaceAlt }]}
              >
                <Pressable
                  onPress={() => reloadTrend(7)}
                  style={[
                    styles.segBtn,
                    trendDays === 7 && { backgroundColor: c.background },
                  ]}
                >
                  <Text
                    style={[
                      styles.segText,
                      {
                        color: trendDays === 7 ? c.primary : c.textMuted,
                        fontWeight: trendDays === 7 ? '600' : '400',
                      },
                    ]}
                  >
                    7日
                  </Text>
                </Pressable>
                <Pressable
                  onPress={() => reloadTrend(30)}
                  style={[
                    styles.segBtn,
                    trendDays === 30 && { backgroundColor: c.background },
                  ]}
                >
                  <Text
                    style={[
                      styles.segText,
                      {
                        color: trendDays === 30 ? c.primary : c.textMuted,
                        fontWeight: trendDays === 30 ? '600' : '400',
                      },
                    ]}
                  >
                    30日
                  </Text>
                </Pressable>
              </View>
            </View>
          </View>
          {trend.length === 0 ? (
            <Text style={[styles.trendEmpty, { color: c.textMuted }]}>
              暂无订单数据
            </Text>
          ) : (
            <>
              <Text style={[styles.trendSummary, { color: c.textSecondary }]}>
                {trendMode === 'amount'
                  ? `合计 ${formatAmount(trendTotalAmount)} · ${trendTotalCount} 单`
                  : `合计 ${trendTotalCount} 单 · ${formatAmount(trendTotalAmount)}`}
              </Text>
              {trend.map((p, idx) => {
                const val = trendMode === 'amount' ? p.amount : p.count;
                const widthPct = maxVal > 0 ? (val / maxVal) * 100 : 0;
                const barColor = trendMode === 'amount' ? c.primary : c.success;
                return (
                  <View
                    key={`${p.date}-${idx}`}
                    style={[
                      styles.trendRow,
                      trendDays === 30 && styles.trendRowCompact,
                    ]}
                  >
                    <Text
                      style={[
                        trendDays === 30
                          ? styles.trendLabel30
                          : styles.trendLabel,
                        { color: c.textSecondary },
                      ]}
                      numberOfLines={1}
                    >
                      {p.date}
                    </Text>
                    <View
                      style={[
                        styles.trendTrack,
                        { backgroundColor: c.surfaceAlt },
                      ]}
                    >
                      <View
                        style={[
                          styles.trendFill,
                          { width: `${widthPct}%`, backgroundColor: barColor },
                        ]}
                      />
                    </View>
                    <Text
                      style={[
                        trendDays === 30 ? styles.trendValue30 : styles.trendValue,
                        { color: barColor },
                      ]}
                      numberOfLines={1}
                    >
                      {trendMode === 'amount'
                        ? p.amount > 0
                          ? formatAmount(p.amount)
                          : '0'
                        : `${p.count}`}
                    </Text>
                  </View>
                );
              })}
            </>
          )}
        </Card>

        {accounts.length === 0 && (
          <Text style={[styles.hint, { color: c.textMuted }]}>
            暂无账号，请先在账号管理中添加
          </Text>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.md },
  grid: { gap: spacing.md },
  gridRow: { flexDirection: 'row', gap: spacing.md },
  infoCard: { gap: spacing.sm },
  infoTitle: { ...typography.heading },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: spacing.sm,
  },
  infoLabel: { ...typography.body },
  infoValue: { ...typography.body, fontWeight: '600' },
  // 订单概况
  statusRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: spacing.sm,
  },
  statusLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  statusRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  statusCount: { ...typography.body, fontWeight: '600' },
  statusAmount: { ...typography.body, fontWeight: '600' },
  totalRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: spacing.sm,
    marginTop: spacing.xs,
  },
  totalAmount: { ...typography.heading, fontWeight: '700' },
  // 趋势
  trendCard: { gap: spacing.sm },
  trendHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  trendHeaderSpace: {
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: spacing.xs,
  },
  trendHeaderLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  trendToggles: {
    flexDirection: 'row',
    gap: spacing.xs,
  },
  segControl: {
    flexDirection: 'row',
    borderRadius: 8,
    padding: 2,
    gap: 2,
  },
  segBtn: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
  },
  segText: {
    ...typography.small,
    fontSize: 11,
  },
  trendSummary: { ...typography.caption },
  trendRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: 2,
  },
  trendRowCompact: { paddingVertical: 1 },
  trendLabel: { ...typography.small, width: 42 },
  trendLabel30: { ...typography.small, width: 36, fontSize: 9 },
  trendTrack: {
    flex: 1,
    height: 8,
    borderRadius: 4,
    overflow: 'hidden',
  },
  trendFill: { height: '100%', borderRadius: 4 },
  trendValue: { ...typography.small, width: 110, textAlign: 'right' },
  trendValue30: { ...typography.small, width: 70, textAlign: 'right', fontSize: 9 },
  trendEmpty: { ...typography.caption },
  hint: { ...typography.caption, textAlign: 'center', paddingVertical: spacing.md },
});
