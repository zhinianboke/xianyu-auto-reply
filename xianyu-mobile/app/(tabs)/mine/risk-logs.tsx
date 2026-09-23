import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  ActivityIndicator,
  Alert,
  RefreshControl,
  ScrollView,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import {
  CheckCircle2,
  XCircle,
  ChevronDown,
  ChevronRight,
  Settings,
  ShieldAlert,
} from 'lucide-react-native';
import { Card, Button, Loading, Input, FormModal, Badge } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { useAuthStore } from '@/stores/auth';
import { getAccountOptions, type AccountOption } from '@/api/wrappers/accounts';
import {
  getRiskControlLogs,
  getRiskTodaySuccessRate,
  clearRiskLogs,
  clearProcessingRiskLogs,
  getLocalSliderConfig,
  updateLocalSliderConfig,
  getRemoteCaptchaConfig,
  saveRemoteCaptchaConfig,
  testRemoteSliderSolve,
  type RiskControlLog,
  type RiskTodaySuccessRate,
  type RemoteCaptchaConfig,
} from '@/api/wrappers/admin';
import { usePagedList } from '@/hooks/usePagedList';

const PAGE_SIZE = 20;

/** 徽章颜色变体（与 ui/Badge 内部口径一致，本文件局部声明以避免跨文件耦合） */
type BadgeVariant = 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'gray';

/** 处理状态 -> 徽章文案/颜色 */
const STATUS_META: Record<string, { text: string; variant: BadgeVariant }> = {
  success: { text: '成功', variant: 'success' },
  failed: { text: '失败', variant: 'danger' },
  processing: { text: '处理中', variant: 'warning' },
  cancelled: { text: '已取消', variant: 'gray' },
};

/** 调用类型 -> 徽章 */
function callTypeMeta(callType?: string) {
  if (callType === 'remote') return { text: '远程', variant: 'info' as BadgeVariant };
  if (callType === 'local') return { text: '本机', variant: 'gray' as BadgeVariant };
  return null;
}

/** 验证引擎 -> 徽章 */
function engineMeta(engine?: string) {
  switch (engine) {
    case 'drissionpage':
      return { text: '兜底引擎', variant: 'primary' as BadgeVariant };
    case 'playwright':
      return { text: '主引擎', variant: 'info' as BadgeVariant };
    case 'real_mouse':
      return { text: '真人鼠标', variant: 'success' as BadgeVariant };
    case 'remote':
      return { text: '远程接口', variant: 'info' as BadgeVariant };
    default:
      return null;
  }
}

/** "2026-01-01T12:34:56" -> "2026-01-01 12:34" */
function formatDate(value?: string): string {
  if (!value) return '';
  return value.replace('T', ' ').slice(0, 16);
}

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

type DateRange = 'today' | '7d' | '30d' | 'all';
const DATE_RANGES: { key: DateRange; label: string }[] = [
  { key: 'today', label: '今天' },
  { key: '7d', label: '近7天' },
  { key: '30d', label: '近30天' },
  { key: 'all', label: '全部' },
];
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

const STATUS_FILTERS: { key: string; label: string }[] = [
  { key: '', label: '全部' },
  { key: 'success', label: '成功' },
  { key: 'failed', label: '失败' },
  { key: 'processing', label: '处理中' },
  { key: 'cancelled', label: '已取消' },
];

const CALLTYPE_FILTERS: { key: string; label: string }[] = [
  { key: '', label: '全部' },
  { key: 'local', label: '本机' },
  { key: 'remote', label: '远程' },
];

export default function RiskLogsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const user = useAuthStore((s) => s.user);
  const isAdmin = !!user?.is_admin;

  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [selectedAccount, setSelectedAccount] = useState('');
  const [selectedStatus, setSelectedStatus] = useState('');
  const [selectedCallType, setSelectedCallType] = useState('');
  const [dateRange, setDateRange] = useState<DateRange>('today');

  const [accountSheet, setAccountSheet] = useState(false);

  const [rate, setRate] = useState<RiskTodaySuccessRate | null>(null);

  // 本机滑块开关（管理员）
  const [localDisabled, setLocalDisabled] = useState(false);
  const [localLoading, setLocalLoading] = useState(isAdmin);
  const [localSaving, setLocalSaving] = useState(false);

  // 远程过滑块配置（管理员）
  const [remoteOpen, setRemoteOpen] = useState(false);
  const [remoteCfg, setRemoteCfg] = useState<RemoteCaptchaConfig | null>(null);
  const [remoteLoading, setRemoteLoading] = useState(false);
  const [remoteSaving, setRemoteSaving] = useState(false);
  const [remoteTesting, setRemoteTesting] = useState(false);

  const [clearing, setClearing] = useState(false);
  const [clearingProcessing, setClearingProcessing] = useState(false);

  const { start, end } = useMemo(() => rangeToDates(dateRange), [dateRange]);

  // 列表分页（offset 模式）：竞态序号、重入守卫均在 usePagedList 内部处理。
  // fetchPage 内联闭包捕获当前筛选条件；usePagedList 每次 render 将最新 options 写入 ref，
  // 故 refresh/loadMore 始终使用最新筛选值。
  const {
    items: logs,
    total,
    loading,
    refreshing,
    loadingMore,
    hasMore,
    refresh: refreshLogs,
    loadMore: loadMoreLogs,
  } = usePagedList<RiskControlLog>({
    mode: 'offset',
    pageSize: PAGE_SIZE,
    fetchPage: async ({ limit, offset }) => {
      const r = await getRiskControlLogs({
        limit,
        offset,
        cookie_id: selectedAccount || undefined,
        start_date: start,
        end_date: end,
        processing_status: selectedStatus || undefined,
        call_type: selectedCallType || undefined,
      });
      return { items: r.items, total: r.total };
    },
    onError: (e, phase) =>
      Alert.alert(phase === 'refresh' ? '加载失败' : '加载更多失败', e.message),
  });

  const loadRate = useCallback(async () => {
    setRate(await getRiskTodaySuccessRate());
  }, []);

  // 本机滑块开关：管理员身份水合可能晚于 token，单独加载并复位 loading
  const loadLocalSlider = useCallback(async () => {
    if (!isAdmin) {
      setLocalLoading(false);
      return;
    }
    try {
      setLocalLoading(true);
      const cfg = await getLocalSliderConfig();
      setLocalDisabled(cfg.enabled);
    } catch (e) {
      Alert.alert('加载本机滑块开关失败', (e as Error).message);
    } finally {
      setLocalLoading(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    getAccountOptions()
      .then(setAccounts)
      .catch((e) => Alert.alert('加载账号列表失败', (e as Error).message));
    loadRate();
    loadLocalSlider();
  }, [loadRate, loadLocalSlider]);

  async function handleSearch() {
    await Promise.all([refreshLogs(), loadRate()]);
  }

  async function handleRefresh() {
    await Promise.all([loadRate(), refreshLogs()]);
  }

  async function toggleLocalSlider() {
    const next = !localDisabled;
    try {
      setLocalSaving(true);
      const cfg = await updateLocalSliderConfig(next);
      setLocalDisabled(cfg.enabled);
    } catch (e) {
      Alert.alert('更新本机滑块开关失败', (e as Error).message);
    } finally {
      setLocalSaving(false);
    }
  }

  async function openRemoteConfig() {
    setRemoteOpen(true);
    if (remoteCfg) return;
    try {
      setRemoteLoading(true);
      setRemoteCfg(await getRemoteCaptchaConfig());
    } catch (e) {
      Alert.alert('加载远程配置失败', (e as Error).message);
    } finally {
      setRemoteLoading(false);
    }
  }

  async function handleSaveRemote() {
    if (!remoteCfg) return;
    try {
      setRemoteSaving(true);
      await saveRemoteCaptchaConfig(remoteCfg);
      Alert.alert('成功', '远程过滑块配置已保存');
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setRemoteSaving(false);
    }
  }

  async function handleTestRemote() {
    if (!remoteCfg) return;
    if (!remoteCfg.url) {
      Alert.alert('提示', '请先填写远程服务URL');
      return;
    }
    try {
      setRemoteTesting(true);
      const res = await testRemoteSliderSolve(remoteCfg.url, remoteCfg.secret_key);
      Alert.alert(res.success ? '连接成功' : '连接失败', res.message || '');
    } finally {
      setRemoteTesting(false);
    }
  }

  function handleClear() {
    Alert.alert('清空确认', '确定要清空所有风控日志吗？此操作不可恢复！', [
      { text: '取消', style: 'cancel' },
      {
        text: '清空',
        style: 'destructive',
        onPress: async () => {
          try {
            setClearing(true);
            await clearRiskLogs();
            await Promise.all([refreshLogs(), loadRate()]);
          } catch (e) {
            Alert.alert('清空失败', (e as Error).message);
          } finally {
            setClearing(false);
          }
        },
      },
    ]);
  }

  function handleClearProcessing() {
    Alert.alert(
      '清空处理中日志',
      '确定要清空所有处理中状态的风控日志吗（含卡死未收尾的记录）？此操作不可恢复！',
      [
        { text: '取消', style: 'cancel' },
        {
          text: '清空',
          style: 'destructive',
          onPress: async () => {
            try {
              setClearingProcessing(true);
              await clearProcessingRiskLogs();
              await Promise.all([refreshLogs(), loadRate()]);
            } catch (e) {
              Alert.alert('清空失败', (e as Error).message);
            } finally {
              setClearingProcessing(false);
            }
          },
        },
      ],
    );
  }

  const accountLabel = useMemo(() => {
    if (!selectedAccount) return '全部账号';
    const acc = accounts.find((a) => a.id === selectedAccount);
    return acc?.remark ? `${acc.id} (${acc.remark})` : selectedAccount;
  }, [selectedAccount, accounts]);

  if (loading) {
    return (
      <SafeAreaView
        style={[styles.container, { backgroundColor: c.background }]}
        edges={['left', 'right', 'bottom']}
      >
        <Loading label="加载风控日志..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: c.background }]}
      edges={['left', 'right', 'bottom']}
    >
      <FlatList
        data={logs}
        keyExtractor={(item) => String(item.id)}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={handleRefresh} />
        }
        onEndReached={loadMoreLogs}
        onEndReachedThreshold={0.2}
        ListHeaderComponent={
          <View style={styles.headerBlock}>
            {/* 管理员配置卡片：本机滑块开关 + 远程配置入口 */}
            {isAdmin ? (
              <Card style={styles.configCard}>
                <View style={styles.configRow}>
                  <View style={styles.configTitleRow}>
                    <Settings size={16} color={c.primary} />
                    <Text style={[styles.configTitle, { color: c.text }]}>
                      过滑块配置
                    </Text>
                  </View>
                  <View style={styles.localSwitchRow}>
                    <Text style={[styles.localSwitchLabel, { color: c.textSecondary }]}>
                      本机滑块不处理
                    </Text>
                    <Toggle
                      value={localDisabled}
                      disabled={localLoading || localSaving}
                      onValueChange={toggleLocalSlider}
                      color={c.primary}
                      trackColorOff={c.borderLight}
                    />
                  </View>
                </View>
                <Pressable
                  style={styles.remoteEntry}
                  onPress={openRemoteConfig}
                  hitSlop={8}
                >
                  <Text style={[styles.remoteEntryText, { color: c.primary }]}>
                    远程过滑块配置
                  </Text>
                  <ChevronRight size={16} color={c.primary} />
                </Pressable>
              </Card>
            ) : null}

            {/* 当日成功率：总体/本机/远程/处理中 */}
            <Card style={styles.rateCard}>
              <View style={styles.rateRow}>
                <RateCell
                  label="总体"
                  value={rate && rate.total > 0 ? `${rate.rate.toFixed(1)}%` : '--'}
                  sub={
                    rate && rate.total > 0
                      ? `${rate.success}/${rate.total}`
                      : ''
                  }
                  color={c.success}
                  c={c}
                />
                <View style={[styles.rateDivider, { backgroundColor: c.borderLight }]} />
                <RateCell
                  label="本机"
                  value={rate?.local_rate != null ? `${rate.local_rate.toFixed(1)}%` : '--'}
                  sub={
                    rate && rate.local_success != null && rate.local_total != null
                      ? `${rate.local_success}/${rate.local_total}`
                      : ''
                  }
                  color={c.primary}
                  c={c}
                />
                <View style={[styles.rateDivider, { backgroundColor: c.borderLight }]} />
                <RateCell
                  label="远程"
                  value={rate?.remote_rate != null ? `${rate.remote_rate.toFixed(1)}%` : '--'}
                  sub={
                    rate && rate.remote_success != null && rate.remote_total != null
                      ? `${rate.remote_success}/${rate.remote_total}`
                      : ''
                  }
                  color={c.warning}
                  c={c}
                />
                <View style={[styles.rateDivider, { backgroundColor: c.borderLight }]} />
                <RateCell
                  label="处理中"
                  value={rate?.processing != null ? String(rate.processing) : '--'}
                  sub=""
                  color={c.warning}
                  c={c}
                />
              </View>
            </Card>

            {/* 筛选区 */}
            <Card style={styles.filterCard}>
              {/* 账号 + 清空按钮 */}
              <View style={styles.filterRow}>
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
                    {accountLabel}
                  </Text>
                  <ChevronDown size={14} color={c.textMuted} />
                </Pressable>
                <Button
                  label="查询"
                  onPress={handleSearch}
                  variant="primary"
                  loading={refreshing}
                  disabled={refreshing}
                  style={styles.searchBtn}
                />
              </View>

              {/* 日期范围 chips */}
              <ChipRow>
                {DATE_RANGES.map((r) => (
                  <Chip
                    key={r.key}
                    label={r.label}
                    active={dateRange === r.key}
                    onPress={() => setDateRange(r.key)}
                    c={c}
                  />
                ))}
              </ChipRow>

              {/* 处理状态 chips */}
              <FilterLine label="状态" c={c}>
                <ChipRow>
                  {STATUS_FILTERS.map((s) => (
                    <Chip
                      key={s.key}
                      label={s.label}
                      active={selectedStatus === s.key}
                      onPress={() => setSelectedStatus(s.key)}
                      c={c}
                    />
                  ))}
                </ChipRow>
              </FilterLine>

              {/* 调用类型 chips */}
              <FilterLine label="调用" c={c}>
                <ChipRow>
                  {CALLTYPE_FILTERS.map((s) => (
                    <Chip
                      key={s.key}
                      label={s.label}
                      active={selectedCallType === s.key}
                      onPress={() => setSelectedCallType(s.key)}
                      c={c}
                    />
                  ))}
                </ChipRow>
              </FilterLine>

              {/* 管理员清空操作 */}
              {isAdmin ? (
                <View style={styles.clearRow}>
                  <Button
                    label="清空处理中"
                    onPress={handleClearProcessing}
                    variant="secondary"
                    loading={clearingProcessing}
                    disabled={clearingProcessing}
                    style={styles.clearBtn}
                  />
                  <Button
                    label="清空日志"
                    onPress={handleClear}
                    variant="danger"
                    loading={clearing}
                    disabled={clearing}
                    style={styles.clearBtn}
                  />
                </View>
              ) : null}
            </Card>

            <View style={styles.totalRow}>
              <ShieldAlert size={14} color={c.warning} />
              <Text style={[styles.totalText, { color: c.textSecondary }]}>
                共 {total} 条记录
              </Text>
            </View>
          </View>
        }
        renderItem={({ item }) => {
          const status = STATUS_META[item.processing_status ?? ''];
          const ct = callTypeMeta(item.call_type);
          const engine = engineMeta(item.captcha_engine);
          return (
            <Card style={styles.card}>
              <View style={styles.cardHeader}>
                {item.success ? (
                  <CheckCircle2 size={18} color={c.success} />
                ) : (
                  <XCircle size={18} color={c.error} />
                )}
                <View style={styles.cardHeaderInfo}>
                  <Text
                    style={[styles.cookieId, { color: c.text }]}
                    numberOfLines={1}
                  >
                    {item.cookie_id ?? '未知账号'}
                  </Text>
                  <Text style={[styles.time, { color: c.textMuted }]}>
                    {formatDate(item.created_at)}
                  </Text>
                </View>
                <View style={styles.badges}>
                  {status ? (
                    <Badge label={status.text} variant={status.variant} />
                  ) : null}
                  {ct ? (
                    <Badge label={ct.text} variant={ct.variant} />
                  ) : null}
                  {engine ? (
                    <Badge label={engine.text} variant={engine.variant} />
                  ) : null}
                </View>
              </View>
              {item.message ? (
                <Text
                  style={[styles.message, { color: c.textSecondary }]}
                  numberOfLines={2}
                >
                  {item.message}
                </Text>
              ) : null}
              {item.error_message ? (
                <Text
                  style={[styles.errorMsg, { color: c.error }]}
                  numberOfLines={2}
                >
                  {item.error_message}
                </Text>
              ) : null}
            </Card>
          );
        }}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: c.textMuted }]}>
              暂无风控日志
            </Text>
          </View>
        }
        ListFooterComponent={
          loadingMore ? (
            <View style={styles.footer}>
              <ActivityIndicator color={c.primary} size="small" />
            </View>
          ) : logs.length > 0 && !hasMore ? (
            <View style={styles.footer}>
              <Text style={[styles.footerText, { color: c.textMuted }]}>
                没有更多了
              </Text>
            </View>
          ) : null
        }
        contentContainerStyle={styles.list}
      />

      {/* 账号选择 sheet */}
      <FormModal visible={accountSheet} onClose={() => setAccountSheet(false)} title="选择账号">
        <ScrollView style={styles.sheetScroll}>
          <Pressable
            onPress={() => {
              setSelectedAccount('');
              setAccountSheet(false);
            }}
            style={[
              styles.sheetItem,
              !selectedAccount && { backgroundColor: c.primaryLight },
            ]}
          >
            <Text
              style={[
                styles.sheetItemText,
                { color: !selectedAccount ? c.primary : c.text },
              ]}
            >
              全部账号
            </Text>
          </Pressable>
          {accounts.map((a) => {
            const active = a.id === selectedAccount;
            return (
              <Pressable
                key={a.pk}
                onPress={() => {
                  setSelectedAccount(a.id);
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

      {/* 远程过滑块配置 sheet */}
      <FormModal
        visible={remoteOpen}
        onClose={() => setRemoteOpen(false)}
        title="远程过滑块配置"
      >
        {remoteLoading ? (
          <View style={styles.remoteLoading}>
            <ActivityIndicator color={c.primary} />
          </View>
        ) : remoteCfg ? (
          <ScrollView style={styles.sheetScroll}>
            <View style={styles.remoteHint}>
              <Text style={[styles.remoteHintText, { color: c.textSecondary }]}>
                填写远程服务URL使用远程服务过滑块验证；测试返回 [punish 链接不能为空]
                代表连接成功。
              </Text>
            </View>
            <View style={styles.field}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
                远程服务URL
              </Text>
              <Input
                value={remoteCfg.url}
                onChangeText={(v) =>
                  setRemoteCfg({ ...remoteCfg, url: v })
                }
                placeholder="https://your-host/api/v1/captcha/slider-solve"
                autoCapitalize="none"
                autoCorrect={false}
              />
            </View>
            <View style={styles.field}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
                秘钥
              </Text>
              <Input
                value={remoteCfg.secret_key}
                onChangeText={(v) =>
                  setRemoteCfg({ ...remoteCfg, secret_key: v })
                }
                placeholder="个人设置中的秘钥"
                autoCapitalize="none"
                autoCorrect={false}
              />
            </View>
            <SwitchField
              label="调用远程接口时传递账号 Cookie"
              desc="传递 Cookie 可提高过滑块成功率（链接过期时远程端可凭此自动重取）"
              value={remoteCfg.pass_cookies}
              onValueChange={(v) =>
                setRemoteCfg({ ...remoteCfg, pass_cookies: v })
              }
              colorOff={c.primary}
              c={c}
            />
            <SwitchField
              label="禁止远程调用本机过滑块接口"
              desc="开启后外部调用本机 slider-solve 接口会被直接拒绝"
              value={remoteCfg.block_remote_calls}
              onValueChange={(v) =>
                setRemoteCfg({ ...remoteCfg, block_remote_calls: v })
              }
              colorOff={c.error}
              c={c}
            />
            <View style={styles.numRow}>
              <View style={styles.numField}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
                  处理中上限
                </Text>
                <Input
                  value={String(remoteCfg.remote_processing_max)}
                  onChangeText={(v) =>
                    setRemoteCfg({
                      ...remoteCfg,
                      remote_processing_max: Number(v) || 0,
                    })
                  }
                  keyboardType="numeric"
                />
              </View>
              <View style={styles.numField}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
                  冷却时间(秒)
                </Text>
                <Input
                  value={String(remoteCfg.remote_cooldown_seconds)}
                  onChangeText={(v) =>
                    setRemoteCfg({
                      ...remoteCfg,
                      remote_cooldown_seconds: Number(v) || 0,
                    })
                  }
                  keyboardType="numeric"
                />
              </View>
            </View>
            <View style={styles.remoteActions}>
              <Button
                label="测试"
                onPress={handleTestRemote}
                variant="secondary"
                loading={remoteTesting}
                disabled={remoteTesting}
                style={styles.remoteActionBtn}
              />
              <Button
                label="保存"
                onPress={handleSaveRemote}
                variant="primary"
                loading={remoteSaving}
                disabled={remoteSaving}
                style={styles.remoteActionBtn}
              />
            </View>
          </ScrollView>
        ) : null}
      </FormModal>
    </SafeAreaView>
  );
}

// ---- 子组件（文件内复用，保持页面单文件闭环） ----

function RateCell({
  label,
  value,
  sub,
  color,
  c,
}: {
  label: string;
  value: string;
  sub: string;
  color: string;
  c: (typeof colors)['light'];
}) {
  return (
    <View style={styles.rateCell}>
      <Text style={[styles.rateValue, { color }]}>{value}</Text>
      <Text style={[styles.rateLabel, { color: c.textSecondary }]}>{label}</Text>
      {sub ? (
        <Text style={[styles.rateSub, { color: c.textMuted }]}>{sub}</Text>
      ) : null}
    </View>
  );
}

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

function ChipRow({ children }: { children: React.ReactNode }) {
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

function FilterLine({
  label,
  c,
  children,
}: {
  label: string;
  c: (typeof colors)['light'];
  children: React.ReactNode;
}) {
  return (
    <View style={styles.filterLine}>
      <Text style={[styles.filterLineLabel, { color: c.textMuted }]}>{label}</Text>
      {children}
    </View>
  );
}

function Toggle({
  value,
  onValueChange,
  disabled,
  color,
  trackColorOff,
}: {
  value: boolean;
  onValueChange: (v: boolean) => void;
  disabled?: boolean;
  color: string;
  trackColorOff: string;
}) {
  return (
    <Pressable
      disabled={disabled}
      onPress={() => onValueChange(!value)}
      style={[
        styles.toggleTrack,
        {
          backgroundColor: value ? color : trackColorOff,
          opacity: disabled ? 0.5 : 1,
        },
      ]}
    >
      <View
        style={[
          styles.toggleKnob,
          { transform: [{ translateX: value ? 18 : 2 }] },
        ]}
      />
    </Pressable>
  );
}

function SwitchField({
  label,
  desc,
  value,
  onValueChange,
  colorOff,
  c,
}: {
  label: string;
  desc?: string;
  value: boolean;
  onValueChange: (v: boolean) => void;
  /** 关闭时使用的 on 色（danger 用红，其余用蓝） */
  colorOff: string;
  c: (typeof colors)['light'];
}) {
  return (
    <View style={styles.switchField}>
      <View style={styles.switchFieldText}>
        <Text style={[styles.fieldLabel, { color: c.text }]}>{label}</Text>
        {desc ? (
          <Text style={[styles.switchFieldDesc, { color: c.textMuted }]}>
            {desc}
          </Text>
        ) : null}
      </View>
      <Toggle
        value={value}
        onValueChange={onValueChange}
        color={colorOff}
        trackColorOff={c.borderLight}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  list: { padding: spacing.lg, gap: spacing.md },
  headerBlock: { gap: spacing.md, marginBottom: spacing.sm },
  configCard: { gap: spacing.sm, padding: spacing.md },
  configRow: { gap: spacing.sm },
  configTitleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  configTitle: { ...typography.caption, fontWeight: '600' },
  localSwitchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  localSwitchLabel: { ...typography.caption },
  remoteEntry: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.xs,
  },
  remoteEntryText: { ...typography.caption, fontWeight: '500' },
  rateCard: { paddingVertical: spacing.md },
  rateRow: { flexDirection: 'row', alignItems: 'center' },
  rateCell: { flex: 1, alignItems: 'center', gap: 2 },
  rateValue: { fontSize: 18, fontWeight: '700' },
  rateLabel: { ...typography.small },
  rateSub: { fontSize: 10 },
  rateDivider: { width: 1, height: 28 },
  filterCard: { gap: spacing.sm, padding: spacing.md },
  filterRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
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
  chipRow: { gap: spacing.xs, paddingVertical: 2 },
  chip: {
    paddingHorizontal: spacing.md,
    height: 28,
    borderRadius: radius.full,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipText: { fontSize: 12, fontWeight: '500' },
  filterLine: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  filterLineLabel: { ...typography.small, width: 32 },
  clearRow: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xs },
  clearBtn: { flex: 1, minHeight: 40 },
  totalRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.xs,
  },
  totalText: { ...typography.small },
  card: { gap: spacing.sm, padding: spacing.md },
  cardHeader: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  cardHeaderInfo: { flex: 1, gap: 2 },
  cookieId: { ...typography.caption, fontWeight: '600' },
  time: { ...typography.small },
  badges: { flexDirection: 'row', gap: spacing.xs, flexShrink: 1 },
  message: { ...typography.caption },
  errorMsg: { ...typography.small },
  footer: { paddingVertical: spacing.lg, alignItems: 'center' },
  footerText: { ...typography.small },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  sheetScroll: { maxHeight: 460 },
  sheetItem: {
    paddingVertical: spacing.md,
    paddingHorizontal: spacing.md,
    borderRadius: radius.sm,
  },
  sheetItemText: { ...typography.body },
  remoteLoading: { paddingVertical: spacing.xxl, alignItems: 'center' },
  remoteHint: {
    padding: spacing.md,
    borderRadius: radius.md,
    backgroundColor: 'rgba(59,130,246,0.08)',
  },
  remoteHintText: { ...typography.small },
  field: { gap: spacing.xs },
  fieldLabel: { ...typography.small },
  switchField: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
  },
  switchFieldText: { flex: 1, gap: 2 },
  switchFieldDesc: { fontSize: 11 },
  numRow: { flexDirection: 'row', gap: spacing.md },
  numField: { flex: 1, gap: spacing.xs },
  remoteActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm },
  remoteActionBtn: { flex: 1, minHeight: 44 },
  toggleTrack: { width: 40, height: 24, borderRadius: 12, justifyContent: 'center' },
  toggleKnob: {
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: '#FFFFFF',
  },
});
