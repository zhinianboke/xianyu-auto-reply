import { useState, useCallback, useEffect, useLayoutEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  RefreshControl,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { useNavigation, useRouter } from 'expo-router';
import { Card, Button, Badge, EmptyState, Loading, FilterTabs } from '@/components/ui';
import { History } from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { usePagedList } from '@/hooks/usePagedList';
import {
  getAiListingTasks,
  getAiListingTask,
  type AiListingTask,
  type AiListingTaskDetail,
} from '@/api/wrappers/ai-listing';

const PAGE_SIZE = 10;

type BadgeVariant = 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'gray';

const STATUS_TABS = [
  { key: '', label: '全部' },
  { key: 'running', label: '进行中' },
  { key: 'success', label: '成功' },
  { key: 'partial', label: '部分成功' },
  { key: 'failed', label: '失败' },
  { key: 'canceled', label: '取消' },
];

/** 任务状态 → Badge 配色 + 文案 */
function taskBadge(status: AiListingTask['status']): { variant: BadgeVariant; label: string } {
  switch (status) {
    case 'running':
      return { variant: 'info', label: '进行中' };
    case 'success':
      return { variant: 'success', label: '成功' };
    case 'partial':
      return { variant: 'warning', label: '部分成功' };
    case 'failed':
      return { variant: 'danger', label: '失败' };
    case 'canceled':
      return { variant: 'gray', label: '已取消' };
    default:
      return { variant: 'gray', label: '待开始' };
  }
}

/** ISO 时间 → 可读字符串，无法解析时原样返回 */
function formatDate(iso?: string | null): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

export default function AiListingHistoryScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();
  const navigation = useNavigation();

  useLayoutEffect(() => {
    navigation.setOptions({ title: '历史任务' });
  }, [navigation]);

  const [statusFilter, setStatusFilter] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [detailMap, setDetailMap] = useState<Record<string, AiListingTaskDetail>>({});
  const [detailLoading, setDetailLoading] = useState<Record<string, boolean>>({});

  const list = usePagedList<AiListingTask>({
    mode: 'page',
    pageSize: PAGE_SIZE,
    auto: false, // 由筛选 effect 统一触发首次加载
    dedupeBy: (t) => t.task_id,
    fetchPage: async ({ page = 1 }) => {
      const resp = await getAiListingTasks(page, PAGE_SIZE, statusFilter || undefined);
      return { items: resp.list, total: resp.total };
    },
    onError: (e, phase) => {
      if (phase === 'refresh') Alert.alert('加载失败', e.message);
    },
  });

  // 挂载与筛选变化时回到第一页重新加载（effect 在渲染后执行，fetchPage 闭包取到最新筛选）
  useEffect(() => {
    list.refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [statusFilter]);

  const handleChangeFilter = useCallback((key: string) => {
    setExpandedId(null);
    setStatusFilter(key);
  }, []);

  const toggleExpand = useCallback(
    async (task: AiListingTask) => {
      const id = task.task_id;
      if (expandedId === id) {
        setExpandedId(null);
        return;
      }
      setExpandedId(id);
      // 首次展开时拉取任务明细，已缓存则直接复用
      if (detailMap[id]) return;
      setDetailLoading((prev) => ({ ...prev, [id]: true }));
      try {
        const detail = await getAiListingTask(id);
        setDetailMap((prev) => ({ ...prev, [id]: detail }));
      } catch (e) {
        Alert.alert('加载明细失败', (e as Error).message);
      } finally {
        setDetailLoading((prev) => ({ ...prev, [id]: false }));
      }
    },
    [expandedId, detailMap],
  );

  if (list.loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载历史任务..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.topBar}>
        <Button
          label="新建任务"
          variant="ghost"
          onPress={() => router.push('/(tabs)/mine/ai-listing')}
          style={styles.newBtn}
        />
      </View>

      <FilterTabs tabs={STATUS_TABS} active={statusFilter} onChange={handleChangeFilter} />

      <FlatList
        data={list.items}
        keyExtractor={(item) => item.task_id}
        refreshControl={<RefreshControl refreshing={list.refreshing} onRefresh={list.refresh} />}
        onEndReached={list.loadMore}
        onEndReachedThreshold={0.3}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <EmptyState icon={History} title="暂无历史任务" message="生成上架任务后，记录会展示在这里" />
        }
        ListFooterComponent={
          list.loadingMore ? (
            <Text style={[styles.loadingMore, { color: c.textMuted }]}>加载中...</Text>
          ) : null
        }
        renderItem={({ item }) => {
          const expanded = expandedId === item.task_id;
          const detail = detailMap[item.task_id];
          const badge = taskBadge(item.status);
          const failedItems = detail?.items.filter((it) => it.status === 'failed') ?? [];
          return (
            <Card style={styles.card}>
              <Pressable onPress={() => toggleExpand(item)} style={styles.cardHeader}>
                <Text style={[styles.keyword, { color: c.text }]} numberOfLines={1}>
                  {item.keyword}
                </Text>
                <Badge label={badge.label} variant={badge.variant} />
              </Pressable>

              <Text style={[styles.meta, { color: c.textSecondary }]} numberOfLines={1}>
                {item.config_name || `配置 #${item.config_id}`} · 成功 {item.success} · 失败 {item.failed} · 共 {item.total}
              </Text>

              <Text style={[styles.time, { color: c.textMuted }]}>
                {formatDate(item.finished_at || item.started_at || item.created_at)}
              </Text>

              {expanded ? (
                <View style={[styles.detailWrap, { borderTopColor: c.border, borderTopWidth: 1 }]}>
                  {detailLoading[item.task_id] ? (
                    <Text style={[styles.hint, { color: c.textMuted }]}>加载明细中...</Text>
                  ) : failedItems.length > 0 ? (
                    failedItems.map((it) => (
                      <View key={it.seq} style={[styles.failedRow, { borderBottomColor: c.borderLight }]}>
                        <Text style={[styles.failedTitle, { color: c.textSecondary }]} numberOfLines={1}>
                          #{it.seq} {it.title}
                        </Text>
                        <Text style={[styles.failedMsg, { color: c.error }]} numberOfLines={2}>
                          {it.error_message}
                        </Text>
                      </View>
                    ))
                  ) : (
                    <Text style={[styles.hint, { color: c.textMuted }]}>无失败明细</Text>
                  )}
                </View>
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
  topBar: { flexDirection: 'row', justifyContent: 'flex-end', paddingHorizontal: spacing.lg, paddingVertical: spacing.sm },
  newBtn: { minHeight: 36, paddingHorizontal: spacing.md, alignSelf: 'flex-end' },
  list: { padding: spacing.lg, paddingTop: spacing.sm, gap: spacing.md },
  card: { gap: spacing.xs },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.sm },
  keyword: { ...typography.body, fontWeight: '600', flexShrink: 1 },
  meta: { ...typography.small },
  time: { ...typography.small },
  detailWrap: { marginTop: spacing.sm, gap: 0 },
  failedRow: {
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: 2,
  },
  failedTitle: { ...typography.small },
  failedMsg: { ...typography.small },
  hint: { ...typography.small, paddingVertical: spacing.sm },
  loadingMore: { textAlign: 'center', padding: spacing.md },
});
