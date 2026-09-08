import { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  RefreshControl,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Loading } from '@/components/ui';
import { colors, spacing, typography } from '@/lib/theme';
import {
  getNotifications,
  markNotificationRead,
  type Notification,
} from '@/api/wrappers/dashboard';

/** 将 ISO/字符串时间格式化为简洁的可读形式，失败则原样返回 */
function formatTime(raw: string): string {
  if (!raw) return '';
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${y}-${m}-${day} ${hh}:${mm}`;
}

const TYPE_LABELS: Record<string, string> = {
  face_verification: '人脸验证',
  face: '人脸验证',
  system: '系统通知',
  order: '订单',
  message: '消息',
  notification: '通知',
};

function typeLabel(type: string): string {
  return TYPE_LABELS[type] ?? type;
}

export default function NotificationsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const list = await getNotifications();
      setNotifications(list);
    } catch (e) {
      console.error('加载通知失败', e);
      Alert.alert('加载失败', (e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handlePress(item: Notification) {
    if (item.read) return;
    // 乐观更新
    setNotifications((prev) =>
      prev.map((n) => (n.id === item.id ? { ...n, read: true } : n)),
    );
    try {
      await markNotificationRead(item.id);
    } catch (e) {
      // 回滚
      setNotifications((prev) =>
        prev.map((n) => (n.id === item.id ? { ...n, read: false } : n)),
      );
      Alert.alert('操作失败', (e as Error).message);
    }
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载通知..." />
      </SafeAreaView>
    );
  }

  const unreadCount = notifications.filter((n) => !n.read).length;

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        {unreadCount > 0 && (
          <View style={[styles.badge, { backgroundColor: c.primary }]}>
            <Text style={styles.badgeText}>{unreadCount} 未读</Text>
          </View>
        )}
      </View>

      <FlatList
        data={notifications}
        keyExtractor={(item) => String(item.id)}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={load} />
        }
        renderItem={({ item }) => (
          <Pressable onPress={() => handlePress(item)}>
            <Card
              style={[
                styles.card,
                { borderColor: c.border },
                !item.read && { borderLeftWidth: 3, borderLeftColor: c.primary },
              ]}
            >
              <View style={styles.cardHeader}>
                <Text
                  style={[styles.cardTitle, { color: c.text }]}
                  numberOfLines={1}
                >
                  {item.title}
                </Text>
                {!item.read ? (
                  <View style={[styles.unreadDot, { backgroundColor: c.primary }]} />
                ) : (
                  <Text style={[styles.readTag, { color: c.textMuted }]}>
                    已读
                  </Text>
                )}
              </View>
              <Text
                style={[styles.cardContent, { color: c.textSecondary }]}
                numberOfLines={3}
              >
                {item.content || '(无内容)'}
              </Text>
              <View style={styles.cardFooter}>
                <View style={[styles.typeTag, { backgroundColor: c.primaryLight }]}>
                  <Text style={[styles.typeText, { color: c.primary }]}>
                    {typeLabel(item.type)}
                  </Text>
                </View>
                <Text style={[styles.time, { color: c.textMuted }]}>
                  {formatTime(item.created_at)}
                </Text>
              </View>
            </Card>
          </Pressable>
        )}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: c.textMuted }]}>
              暂无通知
            </Text>
          </View>
        }
        contentContainerStyle={styles.list}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  badge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: 4 },
  badgeText: { color: '#FFF', ...typography.small },
  list: { padding: spacing.lg, gap: spacing.md },
  card: { gap: spacing.sm, borderWidth: 1 },
  cardHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  cardTitle: { ...typography.body, fontWeight: '600', flex: 1 },
  unreadDot: { width: 8, height: 8, borderRadius: 4 },
  readTag: { ...typography.small },
  cardContent: { ...typography.caption },
  cardFooter: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginTop: spacing.xs,
  },
  typeTag: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: 4 },
  typeText: { ...typography.small },
  time: { ...typography.small },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
});
