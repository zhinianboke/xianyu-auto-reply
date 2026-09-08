import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Switch,
  Alert,
  Modal,
  RefreshControl,
  ScrollView,
  KeyboardAvoidingView,
  Platform,
  Image,
  type TextStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { Card, Button, Input, Loading, EmptyState, Badge, FilterTabs } from '@/components/ui';
import { Ticket, Plus, X } from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getCards,
  createCard,
  updateCard,
  deleteCard,
  uploadCardImage,
  type Card as CardType,
  type CardKind,
  type CardCreateParams,
} from '@/api/wrappers/products';

// ---------------------------------------------------------------------------
// 常量与映射
// ---------------------------------------------------------------------------

const TYPE_OPTIONS: { key: CardKind; label: string }[] = [
  { key: 'text', label: '固定文字' },
  { key: 'data', label: '批量数据' },
  { key: 'api', label: 'API接口' },
  { key: 'image', label: '图片' },
];

const API_METHODS: ('GET' | 'POST')[] = ['GET', 'POST'];

/** POST 请求可插入的上下文变量（对齐 web） */
const POST_PARAMS: { name: string; desc: string }[] = [
  { name: 'order_id', desc: '订单编号' },
  { name: 'item_id', desc: '商品编号' },
  { name: 'item_detail', desc: '商品详情' },
  { name: 'order_amount', desc: '订单金额' },
  { name: 'order_quantity', desc: '订单数量' },
  { name: 'spec_name', desc: '规格名称' },
  { name: 'spec_value', desc: '规格值' },
  { name: 'cookie_id', desc: 'cookies账号id' },
  { name: 'buyer_id', desc: '买家id' },
];

const FEE_PAYERS = [
  { value: 'distributor', label: '分销主支付' },
  { value: 'dealer', label: '分销商支付' },
];

const DOCK_VISIBILITIES = [
  { value: 'public', label: '所有人可见' },
  { value: 'dealer_only', label: '仅分销商可见' },
];

function typeLabel(t: CardKind): string {
  return TYPE_OPTIONS.find((o) => o.key === t)?.label ?? t;
}

function typeBadgeVariant(t: CardKind): 'primary' | 'success' | 'warning' | 'info' {
  switch (t) {
    case 'text':
      return 'primary';
    case 'data':
      return 'success';
    case 'api':
      return 'info';
    case 'image':
      return 'warning';
  }
}

// ---------------------------------------------------------------------------
// 表单状态
// ---------------------------------------------------------------------------

interface CardFormState {
  name: string;
  type: CardKind;
  textContent: string;
  dataContent: string;
  apiUrl: string;
  apiMethod: 'GET' | 'POST';
  apiTimeout: number;
  apiHeaders: string;
  apiParams: string;
  apiResponseField: string;
  imageUrls: string[];
  delaySeconds: number;
  useNoLogisticsForm: boolean;
  enabled: boolean;
  description: string;
  isDockable: boolean;
  price: string;
  feePayer: string;
  minPrice: string;
  dockVisibility: string;
  isMultiSpec: boolean;
  specName: string;
  specValue: string;
}

const EMPTY_FORM: CardFormState = {
  name: '',
  type: 'text',
  textContent: '',
  dataContent: '',
  apiUrl: '',
  apiMethod: 'GET',
  apiTimeout: 60,
  apiHeaders: '',
  apiParams: '',
  apiResponseField: '',
  imageUrls: [],
  delaySeconds: 0,
  useNoLogisticsForm: false,
  enabled: true,
  description: '',
  isDockable: false,
  price: '',
  feePayer: '',
  minPrice: '',
  dockVisibility: 'public',
  isMultiSpec: false,
  specName: '',
  specValue: '',
};

function cardToForm(card: CardType): CardFormState {
  const cfg = card.api_config ?? null;
  return {
    name: card.name ?? '',
    type: (card.type ?? 'text') as CardKind,
    textContent: card.text_content ?? '',
    dataContent: card.data_content ?? '',
    apiUrl: cfg?.url ?? '',
    apiMethod: cfg?.method === 'POST' ? 'POST' : 'GET',
    apiTimeout: cfg?.timeout ?? 60,
    apiHeaders: cfg?.headers ?? '',
    apiParams: cfg?.params ?? '',
    apiResponseField: cfg?.response_field ?? '',
    imageUrls:
      card.image_urls && card.image_urls.length > 0
        ? [...card.image_urls]
        : card.image_url
          ? [card.image_url]
          : [],
    delaySeconds: card.delay_seconds ?? 0,
    useNoLogisticsForm: card.use_no_logistics_form ?? false,
    enabled: card.enabled ?? true,
    description: card.description ?? '',
    isDockable: card.is_dockable ?? false,
    price: card.price ?? '',
    feePayer: card.fee_payer ?? '',
    minPrice: card.min_price ?? '',
    dockVisibility: card.dock_visibility || 'public',
    isMultiSpec: card.is_multi_spec ?? false,
    specName: card.spec_name ?? '',
    specValue: card.spec_value ?? '',
  };
}

/** 将表单组装为后端 CardCreate 入参（条件字段逻辑对齐 web） */
function buildParams(f: CardFormState): CardCreateParams {
  const params: CardCreateParams = {
    name: f.name.trim() || '未命名卡券',
    type: f.type,
    description: f.description.trim() || null,
    enabled: f.enabled,
    delay_seconds: Math.max(0, Math.min(3600, Number(f.delaySeconds) || 0)),
    use_no_logistics_form: f.type === 'text' && f.useNoLogisticsForm,
    is_dockable: f.isDockable,
    price: f.price.trim() || null,
    fee_payer: f.isDockable ? f.feePayer || null : null,
    min_price: f.isDockable ? f.minPrice.trim() || null : null,
    dock_visibility: f.isDockable ? f.dockVisibility || null : null,
    is_multi_spec: f.isMultiSpec,
    spec_name: f.isMultiSpec ? f.specName.trim() || null : null,
    spec_value: f.isMultiSpec ? f.specValue.trim() || null : null,
  };
  if (f.type === 'api') {
    params.api_config = {
      url: f.apiUrl.trim(),
      method: f.apiMethod,
      timeout: Number(f.apiTimeout) || 60,
      headers: f.apiHeaders.trim() || undefined,
      params: f.apiParams.trim() || undefined,
      response_field: f.apiResponseField.trim() || undefined,
    };
  } else if (f.type === 'text') {
    params.text_content = f.textContent.trim();
  } else if (f.type === 'data') {
    params.data_content = f.dataContent.trim();
  }
  if (f.imageUrls.length > 0) params.image_urls = f.imageUrls;
  return params;
}

/** 表单校验：对齐 web 规则，返回错误消息（空串表示通过） */
function validateForm(f: CardFormState): string {
  if (!f.name.trim()) return '请输入卡券名称';
  if (f.type === 'api' && !f.apiUrl.trim()) return '请输入 API 地址';
  if (f.type === 'text' && !f.textContent.trim()) return '请输入固定文字内容';
  if (f.type === 'data' && !f.dataContent.trim()) return '请输入批量数据';
  if (f.isMultiSpec && (!f.specName.trim() || !f.specValue.trim()))
    return '多规格卡券必须填写规格名称和规格值';
  if (f.isDockable) {
    if (!f.price.trim()) return '勾选可对接时，对接价格必填';
    if (!f.feePayer) return '勾选可对接时，手续费支付方式必选';
    if (!f.dockVisibility) return '勾选可对接时，对接类型必选';
  }
  if (f.price.trim()) {
    if (!/^\d+(\.\d{1,2})?$/.test(f.price.trim())) return '对接价格必须是大于0且最多两位小数的数字';
  }
  if (f.minPrice.trim()) {
    if (!/^\d+(\.\d{1,2})?$/.test(f.minPrice.trim())) return '最低售价必须是大于0且最多两位小数的数字';
  }
  if (f.type !== 'image' && f.description.trim() && !f.description.includes('{DELIVERY_CONTENT}'))
    return '非图片类型卡券的备注中必须包含 {DELIVERY_CONTENT} 变量';
  if (f.apiHeaders.trim()) {
    try {
      JSON.parse(f.apiHeaders.trim());
    } catch {
      return '请求头格式错误，请输入有效的 JSON';
    }
  }
  if (f.apiParams.trim()) {
    try {
      JSON.parse(f.apiParams.trim());
    } catch {
      return '请求参数格式错误，请输入有效的 JSON';
    }
  }
  return '';
}

export default function CardsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [cards, setCards] = useState<CardType[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<string>('all');

  const [modalVisible, setModalVisible] = useState(false);
  const [editing, setEditing] = useState<CardType | null>(null);
  const [form, setForm] = useState<CardFormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [dockOpen, setDockOpen] = useState(false);
  const [specOpen, setSpecOpen] = useState(false);

  const loadCards = useCallback(async () => {
    try {
      setRefreshing(true);
      const list = await getCards();
      setCards(list);
    } catch (e) {
      Alert.alert('加载失败', (e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadCards();
  }, [loadCards]);

  // 客户端过滤（已一次性拉取全部卡券）
  const filtered = useMemo(() => {
    const kw = search.trim().toLowerCase();
    return cards.filter((card) => {
      if (typeFilter !== 'all' && card.type !== typeFilter) return false;
      if (!kw) return true;
      const hay = `${card.name ?? ''} ${card.description ?? ''}`.toLowerCase();
      return hay.includes(kw);
    });
  }, [cards, search, typeFilter]);

  // 各类型计数（基于全量，不受搜索影响）
  const typeCounts = useMemo(() => {
    const map: Record<string, number> = { text: 0, data: 0, api: 0, image: 0 };
    for (const card of cards) {
      if (card.type && map[card.type] != null) map[card.type]++;
    }
    return map;
  }, [cards]);

  const filterTabs = useMemo(
    () => [
      { key: 'all', label: '全部', count: cards.length },
      { key: 'text', label: '固定文字', count: typeCounts.text },
      { key: 'data', label: '批量数据', count: typeCounts.data },
      { key: 'api', label: 'API', count: typeCounts.api },
      { key: 'image', label: '图片', count: typeCounts.image },
    ],
    [cards.length, typeCounts],
  );

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setDockOpen(false);
    setSpecOpen(false);
    setModalVisible(true);
  }

  function openEdit(card: CardType) {
    setEditing(card);
    setForm(cardToForm(card));
    setDockOpen(card.is_dockable ?? false);
    setSpecOpen(card.is_multi_spec ?? false);
    setModalVisible(true);
  }

  function closeModal() {
    setModalVisible(false);
  }

  const update = <K extends keyof CardFormState>(field: K, value: CardFormState[K]) =>
    setForm((prev) => ({ ...prev, [field]: value }));

  function setType(t: CardKind) {
    // 非 text 类型不支持无物流表单
    update('type', t);
    if (t !== 'text') update('useNoLogisticsForm', false);
  }

  /** 插入 POST 上下文变量到 apiParams（JSON 对象形式，与 web 一致） */
  function insertParam(name: string) {
    const current = form.apiParams.trim();
    let obj: Record<string, string> = {};
    if (current && current !== '{}') {
      try {
        const parsed = JSON.parse(current);
        if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
          obj = parsed as Record<string, string>;
        }
      } catch {
        // 解析失败则丢弃旧内容，避免脏数据
      }
    }
    obj[name] = `{${name}}`;
    update('apiParams', JSON.stringify(obj, null, 2));
  }

  async function pickImage() {
    if (form.imageUrls.length >= 3) return;
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: false,
      quality: 0.8,
    });
    if (result.canceled || !result.assets || result.assets.length === 0) return;
    setUploading(true);
    try {
      const url = await uploadCardImage(result.assets[0].uri);
      setForm((prev) => ({ ...prev, imageUrls: [...prev.imageUrls, url] }));
    } catch (e) {
      Alert.alert('上传失败', (e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  function removeImage(index: number) {
    setForm((prev) => {
      const next = [...prev.imageUrls];
      next.splice(index, 1);
      return { ...prev, imageUrls: next };
    });
  }

  async function save() {
    const err = validateForm(form);
    if (err) {
      Alert.alert('提示', err);
      return;
    }
    setSaving(true);
    try {
      const params = buildParams(form);
      if (editing) {
        await updateCard(editing.id, params);
      } else {
        await createCard(params);
      }
      setModalVisible(false);
      await loadCards();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function toggleEnabled(card: CardType, next: boolean) {
    // 乐观更新，失败回滚
    const prev = card.enabled;
    setCards((list) => list.map((x) => (x.id === card.id ? { ...x, enabled: next } : x)));
    try {
      await updateCard(card.id, { enabled: next });
    } catch (e) {
      setCards((list) => list.map((x) => (x.id === card.id ? { ...x, enabled: prev } : x)));
      Alert.alert('切换失败', (e as Error).message);
    }
  }

  function confirmDelete(card: CardType) {
    Alert.alert(
      '删除卡券',
      `确定删除「${card.name || card.remark || '此卡券'}」吗？此操作不可恢复。`,
      [
        { text: '取消', style: 'cancel' },
        { text: '删除', style: 'destructive', onPress: () => doDelete(card) },
      ],
      { cancelable: true },
    );
  }

  async function doDelete(card: CardType) {
    try {
      await deleteCard(card.id);
      setCards((prev) => prev.filter((x) => x.id !== card.id));
    } catch (e) {
      Alert.alert('删除失败', (e as Error).message);
    }
  }

  function handleLongPress(card: CardType) {
    Alert.alert(card.name || card.remark || '卡券', undefined, [
      { text: '编辑', onPress: () => openEdit(card) },
      { text: '删除', style: 'destructive', onPress: () => confirmDelete(card) },
      { text: '取消', style: 'cancel' },
    ]);
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载卡券..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <Button label="+ 新建" onPress={openCreate} variant="secondary" />
      </View>

      <View style={[styles.searchWrap, { backgroundColor: c.surface, borderColor: c.border }]}>
        <Input
          value={search}
          onChangeText={setSearch}
          placeholder="搜索名称/备注"
          style={styles.searchInput}
          returnKeyType="search"
        />
      </View>

      <FilterTabs tabs={filterTabs} active={typeFilter} onChange={setTypeFilter} />

      <FlatList
        data={filtered}
        keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadCards} />}
        renderItem={({ item }) => (
          <Pressable onPress={() => openEdit(item)} onLongPress={() => handleLongPress(item)}>
            <Card style={styles.cardItem}>
              <View style={styles.cardTop}>
                <View style={styles.cardTitleRow}>
                  <Text style={[styles.cardName, { color: c.text }]} numberOfLines={1}>
                    {item.name || '未命名卡券'}
                  </Text>
                  <Badge label={typeLabel(item.type)} variant={typeBadgeVariant(item.type)} />
                </View>
                <Switch
                  value={item.enabled ?? true}
                  onValueChange={(v) => toggleEnabled(item, v)}
                  trackColor={{ false: c.border, true: c.primary }}
                />
              </View>
              {item.description ? (
                <Text style={[styles.cardDesc, { color: c.textMuted }]} numberOfLines={1}>
                  {item.description.slice(0, 40)}
                </Text>
              ) : null}
              <View style={styles.cardMeta}>
                {item.is_dockable ? (
                  <Badge label={`对接 ¥${item.price || '-'}`} variant="info" />
                ) : null}
                {item.is_multi_spec ? (
                  <Badge label={`${item.spec_name || ''}:${item.spec_value || ''}`} variant="warning" />
                ) : null}
                {item.use_no_logistics_form ? <Badge label="无物流" variant="gray" /> : null}
                {item.delay_seconds ? <Badge label={`延时${item.delay_seconds}s`} variant="gray" /> : null}
              </View>
            </Card>
          </Pressable>
        )}
        ListEmptyComponent={
          <EmptyState
            icon={Ticket}
            title="暂无卡券"
            message={search || typeFilter !== 'all' ? '没有符合条件的卡券' : '新建卡券后可在发货时复用'}
            actionLabel="添加卡券"
            onAction={openCreate}
          />
        }
        contentContainerStyle={styles.list}
      />

      {/* 新建/编辑表单（底部抽屉） */}
      <Modal visible={modalVisible} transparent animationType="slide" onRequestClose={closeModal}>
        <KeyboardAvoidingView
          style={styles.modalOverlay}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        >
          <Pressable style={styles.modalBackdrop} onPress={closeModal} />
          <View style={[styles.modalSheet, { backgroundColor: c.surface }]}>
            <View style={[styles.modalHandle, { backgroundColor: c.border }]} />
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>
                {editing ? '编辑卡券' : '新建卡券'}
              </Text>
              <Pressable onPress={closeModal} hitSlop={8}>
                <Text style={[styles.modalClose, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>

            <ScrollView
              style={styles.modalScroll}
              contentContainerStyle={styles.modalBody}
              keyboardShouldPersistTaps="handled"
            >
              {/* 类型选择 */}
              <FieldLabel label="卡券类型" required />
              <View style={styles.chipRow}>
                {TYPE_OPTIONS.map((o) => {
                  const on = form.type === o.key;
                  return (
                    <Pressable
                      key={o.key}
                      onPress={() => setType(o.key)}
                      style={[
                        styles.chip,
                        {
                          backgroundColor: on ? c.primary : c.background,
                          borderColor: on ? c.primary : c.border,
                        },
                      ]}
                    >
                      <Text style={[styles.chipText, { color: on ? '#FFFFFF' : c.textSecondary }]}>
                        {o.label}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>

              {/* 名称 */}
              <FieldLabel label="卡券名称" required />
              <Input
                value={form.name}
                onChangeText={(v) => update('name', v)}
                placeholder="例如：游戏点卡、会员卡等"
              />

              {/* 各类型字段 */}
              {form.type === 'text' && (
                <>
                  <FieldLabel label="固定文字内容" required />
                  <Input
                    value={form.textContent}
                    onChangeText={(v) => update('textContent', v)}
                    placeholder="请输入要发送的固定文字内容..."
                    multiline
                    numberOfLines={4}
                    style={styles.textarea}
                  />
                </>
              )}

              {form.type === 'data' && (
                <>
                  <FieldLabel label="数据内容（一行一个）" required />
                  <Input
                    value={form.dataContent}
                    onChangeText={(v) => update('dataContent', v)}
                    placeholder={'卡号1:密码1\n卡号2:密码2\n或兑换码1\n兑换码2'}
                    multiline
                    numberOfLines={6}
                    style={styles.textarea}
                  />
                  <FieldHint text="支持格式：卡号:密码 或 单独的兑换码" />
                </>
              )}

              {form.type === 'api' && (
                <View style={[styles.subSection, { borderColor: c.border }]}>
                  <Text style={[styles.subTitle, { color: c.text }]}>API 配置</Text>

                  <FieldLabel label="API 地址" required />
                  <Input
                    value={form.apiUrl}
                    onChangeText={(v) => update('apiUrl', v)}
                    placeholder="https://api.example.com/get-card"
                    keyboardType="url"
                    autoCapitalize="none"
                  />

                  <FieldLabel label="请求方法" />
                  <View style={styles.chipRow}>
                    {API_METHODS.map((m) => {
                      const on = form.apiMethod === m;
                      return (
                        <Pressable
                          key={m}
                          onPress={() => update('apiMethod', m)}
                          style={[
                            styles.chip,
                            {
                              backgroundColor: on ? c.primary : c.background,
                              borderColor: on ? c.primary : c.border,
                            },
                          ]}
                        >
                          <Text style={[styles.chipText, { color: on ? '#FFFFFF' : c.textSecondary }]}>
                            {m}
                          </Text>
                        </Pressable>
                      );
                    })}
                  </View>

                  <FieldLabel label="超时时间（秒）" />
                  <Input
                    value={String(form.apiTimeout)}
                    onChangeText={(v) => update('apiTimeout', Number(v) || 60)}
                    placeholder="60"
                    keyboardType="numeric"
                    style={styles.numInput}
                  />

                  <FieldLabel label="请求头（JSON）" />
                  <Input
                    value={form.apiHeaders}
                    onChangeText={(v) => update('apiHeaders', v)}
                    placeholder='{"Authorization": "Bearer token"}'
                    multiline
                    numberOfLines={3}
                    style={styles.textarea}
                    autoCapitalize="none"
                  />

                  <FieldLabel label="请求参数（JSON）" />
                  <Input
                    value={form.apiParams}
                    onChangeText={(v) => update('apiParams', v)}
                    placeholder='{"type": "card", "count": 1}'
                    multiline
                    numberOfLines={3}
                    style={styles.textarea}
                    autoCapitalize="none"
                  />
                  {form.apiMethod === 'POST' && (
                    <View style={styles.paramChips}>
                      <Text style={[styles.paramChipsTitle, { color: c.textSecondary }]}>
                        POST 可用变量（点击插入）
                      </Text>
                      <View style={styles.paramChipRow}>
                        {POST_PARAMS.map((p) => (
                          <Pressable
                            key={p.name}
                            onPress={() => insertParam(p.name)}
                            style={[styles.paramChip, { borderColor: c.primaryLight }]}
                            hitSlop={4}
                          >
                            <Text style={[styles.paramChipText, { color: c.primary }]}>{p.name}</Text>
                          </Pressable>
                        ))}
                      </View>
                    </View>
                  )}

                  <FieldLabel label="响应取值字段（选填）" />
                  <Input
                    value={form.apiResponseField}
                    onChangeText={(v) => update('apiResponseField', v)}
                    placeholder="data.cards[0].key"
                    autoCapitalize="none"
                  />
                  <FieldHint text="卡密藏在 JSON 某一层时填路径精确取出，如 data.cards[0].key；接口返回纯文本时请留空。" />
                </View>
              )}

              {form.type === 'image' && (
                <View style={[styles.subSection, { borderColor: c.border }]}>
                  <Text style={[styles.subTitle, { color: c.text }]}>图片（最多 3 张）</Text>
                  <View style={styles.imageGrid}>
                    {form.imageUrls.map((url, index) => (
                      <View key={`${index}-${url}`} style={styles.imageCell}>
                        <Image source={{ uri: url }} style={styles.thumb} />
                        <Pressable
                          onPress={() => removeImage(index)}
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
                    {form.imageUrls.length < 3 && (
                      <Pressable
                        onPress={pickImage}
                        style={[styles.imageAdd, { borderColor: c.border }]}
                        disabled={uploading}
                      >
                        {uploading ? (
                          <Text style={[styles.imageAddText, { color: c.textMuted }]}>上传中</Text>
                        ) : (
                          <>
                            <Plus color={c.textMuted} size={22} />
                            <Text style={[styles.imageAddText, { color: c.textMuted }]}>添加图片</Text>
                          </>
                        )}
                      </Pressable>
                    )}
                  </View>
                </View>
              )}

              {/* 通用字段 */}
              <FieldLabel label="备注信息" />
              <Input
                value={form.description}
                onChangeText={(v) => update('description', v)}
                placeholder={
                  form.type === 'image'
                    ? '可选备注，图片发送后发送此内容\n支持 {order_id} {item_title} 等变量'
                    : '可选备注，非图片类型须包含 {DELIVERY_CONTENT} 变量\n可选 {order_id} {item_title} 等，###### 拆分多条消息'
                }
                multiline
                numberOfLines={3}
                style={styles.textarea}
              />

              <FieldLabel label="延时发货时间（秒，0-3600）" />
              <Input
                value={String(form.delaySeconds)}
                onChangeText={(v) => update('delaySeconds', Number(v) || 0)}
                placeholder="0"
                keyboardType="numeric"
                style={styles.numInput}
              />
              <FieldHint text="0 表示立即发货，最大 3600 秒（1 小时）。" />

              {form.type === 'text' && (
                <SwitchRow
                  label="填写到无需邮寄凭证"
                  hint="开启后不再向买家发送卡券聊天消息"
                  value={form.useNoLogisticsForm}
                  onValueChange={(v) => update('useNoLogisticsForm', v)}
                  trackFalse={c.border}
                  trackTrue={c.primary}
                  textMuted={c.textMuted}
                  textSecondary={c.textSecondary}
                />
              )}

              <SwitchRow
                label="启用卡券"
                hint="停用后不会在发货时使用"
                value={form.enabled}
                onValueChange={(v) => update('enabled', v)}
                trackFalse={c.border}
                trackTrue={c.primary}
                textMuted={c.textMuted}
                textSecondary={c.textSecondary}
              />

              {/* 对接配置（折叠） */}
              <Collapsible
                title="对接配置"
                open={dockOpen}
                onToggle={() => setDockOpen((v) => !v)}
                text={c.text}
                textMuted={c.textMuted}
                border={c.border}
              >
                <SwitchRow
                  label="是否可对接"
                  hint="开启后其他分销商可对接此卡券"
                  value={form.isDockable}
                  onValueChange={(v) => {
                    update('isDockable', v);
                    if (!v) {
                      update('feePayer', '');
                      update('minPrice', '');
                      update('dockVisibility', 'public');
                    }
                  }}
                  trackFalse={c.border}
                  trackTrue={c.primary}
                  textMuted={c.textMuted}
                  textSecondary={c.textSecondary}
                />
                {form.isDockable && (
                  <>
                    <FieldLabel label="对接价格" required />
                    <Input
                      value={form.price}
                      onChangeText={(v) => {
                        if (v === '' || /^\d*\.?\d{0,2}$/.test(v)) update('price', v);
                      }}
                      placeholder="例如：9.90"
                      keyboardType="numeric"
                      style={styles.numInput}
                    />
                    <FieldLabel label="手续费支付方式" required />
                    <View style={styles.chipRow}>
                      {FEE_PAYERS.map((o) => {
                        const on = form.feePayer === o.value;
                        return (
                          <Pressable
                            key={o.value}
                            onPress={() => update('feePayer', o.value)}
                            style={[
                              styles.chip,
                              {
                                backgroundColor: on ? c.primary : c.background,
                                borderColor: on ? c.primary : c.border,
                              },
                            ]}
                          >
                            <Text style={[styles.chipText, { color: on ? '#FFFFFF' : c.textSecondary }]}>
                              {o.label}
                            </Text>
                          </Pressable>
                        );
                      })}
                    </View>
                    <FieldLabel label="最低售价" />
                    <Input
                      value={form.minPrice}
                      onChangeText={(v) => {
                        if (v === '' || /^\d*\.?\d{0,2}$/.test(v)) update('minPrice', v);
                      }}
                      placeholder="可选，例如：5.00"
                      keyboardType="numeric"
                      style={styles.numInput}
                    />
                    <FieldHint text="设置后分销商售价不得低于此价格（可为空）。" />
                    <FieldLabel label="对接可见性" required />
                    <View style={styles.chipRow}>
                      {DOCK_VISIBILITIES.map((o) => {
                        const on = form.dockVisibility === o.value;
                        return (
                          <Pressable
                            key={o.value}
                            onPress={() => update('dockVisibility', o.value)}
                            style={[
                              styles.chip,
                              {
                                backgroundColor: on ? c.primary : c.background,
                                borderColor: on ? c.primary : c.border,
                              },
                            ]}
                          >
                            <Text style={[styles.chipText, { color: on ? '#FFFFFF' : c.textSecondary }]}>
                              {o.label}
                            </Text>
                          </Pressable>
                        );
                      })}
                    </View>
                  </>
                )}
              </Collapsible>

              {/* 多规格（折叠） */}
              <Collapsible
                title="多规格"
                open={specOpen}
                onToggle={() => setSpecOpen((v) => !v)}
                text={c.text}
                textMuted={c.textMuted}
                border={c.border}
              >
                <SwitchRow
                  label="多规格卡券"
                  hint="为同一商品的不同规格创建不同卡券"
                  value={form.isMultiSpec}
                  onValueChange={(v) => update('isMultiSpec', v)}
                  trackFalse={c.border}
                  trackTrue={c.primary}
                  textMuted={c.textMuted}
                  textSecondary={c.textSecondary}
                />
                {form.isMultiSpec && (
                  <>
                    <FieldLabel label="规格名称" required />
                    <Input
                      value={form.specName}
                      onChangeText={(v) => update('specName', v)}
                      placeholder="例如：套餐类型、颜色"
                    />
                    <FieldLabel label="规格值" required />
                    <Input
                      value={form.specValue}
                      onChangeText={(v) => update('specValue', v)}
                      placeholder="例如：30天、红色"
                    />
                    <FieldHint text="卡券名称+规格名称+规格值需唯一；发货时精确匹配订单规格。" />
                  </>
                )}
              </Collapsible>
            </ScrollView>

            <View style={[styles.modalFooter, { borderTopColor: c.border }]}>
              <Button label="取消" variant="ghost" onPress={closeModal} style={styles.modalBtn} />
              <Button
                label="保存"
                onPress={save}
                loading={saving}
                disabled={saving}
                style={styles.modalBtn}
              />
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// 表单内联小组件
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

function SwitchRow({
  label,
  hint,
  value,
  onValueChange,
  trackFalse,
  trackTrue,
  textMuted,
  textSecondary,
}: {
  label: string;
  hint?: string;
  value: boolean;
  onValueChange: (v: boolean) => void;
  trackFalse: string;
  trackTrue: string;
  textMuted: string;
  textSecondary: string;
}) {
  return (
    <View style={styles.switchRow}>
      <View style={styles.switchInfo}>
        <Text style={[styles.switchLabel, { color: textSecondary }]}>{label}</Text>
        {hint ? <Text style={[styles.switchHint, { color: textMuted }]}>{hint}</Text> : null}
      </View>
      <Switch value={value} onValueChange={onValueChange} trackColor={{ false: trackFalse, true: trackTrue }} />
    </View>
  );
}

function Collapsible({
  title,
  open,
  onToggle,
  children,
  text,
  textMuted,
  border,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
  text: string;
  textMuted: string;
  border: string;
}) {
  return (
    <View style={[styles.collapsible, { borderColor: border }]}>
      <Pressable style={styles.collapsibleHeader} onPress={onToggle}>
        <Text style={[styles.collapsibleTitle, { color: text }]}>{title}</Text>
        <Text style={[styles.chevron, { color: textMuted }]}>{open ? '⌄' : '›'}</Text>
      </Pressable>
      {open ? <View style={styles.collapsibleBody}>{children}</View> : null}
    </View>
  );
}

// Input 的 style 为 StyleProp<TextStyle>，自定义样式对象按 TextStyle 收窄，
// 既满足 StyleSheet.create 的 NamedStyles 约束，又可赋值给 Input 的 style 属性。
type InputStyle = TextStyle;

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  headerTitle: { ...typography.heading },
  searchWrap: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.xs,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  searchInput: { minHeight: 40, borderWidth: 0, borderRadius: 0 },
  list: { padding: spacing.lg, gap: spacing.md, paddingBottom: 80 },
  cardItem: { gap: spacing.xs },
  cardTop: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  cardTitleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flexShrink: 1 },
  cardName: { ...typography.body, fontWeight: '600', flexShrink: 1 },
  cardDesc: { ...typography.small },
  cardMeta: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs, marginTop: 2 },

  // Modal
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
  modalBtn: { flex: 1 },

  // Form fields
  fieldLabel: { flexDirection: 'row', alignItems: 'center', marginTop: spacing.xs },
  fieldLabelText: { ...typography.caption, fontWeight: '500' },
  required: { color: '#EF4444', fontSize: 14 },
  fieldHint: { ...typography.small, lineHeight: 16 },
  textarea: { minHeight: 90, textAlignVertical: 'top' },
  numInput: { minHeight: 44 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md,
    height: 32,
    borderRadius: radius.full,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  chipText: { fontSize: 13, fontWeight: '500' },
  subSection: {
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
    marginTop: spacing.xs,
    gap: spacing.xs,
  },
  subTitle: { ...typography.caption, fontWeight: '600' },
  paramChips: { marginTop: spacing.xs },
  paramChipsTitle: { ...typography.small, marginBottom: spacing.xs },
  paramChipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  paramChip: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 3,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  paramChipText: { fontSize: 12, fontFamily: 'monospace' },
  switchRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.md,
    marginTop: spacing.xs,
  },
  switchInfo: { flex: 1, gap: 2 },
  switchLabel: { ...typography.caption, fontWeight: '500' },
  switchHint: { ...typography.small },
  collapsible: {
    borderWidth: 1,
    borderRadius: radius.md,
    marginTop: spacing.xs,
    overflow: 'hidden',
  },
  collapsibleHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: spacing.md,
  },
  collapsibleTitle: { ...typography.caption, fontWeight: '600' },
  chevron: { fontSize: 18, lineHeight: 18 },
  collapsibleBody: { padding: spacing.md, paddingTop: 0, gap: spacing.xs },

  // Image grid
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
});
