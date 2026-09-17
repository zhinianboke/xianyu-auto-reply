import { useState, useEffect, useCallback, type ReactNode } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  Switch,
  Image,
  Alert,
  ActivityIndicator,
  FlatList,
  TextInput,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import * as ImagePicker from 'expo-image-picker';
import { ChevronDown, ChevronRight, Trash2, Package, Plus } from 'lucide-react-native';
import { Card, Button, Input, Loading, FormModal } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getMaterial,
  createMaterial,
  updateMaterial,
  collectFromItem,
  uploadProductImages,
  type MaterialCreateParams,
  type MaterialItemConfig,
  type CollectedMaterialDraft,
} from '@/api/wrappers/product-publish';
import { getCards, searchXianyuItems, type Card as CardModel } from '@/api/wrappers/products';
import { getAccountOptions, type AccountOption } from '@/api/wrappers/accounts';
import type { XianyuItem } from '@/api/wrappers/items';
import {
  type QueryButtonDraft,
  emptyDraft,
  draftFromButton,
  serializeQueryButtons,
} from '@/lib/query-button-draft';

const MAX_IMAGES = 9;
const CONDITION_OPTIONS = ['全新', '几乎全新', '轻微使用', '明显使用', '需要维修'];

/** 已选本地/服务器图片：uri 供预览，path 是服务器路径供发布提交 */
interface LocalImage {
  uri: string;
  path: string;
}

type SectionKey = 'basic' | 'config';

/** 折叠卡片：标题行 + 展开指示箭头，内容条件渲染（对齐 item-edit.tsx 样式） */
function CollapsibleSection({
  title,
  expanded,
  onToggle,
  children,
}: {
  title: string;
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  return (
    <Card style={styles.collapsibleCard}>
      <Pressable
        onPress={onToggle}
        style={({ pressed }) => [styles.sectionHeader, { opacity: pressed ? 0.7 : 1 }]}
      >
        <Text style={[styles.sectionTitle, { color: c.text }]}>{title}</Text>
        {expanded ? (
          <ChevronDown size={18} stroke={c.textMuted} />
        ) : (
          <ChevronRight size={18} stroke={c.textMuted} />
        )}
      </Pressable>
      {expanded ? (
        <View style={[styles.sectionBody, { borderTopColor: c.borderLight }]}>{children}</View>
      ) : null}
    </Card>
  );
}

function accountLabel(acc: AccountOption): string {
  return acc.remark || acc.id;
}

export default function MaterialEditScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();
  const { id } = useLocalSearchParams<{ id?: string }>();
  const materialId = id != null ? Number(id) : NaN;
  const isEdit = Number.isFinite(materialId);

  const [loading, setLoading] = useState(isEdit);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);

  // 基础信息
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [price, setPrice] = useState('');
  const [originalPrice, setOriginalPrice] = useState('');
  const [category, setCategory] = useState('');
  const [condition, setCondition] = useState('全新');
  const [quantity, setQuantity] = useState('1');
  const [images, setImages] = useState<LocalImage[]>([]);

  // 商品列表配置（item_config）
  const [cfgMultiQty, setCfgMultiQty] = useState(false);
  const [cfgCardIds, setCfgCardIds] = useState<number[]>([]);
  const [cfgDefaultReply, setCfgDefaultReply] = useState('');
  const [cfgAiPrompt, setCfgAiPrompt] = useState('');
  const [queryDrafts, setQueryDrafts] = useState<QueryButtonDraft[]>([]);

  // 折叠态：新建默认展开基础信息
  const [expanded, setExpanded] = useState<Record<SectionKey, boolean>>({
    basic: true,
    config: false,
  });

  // 卡券列表（配置区展开时加载，供多选）
  const [cards, setCards] = useState<CardModel[]>([]);
  const [cardsLoaded, setCardsLoaded] = useState(false);

  // 采集弹窗
  const [pickerVisible, setPickerVisible] = useState(false);
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [collecting, setCollecting] = useState(false);

  const toggleSection = (key: SectionKey) => {
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
    if (key === 'config' && !cardsLoaded) loadCards();
  };

  const loadCards = useCallback(async () => {
    try {
      const list = await getCards();
      setCards(list);
    } catch {
      // 卡券加载失败不阻塞表单，多选区为空即可
    } finally {
      setCardsLoaded(true);
    }
  }, []);

  // 编辑模式：加载素材详情（含 item_config 全量配置）
  useEffect(() => {
    if (!isEdit) return;
    let alive = true;
    (async () => {
      try {
        const m = await getMaterial(materialId);
        if (!alive) return;
        setTitle(m.title ?? '');
        setDescription(m.description ?? '');
        setPrice(m.price != null ? String(m.price) : '');
        setOriginalPrice(m.original_price != null ? String(m.original_price) : '');
        setCategory(m.category ?? '');
        setCondition(m.condition || '全新');
        setQuantity(m.quantity != null ? String(m.quantity) : '1');
        setImages(
          (m.images ?? []).map((p) => ({ uri: p, path: p })),
        );
        const cfg = m.item_config;
        if (cfg) {
          setCfgMultiQty(Boolean(cfg.multi_quantity_delivery));
          setCfgCardIds(cfg.card_ids ?? []);
          setCfgDefaultReply(cfg.default_reply ?? '');
          setCfgAiPrompt(cfg.ai_prompt ?? '');
          setQueryDrafts((cfg.query_buttons ?? []).map(draftFromButton));
        }
      } catch (e) {
        Alert.alert('加载素材失败', (e as Error).message);
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [isEdit, materialId]);

  // 采集弹窗打开时加载账号
  useEffect(() => {
    if (!pickerVisible) return;
    if (accounts.length === 0) {
      getAccountOptions()
        .then(setAccounts)
        .catch(() => {});
    }
  }, [pickerVisible, accounts.length]);

  const handlePickImages = useCallback(async () => {
    const remaining = MAX_IMAGES - images.length;
    if (remaining <= 0) return;
    try {
      setUploading(true);
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ['images'],
        allowsMultipleSelection: true,
        selectionLimit: remaining,
        quality: 0.8,
      });
      if (result.canceled || !result.assets || result.assets.length === 0) return;
      const picked = result.assets.slice(0, remaining);
      const uploaded = await uploadProductImages(picked.map((a) => a.uri));
      const next: LocalImage[] = picked
        .map((a, i) => ({ uri: a.uri, path: uploaded.paths[i] }))
        .filter((x) => Boolean(x.path));
      if (next.length > 0) setImages((prev) => [...prev, ...next]);
    } catch (e) {
      Alert.alert('上传失败', (e as Error).message);
    } finally {
      setUploading(false);
    }
  }, [images.length]);

  const removeImage = (index: number) => {
    setImages((prev) => {
      const next = [...prev];
      next.splice(index, 1);
      return next;
    });
  };

  /** 从商品列表项采集：填充基础信息 + 配置区 */
  const handleCollect = useCallback(
    async (itemId: string) => {
      setPickerVisible(false);
      setCollecting(true);
      try {
        const draft = await collectFromItem(itemId);
        if (draft.title) setTitle(draft.title);
        if (draft.description) setDescription(draft.description);
        if (draft.price != null && draft.price !== '') setPrice(String(draft.price));
        if (draft.original_price != null) setOriginalPrice(String(draft.original_price));
        if (draft.category) setCategory(draft.category);
        if (draft.condition) setCondition(draft.condition);
        if (draft.quantity != null) setQuantity(String(draft.quantity));
        if (Array.isArray(draft.images) && draft.images.length > 0) {
          setImages(draft.images.map((p) => ({ uri: p, path: p })));
        }
        const cfg = draft.item_config;
        if (cfg) {
          setCfgMultiQty(Boolean(cfg.multi_quantity_delivery));
          setCfgCardIds(cfg.card_ids ?? []);
          setCfgDefaultReply(cfg.default_reply ?? '');
          setCfgAiPrompt(cfg.ai_prompt ?? '');
          setQueryDrafts((cfg.query_buttons ?? []).map(draftFromButton));
        }
        setExpanded({ basic: true, config: true });
        Alert.alert('采集成功', '已从商品列表项填充素材与配置，请核对后保存');
      } catch (e) {
        Alert.alert('采集失败', (e as Error).message);
      } finally {
        setCollecting(false);
      }
    },
    [],
  );

  function buildItemConfig(): MaterialItemConfig {
    return {
      multi_quantity_delivery: cfgMultiQty,
      card_ids: cfgCardIds,
      default_reply: cfgDefaultReply,
      ai_prompt: cfgAiPrompt,
      query_buttons: serializeQueryButtons(queryDrafts),
    };
  }

  async function handleSave() {
    if (!title.trim()) {
      Alert.alert('提示', '请输入素材标题');
      return;
    }
    if (!description.trim()) {
      Alert.alert('提示', '请输入素材描述');
      return;
    }
    const priceNum = parseFloat(price);
    if (!price.trim() || Number.isNaN(priceNum) || priceNum <= 0) {
      Alert.alert('提示', '请输入大于 0 的售价');
      return;
    }
    if (images.length === 0) {
      Alert.alert('提示', '请至少上传 1 张图片');
      return;
    }
    let originalNum: number | null = null;
    if (originalPrice.trim()) {
      originalNum = parseFloat(originalPrice);
      if (Number.isNaN(originalNum) || originalNum < 0) {
        Alert.alert('提示', '请输入正确的原价');
        return;
      }
    }
    const qtyNum = quantity.trim() ? parseInt(quantity, 10) || 1 : 1;

    let itemConfig: MaterialItemConfig;
    try {
      itemConfig = buildItemConfig();
    } catch (e) {
      Alert.alert('请检查查询配置', (e as Error).message);
      return;
    }

    setSaving(true);
    try {
      const paths = images.map((i) => i.path);
      if (isEdit) {
        await updateMaterial(materialId, {
          title: title.trim(),
          description: description.trim(),
          price: priceNum,
          original_price: originalNum,
          category: category.trim() || null,
          condition,
          quantity: qtyNum,
          images: paths,
          item_config: itemConfig,
        });
        Alert.alert('保存成功', '素材已更新', [
          { text: '确定', onPress: () => router.back() },
        ]);
      } else {
        const params: MaterialCreateParams = {
          title: title.trim(),
          description: description.trim(),
          price: priceNum,
          original_price: originalNum,
          category: category.trim() || null,
          condition,
          quantity: qtyNum,
          images: paths,
          delivery_method: 'express',
          shipping_method: 'free',
          postage: 0,
          item_config: itemConfig,
        };
        await createMaterial(params);
        Alert.alert('创建成功', '素材已创建', [
          { text: '确定', onPress: () => router.back() },
        ]);
      }
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载素材..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <ScrollView
        contentContainerStyle={styles.list}
        keyboardShouldPersistTaps="handled"
      >
        {/* 基础信息 */}
        <CollapsibleSection
          title="基础信息"
          expanded={expanded.basic}
          onToggle={() => toggleSection('basic')}
        >
          <View style={styles.group}>
            <Text style={[styles.label, { color: c.textSecondary }]}>标题</Text>
            <Input
              value={title}
              onChangeText={setTitle}
              maxLength={200}
              placeholder="请输入商品标题"
            />

            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
              描述
            </Text>
            <Input
              value={description}
              onChangeText={setDescription}
              maxLength={5000}
              multiline
              placeholder="请输入商品描述"
              style={styles.descriptionInput}
            />
          </View>

          <View style={styles.group}>
            <Text style={[styles.label, { color: c.textSecondary }]}>价格（元）</Text>
            <Input
              value={price}
              onChangeText={setPrice}
              keyboardType="decimal-pad"
              placeholder="0.00"
            />

            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
              原价（元，选填）
            </Text>
            <Input
              value={originalPrice}
              onChangeText={setOriginalPrice}
              keyboardType="decimal-pad"
              placeholder="0.00"
            />

            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
              分类
            </Text>
            <Input
              value={category}
              onChangeText={setCategory}
              placeholder="可选，例如：数码产品/手机"
            />

            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
              成色
            </Text>
            <View style={styles.chipRow}>
              {CONDITION_OPTIONS.map((opt) => {
                const on = condition === opt;
                return (
                  <Pressable
                    key={opt}
                    onPress={() => setCondition(opt)}
                    style={[
                      styles.chip,
                      {
                        backgroundColor: on ? c.primary : c.background,
                        borderColor: on ? c.primary : c.border,
                      },
                    ]}
                  >
                    <Text style={[styles.chipText, { color: on ? '#FFF' : c.text }]}>{opt}</Text>
                  </Pressable>
                );
              })}
            </View>

            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
              发布数量
            </Text>
            <Input
              value={quantity}
              onChangeText={setQuantity}
              keyboardType="number-pad"
              placeholder="默认 1"
            />
          </View>

          <View style={styles.group}>
            <Text style={[styles.label, { color: c.textSecondary }]}>
              商品图片（{images.length}/{MAX_IMAGES}，至少 1 张）
            </Text>
            <View style={styles.imageGrid}>
              {images.map((img, index) => (
                <View key={`${img.uri}-${index}`} style={styles.imageCell}>
                  <Image
                    source={{ uri: img.uri }}
                    style={[styles.thumb, { backgroundColor: c.surfaceAlt }]}
                  />
                  <Pressable
                    onPress={() => removeImage(index)}
                    style={[styles.imageDel, { backgroundColor: c.error }]}
                    hitSlop={8}
                  >
                    <Text style={styles.imageDelText}>×</Text>
                  </Pressable>
                </View>
              ))}
              {images.length < MAX_IMAGES && (
                <Pressable
                  onPress={handlePickImages}
                  style={[styles.imageAdd, { borderColor: c.border }]}
                  disabled={uploading}
                >
                  {uploading ? (
                    <ActivityIndicator size="small" color={c.primary} />
                  ) : (
                    <>
                      <Plus color={c.textMuted} size={22} />
                      <Text style={[styles.imageAddText, { color: c.textMuted }]}>添加</Text>
                    </>
                  )}
                </Pressable>
              )}
            </View>
          </View>
        </CollapsibleSection>

        {/* 商品列表配置（item_config）：发布回写的数据源 */}
        <CollapsibleSection
          title="商品列表配置"
          expanded={expanded.config}
          onToggle={() => toggleSection('config')}
        >
          <Text style={[styles.hintText, { color: c.textMuted }]}>
            此配置随素材保存，发布成功后一步回写到新商品列表项（多数量发货 / 卡券 / 默认回复 / AI提示 / 查询按钮）。
          </Text>

          {/* 从商品列表采集 */}
          <Button
            label={collecting ? '采集中...' : '从商品列表采集'}
            variant="secondary"
            onPress={() => setPickerVisible(true)}
            loading={collecting}
            disabled={collecting || uploading}
            style={styles.collectBtn}
          />

          <View style={[styles.switchRowNoBorder, { marginTop: spacing.md }]}>
            <Text style={[styles.switchLabel, { color: c.text }]}>多数量发货</Text>
            <Switch
              value={cfgMultiQty}
              onValueChange={setCfgMultiQty}
              trackColor={{ false: c.border, true: c.primary }}
            />
          </View>

          {/* 关联卡券：多选 */}
          <View style={[styles.group, { marginTop: spacing.sm }]}>
            <Text style={[styles.label, { color: c.textSecondary }]}>
              关联卡券（{cfgCardIds.length}）
            </Text>
            {!cardsLoaded ? (
              <ActivityIndicator color={c.primary} style={styles.inlineLoading} />
            ) : cards.length === 0 ? (
              <Text style={[styles.emptyText, { color: c.textMuted }]}>暂无卡券</Text>
            ) : (
              <View style={styles.chipRow}>
                {cards.map((card) => {
                  const on = cfgCardIds.includes(card.id);
                  return (
                    <Pressable
                      key={card.id}
                      onPress={() =>
                        setCfgCardIds((prev) =>
                          on ? prev.filter((x) => x !== card.id) : [...prev, card.id],
                        )
                      }
                      style={[
                        styles.chip,
                        {
                          backgroundColor: on ? c.primary : c.background,
                          borderColor: on ? c.primary : c.border,
                        },
                      ]}
                    >
                      <Text style={[styles.chipText, { color: on ? '#FFF' : c.text }]} numberOfLines={1}>
                        {on ? '✓ ' : ''}
                        {card.name || card.remark || `#${card.id}`}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            )}
          </View>

          {/* 默认回复 */}
          <View style={styles.group}>
            <Text style={[styles.label, { color: c.textSecondary }]}>默认回复</Text>
            <Input
              value={cfgDefaultReply}
              onChangeText={setCfgDefaultReply}
              multiline
              placeholder="买家首次咨询时自动回复的内容"
              style={styles.textArea}
            />
          </View>

          {/* AI 提示词 */}
          <View style={styles.group}>
            <Text style={[styles.label, { color: c.textSecondary }]}>AI 提示词</Text>
            <Input
              value={cfgAiPrompt}
              onChangeText={setCfgAiPrompt}
              multiline
              placeholder="针对本商品的 AI 回复提示词"
              style={styles.textArea}
            />
          </View>

          {/* 查询按钮：内嵌编辑，格式与商品编辑页一致 */}
          <View style={styles.group}>
            <Text style={[styles.label, { color: c.textSecondary }]}>
              查询按钮（{queryDrafts.length}）
            </Text>
            <Text style={[styles.hintText, { color: c.textMuted }]}>
              买家在发货页点击按钮后，由服务端代为请求并展示结果。可用变量：{'{cookie}'} {'{account}'} {'{api_key}'} {'{line}'}。
            </Text>

            {queryDrafts.map((draft, idx) => (
              <View
                key={draft.key}
                style={[styles.queryCard, { borderColor: c.border, backgroundColor: c.background }]}
              >
                <View style={styles.queryCardHeader}>
                  <Text style={[styles.queryCardTitle, { color: c.text }]}>
                    按钮 {idx + 1}
                  </Text>
                  <Pressable
                    onPress={() => setQueryDrafts((prev) => prev.filter((d) => d.key !== draft.key))}
                    style={({ pressed }) => [{ opacity: pressed ? 0.6 : 1 }, styles.queryDelete]}
                  >
                    <Trash2 size={16} stroke={c.error} />
                    <Text style={[styles.queryDeleteText, { color: c.error }]}>删除</Text>
                  </Pressable>
                </View>

                <Text style={[styles.label, { color: c.textSecondary }]}>按钮名称</Text>
                <Input
                  value={draft.name}
                  onChangeText={(v) => updateQueryDraft(draft.key, { name: v })}
                  placeholder="如：查余额"
                />

                <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
                  请求方法
                </Text>
                <View style={styles.chipRow}>
                  {(['GET', 'POST'] as const).map((m) => {
                    const on = draft.method === m;
                    return (
                      <Pressable
                        key={m}
                        onPress={() => updateQueryDraft(draft.key, { method: m })}
                        style={[
                          styles.chip,
                          { backgroundColor: on ? c.primary : c.surface, borderColor: on ? c.primary : c.border },
                        ]}
                      >
                        <Text style={[styles.chipText, { color: on ? '#FFF' : c.text }]}>{m}</Text>
                      </Pressable>
                    );
                  })}
                </View>

                <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>URL</Text>
                <Input
                  value={draft.url}
                  onChangeText={(v) => updateQueryDraft(draft.key, { url: v })}
                  autoCapitalize="none"
                  keyboardType="url"
                  placeholder="https://example.com/api"
                />

                <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
                  请求头（每行 Key: Value）
                </Text>
                <Input
                  value={draft.headersText}
                  onChangeText={(v) => updateQueryDraft(draft.key, { headersText: v })}
                  multiline
                  autoCapitalize="none"
                  placeholder={'Cookie: {cookie}'}
                  style={styles.textAreaSmall}
                />

                {draft.method === 'POST' ? (
                  <>
                    <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
                      POST Body（支持变量）
                    </Text>
                    <Input
                      value={draft.body}
                      onChangeText={(v) => updateQueryDraft(draft.key, { body: v })}
                      multiline
                      autoCapitalize="none"
                      placeholder='{"account": "{account}"}'
                      style={styles.textAreaSmall}
                    />
                  </>
                ) : null}

                <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
                  成功条件（可空，都空则 HTTP 2xx 即成功）
                </Text>
                <View style={styles.skuInputs}>
                  <Input
                    value={draft.successPath}
                    onChangeText={(v) => updateQueryDraft(draft.key, { successPath: v })}
                    autoCapitalize="none"
                    placeholder="路径，如 code"
                    style={styles.skuInput}
                  />
                  <Input
                    value={draft.successValue}
                    onChangeText={(v) => updateQueryDraft(draft.key, { successValue: v })}
                    autoCapitalize="none"
                    placeholder="期望值，如 0"
                    style={styles.skuInput}
                  />
                </View>

                <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
                  错误消息路径（可空）
                </Text>
                <Input
                  value={draft.errorPath}
                  onChangeText={(v) => updateQueryDraft(draft.key, { errorPath: v })}
                  autoCapitalize="none"
                  placeholder="如 message"
                />

                <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
                  结果字段（每行 标签=路径）
                </Text>
                <Input
                  value={draft.fieldsText}
                  onChangeText={(v) => updateQueryDraft(draft.key, { fieldsText: v })}
                  multiline
                  autoCapitalize="none"
                  placeholder={'可用余额=data.availableBalanceCny|¥*\n账户状态=data.status'}
                  style={styles.textAreaSmall}
                />
                <Text style={[styles.hintText, { color: c.textMuted }]}>
                  行尾加 * 表示主结果高亮；| 后为前缀（如 ¥）
                </Text>
              </View>
            ))}

            <Button
              label="添加查询按钮"
              variant="secondary"
              onPress={() => setQueryDrafts((prev) => [...prev, emptyDraft()])}
              style={styles.cardActionBtn}
            />
          </View>
        </CollapsibleSection>

        <Button
          label={saving ? '保存中...' : '保存素材'}
          onPress={handleSave}
          loading={saving}
          disabled={saving || uploading}
          style={styles.saveBtn}
        />
      </ScrollView>

      {/* 从商品列表采集：选账号 → 选商品 → collectFromItem */}
      <CollectPicker
        visible={pickerVisible}
        accounts={accounts}
        onClose={() => setPickerVisible(false)}
        onSelect={handleCollect}
      />
    </SafeAreaView>
  );

  function updateQueryDraft(key: string, patch: Partial<QueryButtonDraft>) {
    setQueryDrafts((prev) => prev.map((d) => (d.key === key ? { ...d, ...patch } : d)));
  }
}

// ---------------------------------------------------------------------------
// 采集弹窗：账号下拉 + 商品关键字搜索 + 列表选择
// ---------------------------------------------------------------------------

function CollectPicker({
  visible,
  accounts,
  onClose,
  onSelect,
}: {
  visible: boolean;
  accounts: AccountOption[];
  onClose: () => void;
  onSelect: (itemId: string) => void;
}) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [accountId, setAccountId] = useState('');
  const [keyword, setKeyword] = useState('');
  const [items, setItems] = useState<XianyuItem[]>([]);
  const [loading, setLoading] = useState(false);

  const loadItems = useCallback(async () => {
    if (!accountId) return;
    setLoading(true);
    try {
      const res = await searchXianyuItems(1, 30, { cookieId: accountId, keyword: keyword.trim() || undefined });
      setItems(res.items);
    } catch (e) {
      Alert.alert('加载商品失败', (e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [accountId, keyword]);

  // 切账号或提交关键字时刷新
  useEffect(() => {
    if (visible && accountId) loadItems();
    if (visible && !accountId) setItems([]);
  }, [visible, accountId, loadItems]);

  const renderItem = ({ item }: { item: XianyuItem }) => (
    <Pressable
      onPress={() => onSelect(item.item_id)}
      style={({ pressed }) => [styles.pickRow, { opacity: pressed ? 0.7 : 1 }]}
    >
      {item.image ? (
        <Image source={{ uri: item.image }} style={[styles.pickThumb, { backgroundColor: c.surfaceAlt }]} />
      ) : (
        <View style={[styles.pickThumb, { backgroundColor: c.surfaceAlt }]}>
          <Package size={16} stroke={c.textMuted} />
        </View>
      )}
      <View style={styles.pickBody}>
        <Text style={[styles.pickTitle, { color: c.text }]} numberOfLines={2}>
          {item.title || '未命名商品'}
        </Text>
        <Text style={[styles.pickMeta, { color: c.warning }]}>¥{item.price}</Text>
      </View>
      <ChevronRight size={18} stroke={c.textMuted} />
    </Pressable>
  );

  return (
    <FormModal visible={visible} onClose={onClose} title="从商品列表采集" contentStyle={styles.pickerSheet}>
      {/* 账号下拉（横向胶囊） */}
      <Text style={[styles.label, { color: c.textSecondary }]}>选择账号</Text>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.chipRowScroll}>
        {accounts.length === 0 ? (
          <Text style={[styles.emptyText, { color: c.textMuted }]}>暂无账号</Text>
        ) : (
          accounts.map((acc) => {
            const on = accountId === acc.id;
            return (
              <Pressable
                key={acc.id}
                onPress={() => setAccountId(acc.id)}
                style={[
                  styles.chip,
                  { backgroundColor: on ? c.primary : c.surface, borderColor: on ? c.primary : c.border },
                ]}
              >
                <Text style={[styles.chipText, { color: on ? '#FFF' : c.text }]} numberOfLines={1}>
                  {accountLabel(acc)}
                </Text>
              </Pressable>
            );
          })
        )}
      </ScrollView>

      {/* 关键字搜索 */}
      <View style={[styles.searchRow, { borderColor: c.border, backgroundColor: c.background }]}>
        <TextInput
          value={keyword}
          onChangeText={setKeyword}
          placeholder="搜索商品标题/ID"
          placeholderTextColor={c.textMuted}
          style={[styles.searchInput, { color: c.text }]}
          onSubmitEditing={loadItems}
          returnKeyType="search"
        />
        <Pressable onPress={loadItems} hitSlop={8}>
          <Text style={[styles.linkText, { color: c.primary }]}>搜索</Text>
        </Pressable>
      </View>

      {loading ? (
        <ActivityIndicator color={c.primary} style={styles.inlineLoading} />
      ) : items.length === 0 ? (
        <Text style={[styles.emptyText, { color: c.textMuted, paddingVertical: spacing.lg }]}>
          {accountId ? '未找到商品，可调整关键字后搜索' : '请先选择账号'}
        </Text>
      ) : (
        <FlatList
          data={items}
          keyExtractor={(item) => item.item_id}
          renderItem={renderItem}
          style={styles.pickList}
          contentContainerStyle={styles.pickListContent}
          ItemSeparatorComponent={() => <View style={{ height: spacing.xs }} />}
        />
      )}
    </FormModal>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  list: { padding: spacing.lg, gap: spacing.md, paddingBottom: 100 },
  collapsibleCard: { padding: 0, overflow: 'hidden' },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.md,
  },
  sectionTitle: { ...typography.body, fontWeight: '600' },
  sectionBody: {
    borderTopWidth: 1,
    paddingHorizontal: spacing.md,
    paddingBottom: spacing.md,
    paddingTop: spacing.sm,
  },
  group: { gap: spacing.xs, marginTop: spacing.sm },
  label: { ...typography.caption },
  descriptionInput: { minHeight: 100, textAlignVertical: 'top' },
  textArea: { minHeight: 100, textAlignVertical: 'top', paddingVertical: spacing.sm },
  textAreaSmall: { minHeight: 72, textAlignVertical: 'top', paddingVertical: spacing.sm },
  hintText: { ...typography.small, paddingVertical: spacing.xs, lineHeight: 18 },
  emptyText: { ...typography.caption, paddingVertical: spacing.sm },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, paddingVertical: spacing.xs },
  chipRowScroll: { gap: spacing.sm, paddingVertical: spacing.xs },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  chipText: { ...typography.caption },
  switchRowNoBorder: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.sm,
  },
  switchLabel: { ...typography.body },
  collectBtn: { marginTop: spacing.md },
  cardActionBtn: { marginTop: spacing.sm },
  saveBtn: { marginTop: spacing.md },
  inlineLoading: { marginVertical: spacing.lg },
  // 图片九宫格
  imageGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, paddingVertical: spacing.xs },
  imageCell: { width: 80, height: 80, position: 'relative' },
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
  imageDelText: { color: '#FFFFFF', fontSize: 14, fontWeight: '700' },
  imageAdd: {
    width: 80,
    height: 80,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'dashed',
    alignItems: 'center',
    justifyContent: 'center',
  },
  imageAddText: { ...typography.small, marginTop: 2 },
  // 查询按钮卡片
  queryCard: {
    marginTop: spacing.sm,
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
  },
  queryCardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: spacing.sm,
  },
  queryCardTitle: { ...typography.caption, fontWeight: '600' },
  queryDelete: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  queryDeleteText: { ...typography.small },
  skuInputs: { flexDirection: 'row', gap: spacing.sm },
  skuInput: { flex: 1 },
  // 采集弹窗
  pickerSheet: { maxHeight: '88%' },
  searchRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    marginTop: spacing.xs,
  },
  searchInput: { flex: 1, minHeight: 44, paddingVertical: 4 },
  linkText: { ...typography.caption, fontWeight: '600', paddingHorizontal: spacing.xs },
  pickList: { marginTop: spacing.xs },
  pickListContent: { paddingBottom: spacing.lg },
  pickRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.sm,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  pickThumb: {
    width: 44,
    height: 44,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pickBody: { flex: 1, gap: 2 },
  pickTitle: { ...typography.small, fontWeight: '500', lineHeight: 16 },
  pickMeta: { ...typography.small, fontWeight: '700' },
});
