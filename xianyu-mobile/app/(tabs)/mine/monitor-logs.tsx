import { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  ScrollView,
  Alert,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { usePagedList } from '@/hooks/usePagedList';
import {
  getMonitorLogs,
  getMonitorTaskOptions,
  clearMonitorLogs,
  isEndpointMissing,
  type MonitorLog,
  type MonitorTaskOption,
} from '@/api/wrappers/monitor';

const PAGE_SIZE = 20;

/** 状态筛选项（value 与后端 status 枚举一致） */
const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: '', label: '全部状态' },
  { value: 'success', label: '成功' },
  { value: 'partial', label: '部分成功' },
  { value: 'failed', label: '失败' },
];

/** 监控类型 → 展示文案（与 listing-monitor 页一致） */
function monitorTypeLabel(type: string): string {
  return type === 'price_drop' ? '降价' : '上新';
}

/** 触发方式 → 展示文案，未知值原样展示 */
function triggerLabel(trigger: string): string {
  if (trigger === 'manual') return '手动';
  if (trigger === 'scheduled' || trigger === 'cron') return '定时';
  return trigger;
}

/** 日志状态 → 徽标配色 */
function statusStyle(status: string, c: (typeof colors)['light']) {
  if (status === 'success') return { bg: c.success, fg: '#FFFFFF', label: '成功' };
  if (status === 'partial') return { bg: c.warning, fg: '#FFFFFF', label: '部分成功' };
  if (status === 'failed') return { bg: c.error, fg: '#FFFFFF', label: '失败' };
  return { bg: c.border, fg: c.textSecondary, label: status || '未知' };
}

/** ISO 时间 → 可读字符串，无法解析时原样返回 */
function formatDate(iso?: string): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(
    d.getMinutes(),
  )}`;
}

export default function MonitorLogsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  // 筛选条件：按任务 / 按状态；变化后由 effect 触发重新加载
  const [taskFilter, setTaskFilter] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [taskOptions, setTaskOptions] = useState<MonitorTaskOption[]>([]);
  const [clearing, setClearing] = useState(false);

  const list = usePagedList<MonitorLog>({
    mode: 'page',
    pageSize: PAGE_SIZE,
    auto: false, // 由筛选 effect 统一触发首次加载
    dedupeBy: (l) => l.id,
    fetchPage: async ({ page = 1 }) => {
      const resp = await getMonitorLogs({
        page,
        pageSize: PAGE_SIZE,
        monitorTaskId: taskFilter ?? undefined,
        status: statusFilter || undefined,
      });
      return { items: resp.list, total: resp.total };
    },
    onError: (e, phase) => {
      if (phase !== 'refresh') return;
      if (isEndpointMissing(e)) {
        Alert.alert('功能不可用', '监控日志需要后端新版支持，请升级后端服务');
      } else {
        Alert.alert('加载失败', e.message);
      }
    },
  });

  // 挂载与筛选变化时回到第一页重新加载（effect 在渲染后执行，fetchPage 闭包取到最新筛选）
  useEffect(() => {
    list.refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [taskFilter, statusFilter]);

  useEffect(() => {
    getMonitorTaskOptions()
      .then(setTaskOptions)
      .catch(() => {
        // 任务选项加载失败不阻塞日志列表，仅无法按任务筛选
      });
  }, []);

  const handleClear = useCallback(() => {
    Alert.alert(
      '清空日志',
      '仅清空 10 天前的监控日志，确定继续吗？',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '清空',
          style: 'destructive',
          onPress: () => {
            setClearing(true);
            clearMonitorLogs()
              .then((count) => {
                Alert.alert('成功', `已清空 ${count} 条 10 天前的监控日志`);
                return list.refresh();
              })
              .catch((e: unknown) =>
                Alert.alert('清空失败', (e as Error).message),
              )
              .finally(() => setClearing(false));
          },
        },
      ],
    );
  }, [list]);

  const taskKeyword = useCallback(
    (taskId: number | null): string => {
      if (taskId == null) return '';
      return (
        taskOptions.find((t) => t.id === taskId)?.keyword ||
        `任务 #${taskId}`
      );
    },
    [taskOptions],
  );

  if (list.loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载监控日志..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <Button
          label="清空日志"
          onPress={handleClear}
          variant="danger"
          loading={clearing}
          disabled={clearing}
        />
      </View>

      {/* 任务筛选（横向 chips） */}
      <View style={styles.filterSection}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={styles.chipRow}>
            <Pressable
              onPress={() => setTaskFilter(null)}
              style={[
                styles.chip,
                {
                  borderColor: taskFilter == null ? c.primary : c.border,
                  backgroundColor: taskFilter == null ? c.primary : 'transparent',
                },
              ]}
            >
              <Text
                style={[
                  styles.chipText,
                  { color: taskFilter == null ? '#FFF' : c.text },
                ]}
              >
                全部任务
              </Text>
            </Pressable>
            {taskOptions.map((t) => {
              const selected = taskFilter === t.id;
              return (
                <Pressable
                  key={t.id}
                  onPress={() => setTaskFilter(t.id)}
                  style={[
                    styles.chip,
                    {
                      borderColor: selected ? c.primary : c.border,
                      backgroundColor: selected ? c.primary : 'transparent',
                    },
                  ]}
                >
                  <Text
                    style={[
                      styles.chipText,
                      { color: selected ? '#FFF' : c.text },
                    ]}
                    numberOfLines={1}
                  >
                    {t.keyword || `任务 #${t.id}`}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </ScrollView>

        {/* 状态筛选 */}
        <ScrollView horizontal showsHorizontalScrollIndicator={false}>
          <View style={styles.chipRow}>
            {STATUS_FILTERS.map((f) => {
              const selected = statusFilter === f.value;
              return (
                <Pressable
                  key={f.value}
                  onPress={() => setStatusFilter(f.value)}
                  style={[
                    styles.chip,
                    {
                      borderColor: selected ? c.primary : c.border,
                      backgroundColor: selected ? c.primary : 'transparent',
                    },
                  ]}
                >
                  <Text
                    style={[
                      styles.chipText,
                      { color: selected ? '#FFF' : c.text },
                    ]}
                  >
                    {f.label}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </ScrollView>
      </View>

      <FlatList
        data={list.items}
        keyExtractor={(item) => String(item.id)}
        refreshControl={
          <RefreshControl refreshing={list.refreshing} onRefresh={list.refresh} />
        }
        onEndReached={list.loadMore}
        onEndReachedThreshold={0.3}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: c.textMuted }]}>暂无监控日志</Text>
          </View>
        }
        ListFooterComponent={
          list.loadingMore ? (
            <Text style={[styles.loadingMore, { color: c.textMuted }]}>加载中...</Text>
          ) : null
        }
        renderItem={({ item }) => {
          const badge = statusStyle(item.status, c);
          return (
            <Card style={styles.card}>
              <View style={styles.cardHeader}>
                <View style={styles.badgeRow}>
                  <View style={[styles.statusBadge, { backgroundColor: badge.bg }]}>
                    <Text style={[styles.statusText, { color: badge.fg }]}>
                      {badge.label}
                    </Text>
                  </View>
                  <View style={[styles.typeBadge, { backgroundColor: c.primaryLight }]}>
                    <Text style={[styles.typeText, { color: c.primary }]}>
                      {monitorTypeLabel(item.monitor_type)}
                    </Text>
                  </View>
                  {item.trigger_type ? (
                    <Text style={[styles.trigger, { color: c.textMuted }]}>
                      {triggerLabel(item.trigger_type)}
                    </Text>
                  ) : null}
                </View>
                <Text style={[styles.time, { color: c.textMuted }]}>
                  {formatDate(item.created_at)}
                </Text>
              </View>

              <Text style={[styles.keyword, { color: c.text }]} numberOfLines={1}>
                {item.keyword || taskKeyword(item.monitor_task_id) || '未知任务'}
              </Text>

              <Text style={[styles.meta, { color: c.textMuted }]}>
                采集 {item.fetched_count} · 新增 {item.inserted_count} · 更新{' '}
                {item.updated_count}
                {item.pages > 0 ? ` · ${item.pages} 页` : ''}
              </Text>

              {item.message ? (
                <Text style={[styles.message, { color: c.textSecondary }]} numberOfLines={2}>
                  {item.message}
                </Text>
              ) : null}
            </Card>
          );
        }}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  filterSection: { gap: spacing.sm, paddingBottom: spacing.sm },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'nowrap',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
  },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    borderWidth: 1,
    maxWidth: 160,
  },
  chipText: { ...typography.small },
  list: { padding: spacing.lg, paddingTop: spacing.sm, gap: spacing.md },
  card: { gap: spacing.xs },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  badgeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flexShrink: 1 },
  statusBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  statusText: { ...typography.micro },
  typeBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  typeText: { ...typography.micro, fontWeight: '600' },
  trigger: { ...typography.small },
  time: { ...typography.small },
  keyword: { ...typography.body, fontWeight: '600', marginTop: spacing.xs },
  meta: { ...typography.small },
  message: { ...typography.small, marginTop: 2 },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  loadingMore: { textAlign: 'center', padding: spacing.md },
});
