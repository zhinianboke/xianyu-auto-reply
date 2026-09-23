import { useState, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, Switch, Pressable, Alert, RefreshControl, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Loading, Badge } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { getScheduledTasks, updateScheduledTask, triggerScheduledTask, type ScheduledTask } from '@/api/wrappers/admin';

function formatInterval(seconds: number): string {
  if (seconds >= 3600) return `${(seconds / 3600).toFixed(1)} 小时`;
  if (seconds >= 60) return `${(seconds / 60).toFixed(0)} 分钟`;
  return `${seconds} 秒`;
}

export default function ScheduledTasksScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const [tasks, setTasks] = useState<ScheduledTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editInterval, setEditInterval] = useState('');
  const [updating, setUpdating] = useState<number | null>(null);

  const load = useCallback(async () => {
    try {
      setRefreshing(true);
      const { tasks } = await getScheduledTasks();
      setTasks(tasks);
    } catch (e) { Alert.alert('加载失败', (e as Error).message); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function handleToggle(task: ScheduledTask, next: boolean) {
    setTasks(prev => prev.map(t => t.id === task.id ? { ...t, enabled: next } : t));
    setUpdating(task.id);
    try { await updateScheduledTask(task.id, { enabled: next }); }
    catch (e) {
      setTasks(prev => prev.map(t => t.id === task.id ? { ...t, enabled: task.enabled } : t));
      Alert.alert('操作失败', (e as Error).message);
    } finally { setUpdating(null); }
  }

  async function handleSaveInterval(task: ScheduledTask) {
    const n = Number(editInterval);
    if (!n || n < 1) { Alert.alert('提示', '请输入有效间隔秒数'); return; }
    setUpdating(task.id);
    try {
      await updateScheduledTask(task.id, { interval_seconds: n });
      setTasks(prev => prev.map(t => t.id === task.id ? { ...t, interval_seconds: n } : t));
      setEditingId(null);
    } catch (e) { Alert.alert('保存失败', (e as Error).message); }
    finally { setUpdating(null); }
  }

  async function handleTrigger(task: ScheduledTask) {
    setUpdating(task.id);
    try {
      await triggerScheduledTask(task.id);
      Alert.alert('已触发', `${task.task_name} 已手动触发`);
    } catch (e) { Alert.alert('触发失败', (e as Error).message); }
    finally { setUpdating(null); }
  }

  if (loading) return (<SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left','right','bottom']}><Loading label="加载定时任务..." /></SafeAreaView>);

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left','right','bottom']}>
      <FlatList
        data={tasks}
        keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} colors={[c.primary]} tintColor={c.primary} />}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => (
          <Card style={styles.card}>
            <View style={styles.cardHeader}>
              <View style={{ flex: 1 }}>
                <Text style={[styles.taskName, { color: c.text }]}>{item.task_name}</Text>
                <Text style={[styles.taskCode, { color: c.textMuted }]}>{item.task_code}</Text>
              </View>
              <Switch
                value={item.enabled}
                onValueChange={(v) => handleToggle(item, v)}
                trackColor={{ false: c.border, true: c.primary }}
                thumbColor="#FFFFFF"
                disabled={updating === item.id}
              />
            </View>
            {item.description ? <Text style={[styles.desc, { color: c.textSecondary }]}>{item.description}</Text> : null}
            <View style={styles.row}>
              <Text style={[styles.label, { color: c.textMuted }]}>间隔</Text>
              {editingId === item.id ? (
                <View style={{ flexDirection: 'row', gap: spacing.xs, alignItems: 'center' }}>
                  <TextInput
                    value={editInterval}
                    onChangeText={setEditInterval}
                    keyboardType="number-pad"
                    style={[styles.intervalInput, { color: c.text, borderColor: c.border, backgroundColor: c.surface }]}
                    placeholder={String(item.interval_seconds)}
                    placeholderTextColor={c.textMuted}
                  />
                  <Pressable onPress={() => handleSaveInterval(item)}><Text style={{ color: c.primary, fontWeight: '600' }}>保存</Text></Pressable>
                  <Pressable onPress={() => setEditingId(null)}><Text style={{ color: c.textMuted }}>取消</Text></Pressable>
                </View>
              ) : (
                <Pressable onPress={() => { setEditingId(item.id); setEditInterval(String(item.interval_seconds)); }}>
                  <Text style={[styles.value, { color: c.primary }]}>{formatInterval(item.interval_seconds)}</Text>
                </Pressable>
              )}
            </View>
            <View style={styles.row}>
              <Text style={[styles.label, { color: c.textMuted }]}>状态</Text>
              <Badge label={item.task_running ? '运行中' : '空闲'} variant={item.task_running ? 'success' : 'gray'} />
              {!item.enabled && <Badge label="已禁用" variant="danger" />}
            </View>
            <Pressable
              onPress={() => handleTrigger(item)}
              disabled={updating === item.id || !item.enabled}
              style={({ pressed }) => [styles.triggerBtn, { opacity: pressed ? 0.7 : (item.enabled ? 1 : 0.4) }]}
            >
              <Text style={[styles.triggerText, { color: '#FFF' }]}>手动触发</Text>
            </Pressable>
          </Card>
        )}
        ListEmptyComponent={<View style={styles.empty}><Text style={[{ color: c.textMuted }]}>暂无定时任务</Text></View>}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  list: { padding: spacing.lg, gap: spacing.md, paddingBottom: 80 },
  card: { gap: spacing.sm },
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  taskName: { ...typography.body, fontWeight: '600' },
  taskCode: { ...typography.small },
  desc: { ...typography.caption },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  label: { ...typography.small, minWidth: 40 },
  value: { ...typography.body, fontWeight: '500' },
  intervalInput: { width: 80, borderWidth: 1, borderRadius: radius.sm, paddingHorizontal: spacing.sm, paddingVertical: 4, fontSize: 14 },
  triggerBtn: { backgroundColor: '#3B82F6', paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderRadius: radius.sm, alignItems: 'center', marginTop: spacing.xs },
  triggerText: { ...typography.caption, fontWeight: '600' },
  empty: { alignItems: 'center', paddingVertical: 40 },
});
