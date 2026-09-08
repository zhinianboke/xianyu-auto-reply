import { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  Switch,
  Image,
  Alert,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { Card, Button, Input, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getSellerItemDetail,
  updateSellerItem,
  type SellerItemForm,
} from '@/api/wrappers/item-edit';

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

export default function ItemEditScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();
  const { cookieId, itemId } = useLocalSearchParams<{ cookieId: string; itemId: string }>();

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
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

  const paramsReady = Boolean(cookieId && itemId);

  const load = useCallback(async () => {
    if (!cookieId || !itemId) {
      setLoadError('缺少 cookieId 或 itemId 参数');
      setLoading(false);
      return;
    }
    setLoading(true);
    setLoadError(null);
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
      setLoadError((e as Error).message || '加载商品详情失败');
    } finally {
      setLoading(false);
    }
  }, [cookieId, itemId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleSave() {
    if (!cookieId || !itemId) return;
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
        <Card style={styles.section}>
          <Text style={[styles.label, { color: c.textSecondary }]}>标题</Text>
          <Input
            value={title}
            onChangeText={setTitle}
            maxLength={200}
            multiline
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
        </Card>

        <Card style={styles.section}>
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
            库存
          </Text>
          <Input
            value={quantity}
            onChangeText={setQuantity}
            keyboardType="number-pad"
            placeholder="1"
          />
        </Card>

        <Card style={styles.section}>
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
        </Card>

        <Card style={styles.section}>
          <Text style={[styles.label, { color: c.textSecondary }]}>配送方式</Text>
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
          {shippingMethod === 'fixed' && (
            <>
              <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
                运费（元）
              </Text>
              <Input
                value={postage}
                onChangeText={setPostage}
                keyboardType="decimal-pad"
                placeholder="0.00"
              />
            </>
          )}

          <View style={[styles.switchRow, { borderBottomColor: c.borderLight }]}>
            <Text style={[styles.switchLabel, { color: c.text }]}>支持自提</Text>
            <Switch
              value={supportPickup}
              onValueChange={setSupportPickup}
              trackColor={{ false: c.border, true: c.primary }}
            />
          </View>
        </Card>

        <Button
          label="保存修改"
          onPress={handleSave}
          loading={saving}
          style={styles.saveBtn}
        />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  list: { padding: spacing.lg, gap: spacing.md },
  section: { gap: spacing.xs },
  label: { ...typography.caption },
  descriptionInput: { minHeight: 100, textAlignVertical: 'top' },
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
  switchLabel: { ...typography.body },
  saveBtn: { marginTop: spacing.sm },
  errorWrap: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: spacing.xl, gap: spacing.sm },
  errorTitle: { ...typography.heading },
  errorText: { ...typography.caption, textAlign: 'center' },
  errorHint: { ...typography.small, textAlign: 'center' },
  retryBtn: { marginTop: spacing.md, minHeight: 40 },
});
