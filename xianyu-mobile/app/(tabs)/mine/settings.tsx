import { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Switch,
  Pressable,
  Alert,
  ActivityIndicator,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { useRouter } from 'expo-router';
import { Card, Button, Input, Loading, FormModal } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { useConfigStore } from '@/stores/config';
import { useAuthStore } from '@/stores/auth';
import {
  getSystemSettings,
  updateSystemSetting,
  getServicesStatus,
  restartService,
  testEmailSend,
  testPasswordLoginRemote,
  pingHealth,
  serializeHiddenMenuKeys,
  getHiddenMenuKeysFromSettings,
  type ServiceKey,
} from '@/api/wrappers/settings';
import {
  User,
  ChevronRight,
  Shield,
  Mail,
  Globe,
  Server,
  Info,
  Settings as SettingsIcon,
  RefreshCw,
  Save,
  RotateCcw,
  MessageSquare,
  Timer,
  EyeOff,
  CalendarClock,
  Wallet,
} from 'lucide-react-native';

/** 设置项类型 */
type FieldType = 'switch' | 'input' | 'toggle' | 'secret';

interface SettingDef {
  key: string;
  label: string;
  type: FieldType;
  category: SettingCategory;
  placeholder?: string;
  numeric?: boolean;
  options?: { value: string; label: string }[];
  /** toggle 默认值（后端未返回时展示用） */
  defaultValue?: string;
}

type SettingCategory =
  | '基础设置'
  | 'SMTP配置'
  | 'Token获取方式'
  | '密码登录远程配置'
  | '提现配置';

/**
 * 已知的系统设置项定义（按类别分组）。
 *
 * key 与 Web 端 Settings.tsx 保持一致，确保写入同一后端配置项。
 * 注：密码登录方式后端枚举为 protocol/browser，
 *    这里用「Web端/远程」标签映射（browser=Web端、protocol=远程）。
 */
const SETTING_DEFS: SettingDef[] = [
  // 基础设置
  { key: 'allow_registration', label: '允许注册', type: 'switch', category: '基础设置' },
  { key: 'enable_login_captcha', label: '登录验证码', type: 'switch', category: '基础设置' },
  { key: 'show_default_login_info', label: '显示默认登录信息', type: 'switch', category: '基础设置' },
  { key: 'log_retention_days', label: '日志保留天数', type: 'input', category: '基础设置', numeric: true, placeholder: '如 30' },
  { key: 'account.face_verify_timeout_disable', label: '人脸验证超时自动禁用', type: 'switch', category: '基础设置' },
  {
    key: 'password_login.mode',
    label: '密码登录方式',
    type: 'toggle',
    category: '基础设置',
    defaultValue: 'browser',
    options: [
      { value: 'browser', label: 'Web端' },
      { value: 'protocol', label: '远程' },
    ],
  },
  // SMTP 配置
  { key: 'smtp_server', label: '服务器', type: 'input', category: 'SMTP配置', placeholder: '如 smtp.qq.com' },
  { key: 'smtp_port', label: '端口', type: 'input', category: 'SMTP配置', numeric: true, placeholder: '如 465' },
  { key: 'smtp_username', label: '发件邮箱', type: 'input', category: 'SMTP配置', placeholder: '发件邮箱地址' },
  { key: 'smtp_password', label: '密码', type: 'secret', category: 'SMTP配置', placeholder: '邮箱密码/授权码' },
  { key: 'smtp_sender', label: '发件人', type: 'input', category: 'SMTP配置', placeholder: '发件人名称' },
  // Token 获取方式
  {
    key: 'token_method',
    label: '获取方式',
    type: 'toggle',
    category: 'Token获取方式',
    defaultValue: 'web',
    options: [
      { value: 'web', label: 'Web端' },
      { value: 'remote', label: '远程' },
    ],
  },
  { key: 'remote_token_url', label: '远程URL', type: 'input', category: 'Token获取方式', placeholder: '远程 Token 服务地址' },
  { key: 'remote_token_key', label: '密钥', type: 'secret', category: 'Token获取方式', placeholder: '远程服务密钥' },
  // 密码登录远程配置（仅当 password_login.mode === 'protocol' 时展示）
  { key: 'password_login.remote_url', label: '远程URL', type: 'input', category: '密码登录远程配置', placeholder: 'https://api.xianyushop.shop/api/external/invoke' },
  { key: 'password_login.remote_secret_key', label: '秘钥', type: 'secret', category: '密码登录远程配置', placeholder: '远程服务密钥' },
  // 提现配置
  { key: 'withdraw.notify_email', label: '提现通知邮箱', type: 'input', category: '提现配置', placeholder: '接收提现通知的邮箱' },
  { key: 'withdraw.min_amount', label: '最低提现金额', type: 'input', category: '提现配置', numeric: true, placeholder: '不填则不限制' },
];

const CATEGORIES: { name: SettingCategory; icon: typeof Shield }[] = [
  { name: '基础设置', icon: Shield },
  { name: 'SMTP配置', icon: Mail },
  { name: 'Token获取方式', icon: Globe },
  { name: '密码登录远程配置', icon: Globe },
  { name: '提现配置', icon: Wallet },
];

// 三个可重启服务（顺序：消息 / 后端 / 定时任务，与 Web 端一致）
const SERVICE_CARDS: { key: ServiceKey; label: string; icon: typeof Server }[] = [
  { key: 'websocket', label: '消息服务', icon: MessageSquare },
  { key: 'backend-web', label: '后端服务', icon: Server },
  { key: 'scheduler', label: '定时任务服务', icon: Timer },
];

const CONFIRM_MESSAGE: Record<ServiceKey, string> = {
  websocket: '确定要重启【消息服务】吗？重启期间账号消息收发会短暂中断，约数秒后自动恢复。',
  'backend-web': '确定要重启【后端服务】吗？重启期间当前管理界面会短暂不可用，恢复后会自动提示。',
  scheduler: '确定要重启【定时任务服务】吗？重启期间定时任务会短暂暂停，约数秒后自动恢复。',
};

// 可隐藏的一级菜单（key/label 与 Web 端 navigation.ts 中非管理员可见项对齐，
// 写入同一后端 key `navigation.hidden_menu_keys`，跨端生效）
const HIDEABLE_MENUS: { key: string; label: string }[] = [
  { key: 'dashboard', label: '仪表盘' },
  { key: 'data-analysis', label: '数据分析' },
  { key: 'accounts', label: '账号管理' },
  { key: 'online-chat-new', label: '在线聊天' },
  { key: 'items', label: '商品管理' },
  { key: 'cards', label: '卡券管理' },
  { key: 'orders', label: '订单管理' },
  { key: 'distribution', label: '分销管理' },
  { key: 'product-publish', label: '商品发布' },
  { key: 'product-monitor', label: '商品监控' },
  { key: 'keywords', label: '自动回复' },
  { key: 'message-logs', label: '消息日志' },
  { key: 'risk-logs', label: '风控日志' },
  { key: 'message-filters', label: '消息过滤' },
  { key: 'notification-channels', label: '通知渠道' },
  { key: 'message-notifications', label: '消息通知' },
  { key: 'blacklist', label: '黑名单管理' },
  { key: 'personal-settings', label: '个人设置' },
  { key: 'tutorial', label: '使用教程' },
  { key: 'feedback', label: '意见反馈' },
  { key: 'ad-apply', label: '广告申请' },
  { key: 'disclaimer', label: '免责声明' },
  { key: 'about', label: '关于' },
];

/** 将后端字符串值解析为布尔 */
function isTruthy(v: string | undefined): boolean {
  if (!v) return false;
  const s = v.trim().toLowerCase();
  return s === 'true' || s === '1' || s === 'yes' || s === 'on';
}

export default function SettingsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();
  const serverUrl = useConfigStore((s) => s.serverUrl);
  const profiles = useConfigStore((s) => s.profiles);
  const activeIndex = useConfigStore((s) => s.activeIndex);
  const user = useAuthStore((s) => s.user);
  const isAdmin = !!user?.is_admin;

  const [sysSettings, setSysSettings] = useState<Record<string, string>>({});
  const [initialSettings, setInitialSettings] = useState<Record<string, string>>({});
  const [sysLoading, setSysLoading] = useState(false);
  const [batchSaving, setBatchSaving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  // 服务管理状态
  const [svcStatus, setSvcStatus] = useState<Record<string, boolean>>({});
  const [svcLoading, setSvcLoading] = useState(false);
  const [restartingKey, setRestartingKey] = useState<ServiceKey | null>(null);

  // 菜单可见性状态
  const [hiddenKeys, setHiddenKeys] = useState<string[]>([]);
  const [menuSaving, setMenuSaving] = useState(false);

  // 用户到期设置独立保存
  const [userExpirySaving, setUserExpirySaving] = useState(false);

  // SMTP 测试邮件弹窗
  const [showTestEmail, setShowTestEmail] = useState(false);
  const [testEmail, setTestEmail] = useState('');
  const [sendingTestEmail, setSendingTestEmail] = useState(false);

  // 密码登录远程接口测试
  const [testingRemote, setTestingRemote] = useState(false);

  const loadSvcStatus = useCallback(async () => {
    setSvcLoading(true);
    try {
      const res = await getServicesStatus();
      if (res.success) {
        const map: Record<string, boolean> = {};
        res.services.forEach((s) => {
          map[s.key] = s.online;
        });
        setSvcStatus(map);
      } else {
        // 状态查询失败不打扰用户，置为未知（不显示在线）
        setSvcStatus({});
      }
    } catch {
      setSvcStatus({});
    } finally {
      setSvcLoading(false);
    }
  }, []);

  const loadSystemSettings = useCallback(async () => {
    if (!isAdmin) return;
    setSysLoading(true);
    try {
      const data = await getSystemSettings();
      setSysSettings(data);
      setInitialSettings(data);
      setHiddenKeys(getHiddenMenuKeysFromSettings(data));
    } catch (e) {
      Alert.alert('加载系统设置失败', (e as Error).message);
    } finally {
      setSysLoading(false);
      setRefreshing(false);
    }
  }, [isAdmin]);

  useEffect(() => {
    loadSystemSettings();
    if (isAdmin) loadSvcStatus();
  }, [loadSystemSettings, loadSvcStatus, isAdmin]);

  // 当前未保存的设置项 key（工作副本与初始快照不一致）
  const dirtyKeys = SETTING_DEFS.filter(
    (d) => (sysSettings[d.key] ?? '') !== (initialSettings[d.key] ?? ''),
  ).map((d) => d.key);
  const hasDirty = dirtyKeys.length > 0;

  function setSettingValue(key: string, value: string) {
    setSysSettings((prev) => ({ ...prev, [key]: value }));
  }

  // Switch / Toggle：立即保存
  async function saveImmediately(def: SettingDef, value: string) {
    const prev = sysSettings[def.key] ?? '';
    setSettingValue(def.key, value);
    try {
      await updateSystemSetting(def.key, value);
      setInitialSettings((s) => ({ ...s, [def.key]: value }));
    } catch (e) {
      setSettingValue(def.key, prev);
      Alert.alert('保存失败', (e as Error).message);
    }
  }

  function handleSwitch(def: SettingDef, next: boolean) {
    saveImmediately(def, next ? 'true' : 'false');
  }

  function handleToggle(def: SettingDef, value: string) {
    // 切换到密码登录「远程」前，远程URL与秘钥必须已填写，避免切换后登录直接失败
    if (def.key === 'password_login.mode' && value === 'protocol') {
      const url = (sysSettings['password_login.remote_url'] ?? '').trim();
      const key = (sysSettings['password_login.remote_secret_key'] ?? '').trim();
      if (!url || !key) {
        Alert.alert('无法切换', '请先在「密码登录远程配置」中填写远程URL与秘钥');
        return;
      }
    }
    saveImmediately(def, value);
  }

  // Input：失焦保存
  async function handleInputBlur(def: SettingDef) {
    const val = sysSettings[def.key] ?? '';
    const init = initialSettings[def.key] ?? '';
    if (val === init) return;
    try {
      await updateSystemSetting(def.key, val);
      setInitialSettings((s) => ({ ...s, [def.key]: val }));
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    }
  }

  // 顶部"保存设置"：批量保存所有修改项
  async function handleBatchSave() {
    if (!dirtyKeys.length) return;
    setBatchSaving(true);
    const failed: string[] = [];
    for (const key of dirtyKeys) {
      try {
        await updateSystemSetting(key, sysSettings[key] ?? '');
        setInitialSettings((s) => ({ ...s, [key]: sysSettings[key] ?? '' }));
      } catch {
        failed.push(key);
      }
    }
    setBatchSaving(false);
    if (failed.length) {
      Alert.alert('部分保存失败', `${failed.length} 项保存失败，请重试`);
    } else {
      Alert.alert('保存成功', '所有修改已保存');
    }
  }

  // 服务重启：二次确认后执行
  function handleRestartRequest(key: ServiceKey) {
    Alert.alert('重启服务确认', CONFIRM_MESSAGE[key], [
      { text: '取消', style: 'cancel' },
      { text: '确定重启', style: 'destructive', onPress: () => doRestart(key) },
    ]);
  }

  async function doRestart(key: ServiceKey) {
    setRestartingKey(key);
    try {
      const res = await restartService(key);
      if (res.success) {
        Alert.alert('已触发', res.message || '重启请求已发送');
        if (key === 'backend-web') {
          // 后端自身重启：轮询健康检查直到恢复
          Alert.alert('提示', '后端服务正在重启，请稍候…');
          waitBackendRecover();
        } else {
          // 消息/定时任务服务：延迟刷新一次状态
          setTimeout(loadSvcStatus, 4000);
        }
      } else {
        Alert.alert('重启失败', res.message || '重启失败');
      }
    } catch (e) {
      Alert.alert('重启失败', (e as Error).message);
    } finally {
      setRestartingKey(null);
    }
  }

  // 后端服务重启后：轮询健康检查直到恢复（最多约 60s）
  const waitBackendRecover = useCallback(async () => {
    const maxAttempts = 30;
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((resolve) => setTimeout(resolve, 2000));
      const ok = await pingHealth();
      if (ok) {
        Alert.alert('成功', '后端服务已重启完成');
        loadSvcStatus();
        return;
      }
    }
    Alert.alert('提示', '后端服务重启超时未恢复，请稍后手动刷新页面确认');
    loadSvcStatus();
  }, [loadSvcStatus]);

  // 菜单可见性：切换后立即保存（带回滚）
  async function handleToggleMenu(menuKey: string, hide: boolean) {
    const prev = [...hiddenKeys];
    const next = hide
      ? Array.from(new Set([...prev, menuKey]))
      : prev.filter((k) => k !== menuKey);
    setHiddenKeys(next);
    setMenuSaving(true);
    try {
      await updateSystemSetting(
        'navigation.hidden_menu_keys',
        serializeHiddenMenuKeys(next),
      );
    } catch (e) {
      setHiddenKeys(prev);
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setMenuSaving(false);
    }
  }

  // 用户到期设置：独立保存（带校验）
  async function handleUserExpirySave() {
    const renew = (sysSettings['user.renew_month_price'] ?? '').trim();
    const days = (sysSettings['user.register_default_days'] ?? '').trim();

    if (renew !== '' && (!/^\d+(\.\d{1,2})?$/.test(renew) || Number(renew) <= 0)) {
      Alert.alert('格式错误', '续期单价必须为大于0的数字（最多两位小数）');
      return;
    }
    if (days !== '' && (!/^\d+$/.test(days) || Number(days) <= 0)) {
      Alert.alert('格式错误', '注册默认天数必须为正整数');
      return;
    }

    setUserExpirySaving(true);
    try {
      await updateSystemSetting('user.renew_month_price', renew);
      await updateSystemSetting('user.register_default_days', days);
      setInitialSettings((s) => ({
        ...s,
        'user.renew_month_price': renew,
        'user.register_default_days': days,
      }));
      Alert.alert('保存成功', '用户到期设置已保存');
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setUserExpirySaving(false);
    }
  }

  // SMTP 测试邮件
  async function handleTestEmail() {
    const email = testEmail.trim();
    if (!email) {
      Alert.alert('提示', '请输入测试邮箱地址');
      return;
    }
    setSendingTestEmail(true);
    try {
      const res = await testEmailSend(email);
      if (res.success) {
        Alert.alert('成功', '测试邮件发送成功');
        setShowTestEmail(false);
        setTestEmail('');
      } else {
        Alert.alert('失败', res.message || '发送测试邮件失败');
      }
    } catch (e) {
      Alert.alert('失败', (e as Error).message);
    } finally {
      setSendingTestEmail(false);
    }
  }

  // 密码登录远程接口测试
  async function handleTestRemote() {
    const url = (sysSettings['password_login.remote_url'] ?? '').trim();
    const key = (sysSettings['password_login.remote_secret_key'] ?? '').trim();
    if (!url || !key) {
      Alert.alert('提示', '请先填写远程URL与秘钥');
      return;
    }
    setTestingRemote(true);
    try {
      const res = await testPasswordLoginRemote({
        remote_url: url,
        remote_secret_key: key,
      });
      if (res.success) {
        Alert.alert('成功', res.message || '远程接口连通性测试成功');
      } else {
        Alert.alert('失败', res.message || '远程接口测试失败');
      }
    } catch (e) {
      Alert.alert('失败', (e as Error).message);
    } finally {
      setTestingRemote(false);
    }
  }

  // 密码登录方式当前值（决定是否展示远程配置卡）
  const passwordLoginMode = sysSettings['password_login.mode'] || 'browser';

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: c.background }]}
      edges={['top', 'left', 'right', 'bottom']}
    >
      <View style={styles.header}>
        {isAdmin && (
          <Button
            label="保存设置"
            onPress={handleBatchSave}
            loading={batchSaving}
            disabled={batchSaving || !hasDirty}
            variant={hasDirty ? 'primary' : 'secondary'}
            style={styles.saveBtn}
          />
        )}
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* 个人设置入口 */}
        <Card style={styles.entryCard}>
          <Pressable
            onPress={() => router.push('/(tabs)/mine/personal')}
            style={({ pressed }) => [
              styles.entryRow,
              pressed && { backgroundColor: c.primaryLight },
            ]}
          >
            <User size={20} stroke={c.textSecondary} />
            <Text style={[styles.entryLabel, { color: c.text }]}>个人设置</Text>
            <ChevronRight size={18} stroke={c.textMuted} />
          </Pressable>
        </Card>

        {/* 系统设置（管理员可见） */}
        {isAdmin && (
          <View style={styles.systemSection}>
            <View style={styles.sectionHeaderRow}>
              <View style={styles.sectionTitleRow}>
                <SettingsIcon size={16} stroke={c.textSecondary} />
                <Text style={[styles.sectionHeader, { color: c.textSecondary }]}>
                  系统设置
                </Text>
              </View>
              <Pressable
                onPress={() => {
                  setRefreshing(true);
                  loadSystemSettings();
                }}
                hitSlop={8}
                disabled={refreshing}
                style={styles.refreshBtn}
              >
                {refreshing ? (
                  <ActivityIndicator size="small" color={c.primary} />
                ) : (
                  <RefreshCw size={16} stroke={c.textSecondary} />
                )}
              </Pressable>
            </View>

            {/* 服务管理（仅管理员，置于最上方） */}
            <Card style={styles.section}>
              <View style={[styles.sectionTitleRow, { justifyContent: 'space-between' }]}>
                <View style={styles.sectionTitleRow}>
                  <RotateCcw size={16} stroke={c.textSecondary} />
                  <Text style={[styles.sectionTitle, { color: c.textSecondary }]}>
                    服务管理
                  </Text>
                </View>
                <Pressable
                  onPress={loadSvcStatus}
                  hitSlop={8}
                  disabled={svcLoading}
                  style={styles.refreshBtn}
                >
                  {svcLoading ? (
                    <ActivityIndicator size="small" color={c.primary} />
                  ) : (
                    <RotateCcw size={16} stroke={c.textSecondary} />
                  )}
                </Pressable>
              </View>
              <Text style={[styles.hint, { color: c.textMuted }]}>
                重启会先停止进程再启动，期间对应功能短暂不可用。
              </Text>
              {SERVICE_CARDS.map(({ key, label, icon: Icon }) => {
                const online = svcStatus[key];
                const restarting = restartingKey === key;
                return (
                  <View
                    key={key}
                    style={[styles.svcRow, { borderTopColor: c.borderLight }]}
                  >
                    <View style={styles.svcLeft}>
                      <Icon size={18} stroke={c.textSecondary} />
                      <Text style={[styles.svcLabel, { color: c.text }]}>{label}</Text>
                    </View>
                    <View style={styles.svcRight}>
                      <View
                        style={[
                          styles.badge,
                          { backgroundColor: online ? c.success : c.border },
                        ]}
                      >
                        <Text style={styles.badgeText}>
                          {online ? '在线' : '离线'}
                        </Text>
                      </View>
                      <Button
                        label={restarting ? '重启中' : '重启'}
                        onPress={() => handleRestartRequest(key)}
                        variant="secondary"
                        loading={restarting}
                        disabled={restarting}
                        style={styles.svcBtn}
                      />
                    </View>
                  </View>
                );
              })}
            </Card>

            {sysLoading ? (
              <Loading label="加载系统设置..." />
            ) : (
              <>
                {CATEGORIES.map((cat) => {
                  // 密码登录远程配置仅在「远程」模式下展示
                  if (
                    cat.name === '密码登录远程配置' &&
                    passwordLoginMode !== 'protocol'
                  ) {
                    return null;
                  }
                  const Icon = cat.icon;
                  const fields = SETTING_DEFS.filter((d) => d.category === cat.name);
                  return (
                    <Card key={cat.name} style={styles.section}>
                      <View style={styles.sectionTitleRow}>
                        <Icon size={16} stroke={c.textSecondary} />
                        <Text style={[styles.sectionTitle, { color: c.textSecondary }]}>
                          {cat.name}
                        </Text>
                      </View>

                      {fields.map((def) => {
                        const value = sysSettings[def.key] ?? '';
                        return (
                          <View key={def.key} style={styles.fieldRow}>
                            {def.type === 'switch' ? (
                              <View style={styles.switchRow}>
                                <Text style={[styles.fieldLabel, { color: c.text, flex: 1 }]}>
                                  {def.label}
                                </Text>
                                <Switch
                                  value={isTruthy(value)}
                                  onValueChange={(v) => handleSwitch(def, v)}
                                  trackColor={{ false: c.border, true: c.primary }}
                                />
                              </View>
                            ) : def.type === 'toggle' ? (
                              <View style={styles.toggleField}>
                                <Text style={[styles.fieldLabel, { color: c.text }]}>
                                  {def.label}
                                </Text>
                                <View
                                  style={[
                                    styles.segmented,
                                    { backgroundColor: c.background, borderColor: c.border },
                                  ]}
                                >
                                  {def.options?.map((opt) => {
                                    const active =
                                      (value || def.defaultValue || '') === opt.value;
                                    return (
                                      <Pressable
                                        key={opt.value}
                                        onPress={() => handleToggle(def, opt.value)}
                                        style={[
                                          styles.segment,
                                          active && { backgroundColor: c.primary },
                                        ]}
                                      >
                                        <Text
                                          style={[
                                            styles.segmentText,
                                            { color: active ? '#FFF' : c.textSecondary },
                                          ]}
                                        >
                                          {opt.label}
                                        </Text>
                                      </Pressable>
                                    );
                                  })}
                                </View>
                              </View>
                            ) : (
                              <View style={styles.inputField}>
                                <Text style={[styles.fieldLabel, { color: c.text }]}>
                                  {def.label}
                                </Text>
                                <Input
                                  value={value}
                                  onChangeText={(t) => setSettingValue(def.key, t)}
                                  onEndEditing={() => handleInputBlur(def)}
                                  placeholder={def.placeholder}
                                  placeholderTextColor={c.textMuted}
                                  keyboardType={def.numeric ? 'numeric' : 'default'}
                                  secureTextEntry={def.type === 'secret'}
                                  autoCapitalize="none"
                                  autoCorrect={false}
                                  style={styles.input}
                                />
                              </View>
                            )}
                          </View>
                        );
                      })}

                      {/* 类别专属操作区 */}
                      {cat.name === 'SMTP配置' && (
                        <Button
                          label="发送测试邮件"
                          onPress={() => setShowTestEmail(true)}
                          variant="secondary"
                          style={styles.catFooterBtn}
                        />
                      )}
                      {cat.name === '密码登录远程配置' && (
                        <View style={styles.footerGroup}>
                          <Text style={[styles.hint, { color: c.textMuted }]}>
                            秘钥通过 X-API-Key 请求头发送，测试仅验证连通性。
                          </Text>
                          <Button
                            label="测试远程接口"
                            onPress={handleTestRemote}
                            loading={testingRemote}
                            disabled={testingRemote}
                            variant="secondary"
                            style={styles.catFooterBtn}
                          />
                        </View>
                      )}
                    </Card>
                  );
                })}

                {/* 菜单可见性 */}
                <Card style={styles.section}>
                  <View style={[styles.sectionTitleRow, { justifyContent: 'space-between' }]}>
                    <View style={styles.sectionTitleRow}>
                      <EyeOff size={16} stroke={c.textSecondary} />
                      <Text style={[styles.sectionTitle, { color: c.textSecondary }]}>
                        菜单可见性
                      </Text>
                    </View>
                    <Text style={[styles.hint, { color: c.textMuted }]}>
                      {menuSaving ? '保存中…' : `已隐藏 ${hiddenKeys.length}/${HIDEABLE_MENUS.length} 项`}
                    </Text>
                  </View>
                  <Text style={[styles.hint, { color: c.textMuted }]}>
                    隐藏后普通用户不可见该一级菜单（含其下所有子菜单）。
                  </Text>
                  {HIDEABLE_MENUS.map((m) => {
                    const checked = hiddenKeys.includes(m.key);
                    return (
                      <View key={m.key} style={styles.switchRow}>
                        <Text style={[styles.fieldLabel, { color: c.text, flex: 1 }]}>
                          {m.label}
                        </Text>
                        <Switch
                          value={checked}
                          onValueChange={(v) => handleToggleMenu(m.key, v)}
                          trackColor={{ false: c.border, true: c.primary }}
                        />
                      </View>
                    );
                  })}
                </Card>

                {/* 用户到期设置（独立保存） */}
                <Card style={styles.section}>
                  <View style={styles.sectionTitleRow}>
                    <CalendarClock size={16} stroke={c.textSecondary} />
                    <Text style={[styles.sectionTitle, { color: c.textSecondary }]}>
                      用户到期设置
                    </Text>
                  </View>
                  <Text style={[styles.hint, { color: c.textMuted }]}>
                    配置续期单价与注册默认天数。注册天数留空表示永不过期。
                  </Text>
                  <View style={styles.inputField}>
                    <Text style={[styles.fieldLabel, { color: c.text }]}>
                      续期一个月价格（元）
                    </Text>
                    <Input
                      value={sysSettings['user.renew_month_price'] ?? ''}
                      onChangeText={(t) =>
                        setSettingValue('user.renew_month_price', t)
                      }
                      placeholder="如 30.00"
                      placeholderTextColor={c.textMuted}
                      keyboardType="numeric"
                      autoCapitalize="none"
                      autoCorrect={false}
                      style={styles.input}
                    />
                  </View>
                  <View style={styles.inputField}>
                    <Text style={[styles.fieldLabel, { color: c.text }]}>
                      注册默认天数（天）
                    </Text>
                    <Input
                      value={sysSettings['user.register_default_days'] ?? ''}
                      onChangeText={(t) =>
                        setSettingValue('user.register_default_days', t)
                      }
                      placeholder="留空表示永不过期"
                      placeholderTextColor={c.textMuted}
                      keyboardType="numeric"
                      autoCapitalize="none"
                      autoCorrect={false}
                      style={styles.input}
                    />
                  </View>
                  <Button
                    label="保存到期设置"
                    onPress={handleUserExpirySave}
                    loading={userExpirySaving}
                    disabled={userExpirySaving}
                    style={styles.catFooterBtn}
                  />
                </Card>
              </>
            )}
          </View>
        )}

        {/* 服务器配置 */}
        <Card style={styles.section}>
          <View style={styles.sectionTitleRow}>
            <Server size={16} stroke={c.textSecondary} />
            <Text style={[styles.sectionTitle, { color: c.textSecondary }]}>服务器</Text>
          </View>
          <View style={styles.settingRow}>
            <Text style={[styles.settingLabel, { color: c.text }]}>当前服务器</Text>
            <Text style={[styles.settingValue, { color: c.textMuted }]} numberOfLines={1}>
              {serverUrl ?? '未配置'}
            </Text>
          </View>
          <View style={styles.settingRow}>
            <Text style={[styles.settingLabel, { color: c.text }]}>当前配置</Text>
            <Text style={[styles.settingValue, { color: c.textMuted }]}>
              {activeIndex >= 0 ? `#${activeIndex + 1}` : '未选择'}
            </Text>
          </View>
          <View style={styles.settingRow}>
            <Text style={[styles.settingLabel, { color: c.text }]}>已保存配置</Text>
            <Text style={[styles.settingValue, { color: c.textMuted }]}>
              {profiles.length} 个
            </Text>
          </View>
        </Card>

        {/* 外观 */}
        <Card style={styles.section}>
          <View style={styles.sectionTitleRow}>
            <Info size={16} stroke={c.textSecondary} />
            <Text style={[styles.sectionTitle, { color: c.textSecondary }]}>外观</Text>
          </View>
          <View style={styles.settingRow}>
            <Text style={[styles.settingLabel, { color: c.text }]}>主题模式</Text>
            <Text style={[styles.settingValue, { color: c.textMuted }]}>
              {scheme === 'dark' ? '深色（跟随系统）' : '浅色（跟随系统）'}
            </Text>
          </View>
        </Card>

        {/* 关于 */}
        <Card style={styles.section}>
          <View style={styles.sectionTitleRow}>
            <Info size={16} stroke={c.textSecondary} />
            <Text style={[styles.sectionTitle, { color: c.textSecondary }]}>关于</Text>
          </View>
          <View style={styles.settingRow}>
            <Text style={[styles.settingLabel, { color: c.text }]}>版本号</Text>
            <Text style={[styles.settingValue, { color: c.textMuted }]}>1.0.0</Text>
          </View>
          <View style={styles.settingRow}>
            <Text style={[styles.settingLabel, { color: c.text }]}>项目</Text>
            <Text style={[styles.settingValue, { color: c.textMuted }]}>
              xianyu-mobile
            </Text>
          </View>
        </Card>
      </ScrollView>

      {/* 发送测试邮件弹窗 */}
      <FormModal
        visible={showTestEmail}
        onClose={() => setShowTestEmail(false)}
        title="发送测试邮件"
      >
        <View style={styles.inputField}>
          <Text style={[styles.fieldLabel, { color: c.text }]}>测试邮箱地址</Text>
          <Input
            value={testEmail}
            onChangeText={setTestEmail}
            placeholder="请输入接收测试邮件的邮箱"
            placeholderTextColor={c.textMuted}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.input}
          />
        </View>
        <View style={styles.modalBtnRow}>
          <Button
            label="取消"
            onPress={() => setShowTestEmail(false)}
            variant="secondary"
            disabled={sendingTestEmail}
            style={styles.modalBtn}
          />
          <Button
            label="发送"
            onPress={handleTestEmail}
            loading={sendingTestEmail}
            disabled={sendingTestEmail}
            style={styles.modalBtn}
          />
        </View>
      </FormModal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.sm,
  },
  saveBtn: { minHeight: 40, paddingHorizontal: spacing.md },
  content: { padding: spacing.lg, gap: spacing.lg, paddingBottom: 120 },
  entryCard: { padding: 0, overflow: 'hidden' },
  entryRow: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: spacing.md,
  },
  entryLabel: { ...typography.body, flex: 1 },
  systemSection: { gap: spacing.md },
  sectionHeaderRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.xs,
  },
  sectionTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  sectionHeader: { ...typography.caption, fontWeight: '600' },
  refreshBtn: { padding: spacing.xs },
  section: { gap: spacing.sm },
  sectionTitle: { ...typography.caption, fontWeight: '600' },
  hint: { ...typography.small, lineHeight: 16 },
  fieldRow: { paddingVertical: spacing.xs },
  switchRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.xs,
  },
  fieldLabel: { ...typography.body, marginBottom: spacing.xs },
  inputField: { gap: spacing.xs },
  input: { minHeight: 44 },
  toggleField: { gap: spacing.xs },
  segmented: {
    flexDirection: 'row',
    borderRadius: radius.sm,
    borderWidth: 1,
    overflow: 'hidden',
  },
  segment: {
    flex: 1,
    paddingVertical: spacing.sm,
    paddingHorizontal: spacing.md,
    alignItems: 'center',
    justifyContent: 'center',
  },
  segmentText: { ...typography.small, fontWeight: '600' },
  // 服务管理
  svcRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
  },
  svcLeft: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  svcLabel: { ...typography.body },
  svcRight: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  badge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.full },
  badgeText: { color: '#FFF', ...typography.micro },
  svcBtn: { minHeight: 36, paddingHorizontal: spacing.md },
  // 类别操作区
  catFooterBtn: { minHeight: 40, alignSelf: 'flex-start' },
  footerGroup: { gap: spacing.xs },
  modalBtnRow: { flexDirection: 'row', gap: spacing.sm, justifyContent: 'flex-end' },
  modalBtn: { flex: 1, minHeight: 40 },
  settingRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.xs,
  },
  settingLabel: { ...typography.body },
  settingValue: { ...typography.body, flex: 1, textAlign: 'right' },
});
