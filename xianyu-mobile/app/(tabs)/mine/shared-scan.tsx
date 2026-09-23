import { useState, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, Alert, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { getApiClient } from '@/api/wrappers/client';

interface ScanSession { session_id: string; status: string; created_at: string; }

export default function SharedScanScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const [sessions, setSessions] = useState<ScanSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    try {
      setRefreshing(true);
      const client = await getApiClient();
      const { data } = (await (client.GET as any)('/api/v1/shared-scan/list')) as {
        data?: ScanSession[]; error?: unknown;
      };
      setSessions(data ?? []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleCreate() {
    try {
      const client = await getApiClient();
      const { data, error } = (await (client.POST as any)('/api/v1/shared-scan/create')) as {
        data?: { session_id: string }; error?: unknown;
      };
      if (error) throw error;
      Alert.alert('成功', `已创建共享扫码会话: ${data?.session_id}`);
      await load();
    } catch (e) { Alert.alert('创建失败', (e as Error).message); }
  }

  async function handleDelete(sessionId: string) {
    Alert.alert('确认删除', `删除会话 ${sessionId}？`, [
      { text: '取消' },
      { text: '删除', onPress: async () => {
        try {
          const client = await getApiClient();
          await (client.DELETE as any)(`/api/v1/shared-scan/${sessionId}`);
          await load();
        } catch (e) { Alert.alert('删除失败', (e as Error).message); }
      } },
    ]);
  }

  if (loading) {
    return (<SafeAreaView style={[styles.container, { backgroundColor: c.background }]}><Loading label="加载..." /></SafeAreaView>);
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <Button label="创建会话" onPress={handleCreate} variant="secondary" />
      </View>
      <FlatList
        data={sessions} keyExtractor={(item) => item.session_id}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
        renderItem={({ item }) => (
          <Card style={styles.card}>
            <Text style={[styles.sessionId, { color: c.text }]} numberOfLines={1}>{item.session_id}</Text>
            <View style={styles.cardRow}>
              <Text style={[styles.status, { color: item.status === 'active' ? c.success : c.textMuted }]}>{item.status}</Text>
              <Text style={[styles.time, { color: c.textMuted }]}>{item.created_at}</Text>
            </View>
            <Button label="删除" variant="danger" onPress={() => handleDelete(item.session_id)} style={styles.btn} />
          </Card>
        )}
        ListEmptyComponent={<View style={styles.empty}><Text style={[styles.emptyText, { color: c.textMuted }]}>暂无共享扫码会话</Text></View>}
        contentContainerStyle={styles.list}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  list: { padding: spacing.lg, gap: spacing.md },
  card: { gap: spacing.sm },
  sessionId: { ...typography.body, fontWeight: '600' },
  cardRow: { flexDirection: 'row', justifyContent: 'space-between' },
  status: { ...typography.caption, fontWeight: '600' },
  time: { ...typography.small },
  btn: { minHeight: 36, marginTop: spacing.xs },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
});
