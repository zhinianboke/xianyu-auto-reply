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
  ListTodo,
} from 'lucide-react-native';
import { Card, StatCard, Loading } from '@/components/ui';
import { colors, spacing, typography } from '@/lib/theme';
import { getBrowseSummary, type DashboardStats } from '@/api/wrappers/dashboard';
import { useAccountsStore } from '@/stores/accounts';

/** YYYY-MM-DD 格式化 */
function formatDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** 从统计结果中按候选字段名提取数字，缺失时返回 undefined */
function maybeNumber(
  obj: Record<string, unknown>,
  keys: string[],
): number | undefined {
  for (const k of keys) {
    if (k in obj && obj[k] != null && obj[k] !== '') {
      const n = Number(obj[k]);
      if (Number.isFinite(n)) return n;
    }
  }
  return undefined;
}

export default function DashboardScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();

  const accounts = useAccountsStore((s) => s.options);
  const loadAccounts = useAccountsStore((s) => s.load);
  const [stats, setStats] = useState<DashboardStats>({
    total_accounts: 0,
    active_accounts: 0,
    today_replies: 0,
    total_orders: 0,
  });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // force=true 用于下拉刷新绕过 60s TTL
  const load = useCallback(async (force = false) => {
    setRefreshing(true);
    try {
      await loadAccounts(force);
      const accs = useAccountsStore.getState().options;

      // 用今天日期范围调用浏览概要；接口需要账号，取第一个账号的 pk
      if (accs.length > 0) {
        const today = formatDate(new Date());
        const result = await getBrowseSummary(String(accs[0].pk), today, today);
        const totalAccounts =
          maybeNumber(result, ['total_accounts', 'account_count', 'accounts']) ??
          accs.length;
        const activeAccounts =
          maybeNumber(result, ['active_accounts', 'active_count']) ??
          accs.filter((a) => a.enabled).length;
        const todayReplies =
          maybeNumber(result, [
            'today_replies',
            'today_reply_count',
            'replies',
          ]) ?? 0;
        const totalOrders =
          maybeNumber(result, ['total_orders', 'orders', 'order_count']) ?? 0;
        setStats({
          total_accounts: totalAccounts,
          active_accounts: activeAccounts,
          today_replies: todayReplies,
          total_orders: totalOrders,
        });
      } else {
        setStats({
          total_accounts: 0,
          active_accounts: 0,
          today_replies: 0,
          total_orders: 0,
        });
      }
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
  // 近7日趋势暂无数据源，该位按约定回退为"账号总数"。
  const statCards: {
    label: string;
    value: number;
    icon: typeof MessageCircle;
    accent: string;
    onPress: () => void;
  }[] = [
    {
      label: '今日回复',
      value: stats.today_replies,
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
      label: '在线账号',
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
              {accounts.length}
            </Text>
          </View>
          <View
            style={[styles.infoRow, { borderTopColor: c.border, borderTopWidth: 1 }]}
          >
            <Text style={[styles.infoLabel, { color: c.textSecondary }]}>
              启用账号
            </Text>
            <Text style={[styles.infoValue, { color: c.success }]}>
              {accounts.filter((a) => a.enabled).length}
            </Text>
          </View>
          <View
            style={[styles.infoRow, { borderTopColor: c.border, borderTopWidth: 1 }]}
          >
            <Text style={[styles.infoLabel, { color: c.textSecondary }]}>
              停用账号
            </Text>
            <Text style={[styles.infoValue, { color: c.textMuted }]}>
              {accounts.filter((a) => !a.enabled).length}
            </Text>
          </View>
        </Card>

        <Card style={styles.todoCard}>
          <View style={styles.todoHeader}>
            <ListTodo size={16} stroke={c.primary} />
            <Text style={[styles.todoTitle, { color: c.text }]}>今日待办</Text>
          </View>
          <Text style={[styles.todoEmpty, { color: c.textMuted }]}>
            暂无待办事项
          </Text>
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
  todoCard: { gap: spacing.sm },
  todoHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  todoTitle: { ...typography.heading },
  todoEmpty: { ...typography.caption },
  hint: { ...typography.caption, textAlign: 'center', paddingVertical: spacing.md },
});
