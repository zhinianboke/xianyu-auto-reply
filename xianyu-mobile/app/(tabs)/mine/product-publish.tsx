import { useState, useCallback, useEffect, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  FlatList,
  Pressable,
  Alert,
  Modal,
  KeyboardAvoidingView,
  Platform,
  Image,
  RefreshControl,
  ActivityIndicator,
  useColorScheme,
  type TextStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import { Card, Button, Input, Badge, EmptyState } from '@/components/ui';
import { Package, Plus, X } from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { getAccountOptions, type AccountOption } from '@/api/wrappers/accounts';
import {
  uploadProductImages,
  publishSingle,
  publishBatch,
  getBatchStatus,
  getPublishLogs,
  listMaterials,
  createMaterial,
  deleteMaterial,
  recommendCategory,
  type ProductMaterial,
  type PublishLogItem,
  type BatchStatus,
  type CategoryCandidate,
} from '@/api/wrappers/product-publish';

// ---------------------------------------------------------------------------
// 常量
// ---------------------------------------------------------------------------

const MAX_IMAGES = 9;
const POLL_INTERVAL_MS = 5000;

const CONDITION_OPTIONS = ['全新', '几乎全新', '轻微使用', '明显使用', '需要维修'];

const DELIVERY_OPTIONS: { value: 'express' | 'pickup'; label: string }[] = [
  { value: 'express', label: '快递发货' },
  { value: 'pickup', label: '当面交易' },
];

const SHIPPING_OPTIONS: { value: 'free' | 'distance' | 'fixed' | 'none'; label: string }[] = [
  { value: 'free', label: '包邮' },
  { value: 'distance', label: '按距离' },
  { value: 'fixed', label: '固定运费' },
  { value: 'none', label: '不包邮' },
];

const LOG_STATUS_FILTERS: { key: string; label: string }[] = [
  { key: '', label: '全部' },
  { key: 'success', label: '成功' },
  { key: 'failed', label: '失败' },
  { key: 'publishing', label: '发布中' },
  { key: 'pending', label: '等待' },
];

/** 已选本地图（uri 供预览，path 是服务器路径供发布提交） */
interface LocalImage {
  uri: string;
  path: string;
}

type TabKey = 'single' | 'batch' | 'logs';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'single', label: '单品发布' },
  { key: 'batch', label: '批量发布' },
  { key: 'logs', label: '发布记录' },
];

function accountLabel(acc: AccountOption): string {
  return acc.remark || acc.id;
}

// ---------------------------------------------------------------------------
// 页面骨架：分段控件（单品发布 / 批量发布 / 发布记录）
// ---------------------------------------------------------------------------

export default function ProductPublishScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [tab, setTab] = useState<TabKey>('single');
  const [accounts, setAccounts] = useState<AccountOption[]>([]);

  // 批量任务状态放在父级：轮询跨 Tab 持续进行，切到"发布记录"也不中断
  const [activeBatch, setActiveBatch] = useState<{ batchId: string; total: number } | null>(null);
  const [batchStatus, setBatchStatus] = useState<BatchStatus | null>(null);
  const [pollError, setPollError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const finishedAlertedRef = useRef(false);

  const loadAccounts = useCallback(async () => {
    try {
      setAccounts(await getAccountOptions());
    } catch {
      // 账号加载失败不阻塞页面，表单提交时会提示选择账号
    }
  }, []);

  useEffect(() => {
    loadAccounts();
  }, [loadAccounts]);

  const stopPolling = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const pollOnce = useCallback(
    async (batchId: string) => {
      try {
        const st = await getBatchStatus(batchId);
        setBatchStatus(st);
        setPollError(null);
        if (st.finished) {
          stopPolling();
          if (!finishedAlertedRef.current) {
            finishedAlertedRef.current = true;
            Alert.alert(
              '批量发布完成',
              `共 ${st.total} 件：成功 ${st.success} 件，失败 ${st.failed} 件`,
            );
          }
        }
      } catch (e) {
        // 任务过期等业务失败：停止轮询并展示原因
        stopPolling();
        setPollError((e as Error).message || '查询批量进度失败');
      }
    },
    [stopPolling],
  );

  // 5 秒轮询批量进度直到 finished
  useEffect(() => {
    if (!activeBatch) return;
    finishedAlertedRef.current = false;
    setPollError(null);
    pollOnce(activeBatch.batchId);
    timerRef.current = setInterval(() => pollOnce(activeBatch.batchId), POLL_INTERVAL_MS);
    return stopPolling;
  }, [activeBatch, pollOnce, stopPolling]);

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      {/* 分段控件 */}
      <View style={[styles.tabs, { backgroundColor: c.surfaceAlt }]}>
        {TABS.map((t) => {
          const on = tab === t.key;
          return (
            <Pressable key={t.key} onPress={() => setTab(t.key)} style={[styles.tabItem, on && { backgroundColor: c.primary }]}>
              <Text style={[styles.tabText, { color: on ? '#FFFFFF' : c.textSecondary }]}>{t.label}</Text>
            </Pressable>
          );
        })}
      </View>

      {tab === 'single' && (
        <SinglePublishTab
          accounts={accounts}
          onPublished={() => setTab('logs')}
        />
      )}
      {tab === 'batch' && (
        <BatchPublishTab
          accounts={accounts}
          activeBatch={activeBatch}
          batchStatus={batchStatus}
          pollError={pollError}
          onStartBatch={(b) => setActiveBatch(b)}
        />
      )}
      {tab === 'logs' && <PublishLogsTab />}
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// 通用小组件
// ---------------------------------------------------------------------------

function FieldLabel({ label, required }: { label: string; required?: boolean }) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  return (
    <View style={styles.fieldLabel}>
      <Text style={[styles.fieldLabelText, { color: c.textSecondary }]}>{label}</Text>
      {required ? <Text style={styles.required}> *</Text> : null}
    </View>
  );
}

function FieldHint({ text }: { text: string }) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  return <Text style={[styles.fieldHint, { color: c.textMuted }]}>{text}</Text>;
}

/** 单选账号胶囊（对齐 items.tsx 的写法） */
function AccountChips({
  accounts,
  selectedId,
  onSelect,
}: {
  accounts: AccountOption[];
  selectedId: string;
  onSelect: (id: string) => void;
}) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  if (accounts.length === 0) {
    return <FieldHint text="暂无闲鱼账号，请先在「账号管理」中添加账号" />;
  }
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRowScroll}>
      {accounts.map((acc) => {
        const selected = selectedId === acc.id;
        return (
          <Pressable
            key={acc.id}
            onPress={() => onSelect(acc.id)}
            style={[
              styles.chip,
              {
                borderColor: selected ? c.primary : c.border,
                backgroundColor: selected ? c.primary : c.surface,
              },
            ]}
          >
            <Text style={[styles.chipText, { color: selected ? '#FFFFFF' : c.text }]} numberOfLines={1}>
              {accountLabel(acc)}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

/** 图片九宫格：预览 + 删除 + 添加（选中即上传换服务器路径） */
function ImageGrid({
  images,
  uploading,
  onPick,
  onRemove,
}: {
  images: LocalImage[];
  uploading: boolean;
  onPick: () => void;
  onRemove: (index: number) => void;
}) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  return (
    <View style={styles.imageGrid}>
      {images.map((img, index) => (
        <View key={`${img.uri}-${index}`} style={styles.imageCell}>
          <Image source={{ uri: img.uri }} style={styles.thumb} />
          <Pressable
            onPress={() => onRemove(index)}
            style={[styles.imageDel, { backgroundColor: c.error }]}
            hitSlop={8}
          >
            <X color="#FFFFFF" size={12} strokeWidth={3} />
          </Pressable>
          <View style={styles.imageIndex}>
            <Text style={styles.imageIndexText}>{index + 1}</Text>
          </View>
        </View>
      ))}
      {images.length < MAX_IMAGES && (
        <Pressable
          onPress={onPick}
          style={[styles.imageAdd, { borderColor: c.border }]}
          disabled={uploading}
        >
          {uploading ? (
            <ActivityIndicator size="small" color={c.primary} />
          ) : (
            <>
              <Plus color={c.textMuted} size={22} />
              <Text style={[styles.imageAddText, { color: c.textMuted }]}>添加图片</Text>
            </>
          )}
        </Pressable>
      )}
    </View>
  );
}

/** 选图并上传，返回 {uri, path} 列表（共享给单品表单与素材表单） */
async function pickAndUploadImages(remaining: number): Promise<LocalImage[]> {
  if (remaining <= 0) return [];
  const result = await ImagePicker.launchImageLibraryAsync({
    mediaTypes: ['images'],
    allowsMultipleSelection: true,
    selectionLimit: remaining,
    quality: 0.8,
  });
  if (result.canceled || !result.assets || result.assets.length === 0) return [];
  const picked = result.assets.slice(0, remaining);
  const uploaded = await uploadProductImages(picked.map((a) => a.uri));
  return picked
    .map((a, i) => ({ uri: a.uri, path: uploaded.paths[i] }))
    .filter((x) => Boolean(x.path));
}

// ---------------------------------------------------------------------------
// Tab 1：单品发布（表单）
// ---------------------------------------------------------------------------

interface SingleFormState {
  accountId: string;
  title: string;
  description: string;
  price: string;
  originalPrice: string;
  stock: string;
  quantity: string;
  condition: string;
  brand: string;
  category: string;
  deliveryMethod: 'express' | 'pickup';
  shippingMethod: 'free' | 'distance' | 'fixed' | 'none';
  postage: string;
  address: string;
  images: LocalImage[];
}

const EMPTY_SINGLE_FORM: SingleFormState = {
  accountId: '',
  title: '',
  description: '',
  price: '',
  originalPrice: '',
  stock: '',
  quantity: '1',
  condition: '全新',
  brand: '',
  category: '',
  deliveryMethod: 'express',
  shippingMethod: 'free',
  postage: '',
  address: '',
  images: [],
};

function SinglePublishTab({
  accounts,
  onPublished,
}: {
  accounts: AccountOption[];
  onPublished: () => void;
}) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [form, setForm] = useState<SingleFormState>(EMPTY_SINGLE_FORM);
  const [uploading, setUploading] = useState(false);
  const [publishing, setPublishing] = useState(false);
  const [recommending, setRecommending] = useState(false);
  const [candidates, setCandidates] = useState<CategoryCandidate[]>([]);
  // 类目推荐选中的候选（携带平台分类字段，发布时一并提交）
  const [selectedCat, setSelectedCat] = useState<CategoryCandidate | null>(null);

  const update = <K extends keyof SingleFormState>(field: K, value: SingleFormState[K]) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const handlePick = useCallback(async () => {
    try {
      setUploading(true);
      const next = await pickAndUploadImages(MAX_IMAGES - form.images.length);
      if (next.length > 0) {
        setForm((prev) => ({ ...prev, images: [...prev.images, ...next] }));
      }
    } catch (e) {
      Alert.alert('上传失败', (e as Error).message);
    } finally {
      setUploading(false);
    }
  }, [form.images.length]);

  const handleRemoveImage = useCallback((index: number) => {
    setForm((prev) => {
      const next = [...prev.images];
      next.splice(index, 1);
      return { ...prev, images: next };
    });
  }, []);

  const handleRecommend = useCallback(async () => {
    if (!form.title.trim() && !form.description.trim()) {
      Alert.alert('提示', '请先填写商品标题或商品描述');
      return;
    }
    setRecommending(true);
    try {
      const res = await recommendCategory({
        title: form.title.trim(),
        description: form.description.trim(),
        account_id: form.accountId || undefined,
      });
      if (res.candidates.length === 0) {
        Alert.alert('提示', '未推荐到合适的类目，请手动填写分类');
      }
      setCandidates(res.candidates);
    } catch (e) {
      Alert.alert('类目推荐失败', (e as Error).message);
    } finally {
      setRecommending(false);
    }
  }, [form.title, form.description, form.accountId]);

  const handleSelectCandidate = useCallback((cand: CategoryCandidate) => {
    setSelectedCat(cand);
    setForm((prev) => ({ ...prev, category: cand.cat_name || '' }));
  }, []);

  async function handlePublish() {
    const err = validateSingleForm(form);
    if (err) {
      Alert.alert('提示', err);
      return;
    }
    setPublishing(true);
    try {
      const body = buildSingleBody(form, selectedCat);
      const res = await publishSingle(body);
      const detail = res.item_id ? `商品ID：${res.item_id}` : res.item_url || '已提交闲鱼发布';
      Alert.alert('发布成功', detail, [{ text: '查看记录', onPress: onPublished }]);
      setForm({ ...EMPTY_SINGLE_FORM, accountId: form.accountId });
      setCandidates([]);
      setSelectedCat(null);
    } catch (e) {
      Alert.alert('发布失败', (e as Error).message || '未知错误');
    } finally {
      setPublishing(false);
    }
  }

  return (
    <ScrollView
      style={styles.flex}
      contentContainerStyle={styles.formBody}
      keyboardShouldPersistTaps="handled"
    >
      {/* 账号 */}
      <FieldLabel label="发布账号" required />
      <AccountChips
        accounts={accounts}
        selectedId={form.accountId}
        onSelect={(id) => update('accountId', id)}
      />

      {/* 图片 */}
      <FieldLabel label={`商品图片（${form.images.length}/${MAX_IMAGES}，至少 1 张）`} required />
      <ImageGrid images={form.images} uploading={uploading} onPick={handlePick} onRemove={handleRemoveImage} />

      {/* 标题 / 描述 */}
      <FieldLabel label="商品标题" required />
      <Input
        value={form.title}
        onChangeText={(v) => update('title', v)}
        placeholder="请输入商品标题（最多 200 字）"
        maxLength={200}
      />

      <FieldLabel label="商品描述" required />
      <Input
        value={form.description}
        onChangeText={(v) => update('description', v)}
        placeholder="请输入商品描述（最多 1500 字）"
        multiline
        numberOfLines={5}
        maxLength={1500}
        style={styles.textarea}
      />

      {/* 价格 */}
      <View style={styles.row2}>
        <View style={styles.flex1}>
          <FieldLabel label="售价（元）" required />
          <Input
            value={form.price}
            onChangeText={(v) => {
              if (v === '' || /^\d*\.?\d{0,2}$/.test(v)) update('price', v);
            }}
            placeholder="0.00"
            keyboardType="decimal-pad"
          />
        </View>
        <View style={styles.flex1}>
          <FieldLabel label="原价（划线价）" />
          <Input
            value={form.originalPrice}
            onChangeText={(v) => {
              if (v === '' || /^\d*\.?\d{0,2}$/.test(v)) update('originalPrice', v);
            }}
            placeholder="可选"
            keyboardType="decimal-pad"
          />
        </View>
      </View>

      <View style={styles.row2}>
        <View style={styles.flex1}>
          <FieldLabel label="库存" />
          <Input
            value={form.stock}
            onChangeText={(v) => {
              if (v === '' || /^\d*$/.test(v)) update('stock', v);
            }}
            placeholder="可选"
            keyboardType="number-pad"
          />
        </View>
        <View style={styles.flex1}>
          <FieldLabel label="发布数量" />
          <Input
            value={form.quantity}
            onChangeText={(v) => {
              if (v === '' || /^\d*$/.test(v)) update('quantity', v);
            }}
            placeholder="默认 1"
            keyboardType="number-pad"
          />
        </View>
      </View>

      {/* 成色 / 品牌 */}
      <FieldLabel label="成色" />
      <View style={styles.chipRow}>
        {CONDITION_OPTIONS.map((opt) => {
          const on = form.condition === opt;
          return (
            <Pressable
              key={opt}
              onPress={() => update('condition', opt)}
              style={[
                styles.chip,
                {
                  borderColor: on ? c.primary : c.border,
                  backgroundColor: on ? c.primary : c.surface,
                },
              ]}
            >
              <Text style={[styles.chipText, { color: on ? '#FFFFFF' : c.text }]}>{opt}</Text>
            </Pressable>
          );
        })}
      </View>

      <FieldLabel label="品牌" />
      <Input
        value={form.brand}
        onChangeText={(v) => update('brand', v)}
        placeholder="可选，例如：苹果、小米"
      />

      {/* 分类 + 类目推荐 */}
      <View style={styles.labelActionRow}>
        <FieldLabel label="商品分类" />
        <Pressable onPress={handleRecommend} disabled={recommending} hitSlop={6}>
          <Text style={[styles.linkText, { color: c.primary }]}>
            {recommending ? '推荐中...' : 'AI 推荐类目'}
          </Text>
        </Pressable>
      </View>
      <Input
        value={form.category}
        onChangeText={(v) => {
          update('category', v);
          if (selectedCat) setSelectedCat(null); // 手动改动视为放弃推荐结果
        }}
        placeholder="可选，例如：数码产品/手机"
      />
      {candidates.length > 0 && (
        <View style={styles.chipRow}>
          {candidates.map((cand, i) => {
            const on = selectedCat === cand;
            return (
              <Pressable
                key={`${cand.cat_id ?? i}-${i}`}
                onPress={() => handleSelectCandidate(cand)}
                style={[
                  styles.chip,
                  {
                    borderColor: on ? c.primary : c.border,
                    backgroundColor: on ? c.primary : c.surface,
                  },
                ]}
              >
                <Text style={[styles.chipText, { color: on ? '#FFFFFF' : c.text }]} numberOfLines={1}>
                  {cand.cat_name || '未知类目'}
                  {cand.score != null ? ` ${Math.round(cand.score * 100)}%` : ''}
                </Text>
              </Pressable>
            );
          })}
        </View>
      )}
      {candidates.length > 0 && (
        <FieldHint text={selectedCat ? `已选择推荐类目：${selectedCat.cat_name}` : '点击候选类目可提高发布精度（可选）'} />
      )}

      {/* 发货方式 */}
      <FieldLabel label="发货方式" />
      <View style={styles.chipRow}>
        {DELIVERY_OPTIONS.map((o) => {
          const on = form.deliveryMethod === o.value;
          return (
            <Pressable
              key={o.value}
              onPress={() => update('deliveryMethod', o.value)}
              style={[
                styles.chip,
                {
                  borderColor: on ? c.primary : c.border,
                  backgroundColor: on ? c.primary : c.surface,
                },
              ]}
            >
              <Text style={[styles.chipText, { color: on ? '#FFFFFF' : c.text }]}>{o.label}</Text>
            </Pressable>
          );
        })}
      </View>

      {/* 运费 */}
      <FieldLabel label="运费" />
      <View style={styles.chipRow}>
        {SHIPPING_OPTIONS.map((o) => {
          const on = form.shippingMethod === o.value;
          return (
            <Pressable
              key={o.value}
              onPress={() => update('shippingMethod', o.value)}
              style={[
                styles.chip,
                {
                  borderColor: on ? c.primary : c.border,
                  backgroundColor: on ? c.primary : c.surface,
                },
              ]}
            >
              <Text style={[styles.chipText, { color: on ? '#FFFFFF' : c.text }]}>{o.label}</Text>
            </Pressable>
          );
        })}
      </View>
      {form.shippingMethod === 'fixed' && (
        <>
          <FieldLabel label="运费金额（元）" required />
          <Input
            value={form.postage}
            onChangeText={(v) => {
              if (v === '' || /^\d*\.?\d{0,2}$/.test(v)) update('postage', v);
            }}
            placeholder="例如：10.00"
            keyboardType="decimal-pad"
          />
        </>
      )}

      {/* 所在地 */}
      <FieldLabel label="宝贝所在地" />
      <Input
        value={form.address}
        onChangeText={(v) => update('address', v)}
        placeholder="可选，例如：浙江省杭州市"
      />

      <Button
        label={publishing ? '发布中...' : '发布商品'}
        onPress={handlePublish}
        loading={publishing}
        disabled={publishing || uploading}
        style={styles.submitBtn}
      />
      <FieldHint text="发布为同步操作，闲鱼处理可能需要数十秒，请耐心等待。" />
    </ScrollView>
  );
}

function validateSingleForm(f: SingleFormState): string {
  if (!f.accountId) return '请选择发布账号';
  if (f.images.length === 0) return '请至少上传 1 张商品图片';
  if (!f.title.trim()) return '请输入商品标题';
  if (!f.description.trim()) return '请输入商品描述';
  const price = parseFloat(f.price);
  if (!f.price.trim() || Number.isNaN(price) || price <= 0) return '请输入大于 0 的售价';
  if (f.originalPrice.trim()) {
    const orig = parseFloat(f.originalPrice);
    if (Number.isNaN(orig) || orig < 0) return '请输入正确的原价';
  }
  if (f.stock.trim()) {
    const stock = parseInt(f.stock, 10);
    if (Number.isNaN(stock) || stock < 0) return '请输入正确的库存数量';
  }
  if (f.quantity.trim()) {
    const qty = parseInt(f.quantity, 10);
    if (Number.isNaN(qty) || qty < 1) return '发布数量必须大于 0';
  }
  if (f.shippingMethod === 'fixed') {
    const postage = parseFloat(f.postage);
    if (!f.postage.trim() || Number.isNaN(postage) || postage < 0) return '固定运费必须填写不小于 0 的金额';
  }
  return '';
}

function buildSingleBody(
  f: SingleFormState,
  selectedCat: CategoryCandidate | null,
): Parameters<typeof publishSingle>[0] {
  const body: Parameters<typeof publishSingle>[0] = {
    account_id: f.accountId,
    title: f.title.trim(),
    description: f.description.trim(),
    price: parseFloat(f.price),
    images: f.images.map((i) => i.path),
    condition: f.condition,
    delivery_method: f.deliveryMethod,
    shipping_method: f.shippingMethod,
    postage: f.shippingMethod === 'fixed' ? parseFloat(f.postage) || 0 : 0,
    quantity: f.quantity.trim() ? parseInt(f.quantity, 10) || 1 : 1,
  };
  if (f.originalPrice.trim()) body.original_price = parseFloat(f.originalPrice);
  if (f.stock.trim()) body.stock = parseInt(f.stock, 10);
  if (f.brand.trim()) body.brand = f.brand.trim();
  if (f.address.trim()) body.address = f.address.trim();
  if (f.category.trim()) body.category = f.category.trim();
  if (selectedCat) {
    // 携带类目推荐返回的平台分类字段，提升闲鱼发布成功率
    body.category_source = 'recommendation';
    if (selectedCat.score != null) body.category_confidence = selectedCat.score;
    if (selectedCat.cat_id) body.platform_category_id = selectedCat.cat_id;
    if (selectedCat.cat_name) body.platform_category_name = selectedCat.cat_name;
    if (selectedCat.channel_cat_id) body.platform_channel_category_id = selectedCat.channel_cat_id;
    if (selectedCat.channel_cat_name) body.platform_channel_category_name = selectedCat.channel_cat_name;
    if (selectedCat.leaf_id) body.platform_leaf_id = selectedCat.leaf_id;
    if (selectedCat.tb_cat_id) body.platform_tb_category_id = selectedCat.tb_cat_id;
    if (selectedCat.path && selectedCat.path.length > 0) body.platform_category_path = selectedCat.path;
  } else if (f.category.trim()) {
    body.category_source = 'manual';
  }
  return body;
}

// ---------------------------------------------------------------------------
// Tab 2：批量发布（素材多选 + 提交 + 进度展示）
// ---------------------------------------------------------------------------

const MATERIAL_PAGE_SIZE = 50;

function BatchPublishTab({
  accounts,
  activeBatch,
  batchStatus,
  pollError,
  onStartBatch,
}: {
  accounts: AccountOption[];
  activeBatch: { batchId: string; total: number } | null;
  batchStatus: BatchStatus | null;
  pollError: string | null;
  onStartBatch: (batch: { batchId: string; total: number }) => void;
}) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [materials, setMaterials] = useState<ProductMaterial[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const [selectedMaterialIds, setSelectedMaterialIds] = useState<number[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);

  const loadMaterials = useCallback(async () => {
    setRefreshing(true);
    try {
      const res = await listMaterials(1, MATERIAL_PAGE_SIZE);
      setMaterials(res.list);
      setTotal(res.total);
    } catch (e) {
      Alert.alert('加载素材失败', (e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadMaterials();
  }, [loadMaterials]);

  const toggleAccount = useCallback((id: string) => {
    setSelectedAccountIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }, []);

  const toggleMaterial = useCallback((id: number) => {
    setSelectedMaterialIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }, []);

  const handleDeleteMaterial = useCallback(
    (material: ProductMaterial) => {
      Alert.alert('删除素材', `确定删除「${material.title}」吗？此操作不可恢复。`, [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteMaterial(material.id);
              setSelectedMaterialIds((prev) => prev.filter((x) => x !== material.id));
              loadMaterials();
            } catch (e) {
              Alert.alert('删除失败', (e as Error).message);
            }
          },
        },
      ]);
    },
    [loadMaterials],
  );

  async function handleStart() {
    if (selectedAccountIds.length === 0) {
      Alert.alert('提示', '请至少选择 1 个发布账号');
      return;
    }
    if (selectedMaterialIds.length === 0) {
      Alert.alert('提示', '请至少选择 1 个发布素材');
      return;
    }
    setSubmitting(true);
    try {
      const res = await publishBatch(selectedAccountIds, selectedMaterialIds);
      onStartBatch({ batchId: res.batch_id, total: res.total });
      Alert.alert('批量任务已提交', res.total > 0 ? `共 ${res.total} 件商品，正在后台执行` : '正在后台执行');
    } catch (e) {
      Alert.alert('提交失败', (e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  // 进度百分比：已出结果（成功+失败）/ 总数
  const done = batchStatus ? batchStatus.success + batchStatus.failed : 0;
  const progressTotal = batchStatus && batchStatus.total > 0 ? batchStatus.total : activeBatch?.total ?? 0;
  const percent = progressTotal > 0 ? Math.min(100, Math.round((done / progressTotal) * 100)) : 0;

  return (
    <View style={styles.flex}>
      {/* 账号多选 */}
      <View style={[styles.sectionBar, { borderBottomColor: c.borderLight }]}>
        <FieldLabel label={`发布账号（已选 ${selectedAccountIds.length}）`} required />
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRowScroll}>
          {accounts.length === 0 && <FieldHint text="暂无闲鱼账号，请先在「账号管理」中添加账号" />}
          {accounts.map((acc) => {
            const on = selectedAccountIds.includes(acc.id);
            return (
              <Pressable
                key={acc.id}
                onPress={() => toggleAccount(acc.id)}
                style={[
                  styles.chip,
                  {
                    borderColor: on ? c.primary : c.border,
                    backgroundColor: on ? c.primary : c.surface,
                  },
                ]}
              >
                <Text style={[styles.chipText, { color: on ? '#FFFFFF' : c.text }]} numberOfLines={1}>
                  {on ? '✓ ' : ''}
                  {accountLabel(acc)}
                </Text>
              </Pressable>
            );
          })}
        </ScrollView>
      </View>

      {/* 素材列表 */}
      <View style={styles.materialHeader}>
        <Text style={[styles.materialTitle, { color: c.text }]}>
          发布素材（已选 {selectedMaterialIds.length}/{total}）
        </Text>
        <Button label="+ 新建素材" onPress={() => setModalVisible(true)} variant="secondary" />
      </View>

      {loading ? (
        <View style={styles.center}>
          <ActivityIndicator size="small" color={c.primary} />
        </View>
      ) : (
        <FlatList
          data={materials}
          keyExtractor={(item) => String(item.id)}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadMaterials} />}
          contentContainerStyle={styles.materialList}
          ListEmptyComponent={
            <EmptyState
              icon={Package}
              title="暂无素材"
              message="先新建素材，再选择素材批量发布"
              actionLabel="新建素材"
              onAction={() => setModalVisible(true)}
            />
          }
          renderItem={({ item }) => {
            const on = selectedMaterialIds.includes(item.id);
            return (
              <Pressable onPress={() => toggleMaterial(item.id)} onLongPress={() => handleDeleteMaterial(item)}>
                <Card style={[styles.materialCard, on && { borderColor: c.primary, borderWidth: 1.5 }]}>
                  <View style={styles.materialRow}>
                    {item.images && item.images.length > 0 ? (
                      <Image
                        source={{ uri: item.images[0] }}
                        style={[styles.materialThumb, { backgroundColor: c.surfaceAlt }]}
                      />
                    ) : (
                      <View style={[styles.materialThumb, { backgroundColor: c.surfaceAlt }]}>
                        <Package size={20} stroke={c.textMuted} />
                      </View>
                    )}
                    <View style={styles.materialBody}>
                      <Text style={[styles.materialName, { color: c.text }]} numberOfLines={2}>
                        {item.title}
                      </Text>
                      <View style={styles.materialMeta}>
                        <Text style={[styles.materialPrice, { color: c.warning }]}>¥{item.price}</Text>
                        <Text style={[styles.materialMetaText, { color: c.textMuted }]}>
                          {item.condition} · 数量 {item.quantity} · {item.images?.length ?? 0} 图
                        </Text>
                      </View>
                    </View>
                    <View style={[styles.checkbox, on && { backgroundColor: c.primary, borderColor: c.primary }, { borderColor: c.border }]}>
                      {on ? <Text style={styles.checkboxText}>✓</Text> : null}
                    </View>
                  </View>
                </Card>
              </Pressable>
            );
          }}
        />
      )}

      {/* 批量进度 */}
      {activeBatch && (
        <View style={[styles.progressCard, { backgroundColor: c.surface, borderColor: c.border }]}>
          <View style={styles.progressHeader}>
            <Text style={[styles.progressTitle, { color: c.text }]}>批量进度</Text>
            <Text style={[styles.progressPercent, { color: c.primary }]}>{percent}%</Text>
          </View>
          <View style={[styles.progressTrack, { backgroundColor: c.surfaceAlt }]}>
            <View style={[styles.progressFill, { backgroundColor: c.primary, width: `${percent}%` }]} />
          </View>
          {batchStatus ? (
            <>
              <View style={styles.progressStats}>
                <Text style={[styles.statText, { color: c.textSecondary }]}>
                  总计 {batchStatus.total} · 成功 <Text style={{ color: c.success }}>{batchStatus.success}</Text> · 失败{' '}
                  <Text style={{ color: c.error }}>{batchStatus.failed}</Text> · 发布中 {batchStatus.publishing} · 等待{' '}
                  {batchStatus.pending}
                </Text>
                {!batchStatus.finished ? (
                  <View style={styles.pollingRow}>
                    <ActivityIndicator size="small" color={c.primary} />
                    <Text style={[styles.pollingText, { color: c.textMuted }]}>每 5 秒自动刷新</Text>
                  </View>
                ) : (
                  <Badge label="已完成" variant="success" />
                )}
              </View>
              {/* 各账号失败/同步明细 */}
              {batchStatus.account_statuses.map((acc) => (
                <View key={acc.account_id} style={[styles.accountStatusRow, { borderTopColor: c.borderLight }]}>
                  <Text style={[styles.accountStatusId, { color: c.text }]} numberOfLines={1}>
                    {acc.account_id}
                  </Text>
                  <Text style={[styles.accountStatusText, { color: c.textSecondary }]}>
                    成功 {acc.success} / 失败 <Text style={{ color: acc.failed > 0 ? c.error : c.textSecondary }}>{acc.failed}</Text> / 发布中 {acc.publishing} / 等待 {acc.pending}
                  </Text>
                  {acc.sync_status === 'failed' || acc.sync_status === 'running' ? (
                    <Text style={[styles.syncMessage, { color: acc.sync_status === 'failed' ? c.error : c.textMuted }]} numberOfLines={2}>
                      {acc.sync_message}
                    </Text>
                  ) : null}
                </View>
              ))}
            </>
          ) : (
            <Text style={[styles.progressWaiting, { color: c.textMuted }]}>正在获取进度...</Text>
          )}
          {pollError && <Text style={[styles.pollError, { color: c.error }]}>{pollError}</Text>}
        </View>
      )}

      {/* 底部提交按钮 */}
      <View style={[styles.footer, { borderTopColor: c.border, backgroundColor: c.surface }]}>
        <Button
          label={submitting ? '提交中...' : `开始批量发布（${selectedAccountIds.length} 账号 × ${selectedMaterialIds.length} 素材）`}
          onPress={handleStart}
          loading={submitting}
          disabled={submitting}
          style={styles.flex1}
        />
      </View>

      <MaterialCreateModal
        visible={modalVisible}
        onClose={() => setModalVisible(false)}
        onCreated={() => {
          setModalVisible(false);
          loadMaterials();
        }}
      />
    </View>
  );
}

// ---------------------------------------------------------------------------
// 素材新建弹窗（底部抽屉）
// ---------------------------------------------------------------------------

interface MaterialFormState {
  title: string;
  description: string;
  price: string;
  originalPrice: string;
  category: string;
  condition: string;
  quantity: string;
  images: LocalImage[];
}

const EMPTY_MATERIAL_FORM: MaterialFormState = {
  title: '',
  description: '',
  price: '',
  originalPrice: '',
  category: '',
  condition: '全新',
  quantity: '1',
  images: [],
};

function MaterialCreateModal({
  visible,
  onClose,
  onCreated,
}: {
  visible: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [form, setForm] = useState<MaterialFormState>(EMPTY_MATERIAL_FORM);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);

  const update = <K extends keyof MaterialFormState>(field: K, value: MaterialFormState[K]) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  const handlePick = useCallback(async () => {
    try {
      setUploading(true);
      const next = await pickAndUploadImages(MAX_IMAGES - form.images.length);
      if (next.length > 0) {
        setForm((prev) => ({ ...prev, images: [...prev.images, ...next] }));
      }
    } catch (e) {
      Alert.alert('上传失败', (e as Error).message);
    } finally {
      setUploading(false);
    }
  }, [form.images.length]);

  const handleRemoveImage = useCallback((index: number) => {
    setForm((prev) => {
      const next = [...prev.images];
      next.splice(index, 1);
      return { ...prev, images: next };
    });
  }, []);

  async function handleSave() {
    if (!form.title.trim()) {
      Alert.alert('提示', '请输入素材标题');
      return;
    }
    if (!form.description.trim()) {
      Alert.alert('提示', '请输入素材描述');
      return;
    }
    const price = parseFloat(form.price);
    if (!form.price.trim() || Number.isNaN(price) || price <= 0) {
      Alert.alert('提示', '请输入大于 0 的售价');
      return;
    }
    if (form.images.length === 0) {
      Alert.alert('提示', '请至少上传 1 张图片');
      return;
    }
    setSaving(true);
    try {
      await createMaterial({
        title: form.title.trim(),
        description: form.description.trim(),
        price,
        original_price: form.originalPrice.trim() ? parseFloat(form.originalPrice) : null,
        category: form.category.trim() || null,
        condition: form.condition,
        quantity: form.quantity.trim() ? parseInt(form.quantity, 10) || 1 : 1,
        images: form.images.map((i) => i.path),
        delivery_method: 'express',
        shipping_method: 'free',
        postage: 0,
      });
      Alert.alert('成功', '素材创建成功');
      setForm(EMPTY_MATERIAL_FORM);
      onCreated();
    } catch (e) {
      Alert.alert('创建失败', (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <KeyboardAvoidingView
        style={styles.modalOverlay}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <Pressable style={styles.modalBackdrop} onPress={onClose} />
        <View style={[styles.modalSheet, { backgroundColor: c.surface }]}>
          <View style={[styles.modalHandle, { backgroundColor: c.border }]} />
          <View style={styles.modalHeader}>
            <Text style={[styles.modalTitle, { color: c.text }]}>新建发布素材</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Text style={[styles.modalClose, { color: c.textMuted }]}>✕</Text>
            </Pressable>
          </View>

          <ScrollView
            style={styles.modalScroll}
            contentContainerStyle={styles.modalBody}
            keyboardShouldPersistTaps="handled"
          >
            <FieldLabel label="商品标题" required />
            <Input
              value={form.title}
              onChangeText={(v) => update('title', v)}
              placeholder="请输入商品标题（最多 200 字）"
              maxLength={200}
            />

            <FieldLabel label="商品描述" required />
            <Input
              value={form.description}
              onChangeText={(v) => update('description', v)}
              placeholder="请输入商品描述（最多 1500 字）"
              multiline
              numberOfLines={4}
              maxLength={1500}
              style={styles.textarea}
            />

            <View style={styles.row2}>
              <View style={styles.flex1}>
                <FieldLabel label="售价（元）" required />
                <Input
                  value={form.price}
                  onChangeText={(v) => {
                    if (v === '' || /^\d*\.?\d{0,2}$/.test(v)) update('price', v);
                  }}
                  placeholder="0.00"
                  keyboardType="decimal-pad"
                />
              </View>
              <View style={styles.flex1}>
                <FieldLabel label="原价（划线价）" />
                <Input
                  value={form.originalPrice}
                  onChangeText={(v) => {
                    if (v === '' || /^\d*\.?\d{0,2}$/.test(v)) update('originalPrice', v);
                  }}
                  placeholder="可选"
                  keyboardType="decimal-pad"
                />
              </View>
            </View>

            <FieldLabel label={`商品图片（${form.images.length}/${MAX_IMAGES}，至少 1 张）`} required />
            <ImageGrid images={form.images} uploading={uploading} onPick={handlePick} onRemove={handleRemoveImage} />

            <FieldLabel label="成色" />
            <View style={styles.chipRow}>
              {CONDITION_OPTIONS.map((opt) => {
                const on = form.condition === opt;
                return (
                  <Pressable
                    key={opt}
                    onPress={() => update('condition', opt)}
                    style={[
                      styles.chip,
                      {
                        borderColor: on ? c.primary : c.border,
                        backgroundColor: on ? c.primary : c.surface,
                      },
                    ]}
                  >
                    <Text style={[styles.chipText, { color: on ? '#FFFFFF' : c.text }]}>{opt}</Text>
                  </Pressable>
                );
              })}
            </View>

            <FieldLabel label="商品分类" />
            <Input
              value={form.category}
              onChangeText={(v) => update('category', v)}
              placeholder="可选，例如：数码产品/手机"
            />

            <FieldLabel label="发布数量" />
            <Input
              value={form.quantity}
              onChangeText={(v) => {
                if (v === '' || /^\d*$/.test(v)) update('quantity', v);
              }}
              placeholder="默认 1"
              keyboardType="number-pad"
            />
            <FieldHint text="批量发布时每个账号按此数量重复发布该素材。" />
          </ScrollView>

          <View style={[styles.modalFooter, { borderTopColor: c.border }]}>
            <Button label="取消" variant="ghost" onPress={onClose} style={styles.flex1} />
            <Button
              label="保存素材"
              onPress={handleSave}
              loading={saving}
              disabled={saving}
              style={styles.flex1}
            />
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

// ---------------------------------------------------------------------------
// Tab 3：发布记录（日志列表）
// ---------------------------------------------------------------------------

const LOG_PAGE_SIZE = 20;

function logStatusMeta(status: PublishLogItem['status']): { label: string; variant: 'success' | 'danger' | 'info' | 'gray' } {
  switch (status) {
    case 'success':
      return { label: '成功', variant: 'success' };
    case 'failed':
      return { label: '失败', variant: 'danger' };
    case 'publishing':
      return { label: '发布中', variant: 'info' };
    default:
      return { label: '等待', variant: 'gray' };
  }
}

function PublishLogsTab() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [logs, setLogs] = useState<PublishLogItem[]>([]);
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadLogs = useCallback(
    async (targetPage: number, status: string, opts?: { append?: boolean }) => {
      if (opts?.append) setLoadingMore(true);
      else setRefreshing(true);
      setError(null);
      try {
        const res = await getPublishLogs(targetPage, LOG_PAGE_SIZE, undefined, status || undefined);
        setLogs((prev) => (opts?.append ? [...prev, ...res.list] : res.list));
        setPage(res.page);
        setTotalPages(res.total_pages);
        setTotal(res.total);
      } catch (e) {
        setError((e as Error).message || '加载发布记录失败');
      } finally {
        setLoading(false);
        setRefreshing(false);
        setLoadingMore(false);
      }
    },
    [],
  );

  useEffect(() => {
    setLoading(true);
    loadLogs(1, statusFilter);
  }, [statusFilter, loadLogs]);

  const handleLoadMore = useCallback(() => {
    if (loadingMore || refreshing || loading) return;
    if (totalPages > 0 && page >= totalPages) return;
    loadLogs(page + 1, statusFilter, { append: true });
  }, [loadingMore, refreshing, loading, totalPages, page, statusFilter, loadLogs]);

  const renderItem = useCallback(
    ({ item }: { item: PublishLogItem }) => {
      const meta = logStatusMeta(item.status);
      return (
        <Card style={styles.logCard}>
          <View style={styles.logTop}>
            <Text style={[styles.logTitle, { color: c.text }]} numberOfLines={2}>
              {item.title || '无标题'}
            </Text>
            <Badge label={meta.label} variant={meta.variant} />
          </View>
          <View style={styles.logMeta}>
            <Text style={[styles.logMetaText, { color: c.textSecondary }]} numberOfLines={1}>
              账号 {item.account_id}
            </Text>
            {item.price ? (
              <Text style={[styles.logPrice, { color: c.warning }]}>¥{item.price}</Text>
            ) : null}
          </View>
          {item.error_message ? (
            <Text style={[styles.logError, { color: c.error }]} numberOfLines={3}>
              {item.error_message}
            </Text>
          ) : null}
          {item.item_id ? (
            <Text style={[styles.logMetaText, { color: c.textMuted }]} numberOfLines={1}>
              商品ID：{item.item_id}
            </Text>
          ) : null}
          <Text style={[styles.logTime, { color: c.textMuted }]}>{item.created_at}</Text>
        </Card>
      );
    },
    [c],
  );

  return (
    <View style={styles.flex}>
      {/* 状态筛选 */}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRowScroll}>
        {LOG_STATUS_FILTERS.map((f) => {
          const on = statusFilter === f.key;
          return (
            <Pressable
              key={f.key}
              onPress={() => setStatusFilter(f.key)}
              style={[
                styles.chip,
                {
                  borderColor: on ? c.primary : c.border,
                  backgroundColor: on ? c.primary : c.surface,
                },
              ]}
            >
              <Text style={[styles.chipText, { color: on ? '#FFFFFF' : c.text }]}>{f.label}</Text>
            </Pressable>
          );
        })}
      </ScrollView>

      <FlatList
        data={logs}
        keyExtractor={(item) => String(item.id)}
        renderItem={renderItem}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadLogs(1, statusFilter)} />}
        contentContainerStyle={styles.logList}
        onEndReached={handleLoadMore}
        onEndReachedThreshold={0.3}
        ListEmptyComponent={
          error ? (
            <EmptyState
              icon={Package}
              title="加载失败"
              message={error}
              error
              onRetry={() => loadLogs(1, statusFilter)}
            />
          ) : (
            <EmptyState icon={Package} title="暂无发布记录" message="单品或批量发布后会在这里生成记录" />
          )
        }
        ListFooterComponent={
          loadingMore ? (
            <View style={styles.center}>
              <ActivityIndicator size="small" color={c.primary} />
            </View>
          ) : logs.length > 0 && page >= totalPages && totalPages > 0 ? (
            <Text style={[styles.footerText, { color: c.textMuted }]}>
              共 {total} 条，没有更多了
            </Text>
          ) : null
        }
      />
    </View>
  );
}

// ---------------------------------------------------------------------------
// 样式
// ---------------------------------------------------------------------------

// Input 的 style 为 StyleProp<TextStyle>，自定义样式对象按 TextStyle 收窄
type InputStyle = TextStyle;

const styles = StyleSheet.create({
  container: { flex: 1 },
  flex: { flex: 1 },

  // 分段控件
  tabs: {
    flexDirection: 'row',
    marginHorizontal: spacing.lg,
    marginTop: spacing.sm,
    marginBottom: spacing.xs,
    borderRadius: radius.md,
    padding: 2,
  },
  tabItem: {
    flex: 1,
    height: 34,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tabText: { fontSize: 13, fontWeight: '600' },

  // 表单
  formBody: { padding: spacing.lg, gap: spacing.xs, paddingBottom: 120 },
  row2: { flexDirection: 'row', gap: spacing.sm },
  flex1: { flex: 1 },
  fieldLabel: { flexDirection: 'row', alignItems: 'center', marginTop: spacing.sm },
  fieldLabelText: { ...typography.caption, fontWeight: '500' },
  required: { color: '#EF4444', fontSize: 14 },
  fieldHint: { ...typography.small, lineHeight: 16 },
  labelActionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginTop: spacing.sm,
    paddingRight: spacing.xs,
  },
  linkText: { ...typography.caption, fontWeight: '600' },
  textarea: { minHeight: 90, textAlignVertical: 'top' } as InputStyle,
  submitBtn: { marginTop: spacing.lg },

  // 胶囊
  chipRowScroll: { gap: spacing.sm, paddingVertical: spacing.xs },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.xs },
  chip: {
    paddingHorizontal: spacing.md,
    height: 32,
    borderRadius: radius.full,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
    maxWidth: 160,
  },
  chipText: { fontSize: 13, fontWeight: '500' },

  // 图片九宫格
  imageGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, marginTop: spacing.xs },
  imageCell: { width: 88, height: 88, position: 'relative' },
  thumb: { width: '100%', height: '100%', borderRadius: radius.md },
  imageDel: {
    position: 'absolute',
    top: -6,
    right: -6,
    width: 22,
    height: 22,
    borderRadius: 11,
    alignItems: 'center',
    justifyContent: 'center',
  },
  imageIndex: {
    position: 'absolute',
    bottom: 4,
    left: 4,
    backgroundColor: 'rgba(0,0,0,0.5)',
    borderRadius: 4,
    paddingHorizontal: 4,
  },
  imageIndexText: { color: '#FFFFFF', fontSize: 10, fontWeight: '600' },
  imageAdd: {
    width: 88,
    height: 88,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'dashed',
    alignItems: 'center',
    justifyContent: 'center',
  },
  imageAddText: { ...typography.small, marginTop: 2 },

  // 批量发布
  sectionBar: {
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.xs,
    paddingBottom: spacing.sm,
    borderBottomWidth: 1,
  },
  materialHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xs,
  },
  materialTitle: { ...typography.heading, flexShrink: 1 },
  materialList: { padding: spacing.lg, paddingTop: spacing.xs, gap: spacing.md, paddingBottom: 120 },
  materialCard: { padding: spacing.md },
  materialRow: { flexDirection: 'row', gap: spacing.md, alignItems: 'center' },
  materialThumb: {
    width: 52,
    height: 52,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  materialBody: { flex: 1, gap: spacing.xs },
  materialName: { ...typography.caption, fontWeight: '600', lineHeight: 18 },
  materialMeta: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  materialPrice: { ...typography.small, fontWeight: '700' },
  materialMetaText: { ...typography.small },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkboxText: { color: '#FFFFFF', fontSize: 13, fontWeight: '700' },

  // 批量进度
  progressCard: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
    padding: spacing.md,
    gap: spacing.sm,
  },
  progressHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  progressTitle: { ...typography.caption, fontWeight: '600' },
  progressPercent: { ...typography.heading },
  progressTrack: { height: 8, borderRadius: 4, overflow: 'hidden' },
  progressFill: { height: '100%', borderRadius: 4 },
  progressStats: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: spacing.sm },
  statText: { ...typography.small, flexShrink: 1 },
  pollingRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  pollingText: { ...typography.small },
  progressWaiting: { ...typography.small },
  pollError: { ...typography.small },
  accountStatusRow: { borderTopWidth: 1, paddingTop: spacing.sm, gap: 2 },
  accountStatusId: { ...typography.small, fontWeight: '600' },
  accountStatusText: { ...typography.small },
  syncMessage: { ...typography.small },

  // 底部提交
  footer: {
    flexDirection: 'row',
    gap: spacing.sm,
    padding: spacing.lg,
    borderTopWidth: 1,
  },

  // 弹窗
  modalOverlay: { flex: 1, justifyContent: 'flex-end' },
  modalBackdrop: { flex: 1, backgroundColor: 'rgba(0,0,0,0.4)' },
  modalSheet: {
    maxHeight: '88%',
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    overflow: 'hidden',
    flexDirection: 'column',
  },
  modalHandle: { width: 36, height: 4, borderRadius: 2, alignSelf: 'center', marginTop: spacing.sm },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  modalTitle: { ...typography.heading },
  modalClose: { fontSize: 22, paddingHorizontal: spacing.xs },
  modalScroll: { flex: 1, paddingHorizontal: spacing.lg },
  modalBody: { paddingBottom: spacing.lg, gap: spacing.xs },
  modalFooter: {
    flexDirection: 'row',
    gap: spacing.sm,
    padding: spacing.lg,
    borderTopWidth: 1,
  },

  // 发布记录
  logList: { padding: spacing.lg, paddingTop: spacing.xs, gap: spacing.md, paddingBottom: 120 },
  logCard: { gap: spacing.xs },
  logTop: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between', gap: spacing.sm },
  logTitle: { ...typography.caption, fontWeight: '600', flexShrink: 1, lineHeight: 20 },
  logMeta: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  logMetaText: { ...typography.small, flexShrink: 1 },
  logPrice: { ...typography.small, fontWeight: '700' },
  logError: { ...typography.small },
  logTime: { ...typography.small },
  center: { paddingVertical: spacing.lg, alignItems: 'center' },
  footerText: { ...typography.small, textAlign: 'center', paddingVertical: spacing.md },
});
