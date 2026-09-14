import { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Switch,
  Alert,
  RefreshControl,
  ScrollView,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Bell, Plus } from 'lucide-react-native';
import { Card, Button, Input, Loading, EmptyState, FormModal } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getNotificationChannels,
  createNotificationChannel,
  updateNotificationChannel,
  deleteNotificationChannel,
  testNotificationChannel,
  type NotificationChannel,
} from '@/api/wrappers/notifications';

// ---------------------------------------------------------------------------
// 渠道类型 × 动态配置字段
// 字段 key 与后端 common/utils/notification_utils.py 的发送函数一一对应：
//   dingtalk/feishu: webhook_url + secret（加签）
//   email: smtp_server / smtp_port / email_user / email_password / recipient_email
//   telegram: bot_token + chat_id；pushplus: token(+topic/template)
//   bark: server_url + device_key；webhook/wecom: webhook_url
// ---------------------------------------------------------------------------
interface FieldDef {
  key: string;
  label: string;
  hint?: string;
  placeholder?: string;
  /** 可留空 */
  optional?: boolean;
  /** 数字输入（保存时转 Number） */
  numeric?: boolean;
  /** 密码框 */
  secure?: boolean;
  /** 新建时的默认值 */
  defaultValue?: string;
}

interface ChannelTypeDef {
  value: string;
  label: string;
  fields: FieldDef[];
}

const CHANNEL_TYPE_DEFS: ChannelTypeDef[] = [
  {
    value: 'webhook',
    label: 'Webhook',
    fields: [
      { key: 'webhook_url', label: '回调地址', placeholder: 'https://example.com/hook', hint: '接收通知消息的自定义 HTTP 地址' },
    ],
  },
  {
    value: 'dingtalk',
    label: '钉钉',
    fields: [
      { key: 'webhook_url', label: 'Webhook 地址', placeholder: 'https://oapi.dingtalk.com/robot/send?access_token=...', hint: '钉钉自定义机器人的 Webhook 地址' },
      { key: 'secret', label: '加签密钥', hint: 'SEC 开头的签名密钥，未开启加签可留空', optional: true },
    ],
  },
  {
    value: 'feishu',
    label: '飞书',
    fields: [
      { key: 'webhook_url', label: 'Webhook 地址', placeholder: 'https://open.feishu.cn/open-apis/bot/v2/hook/...', hint: '飞书自定义机器人的 Webhook 地址' },
      { key: 'secret', label: '签名校验密钥', hint: '开启签名校验时填写，可留空', optional: true },
    ],
  },
  {
    value: 'email',
    label: '邮件',
    fields: [
      { key: 'smtp_server', label: 'SMTP 服务器', placeholder: 'smtp.qq.com', hint: '邮箱服务商的 SMTP 地址' },
      { key: 'smtp_port', label: 'SMTP 端口', placeholder: '587', numeric: true, defaultValue: '587', hint: '465 为 SSL，587 为 STARTTLS' },
      { key: 'email_user', label: '发件邮箱账号', placeholder: 'you@example.com' },
      { key: 'email_password', label: 'SMTP 授权码 / 密码', secure: true, hint: 'QQ 邮箱等需填写授权码' },
      { key: 'recipient_email', label: '收件邮箱', placeholder: 'receiver@example.com' },
    ],
  },
  {
    value: 'telegram',
    label: 'Telegram',
    fields: [
      { key: 'bot_token', label: 'Bot Token', placeholder: '123456:ABC-xxx', hint: '@BotFather 创建机器人后获得的 Token' },
      { key: 'chat_id', label: 'Chat ID', placeholder: '聊天 / 频道 ID' },
    ],
  },
  {
    value: 'pushplus',
    label: 'PushPlus',
    fields: [
      { key: 'token', label: 'Token', placeholder: 'PushPlus 官网获取的推送 Token', hint: 'pushplus.plus 用户中心获取' },
      { key: 'topic', label: '群组编码', hint: '一对多推送时填写，普通推送留空', optional: true },
      { key: 'template', label: '模板', placeholder: 'txt', defaultValue: 'txt', hint: 'html / txt / json 等，默认 txt', optional: true },
    ],
  },
  {
    value: 'bark',
    label: 'Bark',
    fields: [
      { key: 'server_url', label: '服务器地址', placeholder: 'https://api.day.app', defaultValue: 'https://api.day.app', hint: 'Bark 推送服务器，默认官方地址', optional: true },
      { key: 'device_key', label: '设备 Key', placeholder: 'Bark App 中的设备密钥' },
    ],
  },
  {
    value: 'wecom',
    label: '企业微信',
    fields: [
      { key: 'webhook_url', label: 'Webhook 地址', placeholder: 'https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...', hint: '企业微信群机器人的 Webhook 地址' },
    ],
  },
];

function typeDefOf(type: string): ChannelTypeDef {
  return CHANNEL_TYPE_DEFS.find((t) => t.value === type) ?? CHANNEL_TYPE_DEFS[0];
}

function typeLabel(type: string): string {
  return CHANNEL_TYPE_DEFS.find((t) => t.value === type)?.label ?? type;
}

/** 按类型生成表单初始 config（编辑时优先回填已有值） */
function initialConfig(type: string, existing?: Record<string, unknown>): Record<string, string> {
  const cfg: Record<string, string> = {};
  for (const f of typeDefOf(type).fields) {
    const prev = existing?.[f.key];
    cfg[f.key] = prev != null && String(prev) !== '' ? String(prev) : (f.defaultValue ?? '');
  }
  return cfg;
}

export default function NotificationChannelsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [channels, setChannels] = useState<NotificationChannel[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);

  // 新建/编辑共用表单
  const [formVisible, setFormVisible] = useState(false);
  const [editing, setEditing] = useState<NotificationChannel | null>(null);
  const [formName, setFormName] = useState('');
  const [formType, setFormType] = useState<string>(CHANNEL_TYPE_DEFS[0].value);
  const [formConfig, setFormConfig] = useState<Record<string, string>>(
    () => initialConfig(CHANNEL_TYPE_DEFS[0].value),
  );
  const [saving, setSaving] = useState(false);

  const activeDef = typeDefOf(formType);

  const loadChannels = useCallback(async () => {
    try {
      setRefreshing(true);
      const list = await getNotificationChannels();
      setChannels(list);
    } catch (e) { Alert.alert('加载失败', (e as Error).message); }
    finally { setLoading(false); setRefreshing(false); }
  }, []);

  useEffect(() => { loadChannels(); }, [loadChannels]);

  function openCreate() {
    setEditing(null);
    setFormName('');
    setFormType(CHANNEL_TYPE_DEFS[0].value);
    setFormConfig(initialConfig(CHANNEL_TYPE_DEFS[0].value));
    setFormVisible(true);
  }

  function openEdit(item: NotificationChannel) {
    setEditing(item);
    setFormName(item.name);
    setFormType(item.type);
    setFormConfig(initialConfig(item.type, item.config));
    setFormVisible(true);
  }

  function switchType(next: string) {
    setFormType(next);
    setFormConfig(initialConfig(next));
  }

  async function handleSave() {
    const name = formName.trim();
    if (!name) { Alert.alert('提示', '请输入渠道名称'); return; }
    const config: Record<string, unknown> = {};
    for (const f of activeDef.fields) {
      const raw = (formConfig[f.key] ?? '').trim();
      if (!raw) {
        if (!f.optional) { Alert.alert('提示', `请填写「${f.label}」`); return; }
        continue;
      }
      config[f.key] = f.numeric ? Number(raw) || 0 : raw;
    }
    setSaving(true);
    try {
      if (editing) {
        await updateNotificationChannel(editing.id, { name, type: formType, config });
      } else {
        await createNotificationChannel(name, formType, config);
      }
      setFormVisible(false);
      setEditing(null);
      await loadChannels();
    } catch (e) { Alert.alert('保存失败', (e as Error).message); }
    finally { setSaving(false); }
  }

  async function handleToggle(item: NotificationChannel) {
    const next = !item.enabled;
    setChannels((prev) => prev.map((ch) => (ch.id === item.id ? { ...ch, enabled: next } : ch)));
    try { await updateNotificationChannel(item.id, { enabled: next }); }
    catch (e) {
      setChannels((prev) => prev.map((ch) => (ch.id === item.id ? { ...ch, enabled: !next } : ch)));
      Alert.alert('操作失败', (e as Error).message);
    }
  }

  async function handleTest(item: NotificationChannel) {
    setTestingId(item.id);
    try {
      const res = await testNotificationChannel(item.id);
      if (res.success) Alert.alert('测试成功', res.message || '测试消息已发送');
      else Alert.alert('测试失败', res.message || '请检查渠道配置');
    } catch (e) { Alert.alert('测试失败', (e as Error).message); }
    finally { setTestingId(null); }
  }

  function handleDelete(item: NotificationChannel) {
    Alert.alert('确认删除', `删除通知渠道「${item.name}」？此操作不可恢复。`, [
      { text: '取消', style: 'cancel' },
      { text: '删除', style: 'destructive', onPress: async () => {
        try { await deleteNotificationChannel(item.id); await loadChannels(); }
        catch (e) { Alert.alert('删除失败', (e as Error).message); }
      } },
    ]);
  }

  if (loading) {
    return (<SafeAreaView style={[styles.container, { backgroundColor: c.background }]}><Loading label="加载通知渠道..." /></SafeAreaView>);
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <View style={styles.headerTitle}>
          <Text style={[styles.hint, { color: c.textMuted }]}>长按渠道可删除，编辑可修改配置</Text>
        </View>
        <Pressable onPress={openCreate} style={[styles.addBtn, { backgroundColor: c.primary }]} hitSlop={8}>
          <Plus size={20} color="#FFF" />
        </Pressable>
      </View>

      <FlatList
        data={channels} keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadChannels} />}
        renderItem={({ item }) => (
          <Pressable onLongPress={() => handleDelete(item)} delayLongPress={400}>
            <Card style={styles.card}>
              <View style={styles.cardRow}>
                <View style={styles.cardContent}>
                  <View style={styles.typeRow}>
                    <View style={[styles.typeBadge, { backgroundColor: c.primary }]}>
                      <Text style={styles.typeText}>{typeLabel(item.type)}</Text>
                    </View>
                    <Text style={[styles.name, { color: c.text }]} numberOfLines={1}>{item.name}</Text>
                  </View>
                  <Text style={[styles.configSummary, { color: c.textMuted }]} numberOfLines={1}>
                    {summarizeConfig(item)}
                  </Text>
                </View>
                <Switch
                  value={item.enabled}
                  onValueChange={() => handleToggle(item)}
                  trackColor={{ false: c.border, true: c.primary }}
                />
              </View>
              <View style={styles.cardActions}>
                <Button label="编辑" variant="secondary" onPress={() => openEdit(item)} style={styles.actionBtn} />
                <Button
                  label="测试连接"
                  variant="ghost"
                  onPress={() => handleTest(item)}
                  loading={testingId === item.id}
                  style={styles.actionBtn}
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
            onAction={openCreate}
          />
        }
        contentContainerStyle={styles.list}
      />

      <FormModal
        visible={formVisible}
        onClose={() => setFormVisible(false)}
        title={editing ? '编辑通知渠道' : '新建通知渠道'}
      >
        <ScrollView nestedScrollEnabled style={styles.formScroll} contentContainerStyle={styles.formContent}>
          <Text style={[styles.label, { color: c.textSecondary }]}>名称</Text>
          <Input value={formName} onChangeText={setFormName} placeholder="渠道名称，如：钉钉群提醒" style={styles.input} />

          <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>类型</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.typeSelector} contentContainerStyle={styles.typeSelectorContent}>
            {CHANNEL_TYPE_DEFS.map((t) => (
              <Pressable key={t.value} onPress={() => switchType(t.value)}
                style={[styles.typeOption, { backgroundColor: formType === t.value ? c.primary : c.background, borderColor: formType === t.value ? c.primary : c.border }]}>
                <Text style={[styles.typeOptionText, { color: formType === t.value ? '#FFF' : c.text }]}>{t.label}</Text>
              </Pressable>
            ))}
          </ScrollView>

          {activeDef.fields.map((f) => (
            <View key={f.key}>
              <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.sm }]}>
                {f.label}
                {f.optional ? '（可选）' : ''}
              </Text>
              {f.hint ? <Text style={[styles.hint, { color: c.textMuted }]}>{f.hint}</Text> : null}
              <Input
                value={formConfig[f.key] ?? ''}
                onChangeText={(v) => setFormConfig((prev) => ({ ...prev, [f.key]: v }))}
                placeholder={f.placeholder ?? f.label}
                autoCapitalize="none"
                keyboardType={f.numeric ? 'number-pad' : 'default'}
                secureTextEntry={f.secure}
                style={styles.input}
              />
            </View>
          ))}
        </ScrollView>

        <View style={styles.sheetActions}>
          <Button label="取消" variant="secondary" onPress={() => setFormVisible(false)} style={styles.sheetBtn} />
          <Button label={editing ? '保存' : '创建'} onPress={handleSave} loading={saving} style={styles.sheetBtn} />
        </View>
      </FormModal>
    </SafeAreaView>
  );
}

/** 卡片上的一行配置摘要，避免敏感字段直接暴露 */
function summarizeConfig(item: NotificationChannel): string {
  const def = typeDefOf(item.type);
  const parts: string[] = [];
  for (const f of def.fields) {
    const v = item.config?.[f.key];
    if (v == null || String(v) === '') continue;
    const text = String(v);
    if (f.secure) parts.push(`${f.label}: ••••`);
    else if (text.length > 24) parts.push(`${f.label}: ${text.slice(0, 24)}…`);
    else parts.push(`${f.label}: ${text}`);
  }
  return parts.join('　') || '未配置';
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  headerTitle: { flex: 1, marginRight: spacing.md, gap: 2 },
  hint: { ...typography.small },
  addBtn: { width: 32, height: 32, borderRadius: radius.full, alignItems: 'center', justifyContent: 'center' },
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.md, paddingBottom: 80 },
  card: { gap: spacing.sm },
  cardRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  cardContent: { flex: 1, marginRight: spacing.md, gap: spacing.xs },
  typeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  typeBadge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: 4 },
  typeText: { color: '#FFF', fontSize: 11, fontWeight: '600' },
  name: { ...typography.body, flex: 1, fontWeight: '600' },
  configSummary: { ...typography.small },
  cardActions: { flexDirection: 'row', gap: spacing.sm },
  actionBtn: { flex: 1, minHeight: 38 },
  formScroll: { flexGrow: 0 },
  formContent: { gap: spacing.xs, paddingBottom: spacing.sm },
  label: { ...typography.caption },
  typeSelector: { flexGrow: 0 },
  typeSelectorContent: { gap: spacing.sm, paddingVertical: spacing.xs },
  typeOption: { paddingHorizontal: spacing.md, paddingVertical: spacing.sm, borderRadius: radius.sm, borderWidth: 1 },
  typeOptionText: { ...typography.caption },
  input: { marginTop: spacing.xs },
  sheetActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm },
  sheetBtn: { flex: 1 },
});
