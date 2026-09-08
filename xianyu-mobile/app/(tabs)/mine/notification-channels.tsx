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
import { Bell, Plus } from 'lucide-react-native';
import { Card, Button, Input, Loading, EmptyState } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getNotificationChannels,
  createNotificationChannel,
  updateNotificationChannel,
  deleteNotificationChannel,
  testNotificationChannel,
  CHANNEL_TYPES,
  type NotificationChannel,
} from '@/api/wrappers/notifications';

/** 按渠道类型展示的 config 字段提示 */
const TYPE_FIELD_HINTS: Record<string, { urlLabel: string; urlPlaceholder: string; urlHint: string; tokenHint: string }> = {
  dingtalk: { urlLabel: 'Webhook 地址', urlPlaceholder: 'https://oapi.dingtalk.com/robot/send?access_token=...', urlHint: '钉钉自定义机器人的 Webhook 地址', tokenHint: '加签密钥（SEC 开头，可留空）' },
  feishu: { urlLabel: 'Webhook 地址', urlPlaceholder: 'https://open.feishu.cn/open-apis/bot/v2/hook/...', urlHint: '飞书自定义机器人的 Webhook 地址', tokenHint: '签名校验密钥（可留空）' },
  bark: { urlLabel: '服务器地址', urlPlaceholder: 'https://api.day.app', urlHint: 'Bark 推送服务器地址', tokenHint: 'Bark 设备 Key' },
  email: { urlLabel: 'SMTP 地址', urlPlaceholder: 'smtp.qq.com:465', urlHint: 'SMTP 服务器地址（含端口）', tokenHint: 'SMTP 授权码 / 登录密码' },
  webhook: { urlLabel: '回调地址', urlPlaceholder: 'https://example.com/hook', urlHint: '接收通知的自定义 Webhook 地址', tokenHint: '鉴权 Token（可留空）' },
  wecom: { urlLabel: 'Webhook 地址', urlPlaceholder: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...', urlHint: '企业微信群机器人的 Webhook 地址', tokenHint: '可留空' },
};

const DEFAULT_FIELD_HINTS = { urlLabel: 'Webhook 地址', urlPlaceholder: 'https://...', urlHint: '通知接收地址', tokenHint: '访问令牌 / 密钥（可留空）' };

function typeLabel(type: string): string {
  return CHANNEL_TYPES.find((t) => t.value === type)?.label ?? type;
}

export default function NotificationChannelsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [addVisible, setAddVisible] = useState(false);
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState<string>(CHANNEL_TYPES[0].value);
  const [newWebhookUrl, setNewWebhookUrl] = useState('');
  const [newToken, setNewToken] = useState('');
  const [creating, setCreating] = useState(false);

  const fieldHints = TYPE_FIELD_HINTS[newType] ?? DEFAULT_FIELD_HINTS;

  const loadChannels = useCallback(async () => {
    try {
      setRefreshing(true);
      const list = await getNotificationChannels();
      setChannels(list);
    } catch (e) { Alert.alert('加载失败', (e as Error).message); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { loadChannels(); }, [loadChannels]);

  async function handleToggle(item: NotificationChannel) {
    const next = !item.enabled;
    setChannels((prev) => prev.map((ch) => (ch.id === item.id ? { ...ch, enabled: next } : ch)));
    try { await updateNotificationChannel(item.id, { enabled: next }); }
    catch (e) {
      setChannels((prev) => prev.map((ch) => (ch.id === item.id ? { ...ch, enabled: !next } : ch)));
      Alert.alert('操作失败', (e as Error).message);
    }
  }

  function handleLongPress(item: NotificationChannel) {
    Alert.alert(item.name || '通知渠道', `类型: ${typeLabel(item.type)}`, [
      { text: '发送测试', onPress: () => handleTest(item) },
      { text: '删除', style: 'destructive', onPress: () => handleDelete(item) },
      { text: '取消', style: 'cancel' },
    ]);
  }

  async function handleTest(item: NotificationChannel) {
    try {
      const res = await testNotificationChannel(item.id);
      if (res.success) Alert.alert('测试成功', res.message || '测试消息已发送');
      else Alert.alert('测试失败', res.message || '请检查渠道配置');
    } catch (e) { Alert.alert('测试失败', (e as Error).message); }
  }

  function handleDelete(item: NotificationChannel) {
    Alert.alert('确认删除', `删除通知渠道"${item.name}"？`, [
      { text: '取消' },
      { text: '删除', style: 'destructive', onPress: async () => {
        try { await deleteNotificationChannel(item.id); await loadChannels(); }
        catch (e) { Alert.alert('删除失败', (e as Error).message); }
      } },
    ]);
  }

  async function handleCreate() {
    if (!newName.trim()) { Alert.alert('提示', '请输入渠道名称'); return; }
    setCreating(true);
    try {
      const config: Record<string, unknown> = {};
      if (newWebhookUrl.trim()) config.webhook_url = newWebhookUrl.trim();
      if (newToken.trim()) config.token = newToken.trim();
      await createNotificationChannel(newName.trim(), newType, config);
      setNewName(''); setNewWebhookUrl(''); setNewToken(''); setNewType(CHANNEL_TYPES[0].value);
      setAddVisible(false);
      await loadChannels();
    } catch (e) { Alert.alert('创建失败', (e as Error).message); }
    finally { setCreating(false); }
  }

  if (loading) {
    return (<SafeAreaView style={[styles.container, { backgroundColor: c.background }]}><Loading label="加载通知渠道..." /></SafeAreaView>);
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <View style={styles.headerTitle}>
          <Text style={[styles.hint, { color: c.textMuted }]}>长按渠道可测试或删除</Text>
        </View>
        <Pressable onPress={() => setAddVisible(true)} style={[styles.addBtn, { backgroundColor: c.primary }]} hitSlop={8}>
          <Plus size={20} color="#FFF" />
        </Pressable>
      </View>

      <FlatList
        data={channels} keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadChannels} />}
        renderItem={({ item }) => (
          <Pressable onLongPress={() => handleLongPress(item)} delayLongPress={400}>
            <Card style={styles.card}>
              <View style={styles.cardRow}>
                <View style={styles.cardContent}>
                  <View style={styles.typeRow}>
                    <View style={[styles.typeBadge, { backgroundColor: c.primary }]}>
                      <Text style={styles.typeText}>{typeLabel(item.type)}</Text>
                    </View>
                    <Text style={[styles.name, { color: c.text }]} numberOfLines={1}>{item.name}</Text>
                  </View>
                </View>
                <Switch
                  value={item.enabled}
                  onValueChange={() => handleToggle(item)}
                  trackColor={{ false: c.border, true: c.primary }}
                />
              </View>
            </Card>
          </Pressable>
        )}
        ListEmptyComponent={
          <EmptyState
            icon={Bell}
            title="暂无通知渠道"
            message="添加渠道后即可接收监控提醒"
            actionLabel="添加渠道"
            onAction={() => setAddVisible(true)}
          />
        }
        contentContainerStyle={styles.list}
      />

      <Modal visible={addVisible} transparent animationType="slide" onRequestClose={() => setAddVisible(false)}>
        <Pressable style={styles.sheetOverlay} onPress={() => setAddVisible(false)}>
          <Pressable style={[styles.sheet, { backgroundColor: c.surface }]} onPress={() => {}}>
            <View style={[styles.sheetHandle, { backgroundColor: c.border }]} />
            <Text style={[styles.sheetTitle, { color: c.text }]}>新建通知渠道</Text>
            <Text style={[styles.label, { color: c.textSecondary }]}>名称</Text>
            <Input value={newName} onChangeText={setNewName} placeholder="渠道名称" style={styles.input} />
            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.sm }]}>类型</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.typeSelector} contentContainerStyle={styles.typeSelectorContent}>
              {CHANNEL_TYPES.map((t) => (
                <Pressable key={t.value} onPress={() => setNewType(t.value)}
                  style={[styles.typeOption, { backgroundColor: newType === t.value ? c.primary : c.background, borderColor: newType === t.value ? c.primary : c.border }]}>
                  <Text style={[styles.typeOptionText, { color: newType === t.value ? '#FFF' : c.text }]}>{t.label}</Text>
                </Pressable>
              ))}
            </ScrollView>
            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.sm }]}>{fieldHints.urlLabel}</Text>
            <Text style={[styles.hint, { color: c.textMuted }]}>{fieldHints.urlHint}</Text>
            <Input value={newWebhookUrl} onChangeText={setNewWebhookUrl} placeholder={fieldHints.urlPlaceholder} autoCapitalize="none" style={styles.input} />
            <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.sm }]}>Token</Text>
            <Text style={[styles.hint, { color: c.textMuted }]}>{fieldHints.tokenHint}</Text>
            <Input value={newToken} onChangeText={setNewToken} placeholder="Token / 密钥" autoCapitalize="none" style={styles.input} />
            <View style={styles.sheetActions}>
              <Button label="取消" variant="secondary" onPress={() => setAddVisible(false)} style={styles.sheetBtn} />
              <Button label="创建" onPress={handleCreate} loading={creating} style={styles.sheetBtn} />
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
  headerTitle: { flex: 1, marginRight: spacing.md, gap: 2 },
  hint: { ...typography.small },
  addBtn: { width: 32, height: 32, borderRadius: radius.full, alignItems: 'center', justifyContent: 'center' },
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.md },
  card: { gap: spacing.xs },
  cardRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardContent: { flex: 1, marginRight: spacing.md, gap: spacing.xs },
  typeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  typeBadge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: 4 },
  typeText: { color: '#FFF', fontSize: 11, fontWeight: '600' },
  name: { ...typography.body, flex: 1 },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  sheetOverlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.4)' },
  sheet: { borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg, gap: spacing.xs },
  sheetHandle: { width: 36, height: 4, borderRadius: 2, alignSelf: 'center', marginBottom: spacing.sm },
  sheetTitle: { ...typography.heading, textAlign: 'center', marginBottom: spacing.sm },
  label: { ...typography.caption },
  typeSelector: { flexGrow: 0 },
  typeSelectorContent: { gap: spacing.sm, paddingVertical: spacing.xs },
  typeOption: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.sm, borderWidth: 1 },
  typeOptionText: { ...typography.caption },
  input: { marginTop: spacing.xs },
  sheetActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  sheetBtn: { flex: 1 },
});
