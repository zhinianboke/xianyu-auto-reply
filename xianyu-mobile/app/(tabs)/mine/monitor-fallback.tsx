import { useState, useCallback, useEffect, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  ScrollView,
  Alert,
  Modal,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { getAccountOptions, type AccountOption } from '@/api/wrappers/accounts';
import { getListingCategories } from '@/api/wrappers/products';
import {
  getFallbackConfigs,
  saveFallbackConfig,
  deleteFallbackConfig,
  isEndpointMissing,
  type ListingCategory,
  type FallbackConfig,
  type FallbackKind,
} from '@/api/wrappers/monitor';

type TabKey = FallbackKind;

const TABS: { key: TabKey; label: string }[] = [
  { key: 'collect', label: '兜底采集账号' },
  { key: 'order', label: '兜底下单账号' },
];

/** 列表行：无分类全局兜底 + 各分类 */
interface FallbackRow {
  categoryId: number | null;
  name: string;
}

/** 账号展示条目：可选列表项 + 已选但已失效的账号（仍可取消勾选） */
interface AccountRow {
  id: string;
  remark?: string;
  enabled?: boolean;
  /** true 表示在可用账号列表中；false 表示配置里残留的失效账号 */
  exists: boolean;
}

export default function MonitorFallbackScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [tab, setTab] = useState<TabKey>('collect');
  const [categories, setCategories] = useState<ListingCategory[]>([]);
  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [collectConfigs, setCollectConfigs] = useState<FallbackConfig[]>([]);
  const [orderConfigs, setOrderConfigs] = useState<FallbackConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // 编辑弹层：目标分类 + 勾选的账号ID（保持配置原有顺序）
  const [editingRow, setEditingRow] = useState<FallbackRow | null>(null);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  const loadAll = useCallback(async () => {
    setRefreshing(true);
    try {
      const [cats, opts, collect, order] = await Promise.all([
        getListingCategories(),
        getAccountOptions().catch(() => [] as AccountOption[]),
        getFallbackConfigs('collect'),
        getFallbackConfigs('order'),
      ]);
      setCategories(cats);
      setAccounts(opts);
      setCollectConfigs(collect);
      setOrderConfigs(order);
    } catch (e) {
      if (isEndpointMissing(e)) {
        Alert.alert('功能不可用', '兜底账号需要后端新版支持，请升级后端服务');
      } else {
        Alert.alert('加载失败', (e as Error).message);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const configs = tab === 'collect' ? collectConfigs : orderConfigs;

  const configMap = useMemo(() => {
    const map = new Map<number | null, FallbackConfig>();
    for (const cfg of configs) {
      if (!cfg.account_ids.length) continue;
      map.set(cfg.category_id ?? null, cfg);
    }
    return map;
  }, [configs]);

  /** 后端附带的有效性信息（旧版后端无 accounts 字段时为空） */
  const validityMap = useMemo(() => {
    const map = new Map<string, { valid: boolean; reason: string | null }>();
    for (const cfg of configs) {
      for (const a of cfg.accounts ?? []) {
        map.set(a.account_id, { valid: a.valid, reason: a.reason });
      }
    }
    return map;
  }, [configs]);

  const rows: FallbackRow[] = useMemo(
    () => [
      { categoryId: null, name: '无分类（全局兜底）' },
      ...categories.map((cat) => ({ categoryId: cat.id, name: cat.name })),
    ],
    [categories],
  );

  /** 打开编辑弹层：勾选项 = 已配置账号（含失效的，便于取消勾选） */
  function openEdit(row: FallbackRow) {
    const cfg = configMap.get(row.categoryId);
    setSelectedIds(cfg ? [...cfg.account_ids] : []);
    setEditingRow(row);
  }

  /** 可选账号行：可用账号 + 已选但不在可用列表中的残留账号 */
  const accountRows: AccountRow[] = useMemo(() => {
    const rows: AccountRow[] = accounts.map((a) => ({
      id: a.id,
      remark: a.remark,
      enabled: a.enabled,
      exists: true,
    }));
    const known = new Set(accounts.map((a) => a.id));
    for (const id of selectedIds) {
      if (!known.has(id)) {
        rows.unshift({ id, exists: false });
      }
    }
    return rows;
  }, [accounts, selectedIds]);

  function toggleSelect(id: string) {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((v) => v !== id) : [...prev, id],
    );
  }

  async function save() {
    if (!editingRow) return;
    setSaving(true);
    try {
      await saveFallbackConfig(tab, editingRow.categoryId, selectedIds);
      setEditingRow(null);
      await loadAll();
    } catch (e) {
      // 账号不存在/不属于当前用户等业务错误直接展示后端 message
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  function confirmClearConfig(row: FallbackRow) {
    Alert.alert('清空配置', `确定删除「${row.name}」的兜底${tab === 'collect' ? '采集' : '下单'}账号配置吗？`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: () => {
          deleteFallbackConfig(tab, row.categoryId)
            .then(() => {
              setEditingRow(null);
              return loadAll();
            })
            .catch((e: unknown) => Alert.alert('删除失败', (e as Error).message));
        },
      },
    ]);
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载兜底账号配置..." />
      </SafeAreaView>
    );
  }

  const editingConfig = editingRow ? configMap.get(editingRow.categoryId) : undefined;

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <Text style={[styles.intro, { color: c.textMuted }]}>
        任务自身无可用账号时，按「任务账号 → 本人本分类 → 本人无分类 → 管理员」链路回退取账号
      </Text>

      {/* 采集/下单 Tab 切换 */}
      <View style={[styles.tabBar, { borderBottomColor: c.border }]}>
        {TABS.map((t) => {
          const active = t.key === tab;
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
                  styles.tabText,
                  { color: active ? c.primary : c.textSecondary },
                  active && { fontWeight: '600' },
                ]}
              >
                {t.label}
              </Text>
            </Pressable>
          );
        })}
      </View>

      <FlatList
        data={rows}
        keyExtractor={(item) => String(item.categoryId ?? 'none')}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={loadAll} />
        }
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: c.textMuted }]}>
              暂无分类，可先在监控分类页创建
            </Text>
          </View>
        }
        renderItem={({ item }) => {
          const cfg = configMap.get(item.categoryId);
          const ids = cfg?.account_ids ?? [];
          return (
            <Card style={styles.card}>
              <Pressable onPress={() => openEdit(item)}>
                <View style={styles.row}>
                  <View style={styles.info}>
                    <Text style={[styles.rowName, { color: c.text }]} numberOfLines={1}>
                      {item.name}
                    </Text>
                    {ids.length > 0 ? (
                      <View style={styles.accountChips}>
                        {ids.map((id) => {
                          const validity = validityMap.get(id);
                          const invalid = validity ? !validity.valid : false;
                          return (
                            <View
                              key={id}
                              style={[
                                styles.accountChip,
                                {
                                  borderColor: invalid ? c.error : c.success,
                                  backgroundColor: invalid
                                    ? 'transparent'
                                    : c.success + '1A',
                                },
                              ]}
                            >
                              <Text
                                style={[
                                  styles.accountChipText,
                                  { color: invalid ? c.error : c.success },
                                ]}
                                numberOfLines={1}
                              >
                                {id}
                              </Text>
                            </View>
                          );
                        })}
                      </View>
                    ) : (
                      <Text style={[styles.meta, { color: c.textMuted }]}>
                        未配置 · 点击选择账号
                      </Text>
                    )}
                  </View>
                  <View style={[styles.countBadge, { backgroundColor: c.primaryLight }]}>
                    <Text style={[styles.countText, { color: c.primary }]}>
                      {ids.length}
                    </Text>
                  </View>
                </View>
              </Pressable>
            </Card>
          );
        }}
      />

      {/* 账号多选 Modal */}
      <Modal
        visible={editingRow != null}
        transparent
        animationType="fade"
        onRequestClose={() => setEditingRow(null)}
      >
        <Pressable style={styles.overlay} onPress={() => setEditingRow(null)}>
          <Pressable
            style={[styles.modal, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]} numberOfLines={1}>
                {editingRow ? `兜底${tab === 'collect' ? '采集' : '下单'} · ${editingRow.name}` : ''}
              </Text>
              <Pressable onPress={() => setEditingRow(null)} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>
            <Text style={[styles.modalHint, { color: c.textMuted }]}>
              已选 {selectedIds.length} 个账号
            </Text>

            <ScrollView style={styles.modalScroll} keyboardShouldPersistTaps="handled">
              {accountRows.length === 0 ? (
                <Text style={[styles.modalEmpty, { color: c.textMuted }]}>
                  暂无可用账号，请先在账号管理中登录
                </Text>
              ) : (
                accountRows.map((a) => {
                  const selected = selectedIds.includes(a.id);
                  return (
                    <Pressable
                      key={a.id}
                      onPress={() => toggleSelect(a.id)}
                      style={[styles.accountRow, { borderBottomColor: c.borderLight }]}
                    >
                      <View
                        style={[
                          styles.checkbox,
                          {
                            borderColor: selected ? c.primary : c.border,
                            backgroundColor: selected ? c.primary : 'transparent',
                          },
                        ]}
                      >
                        {selected && <Text style={styles.checkmark}>✓</Text>}
                      </View>
                      <View style={styles.accountInfo}>
                        <Text style={[styles.accountId, { color: c.text }]} numberOfLines={1}>
                          {a.remark ? `${a.remark}（${a.id}）` : a.id}
                        </Text>
                        {!a.exists ? (
                          <Text style={[styles.accountState, { color: c.error }]}>
                            已失效（账号不存在或已删除）
                          </Text>
                        ) : a.enabled === false ? (
                          <Text style={[styles.accountState, { color: c.textMuted }]}>
                            已停用
                          </Text>
                        ) : null}
                      </View>
                    </Pressable>
                  );
                })
              )}
            </ScrollView>

            <View style={styles.modalActions}>
              {editingConfig ? (
                <Button
                  label="清空配置"
                  variant="danger"
                  onPress={() => confirmClearConfig(editingRow!)}
                  style={styles.clearBtn}
                />
              ) : null}
              <Button
                label="取消"
                variant="ghost"
                onPress={() => setEditingRow(null)}
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
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.md,
  },
  intro: {
    ...typography.small,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  tabBar: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    marginTop: spacing.xs,
  },
  tabItem: { flex: 1, alignItems: 'center', paddingVertical: spacing.md },
  tabText: { ...typography.body },
  list: { padding: spacing.lg, gap: spacing.md },
  card: { paddingVertical: spacing.md },
  row: { flexDirection: 'row', alignItems: 'center' },
  info: { flex: 1, marginRight: spacing.sm, gap: spacing.xs },
  rowName: { ...typography.body, fontWeight: '600' },
  meta: { ...typography.small },
  accountChips: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  accountChip: {
    paddingHorizontal: spacing.sm,
    paddingVertical: 2,
    borderRadius: radius.full,
    borderWidth: 1,
    maxWidth: '100%',
  },
  accountChipText: { ...typography.micro },
  countBadge: {
    minWidth: 36,
    paddingHorizontal: spacing.sm,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    alignItems: 'center',
  },
  countText: { ...typography.small, fontWeight: '700' },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  // 账号多选 Modal
  overlay: {
    flex: 1,
    justifyContent: 'center',
    padding: spacing.lg,
    backgroundColor: 'rgba(0,0,0,0.5)',
  },
  modal: { borderRadius: radius.lg, padding: spacing.lg, gap: spacing.xs },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  modalTitle: { ...typography.heading, flex: 1, marginRight: spacing.sm },
  closeBtn: { fontSize: 22, paddingHorizontal: spacing.xs },
  modalHint: { ...typography.small },
  modalScroll: { maxHeight: '55%', marginTop: spacing.xs },
  modalEmpty: { ...typography.body, paddingVertical: spacing.lg },
  accountRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  checkbox: {
    width: 22,
    height: 22,
    borderRadius: 6,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkmark: { color: '#FFF', fontSize: 14, fontWeight: '700', lineHeight: 16 },
  accountInfo: { flex: 1, gap: 2 },
  accountId: { ...typography.caption },
  accountState: { ...typography.small },
  modalActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  clearBtn: { flex: 1.2 },
  modalBtn: { flex: 1 },
});
