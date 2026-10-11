import { useState, useCallback, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  RefreshControl,
  Alert,
  Switch,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Plus } from 'lucide-react-native';
import { Card, Button, Input, Loading, EmptyState, FormModal } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { getAccountOptions, type AccountOption } from '@/api/wrappers/accounts';
import {
  getCrawlerJobs,
  getCrawlerJobItems,
  createCrawlerJob,
  deleteCrawlerJob,
  startCrawlerJob,
  stopCrawlerJob,
  runCrawlerJobOnce,
  type CrawlerJob,
  type CrawlerItem,
} from '@/api/wrappers/crawler';

/** ISO/字符串时间 → 简洁可读形式，失败则原样返回 */
function formatTime(raw: string | null): string {
  if (!raw) return '';
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 数值输入兜底：非法输入回退默认值并夹紧范围 */
function clampInt(raw: string, fallback: number, min: number, max: number): number {
  const n = Number(raw);
  if (!Number.isFinite(n)) return fallback;
  return Math.min(max, Math.max(min, Math.round(n)));
}

const FORM_DEFAULTS = {
  keyword: '',
  intervalSeconds: '900',
  startPage: '1',
  pages: '1',
  pageSize: '20',
  detailLimit: '20',
  fetchDetail: true,
  enabled: true,
};

export default function CrawlerScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [jobs, setJobs] = useState<CrawlerJob[]>([]);
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [itemsMap, setItemsMap] = useState<Record<number, CrawlerItem[]>>({});
  const [itemsLoading, setItemsLoading] = useState<Record<number, boolean>>({});
  /** 启停/删除/立即执行的按任务加载态 */
  const [actionLoading, setActionLoading] = useState<Record<number, boolean>>({});

  // 新建任务表单
  const [formVisible, setFormVisible] = useState(false);
  const [cookieId, setCookieId] = useState('');
  const [keyword, setKeyword] = useState(FORM_DEFAULTS.keyword);
  const [intervalSeconds, setIntervalSeconds] = useState(FORM_DEFAULTS.intervalSeconds);
  const [startPage, setStartPage] = useState(FORM_DEFAULTS.startPage);
  const [pages, setPages] = useState(FORM_DEFAULTS.pages);
  const [pageSize, setPageSize] = useState(FORM_DEFAULTS.pageSize);
  const [detailLimit, setDetailLimit] = useState(FORM_DEFAULTS.detailLimit);
  const [fetchDetail, setFetchDetail] = useState(FORM_DEFAULTS.fetchDetail);
  const [enabled, setEnabled] = useState(FORM_DEFAULTS.enabled);
  const [creating, setCreating] = useState(false);
  const loadedAccounts = useRef(false);

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

  const loadAccounts = useCallback(async (force = false) => {
    if (loadedAccounts.current && !force) return;
    try {
      const list = await getAccountOptions();
      setAccounts(list);
      loadedAccounts.current = true;
    } catch {
      // 账号列表加载失败不阻塞任务列表，创建时再校验
    }
  }, []);

  useEffect(() => {
    loadJobs();
    loadAccounts();
  }, [loadJobs, loadAccounts]);

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
        const items = await getCrawlerJobItems(job.id);
        setItemsMap((prev) => ({ ...prev, [job.id]: items }));
      } catch (e) {
        Alert.alert('加载商品失败', (e as Error).message);
      } finally {
        setItemsLoading((prev) => ({ ...prev, [job.id]: false }));
      }
    },
    [expandedId, itemsMap],
  );

  const withAction = useCallback(
    async (jobId: number, fn: () => Promise<void>) => {
      setActionLoading((prev) => ({ ...prev, [jobId]: true }));
      try {
        await fn();
      } finally {
        setActionLoading((prev) => ({ ...prev, [jobId]: false }));
      }
    },
    [],
  );

  const handleStart = useCallback(
    (jobId: number) =>
      withAction(jobId, async () => {
        try {
          await startCrawlerJob(jobId);
          await loadJobs();
        } catch (e) {
          Alert.alert('启动失败', (e as Error).message);
        }
      }),
    [withAction, loadJobs],
  );

  const handleStop = useCallback(
    (jobId: number) =>
      withAction(jobId, async () => {
        try {
          await stopCrawlerJob(jobId);
          await loadJobs();
        } catch (e) {
          Alert.alert('停止失败', (e as Error).message);
        }
      }),
    [withAction, loadJobs],
  );

  /** 立即执行一次：后端同步采集，可能耗时较长 */
  const handleRunOnce = useCallback(
    (job: CrawlerJob) =>
      withAction(job.id, async () => {
        try {
          const res = await runCrawlerJobOnce(job.id);
          if (res.success) {
            Alert.alert('执行完成', `写入 ${res.upserted} 条（共抓到 ${res.total} 条）`);
          } else {
            Alert.alert('执行失败', res.error || '采集服务返回失败');
          }
          setItemsMap((prev) => {
            const next = { ...prev };
            delete next[job.id]; // 重新展开时拉取最新结果
            return next;
          });
          await loadJobs();
        } catch (e) {
          Alert.alert('执行失败', (e as Error).message);
        }
      }),
    [withAction, loadJobs],
  );

  const confirmDeleteJob = useCallback(
    (job: CrawlerJob) => {
      Alert.alert(
        '确认删除',
        `删除任务「${job.keyword}」（#${job.id}）？采集到的 ${job.item_count} 件商品记录将一并删除，不可恢复。`,
        [
          { text: '取消', style: 'cancel' },
          {
            text: '删除',
            style: 'destructive',
            onPress: () =>
              withAction(job.id, async () => {
                try {
                  await deleteCrawlerJob(job.id);
                  if (expandedId === job.id) setExpandedId(null);
                  await loadJobs();
                } catch (e) {
                  Alert.alert('删除失败', (e as Error).message);
                }
              }),
          },
        ],
      );
    },
    [withAction, loadJobs, expandedId],
  );

  /** 长按菜单：删除/立即执行入口 */
  function handleLongPress(job: CrawlerJob) {
    Alert.alert(`任务 #${job.id}`, `关键词：${job.keyword}\n账号：${job.cookie_id}`, [
      { text: '立即执行一次', onPress: () => handleRunOnce(job) },
      { text: '删除任务', style: 'destructive', onPress: () => confirmDeleteJob(job) },
      { text: '取消', style: 'cancel' },
    ]);
  }

  function openCreate() {
    loadAccounts();
    if (!cookieId && accounts.length > 0) setCookieId(accounts[0].id);
    setFormVisible(true);
  }

  async function handleCreate() {
    const kw = keyword.trim();
    if (!cookieId) { Alert.alert('提示', '请先选择采集账号'); return; }
    if (!kw) { Alert.alert('提示', '请填写搜索关键词'); return; }
    const interval = clampInt(intervalSeconds, 900, 60, 86400);
    if (Number(intervalSeconds) < 60) { Alert.alert('提示', '执行间隔至少 60 秒'); return; }
    setCreating(true);
    try {
      const jobId = await createCrawlerJob({
        cookie_id: cookieId,
        keyword: kw,
        interval_seconds: interval,
        start_page: clampInt(startPage, 1, 1, 50),
        pages: clampInt(pages, 1, 1, 10),
        page_size: clampInt(pageSize, 20, 1, 50),
        fetch_detail: fetchDetail,
        detail_limit: clampInt(detailLimit, 20, 0, 50),
        enabled,
      });
      setFormVisible(false);
      setKeyword(FORM_DEFAULTS.keyword);
      Alert.alert('创建成功', jobId != null ? `任务 #${jobId} 已创建` : '任务已创建');
      await loadJobs();
    } catch (e) {
      Alert.alert('创建失败', (e as Error).message);
    } finally {
      setCreating(false);
    }
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载爬虫任务..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <Text style={[styles.headerHint, { color: c.textMuted }]}>长按任务可立即执行或删除</Text>
        <Pressable onPress={openCreate} style={[styles.addBtn, { backgroundColor: c.primary }]} hitSlop={8}>
          <Plus size={20} color="#FFF" />
        </Pressable>
      </View>

      <FlatList
        data={jobs}
        keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadJobs} />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <EmptyState
            icon={Plus}
            title="暂无爬虫任务"
            message="创建定时采集任务，按关键词自动抓取闲鱼商品"
            actionLabel="新建任务"
            onAction={openCreate}
          />
        }
        renderItem={({ item }) => {
          const expanded = expandedId === item.id;
          const busy = !!actionLoading[item.id];
          const items = itemsMap[item.id];
          return (
            <Pressable onLongPress={() => handleLongPress(item)} delayLongPress={400}>
              <Card style={styles.card}>
                <Pressable onPress={() => toggleExpand(item)} style={styles.jobHeader}>
                  <View style={styles.jobInfo}>
                    <Text style={[styles.jobName, { color: c.text }]} numberOfLines={1}>
                      {item.keyword}
                    </Text>
                    <Text style={[styles.jobAccount, { color: c.textMuted }]} numberOfLines={1}>
                      #{item.id} · {item.cookie_id}
                    </Text>
                    <View style={styles.jobMeta}>
                      <View style={[styles.badge, { backgroundColor: item.running ? c.success : item.enabled ? c.info : c.textMuted }]}>
                        <Text style={styles.badgeText}>{item.running ? '运行中' : item.enabled ? '已启用' : '已停止'}</Text>
                      </View>
                      <Text style={[styles.count, { color: c.textMuted }]}>{item.item_count} 件商品</Text>
                      {item.last_run_at ? (
                        <Text style={[styles.count, { color: c.textMuted }]} numberOfLines={1}>
                          上次 {formatTime(item.last_run_at)}
                        </Text>
                      ) : null}
                    </View>
                    {item.last_error ? (
                      <Text style={[styles.lastError, { color: c.error }]} numberOfLines={2}>
                        {item.last_error}
                      </Text>
                    ) : null}
                  </View>
                  <Text style={[styles.chevron, { color: c.textMuted }]}>{expanded ? '▲' : '▼'}</Text>
                </Pressable>

                <View style={styles.jobActions}>
                  <Button
                    label="立即执行"
                    variant="primary"
                    onPress={() => handleRunOnce(item)}
                    loading={busy}
                    style={styles.actionBtn}
                  />
                  {item.running || item.enabled ? (
                    <Button
                      label="停止"
                      variant="danger"
                      onPress={() => handleStop(item.id)}
                      loading={busy}
                      style={styles.actionBtn}
                    />
                  ) : (
                    <Button
                      label="启动"
                      variant="secondary"
                      onPress={() => handleStart(item.id)}
                      loading={busy}
                      style={styles.actionBtn}
                    />
                  )}
                </View>

                {expanded && (
                  <View style={[styles.itemsWrap, { borderTopColor: c.border, borderTopWidth: 1 }]}>
                    {itemsLoading[item.id] ? (
                      <Text style={[styles.hint, { color: c.textMuted }]}>加载商品中...</Text>
                    ) : items && items.length > 0 ? (
                      items.map((it) => (
                        <View key={it.item_id} style={[styles.itemRow, { borderBottomColor: c.border }]}>
                          <View style={styles.itemTexts}>
                            <Text style={[styles.itemTitle, { color: c.text }]} numberOfLines={1}>
                              {it.title || it.item_id}
                            </Text>
                            {(it.area || it.seller_name) && (
                              <Text style={[styles.itemSub, { color: c.textMuted }]} numberOfLines={1}>
                                {[it.area, it.seller_name].filter(Boolean).join(' · ')}
                              </Text>
                            )}
                          </View>
                          <Text style={[styles.itemPrice, { color: c.primary }]}>¥{it.price}</Text>
                        </View>
                      ))
                    ) : (
                      <Text style={[styles.hint, { color: c.textMuted }]}>暂无商品，可点击「立即执行」抓取</Text>
                    )}
                  </View>
                )}
              </Card>
            </Pressable>
          );
        }}
      />

      <FormModal visible={formVisible} onClose={() => setFormVisible(false)} title="新建采集任务">
        <ScrollView nestedScrollEnabled style={styles.formScroll} contentContainerStyle={styles.formContent}>
          <Text style={[styles.label, { color: c.textSecondary }]}>采集账号</Text>
          {accounts.length === 0 ? (
            <Text style={[styles.hint, { color: c.error }]}>暂无可用账号，请先在「账号管理」登录</Text>
          ) : (
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.accountSelector} contentContainerStyle={styles.accountSelectorContent}>
              {accounts.map((a) => (
                <Pressable
                  key={a.id}
                  onPress={() => setCookieId(a.id)}
                  style={[styles.accountOption, { backgroundColor: cookieId === a.id ? c.primary : c.background, borderColor: cookieId === a.id ? c.primary : c.border }]}
                >
                  <Text style={[styles.typeOptionText, { color: cookieId === a.id ? '#FFF' : c.text }]} numberOfLines={1}>
                    {a.remark || a.id}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>
          )}

          <Text style={[styles.label, { color: c.textSecondary }]}>搜索关键词</Text>
          <Input value={keyword} onChangeText={setKeyword} placeholder="如：iPhone 数据线" style={styles.input} />

          <View style={styles.gridRow}>
            <View style={styles.gridItem}>
              <Text style={[styles.label, { color: c.textSecondary }]}>间隔（秒，≥60）</Text>
              <Input value={intervalSeconds} onChangeText={setIntervalSeconds} keyboardType="number-pad" style={styles.input} />
            </View>
            <View style={styles.gridItem}>
              <Text style={[styles.label, { color: c.textSecondary }]}>起始页</Text>
              <Input value={startPage} onChangeText={setStartPage} keyboardType="number-pad" style={styles.input} />
            </View>
          </View>
          <View style={styles.gridRow}>
            <View style={styles.gridItem}>
              <Text style={[styles.label, { color: c.textSecondary }]}>抓取页数（≤10）</Text>
              <Input value={pages} onChangeText={setPages} keyboardType="number-pad" style={styles.input} />
            </View>
            <View style={styles.gridItem}>
              <Text style={[styles.label, { color: c.textSecondary }]}>每页条数（≤50）</Text>
              <Input value={pageSize} onChangeText={setPageSize} keyboardType="number-pad" style={styles.input} />
            </View>
          </View>

          <View style={styles.switchRow}>
            <View style={styles.switchTexts}>
              <Text style={[styles.label, { color: c.text }]}>抓取商品详情</Text>
              <Text style={[styles.hint, { color: c.textMuted }]}>包含描述、浏览/想要数等详情字段</Text>
            </View>
            <Switch value={fetchDetail} onValueChange={setFetchDetail} trackColor={{ false: c.border, true: c.primary }} />
          </View>
          {fetchDetail && (
            <View>
              <Text style={[styles.label, { color: c.textSecondary }]}>详情抓取上限（≤50）</Text>
              <Input value={detailLimit} onChangeText={setDetailLimit} keyboardType="number-pad" style={styles.input} />
            </View>
          )}

          <View style={styles.switchRow}>
            <View style={styles.switchTexts}>
              <Text style={[styles.label, { color: c.text }]}>创建后立即启用</Text>
              <Text style={[styles.hint, { color: c.textMuted }]}>按设定间隔自动执行采集</Text>
            </View>
            <Switch value={enabled} onValueChange={setEnabled} trackColor={{ false: c.border, true: c.primary }} />
          </View>
        </ScrollView>

        <View style={styles.sheetActions}>
          <Button label="取消" variant="secondary" onPress={() => setFormVisible(false)} style={styles.sheetBtn} />
          <Button label="创建任务" onPress={handleCreate} loading={creating} style={styles.sheetBtn} />
        </View>
      </FormModal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  headerHint: { ...typography.small, flex: 1, marginRight: spacing.md },
  addBtn: { width: 32, height: 32, borderRadius: radius.full, alignItems: 'center', justifyContent: 'center' },
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.md, paddingBottom: 80 },
  card: { gap: spacing.sm },
  jobHeader: { flexDirection: 'row', alignItems: 'center' },
  jobInfo: { flex: 1, marginRight: spacing.sm, gap: spacing.xs },
  jobName: { ...typography.body, fontWeight: '600' },
  jobAccount: { ...typography.small },
  jobMeta: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flexWrap: 'wrap' },
  badge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.sm },
  badgeText: { ...typography.small, fontWeight: '600', color: '#FFF' },
  count: { ...typography.small },
  lastError: { ...typography.small },
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
  itemTexts: { flex: 1, marginRight: spacing.sm, gap: 2 },
  itemTitle: { ...typography.caption, fontWeight: '600' },
  itemSub: { ...typography.small },
  itemPrice: { ...typography.caption, fontWeight: '600' },
  hint: { ...typography.small, paddingVertical: spacing.sm },
  // 新建表单
  formScroll: { flexGrow: 0 },
  formContent: { gap: spacing.xs, paddingBottom: spacing.sm },
  label: { ...typography.caption },
  accountSelector: { flexGrow: 0 },
  accountSelectorContent: { gap: spacing.sm, paddingVertical: spacing.xs },
  accountOption: { maxWidth: 160, paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.sm, borderWidth: 1 },
  typeOptionText: { ...typography.caption },
  input: { marginTop: spacing.xs },
  gridRow: { flexDirection: 'row', gap: spacing.sm },
  gridItem: { flex: 1 },
  switchRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: spacing.sm },
  switchTexts: { flex: 1, marginRight: spacing.md, gap: 2 },
  sheetActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm },
  sheetBtn: { flex: 1 },
});
