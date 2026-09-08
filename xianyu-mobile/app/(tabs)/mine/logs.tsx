import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  ScrollView,
  Alert,
  RefreshControl,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { ChevronDown } from 'lucide-react-native';
import { Card, Button, Loading, Badge, FormModal } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { useAuthStore } from '@/stores/auth';
import { getAccountOptions, type AccountOption } from '@/api/wrappers/accounts';
import {
  getAdminLogs,
  clearAdminLogs,
  getAutoReplyLogs,
  getAccountLoginLogs,
  clearAccountLoginLogs,
  type LogEntry,
  type AccountLoginLog,
} from '@/api/wrappers/admin';
import { usePagedList } from '@/hooks/usePagedList';

const PAGE_SIZE = 20;

/** 徽章颜色变体（与 ui/Badge 内部口径一致，本文件局部声明以避免跨文件耦合） */
type BadgeVariant = 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'gray';

type TabKey = 'admin' | 'autoreply' | 'login';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'admin', label: '管理员日志' },
  { key: 'autoreply', label: '自动回复日志' },
  { key: 'login', label: '登录日志' },
];

// 登录状态 -> 徽章文案/颜色（对齐 web LOGIN_STATUS_LABELS）
const LOGIN_STATUS_LABELS: Record<string, { text: string; variant: BadgeVariant }> = {
  success: { text: '成功', variant: 'success' },
  failed: { text: '失败', variant: 'danger' },
  skipped_cooldown: { text: '冷却跳过', variant: 'warning' },
  no_credentials: { text: '未配置账密', variant: 'gray' },
};

// 失败/跳过细分原因中文映射（对齐 web FAILURE_REASON_LABELS）
const FAILURE_REASON_LABELS: Record<string, string> = {
  bad_credentials: '账号或密码错误',
  baxia_punish_captcha: '风控图形验证（如找松鼠）',
  account_info_missing: '无法获取账号信息',
  no_credentials: '未配置账号或密码',
  cookie_already_updated_externally: 'Cookie已被外部更新',
  cookie_update_failed: 'Cookie更新或重启失败',
  login_no_cookie_returned: '登录未返回Cookie',
  login_cooldown: '密码登录冷却中',
  password_error_cooldown: '账密错误冷却中',
  exception: '其他异常',
};

const LOGIN_STATUS_FILTERS: { key: string; label: string }[] = [
  { key: '', label: '全部' },
  { key: 'success', label: '成功' },
  { key: 'failed', label: '失败' },
  { key: 'skipped_cooldown', label: '冷却跳过' },
  { key: 'no_credentials', label: '未配置账密' },
];

type DateRange = 'today' | '7d' | '30d' | 'all';
const DATE_RANGES: { key: DateRange; label: string }[] = [
  { key: 'today', label: '今天' },
  { key: '7d', label: '近7天' },
  { key: '30d', label: '近30天' },
  { key: 'all', label: '全部' },
];

function pad(n: number) {
  return String(n).padStart(2, '0');
}
function dateStr(d: Date) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}
function todayStr() {
  return dateStr(new Date());
}
function daysAgoStr(n: number) {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return dateStr(d);
}
function rangeToDates(range: DateRange): { start?: string; end?: string } {
  const today = todayStr();
  switch (range) {
    case 'today':
      return { start: today, end: today };
    case '7d':
      return { start: daysAgoStr(6), end: today };
    case '30d':
      return { start: daysAgoStr(29), end: today };
    case 'all':
    default:
      return {};
  }
}

function renderDuration(ms: number | null | undefined): string {
  if (ms == null) return '-';
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

/** ISO 时间 → 可读字符串，无法解析时原样返回 */
function formatDate(iso?: string): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(
    d.getHours(),
  )}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

export default function LogsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const user = useAuthStore((s) => s.user);

  const [tab, setTab] = useState<TabKey>('admin');

  // 账号列表（登录日志筛选用），管理员页面挂载时加载
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [accountSheet, setAccountSheet] = useState(false);

  // 登录日志筛选
  const [loginAccount, setLoginAccount] = useState('');
  const [loginStatus, setLoginStatus] = useState('');
  const [loginDateRange, setLoginDateRange] = useState<DateRange>('today');

  const [clearing, setClearing] = useState(false);
  const [loginClearing, setLoginClearing] = useState(false);

  // 首次切到未加载 Tab 时的整屏 loading（对齐原共享 loading 行为）
  const [tabGateLoading, setTabGateLoading] = useState(false);
  const autoStartedRef = useRef(false);
  const loginStartedRef = useRef(false);

  // ---- 管理员日志（page 分页，带 total，追加按 id 去重） ----
  const adminList = usePagedList<LogEntry>({
    mode: 'page',
    pageSize: PAGE_SIZE,
    dedupeBy: (l) => l.id,
    fetchPage: async ({ page = 1 }) => {
      const resp = await getAdminLogs(page, PAGE_SIZE);
      return { items: resp.data, total: resp.total };
    },
    onError: (e, phase) => {
      console.error('加载管理员日志失败', e);
      if (phase === 'refresh') Alert.alert('加载失败', e.message);
    },
  });

  // ---- 自动回复日志（page 分页；接口无 total，按"是否满一页"折算 hasMore） ----
  const autoLoadedRef = useRef(0);
  const autoList = usePagedList<LogEntry>({
    mode: 'page',
    pageSize: PAGE_SIZE,
    auto: false, // 首次切到该 Tab 时才加载
    dedupeBy: (l) => l.id,
    fetchPage: async ({ page = 1 }) => {
      const list = await getAutoReplyLogs(page);
      if (page === 1) autoLoadedRef.current = 0;
      autoLoadedRef.current += list.length;
      return {
        items: list,
        // 短页视为最后一页：total 钉在已加载数，保持原 hasMore 判断
        total:
          list.length >= PAGE_SIZE ? Number.MAX_SAFE_INTEGER : autoLoadedRef.current,
      };
    },
    onError: (e, phase) => {
      console.error('加载自动回复日志失败', e);
      if (phase === 'refresh') Alert.alert('加载失败', e.message);
    },
  });

  // ---- 登录日志（offset 分页 + 多维筛选；首次切到 Tab 才加载） ----
  // fetchPage 内联闭包捕获当前筛选条件；usePagedList 每次 render 将最新 options 写入 ref，
  // 故 refresh/loadMore 始终使用最新筛选值。
  const loginList = usePagedList<AccountLoginLog>({
    mode: 'offset',
    pageSize: PAGE_SIZE,
    auto: false,
    fetchPage: async ({ limit, offset }) => {
      const { start, end } = rangeToDates(loginDateRange);
      const r = await getAccountLoginLogs({
        limit,
        offset,
        cookie_id: loginAccount || undefined,
        start_date: start,
        end_date: end,
        login_status: loginStatus || undefined,
      });
      return { items: r.items, total: r.total };
    },
    onError: (e, phase) => {
      console.error('加载登录日志失败', e);
      if (phase === 'refresh') Alert.alert('加载失败', e.message);
    },
  });

  // 账号 cookie_id -> remark 映射，避免渲染时重复 find
  const accountNoteMap = useMemo(() => {
    const map = new Map<string, string>();
    accounts.forEach((acc) => {
      if (acc.remark) map.set(acc.id, acc.remark);
    });
    return map;
  }, [accounts]);

  // 账号列表加载（仅管理员进入页面时，供登录日志筛选）
  const loadAccounts = useCallback(async () => {
    try {
      setAccounts(await getAccountOptions());
    } catch (e) {
      console.error('加载账号列表失败', e);
    }
  }, []);

  // 挂载时加载账号列表（登录日志筛选用）
  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  function switchTab(key: TabKey) {
    if (key === tab) return;
    setTab(key);
    // 未加载过的 Tab 首次进入时拉取；已加载的直接展示 hook 缓存
    if (key === 'autoreply' && !autoStartedRef.current) {
      autoStartedRef.current = true;
      setTabGateLoading(true);
      autoList.refresh().finally(() => setTabGateLoading(false));
    } else if (key === 'login' && !loginStartedRef.current) {
      loginStartedRef.current = true;
      setTabGateLoading(true);
      loginList.refresh().finally(() => setTabGateLoading(false));
    }
  }

  function handleRefresh() {
    if (tab === 'admin') adminList.refresh();
    else if (tab === 'autoreply') autoList.refresh();
    else loginList.refresh();
  }

  function handleLoadMore() {
    if (tab === 'admin') adminList.loadMore();
    else if (tab === 'autoreply') autoList.loadMore();
    else loginList.loadMore();
  }

  function handleSearchLogin() {
    loginList.refresh();
  }

  async function handleClear() {
    Alert.alert('清除日志', '确定清除所有管理员日志吗？此操作不可恢复。', [
      { text: '取消', style: 'cancel' },
      {
        text: '清除',
        style: 'destructive',
        onPress: async () => {
          setClearing(true);
          try {
            await clearAdminLogs();
            adminList.reset();
            Alert.alert('成功', '日志已清除');
          } catch (e) {
            Alert.alert('清除失败', (e as Error).message);
          } finally {
            setClearing(false);
          }
        },
      },
    ]);
  }

  function handleClearLogin(mode: 'older_than_10d' | 'all') {
    const is10d = mode === 'older_than_10d';
    Alert.alert(
      is10d ? '清理确认' : '清空确认',
      is10d
        ? '将删除 10 天前的全部账号登录日志（保留最近 10 天数据），此操作不可恢复，是否继续？'
        : '将清空全部账号登录日志（包含历史所有数据），此操作不可恢复，是否继续？',
      [
        { text: '取消', style: 'cancel' },
        {
          text: is10d ? '清理' : '清空',
          style: 'destructive',
          onPress: async () => {
            setLoginClearing(true);
            try {
              if (is10d) {
                await clearAccountLoginLogs({ days: 10 });
              } else {
                await clearAccountLoginLogs();
              }
              await loginList.refresh();
              Alert.alert('成功', is10d ? '已清理 10 天前的日志' : '已清空全部日志');
            } catch (e) {
              Alert.alert('清理失败', (e as Error).message);
            } finally {
              setLoginClearing(false);
            }
          },
        },
      ],
    );
  }

  // 当前激活 tab 对应的列表句柄
  const list =
    tab === 'admin' ? adminList : tab === 'autoreply' ? autoList : loginList;
  const currentData = list.items as (LogEntry | AccountLoginLog)[];

  const loading = list.loading || tabGateLoading;
  const refreshing = list.refreshing;
  const showLoadingMore = list.loadingMore;

  const loginAccountLabel = useMemo(() => {
    if (!loginAccount) return '全部账号';
    const acc = accounts.find((a) => a.id === loginAccount);
    return acc?.remark ? `${acc.id} (${acc.remark})` : loginAccount;
  }, [loginAccount, accounts]);

  // 非管理员：无权限提示
  if (!user?.is_admin) {
    return (
      <SafeAreaView
        style={[styles.container, { backgroundColor: c.background }]}
        edges={['left', 'right', 'bottom']}
      >
        <View style={styles.empty}>
          <Text style={[styles.emptyText, { color: c.textMuted }]}>
            无权限访问，仅管理员可查看
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  if (loading && currentData.length === 0) {
    return (
      <SafeAreaView
        style={[styles.container, { backgroundColor: c.background }]}
        edges={['left', 'right', 'bottom']}
      >
        <Loading label="加载日志..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: c.background }]}
      edges={['left', 'right', 'bottom']}
    >
      <View style={styles.header}>
        {tab === 'admin' && (
          <Button
            label="清除日志"
            onPress={handleClear}
            variant="danger"
            loading={clearing}
            disabled={clearing}
          />
        )}
        {tab === 'login' && (
          <View style={styles.loginActions}>
            <Button
              label="清理10天前"
              onPress={() => handleClearLogin('older_than_10d')}
              variant="secondary"
              loading={loginClearing}
              disabled={loginClearing}
              style={styles.loginActionBtn}
            />
            <Button
              label="清空全部"
              onPress={() => handleClearLogin('all')}
              variant="danger"
              loading={loginClearing}
              disabled={loginClearing}
              style={styles.loginActionBtn}
            />
          </View>
        )}
      </View>

      {/* Tab 切换 */}
      <View style={[styles.tabBar, { borderBottomColor: c.border }]}>
        {TABS.map((t) => {
          const active = t.key === tab;
          return (
            <Pressable
              key={t.key}
              onPress={() => switchTab(t.key)}
              style={[
                styles.tabItem,
                active && { borderBottomColor: c.primary, borderBottomWidth: 2 },
              ]}
            >
              <Text
                style={[
                  styles.tabText,
                  { color: active ? c.primary : c.textSecondary },
                  active && { fontWeight: '600' },
                ]}
              >
                {t.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {/* 登录日志筛选区（仅 login tab） */}
      {tab === 'login' ? (
        <Card style={styles.loginFilter}>
          <View style={styles.loginFilterRow}>
            <Pressable
              style={[
                styles.accountPicker,
                { borderColor: c.border, backgroundColor: c.surface },
              ]}
              onPress={() => setAccountSheet(true)}
            >
              <Text
                style={[styles.accountPickerText, { color: c.text }]}
                numberOfLines={1}
              >
                {loginAccountLabel}
              </Text>
              <ChevronDown size={14} color={c.textMuted} />
            </Pressable>
            <Button
              label="查询"
              onPress={handleSearchLogin}
              variant="primary"
              loading={loginList.refreshing}
              disabled={loginList.refreshing}
              style={styles.searchBtn}
            />
          </View>
          <ChipRow c={c}>
            {DATE_RANGES.map((r) => (
              <Chip
                key={r.key}
                label={r.label}
                active={loginDateRange === r.key}
                onPress={() => setLoginDateRange(r.key)}
                c={c}
              />
            ))}
          </ChipRow>
          <ChipRow c={c}>
            {LOGIN_STATUS_FILTERS.map((s) => (
              <Chip
                key={s.key}
                label={s.label}
                active={loginStatus === s.key}
                onPress={() => setLoginStatus(s.key)}
                c={c}
              />
            ))}
          </ChipRow>
        </Card>
      ) : null}

      <FlatList
        data={currentData}
        keyExtractor={(item, index) =>
          item.id != null ? String(item.id) : String(index)
        }
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
        }
        onEndReached={handleLoadMore}
        onEndReachedThreshold={0.3}
        renderItem={({ item }) => {
          if (tab === 'login') {
            const log = item as AccountLoginLog;
            const note = accountNoteMap.get(log.cookie_id);
            const meta =
              LOGIN_STATUS_LABELS[log.login_status] ?? {
                text: log.login_status || '-',
                variant: 'gray' as BadgeVariant,
              };
            const fr = log.failure_reason;
            return (
              <Card style={styles.card}>
                <View style={styles.cardHeader}>
                  <Badge label={meta.text} variant={meta.variant} />
                  <Text style={[styles.time, { color: c.textMuted }]}>
                    {formatDate(log.created_at)}
                  </Text>
                </View>
                <Text
                  style={[styles.cookieId, { color: c.text }]}
                  numberOfLines={1}
                >
                  {note ? `${log.cookie_id} (${note})` : log.cookie_id || '-'}
                </Text>
                {log.username ? (
                  <Text style={[styles.sub, { color: c.textSecondary }]}>
                    用户名：{log.username}
                  </Text>
                ) : null}
                {log.trigger_reason ? (
                  <Text style={[styles.sub, { color: c.textSecondary }]}>
                    触发：{log.trigger_reason}
                  </Text>
                ) : null}
                {fr ? (
                  <Text style={[styles.sub, { color: c.error }]}>
                    失败：{FAILURE_REASON_LABELS[fr] ?? fr}
                  </Text>
                ) : null}
                {log.error_message ? (
                  <Text
                    style={[styles.sub, { color: c.textMuted }]}
                    numberOfLines={2}
                  >
                    {log.error_message}
                  </Text>
                ) : null}
                {log.duration_ms != null ? (
                  <Text style={[styles.sub, { color: c.textMuted }]}>
                    耗时：{renderDuration(log.duration_ms)}
                  </Text>
                ) : null}
              </Card>
            );
          }
          const log = item as LogEntry;
          return (
            <Card style={styles.card}>
              {log.type ? (
                <View style={styles.cardHeader}>
                  <View style={[styles.typeTag, { backgroundColor: c.primaryLight }]}>
                    <Text style={[styles.typeText, { color: c.primary }]}>
                      {log.type}
                    </Text>
                  </View>
                  <Text style={[styles.time, { color: c.textMuted }]}>
                    {formatDate(log.created_at)}
                  </Text>
                </View>
              ) : (
                <Text style={[styles.time, { color: c.textMuted }]}>
                  {formatDate(log.created_at)}
                </Text>
              )}
              <Text style={[styles.content, { color: c.text }]}>
                {log.content || '(无内容)'}
              </Text>
            </Card>
          );
        }}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: c.textMuted }]}>暂无日志</Text>
          </View>
        }
        ListFooterComponent={
          showLoadingMore ? (
            <Text style={[styles.loadingMore, { color: c.textMuted }]}>
              加载中...
            </Text>
          ) : null
        }
        contentContainerStyle={styles.listContent}
      />

      {/* 账号选择 sheet（登录日志筛选） */}
      <FormModal
        visible={accountSheet}
        onClose={() => setAccountSheet(false)}
        title="选择账号"
      >
        <ScrollView style={styles.sheetScroll}>
          <Pressable
            onPress={() => {
              setLoginAccount('');
              setAccountSheet(false);
            }}
            style={[
              styles.sheetItem,
              !loginAccount && { backgroundColor: c.primaryLight },
            ]}
          >
            <Text
              style={[
                styles.sheetItemText,
                { color: !loginAccount ? c.primary : c.text },
              ]}
            >
              全部账号
            </Text>
          </Pressable>
          {accounts.map((a) => {
            const active = a.id === loginAccount;
            return (
              <Pressable
                key={a.pk}
                onPress={() => {
                  setLoginAccount(a.id);
                  setAccountSheet(false);
                }}
                style={[styles.sheetItem, active && { backgroundColor: c.primaryLight }]}
              >
                <Text
                  style={[
                    styles.sheetItemText,
                    { color: active ? c.primary : c.text },
                  ]}
                  numberOfLines={1}
                >
                  {a.remark ? `${a.id} (${a.remark})` : a.id}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </FormModal>
    </SafeAreaView>
  );
}

// ---- 文件内复用子组件 ----

function Chip({
  label,
  active,
  onPress,
  c,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  c: (typeof colors)['light'];
}) {
  return (
    <Pressable
      onPress={onPress}
      style={[
        styles.chip,
        {
          backgroundColor: active ? c.primary : c.surface,
          borderColor: active ? c.primary : c.border,
        },
      ]}
    >
      <Text style={[styles.chipText, { color: active ? '#FFFFFF' : c.textSecondary }]}>
        {label}
      </Text>
    </Pressable>
  );
}

function ChipRow({
  c,
  children,
}: {
  c: (typeof colors)['light'];
  children: React.ReactNode;
}) {
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      contentContainerStyle={styles.chipRow}
    >
      {children}
    </ScrollView>
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
  loginActions: { flexDirection: 'row', gap: spacing.sm },
  loginActionBtn: { minHeight: 40, paddingHorizontal: spacing.lg },
  tabBar: {
    flexDirection: 'row',
    borderBottomWidth: 1,
  },
  tabItem: {
    flex: 1,
    alignItems: 'center',
    paddingVertical: spacing.md,
  },
  tabText: { ...typography.body },
  loginFilter: { gap: spacing.sm, marginHorizontal: spacing.lg, padding: spacing.md },
  loginFilterRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  accountPicker: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: 40,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
  },
  accountPickerText: { ...typography.caption, flexShrink: 1 },
  searchBtn: { minHeight: 40, paddingHorizontal: spacing.lg },
  chipRow: { gap: spacing.xs, paddingVertical: 2, alignItems: 'center' },
  chip: {
    paddingHorizontal: spacing.md,
    height: 28,
    borderRadius: radius.full,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipText: { fontSize: 12, fontWeight: '500' },
  listContent: { padding: spacing.lg, gap: spacing.md },
  card: { gap: spacing.sm, padding: spacing.md },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.sm,
  },
  typeTag: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: 4,
  },
  typeText: { ...typography.small },
  time: { ...typography.small },
  content: { ...typography.body },
  cookieId: { ...typography.caption, fontWeight: '600' },
  sub: { ...typography.small },
  empty: { alignItems: 'center', justifyContent: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  loadingMore: { textAlign: 'center', padding: spacing.md },
  sheetScroll: { maxHeight: 460 },
  sheetItem: {
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: radius.sm,
  },
  sheetItemText: { ...typography.body },
});
