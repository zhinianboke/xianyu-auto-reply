import { useState, useCallback, useEffect } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, RefreshControl, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getCrawlerJobs,
  getCrawlerItems,
  startCrawler,
  stopCrawler,
  type CrawlerJob,
  type CrawlerItem,
} from '@/api/wrappers/distribution';

/** 运行中状态：可停止、不可再次启动 */
function isRunning(status: string): boolean {
  const s = status.toLowerCase();
  return ['running', 'active', 'started', 'ongoing', 'processing'].some((k) =>
    s.includes(k),
  );
}

/** 由状态文案派生标签颜色 */
function statusColor(status: string, c: { success: string; warning: string; error: string; textMuted: string }): string {
  const s = status.toLowerCase();
  if (['fail', 'error', 'stopped', 'cancel', 'timeout'].some((k) => s.includes(k)))
    return c.error;
  if (isRunning(status)) return c.success;
  if (['pending', 'waiting', 'queued'].some((k) => s.includes(k))) return c.warning;
  return c.textMuted;
}

export default function CrawlerScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [jobs, setJobs] = useState<CrawlerJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [itemsMap, setItemsMap] = useState<Record<number, CrawlerItem[]>>({});
  const [itemsLoading, setItemsLoading] = useState<Record<number, boolean>>({});
  const [actionLoading, setActionLoading] = useState<Record<number, boolean>>({});

  const loadJobs = useCallback(async () => {
    setRefreshing(true);
    try {
      setJobs(await getCrawlerJobs());
    } catch (e) {
      Alert.alert('加载失败', (e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadJobs();
  }, [loadJobs]);

  const toggleExpand = useCallback(
    async (job: CrawlerJob) => {
      if (expandedId === job.id) {
        setExpandedId(null);
        return;
      }
      setExpandedId(job.id);
      // 首次展开时拉取商品列表，已缓存则直接复用
      if (itemsMap[job.id]) return;
      setItemsLoading((prev) => ({ ...prev, [job.id]: true }));
      try {
        const items = await getCrawlerItems(job.id);
        setItemsMap((prev) => ({ ...prev, [job.id]: items }));
      } catch (e) {
        Alert.alert('加载商品失败', (e as Error).message);
      } finally {
        setItemsLoading((prev) => ({ ...prev, [job.id]: false }));
      }
    },
    [expandedId, itemsMap],
  );

  const handleStart = useCallback(
    async (jobId: number) => {
      setActionLoading((prev) => ({ ...prev, [jobId]: true }));
      try {
        await startCrawler(jobId);
        await loadJobs();
      } catch (e) {
        Alert.alert('启动失败', (e as Error).message);
      } finally {
        setActionLoading((prev) => ({ ...prev, [jobId]: false }));
      }
    },
    [loadJobs],
  );

  const handleStop = useCallback(
    async (jobId: number) => {
      setActionLoading((prev) => ({ ...prev, [jobId]: true }));
      try {
        await stopCrawler(jobId);
        await loadJobs();
      } catch (e) {
        Alert.alert('停止失败', (e as Error).message);
      } finally {
        setActionLoading((prev) => ({ ...prev, [jobId]: false }));
      }
    },
    [loadJobs],
  );

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载爬虫任务..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <FlatList
        data={jobs}
        keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadJobs} />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: c.textMuted }]}>暂无爬虫任务</Text>
          </View>
        }
        renderItem={({ item }) => {
          const expanded = expandedId === item.id;
          const running = isRunning(item.status);
          const items = itemsMap[item.id];
          const busy = !!actionLoading[item.id];
          return (
            <Card style={styles.card}>
              <Pressable
                onPress={() => toggleExpand(item)}
                style={styles.jobHeader}
              >
                <View style={styles.jobInfo}>
                  <Text style={[styles.jobName, { color: c.text }]} numberOfLines={1}>
                    {item.name}
                  </Text>
                  <View style={styles.jobMeta}>
                    <View
                      style={[styles.badge, { backgroundColor: statusColor(item.status, c) }]}
                    >
                      <Text style={styles.badgeText}>{item.status}</Text>
                    </View>
                    {item.items_count != null && (
                      <Text style={[styles.count, { color: c.textMuted }]}>
                        {item.items_count} 件商品
                      </Text>
                    )}
                  </View>
                </View>
                <Text style={[styles.chevron, { color: c.textMuted }]}>
                  {expanded ? '▲' : '▼'}
                </Text>
              </Pressable>

              <View style={styles.jobActions}>
                <Button
                  label="启动"
                  variant={running ? 'ghost' : 'primary'}
                  onPress={() => handleStart(item.id)}
                  loading={busy}
                  disabled={running || busy}
                  style={styles.actionBtn}
                />
                <Button
                  label="停止"
                  variant="danger"
                  onPress={() => handleStop(item.id)}
                  loading={busy}
                  disabled={!running || busy}
                  style={styles.actionBtn}
                />
              </View>

              {expanded && (
                <View
                  style={[styles.itemsWrap, { borderTopColor: c.border, borderTopWidth: 1 }]}
                >
                  {itemsLoading[item.id] ? (
                    <Text style={[styles.hint, { color: c.textMuted }]}>
                      加载商品中...
                    </Text>
                  ) : items && items.length > 0 ? (
                    items.map((it) => (
                      <View
                        key={it.item_id}
                        style={[styles.itemRow, { borderBottomColor: c.border }]}
                      >
                        <Text
                          style={[styles.itemTitle, { color: c.text }]}
                          numberOfLines={1}
                        >
                          {it.title}
                        </Text>
                        <Text style={[styles.itemPrice, { color: c.primary }]}>
                          ¥{it.price}
                        </Text>
                      </View>
                    ))
                  ) : (
                    <Text style={[styles.hint, { color: c.textMuted }]}>暂无商品</Text>
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
  list: { padding: spacing.lg, gap: spacing.md },
  card: { gap: spacing.sm },
  jobHeader: { flexDirection: 'row', alignItems: 'center' },
  jobInfo: { flex: 1, marginRight: spacing.sm, gap: spacing.xs },
  jobName: { ...typography.body, fontWeight: '600' },
  jobMeta: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  badge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.sm },
  badgeText: { ...typography.small, fontWeight: '600', color: '#FFF' },
  count: { ...typography.small },
  chevron: { fontSize: 12, fontWeight: '600' },
  jobActions: { flexDirection: 'row', gap: spacing.sm },
  actionBtn: { flex: 1, minHeight: 40 },
  itemsWrap: { paddingTop: spacing.sm, marginTop: spacing.xs, gap: 0 },
  itemRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  itemTitle: { ...typography.caption, flex: 1, marginRight: spacing.sm },
  itemPrice: { ...typography.caption, fontWeight: '600' },
  hint: { ...typography.small, paddingVertical: spacing.sm },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
});
