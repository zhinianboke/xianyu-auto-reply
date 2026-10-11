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
  KeyboardAvoidingView,
  Platform,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Bell, FileText, Plus, X } from 'lucide-react-native';
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

// ---------------------------------------------------------------------------
// 通知正文模板（后端 common/utils/notification_template.py 渲染）
// 占位符 {{variable}}，留空时使用系统默认模板
// ---------------------------------------------------------------------------
type NotificationTemplates = {
  chat_template: string;
  delivery_template: string;
  account_template: string;
};

/** 模板字段定义，variables 需与后端 TEMPLATE_VARIABLES 保持一致 */
const TEMPLATE_FIELDS: { key: keyof NotificationTemplates; label: string; variables: string[] }[] = [
  {
    key: 'chat_template',
    label: '消息通知',
    variables: ['account', 'account_id', 'account_remark', 'buyer_nick', 'buyer_id', 'message', 'item_id', 'chat_id', 'time'],
  },
  {
    key: 'delivery_template',
    label: '自动发货通知',
    variables: ['account', 'account_id', 'account_remark', 'buyer_nick', 'buyer_id', 'message', 'item_id', 'chat_id', 'time', 'order_id', 'amount', 'quantity', 'result'],
  },
  {
    key: 'account_template',
    label: '账号异常通知',
    variables: ['account', 'account_id', 'account_remark', 'title', 'notification_type', 'detail', 'chat_id', 'verification_url', 'verification_info', 'time'],
  },
];

/** 校验模板占位符：格式错误或含不支持的变量时返回错误文案 */
function validateTemplateDraft(templates: NotificationTemplates): string | null {
  const placeholderPattern = /{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}/g;
  for (const field of TEMPLATE_FIELDS) {
    const template = templates[field.key];
    const placeholders = [...template.matchAll(placeholderPattern)];
    const remaining = template.replace(placeholderPattern, '');
    if (remaining.includes('{{') || remaining.includes('}}')) {
      return `${field.label}模板占位符格式错误，应使用 {{variable}} 格式`;
    }
    const unknown = [...new Set(placeholders.map((match) => match[1]).filter((name) => !field.variables.includes(name)))];
    if (unknown.length > 0) {
      return `${field.label}模板包含不支持的占位符: ${unknown.map((name) => `{{${name}}}`).join(', ')}`;
    }
  }
  return null;
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

  // 通知模板编辑
  const [editingChannel, setEditingChannel] = useState<NotificationChannel | null>(null);
  const [templateDraft, setTemplateDraft] = useState<NotificationTemplates>({
    chat_template: '',
    delivery_template: '',
    account_template: '',
  });
  const [savingTemplates, setSavingTemplates] = useState(false);

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
    // 编辑时保留模板等非表单字段，避免保存配置时把已设模板清空
    if (editing) {
      for (const key of ['chat_template', 'delivery_template', 'account_template'] as const) {
        const prev = editing.config?.[key];
        if (typeof prev === 'string' && prev) config[key] = prev;
      }
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

  /** 打开模板编辑弹窗，回填该渠道已保存的模板 */
  function handleEditTemplates(item: NotificationChannel) {
    setEditingChannel(item);
    setTemplateDraft({
      chat_template: typeof item.config.chat_template === 'string' ? item.config.chat_template : '',
      delivery_template: typeof item.config.delivery_template === 'string' ? item.config.delivery_template : '',
      account_template: typeof item.config.account_template === 'string' ? item.config.account_template : '',
    });
  }

  async function handleSaveTemplates() {
    if (!editingChannel) return;
    const validationError = validateTemplateDraft(templateDraft);
    if (validationError) { Alert.alert('模板格式错误', validationError); return; }
    setSavingTemplates(true);
    const config = { ...editingChannel.config, ...templateDraft };
    try {
      await updateNotificationChannel(editingChannel.id, { config });
      setChannels((prev) => prev.map((ch) => (ch.id === editingChannel.id ? { ...ch, config } : ch)));
      setEditingChannel(null);
      Alert.alert('保存成功', '通知模板已更新');
    } catch (e) { Alert.alert('保存失败', (e as Error).message); }
    finally { setSavingTemplates(false); }
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
                <Pressable
                  onPress={() => handleEditTemplates(item)}
                  style={styles.templateButton}
                  accessibilityRole="button"
                  accessibilityLabel={`编辑${item.name}的通知模板`}
                  hitSlop={8}
                >
                  <FileText size={18} color={c.primary} />
                </Pressable>
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

      {/* 通知模板编辑弹窗（留空使用系统默认模板） */}
      <Modal
        visible={editingChannel != null}
        transparent
        animationType="slide"
        onRequestClose={() => {}}
      >
        <KeyboardAvoidingView
          style={styles.templateOverlay}
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        >
          <View style={[styles.templateSheet, { backgroundColor: c.surface }]}>
            <View style={styles.templateHeader}>
              <Text style={[styles.sheetTitle, { color: c.text }]}>通知模板</Text>
              <Pressable
                onPress={() => setEditingChannel(null)}
                disabled={savingTemplates}
                style={styles.closeButton}
                accessibilityRole="button"
                accessibilityLabel="关闭通知模板编辑"
                hitSlop={8}
              >
                <X size={20} color={c.textSecondary} />
              </Pressable>
            </View>
            <Text style={[styles.templateChannelName, { color: c.textSecondary }]} numberOfLines={1}>
              {editingChannel?.name}
            </Text>
            <ScrollView style={styles.templateScroll} keyboardShouldPersistTaps="handled">
              {TEMPLATE_FIELDS.map((field) => (
                <View key={field.key} style={styles.templateField}>
                  <Text style={[styles.label, { color: c.text }]}>{field.label}</Text>
                  <Text style={[styles.templateVariables, { color: c.textMuted }]}>{field.variables.map((name) => `{{${name}}}`).join(' ')}</Text>
                  <Input
                    value={templateDraft[field.key]}
                    onChangeText={(value) => setTemplateDraft((prev) => ({ ...prev, [field.key]: value }))}
                    placeholder="留空时使用系统默认模板"
                    multiline
                    textAlignVertical="top"
                    style={styles.templateInput}
                    editable={!savingTemplates}
                  />
                </View>
              ))}
            </ScrollView>
            <View style={styles.sheetActions}>
              <Button
                label="关闭"
                variant="secondary"
                onPress={() => setEditingChannel(null)}
                disabled={savingTemplates}
                style={styles.sheetBtn}
              />
              <Button
                label="保存"
                onPress={handleSaveTemplates}
                loading={savingTemplates}
                style={styles.sheetBtn}
              />
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
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
  templateButton: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center', marginRight: spacing.sm },
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
  // 通知模板弹窗
  sheetTitle: { ...typography.heading, textAlign: 'center' },
  templateOverlay: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.4)' },
  templateSheet: { maxHeight: '90%', borderTopLeftRadius: radius.xl, borderTopRightRadius: radius.xl, padding: spacing.lg },
  templateHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center' },
  closeButton: { position: 'absolute', right: 0, width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  templateChannelName: { ...typography.caption, textAlign: 'center', marginBottom: spacing.md },
  templateScroll: { flexShrink: 1 },
  templateField: { gap: spacing.xs, marginBottom: spacing.md },
  templateVariables: { ...typography.small },
  templateInput: { minHeight: 88, paddingTop: spacing.md },
});
