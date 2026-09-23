import { useState, useCallback, useEffect, useRef, useLayoutEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  Alert,
  AppState,
  Image,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { useNavigation, useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { Card, Button, Input, EmptyState, Badge, Loading } from '@/components/ui';
import { Sparkles, X, Plus } from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  createAiListingTask,
  getAiListingTask,
  cancelAiListingTask,
  getAiListingConfigs,
  type AiListingConfig,
  type AiListingTaskParams,
  type AiListingTaskDetail,
} from '@/api/wrappers/ai-listing';
import { uploadProductImages } from '@/api/wrappers/product-publish';

const POLL_INTERVAL = 3000;

const CONDITION_OPTIONS = ['全新', '几乎全新', '轻微', '明显', '重度'];
type ShippingMethod = NonNullable<AiListingTaskParams['material_defaults']['shipping_method']>;
const SHIPPING_OPTIONS: Array<{ value: ShippingMethod; label: string }> = [
  { value: 'free', label: '包邮' },
  { value: 'distance', label: '按距离' },
  { value: 'fixed', label: '固定运费' },
  { value: 'template', label: '运费模板' },
  { value: 'none', label: '不包邮' },
];

type BadgeVariant = 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'gray';

/** 任务状态 → Badge 配色 + 文案 */
function taskBadge(status: AiListingTaskDetail['status']): { variant: BadgeVariant; label: string } {
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

export default function AiListingScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();
  const navigation = useNavigation();

  useLayoutEffect(() => {
    navigation.setOptions({ title: 'AI 上架' });
  }, [navigation]);

  const [configs, setConfigs] = useState<AiListingConfig[]>([]);
  const [configsLoading, setConfigsLoading] = useState(true);
  const [selectedConfigId, setSelectedConfigId] = useState<number | null>(null);

  const [keyword, setKeyword] = useState('');
  const [countText, setCountText] = useState('5');
  const [priceMode, setPriceMode] = useState<'fixed' | 'range'>('fixed');
  const [priceText, setPriceText] = useState('');
  const [priceMinText, setPriceMinText] = useState('');
  const [priceMaxText, setPriceMaxText] = useState('');

  const [materialExpanded, setMaterialExpanded] = useState(false);
  const [condition, setCondition] = useState('全新');
  const [brand, setBrand] = useState('');
  const [quantityText, setQuantityText] = useState('1');
  const [shippingMethod, setShippingMethod] = useState<ShippingMethod>('free');
  const [postageText, setPostageText] = useState('');
  const [fallbackImages, setFallbackImages] = useState<string[]>([]);

  const [creating, setCreating] = useState(false);
  const [currentTask, setCurrentTask] = useState<AiListingTaskDetail | null>(null);
  const [taskActionLoading, setTaskActionLoading] = useState(false);

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const activeTaskIdRef = useRef<string | null>(null);

  const loadConfigs = useCallback(async () => {
    setConfigsLoading(true);
    try {
      const resp = await getAiListingConfigs(1, 50);
      setConfigs(resp.list);
      setSelectedConfigId((prev) => prev ?? resp.list[0]?.id ?? null);
    } catch (e) {
      Alert.alert('加载配置失败', (e as Error).message);
    } finally {
      setConfigsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadConfigs();
  }, [loadConfigs]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const fetchTask = useCallback(
    async (taskId: string) => {
      try {
        const detail = await getAiListingTask(taskId);
        setCurrentTask(detail);
        if (detail.finished) {
          stopPolling();
          activeTaskIdRef.current = null;
        }
      } catch (e) {
        // 轮询失败先停掉，避免错误刷屏；任务卡片仍保留最后一次状态
        stopPolling();
        Alert.alert('同步任务状态失败', (e as Error).message);
      }
    },
    [stopPolling],
  );

  const startPolling = useCallback(
    (taskId: string) => {
      stopPolling();
      activeTaskIdRef.current = taskId;
      pollRef.current = setInterval(() => {
        fetchTask(taskId);
      }, POLL_INTERVAL);
    },
    [stopPolling, fetchTask],
  );

  // 卸载时清理轮询
  useEffect(() => () => stopPolling(), [stopPolling]);

  // AppState：后台暂停轮询，回到前台若有未完成任务则立即同步并续上
  useEffect(() => {
    const sub = AppState.addEventListener('change', (state) => {
      const tid = activeTaskIdRef.current;
      if (state === 'active') {
        if (tid) {
          fetchTask(tid);
          startPolling(tid);
        }
      } else {
        stopPolling();
      }
    });
    return () => sub.remove();
  }, [fetchTask, startPolling, stopPolling]);

  const selectedConfig = configs.find((cfg) => cfg.id === selectedConfigId) ?? null;

  /** 选择 1~9 张兜底图片（本地 uri），重复 uri 自动去重 */
  const handlePickImages = useCallback(async () => {
    if (fallbackImages.length >= 9) return;
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsMultipleSelection: true,
      allowsEditing: false,
      quality: 0.8,
      selectionLimit: 9 - fallbackImages.length,
    });
    if (result.canceled || !result.assets || result.assets.length === 0) return;
    const newUris = result.assets.map((a) => a.uri).filter(Boolean);
    setFallbackImages((prev) => {
      const existing = new Set(prev);
      const added = newUris.filter((u) => !existing.has(u));
      return [...prev, ...added].slice(0, 9);
    });
  }, [fallbackImages.length]);

  const handleStart = useCallback(async () => {
    if (!selectedConfig) {
      Alert.alert('提示', '请选择 AI 配置');
      return;
    }
    const kw = keyword.trim();
    if (!kw) {
      Alert.alert('提示', '请输入生成主题');
      return;
    }
    const countNum = Number(countText);
    const count = Math.floor(countNum);
    if (!Number.isFinite(countNum) || count < 1 || count > 50) {
      Alert.alert('提示', '条数需为 1~50 的整数');
      return;
    }
    let price: number | undefined;
    let priceMin: number | undefined;
    let priceMax: number | undefined;
    if (priceMode === 'fixed') {
      const v = Number(priceText);
      if (!priceText.trim() || !Number.isFinite(v) || v < 0) {
        Alert.alert('提示', '请输入正确的价格');
        return;
      }
      price = v;
    } else {
      const lo = Number(priceMinText);
      const hi = Number(priceMaxText);
      if (!priceMinText.trim() || !Number.isFinite(lo) || lo < 0) {
        Alert.alert('提示', '请输入正确的最低价');
        return;
      }
      if (!priceMaxText.trim() || !Number.isFinite(hi) || hi < 0) {
        Alert.alert('提示', '请输入正确的最高价');
        return;
      }
      if (lo > hi) {
        Alert.alert('提示', '最低价不能高于最高价');
        return;
      }
      priceMin = lo;
      priceMax = hi;
    }
    const qtyNum = Number(quantityText);
    const qty = Math.floor(qtyNum);
    if (!Number.isFinite(qtyNum) || qty < 1) {
      Alert.alert('提示', '数量需为不小于 1 的整数');
      return;
    }
    let postage: number | undefined;
    if (shippingMethod === 'fixed' && postageText.trim()) {
      const v = Number(postageText);
      if (!Number.isFinite(v) || v < 0) {
        Alert.alert('提示', '请输入正确的运费金额');
        return;
      }
      postage = v;
    }

    // 兜底图片：未启用 AI 配图时必须至少 1 张
    if (!selectedConfig.image_enabled && fallbackImages.length === 0) {
      Alert.alert('提示', '当前配置未启用 AI 配图，请至少上传 1 张兜底图片');
      return;
    }

    setCreating(true);
    try {
      // 上传兜底图片，取 url 填入 material_defaults.images（与 web 一致）
      let images: string[] = [];
      if (fallbackImages.length > 0) {
        try {
          const up = await uploadProductImages(fallbackImages);
          images = up.urls;
        } catch (e) {
          Alert.alert('图片上传失败', (e as Error).message);
          return;
        }
      }

      const params: AiListingTaskParams = {
        config_id: selectedConfig.id,
        keyword: kw,
        count,
        price_mode: priceMode,
        material_defaults: {
          condition,
          brand: brand.trim() || undefined,
          quantity: qty,
          shipping_method: shippingMethod,
          postage,
          images,
        },
      };
      if (priceMode === 'fixed') {
        params.price = price;
      } else {
        params.price_min = priceMin;
        params.price_max = priceMax;
      }
      if (selectedConfig.image_enabled) params.image_enabled = true;

      const { task_id } = await createAiListingTask(params);
      const detail = await getAiListingTask(task_id);
      setCurrentTask(detail);
      if (!detail.finished) startPolling(task_id);
      else activeTaskIdRef.current = null;
    } catch (e) {
      Alert.alert('创建失败', (e as Error).message);
    } finally {
      setCreating(false);
    }
  }, [
    selectedConfig,
    keyword,
    countText,
    priceMode,
    priceText,
    priceMinText,
    priceMaxText,
    quantityText,
    shippingMethod,
    postageText,
    condition,
    brand,
    fallbackImages,
    startPolling,
  ]);

  const handleCancel = useCallback(async () => {
    if (!currentTask) return;
    setTaskActionLoading(true);
    try {
      await cancelAiListingTask(currentTask.task_id);
      await fetchTask(currentTask.task_id);
    } catch (e) {
      Alert.alert('取消失败', (e as Error).message);
    } finally {
      setTaskActionLoading(false);
    }
  }, [currentTask, fetchTask]);

  const handleClear = useCallback(() => {
    stopPolling();
    activeTaskIdRef.current = null;
    setCurrentTask(null);
  }, [stopPolling]);

  if (configsLoading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载配置..." />
      </SafeAreaView>
    );
  }

  if (configs.length === 0) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <EmptyState
          icon={Sparkles}
          title="暂无 AI 配置"
          message="请先在配置管理新建配置后再生成上架任务"
          actionLabel="去新建配置"
          onAction={() => router.push('/(tabs)/mine/ai-listing-configs')}
        />
      </SafeAreaView>
    );
  }

  const running = currentTask != null && !currentTask.finished;
  const failedItems = currentTask?.items.filter((it) => it.status === 'failed') ?? [];

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.topBar}>
          <Button
            label="历史任务"
            variant="ghost"
            onPress={() => router.push('/(tabs)/mine/ai-listing-history')}
            style={styles.historyBtn}
          />
        </View>

        {/* AI 配置 */}
        <Card style={styles.section}>
          <Text style={[styles.label, { color: c.textSecondary }]}>AI 配置</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRowScroll}>
            {configs.map((cfg) => {
              const selected = selectedConfigId === cfg.id;
              return (
                <Pressable
                  key={cfg.id}
                  onPress={() => setSelectedConfigId(cfg.id)}
                  style={[
                    styles.chip,
                    {
                      borderColor: selected ? c.primary : c.border,
                      backgroundColor: selected ? c.primary : c.background,
                    },
                  ]}
                >
                  <Text style={[styles.chipText, { color: selected ? '#FFFFFF' : c.text }]} numberOfLines={1}>
                    {cfg.name}
                  </Text>
                </Pressable>
              );
            })}
          </ScrollView>
          {selectedConfig ? (
            <Text style={[styles.configMeta, { color: c.textMuted }]} numberOfLines={1}>
              {selectedConfig.text_model}
              {selectedConfig.image_enabled ? ' · 自动配图' : ' · 不配图'}
            </Text>
          ) : null}
        </Card>

        {/* 生成参数 */}
        <Card style={styles.section}>
          <Text style={[styles.label, { color: c.textSecondary }]}>生成主题</Text>
          <Input value={keyword} onChangeText={setKeyword} placeholder="如：iPhone 15 Pro 256G" maxLength={200} />

          <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>条数（1~50）</Text>
          <Input value={countText} onChangeText={setCountText} keyboardType="number-pad" placeholder="5" />

          <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>价格模式</Text>
          <View style={styles.chipRow}>
            {(['fixed', 'range'] as const).map((m) => {
              const selected = priceMode === m;
              return (
                <Pressable
                  key={m}
                  onPress={() => setPriceMode(m)}
                  style={[
                    styles.chip,
                    {
                      borderColor: selected ? c.primary : c.border,
                      backgroundColor: selected ? c.primary : c.background,
                    },
                  ]}
                >
                  <Text style={[styles.chipText, { color: selected ? '#FFFFFF' : c.text }]}>
                    {m === 'fixed' ? '固定价' : '区间价'}
                  </Text>
                </Pressable>
              );
            })}
          </View>

          {priceMode === 'fixed' ? (
            <>
              <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>价格（元）</Text>
              <Input value={priceText} onChangeText={setPriceText} keyboardType="decimal-pad" placeholder="0.00" />
            </>
          ) : (
            <>
              <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>价格区间（元）</Text>
              <View style={styles.priceRow}>
                <Input
                  value={priceMinText}
                  onChangeText={setPriceMinText}
                  keyboardType="decimal-pad"
                  placeholder="最低"
                  style={styles.priceInput}
                />
                <Text style={[styles.priceSep, { color: c.textMuted }]}>-</Text>
                <Input
                  value={priceMaxText}
                  onChangeText={setPriceMaxText}
                  keyboardType="decimal-pad"
                  placeholder="最高"
                  style={styles.priceInput}
                />
              </View>
            </>
          )}
        </Card>

        {/* 素材默认值（折叠） */}
        <Card style={styles.section}>
          <Pressable style={styles.foldHeader} onPress={() => setMaterialExpanded((v) => !v)}>
            <Text style={[styles.foldTitle, { color: c.text }]}>素材默认值</Text>
            <Text style={[styles.chevron, { color: c.textMuted }]}>{materialExpanded ? '▲' : '▼'}</Text>
          </Pressable>

          {materialExpanded ? (
            <View style={styles.foldBody}>
              <Text style={[styles.label, { color: c.textSecondary }]}>成色</Text>
              <View style={styles.chipRow}>
                {CONDITION_OPTIONS.map((opt) => {
                  const selected = condition === opt;
                  return (
                    <Pressable
                      key={opt}
                      onPress={() => setCondition(opt)}
                      style={[
                        styles.chip,
                        {
                          borderColor: selected ? c.primary : c.border,
                          backgroundColor: selected ? c.primary : c.background,
                        },
                      ]}
                    >
                      <Text style={[styles.chipText, { color: selected ? '#FFFFFF' : c.text }]}>{opt}</Text>
                    </Pressable>
                  );
                })}
              </View>

              <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>品牌</Text>
              <Input value={brand} onChangeText={setBrand} placeholder="选填，如：Apple" maxLength={100} />

              <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>数量</Text>
              <Input value={quantityText} onChangeText={setQuantityText} keyboardType="number-pad" placeholder="1" />

              <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>运费方式</Text>
              <View style={styles.chipRow}>
                {SHIPPING_OPTIONS.map((opt) => {
                  const selected = shippingMethod === opt.value;
                  return (
                    <Pressable
                      key={opt.value}
                      onPress={() => setShippingMethod(opt.value)}
                      style={[
                        styles.chip,
                        {
                          borderColor: selected ? c.primary : c.border,
                          backgroundColor: selected ? c.primary : c.background,
                        },
                      ]}
                    >
                      <Text style={[styles.chipText, { color: selected ? '#FFFFFF' : c.text }]}>{opt.label}</Text>
                    </Pressable>
                  );
                })}
              </View>

              {shippingMethod === 'fixed' ? (
                <>
                  <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>运费（元）</Text>
                  <Input value={postageText} onChangeText={setPostageText} keyboardType="decimal-pad" placeholder="0.00" />
                </>
              ) : null}
            </View>
          ) : null}
        </Card>

        {/* 兜底图片 */}
        <Card style={styles.section}>
          <Text style={[styles.label, { color: c.textSecondary }]}>兜底图片</Text>
          <Text style={[styles.configMeta, { color: c.textMuted }]}>
            {selectedConfig?.image_enabled ? '已启用 AI 配图，可留空' : '未启用 AI 配图，需至少 1 张'}
          </Text>
          <View style={styles.imageGrid}>
            {fallbackImages.map((uri, index) => (
              <View key={uri} style={[styles.imageTile, { borderColor: c.border }]}>
                <Image source={{ uri }} style={styles.imageThumb} resizeMode="cover" />
                <Pressable
                  onPress={() => setFallbackImages((prev) => prev.filter((_, i) => i !== index))}
                  hitSlop={8}
                  style={styles.imageDel}
                >
                  <X size={12} color="#FFFFFF" />
                </Pressable>
              </View>
            ))}
            {fallbackImages.length < 9 ? (
              <Pressable
                onPress={handlePickImages}
                style={[styles.imageTile, styles.imageAdd, { borderColor: c.border }]}
              >
                <Plus size={20} color={c.textMuted} />
                <Text style={[styles.imageAddText, { color: c.textMuted }]}>添加</Text>
              </Pressable>
            ) : null}
          </View>
        </Card>

        <Button
          label="开始生成"
          onPress={handleStart}
          loading={creating}
          disabled={creating || running}
          style={styles.startBtn}
        />

        {/* 当前任务进度 */}
        {currentTask ? (
          <Card style={styles.section}>
            <View style={styles.taskHeader}>
              <Text style={[styles.taskKeyword, { color: c.text }]} numberOfLines={1}>
                {currentTask.keyword}
              </Text>
              {(() => {
                const b = taskBadge(currentTask.status);
                return <Badge label={b.label} variant={b.variant} />;
              })()}
            </View>

            <View style={[styles.progressTrack, { backgroundColor: c.surfaceAlt, borderColor: c.border }]}>
              <View
                style={[
                  styles.progressFill,
                  {
                    width: `${Math.min(100, Math.max(0, currentTask.progress_percent))}%`,
                    backgroundColor: c.primary,
                  },
                ]}
              />
            </View>

            <Text style={[styles.counts, { color: c.textSecondary }]}>
              成功 {currentTask.success} · 失败 {currentTask.failed} · 共 {currentTask.total}
            </Text>

            {currentTask.error_message ? (
              <Text style={[styles.taskError, { color: c.error }]} numberOfLines={3}>
                {currentTask.error_message}
              </Text>
            ) : null}

            {failedItems.length > 0 ? (
              <View style={[styles.failedWrap, { borderTopColor: c.border, borderTopWidth: 1 }]}>
                {failedItems.map((it) => (
                  <View key={it.seq} style={[styles.failedRow, { borderBottomColor: c.borderLight }]}>
                    <Text style={[styles.failedTitle, { color: c.textSecondary }]} numberOfLines={1}>
                      #{it.seq} {it.title}
                    </Text>
                    <Text style={[styles.failedMsg, { color: c.error }]} numberOfLines={2}>
                      {it.error_message}
                    </Text>
                  </View>
                ))}
              </View>
            ) : null}

            <View style={styles.taskActions}>
              {running ? (
                <Button
                  label="取消任务"
                  variant="danger"
                  onPress={handleCancel}
                  loading={taskActionLoading}
                  disabled={taskActionLoading}
                  style={styles.taskBtn}
                />
              ) : (
                <Button label="清除" variant="secondary" onPress={handleClear} style={styles.taskBtn} />
              )}
            </View>
          </Card>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.md },
  topBar: { flexDirection: 'row', justifyContent: 'flex-end' },
  historyBtn: { minHeight: 36, paddingHorizontal: spacing.md, alignSelf: 'flex-end' },
  section: { gap: spacing.xs, padding: spacing.md },
  label: { ...typography.caption },
  configMeta: { ...typography.small, marginTop: 2 },
  chipRowScroll: { gap: spacing.sm, paddingVertical: 2 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
    borderWidth: 1,
  },
  chipText: { ...typography.small },
  priceRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  priceInput: { flex: 1 },
  priceSep: { ...typography.body },
  foldHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  foldTitle: { ...typography.body, fontWeight: '600' },
  chevron: { fontSize: 12, fontWeight: '600' },
  foldBody: { marginTop: spacing.sm },
  imageGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.sm },
  imageTile: {
    width: 64,
    height: 64,
    borderRadius: radius.md,
    borderWidth: 1,
    overflow: 'hidden',
  },
  imageThumb: { width: '100%', height: '100%' },
  imageDel: {
    position: 'absolute',
    top: 2,
    right: 2,
    width: 18,
    height: 18,
    borderRadius: 9,
    backgroundColor: 'rgba(0,0,0,0.55)',
    alignItems: 'center',
    justifyContent: 'center',
  },
  imageAdd: {
    alignItems: 'center',
    justifyContent: 'center',
    gap: 2,
    borderStyle: 'dashed',
  },
  imageAddText: { ...typography.micro },
  startBtn: { minHeight: 48, alignSelf: 'stretch' },
  taskHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.sm,
  },
  taskKeyword: { ...typography.body, fontWeight: '600', flexShrink: 1 },
  progressTrack: {
    height: 6,
    borderRadius: radius.full,
    borderWidth: 1,
    marginTop: spacing.sm,
    overflow: 'hidden',
  },
  progressFill: { height: '100%', borderRadius: radius.full },
  counts: { ...typography.small, marginTop: spacing.xs },
  taskError: { ...typography.small, marginTop: spacing.xs },
  failedWrap: { marginTop: spacing.sm, gap: 0 },
  failedRow: {
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
    gap: 2,
  },
  failedTitle: { ...typography.small },
  failedMsg: { ...typography.small },
  taskActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm },
  taskBtn: { flex: 1, minHeight: 40 },
});
