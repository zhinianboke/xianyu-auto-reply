import { useState, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, Alert, Modal, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useColorScheme } from 'react-native';
import { Card, Button, Input, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { useAccountsStore } from '@/stores/accounts';
import { getKeywords, saveKeywords, type Keyword } from '@/api/wrappers/keywords';

export default function KeywordsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();

  const accounts = useAccountsStore((s) => s.options);
  const loadAccountOptions = useAccountsStore((s) => s.load);
  const [selectedId, setSelectedId] = useState<string>('');
  const [keywords, setKeywords] = useState<Keyword[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [editingIdx, setEditingIdx] = useState<number | null>(null);
  const [editKeyword, setEditKeyword] = useState('');
  const [editReply, setEditReply] = useState('');
  const [saving, setSaving] = useState(false);
  const [addVisible, setAddVisible] = useState(false);
  const [newKeyword, setNewKeyword] = useState('');
  const [newReply, setNewReply] = useState('');

  const loadAccounts = useCallback(async () => {
    try {
      await loadAccountOptions();
      const list = useAccountsStore.getState().options;
      if (list.length > 0 && !selectedId) setSelectedId(list[0].id);
    } catch (e) { console.error(e); }
  }, [selectedId, loadAccountOptions]);

  const loadKeywords = useCallback(async () => {
    if (!selectedId) return;
    try {
      setRefreshing(true);
      const list = await getKeywords(selectedId);
      setKeywords(list);
    } catch (e) { console.error(e); }
    finally { setLoading(false); setRefreshing(false); }
  }, [selectedId]);

  useEffect(() => { loadAccounts(); }, [loadAccounts]);
  useEffect(() => { if (selectedId) { setLoading(true); loadKeywords(); } }, [selectedId, loadKeywords]);

  function handleAdd() {
    if (!newKeyword.trim()) { Alert.alert('提示', '请输入关键词'); return; }
    const updated = [...keywords, { keyword: newKeyword.trim(), reply: newReply.trim(), item_id: '' }];
    setKeywords(updated);
    setNewKeyword(''); setNewReply(''); setAddVisible(false);
  }

  async function handleSave() {
    if (!selectedId) return;
    setSaving(true);
    try {
      await saveKeywords(selectedId, keywords);
      Alert.alert('成功', '关键词已保存');
    } catch (e) { Alert.alert('保存失败', (e as Error).message); }
    finally { setSaving(false); }
  }

  function startEdit(idx: number) {
    setEditingIdx(idx);
    setEditKeyword(keywords[idx]?.keyword ?? '');
    setEditReply(keywords[idx]?.reply ?? '');
  }

  function saveEdit() {
    if (editingIdx === null) return;
    const updated = [...keywords];
    updated[editingIdx] = { ...updated[editingIdx], keyword: editKeyword, reply: editReply };
    setKeywords(updated);
    setEditingIdx(null);
  }

  function handleDelete(idx: number) {
    Alert.alert('确认删除', `删除关键词"${keywords[idx]?.keyword}"？`, [
      { text: '取消' },
      { text: '删除', onPress: () => setKeywords(keywords.filter((_, i) => i !== idx)) },
    ]);
  }

  if (loading) {
    return (<SafeAreaView style={[styles.container, { backgroundColor: c.background }]}><Loading label="加载关键词..." /></SafeAreaView>);
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <Button label="保存" onPress={handleSave} loading={saving} />
      </View>

      {accounts.length > 0 && (
        <FlatList
          horizontal style={{ flexGrow: 0, height: 40 }} data={accounts} keyExtractor={(item) => item.id}
          renderItem={({ item }) => (
            <Pressable onPress={() => setSelectedId(item.id)}
              style={[styles.chip, { backgroundColor: selectedId === item.id ? c.primary : c.surface, borderColor: c.border }]}>
              <Text style={[styles.chipText, { color: selectedId === item.id ? '#FFF' : c.text }]} numberOfLines={1}>
                {item.remark || item.id}
              </Text>
            </Pressable>
          )}
          contentContainerStyle={styles.chipList} showsHorizontalScrollIndicator={false}
        />
      )}

      <FlatList
        data={keywords} keyExtractor={(_, i) => String(i)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadKeywords} />}
        renderItem={({ item, index }) => (
          <Card style={styles.card}>
            <View style={styles.cardRow}>
              <View style={styles.cardContent}>
                <Text style={[styles.kw, { color: c.primary }]} numberOfLines={1}>{item.keyword}</Text>
                <Text style={[styles.reply, { color: c.textSecondary }]} numberOfLines={2}>{item.reply || '(无回复)'}</Text>
                {item.item_id ? <Text style={[styles.itemId, { color: c.textMuted }]}>商品: {item.item_id}</Text> : null}
              </View>
              <View style={styles.cardActions}>
                <Button label="编辑" variant="secondary" onPress={() => startEdit(index)} style={styles.btn} />
                <Button label="删除" variant="danger" onPress={() => handleDelete(index)} style={styles.btn} />
              </View>
            </View>
          </Card>
        )}
        ListEmptyComponent={<View style={styles.empty}><Text style={[styles.emptyText, { color: c.textMuted }]}>暂无关键词</Text></View>}
        ListFooterComponent={<Button label="添加关键词" variant="secondary" onPress={() => setAddVisible(true)} style={styles.addBtn} />}
        contentContainerStyle={styles.list}
      />

      {/* 添加 Modal */}
      <Modal visible={addVisible} transparent animationType="fade" onRequestClose={() => setAddVisible(false)}>
        <Pressable style={styles.overlay} onPress={() => setAddVisible(false)}>
          <Pressable style={[styles.modal, { backgroundColor: c.surface }]} onPress={() => {}}>
            <Text style={[styles.modalTitle, { color: c.text }]}>添加关键词</Text>
            <Text style={[styles.label, { color: c.textSecondary }]}>关键词</Text>
            <Input value={newKeyword} onChangeText={setNewKeyword} placeholder="买家发送的关键词" style={styles.input} />
            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.sm }]}>回复内容</Text>
            <Input value={newReply} onChangeText={setNewReply} placeholder="自动回复内容" multiline style={styles.input} />
            <View style={styles.modalActions}>
              <Button label="取消" variant="secondary" onPress={() => setAddVisible(false)} style={styles.modalBtn} />
              <Button label="添加" onPress={handleAdd} style={styles.modalBtn} />
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      {/* 编辑 Modal */}
      <Modal visible={editingIdx !== null} transparent animationType="fade" onRequestClose={() => setEditingIdx(null)}>
        <Pressable style={styles.overlay} onPress={() => setEditingIdx(null)}>
          <Pressable style={[styles.modal, { backgroundColor: c.surface }]} onPress={() => {}}>
            <Text style={[styles.modalTitle, { color: c.text }]}>编辑关键词</Text>
            <Text style={[styles.label, { color: c.textSecondary }]}>关键词</Text>
            <Input value={editKeyword} onChangeText={setEditKeyword} style={styles.input} />
            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.sm }]}>回复内容</Text>
            <Input value={editReply} onChangeText={setEditReply} multiline style={styles.input} />
            <View style={styles.modalActions}>
              <Button label="取消" variant="secondary" onPress={() => setEditingIdx(null)} style={styles.modalBtn} />
              <Button label="保存" onPress={saveEdit} style={styles.modalBtn} />
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  chipList: { paddingHorizontal: spacing.sm, gap: spacing.sm },
  chip: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.xl, borderWidth: 1 },
  chipText: { ...typography.caption, maxWidth: 120 },
  list: { padding: spacing.lg, gap: spacing.md },
  card: { gap: spacing.xs },
  cardRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardContent: { flex: 1, marginRight: spacing.md, gap: spacing.xs },
  cardActions: { flexDirection: 'row', gap: spacing.xs },
  btn: { minHeight: 36 },
  kw: { ...typography.body, fontWeight: '600' },
  reply: { ...typography.caption },
  itemId: { ...typography.small },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  addBtn: { marginTop: spacing.md },
  overlay: { flex: 1, justifyContent: 'center', padding: spacing.lg, backgroundColor: 'rgba(0,0,0,0.5)' },
  modal: { borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  modalTitle: { ...typography.heading, textAlign: 'center' },
  label: { ...typography.caption },
  input: { marginTop: spacing.xs },
  modalActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  modalBtn: { flex: 1 },
});
