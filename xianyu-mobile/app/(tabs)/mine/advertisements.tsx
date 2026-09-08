/**
 * 广告申请 / 管理（移动端）。
 *
 * 对应 web：AdApply（用户：新建/编辑/删除/付款）+ AdManage（管理员：审核）。
 * 功能：
 *  1. 图片上传：expo-image-picker 选图 → POST /api/v1/upload/upload-image → 表单带 image_url
 *  2. 广告编辑：预填表单 → updateAdvertisement（已通过的广告禁止编辑）
 *  3. 状态筛选 FilterTabs：全部 / 待审核 / 已通过 / 已拒绝（客户端过滤）
 *  4. 广告支付：createAdPayment 拿二维码 → 轮询 checkAdPaymentStatus，approved 即完成
 *
 * 仅用户态显示编辑/支付；管理员态显示通过/拒绝。状态枚举：
 * unpaid=待付款 / pending=待审核 / approved=已通过 / rejected=已拒绝。
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Alert,
  Image,
  Modal,
  ScrollView,
  RefreshControl,
  ActivityIndicator,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import QRCode from 'react-native-qrcode-svg';
import { X, CheckCircle, AlertCircle, ImagePlus } from 'lucide-react-native';
import {
  Card,
  Button,
  Input,
  Loading,
  Badge,
  FilterTabs,
  FormModal,
} from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { useAuthStore } from '@/stores/auth';
import {
  getAdvertisements,
  getAdminAdvertisements,
  createAdvertisement,
  updateAdvertisement,
  deleteAdvertisement,
  approveAdvertisement,
  rejectAdvertisement,
  getAdPrices,
  uploadAdImage,
  createAdPayment,
  checkAdPaymentStatus,
  type Advertisement,
  type AdPrices,
} from '@/api/wrappers/advertisements';

type AdType = 'carousel' | 'text';
type FilterKey = 'all' | 'pending' | 'approved' | 'rejected';
type PayStep = 'confirm' | 'qrcode' | 'success' | 'error';

const AD_TYPES: AdType[] = ['text', 'carousel'];

type BadgeVariant = 'success' | 'warning' | 'danger' | 'gray';

/** 状态 -> Badge 变体 + 文案 */
function statusBadge(status: string): { label: string; variant: BadgeVariant } {
  const s = (status || '').toLowerCase();
  if (s === 'approved' || s === 'active' || s === 'online')
    return { label: '已通过', variant: 'success' };
  if (s === 'pending' || s === 'reviewing') return { label: '待审核', variant: 'warning' };
  if (s === 'unpaid') return { label: '待付款', variant: 'danger' };
  if (s === 'rejected') return { label: '已拒绝', variant: 'danger' };
  return { label: status || '未知', variant: 'gray' };
}

/** 广告归属的筛选 tab（unpaid 等不归入具体 tab，仅出现在"全部"）。 */
function filterOf(ad: Advertisement): FilterKey {
  const s = (ad.status || '').toLowerCase();
  if (s === 'approved' || s === 'active' || s === 'online') return 'approved';
  if (s === 'pending' || s === 'reviewing') return 'pending';
  if (s === 'rejected') return 'rejected';
  return 'all';
}

/** 计算 n 个月后的日期（YYYY-MM-DD） */
function expireAfterMonths(months: number): string {
  const d = new Date();
  d.setMonth(d.getMonth() + months);
  return d.toISOString().split('T')[0];
}

export default function AdvertisementsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const user = useAuthStore((s) => s.user);
  const isAdmin = !!user?.is_admin;

  // 列表
  const [ads, setAds] = useState<Advertisement[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<FilterKey>('all');

  // 价格（创建/编辑时预估费用）
  const [adPrices, setAdPrices] = useState<AdPrices>({});

  // 表单（新建/编辑共用）
  const [formVisible, setFormVisible] = useState(false);
  const [editingAd, setEditingAd] = useState<Advertisement | null>(null);
  const [fTitle, setFTitle] = useState('');
  const [fContent, setFContent] = useState('');
  const [fLink, setFLink] = useState('');
  const [fType, setFType] = useState<AdType>('text');
  const [fMonths, setFMonths] = useState('1');
  const [fImageUrl, setFImageUrl] = useState('');
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);

  // 图片预览
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  // 付款弹窗
  const [payAd, setPayAd] = useState<Advertisement | null>(null);
  const [payStep, setPayStep] = useState<PayStep>('confirm');
  const [payLoading, setPayLoading] = useState(false);
  const [payQr, setPayQr] = useState('');
  const [payOrderNo, setPayOrderNo] = useState('');
  const [payMsg, setPayMsg] = useState('');
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      setRefreshing(true);
      const [list, prices] = await Promise.all([
        isAdmin ? getAdminAdvertisements() : getAdvertisements(),
        getAdPrices().catch(() => ({})),
      ]);
      setAds(list);
      setAdPrices(prices);
    } catch (e) {
      Alert.alert('加载失败', (e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    load();
  }, [load]);

  // 卸载时清理付款轮询
  useEffect(() => {
    return () => clearPoll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const counts = useMemo(() => {
    const m: Record<FilterKey, number> = { all: ads.length, pending: 0, approved: 0, rejected: 0 };
    for (const a of ads) {
      const f = filterOf(a);
      if (f !== 'all') m[f]++;
    }
    return m;
  }, [ads]);

  const tabs = useMemo(
    () => [
      { key: 'all', label: '全部', count: counts.all },
      { key: 'pending', label: '待审核', count: counts.pending },
      { key: 'approved', label: '已通过', count: counts.approved },
      { key: 'rejected', label: '已拒绝', count: counts.rejected },
    ],
    [counts],
  );

  const filteredAds = useMemo(
    () => (filter === 'all' ? ads : ads.filter((a) => filterOf(a) === filter)),
    [ads, filter],
  );

  // 预估费用 / 到期日
  const estAmount = useMemo(() => {
    const m = parseInt(fMonths, 10);
    if (!m || m <= 0) return null;
    const unit = parseFloat(adPrices[fType] || '0');
    if (!unit) return null;
    return (unit * m).toFixed(2);
  }, [fMonths, fType, adPrices]);

  const estExpire = useMemo(() => {
    const m = parseInt(fMonths, 10);
    return m && m > 0 ? expireAfterMonths(m) : null;
  }, [fMonths]);

  // --- 付款轮询 ---

  const clearPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startPolling = useCallback(
    (adId: number, orderNo: string) => {
      clearPoll();
      pollRef.current = setInterval(async () => {
        try {
          const res = await checkAdPaymentStatus(adId, orderNo);
          if (res.status === 'approved') {
            clearPoll();
            setPayStep('success');
            setTimeout(() => {
              handleClosePayment();
              load();
            }, 1500);
          }
        } catch {
          // 轮询失败静默重试
        }
      }, 3000);
    },
    [clearPoll, load],
  );

  const resetPayment = useCallback(() => {
    setPayStep('confirm');
    setPayLoading(false);
    setPayQr('');
    setPayOrderNo('');
    setPayMsg('');
    clearPoll();
  }, [clearPoll]);

  const handleClosePayment = useCallback(() => {
    clearPoll();
    resetPayment();
    setPayAd(null);
  }, [clearPoll, resetPayment]);

  async function handleSubmitPayment() {
    if (!payAd || payLoading) return;
    setPayLoading(true);
    try {
      const order = await createAdPayment(payAd.id);
      setPayQr(order.qr_code);
      setPayOrderNo(order.order_no);
      setPayStep('qrcode');
      startPolling(payAd.id, order.order_no);
    } catch (e) {
      setPayMsg((e as Error).message || '网络错误，请稍后重试');
      setPayStep('error');
    } finally {
      setPayLoading(false);
    }
  }

  // --- 图片上传 ---

  async function handlePickImage() {
    const perm = await ImagePicker.getMediaLibraryPermissionsAsync();
    if (perm.status !== 'granted') {
      const req = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (req.status !== 'granted') {
        Alert.alert('无相册权限', '请在系统设置中允许访问相册后再试');
        return;
      }
    }
    try {
      const result = await ImagePicker.launchImageLibraryAsync({
        mediaTypes: ImagePicker.MediaTypeOptions.Images,
        allowsEditing: true,
        aspect: [1, 1],
        quality: 0.8,
      });
      if (result.canceled || !result.assets?.length) return;
      const uri = result.assets[0].uri;
      setUploading(true);
      const url = await uploadAdImage(uri);
      setFImageUrl(url);
    } catch (e) {
      Alert.alert('上传失败', (e as Error).message);
    } finally {
      setUploading(false);
    }
  }

  // --- 表单 ---

  function openCreate() {
    setEditingAd(null);
    setFTitle('');
    setFContent('');
    setFLink('');
    setFType('text');
    setFMonths('1');
    setFImageUrl('');
    setFormVisible(true);
  }

  function openEdit(ad: Advertisement) {
    setEditingAd(ad);
    setFTitle(ad.title);
    setFContent(ad.content || '');
    setFLink(ad.link || '');
    setFType(ad.ad_type === 'carousel' ? 'carousel' : 'text');
    setFMonths(ad.months ? String(ad.months) : '1');
    setFImageUrl(ad.image_url || '');
    setFormVisible(true);
  }

  async function handleSave() {
    if (!fTitle.trim()) {
      Alert.alert('提示', '请输入广告标题');
      return;
    }
    const months = parseInt(fMonths, 10);
    if (!months || months <= 0) {
      Alert.alert('提示', '请输入有效的月数（大于 0 的整数）');
      return;
    }
    setSaving(true);
    try {
      const payload = {
        title: fTitle.trim(),
        ad_type: fType,
        months,
        content: fContent.trim() || undefined,
        link: fLink.trim() || undefined,
        image_url: fImageUrl || undefined,
      };
      if (editingAd) {
        await updateAdvertisement(editingAd.id, payload);
      } else {
        await createAdvertisement(payload);
      }
      setFormVisible(false);
      await load();
    } catch (e) {
      Alert.alert(editingAd ? '保存失败' : '创建失败', (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function handleDelete(ad: Advertisement) {
    Alert.alert('确认删除', `删除广告"${ad.title}"？`, [
      { text: '取消' },
      {
        text: '删除',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteAdvertisement(ad.id);
            await load();
          } catch (e) {
            Alert.alert('删除失败', (e as Error).message);
          }
        },
      },
    ]);
  }

  async function handleApprove(id: number) {
    try {
      await approveAdvertisement(id);
      await load();
    } catch (e) {
      Alert.alert('操作失败', (e as Error).message);
    }
  }

  function handleReject(id: number) {
    Alert.alert('拒绝广告', '确定拒绝该广告？', [
      { text: '取消' },
      {
        text: '拒绝',
        style: 'destructive',
        onPress: async () => {
          try {
            await rejectAdvertisement(id);
            await load();
          } catch (e) {
            Alert.alert('操作失败', (e as Error).message);
          }
        },
      },
    ]);
  }

  // --- 渲染 ---

  if (loading) {
    return (
      <SafeAreaView
        style={[styles.container, { backgroundColor: c.background }]}
        edges={['left', 'right', 'bottom']}
      >
        <Loading label="加载广告..." />
      </SafeAreaView>
    );
  }

  const textAreaStyle = [
    styles.textArea,
    { backgroundColor: c.background, color: c.text, borderColor: c.border },
  ];

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: c.background }]}
      edges={['left', 'right', 'bottom']}
    >
      {/* 顶栏 */}
      <View style={styles.header}>
        <View style={styles.headerTitle}>
          <Text style={[styles.title, { color: c.text }]} numberOfLines={1}>
            {isAdmin ? '广告管理' : '广告申请'}
          </Text>
        </View>
        <View style={styles.headerActions}>
          <Button
            label="新增"
            variant="secondary"
            onPress={openCreate}
            style={styles.headerBtn}
          />
          <Button
            label="刷新"
            variant="secondary"
            onPress={load}
            loading={refreshing && !loading}
            style={styles.headerBtn}
          />
        </View>
      </View>

      <FilterTabs tabs={tabs} active={filter} onChange={(k) => setFilter(k as FilterKey)} />

      <FlatList
        data={filteredAds}
        keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: c.textMuted }]}>暂无广告</Text>
          </View>
        }
        renderItem={({ item }) => {
          const badge = statusBadge(item.status);
          const sLower = (item.status || '').toLowerCase();
          const isUnpaid = sLower === 'unpaid';
          const isApproved = sLower === 'approved' || sLower === 'active' || sLower === 'online';
          const isPending = sLower === 'pending' || sLower === 'reviewing';
          return (
            <Card style={styles.card}>
              {/* 标题行 */}
              <View style={styles.cardHeader}>
                <View
                  style={[
                    styles.typeBadge,
                    {
                      backgroundColor: item.ad_type === 'carousel' ? c.primary : c.surfaceAlt,
                    },
                  ]}
                >
                  <Text
                    style={[
                      styles.typeText,
                      { color: item.ad_type === 'carousel' ? '#FFF' : c.textSecondary },
                    ]}
                  >
                    {item.ad_type === 'carousel' ? '轮播' : '文字'}
                  </Text>
                </View>
                <Text style={[styles.adTitle, { color: c.text }]} numberOfLines={1}>
                  {item.title}
                </Text>
                <Badge label={badge.label} variant={badge.variant} />
              </View>

              {/* 缩略图 + 元信息 */}
              <View style={styles.metaRow}>
                {item.image_url ? (
                  <Pressable onPress={() => setPreviewUrl(item.image_url!)}>
                    <Image
                      source={{ uri: item.image_url }}
                      style={[styles.thumb, { backgroundColor: c.surfaceAlt }]}
                    />
                  </Pressable>
                ) : null}
                <View style={styles.metaCol}>
                  {item.content ? (
                    <Text
                      style={[styles.adContent, { color: c.textSecondary }]}
                      numberOfLines={2}
                    >
                      {item.content}
                    </Text>
                  ) : null}
                  <View style={styles.metaLine}>
                    {item.expire_date ? (
                      <Text style={[styles.metaText, { color: c.textMuted }]}>
                        到期 {item.expire_date}
                      </Text>
                    ) : null}
                    {item.months ? (
                      <Text style={[styles.metaText, { color: c.textMuted }]}>
                        {item.months} 月
                      </Text>
                    ) : null}
                    {item.total_amount ? (
                      <Text style={[styles.metaText, { color: c.warning, fontWeight: '600' }]}>
                        ¥{item.total_amount}
                      </Text>
                    ) : null}
                  </View>
                </View>
              </View>

              {/* 操作 */}
              <View style={styles.cardActions}>
                {isAdmin ? (
                  isPending ? (
                    <Button
                      label="通过"
                      onPress={() => handleApprove(item.id)}
                      style={styles.actionBtn}
                    />
                  ) : (
                    <Button
                      label="拒绝"
                      variant="danger"
                      onPress={() => handleReject(item.id)}
                      style={styles.actionBtn}
                    />
                  )
                ) : (
                  <>
                    {isUnpaid && (
                      <Button
                        label="支付"
                        onPress={() => {
                          resetPayment();
                          setPayAd(item);
                        }}
                        style={styles.actionBtn}
                      />
                    )}
                    {!isApproved && (
                      <Button
                        label="编辑"
                        variant="secondary"
                        onPress={() => openEdit(item)}
                        style={styles.actionBtn}
                      />
                    )}
                  </>
                )}
                <Button
                  label="删除"
                  variant={isAdmin ? 'secondary' : 'danger'}
                  onPress={() => handleDelete(item)}
                  style={styles.actionBtn}
                />
              </View>
            </Card>
          );
        }}
      />

      {/* 新建/编辑表单 */}
      <FormModal
        visible={formVisible}
        onClose={() => setFormVisible(false)}
        title={editingAd ? '编辑广告' : '新建广告'}
      >
        <ScrollView
          style={styles.formScroll}
          contentContainerStyle={styles.formFields}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* 类型 */}
          <View style={styles.field}>
            <Text style={[styles.label, { color: c.textSecondary }]}>广告类型</Text>
            <View style={styles.typeSelector}>
              {AD_TYPES.map((t) => {
                const on = fType === t;
                return (
                  <Pressable
                    key={t}
                    onPress={() => setFType(t)}
                    style={[
                      styles.typeOption,
                      {
                        backgroundColor: on ? c.primary : c.background,
                        borderColor: on ? c.primary : c.border,
                      },
                    ]}
                  >
                    <Text style={[styles.typeOptionText, { color: on ? '#FFF' : c.text }]}>
                      {t === 'carousel' ? '轮播图' : '文字广告'}
                    </Text>
                  </Pressable>
                );
              })}
            </View>
          </View>

          {/* 标题 */}
          <View style={styles.field}>
            <Text style={[styles.label, { color: c.textSecondary }]}>标题 *</Text>
            <Input
              value={fTitle}
              onChangeText={setFTitle}
              placeholder="广告标题"
              maxLength={200}
            />
          </View>

          {/* 内容 */}
          <View style={styles.field}>
            <Text style={[styles.label, { color: c.textSecondary }]}>正文</Text>
            <Input
              value={fContent}
              onChangeText={setFContent}
              placeholder="广告正文内容（选填）"
              multiline
              style={textAreaStyle}
            />
          </View>

          {/* 链接 */}
          <View style={styles.field}>
            <Text style={[styles.label, { color: c.textSecondary }]}>链接</Text>
            <Input
              value={fLink}
              onChangeText={setFLink}
              placeholder="https://（选填）"
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
            />
          </View>

          {/* 月数 + 到期 */}
          <View style={styles.fieldRow}>
            <View style={styles.fieldCol}>
              <Text style={[styles.label, { color: c.textSecondary }]}>购买月数 *</Text>
              <Input
                value={fMonths}
                onChangeText={(v) => {
                  if (v === '' || /^[1-9]\d*$/.test(v)) setFMonths(v);
                }}
                keyboardType="numeric"
                placeholder="月数"
              />
            </View>
            <View style={styles.fieldCol}>
              <Text style={[styles.label, { color: c.textSecondary }]}>到期日期</Text>
              <View
                style={[
                  styles.readonlyField,
                  { backgroundColor: c.surfaceAlt, borderColor: c.border },
                ]}
              >
                <Text style={[styles.readonlyText, { color: c.textMuted }]}>
                  {estExpire || '自动计算'}
                </Text>
              </View>
            </View>
          </View>

          {/* 预估费用 */}
          {estAmount ? (
            <View
              style={[styles.amountBox, { backgroundColor: c.primaryLight, borderColor: c.primary }]}
            >
              <Text style={[styles.amountLabel, { color: c.primary }]}>
                预计费用 ¥{estAmount}
              </Text>
              <Text style={[styles.amountSub, { color: c.primary }]}>
                （{adPrices[fType] || '0'}元/月 × {fMonths}月）
              </Text>
            </View>
          ) : null}

          {/* 图片 */}
          <View style={styles.field}>
            <Text style={[styles.label, { color: c.textSecondary }]}>图片</Text>
            <View style={styles.imageRow}>
              {fImageUrl ? (
                <View style={styles.imageBox}>
                  <Image source={{ uri: fImageUrl }} style={styles.imagePreview} />
                  <Pressable
                    onPress={() => setFImageUrl('')}
                    style={[styles.removeBtn, { backgroundColor: c.error }]}
                    hitSlop={8}
                  >
                    <X size={12} color="#FFF" />
                  </Pressable>
                </View>
              ) : (
                <Pressable
                  onPress={handlePickImage}
                  disabled={uploading}
                  style={[styles.uploadBox, { borderColor: c.border, backgroundColor: c.background }]}
                >
                  {uploading ? (
                    <ActivityIndicator color={c.textMuted} />
                  ) : (
                    <ImagePlus size={22} color={c.textMuted} />
                  )}
                </Pressable>
              )}
              <Pressable
                onPress={handlePickImage}
                disabled={uploading || !fImageUrl}
                style={[
                  styles.changeBtn,
                  {
                    borderColor: c.border,
                    opacity: uploading || !fImageUrl ? 0.4 : 1,
                  },
                ]}
              >
                <Text style={[styles.changeText, { color: c.primary }]}>
                  {fImageUrl ? '重新选择' : '选择图片'}
                </Text>
              </Pressable>
            </View>
          </View>
        </ScrollView>

        {/* 操作（固定在底部，不随字段滚动） */}
        <View style={styles.formActions}>
          <Button
            label="取消"
            variant="secondary"
            onPress={() => setFormVisible(false)}
            disabled={saving}
            style={styles.formBtn}
          />
          <Button
            label={editingAd ? '保存' : '提交'}
            onPress={handleSave}
            loading={saving}
            style={styles.formBtn}
          />
        </View>
      </FormModal>

      {/* 图片预览 */}
      <Modal
        visible={previewUrl !== null}
        transparent
        animationType="fade"
        onRequestClose={() => setPreviewUrl(null)}
      >
        <Pressable
          style={[styles.previewOverlay, { backgroundColor: c.overlay }]}
          onPress={() => setPreviewUrl(null)}
        >
          <View style={styles.previewCloseWrap}>
            <Pressable
              onPress={() => setPreviewUrl(null)}
              style={[styles.previewClose, { backgroundColor: c.surface }]}
              hitSlop={10}
            >
              <X size={18} color={c.text} />
            </Pressable>
          </View>
          {previewUrl ? (
            <Image
              source={{ uri: previewUrl }}
              style={styles.previewImage}
              resizeMode="contain"
            />
          ) : null}
        </Pressable>
      </Modal>

      {/* 付款弹窗 */}
      <Modal
        visible={payAd !== null}
        transparent
        animationType="fade"
        onRequestClose={handleClosePayment}
      >
        <Pressable
          style={[styles.payOverlay, { backgroundColor: c.overlay }]}
          onPress={handleClosePayment}
        >
          <Pressable
            style={[styles.paySheet, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            <View style={styles.payHeader}>
              <Text style={[styles.payTitle, { color: c.text }]}>广告付款</Text>
              <Pressable onPress={handleClosePayment} hitSlop={8}>
                <X size={20} color={c.textMuted} />
              </Pressable>
            </View>

            {payStep === 'confirm' && payAd ? (
              <View style={styles.payBody}>
                <View
                  style={[styles.paySummary, { backgroundColor: c.surfaceAlt }]}
                >
                  <View style={styles.payRow}>
                    <Text style={[styles.payKey, { color: c.textSecondary }]}>广告标题</Text>
                    <Text
                      style={[styles.payVal, { color: c.text }]}
                      numberOfLines={1}
                    >
                      {payAd.title}
                    </Text>
                  </View>
                  <View style={styles.payRow}>
                    <Text style={[styles.payKey, { color: c.textSecondary }]}>广告类型</Text>
                    <Text style={[styles.payVal, { color: c.text }]}>
                      {payAd.ad_type === 'carousel' ? '轮播图' : '文字广告'}
                    </Text>
                  </View>
                  <View style={styles.payRow}>
                    <Text style={[styles.payKey, { color: c.textSecondary }]}>购买月数</Text>
                    <Text style={[styles.payVal, { color: c.text }]}>
                      {payAd.months ?? '-'} 个月
                    </Text>
                  </View>
                  <View style={styles.payRow}>
                    <Text style={[styles.payKey, { color: c.textSecondary }]}>到期日期</Text>
                    <Text style={[styles.payVal, { color: c.text }]}>
                      {payAd.expire_date || '-'}
                    </Text>
                  </View>
                  <View
                    style={[styles.payRow, styles.payAmountRow, { borderColor: c.border }]}
                  >
                    <Text style={[styles.payKey, { color: c.textSecondary, fontWeight: '600' }]}>
                      应付金额
                    </Text>
                    <Text style={[styles.payAmount, { color: c.warning }]}>
                      ¥{payAd.total_amount || '0'}
                    </Text>
                  </View>
                </View>
                <Button
                  label={payLoading ? '生成二维码中...' : '确认付款'}
                  onPress={handleSubmitPayment}
                  loading={payLoading}
                  style={styles.payConfirmBtn}
                />
              </View>
            ) : null}

            {payStep === 'qrcode' ? (
              <View style={styles.payBodyCenter}>
                <Text style={[styles.payHint, { color: c.textSecondary }]}>
                  请使用支付宝扫描下方二维码完成支付
                </Text>
                <View style={styles.qrBox}>
                  <QRCode value={payQr} size={200} color="#0F172A" backgroundColor="#FFFFFF" />
                </View>
                <Text style={[styles.payAmountBig, { color: c.warning }]}>
                  ¥{payAd?.total_amount || '0'}
                </Text>
                <Text style={[styles.payOrderNo, { color: c.textMuted }]}>
                  订单号: {payOrderNo}
                </Text>
                <View style={styles.payWaiting}>
                  <ActivityIndicator color={c.primary} size="small" />
                  <Text style={[styles.payWaitingText, { color: c.primary }]}>等待支付中...</Text>
                </View>
              </View>
            ) : null}

            {payStep === 'success' ? (
              <View style={styles.payBodyCenter}>
                <CheckCircle size={56} color={c.success} />
                <Text style={[styles.payResultTitle, { color: c.success }]}>付款成功</Text>
                <Text style={[styles.payResultSub, { color: c.textSecondary }]}>
                  广告已自动审核通过
                </Text>
              </View>
            ) : null}

            {payStep === 'error' ? (
              <View style={styles.payBodyCenter}>
                <AlertCircle size={56} color={c.error} />
                <Text style={[styles.payResultTitle, { color: c.error }]}>付款失败</Text>
                <Text style={[styles.payResultSub, { color: c.textSecondary }]}>{payMsg}</Text>
                <Button label="重试" variant="secondary" onPress={resetPayment} style={styles.retryBtn} />
              </View>
            ) : null}
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
    paddingBottom: spacing.sm,
  },
  headerTitle: { flex: 1, marginRight: spacing.sm },
  headerActions: { flexDirection: 'row', gap: spacing.sm },
  headerBtn: { minHeight: 40, paddingHorizontal: spacing.lg },
  title: { ...typography.title },
  list: { padding: spacing.lg, gap: spacing.md },
  card: { gap: spacing.sm, padding: spacing.md },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  typeBadge: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  typeText: { fontSize: 11, fontWeight: '600' },
  adTitle: { ...typography.body, fontWeight: '600', flex: 1 },
  metaRow: { flexDirection: 'row', gap: spacing.sm },
  thumb: {
    width: 56,
    height: 56,
    borderRadius: radius.sm,
  },
  metaCol: { flex: 1, gap: spacing.xs },
  adContent: { ...typography.caption },
  metaLine: { flexDirection: 'row', gap: spacing.md, flexWrap: 'wrap' },
  metaText: { ...typography.small },
  cardActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xs },
  actionBtn: { flex: 1, minHeight: 38, paddingHorizontal: spacing.sm },
  empty: { alignItems: 'center', paddingVertical: 32 },
  emptyText: { ...typography.body },
  // 表单
  field: { gap: spacing.xs },
  fieldRow: { flexDirection: 'row', gap: spacing.md },
  fieldCol: { flex: 1, gap: spacing.xs },
  label: { ...typography.caption },
  typeSelector: { flexDirection: 'row', gap: spacing.sm },
  typeOption: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  typeOptionText: { ...typography.caption },
  textArea: {
    ...typography.body,
    minHeight: 90,
    textAlignVertical: 'top',
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
  },
  readonlyField: {
    minHeight: 50,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
    justifyContent: 'center',
  },
  readonlyText: { ...typography.body },
  amountBox: {
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    flexWrap: 'wrap',
  },
  amountLabel: { ...typography.body, fontWeight: '700' },
  amountSub: { ...typography.small },
  imageRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  imageBox: { position: 'relative' },
  imagePreview: {
    width: 72,
    height: 72,
    borderRadius: radius.md,
  },
  removeBtn: {
    position: 'absolute',
    top: -6,
    right: -6,
    width: 20,
    height: 20,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  uploadBox: {
    width: 72,
    height: 72,
    borderRadius: radius.md,
    borderWidth: 1,
    borderStyle: 'dashed',
    alignItems: 'center',
    justifyContent: 'center',
  },
  changeBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  changeText: { ...typography.caption, fontWeight: '600' },
  formScroll: { maxHeight: 420 },
  formFields: { gap: spacing.md },
  formActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm },
  formBtn: { flex: 1 },
  // 图片预览
  previewOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.lg,
  },
  previewCloseWrap: { alignSelf: 'flex-end', marginBottom: spacing.sm },
  previewClose: {
    width: 36,
    height: 36,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  previewImage: {
    width: '100%',
    height: '80%',
    borderRadius: radius.md,
  },
  // 付款
  payOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.lg,
  },
  paySheet: {
    width: '100%',
    maxWidth: 360,
    borderRadius: radius.xl,
    padding: spacing.lg,
    gap: spacing.md,
  },
  payHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  payTitle: { ...typography.heading },
  payBody: { gap: spacing.md },
  payBodyCenter: { alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.sm },
  paySummary: { padding: spacing.md, borderRadius: radius.md, gap: spacing.xs },
  payRow: { flexDirection: 'row', justifyContent: 'space-between', gap: spacing.sm },
  payKey: { ...typography.small },
  payVal: { ...typography.small, fontWeight: '500', flex: 1, textAlign: 'right' },
  payAmountRow: { paddingTop: spacing.sm, marginTop: spacing.xs, borderTopWidth: 1 },
  payAmount: { fontSize: 20, fontWeight: '700' },
  payConfirmBtn: { minHeight: 44 },
  payHint: { ...typography.caption, textAlign: 'center' },
  qrBox: {
    padding: spacing.md,
    backgroundColor: '#FFFFFF',
    borderRadius: radius.md,
  },
  payAmountBig: { fontSize: 22, fontWeight: '700' },
  payOrderNo: { ...typography.micro },
  payWaiting: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  payWaitingText: { ...typography.caption },
  payResultTitle: { ...typography.heading, marginTop: spacing.xs },
  payResultSub: { ...typography.caption, textAlign: 'center' },
  retryBtn: { marginTop: spacing.xs, minWidth: 120, minHeight: 40 },
});
