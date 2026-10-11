import { useState, useEffect, useCallback, useRef } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Alert,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { ScanLine } from 'lucide-react-native';
import { Card, Button, Loading, EmptyState } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  createSharedSession,
  listSharedSessions,
  getSharedSessionStatus,
  deleteSharedSession,
  type SharedScanSession,
  type SharedScanWorkerInfo,
} from '@/api/wrappers/shared-scan';

/** 兼职扫码状态 → 中文标签 + 语义色（对齐 web SharedScanManager 的徽章） */
function workerStatusMeta(
  status: string,
  c: { info: string; warning: string; success: string; error: string; textMuted: string },
): { label: string; color: string } {
  switch (status) {
    case 'qrcode_ready':
      return { label: '等待扫码', color: c.info };
    case 'scanning':
      return { label: '扫码中', color: c.warning };
    case 'verification_required':
      return { label: '需人脸验证', color: c.warning };
    case 'success':
      return { label: '登录成功', color: c.success };
    case 'failed':
      return { label: '登录失败', color: c.error };
    default:
      return { label: status || '未知', color: c.textMuted };
  }
}

/** ISO/字符串时间 → 简洁可读形式，失败则原样返回 */
function formatTime(raw: string): string {
  if (!raw) return '';
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** Unix 秒时间戳 → HH:mm */
function formatUnix(ts: number): string {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  if (Number.isNaN(d.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** 轮询间隔（毫秒），与 web 端一致 */
const POLL_INTERVAL = 3000;

export default function SharedScanScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [sessions, setSessions] = useState<SharedScanSession[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [creating, setCreating] = useState(false);

  // 展开查看兼职状态的会话
  const [activeId, setActiveId] = useState<string | null>(null);
  const [workers, setWorkers] = useState<SharedScanWorkerInfo[]>([]);
  const [workersLoading, setWorkersLoading] = useState(false);
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  const fetchWorkers = useCallback(async (sessionId: string, showLoading = false) => {
    if (showLoading) setWorkersLoading(true);
    try {
      const status = await getSharedSessionStatus(sessionId);
      setWorkers(status.part_time_workers);
    } catch {
      // 轮询失败静默，不打断刷新
    } finally {
      if (showLoading) setWorkersLoading(false);
    }
  }, []);

  const load = useCallback(async () => {
    try {
      setRefreshing(true);
      setSessions(await listSharedSessions());
    } catch (e) {
      Alert.alert('加载失败', (e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  /** 展开某会话的兼职状态面板，并开始轮询 */
  const openWorkers = useCallback(
    (sessionId: string) => {
      stopPolling();
      setActiveId(sessionId);
      setWorkers([]);
      fetchWorkers(sessionId, true);
      pollTimer.current = setInterval(() => fetchWorkers(sessionId), POLL_INTERVAL);
    },
    [stopPolling, fetchWorkers],
  );

  const closeWorkers = useCallback(() => {
    stopPolling();
    setActiveId(null);
    setWorkers([]);
  }, [stopPolling]);

  // 卸载时清理轮询
  useEffect(() => stopPolling, [stopPolling]);

  const toggleWorkers = useCallback(
    (sessionId: string) => {
      if (activeId === sessionId) closeWorkers();
      else openWorkers(sessionId);
    },
    [activeId, closeWorkers, openWorkers],
  );

  async function handleCreate() {
    setCreating(true);
    try {
      const created = await createSharedSession();
      await load();
      if (created.session_id) openWorkers(created.session_id);
      Alert.alert('创建成功', '会话已创建，复制链接发给兼职即可扫码登录', [
        { text: '复制链接', onPress: () => copyLink(created.share_url) },
        { text: '完成', style: 'cancel' },
      ]);
    } catch (e) {
      Alert.alert('创建失败', (e as Error).message);
    } finally {
      setCreating(false);
    }
  }

  async function copyLink(url: string) {
    if (!url) {
      Alert.alert('复制失败', '分享链接为空，请刷新列表后重试');
      return;
    }
    try {
      await Clipboard.setStringAsync(url);
      Alert.alert('已复制', '分享链接已复制到剪贴板，发给兼职即可');
    } catch {
      Alert.alert('复制失败', '请手动复制：' + url);
    }
  }

  function handleDelete(session: SharedScanSession) {
    Alert.alert('确认删除', `删除会话 ${session.session_id.slice(0, 8)}…？该会话下 ${session.worker_count} 条兼职记录将一并删除。`, [
      { text: '取消', style: 'cancel' },
      {
        text: '删除', style: 'destructive', onPress: async () => {
          try {
            await deleteSharedSession(session.session_id);
            if (activeId === session.session_id) closeWorkers();
            await load();
          } catch (e) { Alert.alert('删除失败', (e as Error).message); }
        },
      },
    ]);
  }

  if (loading) {
    return (<SafeAreaView style={[styles.container, { backgroundColor: c.background }]}><Loading label="加载共享会话..." /></SafeAreaView>);
  }

  const stats = {
    total: workers.length,
    waiting: workers.filter((w) => w.status === 'qrcode_ready').length,
    scanning: workers.filter((w) => w.status === 'scanning').length,
    success: workers.filter((w) => w.status === 'success').length,
  };

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <Text style={[styles.headerHint, { color: c.textMuted }]}>创建会话并把链接发给兼职，各自独立扫码</Text>
        <Button label="创建会话" onPress={handleCreate} loading={creating} style={styles.createBtn} />
      </View>

      <FlatList
        data={sessions}
        keyExtractor={(item) => item.session_id}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
        renderItem={({ item }) => {
          const expanded = activeId === item.session_id;
          return (
            <Card style={styles.card}>
              <Pressable onPress={() => toggleWorkers(item.session_id)} style={styles.cardTop}>
                <View style={styles.sessionInfo}>
                  <Text style={[styles.sessionId, { color: c.text }]} numberOfLines={1}>
                    {item.session_id.slice(0, 8)}…
                  </Text>
                  <View style={[styles.sessionBadge, { backgroundColor: item.status === 'active' ? c.info : c.textMuted }]}>
                    <Text style={styles.badgeText}>{item.status === 'active' ? '进行中' : item.status}</Text>
                  </View>
                </View>
                <Text style={[styles.sessionStats, { color: c.textMuted }]}>
                  {item.worker_count} 名兼职 · {item.success_count} 人成功
                </Text>
                <Text style={[styles.sessionTime, { color: c.textMuted }]}>
                  创建 {formatTime(item.created_at)}{item.expires_at ? ` · ${formatTime(item.expires_at)} 过期` : ''}
                </Text>
              </Pressable>

              <View style={styles.cardActions}>
                <Button label="复制链接" variant="secondary" onPress={() => copyLink(item.share_url)} style={styles.actionBtn} />
                <Button
                  label={expanded ? '收起状态' : '查看兼职'}
                  variant="ghost"
                  onPress={() => toggleWorkers(item.session_id)}
                  style={styles.actionBtn}
                />
                <Button label="删除" variant="danger" onPress={() => handleDelete(item)} style={styles.actionBtn} />
              </View>

              {expanded && (
                <View style={[styles.workersWrap, { borderTopColor: c.border, borderTopWidth: 1 }]}>
                  <View style={styles.workersHeader}>
                    <Text style={[styles.workersStats, { color: c.textSecondary }]}>
                      共 {stats.total} 人 · 等待 {stats.waiting} · 扫码中 {stats.scanning} · 成功 {stats.success}
                    </Text>
                    <Pressable onPress={() => fetchWorkers(item.session_id, true)} hitSlop={8}>
                      <Text style={[styles.refreshText, { color: c.primary }]}>刷新</Text>
                    </Pressable>
                  </View>
                  {workersLoading && workers.length === 0 ? (
                    <Text style={[styles.hint, { color: c.textMuted }]}>加载兼职状态...</Text>
                  ) : workers.length === 0 ? (
                    <Text style={[styles.hint, { color: c.textMuted }]}>
                      暂无兼职加入，将分享链接发给兼职后，每 3 秒自动刷新状态
                    </Text>
                  ) : (
                    workers.map((w) => {
                      const meta = workerStatusMeta(w.status, c);
                      return (
                        <View key={w.sub_session_id} style={[styles.workerRow, { borderBottomColor: c.border }]}>
                          <View style={styles.workerTexts}>
                            <Text style={[styles.workerId, { color: c.text }]} numberOfLines={1}>
                              {w.sub_session_id.slice(0, 8)}…
                            </Text>
                            <Text style={[styles.workerSub, { color: c.textMuted }]} numberOfLines={1}>
                              {w.joined_at ? `加入 ${formatUnix(w.joined_at)}` : ''}
                              {w.account_id ? ` · 账号 ${w.account_id}` : ''}
                            </Text>
                          </View>
                          <View style={[styles.workerBadge, { backgroundColor: meta.color }]}>
                            <Text style={styles.badgeText}>{meta.label}</Text>
                          </View>
                        </View>
                      );
                    })
                  )}
                </View>
              )}
            </Card>
          );
        }}
        ListEmptyComponent={
          <EmptyState
            icon={ScanLine}
            title="暂无共享会话"
            message="创建会话后将链接发给多个兼职，各自独立扫码登录闲鱼账号"
            actionLabel="创建会话"
            onAction={handleCreate}
          />
        }
        contentContainerStyle={styles.list}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: spacing.lg, paddingVertical: spacing.md, gap: spacing.md },
  headerHint: { ...typography.small, flex: 1 },
  createBtn: { minHeight: 40, paddingHorizontal: spacing.md },
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.md, paddingBottom: 80 },
  card: { gap: spacing.sm },
  cardTop: { gap: spacing.xs },
  sessionInfo: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  sessionId: { ...typography.body, fontWeight: '600' },
  sessionBadge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: 4 },
  sessionStats: { ...typography.caption },
  sessionTime: { ...typography.small },
  cardActions: { flexDirection: 'row', gap: spacing.sm },
  actionBtn: { flex: 1, minHeight: 38 },
  workersWrap: { paddingTop: spacing.sm, marginTop: spacing.xs, gap: spacing.sm },
  workersHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  workersStats: { ...typography.small, flex: 1, marginRight: spacing.sm },
  refreshText: { ...typography.small, fontWeight: '600' },
  workerRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  workerTexts: { flex: 1, marginRight: spacing.sm, gap: 2 },
  workerId: { ...typography.caption, fontWeight: '600' },
  workerSub: { ...typography.small },
  workerBadge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.sm },
  badgeText: { ...typography.small, fontWeight: '600', color: '#FFF' },
  hint: { ...typography.small },
});
