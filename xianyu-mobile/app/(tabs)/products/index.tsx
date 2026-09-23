import { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Switch,
  Pressable,
  Alert,
  Modal,
  RefreshControl,
  ScrollView,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, EmptyState, Loading, Button, Input, FormModal, StatCard } from '@/components/ui';
import { ShoppingBag, Ticket, Truck, ClipboardList, Activity, Package, Trash2 } from 'lucide-react-native';
import { useRouter } from 'expo-router';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getListingOverview,
  getMonitoredItems,
  getCards,
  createCard,
  updateCard,
  deleteCard,
  getDeliveryBlockRules,
  updateDeliveryBlockRules,
  type ListingOverview,
  type MonitoredItem,
  type Card as CardType,
  type DeliveryBlockRule,
} from '@/api/wrappers/products';
import { useAccountsStore } from '@/stores/accounts';
import { updateItemPrice } from '@/api/wrappers/item-edit';

const TABS = [
  { key: 'monitor', label: '商品监控' },
  { key: 'cards', label: '卡券管理' },
  { key: 'delivery', label: '发货规则' },
] as const;

type TabKey = (typeof TABS)[number]['key'];
type Palette = typeof colors.light;

/** 根据监控状态文案返回主题色 */
function statusColor(status: string, c: Palette): string {
  if (status.includes('已下单')) return c.success;
  if (status.includes('失败')) return c.error;
  if (status.includes('私信')) return c.primary;
  return c.textMuted;
}

export default function ProductsPage() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const [tab, setTab] = useState<TabKey>('monitor');

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
      {/* 子 Tab 切换条 */}
      <View
        style={[
          styles.tabBar,
          { backgroundColor: c.surface, borderBottomColor: c.border },
        ]}
      >
        {TABS.map((t) => {
          const active = tab === t.key;
          return (
            <Pressable
              key={t.key}
              onPress={() => setTab(t.key)}
              style={[
                styles.tabItem,
                active && { borderBottomColor: c.primary, borderBottomWidth: 2 },
              ]}
            >
              <Text
                style={[
                  styles.tabLabel,
                  { color: active ? c.primary : c.textSecondary },
                ]}
              >
                {t.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      {tab === 'monitor' && <MonitorTab />}
      {tab === 'cards' && <CardsTab />}
      {tab === 'delivery' && <DeliveryTab />}
    </SafeAreaView>
  );
}

// ---------------------------------------------------------------------------
// 1. 商品监控：概览统计 + 监控商品列表
// ---------------------------------------------------------------------------

function MonitorTab() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();
  const [overview, setOverview] = useState<ListingOverview | null>(null);
  const [items, setItems] = useState<MonitoredItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  // 改价 Modal：priceTarget 为当前改价商品，null 表示 Modal 关闭
  const [priceTarget, setPriceTarget] = useState<MonitoredItem | null>(null);
  const [priceText, setPriceText] = useState('');
  const [quantityText, setQuantityText] = useState('');
  const [savingPrice, setSavingPrice] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const [ov, list] = await Promise.all([
        getListingOverview(),
        getMonitoredItems(),
      ]);
      setOverview(ov);
      setItems(list);
    } catch (e) {
      Alert.alert('加载失败', (e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  function openPriceModal(item: MonitoredItem) {
    if (!item.cookie_id) {
      Alert.alert('无法改价', '该商品未关联账号信息，无法改价');
      return;
    }
    setPriceTarget(item);
    setPriceText(item.price);
    setQuantityText('');
  }

  function closePriceModal() {
    setPriceTarget(null);
  }

  async function submitPrice() {
    const target = priceTarget;
    if (!target || !target.cookie_id) return;
    const price = Number(priceText);
    if (!Number.isFinite(price) || price <= 0) {
      Alert.alert('提示', '请输入有效的价格');
      return;
    }
    const quantityRaw = quantityText.trim();
    if (!quantityRaw) {
      Alert.alert('提示', '请输入库存数量');
      return;
    }
    const quantity = Number(quantityRaw);
    if (!Number.isInteger(quantity) || quantity < 0) {
      Alert.alert('提示', '请输入有效的库存数量');
      return;
    }
    setSavingPrice(true);
    try {
      const res = await updateItemPrice(target.cookie_id, target.item_id, {
        price,
        quantity,
      });
      if (!res.success) {
        Alert.alert('改价失败', res.message || '请稍后重试');
        return;
      }
      closePriceModal();
      await load();
      Alert.alert('改价成功', res.message || '价格与库存已更新');
    } catch (e) {
      Alert.alert('改价失败', (e as Error).message);
    } finally {
      setSavingPrice(false);
    }
  }

  if (loading) return <Loading label="加载监控数据..." />;

  return (
    <>
      <FlatList
        data={items}
        keyExtractor={(item) => item.item_id}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={load} />
        }
        ListHeaderComponent={
          <View style={styles.statsRow}>
            <StatCard
              label="任务数"
              value={overview?.total_tasks ?? 0}
              icon={ClipboardList}
              onPress={() => router.push('/(tabs)/mine/listing-monitor')}
            />
            <StatCard
              label="活跃任务"
              value={overview?.active_tasks ?? 0}
              icon={Activity}
              accent={c.success}
              onPress={() => router.push('/(tabs)/mine/listing-monitor')}
            />
            <StatCard
              label="商品数"
              value={overview?.total_items ?? 0}
              icon={Package}
              onPress={() => router.push('/(tabs)/mine/listing-monitor')}
            />
          </View>
        }
        renderItem={({ item }) => (
          <Card style={styles.itemCard}>
            <View style={styles.itemHeader}>
              <Text
                style={[styles.itemTitle, { color: c.text }]}
                numberOfLines={2}
              >
                {item.title || '未命名商品'}
              </Text>
              <Text style={[styles.itemPrice, { color: c.primary }]}>
                ¥{item.price}
              </Text>
            </View>
            <View style={[styles.itemFooter, { borderTopColor: c.border }]}>
              <Text
                style={[styles.itemId, { color: c.textMuted }]}
                numberOfLines={1}
              >
                ID: {item.item_id}
              </Text>
              <Text
                style={[styles.itemStatus, { color: statusColor(item.status, c) }]}
              >
                {item.status}
              </Text>
            </View>
            <View style={styles.itemActions}>
              <Button
                label="改价"
                variant="secondary"
                onPress={() => openPriceModal(item)}
                style={styles.actionBtn}
              />
            </View>
          </Card>
        )}
        ListEmptyComponent={
          <EmptyState
            icon={ShoppingBag}
            title="暂无监控商品"
            message="添加监控后商品状态会显示在这里"
            actionLabel="添加监控商品"
            onAction={() => router.push('/(tabs)/mine/listing-monitor')}
          />
        }
        contentContainerStyle={styles.listContent}
      />

      {/* 改价 Modal */}
      <FormModal
        visible={priceTarget !== null}
        onClose={closePriceModal}
        title="商品改价"
      >
        <Text
          style={[styles.priceItemTitle, { color: c.textMuted }]}
          numberOfLines={1}
        >
          {priceTarget?.title || '未命名商品'}
        </Text>

        <View style={styles.fieldGroup}>
          <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
            价格（元）
          </Text>
          <Input
            value={priceText}
            onChangeText={setPriceText}
            placeholder="请输入新价格"
            keyboardType="number-pad"
            autoFocus
          />
        </View>

        <View style={styles.fieldGroup}>
          <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
            库存
          </Text>
          <Input
            value={quantityText}
            onChangeText={setQuantityText}
            placeholder="请输入库存数量"
            keyboardType="number-pad"
          />
        </View>

        <View style={styles.modalActions}>
          <Button
            label="取消"
            variant="ghost"
            onPress={closePriceModal}
            style={styles.modalBtn}
          />
          <Button
            label="确定"
            onPress={submitPrice}
            loading={savingPrice}
            disabled={savingPrice}
            style={styles.modalBtn}
          />
        </View>
      </FormModal>
    </>
  );
}

// ---------------------------------------------------------------------------
// 2. 卡券管理：列表 + 新增/编辑/删除
// ---------------------------------------------------------------------------

function CardsTab() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const [cards, setCards] = useState<CardType[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  // editing === null 表示新增模式
  const [editing, setEditing] = useState<CardType | null>(null);
  const [content, setContent] = useState('');
  const [remark, setRemark] = useState('');
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
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
    load();
  }, [load]);

  function openCreate() {
    setEditing(null);
    setContent('');
    setRemark('');
    setModalVisible(true);
  }

  function openEdit(card: CardType) {
    setEditing(card);
    setContent(card.content);
    setRemark(card.remark ?? '');
    setModalVisible(true);
  }

  function closeModal() {
    setModalVisible(false);
  }

  async function save() {
    const contentTrim = content.trim();
    if (!contentTrim) {
      Alert.alert('提示', '请输入卡券内容');
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await updateCard(editing.id, contentTrim, remark.trim() || undefined);
      } else {
        await createCard(contentTrim, remark.trim() || undefined);
      }
      closeModal();
      await load();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function confirmDelete(card: CardType) {
    Alert.alert(
      '删除卡券',
      `确定删除「${card.remark || '此卡券'}」吗？此操作不可恢复。`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: () => doDelete(card),
        },
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
    Alert.alert(card.remark || '卡券', undefined, [
      { text: '编辑', onPress: () => openEdit(card) },
      {
        text: '删除',
        style: 'destructive',
        onPress: () => confirmDelete(card),
      },
      { text: '取消', style: 'cancel' },
    ]);
  }

  if (loading) return <Loading label="加载卡券..." />;

  return (
    <>
      <View style={styles.subHeader}>
        <Text style={[styles.subTitle, { color: c.text }]}>
          共 {cards.length} 张
        </Text>
        <Button label="+ 新增卡券" onPress={openCreate} variant="secondary" />
      </View>

      <FlatList
        data={cards}
        keyExtractor={(item) => String(item.id)}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={load} />
        }
        renderItem={({ item }) => (
          <Pressable onLongPress={() => handleLongPress(item)}>
            <Card style={styles.cardItem}>
              <Text
                style={[styles.cardContent, { color: c.text }]}
                numberOfLines={3}
              >
                {item.content || '（空内容）'}
              </Text>
              {item.remark ? (
                <Text
                  style={[styles.cardRemark, { color: c.textMuted }]}
                  numberOfLines={1}
                >
                  备注：{item.remark}
                </Text>
              ) : null}
            </Card>
          </Pressable>
        )}
        ListEmptyComponent={
          <EmptyState
            icon={Ticket}
            title="暂无卡券"
            message="点击右上角「+ 新增卡券」添加"
          />
        }
        contentContainerStyle={styles.listContent}
      />

      {/* 新增/编辑 Modal */}
      <Modal
        visible={modalVisible}
        transparent
        animationType="fade"
        onRequestClose={closeModal}
      >
        <Pressable style={styles.modalOverlay} onPress={closeModal}>
          <Pressable
            style={[styles.modalCard, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>
                {editing ? '编辑卡券' : '新增卡券'}
              </Text>
              <Pressable onPress={closeModal} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>

            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
                内容
              </Text>
              <Input
                value={content}
                onChangeText={setContent}
                placeholder="请输入卡券内容"
                multiline
                numberOfLines={4}
                autoFocus
              />
            </View>

            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
                备注
              </Text>
              <Input
                value={remark}
                onChangeText={setRemark}
                placeholder="可选，备注名称"
                maxLength={50}
              />
            </View>

            <View style={styles.modalActions}>
              <Button
                label="取消"
                variant="ghost"
                onPress={closeModal}
                style={styles.modalBtn}
              />
              <Button
                label="保存"
                onPress={save}
                loading={saving}
                disabled={saving}
                style={styles.modalBtn}
              />
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </>
  );
}

// ---------------------------------------------------------------------------
// 3. 发货规则：选择账号 + 规则启用/禁用
// ---------------------------------------------------------------------------

function DeliveryTab() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const accounts = useAccountsStore((s) => s.options);
  const loadAccountOptions = useAccountsStore((s) => s.load);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [rules, setRules] = useState<DeliveryBlockRule[]>([]);
  const [loading, setLoading] = useState(true);
  const [ruleLoading, setRuleLoading] = useState(false);
  const [updating, setUpdating] = useState<string | null>(null);

  // 加载账号列表
  useEffect(() => {
    (async () => {
      try {
        await loadAccountOptions();
        const list = useAccountsStore.getState().options;
        if (list.length > 0 && list[0].id) setSelectedId(list[0].id);
      } catch (e) {
        Alert.alert('加载账号失败', (e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, [loadAccountOptions]);

  // 加载选中账号的发货规则
  const loadRules = useCallback(async (acctId: string) => {
    setRuleLoading(true);
    try {
      const r = await getDeliveryBlockRules(acctId);
      setRules(r);
    } catch (e) {
      Alert.alert('加载规则失败', (e as Error).message);
      setRules([]);
    } finally {
      setRuleLoading(false);
    }
  }, []);

  useEffect(() => {
    if (selectedId) {
      loadRules(selectedId);
    } else {
      setRules([]);
    }
  }, [selectedId, loadRules]);

  async function toggleRule(rule: DeliveryBlockRule, nextVal: boolean) {
    if (!selectedId) return;
    const prev = rules;
    const next = prev.map((r) =>
      r.id === rule.id ? { ...r, enabled: nextVal } : r,
    );
    setRules(next);
    setUpdating(rule.rule_type);
    try {
      await updateDeliveryBlockRules(selectedId, next);
    } catch (e) {
      setRules(prev);
      Alert.alert('更新失败', (e as Error).message);
    } finally {
      setUpdating(null);
    }
  }

  function confirmDeleteRule(rule: DeliveryBlockRule) {
    Alert.alert(
      '删除发货规则',
      `确定删除「${rule.rule_value || rule.rule_type}」吗？此操作不可恢复。`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: () => deleteRule(rule),
        },
      ],
      { cancelable: true },
    );
  }

  // 删除 = 整体替换：传不含该规则的新数组，后端据此移除
  async function deleteRule(rule: DeliveryBlockRule) {
    if (!selectedId) return;
    const prev = rules;
    const next = prev.filter((r) => r.id !== rule.id);
    setRules(next);
    setUpdating(rule.rule_type);
    try {
      await updateDeliveryBlockRules(selectedId, next);
    } catch (e) {
      setRules(prev);
      Alert.alert('删除失败', (e as Error).message);
    } finally {
      setUpdating(null);
    }
  }

  if (loading) return <Loading label="加载账号..." />;

  return (
    <>
      {/* 账号横向选择 */}
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        style={[styles.acctScroll, { borderBottomColor: c.border }]}
        contentContainerStyle={styles.acctScrollContent}
      >
        {accounts.map((a) => {
          const active = a.id === selectedId;
          return (
            <Pressable
              key={a.id}
              onPress={() => setSelectedId(a.id)}
              style={[
                styles.acctChip,
                {
                  backgroundColor: active ? c.primary : c.surface,
                  borderColor: active ? c.primary : c.border,
                },
              ]}
            >
              <Text
                style={[styles.acctChipText, { color: active ? '#FFF' : c.text }]}
                numberOfLines={1}
              >
                {a.remark || a.id}
              </Text>
            </Pressable>
          );
        })}
        {accounts.length === 0 && (
          <Text style={[styles.emptyText, { color: c.textMuted }]}>
            暂无账号
          </Text>
        )}
      </ScrollView>

      {ruleLoading ? (
        <Loading label="加载规则..." />
      ) : (
        <FlatList
          data={rules}
          keyExtractor={(item) => String(item.id)}
          renderItem={({ item }) => (
            <Card style={styles.ruleCard}>
              <View style={styles.ruleRow}>
                <View style={styles.ruleInfo}>
                  <Text
                    style={[styles.ruleValue, { color: c.text }]}
                    numberOfLines={1}
                  >
                    {item.rule_value}
                  </Text>
                  <Text
                    style={[styles.ruleType, { color: c.textMuted }]}
                    numberOfLines={1}
                  >
                    {item.rule_type}
                  </Text>
                </View>
                <Pressable
                  onPress={() => confirmDeleteRule(item)}
                  disabled={updating === item.rule_type}
                  hitSlop={8}
                  style={styles.ruleDeleteBtn}
                  accessibilityRole="button"
                  accessibilityLabel="删除发货规则"
                >
                  <Trash2 color={c.error} size={18} />
                </Pressable>
                <Switch
                  value={item.enabled}
                  onValueChange={(v) => toggleRule(item, v)}
                  disabled={updating === item.rule_type}
                  trackColor={{ false: c.border, true: c.primary }}
                />
              </View>
            </Card>
          )}
          ListEmptyComponent={
            <EmptyState
              icon={Truck}
              title={selectedId ? '该账号暂无可用发货规则' : '请先选择账号'}
            />
          }
          contentContainerStyle={styles.listContent}
        />
      )}
    </>
  );
}

// ---------------------------------------------------------------------------
// 样式
// ---------------------------------------------------------------------------

const styles = StyleSheet.create({
  container: { flex: 1 },
  // 子 Tab 切换条
  tabBar: {
    flexDirection: 'row',
    borderBottomWidth: 1,
  },
  tabItem: {
    flex: 1,
    paddingVertical: spacing.md,
    alignItems: 'center',
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  tabLabel: { ...typography.body, fontWeight: '600' },
  // 通用列表
  listContent: { padding: spacing.lg, gap: spacing.md },
  empty: { alignItems: 'center', justifyContent: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  // 子页头
  subHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  subTitle: { ...typography.heading },
  // 监控统计
  statsRow: { flexDirection: 'row', gap: spacing.md, marginBottom: spacing.md },
  // 监控商品项
  itemCard: { gap: spacing.sm },
  itemHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    gap: spacing.md,
  },
  itemTitle: { ...typography.body, flex: 1, fontWeight: '500' },
  itemPrice: { ...typography.body, fontWeight: '600' },
  itemFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderTopWidth: 1,
    paddingTop: spacing.sm,
    gap: spacing.sm,
  },
  itemId: { ...typography.small, flex: 1 },
  itemStatus: { ...typography.caption, fontWeight: '600' },
  itemActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
  },
  actionBtn: { minHeight: 36, paddingHorizontal: spacing.lg },
  // 卡券
  cardItem: { gap: spacing.xs },
  cardContent: { ...typography.body },
  cardRemark: { ...typography.small },
  // 账号选择
  // 横向列表必须给显式高度：默认 flexGrow:1 会撑满整屏；仅 flexGrow:0 时安卓初始测量会把文字压扁
  acctScroll: {
    flexGrow: 0,
    minHeight: 54,
    borderBottomWidth: 1,
  },
  acctScrollContent: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    gap: spacing.sm,
    alignItems: 'center',
  },
  acctChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.lg,
    borderWidth: 1,
  },
  acctChipText: { ...typography.caption, fontWeight: '600' },
  // 发货规则
  ruleCard: { padding: spacing.md },
  ruleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.md,
  },
  ruleInfo: { flex: 1 },
  ruleDeleteBtn: {
    padding: spacing.xs,
    borderRadius: radius.sm,
  },
  ruleValue: { ...typography.body, fontWeight: '500' },
  ruleType: { ...typography.small, marginTop: spacing.xs },
  // Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.lg,
  },
  modalCard: {
    width: '100%',
    maxWidth: 340,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.md,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  modalTitle: { ...typography.heading },
  closeBtn: { fontSize: 22, paddingHorizontal: spacing.xs },
  priceItemTitle: { ...typography.small },
  fieldGroup: { gap: spacing.xs },
  fieldLabel: { ...typography.caption },
  modalActions: { flexDirection: 'row', gap: spacing.sm },
  modalBtn: { flex: 1 },
});
