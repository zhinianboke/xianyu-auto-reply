import { useState, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, RefreshControl, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { useRouter } from 'expo-router';
import {
  MessageCircle,
  ShoppingBag,
  Wifi,
  Users,
  TrendingUp,
} from 'lucide-react-native';
import { Card, StatCard, Loading } from '@/components/ui';
import { colors, spacing, typography } from '@/lib/theme';
import {
  getCookieStats,
  getOrderTrend,
  type CookieStats,
  type OrderTrendPoint,
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

/** 金额展示：0 显示 0，保留两位小数 */
function formatAmount(n: number): string {
  return `¥${n.toFixed(2)}`;
}

export default function DashboardScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();

  const accounts = useAccountsStore((s) => s.options);
  const loadAccounts = useAccountsStore((s) => s.load);
  // 真实数据源：GET /api/v1/cookies/stats + /api/v1/cookies/stats/order-trend
  const [stats, setStats] = useState<CookieStats>(EMPTY_STATS);
  const [trend, setTrend] = useState<OrderTrendPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // force=true 用于下拉刷新绕过 60s TTL
  const load = useCallback(async (force = false) => {
    setRefreshing(true);
    try {
      await loadAccounts(force);
      // 趋势失败不阻断统计卡展示
      const [statsRes, trendRes] = await Promise.all([
        getCookieStats(),
        getOrderTrend(7).catch(() => [] as OrderTrendPoint[]),
      ]);
      setStats(statsRes);
      setTrend(trendRes);
    } catch (e) {
      console.error('加载仪表盘失败', e);
      Alert.alert('加载失败', (e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [loadAccounts]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
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

  // 近7日趋势条形图（横向，参考 data-analysis 分布条画法）
  const maxAmount = trend.reduce((m, p) => Math.max(m, p.amount), 0);
  const trendTotalCount = trend.reduce((sum, p) => sum + p.count, 0);
  const trendTotalAmount = trend.reduce((sum, p) => sum + p.amount, 0);

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
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

        {/* 近7日订单趋势（真实数据源 order-trend；无数据源支撑的"今日待办"卡已移除） */}
        <Card style={styles.trendCard}>
          <View style={styles.trendHeader}>
            <TrendingUp size={16} stroke={c.primary} />
            <Text style={[styles.infoTitle, { color: c.text }]}>近7日订单</Text>
          </View>
          {trend.length === 0 ? (
            <Text style={[styles.trendEmpty, { color: c.textMuted }]}>
              暂无订单数据
            </Text>
          ) : (
            <>
              <Text style={[styles.trendSummary, { color: c.textSecondary }]}>
                合计 {trendTotalCount} 单 · {formatAmount(trendTotalAmount)}
              </Text>
              {trend.map((p, idx) => {
                const widthPct =
                  maxAmount > 0 ? (p.amount / maxAmount) * 100 : 0;
                return (
                  <View key={`${p.date}-${idx}`} style={styles.trendRow}>
                    <Text
                      style={[styles.trendLabel, { color: c.textSecondary }]}
                      numberOfLines={1}
                    >
                      {p.date}
                    </Text>
                    <View
                      style={[styles.trendTrack, { backgroundColor: c.surfaceAlt }]}
                    >
                      <View
                        style={[
                          styles.trendFill,
                          { width: `${widthPct}%`, backgroundColor: c.primary },
                        ]}
                      />
                    </View>
                    <Text
                      style={[styles.trendValue, { color: c.primary }]}
                      numberOfLines={1}
                    >
                      {p.amount > 0 ? formatAmount(p.amount) : '0'} · {p.count}单
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
  // 近7日订单趋势
  trendCard: { gap: spacing.sm },
  trendHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  trendSummary: { ...typography.caption },
  trendRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  trendLabel: { ...typography.small, width: 42 },
  trendTrack: {
    flex: 1,
    height: 8,
    borderRadius: 4,
    overflow: 'hidden',
  },
  trendFill: { height: '100%', borderRadius: 4 },
  trendValue: { ...typography.small, width: 110, textAlign: 'right' },
  trendEmpty: { ...typography.caption },
  hint: { ...typography.caption, textAlign: 'center', paddingVertical: spacing.md },
});
