import { useState, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, Switch, Alert, Modal, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button, Input, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getMessageFilters,
  createMessageFilter,
  deleteMessageFilter,
  toggleMessageFilter,
  type MessageFilter,
  type MessageFilterType,
} from '@/api/wrappers/message-filters';
import { getAccountOptions, type AccountOption } from '@/api/wrappers/accounts';

/** 过滤类型选项：值 + 中文标签 */
const TYPE_OPTIONS: { value: MessageFilterType; label: string }[] = [
  { value: 'skip_reply', label: '跳过回复' },
  { value: 'skip_notify', label: '跳过通知' },
];

function typeLabel(t: string): string {
  return TYPE_OPTIONS.find((o) => o.value === t)?.label ?? t;
}

export default function MessageFiltersScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [filters, setFilters] = useState<MessageFilter[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [addVisible, setAddVisible] = useState(false);
  const [newType, setNewType] = useState<MessageFilterType>('skip_reply');
  const [newValue, setNewValue] = useState('');

  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [selectedAccountId, setSelectedAccountId] = useState<string>('');

  const loadAccounts = useCallback(async () => {
    try {
      const list = await getAccountOptions();
      setAccounts(list);
      const first = list.find((a) => a.enabled) ?? list[0];
      if (first) setSelectedAccountId(first.id);
    } catch (e) {
      Alert.alert('加载账号失败', (e as Error).message);
    }
  }, []);

  const loadFilters = useCallback(async () => {
    try {
      setRefreshing(true);
      const list = await getMessageFilters(selectedAccountId || undefined);
      setFilters(list);
    } catch (e) { console.error(e); }
    finally { setLoading(false); setRefreshing(false); }
  }, [selectedAccountId]);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);
  useEffect(() => { if (selectedAccountId) loadFilters(); else setLoading(false); }, [selectedAccountId, loadFilters]);

  async function handleAdd() {
    if (!newValue.trim()) { Alert.alert('提示', '请输入过滤关键词'); return; }
    if (!selectedAccountId) { Alert.alert('提示', '请先选择账号'); return; }
    try {
      await createMessageFilter(newType, newValue.trim(), selectedAccountId);
      setNewValue(''); setAddVisible(false);
      await loadFilters();
    } catch (e) { Alert.alert('添加失败', (e as Error).message); }
  }

  async function handleToggle(id: number, currentEnabled: boolean) {
    setFilters((prev) => prev.map((f) => (f.id === id ? { ...f, enabled: !currentEnabled } : f)));
    try { await toggleMessageFilter(id); }
    catch (e) {
      setFilters((prev) => prev.map((f) => (f.id === id ? { ...f, enabled: currentEnabled } : f)));
      Alert.alert('操作失败', (e as Error).message);
    }
  }

  function handleDelete(id: number, value: string) {
    Alert.alert('确认删除', `删除过滤规则"${value}"？`, [
      { text: '取消' },
      { text: '删除', onPress: async () => {
        try { await deleteMessageFilter(id); await loadFilters(); }
        catch (e) { Alert.alert('删除失败', (e as Error).message); }
      } },
    ]);
  }

  if (loading) {
    return (<SafeAreaView style={[styles.container, { backgroundColor: c.background }]}><Loading label="加载过滤规则..." /></SafeAreaView>);
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      {accounts.length > 0 && (
        <FlatList
          horizontal
          style={styles.accountScroll}
          data={accounts}
          keyExtractor={(item) => item.id}
          contentContainerStyle={styles.accountList}
          showsHorizontalScrollIndicator={false}
          renderItem={({ item }) => {
            const active = selectedAccountId === item.id;
            return (
              <Pressable
                onPress={() => setSelectedAccountId(item.id)}
                style={[styles.chip, { backgroundColor: active ? c.primary : c.surface, borderColor: active ? c.primary : c.border }]}
              >
                <Text style={[styles.chipText, { color: active ? '#FFF' : c.text }]} numberOfLines={1}>{item.remark || item.id}</Text>
              </Pressable>
            );
          }}
        />
      )}

      <View style={styles.header}>
        <Text style={[styles.title, { color: c.text }]}>共 {filters.length} 条规则</Text>
        <Button label="添加" onPress={() => setAddVisible(true)} variant="secondary" />
      </View>

      <FlatList
        data={filters} keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadFilters} />}
        renderItem={({ item }) => (
          <Card style={styles.card}>
            <View style={styles.cardRow}>
              <View style={styles.cardContent}>
                <View style={styles.typeRow}>
                  <View style={[styles.typeBadge, { backgroundColor: item.filter_type === 'skip_reply' ? c.primary : c.warning }]}>
                    <Text style={styles.typeText}>{typeLabel(item.filter_type)}</Text>
                  </View>
                  <Text style={[styles.value, { color: c.text }]} numberOfLines={1}>{item.keyword}</Text>
                </View>
                {item.account_id && <Text style={[styles.accountId, { color: c.textMuted }]}>账号: {item.account_id}</Text>}
              </View>
              <View style={styles.cardActions}>
                <Switch
                  value={item.enabled}
                  onValueChange={() => handleToggle(item.id, item.enabled)}
                  trackColor={{ false: c.border, true: c.primary }}
                />
                <Button label="删除" variant="danger" onPress={() => handleDelete(item.id, item.keyword)} style={styles.btn} />
              </View>
            </View>
          </Card>
        )}
        ListEmptyComponent={<View style={styles.empty}><Text style={[styles.emptyText, { color: c.textMuted }]}>暂无过滤规则</Text></View>}
        contentContainerStyle={styles.list}
      />

      <Modal visible={addVisible} transparent animationType="fade" onRequestClose={() => setAddVisible(false)}>
        <Pressable style={styles.overlay} onPress={() => setAddVisible(false)}>
          <Pressable style={[styles.modal, { backgroundColor: c.surface }]} onPress={() => {}}>
            <Text style={[styles.modalTitle, { color: c.text }]}>添加过滤规则</Text>
            <Text style={[styles.label, { color: c.textSecondary }]}>过滤类型</Text>
            <View style={styles.typeSelector}>
              {TYPE_OPTIONS.map((t) => (
                <Pressable key={t.value} onPress={() => setNewType(t.value)}
                  style={[styles.typeOption, { backgroundColor: newType === t.value ? c.primary : c.background, borderColor: c.border }]}>
                  <Text style={[styles.typeOptionText, { color: newType === t.value ? '#FFF' : c.text }]}>{t.label}</Text>
                </Pressable>
              ))}
            </View>
            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.sm }]}>过滤关键词</Text>
            <Input value={newValue} onChangeText={setNewValue} placeholder="输入要过滤的关键词" style={styles.input} />
            <View style={styles.modalActions}>
              <Button label="取消" variant="secondary" onPress={() => setAddVisible(false)} style={styles.modalBtn} />
              <Button label="添加" onPress={handleAdd} style={styles.modalBtn} />
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  // 横向账号选择器：显式高度避免撑满/压扁
  accountScroll: { flexGrow: 0, minHeight: 54 },
  accountList: { paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, gap: spacing.sm, alignItems: 'center' },
  chip: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: 999, borderWidth: 1 },
  chipText: { fontSize: 14, maxWidth: 120 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: spacing.lg, paddingVertical: spacing.sm },
  title: { ...typography.body },
  list: { padding: spacing.lg, gap: spacing.md, paddingBottom: 80 },
  card: { gap: spacing.xs },
  cardRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardContent: { flex: 1, marginRight: spacing.md, gap: spacing.xs },
  cardActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  typeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  typeBadge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: 4 },
  typeText: { color: '#FFF', fontSize: 11, fontWeight: '600' },
  value: { ...typography.body, flex: 1 },
  accountId: { ...typography.small },
  btn: { minHeight: 36 },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  overlay: { flex: 1, justifyContent: 'center', padding: spacing.lg, backgroundColor: 'rgba(0,0,0,0.5)' },
  modal: { borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  modalTitle: { ...typography.heading, textAlign: 'center' },
  label: { ...typography.caption },
  typeSelector: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.xs },
  typeOption: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.sm, borderWidth: 1 },
  typeOptionText: { ...typography.caption },
  input: { marginTop: spacing.xs },
  modalActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  modalBtn: { flex: 1 },
});
