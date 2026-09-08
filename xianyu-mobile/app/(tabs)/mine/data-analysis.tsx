import { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  RefreshControl,
  Alert,
  TextInput,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { ChevronRight, ChevronDown } from 'lucide-react-native';
import { Card, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getBrowseSummary,
  getSellerSummary,
  type AnalysisSummary,
  type DistributionItem,
  type BannerDataItem,
} from '@/api/wrappers/dashboard';
import { useAccountsStore } from '@/stores/accounts';

type RangeKey = 'today' | '7d' | '30d' | 'custom';

const RANGE_PRESETS: { key: RangeKey; label: string }[] = [
  { key: 'today', label: '今天' },
  { key: '7d', label: '近7天' },
  { key: '30d', label: '近30天' },
  { key: 'custom', label: '自定义' },
];

/** 核心指标卡配置（对齐 web CORE_METRICS，2×5 网格） */
const CORE_METRICS = [
  { name: 'vstPv', label: '商品访问次数' },
  { name: 'vstUv', label: '商品访问人数' },
  { name: 'showPv', label: '商品曝光次数' },
  { name: 'showUv', label: '商品曝光人数' },
  { name: 'ipv', label: '商品浏览次数' },
  { name: 'ipvUv', label: '商品浏览人数' },
  { name: 'payOrdCnt', label: '支付笔数' },
  { name: 'payAmt', label: '支付金额(元)' },
  { name: 'rfdOrdCnt', label: '发起退款笔数' },
  { name: 'rfdAmt', label: '发起退款金额(元)' },
] as const;

/** 金额类指标：值前加 ¥ 前缀（对齐 web 行为） */
const AMOUNT_METRICS = new Set<string>(['payAmt', 'rfdAmt']);

/** YYYY-MM-DD 格式化 */
function formatDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

/** HH:mm 格式化 */
function formatTime(d: Date): string {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** 根据预设计算起止日期（YYYY-MM-DD） */
function rangeDates(range: RangeKey): { start: string; end: string } {
  const end = new Date();
  const start = new Date();
  if (range === '7d') start.setDate(start.getDate() - 6);
  else if (range === '30d') start.setDate(start.getDate() - 29);
  return { start: formatDate(start), end: formatDate(end) };
}

/** 校验 YYYY-MM-DD 是否为合法日历日期 */
function isValidDate(s: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) return false;
  const d = new Date(`${s}T00:00:00`);
  return Number.isFinite(d.getTime());
}

/** 输入框自动格式化为 YYYY-MM-DD（只取前 8 位数字，补 dash） */
function normalizeDateInput(s: string): string {
  const d = s.replace(/\D/g, '').slice(0, 8);
  if (d.length <= 4) return d;
  if (d.length <= 6) return `${d.slice(0, 4)}-${d.slice(4)}`;
  return `${d.slice(0, 4)}-${d.slice(4, 6)}-${d.slice(6)}`;
}

/** 接口字段名 → 中文业务文案（避免向用户裸露 JSON key）。
 *  指标部分对齐 web METRIC_NAME_MAP（30+ 项）。 */
const FIELD_LABELS: Record<string, string> = {
  // 分布数组与包装结构
  buyerActiveList: '买家活跃时段',
  buyerProvinceList: '买家地域分布',
  itemCateList: '商品类目分布',
  sceneSourceList: '流量来源场景',
  graphBannerBenchData: '横幅基准数据',
  bannerDataList: '横幅列表',
  graphDataList: '图表数据点',
  // 分布单项字段
  profileCode: '维度编码',
  profileVal: '维度值',
  usrRatio: '用户占比',
  usrRatioFormat: '用户占比(格式化)',
  // 横幅指标项字段
  name: '指标名',
  dataStr: '指标值',
  ratio: '同比环比',
  ratioFormat: '涨跌幅',
  lastDataStr: '上期值',
  cycle: '对比周期',
  ds: '日期',
  // 卖家数据罗盘指标（对齐 web METRIC_NAME_MAP）
  payAmt: '支付金额(元)',
  fstByrPayAmt: '首次买家支付金额',
  rptByrPayAmt: '复购买家支付金额',
  payOrdCnt: '支付笔数',
  aov: '客单价(元)',
  rfdAmt: '退款金额(元)',
  showUv: '商品曝光人数',
  showPv: '商品曝光次数',
  ipvUv: '商品浏览人数',
  ipv: '商品浏览次数',
  payByrCnt: '支付买家数',
  vstPv: '商品访问次数',
  vstUv: '商品访问人数',
  showItmCnt: '曝光商品数',
  ipvItmCnt: '访问商品数',
  stItmCnt: '成交商品数',
  uctr: '访问转化率',
  onlCnt: '在架商品数',
  chatUv: '咨询人数',
  rptOrdCnt: '复购订单数',
  rptByrCnt: '复购买家数',
  rpr: '复购率',
  rep3minUvRate: '3分钟回复率',
  showPvCmpPctl: '曝光竞争力',
  payOrdCntCmpPctl: '成交竞争力',
  rfdOrdCnt: '退款笔数',
  addRecItemCnt: '加入推荐商品数',
  priceCutItmCnt: '降价商品数',
  favCnt: '收藏数',
  newItmCnt: '新发商品数',
  cmtItmCnt: '评价商品数',
};

interface StatRow {
  label: string;
  value: string;
}

interface MetricRow {
  label: string;
  value: string;
  ratio?: string;
  ratioTone?: 'up' | 'down' | 'flat';
}

/** 交给条形图渲染的分布数组字段（不在 flattenStats 里压成"N 项"） */
const DISTRIBUTION_FIELDS = [
  'buyerActiveList',
  'buyerProvinceList',
  'itemCateList',
  'sceneSourceList',
] as const;

/** flattenStats 跳过的键：分布数组（交条形图）+ 横幅/趋势包装（已由核心指标卡呈现） */
const FLATTEN_SKIP = new Set<string>([
  ...DISTRIBUTION_FIELDS,
  'graphBannerBenchData',
  'bannerDataList',
  'graphDataList',
]);

interface DistributionGroup {
  key: string;
  label: string;
  items: DistributionItem[];
}

/** 将统计对象扁平化为 {label, value} 行（递归2层，避免 [object Object]）；
 *  分布数组与横幅/趋势包装交由专门组件渲染，此处跳过。 */
function flattenStats(obj: Record<string, unknown>, prefix = ''): StatRow[] {
  const rows: StatRow[] = [];
  for (const [k, v] of Object.entries(obj)) {
    if (v == null) continue;
    if (FLATTEN_SKIP.has(k)) continue;
    const rawLabel = prefix ? `${prefix} · ${k}` : k;
    const label = FIELD_LABELS[k]
      ? prefix
        ? `${prefix} · ${FIELD_LABELS[k]}`
        : FIELD_LABELS[k]
      : rawLabel;
    if (Array.isArray(v)) {
      rows.push({ label, value: `${v.length} 项` });
    } else if (typeof v === 'object') {
      rows.push(...flattenStats(v as Record<string, unknown>, label));
    } else {
      rows.push({ label, value: String(v) });
    }
  }
  return rows;
}

/** 从概要对象抽取分布数组（wrapper 已归一化为 DistributionItem[]） */
function extractDistributions(obj: AnalysisSummary): DistributionGroup[] {
  const groups: DistributionGroup[] = [];
  for (const k of DISTRIBUTION_FIELDS) {
    const v = obj[k];
    if (v && v.length > 0) {
      groups.push({ key: k, label: FIELD_LABELS[k] ?? k, items: v });
    }
  }
  return groups;
}

/** 组内最大占比：最大条撑满，其余按比例缩短 */
function groupMaxRatio(items: DistributionItem[]): number {
  let m = 0;
  for (const it of items) if (it.usrRatio > m) m = it.usrRatio;
  return m;
}

/** 横幅指标列表 → name→item 映射，供核心指标卡按字段名取值 */
function bannerMap(list?: BannerDataItem[]): Record<string, BannerDataItem> {
  const m: Record<string, BannerDataItem> = {};
  if (list) for (const it of list) if (it.name) m[it.name] = it;
  return m;
}

/** 将数组按每行 2 个切分，供 2 列网格渲染 */
function pairs<T>(arr: T[]): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < arr.length; i += 2) out.push(arr.slice(i, i + 2));
  return out;
}

interface Section {
  title: string;
  subtitle?: string;
  metrics: MetricRow[];
  scalars: StatRow[];
  distributions: DistributionGroup[];
}

/** 紧凑核心指标卡：标签 + 大数值 + 涨跌幅，蓝白主题，用于 2×5 网格 */
function MetricCard({
  label,
  value,
  ratio,
  ratioTone,
}: {
  label: string;
  value: string;
  ratio?: string;
  ratioTone?: 'up' | 'down' | 'flat';
}) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const tone =
    ratioTone === 'up'
      ? c.success
      : ratioTone === 'down'
        ? c.error
        : c.textMuted;
  return (
    <View
      style={[
        mStyles.card,
        { backgroundColor: c.surface, borderColor: c.border },
      ]}
    >
      <Text style={[mStyles.label, { color: c.textMuted }]} numberOfLines={2}>
        {label}
      </Text>
      <Text style={[mStyles.value, { color: c.primary }]} numberOfLines={1}>
        {value}
      </Text>
      {ratio ? (
        <Text style={[mStyles.ratio, { color: tone }]} numberOfLines={1}>
          {ratio}
        </Text>
      ) : null}
    </View>
  );
}

const mStyles = StyleSheet.create({
  card: { flex: 1, borderRadius: radius.md, padding: spacing.sm, borderWidth: 1 },
  label: { ...typography.small, marginBottom: 2 },
  value: { fontSize: 16, fontWeight: '700' },
  ratio: { ...typography.micro, marginTop: 2 },
});

export default function DataAnalysisScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const accounts = useAccountsStore((s) => s.options);
  const loadAccountOptions = useAccountsStore((s) => s.load);
  const [selectedPk, setSelectedPk] = useState('');
  const [range, setRange] = useState<RangeKey>('today');
  const [customStart, setCustomStart] = useState('');
  const [customEnd, setCustomEnd] = useState('');
  const [browse, setBrowse] = useState<AnalysisSummary>({});
  const [seller, setSeller] = useState<AnalysisSummary>({});
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  // 最近一次 loadData 成功完成时间，供顶部"更新于 HH:mm"展示
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  // 请求序号：快速切换账号 A→B 时丢弃 A 的过期响应，避免旧统计覆盖新账号数据
  const dataSeqRef = useRef(0);

  // 加载账号列表，首次加载时设置默认选中；force=true 用于下拉刷新绕过 60s TTL
  const loadAccounts = useCallback(async (force = false) => {
    await loadAccountOptions(force);
    const accs = useAccountsStore.getState().options;
    if (!selectedPk && accs.length > 0) {
      const defaultAcc = accs.find((a) => a.enabled) ?? accs[0];
      setSelectedPk(String(defaultAcc.pk));
    }
  }, [selectedPk, loadAccountOptions]);

  // 加载统计数据（账号 + 时间范围确定后调用）
  const loadData = useCallback(async () => {
    if (!selectedPk) {
      setLoading(false);
      return;
    }
    let start: string;
    let end: string;
    if (range === 'custom') {
      // 自定义日期需手动点"查询"触发；此处校验通过后才发请求
      if (!isValidDate(customStart) || !isValidDate(customEnd)) {
        setLoading(false);
        setRefreshing(false);
        return;
      }
      if (customStart > customEnd) {
        Alert.alert('日期无效', '开始日期不能晚于结束日期');
        setRefreshing(false);
        setLoading(false);
        return;
      }
      start = customStart;
      end = customEnd;
    } else {
      ({ start, end } = rangeDates(range));
    }
    const seq = ++dataSeqRef.current;
    setRefreshing(true);
    try {
      const [browseData, sellerData] = await Promise.all([
        getBrowseSummary(selectedPk, start, end),
        getSellerSummary(selectedPk, start, end),
      ]);
      if (dataSeqRef.current !== seq) return; // 已切到别的账号，丢弃本次响应
      setBrowse(browseData);
      setSeller(sellerData);
      setUpdatedAt(new Date());
    } catch (e) {
      if (dataSeqRef.current === seq) {
        console.error('加载数据分析失败', e);
        Alert.alert('加载失败', (e as Error).message);
      }
    } finally {
      if (dataSeqRef.current === seq) {
        setLoading(false);
        setRefreshing(false);
      }
    }
  }, [selectedPk, range, customStart, customEnd]);

  // 首次加载账号
  useEffect(() => {
    loadAccounts().catch((e) => {
      console.error('加载账号失败', e);
      Alert.alert('加载失败', (e as Error).message);
      setLoading(false);
    });
  }, [loadAccounts]);

  // 账号或预设时间范围变化时重新加载统计数据；
  // 自定义日期需手动点"查询"（对齐 web），切换到此模式时不自动触发。
  useEffect(() => {
    if (!selectedPk) {
      setLoading(false);
      return;
    }
    if (range === 'custom') {
      setLoading(false);
      return;
    }
    loadData();
  }, [selectedPk, range, loadData]);

  // 下拉刷新：账号（强制）+ 数据一起刷新
  const refresh = useCallback(async () => {
    await loadAccounts(true);
    if (selectedPk) await loadData();
  }, [loadAccounts, loadData, selectedPk]);

  function selectAccount(pk: number) {
    setSelectedPk(String(pk));
  }

  function selectRange(r: RangeKey) {
    // 首次进入自定义时预填近 7 天，便于直接查询
    if (r === 'custom' && !customStart && !customEnd) {
      const { start, end } = rangeDates('7d');
      setCustomStart(start);
      setCustomEnd(end);
    }
    setRange(r);
  }

  if (loading) {
    return (
      <SafeAreaView
        style={[styles.container, { backgroundColor: c.background }]}
        edges={['left', 'right', 'bottom']}
      >
        <Loading label="加载数据..." />
      </SafeAreaView>
    );
  }

  // 核心指标行：按 CORE_METRICS 字段名从横幅列表取值
  const bMap = bannerMap(seller.bannerDataList);
  const hasBanner = !!seller.bannerDataList && seller.bannerDataList.length > 0;
  const coreMetricRows: MetricRow[] = hasBanner
    ? CORE_METRICS.map((m) => {
        const item = bMap[m.name];
        const raw = item?.dataStr;
        const value = raw
          ? AMOUNT_METRICS.has(m.name)
            ? `¥${raw}`
            : raw
          : '--';
        let ratio: string | undefined;
        let ratioTone: MetricRow['ratioTone'] | undefined;
        if (item && item.ratioFormat && item.ratioFormat !== '-') {
          ratio = item.ratioFormat;
          const r = item.ratio ?? 0;
          ratioTone = r > 0 ? 'up' : r < 0 ? 'down' : 'flat';
        }
        return { label: m.label, value, ratio, ratioTone };
      })
    : [];

  const sections: Section[] = [
    {
      title: '浏览概要',
      subtitle: '流量分布',
      metrics: [],
      scalars: flattenStats(browse).filter((r) => !r.label.startsWith('_')),
      distributions: extractDistributions(browse),
    },
    ...(hasBanner
      ? [
          {
            title: '核心指标',
            subtitle: '数据罗盘',
            metrics: coreMetricRows,
            scalars: [] as StatRow[],
            distributions: [] as DistributionGroup[],
          },
        ]
      : []),
    {
      title: '卖家明细',
      subtitle: '数据罗盘',
      metrics: [],
      scalars: flattenStats(seller).filter((r) => !r.label.startsWith('_')),
      distributions: extractDistributions(seller),
    },
  ].filter(
    (s) =>
      s.metrics.length > 0 || s.scalars.length > 0 || s.distributions.length > 0,
  );

  const customReady =
    isValidDate(customStart) && isValidDate(customEnd) && customStart <= customEnd;

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: c.background }]}
      edges={['left', 'right', 'bottom']}
    >
      <View style={styles.metaRow}>
        <Text style={[styles.metaText, { color: c.textMuted }]}>
          更新于 {updatedAt ? formatTime(updatedAt) : '--:--'}
        </Text>
      </View>

      {/* 账号选择器 */}
      {accounts.length > 0 && (
        <FlatList
          horizontal
          style={styles.chipScroll}
          data={accounts}
          keyExtractor={(item) => String(item.pk)}
          renderItem={({ item }) => {
            const active = selectedPk === String(item.pk);
            return (
              <Pressable
                onPress={() => selectAccount(item.pk)}
                style={[
                  styles.chip,
                  {
                    backgroundColor: active ? c.primary : c.surface,
                    borderColor: active ? c.primary : c.border,
                  },
                ]}
              >
                <Text
                  style={[styles.chipText, { color: active ? '#FFF' : c.text }]}
                  numberOfLines={1}
                >
                  {item.remark || item.id}
                </Text>
                <ChevronDown size={12} stroke={active ? '#FFFFFF' : c.textMuted} />
              </Pressable>
            );
          }}
          contentContainerStyle={styles.chipList}
          showsHorizontalScrollIndicator={false}
        />
      )}

      {/* 时间范围预设 */}
      <View style={styles.rangeRow}>
        {RANGE_PRESETS.map((r) => {
          const active = range === r.key;
          return (
            <Pressable
              key={r.key}
              onPress={() => selectRange(r.key)}
              style={[
                styles.rangeBtn,
                {
                  backgroundColor: active ? c.primary : c.surface,
                  borderColor: active ? c.primary : c.border,
                },
              ]}
            >
              <Text
                style={{ color: active ? '#FFF' : c.text, ...typography.caption }}
              >
                {r.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {/* 自定义日期范围：选"自定义"时展开起止日期输入 + 查询按钮 */}
      {range === 'custom' && (
        <View style={styles.customRow}>
          <TextInput
            value={customStart}
            onChangeText={(t) => setCustomStart(normalizeDateInput(t))}
            placeholder="开始 YYYY-MM-DD"
            placeholderTextColor={c.textMuted}
            keyboardType="number-pad"
            maxLength={10}
            style={[
              styles.dateInput,
              {
                backgroundColor: c.surface,
                color: c.text,
                borderColor: c.border,
              },
            ]}
          />
          <Text style={[styles.dash, { color: c.textMuted }]}>至</Text>
          <TextInput
            value={customEnd}
            onChangeText={(t) => setCustomEnd(normalizeDateInput(t))}
            placeholder="结束 YYYY-MM-DD"
            placeholderTextColor={c.textMuted}
            keyboardType="number-pad"
            maxLength={10}
            style={[
              styles.dateInput,
              {
                backgroundColor: c.surface,
                color: c.text,
                borderColor: c.border,
              },
            ]}
          />
          <Pressable
            onPress={loadData}
            disabled={refreshing || !customReady}
            style={[
              styles.queryBtn,
              {
                backgroundColor: customReady ? c.primary : c.surfaceAlt,
                borderColor: customReady ? c.primary : c.border,
                opacity: refreshing || !customReady ? 0.6 : 1,
              },
            ]}
          >
            <Text style={styles.queryBtnText}>查询</Text>
          </Pressable>
        </View>
      )}

      <FlatList
        data={sections}
        keyExtractor={(item) => item.title}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
        renderItem={({ item }) => (
          <View>
            <View style={styles.sectionHeader}>
              <Text style={[styles.sectionTitle, { color: c.text }]}>
                {item.title}
              </Text>
              {item.subtitle ? (
                <Text style={[styles.sectionSubtitle, { color: c.textMuted }]}>
                  {item.subtitle}
                </Text>
              ) : null}
            </View>

            {item.metrics.length === 0 &&
            item.scalars.length === 0 &&
            item.distributions.length === 0 ? (
              <Card style={[styles.sectionCard, { borderColor: c.border }]}>
                <Text style={[styles.emptyInline, { color: c.textMuted }]}>
                  暂无数据
                </Text>
              </Card>
            ) : (
              <>
                {/* 核心指标 2×5 网格 */}
                {item.metrics.length > 0 && (
                  <View style={styles.grid}>
                    {pairs(item.metrics).map((row, ri) => (
                      <View key={`m-${ri}`} style={styles.gridRow}>
                        {row.map((m, ci) => (
                          <MetricCard
                            key={`mc-${ri}-${ci}`}
                            label={m.label}
                            value={m.value}
                            ratio={m.ratio}
                            ratioTone={m.ratioTone}
                          />
                        ))}
                        {row.length === 1 && <View style={styles.gridSpacer} />}
                      </View>
                    ))}
                  </View>
                )}

                {item.scalars.length > 0 && (
                  <Card style={[styles.sectionCard, { borderColor: c.border }]}>
                    {item.scalars.map((row, idx) => (
                      <View
                        key={`s-${row.label}-${idx}`}
                        style={[
                          styles.statRow,
                          idx > 0 && { borderTopColor: c.border, borderTopWidth: 1 },
                        ]}
                      >
                        <Text
                          style={[styles.statKey, { color: c.textSecondary }]}
                          numberOfLines={2}
                        >
                          {row.label}
                        </Text>
                        <Text
                          style={[styles.statVal, { color: c.primary }]}
                          numberOfLines={1}
                        >
                          {row.value}
                        </Text>
                        <ChevronRight size={16} stroke={c.textMuted} />
                      </View>
                    ))}
                  </Card>
                )}

                {item.distributions.map((group) => {
                  const maxRatio = groupMaxRatio(group.items);
                  return (
                    <Card
                      key={`d-${group.key}`}
                      style={[styles.distCard, { borderColor: c.border }]}
                    >
                      <Text style={[styles.distTitle, { color: c.text }]}>
                        {group.label}
                      </Text>
                      {group.items.map((bar, idx) => {
                        const widthPct =
                          maxRatio > 0 ? (bar.usrRatio / maxRatio) * 100 : 0;
                        return (
                          <View
                            key={`${bar.profileCode}-${idx}`}
                            style={styles.barRow}
                          >
                            <Text
                              style={[styles.barLabel, { color: c.textSecondary }]}
                              numberOfLines={1}
                              ellipsizeMode="tail"
                            >
                              {bar.profileVal}
                            </Text>
                            <View
                              style={[
                                styles.barTrack,
                                { backgroundColor: c.surfaceAlt },
                              ]}
                            >
                              <View
                                style={[
                                  styles.barFill,
                                  {
                                    width: `${widthPct}%`,
                                    backgroundColor: c.primary,
                                  },
                                ]}
                              />
                            </View>
                            <Text
                              style={[styles.barVal, { color: c.primary }]}
                              numberOfLines={1}
                            >
                              {bar.usrRatioFormat || `${bar.usrRatio.toFixed(1)}%`}
                            </Text>
                          </View>
                        );
                      })}
                    </Card>
                  );
                })}
              </>
            )}
          </View>
        )}
        ListEmptyComponent={
          accounts.length === 0 ? (
            <View style={styles.empty}>
              <Text style={[styles.emptyText, { color: c.textMuted }]}>
                暂无账号，请先在账号管理中添加
              </Text>
            </View>
          ) : null
        }
        contentContainerStyle={styles.list}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  chipList: {
    paddingHorizontal: spacing.lg,
    gap: spacing.sm,
    paddingBottom: spacing.sm,
    alignItems: 'center',
  },
  // 横向列表必须给显式高度：默认 flexGrow:1 会撑满整屏；仅 flexGrow:0 时安卓初始测量会把文字压扁
  chipScroll: { flexGrow: 0, minHeight: 54 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.xl,
    borderWidth: 1,
  },
  chipText: { ...typography.caption, maxWidth: 120 },
  rangeRow: {
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },
  rangeBtn: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  // 自定义日期行
  customRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },
  dateInput: {
    flex: 1,
    minHeight: 38,
    borderRadius: radius.sm,
    borderWidth: 1,
    paddingHorizontal: spacing.sm,
    ...typography.caption,
  },
  dash: { ...typography.small },
  queryBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  queryBtnText: {
    color: '#FFFFFF',
    ...typography.caption,
    fontWeight: '600',
  },
  // 核心指标 2 列网格
  grid: {
    gap: spacing.sm,
    paddingBottom: spacing.sm,
  },
  gridRow: {
    flexDirection: 'row',
    gap: spacing.sm,
  },
  gridSpacer: { flex: 1 },
  // 底部留白避让 tab 栏，避免最后一张卡片被遮挡
  list: { padding: spacing.lg, gap: spacing.md, paddingBottom: 80 },
  sectionHeader: { marginBottom: spacing.sm, gap: spacing.xs },
  sectionTitle: { ...typography.heading },
  sectionSubtitle: { ...typography.small },
  sectionCard: { padding: 0, overflow: 'hidden', borderWidth: 1 },
  statRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: spacing.md,
  },
  statKey: { ...typography.caption, flex: 1 },
  statVal: { ...typography.body, fontWeight: '600', maxWidth: '40%' },
  // 分布条形图（纯 View 实现，无第三方图表库）
  distCard: { padding: spacing.md, gap: spacing.xs },
  distTitle: { ...typography.caption, fontWeight: '600', marginBottom: spacing.xs },
  barRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
  },
  barLabel: { ...typography.small, width: 80 },
  barTrack: {
    flex: 1,
    height: 8,
    borderRadius: radius.full,
    overflow: 'hidden',
  },
  barFill: { height: '100%' },
  barVal: {
    ...typography.small,
    width: 48,
    textAlign: 'right',
    fontWeight: '600',
  },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
  },
  metaText: { ...typography.small },
  emptyInline: { ...typography.caption, padding: spacing.lg, textAlign: 'center' },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
});
