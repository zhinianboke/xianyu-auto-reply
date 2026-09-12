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
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { ChevronDown, ChevronRight, Trash2 } from 'lucide-react-native';
import { Card, Button, Input, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getSellerItemDetail,
  updateSellerItem,
  updateItemPrice,
  type SellerItemForm,
} from '@/api/wrappers/item-edit';
import {
  getXianyuItemDetail,
  setItemMultiSpec,
  setItemMultiQuantityDelivery,
  getItemDefaultReply,
  saveItemDefaultReply,
  getItemAiPrompt,
  saveItemAiPrompt,
  type XianyuItemSku,
} from '@/api/wrappers/items';
import {
  getItemQueryButtons,
  saveItemQueryButtons,
  type QueryButton,
  type QueryResultField,
} from '@/api/wrappers/item-query-config';

// seller-detail 可能回填 'template'，表单仅支持四种；回填为 template 时不选中任何 chip，保存时回退为原值
type ShippingMethod = NonNullable<SellerItemForm['shipping_method']>;

const SHIPPING_OPTIONS: Array<{ value: 'free' | 'distance' | 'fixed' | 'none'; label: string }> = [
  { value: 'free', label: '包邮' },
  { value: 'distance', label: '按距离' },
  { value: 'fixed', label: '固定运费' },
  { value: 'none', label: '不包邮' },
];

/** seller-detail / seller-edit 依赖后端新接口，旧版后端会 404 */
const BACKEND_VERSION_HINT = '该功能需要后端 v最新版支持';

type SectionKey = 'basic' | 'cards' | 'delivery' | 'reply' | 'ai' | 'query';

/** 折叠卡片：标题行 + 展开指示箭头，内容条件渲染（不用动画库） */
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

/** 卡片数据加载失败的内联提示 + 重试入口（失败时不渲染表单，防止空态保存覆盖服务端配置） */
function LoadErrorRow({ message, onRetry }: { message: string; onRetry: () => void }) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  return (
    <View style={styles.loadErrorWrap}>
      <Text style={[styles.loadErrorText, { color: c.error }]}>加载失败：{message}</Text>
      <Button label="重试" variant="secondary" onPress={onRetry} style={styles.loadErrorBtn} />
    </View>
  );
}

// ---------------------------------------------------------------------------
// 查询配置：编辑态文本 ⇄ QueryButton 结构的序列化/反序列化（与 web 端弹窗同格式）
// 请求头：每行 `Key: Value`；结果字段：每行 `标签=路径`，行尾 `*` 表高亮，`|前缀` 表前缀
// ---------------------------------------------------------------------------

interface QueryButtonDraft {
  key: string;
  name: string;
  method: 'GET' | 'POST';
  url: string;
  headersText: string;
  body: string;
  successPath: string;
  successValue: string;
  errorPath: string;
  fieldsText: string;
}

let draftSeq = 0;
function nextDraftKey(): string {
  draftSeq += 1;
  return `qb-${Date.now()}-${draftSeq}`;
}

function emptyDraft(): QueryButtonDraft {
  return {
    key: nextDraftKey(),
    name: '',
    method: 'GET',
    url: '',
    headersText: '',
    body: '',
    successPath: '',
    successValue: '',
    errorPath: '',
    fieldsText: '',
  };
}

function headersToText(headers?: Record<string, string> | null): string {
  if (!headers) return '';
  return Object.entries(headers)
    .map(([k, v]) => `${k}: ${v}`)
    .join('\n');
}

function textToHeaders(text: string, buttonName: string): Record<string, string> | null {
  const out: Record<string, string> = {};
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    const line = lines[i].trim();
    if (!line) continue;
    const idx = line.indexOf(':');
    if (idx <= 0) {
      throw new Error(`按钮「${buttonName}」请求头第 ${i + 1} 行格式应为 Key: Value`);
    }
    out[line.slice(0, idx).trim()] = line.slice(idx + 1).trim();
  }
  return Object.keys(out).length > 0 ? out : null;
}

function fieldsToText(fields: QueryResultField[]): string {
  return fields
    .map((f) => `${f.label}=${f.path}${f.prefix ? `|${f.prefix}` : ''}${f.highlight ? '*' : ''}`)
    .join('\n');
}

function textToFields(text: string, buttonName: string): QueryResultField[] {
  const out: QueryResultField[] = [];
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    let line = lines[i].trim();
    if (!line) continue;
    let highlight = false;
    if (line.endsWith('*')) {
      highlight = true;
      line = line.slice(0, -1).trimEnd();
    }
    let prefix: string | undefined;
    const pipeIdx = line.indexOf('|');
    if (pipeIdx >= 0) {
      prefix = line.slice(pipeIdx + 1).trim() || undefined;
      line = line.slice(0, pipeIdx);
    }
    const eqIdx = line.indexOf('=');
    const label = eqIdx > 0 ? line.slice(0, eqIdx).trim() : '';
    const path = eqIdx > 0 ? line.slice(eqIdx + 1).trim() : '';
    if (!label || !path) {
      throw new Error(`按钮「${buttonName}」结果字段第 ${i + 1} 行格式应为 标签=路径`);
    }
    out.push({
      label,
      path,
      ...(highlight ? { highlight: true } : {}),
      ...(prefix ? { prefix } : {}),
    });
  }
  return out;
}

function draftFromButton(b: QueryButton): QueryButtonDraft {
  return {
    key: nextDraftKey(),
    name: b.name ?? '',
    method: b.method === 'POST' ? 'POST' : 'GET',
    url: b.url ?? '',
    headersText: headersToText(b.headers),
    body: b.body ?? '',
    successPath: b.success_path ?? '',
    successValue: b.success_value ?? '',
    errorPath: b.error_path ?? '',
    fieldsText: fieldsToText(b.result_fields ?? []),
  };
}

/** 编辑态 → QueryButton[]，契约校验：name/url/result_fields 必填、method 枚举、url 必须 http(s) */
function serializeQueryButtons(drafts: QueryButtonDraft[]): QueryButton[] {
  return drafts.map((d, i) => {
    const name = d.name.trim();
    if (!name) throw new Error(`第 ${i + 1} 个按钮请填写名称`);
    const url = d.url.trim();
    if (!url) throw new Error(`按钮「${name}」请填写 URL`);
    if (!/^https?:\/\//i.test(url)) {
      throw new Error(`按钮「${name}」URL 必须以 http:// 或 https:// 开头`);
    }
    const resultFields = textToFields(d.fieldsText, name);
    if (resultFields.length === 0) {
      throw new Error(`按钮「${name}」至少需要一个结果字段`);
    }
    return {
      name,
      method: d.method,
      url,
      headers: textToHeaders(d.headersText, name),
      body: d.method === 'POST' && d.body.trim() ? d.body : null,
      success_path: d.successPath.trim() || null,
      success_value: d.successValue.trim() || null,
      error_path: d.errorPath.trim() || null,
      result_fields: resultFields,
    };
  });
}

export default function ItemEditScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();
  const { cookieId, itemId } = useLocalSearchParams<{ cookieId: string; itemId: string }>();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  // 平台详情（鱼小铺 seller-detail）失败原因：非空时基础信息降级为本地只读，不阻塞本地配置卡片
  const [platformError, setPlatformError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [price, setPrice] = useState('');
  const [originalPrice, setOriginalPrice] = useState('');
  const [quantity, setQuantity] = useState('');
  const [images, setImages] = useState<string[]>([]);
  const [shippingMethod, setShippingMethod] = useState<'free' | 'distance' | 'fixed' | 'none'>('free');
  const [postage, setPostage] = useState('');
  const [supportPickup, setSupportPickup] = useState(false);

  // 快捷改价：多规格行（来自本地库 item_sku_list，含 sku_id 供回传）
  const [priceSkus, setPriceSkus] = useState<
    Array<{ skuId: string; label: string; price: string; quantity: string }>
  >([]);
  const [isMultiSpecItem, setIsMultiSpecItem] = useState(false);
  const [priceSaving, setPriceSaving] = useState(false);
  // 商品标记（本地库标记，供商品列表筛选）
  const [flagMultiSpec, setFlagMultiSpec] = useState(false);
  const [flagMultiQty, setFlagMultiQty] = useState(false);
  // 标记切换 in-flight 锁：防止快速连拨产生并发 PUT，失败回滚覆盖后发请求的结果
  const [flagSaving, setFlagSaving] = useState(false);

  // 折叠卡片：默认只展开基础信息
  const [expanded, setExpanded] = useState<Record<SectionKey, boolean>>({
    basic: true,
    cards: false,
    delivery: false,
    reply: false,
    ai: false,
    query: false,
  });

  // 默认回复（展开时才加载）
  const [replyLoaded, setReplyLoaded] = useState(false);
  const [replyLoading, setReplyLoading] = useState(false);
  const [replyLoadError, setReplyLoadError] = useState<string | null>(null);
  const [replySaving, setReplySaving] = useState(false);
  const [replyEnabled, setReplyEnabled] = useState(false);
  // web 端另有 image 类型，移动端不支持编辑图片，回填时保留原值
  const [replyType, setReplyType] = useState<'text' | 'api' | 'image'>('text');
  const [replyContent, setReplyContent] = useState('');
  const [replyImage, setReplyImage] = useState('');
  const [replyOnce, setReplyOnce] = useState(false);
  const [replyApiUrl, setReplyApiUrl] = useState('');
  const [replyApiTimeout, setReplyApiTimeout] = useState('80');

  // AI提示词（展开时才加载）
  const [aiLoaded, setAiLoaded] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiLoadError, setAiLoadError] = useState<string | null>(null);
  const [aiSaving, setAiSaving] = useState(false);
  const [aiPrompt, setAiPrompt] = useState('');

  // 查询配置（展开时才加载）
  const [queryLoaded, setQueryLoaded] = useState(false);
  const [queryLoading, setQueryLoading] = useState(false);
  const [queryLoadError, setQueryLoadError] = useState<string | null>(null);
  const [querySaving, setQuerySaving] = useState(false);
  const [queryDrafts, setQueryDrafts] = useState<QueryButtonDraft[]>([]);

  const paramsReady = Boolean(cookieId && itemId);

  const load = useCallback(async () => {
    if (!cookieId || !itemId) {
      setLoadError('缺少 cookieId 或 itemId 参数');
      setLoading(false);
      return;
    }
    setLoading(true);
    setLoadError(null);
    setPlatformError(null);
    // 平台详情（seller-detail）依赖鱼小铺：失败（如账号未开通鱼小铺）只降级「基础信息」，
    // 不再整页报错——发货设置/卡券关联/默认回复/AI提示词/查询配置都是本地配置，照常可用
    let platformFailed = false;
    try {
      const { form } = await getSellerItemDetail(cookieId, itemId);
      setTitle(form.title ?? '');
      setDescription(form.description ?? '');
      setPrice(form.price != null ? String(form.price) : '');
      setOriginalPrice(form.original_price != null ? String(form.original_price) : '');
      setQuantity(form.quantity != null ? String(form.quantity) : '');
      setImages(Array.isArray(form.images) ? form.images : []);
      if (form.shipping_method && form.shipping_method !== 'template') {
        setShippingMethod(form.shipping_method);
      }
      setPostage(form.postage != null ? String(form.postage) : '');
      setSupportPickup(Boolean(form.support_pickup));
    } catch (e) {
      platformFailed = true;
      setPlatformError((e as Error).message || '获取平台商品详情失败');
    }
    // 本地库详情：取多规格明细（含 sku_id）与列表筛选标记；失败不阻塞编辑表单。
    // 平台详情失败时用本地记录回填标题/价格/库存/主图（xy_catalog_items 有这些字段）
    try {
      const { item } = await getXianyuItemDetail(cookieId, itemId);
      if (platformFailed) {
        if (item.title) setTitle(item.title);
        if (item.price) setPrice(item.price);
        if (item.quantity !== null && item.quantity !== undefined && item.quantity !== '') {
          setQuantity(String(item.quantity));
        }
        if (item.image) setImages([item.image]);
      }
      const skus = item.item_sku_list ?? [];
      if (skus.length > 0) {
        setIsMultiSpecItem(true);
        setPriceSkus(
          skus.map((sku: XianyuItemSku) => ({
            skuId: sku.sku_id,
            label:
              (sku.specs ?? []).map((s) => `${s.name}：${s.value}`).join('，') || sku.sku_id,
            price: sku.price != null ? String(sku.price) : '',
            quantity: sku.quantity != null ? String(sku.quantity) : '',
          })),
        );
      } else {
        setIsMultiSpecItem(false);
        setPriceSkus([]);
      }
      setFlagMultiSpec(Boolean(item.is_multi_spec));
      setFlagMultiQty(Boolean(item.multi_quantity_delivery));
    } catch {
      // 本地详情缺失时退化为单规格快捷改价（用表单价格/库存）
      setIsMultiSpecItem(false);
      setPriceSkus([]);
    }
    setLoading(false);
  }, [cookieId, itemId]);

  useEffect(() => {
    load();
  }, [load]);

  const loadDefaultReply = useCallback(async () => {
    if (!cookieId || !itemId) return;
    setReplyLoading(true);
    setReplyLoadError(null);
    try {
      const cfg = await getItemDefaultReply(cookieId, itemId);
      setReplyEnabled(Boolean(cfg.enabled));
      setReplyType(cfg.reply_type === 'api' ? 'api' : cfg.reply_type === 'image' ? 'image' : 'text');
      setReplyContent(cfg.reply_content ?? '');
      setReplyImage(cfg.reply_image ?? '');
      setReplyOnce(Boolean(cfg.reply_once));
      setReplyApiUrl(cfg.api_url ?? '');
      setReplyApiTimeout(cfg.api_timeout != null ? String(cfg.api_timeout) : '80');
      setReplyLoaded(true);
    } catch (e) {
      // 内联展示加载失败 + 重试入口，避免空态表单被误保存覆盖服务端配置
      setReplyLoadError((e as Error).message || '获取默认回复失败');
    } finally {
      setReplyLoading(false);
    }
  }, [cookieId, itemId]);

  const loadAiPrompt = useCallback(async () => {
    if (!cookieId || !itemId) return;
    setAiLoading(true);
    setAiLoadError(null);
    try {
      const cfg = await getItemAiPrompt(cookieId, itemId);
      setAiPrompt(cfg.ai_prompt ?? '');
      setAiLoaded(true);
    } catch (e) {
      setAiLoadError((e as Error).message || '获取AI提示词失败');
    } finally {
      setAiLoading(false);
    }
  }, [cookieId, itemId]);

  const loadQueryButtons = useCallback(async () => {
    if (!cookieId || !itemId) return;
    setQueryLoading(true);
    setQueryLoadError(null);
    try {
      const buttons = await getItemQueryButtons(cookieId, itemId);
      setQueryDrafts(buttons.map(draftFromButton));
      setQueryLoaded(true);
    } catch (e) {
      setQueryLoadError((e as Error).message || '获取查询配置失败');
    } finally {
      setQueryLoading(false);
    }
  }, [cookieId, itemId]);

  /** 展开时才拉取该卡片数据（各卡片独立加载、独立保存） */
  function toggleSection(key: SectionKey) {
    const willExpand = !expanded[key];
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));
    if (!willExpand) return;
    if (key === 'reply' && !replyLoaded && !replyLoading) loadDefaultReply();
    else if (key === 'ai' && !aiLoaded && !aiLoading) loadAiPrompt();
    else if (key === 'query' && !queryLoaded && !queryLoading) loadQueryButtons();
  }

  async function handleSave() {
    if (!cookieId || !itemId || platformError) return;
    if (!title.trim()) {
      Alert.alert('提示', '请输入商品标题');
      return;
    }
    const priceNum = parseFloat(price);
    if (!price.trim() || Number.isNaN(priceNum) || priceNum < 0) {
      Alert.alert('提示', '请输入正确的价格');
      return;
    }
    const quantityNum = parseInt(quantity, 10);
    if (!quantity.trim() || Number.isNaN(quantityNum) || quantityNum < 1) {
      Alert.alert('提示', '请输入正确的库存数量');
      return;
    }
    let originalNum: number | undefined;
    if (originalPrice.trim()) {
      originalNum = parseFloat(originalPrice);
      if (Number.isNaN(originalNum) || originalNum < 0) {
        Alert.alert('提示', '请输入正确的原价');
        return;
      }
    }
    let postageNum: number | undefined;
    if (shippingMethod === 'fixed' && postage.trim()) {
      postageNum = parseFloat(postage);
      if (Number.isNaN(postageNum) || postageNum < 0) {
        Alert.alert('提示', '请输入正确的运费金额');
        return;
      }
    }

    setSaving(true);
    try {
      await updateSellerItem(cookieId, itemId, {
        title: title.trim(),
        description,
        price: priceNum,
        original_price: originalNum,
        images,
        quantity: quantityNum,
        shipping_method: shippingMethod,
        support_pickup: supportPickup,
        postage: postageNum,
      });
      Alert.alert('保存成功', '商品信息已更新', [
        { text: '确定', onPress: () => router.back() },
      ]);
    } catch (e) {
      Alert.alert('保存失败', `${(e as Error).message || '未知错误'}\n${BACKEND_VERSION_HINT}`);
    } finally {
      setSaving(false);
    }
  }

  const updateSkuRow = (idx: number, field: 'price' | 'quantity', value: string) => {
    setPriceSkus((prev) => prev.map((row, i) => (i === idx ? { ...row, [field]: value } : row)));
  };

  /** 单规格快捷改价：仅提交价格与库存（PUT /items/{cookie_id}/{item_id}/price） */
  async function handleQuickPriceSave() {
    if (!cookieId || !itemId || priceSaving || platformError) return;
    const priceNum = parseFloat(price);
    if (!price.trim() || Number.isNaN(priceNum) || priceNum <= 0) {
      Alert.alert('提示', '价格需大于0');
      return;
    }
    const quantityNum = parseInt(quantity, 10);
    if (!quantity.trim() || Number.isNaN(quantityNum) || quantityNum < 0) {
      Alert.alert('提示', '库存不能为负数');
      return;
    }
    setPriceSaving(true);
    try {
      const res = await updateItemPrice(cookieId, itemId, {
        price: priceNum,
        quantity: quantityNum,
      });
      if (!res.success) {
        Alert.alert('改价失败', res.message || '未知错误');
        return;
      }
      Alert.alert('改价成功', res.message || '价格与库存已更新');
    } catch (e) {
      Alert.alert('改价失败', `${(e as Error).message || '未知错误'}\n${BACKEND_VERSION_HINT}`);
    } finally {
      setPriceSaving(false);
    }
  }

  /** 多规格快捷改价：提交每个 SKU 的价格与库存 */
  async function handleSkuPriceSave() {
    if (!cookieId || !itemId || priceSaving || platformError) return;
    for (const sku of priceSkus) {
      const p = parseFloat(sku.price);
      if (!sku.price || Number.isNaN(p) || p <= 0) {
        Alert.alert('提示', `规格「${sku.label}」价格需大于0`);
        return;
      }
      const q = parseInt(sku.quantity, 10);
      if (!sku.quantity || Number.isNaN(q) || q < 0) {
        Alert.alert('提示', `规格「${sku.label}」库存不能为负数`);
        return;
      }
    }
    setPriceSaving(true);
    try {
      const res = await updateItemPrice(cookieId, itemId, {
        skus: priceSkus.map((sku) => ({
          sku_id: sku.skuId,
          price: parseFloat(sku.price),
          quantity: parseInt(sku.quantity, 10),
        })),
      });
      if (!res.success) {
        Alert.alert('改价失败', res.message || '未知错误');
        return;
      }
      Alert.alert('改价成功', res.message || '规格价格与库存已更新');
    } catch (e) {
      Alert.alert('改价失败', `${(e as Error).message || '未知错误'}\n${BACKEND_VERSION_HINT}`);
    } finally {
      setPriceSaving(false);
    }
  }

  /** 切换本地"多规格 / 多数量发货"标记（供商品列表筛选）；请求进行中禁用开关避免并发乱序 */
  async function handleToggleFlag(kind: 'spec' | 'qty', value: boolean) {
    if (!cookieId || !itemId || flagSaving) return;
    const setter = kind === 'spec' ? setFlagMultiSpec : setFlagMultiQty;
    const prev = kind === 'spec' ? flagMultiSpec : flagMultiQty;
    setter(value);
    setFlagSaving(true);
    try {
      if (kind === 'spec') await setItemMultiSpec(cookieId, itemId, value);
      else await setItemMultiQuantityDelivery(cookieId, itemId, value);
    } catch (e) {
      setter(prev);
      Alert.alert('操作失败', (e as Error).message || '未知错误');
    } finally {
      setFlagSaving(false);
    }
  }

  /** 保存默认回复：reply_image/reply_type(image) 移动端不编辑，原样回传避免丢配置 */
  async function handleSaveDefaultReply() {
    if (!cookieId || !itemId || replySaving) return;
    if (replyType === 'api' && !replyApiUrl.trim()) {
      Alert.alert('提示', 'API 类型请填写 API 地址');
      return;
    }
    let timeout = parseInt(replyApiTimeout, 10);
    if (Number.isNaN(timeout) || timeout <= 0) timeout = 80;
    setReplySaving(true);
    try {
      const msg = await saveItemDefaultReply(cookieId, itemId, {
        reply_content: replyContent,
        reply_image: replyImage,
        enabled: replyEnabled,
        reply_once: replyOnce,
        reply_type: replyType,
        api_url: replyApiUrl.trim(),
        api_timeout: timeout,
      });
      Alert.alert('保存成功', msg || '默认回复已保存');
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message || '未知错误');
    } finally {
      setReplySaving(false);
    }
  }

  async function handleSaveAiPrompt() {
    if (!cookieId || !itemId || aiSaving) return;
    setAiSaving(true);
    try {
      const msg = await saveItemAiPrompt(cookieId, itemId, aiPrompt);
      Alert.alert('保存成功', msg || 'AI提示词已保存');
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message || '未知错误');
    } finally {
      setAiSaving(false);
    }
  }

  async function handleSaveQueryButtons() {
    if (!cookieId || !itemId || querySaving) return;
    let buttons: QueryButton[];
    try {
      buttons = serializeQueryButtons(queryDrafts);
    } catch (e) {
      Alert.alert('请检查配置', (e as Error).message);
      return;
    }
    setQuerySaving(true);
    try {
      const msg = await saveItemQueryButtons(cookieId, itemId, buttons);
      Alert.alert('保存成功', msg || '查询配置已保存');
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message || '未知错误');
    } finally {
      setQuerySaving(false);
    }
  }

  const updateQueryDraft = (key: string, patch: Partial<QueryButtonDraft>) => {
    setQueryDrafts((prev) => prev.map((d) => (d.key === key ? { ...d, ...patch } : d)));
  };

  const removeQueryDraft = (key: string) => {
    setQueryDrafts((prev) => prev.filter((d) => d.key !== key));
  };

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载商品详情..." />
      </SafeAreaView>
    );
  }

  if (!paramsReady || loadError) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <View style={styles.errorWrap}>
          <Text style={[styles.errorTitle, { color: c.error }]}>无法编辑该商品</Text>
          <Text style={[styles.errorText, { color: c.textSecondary }]}>
            {loadError ?? '缺少 cookieId 或 itemId 参数'}
          </Text>
          <Text style={[styles.errorHint, { color: c.textMuted }]}>{BACKEND_VERSION_HINT}</Text>
          {paramsReady && (
            <Button label="重试" variant="secondary" onPress={load} style={styles.retryBtn} />
          )}
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <ScrollView
        contentContainerStyle={styles.list}
        keyboardShouldPersistTaps="handled"
      >
        {/* 基础信息：原有表单内容，默认展开 */}
        <CollapsibleSection
          title="基础信息"
          expanded={expanded.basic}
          onToggle={() => toggleSection('basic')}
        >
          {platformError ? (
            <View
              style={[
                styles.platformBanner,
                { backgroundColor: c.surfaceAlt, borderLeftColor: c.warning },
              ]}
            >
              <Text style={[styles.platformBannerText, { color: c.textSecondary }]}>
                {platformError}，平台信息不可编辑，下方为本地信息
              </Text>
            </View>
          ) : null}

          <View style={styles.group}>
            <Text style={[styles.label, { color: c.textSecondary }]}>标题</Text>
            <Input
              value={title}
              onChangeText={setTitle}
              maxLength={200}
              multiline
              editable={!platformError}
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
              editable={!platformError}
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
              editable={!platformError}
              placeholder="0.00"
            />

            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
              原价（元，选填）
            </Text>
            <Input
              value={originalPrice}
              onChangeText={setOriginalPrice}
              keyboardType="decimal-pad"
              editable={!platformError}
              placeholder="0.00"
            />

            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
              库存
            </Text>
            <Input
              value={quantity}
              onChangeText={setQuantity}
              keyboardType="number-pad"
              editable={!platformError}
              placeholder="1"
            />

            {!isMultiSpecItem ? (
              <Button
                label="仅保存价格与库存（快捷改价）"
                variant="secondary"
                onPress={handleQuickPriceSave}
                loading={priceSaving}
                disabled={Boolean(platformError)}
                style={styles.quickPriceBtn}
              />
            ) : null}
          </View>

          {isMultiSpecItem ? (
            <View style={styles.group}>
              <Text style={[styles.label, { color: c.textSecondary }]}>改价（多规格）</Text>
              <Text style={[styles.hintText, { color: c.textMuted }]}>
                逐个规格设置价格与库存，保存后立即生效
              </Text>
              {priceSkus.map((sku, idx) => (
                <View key={sku.skuId || idx} style={styles.skuRow}>
                  <Text style={[styles.skuLabel, { color: c.text }]} numberOfLines={2}>
                    {sku.label}
                  </Text>
                  <View style={styles.skuInputs}>
                    <Input
                      value={sku.price}
                      onChangeText={(v) => updateSkuRow(idx, 'price', v)}
                      keyboardType="decimal-pad"
                      editable={!platformError}
                      placeholder="价格"
                      style={styles.skuInput}
                    />
                    <Input
                      value={sku.quantity}
                      onChangeText={(v) => updateSkuRow(idx, 'quantity', v)}
                      keyboardType="number-pad"
                      editable={!platformError}
                      placeholder="库存"
                      style={styles.skuInput}
                    />
                  </View>
                </View>
              ))}
              <Button
                label="保存全部规格价格"
                onPress={handleSkuPriceSave}
                loading={priceSaving}
                disabled={Boolean(platformError)}
                style={styles.quickPriceBtn}
              />
            </View>
          ) : null}

          <View style={styles.group}>
            <Text style={[styles.label, { color: c.textSecondary }]}>商品图片</Text>
            {images.length > 0 ? (
              // TODO: 暂仅展示回填图片，后续支持增删与排序
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                <View style={styles.imageRow}>
                  {images.map((uri, idx) => (
                    <Image
                      key={`${uri}-${idx}`}
                      source={{ uri }}
                      style={[styles.thumbnail, { backgroundColor: c.borderLight }]}
                    />
                  ))}
                </View>
              </ScrollView>
            ) : (
              <Text style={[styles.emptyText, { color: c.textMuted }]}>暂无图片</Text>
            )}
          </View>

          <View style={styles.group}>
            <Text style={[styles.label, { color: c.textSecondary }]}>配送方式</Text>
            <View style={styles.chipRow}>
              {SHIPPING_OPTIONS.map((opt) => {
                const selected = shippingMethod === opt.value;
                return (
                  <Pressable
                    key={opt.value}
                    onPress={() => setShippingMethod(opt.value)}
                    disabled={Boolean(platformError)}
                    style={[
                      styles.chip,
                      {
                        backgroundColor: selected ? c.primary : c.background,
                        borderColor: selected ? c.primary : c.border,
                        opacity: platformError ? 0.5 : 1,
                      },
                    ]}
                  >
                    <Text style={[styles.chipText, { color: selected ? '#FFF' : c.text }]}>
                      {opt.label}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
            {shippingMethod === 'fixed' && (
              <>
                <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
                  运费（元）
                </Text>
                <Input
                  value={postage}
                  onChangeText={setPostage}
                  keyboardType="decimal-pad"
                  editable={!platformError}
                  placeholder="0.00"
                />
              </>
            )}

            <View style={[styles.switchRow, { borderTopColor: c.borderLight }]}>
              <Text style={[styles.switchLabel, { color: c.text }]}>支持自提</Text>
              <Switch
                value={supportPickup}
                onValueChange={setSupportPickup}
                disabled={Boolean(platformError)}
                trackColor={{ false: c.border, true: c.primary }}
              />
            </View>
          </View>

          <Button
            label="保存修改"
            onPress={handleSave}
            loading={saving}
            disabled={Boolean(platformError)}
            style={styles.saveBtn}
          />
        </CollapsibleSection>

        {/* 卡券关联：跳转现有关联页，不重造关联逻辑 */}
        <CollapsibleSection
          title="卡券关联"
          expanded={expanded.cards}
          onToggle={() => toggleSection('cards')}
        >
          <Text style={[styles.hintText, { color: c.textMuted }]}>
            将卡券关联到本商品，买家下单后按关联卡券发货。关联操作在「关联商品」页面完成。
          </Text>
          <Button
            label="管理卡券关联"
            variant="secondary"
            onPress={() =>
              router.push({
                pathname: '/(tabs)/mine/card-item-relation',
                params: { cookieId: cookieId ?? '', itemId: itemId ?? '' },
              })
            }
            style={styles.cardActionBtn}
          />
        </CollapsibleSection>

        {/* 发货设置：多规格 / 多数量发货标记（本地库标记，供商品列表筛选） */}
        <CollapsibleSection
          title="发货设置"
          expanded={expanded.delivery}
          onToggle={() => toggleSection('delivery')}
        >
          <View style={[styles.switchRowNoBorder]}>
            <Text style={[styles.switchLabel, { color: c.text }]}>多规格</Text>
            <Switch
              value={flagMultiSpec}
              onValueChange={(v) => handleToggleFlag('spec', v)}
              disabled={flagSaving}
              trackColor={{ false: c.border, true: c.primary }}
            />
          </View>
          <View style={[styles.switchRow, { borderTopColor: c.borderLight }]}>
            <Text style={[styles.switchLabel, { color: c.text }]}>多数量发货</Text>
            <Switch
              value={flagMultiQty}
              onValueChange={(v) => handleToggleFlag('qty', v)}
              disabled={flagSaving}
              trackColor={{ false: c.border, true: c.primary }}
            />
          </View>
          <Text style={[styles.hintText, { color: c.textMuted }]}>
            标记仅用于商品列表筛选，不影响闲鱼平台商品
          </Text>
        </CollapsibleSection>

        {/* 默认回复：展开时加载；图片上传请前往 web 端 */}
        <CollapsibleSection
          title="默认回复"
          expanded={expanded.reply}
          onToggle={() => toggleSection('reply')}
        >
          {replyLoading ? (
            <ActivityIndicator color={c.primary} style={styles.inlineLoading} />
          ) : replyLoadError ? (
            <LoadErrorRow message={replyLoadError} onRetry={loadDefaultReply} />
          ) : (
            <>
              <View style={styles.switchRowNoBorder}>
                <Text style={[styles.switchLabel, { color: c.text }]}>启用默认回复</Text>
                <Switch
                  value={replyEnabled}
                  onValueChange={setReplyEnabled}
                  trackColor={{ false: c.border, true: c.primary }}
                />
              </View>

              <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
                回复类型
              </Text>
              <View style={styles.chipRow}>
                {(
                  [
                    { value: 'text', label: '文本' },
                    { value: 'api', label: '接口' },
                  ] as const
                ).map((opt) => {
                  const selected = replyType === opt.value;
                  return (
                    <Pressable
                      key={opt.value}
                      onPress={() => setReplyType(opt.value)}
                      style={[
                        styles.chip,
                        {
                          backgroundColor: selected ? c.primary : c.background,
                          borderColor: selected ? c.primary : c.border,
                        },
                      ]}
                    >
                      <Text style={[styles.chipText, { color: selected ? '#FFF' : c.text }]}>
                        {opt.label}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>

              {replyType === 'text' ? (
                <>
                  <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
                    回复内容
                  </Text>
                  <Input
                    value={replyContent}
                    onChangeText={setReplyContent}
                    multiline
                    placeholder="买家首次咨询时自动回复的内容"
                    style={styles.textArea}
                  />
                </>
              ) : null}

              {replyType === 'api' ? (
                <>
                  <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
                    API 地址
                  </Text>
                  <Input
                    value={replyApiUrl}
                    onChangeText={setReplyApiUrl}
                    autoCapitalize="none"
                    keyboardType="url"
                    placeholder="https://example.com/reply"
                  />
                  <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
                    超时时间（秒）
                  </Text>
                  <Input
                    value={replyApiTimeout}
                    onChangeText={setReplyApiTimeout}
                    keyboardType="number-pad"
                    placeholder="80"
                  />
                </>
              ) : null}

              {replyType === 'image' ? (
                <Text style={[styles.hintText, { color: c.textMuted }]}>
                  当前为图片回复，图片上传与编辑请前往 web 端；在此保存将保留原图片配置
                </Text>
              ) : null}

              <View style={[styles.switchRow, { borderTopColor: c.borderLight }]}>
                <Text style={[styles.switchLabel, { color: c.text }]}>每个买家仅回复一次</Text>
                <Switch
                  value={replyOnce}
                  onValueChange={setReplyOnce}
                  trackColor={{ false: c.border, true: c.primary }}
                />
              </View>

              <Text style={[styles.hintText, { color: c.textMuted }]}>
                图片回复的上传请前往 web 端配置
              </Text>

              <Button
                label="保存默认回复"
                onPress={handleSaveDefaultReply}
                loading={replySaving}
                disabled={!replyLoaded}
                style={styles.cardActionBtn}
              />
            </>
          )}
        </CollapsibleSection>

        {/* AI提示词：展开时加载 */}
        <CollapsibleSection
          title="AI提示词"
          expanded={expanded.ai}
          onToggle={() => toggleSection('ai')}
        >
          {aiLoading ? (
            <ActivityIndicator color={c.primary} style={styles.inlineLoading} />
          ) : aiLoadError ? (
            <LoadErrorRow message={aiLoadError} onRetry={loadAiPrompt} />
          ) : (
            <>
              <Text style={[styles.hintText, { color: c.textMuted }]}>
                针对本商品的 AI 回复提示词，优先级高于账号级配置
              </Text>
              <Input
                value={aiPrompt}
                onChangeText={setAiPrompt}
                multiline
                placeholder="请输入本商品的 AI 提示词"
                style={styles.textArea}
              />
              <Button
                label="保存AI提示词"
                onPress={handleSaveAiPrompt}
                loading={aiSaving}
                disabled={!aiLoaded}
                style={styles.cardActionBtn}
              />
            </>
          )}
        </CollapsibleSection>

        {/* 查询配置：展开时加载；文本行编辑格式与 web 端一致 */}
        <CollapsibleSection
          title="查询配置"
          expanded={expanded.query}
          onToggle={() => toggleSection('query')}
        >
          {queryLoading ? (
            <ActivityIndicator color={c.primary} style={styles.inlineLoading} />
          ) : queryLoadError ? (
            <LoadErrorRow message={queryLoadError} onRetry={loadQueryButtons} />
          ) : (
            <>
              <Text style={[styles.hintText, { color: c.textMuted }]}>
                买家在发货页点击按钮后，由服务端代为请求并展示结果。可用变量：
                {'{cookie}'} {'{account}'} {'{api_key}'} {'{line}'}，可用于 URL、请求头与 Body。
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
                      onPress={() => removeQueryDraft(draft.key)}
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
                      const selected = draft.method === m;
                      return (
                        <Pressable
                          key={m}
                          onPress={() => updateQueryDraft(draft.key, { method: m })}
                          style={[
                            styles.chip,
                            {
                              backgroundColor: selected ? c.primary : c.surface,
                              borderColor: selected ? c.primary : c.border,
                            },
                          ]}
                        >
                          <Text style={[styles.chipText, { color: selected ? '#FFF' : c.text }]}>
                            {m}
                          </Text>
                        </Pressable>
                      );
                    })}
                  </View>

                  <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
                    URL
                  </Text>
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
                      <Text
                        style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}
                      >
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
              <Button
                label="保存查询配置"
                onPress={handleSaveQueryButtons}
                loading={querySaving}
                disabled={!queryLoaded}
                style={styles.cardSaveBtn}
              />
            </>
          )}
        </CollapsibleSection>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  list: { padding: spacing.lg, gap: spacing.md },
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
  platformBanner: {
    marginTop: spacing.sm,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.sm,
    borderLeftWidth: 3,
  },
  platformBannerText: { ...typography.small, lineHeight: 18 },
  label: { ...typography.caption },
  descriptionInput: { minHeight: 100, textAlignVertical: 'top' },
  textArea: { minHeight: 100, textAlignVertical: 'top', paddingVertical: spacing.sm },
  textAreaSmall: { minHeight: 72, textAlignVertical: 'top', paddingVertical: spacing.sm },
  imageRow: { flexDirection: 'row', gap: spacing.sm, paddingVertical: spacing.xs },
  thumbnail: { width: 56, height: 56, borderRadius: radius.sm },
  emptyText: { ...typography.caption, paddingVertical: spacing.sm },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm, paddingVertical: spacing.xs },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  chipText: { ...typography.caption },
  switchRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.sm,
    paddingTop: spacing.md,
    borderTopWidth: 1,
  },
  switchRowNoBorder: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.sm,
  },
  switchLabel: { ...typography.body },
  hintText: { ...typography.small, paddingVertical: spacing.xs, lineHeight: 18 },
  quickPriceBtn: { marginTop: spacing.md },
  skuRow: { marginTop: spacing.sm, gap: spacing.xs },
  skuLabel: { ...typography.small, fontWeight: '600' },
  skuInputs: { flexDirection: 'row', gap: spacing.sm },
  skuInput: { flex: 1 },
  saveBtn: { marginTop: spacing.md },
  cardActionBtn: { marginTop: spacing.md },
  cardSaveBtn: { marginTop: spacing.sm },
  inlineLoading: { marginVertical: spacing.lg },
  loadErrorWrap: { alignItems: 'center', paddingVertical: spacing.md, gap: spacing.sm },
  loadErrorText: { ...typography.caption, textAlign: 'center' },
  loadErrorBtn: { minHeight: 40, paddingHorizontal: spacing.xl },
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
  errorWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl, gap: spacing.sm },
  errorTitle: { ...typography.heading },
  errorText: { ...typography.caption, textAlign: 'center' },
  errorHint: { ...typography.small, textAlign: 'center' },
  retryBtn: { marginTop: spacing.md, minHeight: 40 },
});
