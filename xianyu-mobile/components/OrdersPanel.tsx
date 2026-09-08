import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Modal,
  TouchableOpacity,
  ScrollView,
  RefreshControl,
  Alert,
  type ViewStyle,
} from 'react-native';
import { useColorScheme } from 'react-native';
import { Button, Card, DetailRow, Loading } from '@/components/ui';
import { colors, spacing, typography, radius, type ThemeColors } from '@/lib/theme';
import { formatDateTime, getStatusMeta, toneColors } from '@/lib/orderStatus';
import {
  getCustomerOrders,
  getOrderDetail,
  cancelOrder,
  noLogisticsDelivery,
  manualDelivery,
  type CustomerOrder,
  type OrderDetail,
} from '@/api/wrappers/orders';

interface OrdersPanelProps {
  accountId: string;
  buyerId: string;
}

// ============ 订单操作状态判定 ============

/** 处于「待发货」语义、可执行发货/取消操作的状态集合 */
const SHIPPABLE_STATUSES = ['pending_ship', 'pending', 'paid', '待发货'];

/** 可执行取消的状态集合（含待付款） */
const CANCELLABLE_STATUSES = [
  'pending_payment',
  'pending_ship',
  'pending',
  'paid',
  '待付款',
  '待发货',
];

function isShippable(status: string): boolean {
  return SHIPPABLE_STATUSES.includes(status);
}

function isCancellable(status: string): boolean {
  return CANCELLABLE_STATUSES.includes(status);
}

// ============ 组件 ============

type ActionType = 'cancel' | 'noLogistics' | 'manual';

export function OrdersPanel({ accountId, buyerId }: OrdersPanelProps) {
  const scheme = useColorScheme();
  const dark = scheme === 'dark';
  const c: ThemeColors = colors[dark ? 'dark' : 'light'];

  const [orders, setOrders] = useState<CustomerOrder[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [actionOrderNo, setActionOrderNo] = useState<string | null>(null);
  const [actionType, setActionType] = useState<ActionType | null>(null);
  const [detailVisible, setDetailVisible] = useState(false);
  const [detail, setDetail] = useState<OrderDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  const anyActionRunning = actionOrderNo !== null;

  const load = useCallback(
    async (isRefresh: boolean) => {
      if (!accountId || !buyerId) return;
      try {
        if (isRefresh) setRefreshing(true);
        else setLoading(true);
        const list = await getCustomerOrders(accountId, buyerId);
        setOrders(list);
      } catch (e) {
        console.error('加载客户订单失败', e);
        Alert.alert('加载失败', (e as Error).message || '无法获取订单列表');
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [accountId, buyerId],
  );

  useEffect(() => {
    load(false);
  }, [load]);

  const openDetail = useCallback(async (orderNo: string) => {
    setDetailVisible(true);
    setDetail(null);
    setDetailLoading(true);
    try {
      const d = await getOrderDetail(orderNo);
      setDetail(d);
    } catch (e) {
      Alert.alert('获取详情失败', (e as Error).message);
      setDetailVisible(false);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const closeDetail = useCallback(() => setDetailVisible(false), []);

  const runAction = useCallback(
    (order: CustomerOrder, type: ActionType) => {
      if (anyActionRunning) return;
      const fn =
        type === 'cancel'
          ? cancelOrder
          : type === 'noLogistics'
            ? noLogisticsDelivery
            : manualDelivery;
      const verb =
        type === 'cancel'
          ? '取消该订单'
          : type === 'noLogistics'
            ? '执行无物流发货'
            : '执行发卡发货';
      Alert.alert('操作确认', `确定${verb}？`, [
        { text: '取消', style: 'cancel' },
        {
          text: '确定',
          style: 'default',
          onPress: async () => {
            setActionOrderNo(order.order_no);
            setActionType(type);
            try {
              await fn(order.order_no);
              Alert.alert('操作成功', `${verb}已完成`);
              await load(true);
            } catch (e) {
              Alert.alert('操作失败', (e as Error).message);
            } finally {
              setActionOrderNo(null);
              setActionType(null);
            }
          },
        },
      ]);
    },
    [anyActionRunning, load],
  );

  const isThisAction = (orderNo: string, type: ActionType) =>
    actionOrderNo === orderNo && actionType === type;

  const renderItem = ({ item }: { item: CustomerOrder }) => {
    const meta = getStatusMeta(item.status);
    const tc = toneColors(meta.tone, dark);
    const shippable = isShippable(item.status);
    const cancellable = isCancellable(item.status);

    return (
      <Card style={styles.orderCard}>
        {/* 点击商品信息区打开详情（独立 Pressable，避免与按钮嵌套） */}
        <Pressable
          onPress={() => openDetail(item.order_no)}
          disabled={detailLoading}
          style={({ pressed }) => [
            styles.cardTop,
            pressed && { opacity: 0.85 } as ViewStyle,
          ]}
        >
          <Text style={[styles.title, { color: c.text }]} numberOfLines={2}>
            {item.item_title || item.item_id}
          </Text>
          <View style={styles.metaRow}>
            <Text style={[styles.amount, { color: c.error }]}>
              ¥{item.amount || '--'}
            </Text>
            <Text style={[styles.qty, { color: c.textSecondary }]}>
              ×{item.quantity}
            </Text>
            <View
              style={[styles.tag, { backgroundColor: tc.bg, borderRadius: radius.sm }]}
            >
              <Text style={[styles.tagText, { color: tc.fg }]}>{meta.label}</Text>
            </View>
          </View>
          {item.placed_at ? (
            <Text style={[styles.time, { color: c.textMuted }]}>
              {formatDateTime(item.placed_at)}
            </Text>
          ) : null}
          <Text style={[styles.orderNo, { color: c.textMuted }]} numberOfLines={1}>
            订单：{item.order_no}
          </Text>
          {item.delivery_fail_reason ? (
            <Text style={[styles.failReason, { color: c.error }]} numberOfLines={2}>
              {item.delivery_fail_reason}
            </Text>
          ) : null}
        </Pressable>

        {/* 操作区 */}
        <View style={styles.actions}>
          <Button
            label="订单详情"
            variant="secondary"
            onPress={() => openDetail(item.order_no)}
            disabled={detailLoading || anyActionRunning}
            style={styles.actionBtn}
          />
          {cancellable && (
            <Button
              label="取消订单"
              variant="danger"
              onPress={() => runAction(item, 'cancel')}
              loading={isThisAction(item.order_no, 'cancel')}
              disabled={anyActionRunning}
              style={styles.actionBtn}
            />
          )}
        </View>
        {shippable && (
          <Button
            label="无物流发货"
            onPress={() => runAction(item, 'noLogistics')}
            loading={isThisAction(item.order_no, 'noLogistics')}
            disabled={anyActionRunning}
            style={styles.fullBtn}
          />
        )}
        {shippable && (
          <Button
            label={item.card_only_delivered ? '卡券已发送' : '发卡发货'}
            variant="secondary"
            onPress={() => runAction(item, 'manual')}
            loading={isThisAction(item.order_no, 'manual')}
            disabled={anyActionRunning || item.card_only_delivered}
            style={styles.fullBtn}
          />
        )}
      </Card>
    );
  };

  if (loading) {
    return <Loading label="加载订单..." />;
  }

  return (
    <View style={[styles.container, { backgroundColor: c.background }]}>
      <View style={[styles.header, { borderBottomColor: c.border }]}>
        <Text style={[styles.headerTitle, { color: c.text }]}>
          客户订单{orders.length > 0 ? ` (${orders.length})` : ''}
        </Text>
        <Pressable
          onPress={() => load(true)}
          disabled={refreshing}
          style={({ pressed }) => [
            styles.refreshBtn,
            pressed && { opacity: 0.6 } as ViewStyle,
          ]}
        >
          <Text style={[styles.refreshText, { color: c.primary }]}>
            {refreshing ? '刷新中...' : '刷新'}
          </Text>
        </Pressable>
      </View>

      <FlatList
        data={orders}
        keyExtractor={(item) => item.order_no}
        renderItem={renderItem}
        contentContainerStyle={styles.list}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={() => load(true)}
            colors={[c.primary]}
            tintColor={c.primary}
          />
        }
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: c.textMuted }]}>
              暂无订单
            </Text>
          </View>
        }
      />

      {/* 订单详情弹窗 */}
      <Modal
        visible={detailVisible}
        transparent
        animationType="fade"
        onRequestClose={closeDetail}
      >
        <View style={styles.modalOverlay}>
          <View
            style={[
              styles.modalCard,
              { backgroundColor: c.surface, borderColor: c.border },
            ]}
          >
            <View style={[styles.modalHeader, { borderBottomColor: c.border }]}>
              <Text style={[styles.modalTitle, { color: c.text }]}>订单详情</Text>
              <TouchableOpacity onPress={closeDetail} style={styles.closeBtn}>
                <Text style={[styles.closeText, { color: c.textSecondary }]}>
                  ✕
                </Text>
              </TouchableOpacity>
            </View>

            {detailLoading ? (
              <View style={styles.modalLoading}>
                <Loading label="加载详情..." />
              </View>
            ) : detail ? (
              <ScrollView style={styles.modalBody} contentContainerStyle={styles.modalBodyContent}>
                <Text style={[styles.title, { color: c.text }]} numberOfLines={3}>
                  {detail.item_title || detail.order_no}
                </Text>
                <View style={styles.detailGrid}>
                  <DetailRow label="实收金额" value={`¥${detail.amount || '--'}`} c={c} />
                  <DetailRow label="数量" value={String(detail.quantity)} c={c} />
                  <DetailRow
                    label="规格"
                    value={
                      detail.spec_name
                        ? `${detail.spec_name}${detail.spec_value ? '：' + detail.spec_value : ''}`
                        : '无'
                    }
                    c={c}
                  />
                  <DetailRow label="订单状态" value={getStatusMeta(detail.status).label} c={c} />
                  <DetailRow
                    label="收货人"
                    value={detail.receiver_name || '未获取'}
                    c={c}
                  />
                  <DetailRow
                    label="联系电话"
                    value={detail.receiver_phone || '未获取'}
                    c={c}
                  />
                  <DetailRow
                    label="收货地址"
                    value={detail.receiver_address || '未获取'}
                    c={c}
                  />
                </View>
              </ScrollView>
            ) : null}
          </View>
        </View>
      </Modal>
    </View>
  );
}

// ============ 样式 ============

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  headerTitle: { ...typography.heading, fontSize: 15 },
  refreshBtn: { paddingHorizontal: spacing.sm, paddingVertical: spacing.xs },
  refreshText: { ...typography.caption, fontWeight: '600' },
  list: { padding: spacing.md, gap: spacing.md },
  empty: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 60,
  },
  emptyText: { ...typography.body },
  orderCard: { padding: spacing.md, gap: 0 },
  cardTop: { gap: spacing.xs },
  title: { ...typography.body, fontWeight: '600' },
  metaRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  amount: { ...typography.body, fontWeight: '700' },
  qty: { ...typography.caption },
  tag: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    marginLeft: 'auto',
  },
  tagText: { ...typography.small, fontWeight: '600' },
  time: { ...typography.small },
  orderNo: { ...typography.small },
  failReason: { ...typography.small },
  actions: {
    flexDirection: 'row',
    gap: spacing.sm,
    marginTop: spacing.sm,
  },
  actionBtn: { flex: 1, minHeight: 38 },
  fullBtn: { minHeight: 38, marginTop: spacing.xs },
  // Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    alignItems: 'center',
    justifyContent: 'center',
    padding: spacing.lg,
  },
  modalCard: {
    width: '100%',
    maxWidth: 420,
    maxHeight: '80%',
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  modalTitle: { ...typography.heading, fontSize: 16 },
  closeBtn: { padding: spacing.xs },
  closeText: { fontSize: 20 },
  modalLoading: { height: 220 },
  modalBody: {},
  modalBodyContent: { padding: spacing.lg, gap: spacing.sm },
  detailGrid: { gap: spacing.sm },
});
