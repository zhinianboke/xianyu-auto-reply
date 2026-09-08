import { useState, useEffect, useCallback } from 'react';
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
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Card, Button, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getNotificationChannels,
  getMessageNotifications,
  createMessageNotification,
  updateMessageNotification,
  deleteMessageNotification,
  type MessageNotificationBinding,
} from '@/api/wrappers/notifications';
import type { AccountOption } from '@/api/wrappers/accounts';
import { useAccountsStore } from '@/stores/accounts';

function accountLabel(a: AccountOption): string {
  return a.remark ? `${a.remark} (${a.id})` : a.id;
}

export default function MessageNotificationsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [bindings, setBindings] = useState<MessageNotificationBinding[]>([]);
  const [channels, setChannels] = useState<{ id: number; name: string }[]>([]);
  const accounts = useAccountsStore((s) => s.options);
  const loadAccountOptions = useAccountsStore((s) => s.load);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [addVisible, setAddVisible] = useState(false);
  const [newAccountId, setNewAccountId] = useState('');
  const [newChannelId, setNewChannelId] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);

  // force=true 用于下拉刷新绕过 60s TTL；账号请求与绑定/渠道请求并行
  const loadAll = useCallback(async (force = false) => {
    try {
      setRefreshing(true);
      const accTask = loadAccountOptions(force);
      const [b, ch] = await Promise.all([getMessageNotifications(), getNotificationChannels()]);
      await accTask;
      setBindings(b);
      setChannels(ch.map((item) => ({ id: item.id, name: item.name })));
    } catch (e) { Alert.alert('加载失败', (e as Error).message); }
    finally { setLoading(false); setRefreshing(false); }
  }, [loadAccountOptions]);

  useEffect(() => { loadAll(); }, [loadAll]);

  function channelName(channelId: number): string {
    const found = channels.find((ch) => ch.id === channelId);
    return found?.name ?? `渠道 #${channelId}`;
  }

  async function handleToggle(item: MessageNotificationBinding) {
    const next = !item.enabled;
    setBindings((prev) => prev.map((b) => (b.id === item.id ? { ...b, enabled: next } : b)));
    try { await updateMessageNotification(item.id, next); }
    catch (e) {
      setBindings((prev) => prev.map((b) => (b.id === item.id ? { ...b, enabled: !next } : b)));
      Alert.alert('操作失败', (e as Error).message);
    }
  }

  function handleDelete(item: MessageNotificationBinding) {
    Alert.alert('确认删除', `删除账号 ${item.account_id} 的通知绑定？`, [
      { text: '取消' },
      { text: '删除', style: 'destructive', onPress: async () => {
        try { await deleteMessageNotification(item.id); await loadAll(); }
        catch (e) { Alert.alert('删除失败', (e as Error).message); }
      } },
    ]);
  }

  function openAdd() {
    if (!newAccountId && accounts.length > 0) setNewAccountId(accounts[0].id);
    if (newChannelId == null && channels.length > 0) setNewChannelId(channels[0].id);
    setAddVisible(true);
  }

  async function handleCreate() {
    if (!newAccountId) { Alert.alert('提示', '请选择账号'); return; }
    if (newChannelId == null) { Alert.alert('提示', '请选择通知渠道'); return; }
    setCreating(true);
    try {
      await createMessageNotification(newAccountId, newChannelId);
      setNewAccountId(''); setNewChannelId(null);
      setAddVisible(false);
      await loadAll();
    } catch (e) { Alert.alert('创建失败', (e as Error).message); }
    finally { setCreating(false); }
  }

  if (loading) {
    return (<SafeAreaView style={[styles.container, { backgroundColor: c.background }]}><Loading label="加载通知绑定..." /></SafeAreaView>);
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <Button label="新建绑定" variant="secondary" onPress={openAdd} />
      </View>

      <FlatList
        data={bindings} keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadAll(true)} />}
        renderItem={({ item }) => (
          <Card style={styles.card}>
            <View style={styles.cardRow}>
              <View style={styles.cardContent}>
                <Text style={[styles.accountId, { color: c.text }]} numberOfLines={1}>{item.account_id}</Text>
                <View style={styles.channelRow}>
                  <View style={[styles.channelBadge, { backgroundColor: c.primaryLight }]}>
                    <Text style={[styles.channelBadgeText, { color: c.primary }]} numberOfLines={1}>{item.channel_name || channelName(item.channel_id)}</Text>
                  </View>
                </View>
              </View>
              <View style={styles.cardActions}>
                <Switch
                  value={item.enabled}
                  onValueChange={() => handleToggle(item)}
                  trackColor={{ false: c.border, true: c.primary }}
                />
                <Button label="删除" variant="danger" onPress={() => handleDelete(item)} style={styles.btn} />
              </View>
            </View>
          </Card>
        )}
        ListEmptyComponent={<View style={styles.empty}><Text style={[styles.emptyText, { color: c.textMuted }]}>暂无通知绑定</Text></View>}
        contentContainerStyle={styles.list}
      />

      <Modal visible={addVisible} transparent animationType="slide" onRequestClose={() => setAddVisible(false)}>
        <Pressable style={styles.sheetOverlay} onPress={() => setAddVisible(false)}>
          <Pressable style={[styles.sheet, { backgroundColor: c.surface }]} onPress={() => {}}>
            <View style={[styles.sheetHandle, { backgroundColor: c.border }]} />
            <Text style={[styles.sheetTitle, { color: c.text }]}>新建绑定</Text>
            <Text style={[styles.label, { color: c.textSecondary }]}>账号</Text>
            {accounts.length > 0 ? (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.optionSelector} contentContainerStyle={styles.optionSelectorContent}>
                {accounts.map((a) => (
                  <Pressable key={a.id} onPress={() => setNewAccountId(a.id)}
                    style={[styles.optionChip, { backgroundColor: newAccountId === a.id ? c.primary : c.background, borderColor: newAccountId === a.id ? c.primary : c.border }]}>
                    <Text style={[styles.optionChipText, { color: newAccountId === a.id ? '#FFF' : c.text }]} numberOfLines={1}>{accountLabel(a)}</Text>
                  </Pressable>
                ))}
              </ScrollView>
            ) : (
              <Text style={[styles.emptyOptions, { color: c.textMuted }]}>暂无可用账号</Text>
            )}
            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.sm }]}>通知渠道</Text>
            {channels.length > 0 ? (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.optionSelector} contentContainerStyle={styles.optionSelectorContent}>
                {channels.map((ch) => (
                  <Pressable key={ch.id} onPress={() => setNewChannelId(ch.id)}
                    style={[styles.optionChip, { backgroundColor: newChannelId === ch.id ? c.primary : c.background, borderColor: newChannelId === ch.id ? c.primary : c.border }]}>
                    <Text style={[styles.optionChipText, { color: newChannelId === ch.id ? '#FFF' : c.text }]} numberOfLines={1}>{ch.name}</Text>
                  </Pressable>
                ))}
              </ScrollView>
            ) : (
              <Text style={[styles.emptyOptions, { color: c.textMuted }]}>暂无通知渠道，请先创建渠道</Text>
            )}
            <View style={styles.sheetActions}>
              <Button label="取消" variant="secondary" onPress={() => setAddVisible(false)} style={styles.sheetBtn} />
              <Button label="创建" onPress={handleCreate} loading={creating} disabled={accounts.length === 0 || channels.length === 0} style={styles.sheetBtn} />
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
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.md },
  card: { gap: spacing.xs },
  cardRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardContent: { flex: 1, marginRight: spacing.md, gap: spacing.xs },
  cardActions: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  accountId: { ...typography.body },
  channelRow: { flexDirection: 'row', alignItems: 'center' },
  channelBadge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: 4, alignSelf: 'flex-start', maxWidth: '100%' },
  channelBadgeText: { fontSize: 11, fontWeight: '600' },
  btn: { minHeight: 36 },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  sheetOverlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: { borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg, gap: spacing.xs },
  sheetHandle: { width: 36, height: 4, borderRadius: 2, alignSelf: 'center', marginBottom: spacing.sm },
  sheetTitle: { ...typography.heading, textAlign: 'center', marginBottom: spacing.sm },
  label: { ...typography.caption },
  optionSelector: { flexGrow: 0 },
  optionSelectorContent: { gap: spacing.sm, paddingVertical: spacing.xs },
  optionChip: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.sm, borderWidth: 1, maxWidth: 220 },
  optionChipText: { ...typography.caption },
  emptyOptions: { ...typography.caption, paddingVertical: spacing.sm },
  sheetActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  sheetBtn: { flex: 1 },
});
