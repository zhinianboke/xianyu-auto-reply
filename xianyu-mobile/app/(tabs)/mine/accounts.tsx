import { useState, useEffect, useCallback, useRef, useMemo, memo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Switch,
  Pressable,
  Alert,
  Modal,
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  Image,
  type ListRenderItem,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Loading, Button, Input, FAB, FormModal, FilterTabs } from '@/components/ui';
import { Trash2, Eye, EyeOff } from 'lucide-react-native';
import { PasswordLoginModal } from '@/components/PasswordLoginModal';
import * as DocumentPicker from 'expo-document-picker';
import * as ImagePicker from 'expo-image-picker';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getAccountDetailsPaginated,
  toggleAccount,
  toggleAccountFeature,
  batchUpdateStatus,
  batchClearTokenCache,
  batchCloseNotice,
  batchRenewLogin,
  exportAccounts,
  importAccounts,
  updateAccountRemark,
  updateAccountCookie,
  updateAccountPauseDuration,
  updateAccountLoginInfo,
  deleteAccount,
  generateQrLogin,
  checkQrLoginStatus,
  getQrLoginCookie,
  getDefaultReply,
  updateDefaultReply,
  uploadDefaultReplyImage,
  type AccountDetail,
  type QrLoginSession,
  type ToggleKey,
  type DefaultReplyConfig,
} from '@/api/wrappers/accounts';
import {
  getAccountAiSettings,
  updateAccountAiSettings,
  testAccountAiConnection,
  AI_PROVIDER_OPTIONS,
  AI_PROVIDER_DEFAULT_BASE_URLS,
  type AIProviderType,
  type AIReplySettings,
} from '@/api/wrappers/ai-settings';
import { useAccountsStore } from '@/stores/accounts';
import {
  getAgreeDeliverConfig,
  updateAgreeDeliverConfig,
  getPickupUrlSuggestion,
} from '@/api/wrappers/agree-deliver';
import {
  getProxyConfig,
  updateProxyConfig,
  updateMessageExpireTime,
  updateReplyDelay,
  getFaceVerificationScreenshot,
  deleteFaceVerificationScreenshot,
  getConfirmReceiptMessage,
  updateConfirmReceiptMessage,
  uploadConfirmReceiptImage,
  getAutoRateConfig,
  updateAutoRateConfig,
  getDeliveryBlockRules,
  updateDeliveryBlockRules,
  getRefundCancelConfig,
  updateRefundCancelConfig,
  type ProxyType,
  type ProxyConfig,
  type FaceVerificationScreenshot,
  type ConfirmReceiptConfig,
  type AutoRateConfig,
  type DeliveryBlockRuleItem,
  type DeliveryBlockRulePayload,
  type RefundCancelConfig,
} from '@/api/wrappers/account-advanced';

const PAGE_SIZE = 20;
const POLL_INTERVAL = 2000;

/** 顶部筛选 tab：全部 / 在线 / 离线 / 已禁用（客户端过滤已加载列表） */
type AccountFilter = 'all' | 'online' | 'offline' | 'disabled';
const FILTER_TABS: { key: AccountFilter; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'online', label: '在线' },
  { key: 'offline', label: '离线' },
  { key: 'disabled', label: '已禁用' },
];

/** 9 个功能开关定义 */
const TOGGLE_DEFS: { key: ToggleKey; label: string }[] = [
  { key: 'auto_confirm', label: '自动确认收货' },
  { key: 'auto_polish', label: '商品自动擦亮' },
  { key: 'auto_red_flower', label: '自动求小红花' },
  { key: 'scheduled_redelivery', label: '定时补发货' },
  { key: 'scheduled_rate', label: '定时补评价' },
  { key: 'confirm_before_send', label: '发货成功再发卡券' },
  { key: 'send_before_confirm', label: '卡券成功再确认发货' },
  { key: 'only_send_card', label: '只发卡券不确认发货' },
  { key: 'ai_reply_block_ordered_users', label: '已下单禁AI回复' },
];

/** 8 项高级配置入口 key，对应弹窗 dispatch */
type AdvancedConfigKey =
  | 'proxy'
  | 'messageExpireTime'
  | 'replyDelay'
  | 'faceVerification'
  | 'confirmReceipt'
  | 'autoRate'
  | 'deliveryDisabled'
  | 'refundCancel';

/** 8 项高级配置入口定义（与 AI设置/默认回复/同意后发货 同风格） */
const ADVANCED_CONFIG_DEFS: { key: AdvancedConfigKey; label: string }[] = [
  { key: 'proxy', label: '代理设置' },
  { key: 'messageExpireTime', label: '消息等待时间' },
  { key: 'replyDelay', label: '回复延迟' },
  { key: 'faceVerification', label: '人脸验证截图' },
  { key: 'confirmReceipt', label: '确认收货消息' },
  { key: 'autoRate', label: '自动评价' },
  { key: 'deliveryDisabled', label: '禁止发货规则' },
  { key: 'refundCancel', label: '退款订单注销' },
];

/** 扫码状态文案 */
function statusLabel(status: string): string {
  switch (status) {
    case 'loading':
      return '正在生成二维码...';
    case 'ready':
      return '请使用闲鱼 App 扫码登录';
    case 'scanned':
      return '已扫描，请在手机上确认登录';
    case 'verification_required':
      return '需要人脸验证';
    case 'success':
      return '登录成功';
    default:
      return '等待扫码...';
  }
}

type ThemeColors = (typeof colors)['light'];

interface AccountCardProps {
  item: AccountDetail;
  /** colors.light / colors.dark 的稳定引用，仅随系统主题切换变化 */
  c: ThemeColors;
  multiSelect: boolean;
  /** 派生布尔值而非整个 selectedIds，勾选时仅被操作的卡片重渲染 */
  selected: boolean;
  /** 派生布尔值而非整个 expandedPk，展开切换时仅目标卡片重渲染 */
  expanded: boolean;
  onPress: (item: AccountDetail) => void;
  onLongPress: (item: AccountDetail) => void;
  onToggle: (id: string, currentEnabled: boolean) => void;
  onToggleFeature: (accountId: string, key: ToggleKey, currentVal: boolean) => void;
  onEdit: (account: AccountDetail) => void;
  onDelete: (account: AccountDetail) => void;
  onPasswordLogin: (account: AccountDetail) => void;
  onToggleExpand: (pk: number) => void;
  onOpenAgreeConfig: (account: AccountDetail) => void;
  onOpenAiSettings: (account: AccountDetail) => void;
  onOpenDefaultReply: (account: AccountDetail) => void;
  onOpenAdvanced: (account: AccountDetail, key: AdvancedConfigKey) => void;
}

/** 卡片操作按钮：flex:1 等宽 + numberOfLines=1，避免"密码登录""更多设置"在四按钮行内折行 */
function CardActionButton({
  label,
  onPress,
  tone,
  c,
}: {
  label: string;
  onPress: () => void;
  tone: 'primary' | 'secondary';
  c: ThemeColors;
}) {
  const isPrimary = tone === 'primary';
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.cardActionBtn,
        {
          backgroundColor: isPrimary ? c.primary : c.surface,
          borderColor: isPrimary ? c.primary : c.border,
          opacity: pressed ? 0.7 : 1,
        },
      ]}
    >
      <Text
        style={[styles.cardActionText, { color: isPrimary ? '#FFFFFF' : c.text }]}
        numberOfLines={1}
      >
        {label}
      </Text>
    </Pressable>
  );
}

/** 账号卡片：统计 + 4 按钮 + 9 开关的可展开列表项 */
const AccountCard = memo(function AccountCard({
  item,
  c,
  multiSelect,
  selected,
  expanded,
  onPress,
  onLongPress,
  onToggle,
  onToggleFeature,
  onEdit,
  onDelete,
  onPasswordLogin,
  onToggleExpand,
  onOpenAgreeConfig,
  onOpenAiSettings,
  onOpenDefaultReply,
  onOpenAdvanced,
}: AccountCardProps) {
  return (
    <Pressable onLongPress={() => onLongPress(item)} onPress={() => onPress(item)}>
      <Card style={[styles.card, multiSelect && selected && { borderColor: c.primary, borderWidth: 2 }]}>
        {multiSelect && (
          <View style={[styles.selectIndicator, { backgroundColor: selected ? c.primary : c.border }]}>
            <Text style={{ color: '#FFF', fontSize: 16, fontWeight: '700' }}>{selected ? '✓' : ''}</Text>
          </View>
        )}
        <View style={styles.cardHeader}>
          <View style={styles.cardInfo}>
            <View style={styles.nameRow}>
              <View
                style={[
                  styles.statusDot,
                  { backgroundColor: item.online ? c.success : c.textMuted },
                ]}
              />
              <Text style={[styles.accountName, { color: c.text }]} numberOfLines={1}>
                {item.remark || item.id}
              </Text>
            </View>
            <Text style={[styles.accountId, { color: c.textMuted }]} numberOfLines={1}>
              ID: {item.id}
            </Text>
          </View>
          <Switch
            value={item.enabled}
            onValueChange={() => onToggle(item.id, item.enabled)}
            trackColor={{ false: c.border, true: c.primary }}
          thumbColor="#FFFFFF"
          />
        </View>

        <View style={[styles.statsRow, { borderTopColor: c.border }]}>
          <View style={styles.stat}>
            <Text style={[styles.statValue, { color: c.text }]}>
              {item.today_reply_count ?? '-'}
            </Text>
            <Text style={[styles.statLabel, { color: c.textMuted }]}>今日回复</Text>
          </View>
          <View style={styles.stat}>
            <Text style={[styles.statValue, { color: c.text }]}>
              {item.keyword_count ?? '-'}
            </Text>
            <Text style={[styles.statLabel, { color: c.textMuted }]}>关键词</Text>
          </View>
          <View style={styles.stat}>
            <Text
              style={[
                styles.statValue,
                { color: item.online ? c.success : c.textMuted },
              ]}
            >
              {item.online ? '在线' : '离线'}
            </Text>
            <Text style={[styles.statLabel, { color: c.textMuted }]}>状态</Text>
          </View>
        </View>

        {!item.enabled && item.disable_reason ? (
          <Text style={[styles.disableReason, { color: c.error }]} numberOfLines={1}>
            停用原因：{item.disable_reason}
          </Text>
        ) : null}

        <View style={styles.cardActions}>
          <CardActionButton label="编辑" onPress={() => onEdit(item)} tone="secondary" c={c} />
          <CardActionButton label="密码登录" onPress={() => onPasswordLogin(item)} tone="primary" c={c} />
          <CardActionButton
            label={expanded ? '收起' : '更多设置'}
            onPress={() => onToggleExpand(item.pk)}
            tone="secondary"
            c={c}
          />
          <Pressable
            onPress={() => onDelete(item)}
            hitSlop={8}
            style={({ pressed }) => [
              styles.cardActionBtn,
              { borderColor: c.error, opacity: pressed ? 0.7 : 1 },
            ]}
          >
            <Trash2 size={18} stroke={c.error} />
          </Pressable>
        </View>

        {/* 9 个功能开关（可展开） */}
        {expanded && (
          <View style={[styles.togglesContainer, { borderTopColor: c.border }]}>
            {TOGGLE_DEFS.map(({ key, label }) => (
              <View key={key} style={styles.toggleRow}>
                <Text style={[styles.toggleLabel, { color: c.text }]}>{label}</Text>
                <Switch
                  value={Boolean((item as unknown as Record<string, unknown>)[key])}
                  onValueChange={() =>
                    onToggleFeature(item.id, key, Boolean((item as unknown as Record<string, unknown>)[key]))
                  }
                  trackColor={{ false: c.border, true: c.primary }}
                  thumbColor="#FFFFFF"
                />
              </View>
            ))}
            {/* 同意后发货配置入口 */}
            <Pressable style={styles.toggleRow} onPress={() => onOpenAgreeConfig(item)}>
              <Text style={[styles.toggleLabel, { color: c.text }]}>同意后发货</Text>
              <Text style={[styles.agreeEntryHint, { color: c.textMuted }]}>配置 ›</Text>
            </Pressable>
            {/* AI 设置入口 */}
            <Pressable style={styles.toggleRow} onPress={() => onOpenAiSettings(item)}>
              <Text style={[styles.toggleLabel, { color: c.text }]}>AI设置</Text>
              <Text style={[styles.agreeEntryHint, { color: c.textMuted }]}>配置 ›</Text>
            </Pressable>
            {/* 默认回复入口 */}
            <Pressable style={styles.toggleRow} onPress={() => onOpenDefaultReply(item)}>
              <Text style={[styles.toggleLabel, { color: c.text }]}>默认回复</Text>
              <Text style={[styles.agreeEntryHint, { color: c.textMuted }]}>配置 ›</Text>
            </Pressable>
            {/* 8 项高级配置入口 */}
            {ADVANCED_CONFIG_DEFS.map(({ key, label }) => (
              <Pressable
                key={key}
                style={styles.toggleRow}
                onPress={() => onOpenAdvanced(item, key)}
              >
                <Text style={[styles.toggleLabel, { color: c.text }]}>{label}</Text>
                <Text style={[styles.agreeEntryHint, { color: c.textMuted }]}>配置 ›</Text>
              </Pressable>
            ))}
          </View>
        )}
      </Card>
    </Pressable>
  );
});

export default function AccountsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [accounts, setAccounts] = useState<AccountDetail[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  // 功能开关展开 + 多选 + 密码登录
  const [expandedPk, setExpandedPk] = useState<number | null>(null);
  const [multiSelect, setMultiSelect] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [batchLoading, setBatchLoading] = useState(false);
  const [pwdLoginAccount, setPwdLoginAccount] = useState<AccountDetail | null>(null);

  // 扫码登录状态
  const [qrVisible, setQrVisible] = useState(false);
  const [qrSession, setQrSession] = useState<QrLoginSession | null>(null);
  const [qrLoading, setQrLoading] = useState(false);
  const [qrStatus, setQrStatus] = useState('loading');
  const [qrMessage, setQrMessage] = useState('');
  const [qrCompleting, setQrCompleting] = useState(false);

  // 编辑状态
  const [editVisible, setEditVisible] = useState(false);
  const [editAccount, setEditAccount] = useState<AccountDetail | null>(null);
  const [editRemark, setEditRemark] = useState('');
  const [editSaving, setEditSaving] = useState(false);
  // 编辑扩展字段：Cookie / 暂停时间 / 登录信息（与 web 编辑弹窗字段对齐）
  const [editCookie, setEditCookie] = useState('');
  const [editPauseDuration, setEditPauseDuration] = useState('0');
  const [editUsername, setEditUsername] = useState('');
  const [editPassword, setEditPassword] = useState('');
  const [editPasswordVisible, setEditPasswordVisible] = useState(false);
  const [editShowBrowser, setEditShowBrowser] = useState(false);

  // 顶部筛选：状态 tab + 关键词搜索（客户端过滤已加载列表）
  const [filterTab, setFilterTab] = useState<AccountFilter>('all');
  const [searchKey, setSearchKey] = useState('');

  // 同意后发货配置
  const [agreeVisible, setAgreeVisible] = useState(false);
  const [agreeAccount, setAgreeAccount] = useState<AccountDetail | null>(null);
  const [agreeLoading, setAgreeLoading] = useState(false);
  const [agreeSaving, setAgreeSaving] = useState(false);
  const [agreeEnabled, setAgreeEnabled] = useState(false);
  const [agreeMessage, setAgreeMessage] = useState('');
  const [agreeUrl, setAgreeUrl] = useState('');
  const [suggestLoading, setSuggestLoading] = useState(false);

  // AI 设置
  const [aiVisible, setAiVisible] = useState(false);
  const [aiAccount, setAiAccount] = useState<AccountDetail | null>(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiSaving, setAiSaving] = useState(false);
  const [aiTesting, setAiTesting] = useState(false);
  const [aiEnabled, setAiEnabled] = useState(false);
  const [aiProvider, setAiProvider] = useState<AIProviderType>('openai_compatible');
  const [aiApiUrl, setAiApiUrl] = useState('');
  const [aiApiKey, setAiApiKey] = useState('');
  const [aiModel, setAiModel] = useState('');
  const [aiBargainRounds, setAiBargainRounds] = useState('3');
  const [aiPrompts, setAiPrompts] = useState('');
  const [aiTimeStart, setAiTimeStart] = useState('');
  const [aiTimeEnd, setAiTimeEnd] = useState('');

  // 默认回复
  const [replyVisible, setReplyVisible] = useState(false);
  const [replyAccount, setReplyAccount] = useState<AccountDetail | null>(null);
  const [replyLoading, setReplyLoading] = useState(false);
  const [replySaving, setReplySaving] = useState(false);
  const [replyImgUploading, setReplyImgUploading] = useState(false);
  const [replyEnabled, setReplyEnabled] = useState(false);
  const [replyType, setReplyType] = useState<'text' | 'api'>('text');
  const [replyContent, setReplyContent] = useState('');
  const [replyImage, setReplyImage] = useState('');
  const [replyApiUrl, setReplyApiUrl] = useState('');
  const [replyApiTimeout, setReplyApiTimeout] = useState('80');
  const [replyOnce, setReplyOnce] = useState(false);

  // ==================== 8 项高级配置状态 ====================
  // 1. 代理设置
  const [proxyVisible, setProxyVisible] = useState(false);
  const [proxyAccount, setProxyAccount] = useState<AccountDetail | null>(null);
  const [proxyLoading, setProxyLoading] = useState(false);
  const [proxySaving, setProxySaving] = useState(false);
  const [proxyType, setProxyType] = useState<ProxyType>('none');
  const [proxyHost, setProxyHost] = useState('');
  const [proxyPort, setProxyPort] = useState('');
  const [proxyUser, setProxyUser] = useState('');
  const [proxyPass, setProxyPass] = useState('');

  // 2. 消息等待时间
  const [msgExpireVisible, setMsgExpireVisible] = useState(false);
  const [msgExpireAccount, setMsgExpireAccount] = useState<AccountDetail | null>(null);
  const [msgExpireSaving, setMsgExpireSaving] = useState(false);
  const [msgExpireValue, setMsgExpireValue] = useState('');

  // 3. 回复延迟
  const [replyDelayVisible, setReplyDelayVisible] = useState(false);
  const [replyDelayAccount, setReplyDelayAccount] = useState<AccountDetail | null>(null);
  const [replyDelaySaving, setReplyDelaySaving] = useState(false);
  const [replyDelayValue, setReplyDelayValue] = useState('');

  // 4. 人脸验证截图
  const [faceVisible, setFaceVisible] = useState(false);
  const [faceAccount, setFaceAccount] = useState<AccountDetail | null>(null);
  const [faceLoading, setFaceLoading] = useState(false);
  const [faceDeleting, setFaceDeleting] = useState(false);
  const [faceShot, setFaceShot] = useState<FaceVerificationScreenshot | null>(null);

  // 5. 确认收货消息
  const [crVisible, setCrVisible] = useState(false);
  const [crAccount, setCrAccount] = useState<AccountDetail | null>(null);
  const [crLoading, setCrLoading] = useState(false);
  const [crSaving, setCrSaving] = useState(false);
  const [crImgUploading, setCrImgUploading] = useState(false);
  const [crEnabled, setCrEnabled] = useState(false);
  const [crContent, setCrContent] = useState('');
  const [crImage, setCrImage] = useState('');

  // 6. 自动评价
  const [arVisible, setArVisible] = useState(false);
  const [arAccount, setArAccount] = useState<AccountDetail | null>(null);
  const [arLoading, setArLoading] = useState(false);
  const [arSaving, setArSaving] = useState(false);
  const [arEnabled, setArEnabled] = useState(false);
  const [arType, setArType] = useState<'text' | 'api'>('text');
  const [arTextContent, setArTextContent] = useState('');
  const [arApiUrl, setArApiUrl] = useState('');

  // 7. 禁止发货规则
  const [ddVisible, setDdVisible] = useState(false);
  const [ddAccount, setDdAccount] = useState<AccountDetail | null>(null);
  const [ddLoading, setDdLoading] = useState(false);
  const [ddSaving, setDdSaving] = useState(false);
  const [ddRules, setDdRules] = useState<DeliveryBlockRuleItem[]>([]);

  // 8. 退款订单注销
  const [rcVisible, setRcVisible] = useState(false);
  const [rcAccount, setRcAccount] = useState<AccountDetail | null>(null);
  const [rcLoading, setRcLoading] = useState(false);
  const [rcSaving, setRcSaving] = useState(false);
  const [rcEnabled, setRcEnabled] = useState(false);
  const [rcUrl, setRcUrl] = useState('');
  const [rcTimeout, setRcTimeout] = useState('60');

  // 分页游标
  const pageRef = useRef(1);
  const hasMoreRef = useRef(true);
  const loadingMoreRef = useRef(false);
  const loadedRef = useRef(0);
  const totalRef = useRef(0);
  // 同意后发货配置请求序号，丢弃快速关闭/重开时的过期回填
  const agreeReqRef = useRef(0);
  // AI 设置 / 默认回复请求序号，同上
  const aiReqRef = useRef(0);
  const replyReqRef = useRef(0);
  // 高级配置请求序号：代理/人脸/确认收货/自动评价/禁止发货/退款注销 共用，丢弃过期回填
  const advancedReqRef = useRef(0);

  // 客户端筛选：按 tab（在线 / 离线=启用且不在线 / 已禁用）+ 关键词（账号ID/备注）
  const filteredAccounts = useMemo(() => {
    const kw = searchKey.trim().toLowerCase();
    return accounts.filter((a) => {
      if (filterTab === 'online' && !a.online) return false;
      // 离线：启用但未在线；已禁用单独成 tab，避免与离线重叠
      if (filterTab === 'offline' && (a.online || !a.enabled)) return false;
      if (filterTab === 'disabled' && a.enabled) return false;
      if (kw) {
        const id = (a.id || '').toLowerCase();
        const remark = (a.remark || '').toLowerCase();
        if (!id.includes(kw) && !remark.includes(kw)) return false;
      }
      return true;
    });
  }, [accounts, filterTab, searchKey]);

  // 各 tab 计数（基于已加载列表，用于 FilterTabs 角标）
  const filterCounts = useMemo(() => {
    let online = 0;
    let offline = 0;
    let disabled = 0;
    for (const a of accounts) {
      if (!a.enabled) disabled += 1;
      else if (a.online) online += 1;
      else offline += 1;
    }
    return { all: accounts.length, online, offline, disabled };
  }, [accounts]);

  const loadAccounts = useCallback(async (reset: boolean) => {
    if (reset) {
      pageRef.current = 1;
      hasMoreRef.current = true;
      loadedRef.current = 0;
      setRefreshing(true);
    } else {
      if (!hasMoreRef.current || loadingMoreRef.current) return;
      setLoadingMore(true);
      loadingMoreRef.current = true;
    }
    try {
      const page = reset ? 1 : pageRef.current;
      const resp = await getAccountDetailsPaginated(page, PAGE_SIZE);
      totalRef.current = resp.total;
      if (reset) {
        setAccounts(resp.data);
      } else {
        // 去重，避免重复追加
        setAccounts((prev) => {
          const ids = new Set(prev.map((a) => a.pk));
          return [...prev, ...resp.data.filter((a) => !ids.has(a.pk))];
        });
      }
      loadedRef.current += resp.data.length;
      pageRef.current = page + 1;
      hasMoreRef.current =
        resp.data.length > 0 && loadedRef.current < resp.total;
    } catch (e) {
      console.error('加载账号失败', e);
      if (reset) Alert.alert('加载失败', (e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
      loadingMoreRef.current = false;
    }
  }, []);

  useEffect(() => {
    loadAccounts(true);
  }, [loadAccounts]);

  // 以下 handler 仅依赖 setState / ref，用 useCallback 稳定引用，供 AccountCard 的 memo 生效
  const handleToggle = useCallback(async (id: string, currentEnabled: boolean) => {
    try {
      setAccounts((prev) =>
        prev.map((a) => (a.id === id ? { ...a, enabled: !currentEnabled } : a)),
      );
      await toggleAccount(id, !currentEnabled);
    } catch (e) {
      setAccounts((prev) =>
        prev.map((a) => (a.id === id ? { ...a, enabled: currentEnabled } : a)),
      );
      Alert.alert('操作失败', (e as Error).message);
    }
  }, []);

  // ---- 功能开关 ----
  const handleToggleFeature = useCallback(async (accountId: string, key: ToggleKey, currentVal: boolean) => {
    setAccounts((prev) =>
      prev.map((a) => (a.id === accountId ? { ...a, [key]: !currentVal } : a)),
    );
    try {
      await toggleAccountFeature(accountId, key, !currentVal);
    } catch (e) {
      setAccounts((prev) =>
        prev.map((a) => (a.id === accountId ? { ...a, [key]: currentVal } : a)),
      );
      Alert.alert('操作失败', (e as Error).message);
    }
  }, []);

  // ---- 多选 + 批量操作 ----
  const toggleSelect = useCallback((id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }, []);

  function exitMultiSelect() {
    setMultiSelect(false);
    setSelectedIds(new Set());
  }

  async function handleBatch(action: 'enable' | 'disable' | 'clearToken' | 'closeNotice' | 'renew') {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) return;
    setBatchLoading(true);
    try {
      if (action === 'enable') await batchUpdateStatus(ids, true);
      else if (action === 'disable') await batchUpdateStatus(ids, false);
      else if (action === 'clearToken') await batchClearTokenCache(ids);
      else if (action === 'closeNotice') await batchCloseNotice(ids);
      else if (action === 'renew') await batchRenewLogin(ids);
      useAccountsStore.getState().invalidate();
      Alert.alert('成功', `已对 ${ids.length} 个账号执行操作`);
      exitMultiSelect();
      await loadAccounts(true);
    } catch (e) {
      Alert.alert('批量操作失败', (e as Error).message);
    } finally {
      setBatchLoading(false);
    }
  }

  async function handleExport() {
    const ids = multiSelect ? Array.from(selectedIds) : undefined;
    try {
      const blob = await exportAccounts(ids);
      Alert.alert('导出成功', `已导出 ${blob.size} 字节数据`);
    } catch (e) {
      Alert.alert('导出失败', (e as Error).message);
    }
  }

  async function handleImport() {
    try {
      const result = await DocumentPicker.getDocumentAsync({ type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
      if (result.canceled || !result.assets?.[0]) return;
      await importAccounts(result.assets[0].uri);
      useAccountsStore.getState().invalidate();
      Alert.alert('导入成功');
      await loadAccounts(true);
    } catch (e) {
      Alert.alert('导入失败', (e as Error).message);
    }
  }

  // ---- 扫码登录 ----
  async function startQrLogin() {
    setQrVisible(true);
    setQrLoading(true);
    setQrMessage('');
    setQrStatus('loading');
    setQrCompleting(false);
    setQrSession(null);
    try {
      const session = await generateQrLogin();
      setQrSession(session);
      // 后端 generate 不返回 status，二维码已生成 → 设为 ready
      setQrStatus('ready');
    } catch (e) {
      setQrMessage((e as Error).message);
      setQrStatus('error');
    } finally {
      setQrLoading(false);
    }
  }

  function closeQr() {
    setQrVisible(false);
    setQrSession(null);
    setQrCompleting(false);
    setQrMessage('');
    setQrStatus('loading');
  }

  // 轮询扫码状态：基于 session_id 的 effect 驱动，递归 setTimeout 避免并发
  useEffect(() => {
    const sessionId = qrSession?.session_id;
    if (!sessionId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const poll = async () => {
      if (cancelled) return;
      try {
        const status = await checkQrLoginStatus(sessionId);
        if (cancelled) return;
        // 合并而非替换：status 响应可能不含 session_id，保留原值以维持轮询
        setQrSession((prev) => (prev ? { ...prev, ...status } : status));
        setQrStatus(status.status || 'waiting');
        if (status.message) setQrMessage(status.message);

        if (status.status === 'success') {
          setQrCompleting(true);
          try {
            await getQrLoginCookie(sessionId);
          } catch {
            /* 忽略 cookie 拉取错误，刷新列表即可体现结果 */
          }
          if (cancelled) return;
          setQrCompleting(false);
          setQrVisible(false);
          setQrSession(null);
          loadAccounts(true);
          return;
        }
        if (status.status === 'expired' || status.status === 'error') {
          return; // 停止轮询，等待用户刷新
        }
      } catch (e) {
        if (cancelled) return;
        setQrMessage((e as Error).message);
      }
      if (cancelled) return;
      timer = setTimeout(poll, POLL_INTERVAL);
    };

    timer = setTimeout(poll, POLL_INTERVAL);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [qrSession?.session_id, loadAccounts]);

  // ---- 账号编辑 / 删除 ----
  const openEdit = useCallback((account: AccountDetail) => {
    setEditAccount(account);
    setEditRemark(account.remark ?? '');
    setEditCookie(account.cookie ?? '');
    setEditPauseDuration(String(account.pause_duration ?? 0));
    setEditUsername(account.username ?? '');
    setEditPassword(account.login_password ?? '');
    setEditPasswordVisible(false);
    setEditShowBrowser(account.show_browser ?? false);
    setEditVisible(true);
  }, []);

  async function saveEdit() {
    if (!editAccount) return;
    const account = editAccount;
    const remark = editRemark.trim();
    const cookie = editCookie.trim();
    const pauseDuration = Number(editPauseDuration) || 0;
    setEditSaving(true);
    try {
      const tasks: Promise<unknown>[] = [];
      // 备注
      if (remark !== (account.remark ?? '')) {
        tasks.push(updateAccountRemark(account.id, remark));
      }
      // Cookie：仅在非空且变化时更新，避免误清空
      if (cookie && cookie !== (account.cookie ?? '')) {
        tasks.push(updateAccountCookie(account.id, cookie));
      }
      // 暂停时间
      if (pauseDuration !== (account.pause_duration ?? 0)) {
        tasks.push(updateAccountPauseDuration(account.id, pauseDuration));
      }
      // 登录信息（用户名 / 密码 / 显示浏览器）
      const loginInfoChanged =
        editUsername !== (account.username ?? '') ||
        editPassword !== (account.login_password ?? '') ||
        editShowBrowser !== (account.show_browser ?? false);
      if (loginInfoChanged) {
        tasks.push(
          updateAccountLoginInfo(account.id, {
            username: editUsername,
            login_password: editPassword,
            show_browser: editShowBrowser,
          }),
        );
      }
      await Promise.all(tasks);
      setAccounts((prev) =>
        prev.map((a) =>
          a.id === account.id
            ? {
                ...a,
                remark,
                cookie,
                pause_duration: pauseDuration,
                username: editUsername,
                login_password: editPassword,
                show_browser: editShowBrowser,
              }
            : a,
        ),
      );
      setEditVisible(false);
      setEditAccount(null);
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setEditSaving(false);
    }
  }

  const handleDelete = useCallback((account: AccountDetail) => {
    Alert.alert(
      '删除账号',
      `确定删除账号「${account.remark || account.id}」吗？此操作不可恢复。`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteAccount(account.id);
              useAccountsStore.getState().invalidate();
              setAccounts((prev) => prev.filter((a) => a.id !== account.id));
              loadedRef.current = Math.max(0, loadedRef.current - 1);
              if (totalRef.current > 0) totalRef.current -= 1;
            } catch (e) {
              Alert.alert('删除失败', (e as Error).message);
            }
          },
        },
      ],
      { cancelable: true },
    );
  }, []);

  // ---- 同意后发货配置 ----
  const openAgreeConfig = useCallback((account: AccountDetail) => {
    const req = ++agreeReqRef.current;
    setAgreeAccount(account);
    setAgreeEnabled(false);
    setAgreeMessage('');
    setAgreeUrl('');
    setAgreeVisible(true);
    setAgreeLoading(true);
    getAgreeDeliverConfig(account.id)
      .then((cfg) => {
        if (req !== agreeReqRef.current) return;
        setAgreeEnabled(cfg.enabled);
        setAgreeMessage(cfg.notify_message ?? '');
        setAgreeUrl(cfg.pickup_url ?? '');
      })
      .catch((e) => {
        if (req !== agreeReqRef.current) return;
        Alert.alert('加载配置失败', (e as Error).message);
        setAgreeVisible(false);
        setAgreeAccount(null);
      })
      .finally(() => {
        if (req !== agreeReqRef.current) return;
        setAgreeLoading(false);
      });
  }, []);

  function closeAgree() {
    agreeReqRef.current += 1;
    setAgreeVisible(false);
    setAgreeAccount(null);
  }

  async function handleSuggestPickupUrl() {
    setSuggestLoading(true);
    try {
      const s = await getPickupUrlSuggestion();
      if (s?.pickup_url) {
        setAgreeUrl(s.pickup_url);
      } else {
        Alert.alert('未获取到推荐', s?.warning || '暂时没有推荐地址，请手动填写');
      }
    } catch (e) {
      Alert.alert('获取推荐失败', (e as Error).message);
    } finally {
      setSuggestLoading(false);
    }
  }

  async function saveAgreeConfig() {
    if (!agreeAccount) return;
    const url = agreeUrl.trim();
    // 后端约束：enabled=true 时 pickup_url 必填
    if (agreeEnabled && !url) {
      Alert.alert('缺少提货页地址', '开启同意后发货时必须填写提货页地址');
      return;
    }
    setAgreeSaving(true);
    try {
      await updateAgreeDeliverConfig(agreeAccount.id, {
        enabled: agreeEnabled,
        notify_message: agreeMessage.trim(),
        pickup_url: url,
      });
      Alert.alert('成功', '同意后发货配置已保存');
      closeAgree();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setAgreeSaving(false);
    }
  }

  // ---- AI 设置 ----
  const openAiSettings = useCallback((account: AccountDetail) => {
    const req = ++aiReqRef.current;
    setAiAccount(account);
    setAiVisible(true);
    setAiLoading(true);
    setAiEnabled(false);
    setAiProvider('openai_compatible');
    setAiApiUrl('');
    setAiApiKey('');
    setAiModel('');
    setAiBargainRounds('3');
    setAiPrompts('');
    setAiTimeStart('');
    setAiTimeEnd('');
    getAccountAiSettings(account.id)
      .then((s) => {
        if (req !== aiReqRef.current) return;
        const provider = (s.provider_type as AIProviderType) || 'openai_compatible';
        setAiEnabled(s.ai_enabled ?? s.enabled ?? false);
        setAiProvider(provider);
        setAiApiUrl(s.base_url ?? AI_PROVIDER_DEFAULT_BASE_URLS[provider]);
        setAiApiKey(s.api_key ?? '');
        setAiModel(s.model_name ?? '');
        setAiBargainRounds(String(s.max_bargain_rounds ?? 3));
        setAiPrompts(s.custom_prompts ?? '');
        setAiTimeStart(s.ai_time_range_start ?? '');
        setAiTimeEnd(s.ai_time_range_end ?? '');
      })
      .catch((e) => {
        if (req !== aiReqRef.current) return;
        Alert.alert('加载AI设置失败', (e as Error).message);
        setAiVisible(false);
        setAiAccount(null);
      })
      .finally(() => {
        if (req !== aiReqRef.current) return;
        setAiLoading(false);
      });
  }, []);

  function closeAi() {
    aiReqRef.current += 1;
    setAiVisible(false);
    setAiAccount(null);
  }

  function handleAiProviderChange(next: AIProviderType) {
    setAiProvider(next);
    // 仅当前地址为空或仍是其它服务商默认值时联动填充
    const isPrevDefault =
      !aiApiUrl || Object.values(AI_PROVIDER_DEFAULT_BASE_URLS).includes(aiApiUrl);
    if (isPrevDefault) setAiApiUrl(AI_PROVIDER_DEFAULT_BASE_URLS[next]);
  }

  function buildAiSettings(): AIReplySettings {
    return {
      ai_enabled: aiEnabled,
      provider_type: aiProvider,
      base_url: aiApiUrl.trim(),
      api_key: aiApiKey,
      model_name: aiModel.trim(),
      max_bargain_rounds: Number(aiBargainRounds) || 0,
      custom_prompts: aiPrompts,
      ai_time_range_start: aiTimeStart.trim(),
      ai_time_range_end: aiTimeEnd.trim(),
    };
  }

  function aiMissingFields(): string[] {
    const items: string[] = [];
    if (!aiApiUrl.trim()) items.push('API地址');
    if (!aiApiKey.trim()) items.push('API Key');
    if (aiProvider !== 'dashscope_app' && !aiModel.trim()) items.push('模型');
    return items;
  }

  async function saveAiSettings() {
    if (!aiAccount) return;
    if (aiEnabled && aiMissingFields().length > 0) {
      Alert.alert('配置不完整', `请先补全：${aiMissingFields().join('、')}`);
      return;
    }
    setAiSaving(true);
    try {
      const res = await updateAccountAiSettings(aiAccount.id, buildAiSettings());
      if (!res.success) {
        Alert.alert('保存失败', res.message || 'AI配置未填写完整');
        return;
      }
      Alert.alert('成功', 'AI设置已保存');
      closeAi();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setAiSaving(false);
    }
  }

  async function testAiConnection() {
    if (!aiAccount) return;
    if (aiMissingFields().length > 0) {
      Alert.alert('配置不完整', `请先补全：${aiMissingFields().join('、')}`);
      return;
    }
    setAiTesting(true);
    try {
      // 先保存当前输入再测试，确保后端用最新配置发起请求
      const saveRes = await updateAccountAiSettings(aiAccount.id, buildAiSettings());
      if (!saveRes.success) {
        Alert.alert('保存失败', saveRes.message || 'AI配置未填写完整，无法测试');
        return;
      }
      const res = await testAccountAiConnection(aiAccount.id);
      Alert.alert(
        res.success ? '测试成功' : '测试失败',
        res.message || (res.success ? 'AI连接正常' : 'AI连接测试失败'),
      );
    } catch (e) {
      Alert.alert('测试失败', (e as Error).message);
    } finally {
      setAiTesting(false);
    }
  }

  // ---- 默认回复 ----
  const openDefaultReply = useCallback((account: AccountDetail) => {
    const req = ++replyReqRef.current;
    setReplyAccount(account);
    setReplyVisible(true);
    setReplyLoading(true);
    setReplyEnabled(false);
    setReplyType('text');
    setReplyContent('');
    setReplyImage('');
    setReplyApiUrl('');
    setReplyApiTimeout('80');
    setReplyOnce(false);
    getDefaultReply(account.id)
      .then((cfg) => {
        if (req !== replyReqRef.current) return;
        setReplyEnabled(cfg.enabled);
        setReplyType(cfg.reply_type === 'api' ? 'api' : 'text');
        setReplyContent(cfg.reply_content);
        setReplyImage(cfg.reply_image);
        setReplyApiUrl(cfg.api_url);
        setReplyApiTimeout(String(cfg.api_timeout || 80));
        setReplyOnce(cfg.reply_once);
      })
      .catch((e) => {
        if (req !== replyReqRef.current) return;
        Alert.alert('加载默认回复失败', (e as Error).message);
        setReplyVisible(false);
        setReplyAccount(null);
      })
      .finally(() => {
        if (req !== replyReqRef.current) return;
        setReplyLoading(false);
      });
  }, []);

  function closeReply() {
    replyReqRef.current += 1;
    setReplyVisible(false);
    setReplyAccount(null);
  }

  async function pickReplyImage() {
    if (!replyAccount) return;
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: false,
      quality: 0.8,
    });
    if (result.canceled || !result.assets || result.assets.length === 0) return;
    const uri = result.assets[0].uri;
    setReplyImgUploading(true);
    try {
      const url = await uploadDefaultReplyImage(replyAccount.id, uri);
      setReplyImage(url);
      Alert.alert('成功', '图片上传成功');
    } catch (e) {
      Alert.alert('图片上传失败', (e as Error).message);
    } finally {
      setReplyImgUploading(false);
    }
  }

  async function saveDefaultReply() {
    if (!replyAccount) return;
    if (replyType === 'api' && !replyApiUrl.trim()) {
      Alert.alert('缺少API地址', '选择API回复时必须填写API地址');
      return;
    }
    const cfg: DefaultReplyConfig = {
      enabled: replyEnabled,
      reply_type: replyType,
      reply_content: replyContent,
      reply_image: replyImage,
      api_url: replyApiUrl.trim(),
      api_timeout: Number(replyApiTimeout) || 80,
      reply_once: replyOnce,
    };
    setReplySaving(true);
    try {
      const res = await updateDefaultReply(replyAccount.id, cfg);
      if (!res.success) {
        Alert.alert('保存失败', res.message || '保存失败');
        return;
      }
      Alert.alert('成功', '默认回复已保存');
      closeReply();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setReplySaving(false);
    }
  }

  // ==================== 8 项高级配置：open / close / save ====================

  // ---- 1. 代理设置 ----
  function openProxySettings(account: AccountDetail) {
    const req = ++advancedReqRef.current;
    setProxyAccount(account);
    setProxyVisible(true);
    setProxyLoading(true);
    setProxyType('none');
    setProxyHost('');
    setProxyPort('');
    setProxyUser('');
    setProxyPass('');
    getProxyConfig(account.id)
      .then((cfg) => {
        if (req !== advancedReqRef.current) return;
        setProxyType(cfg.proxy_type || 'none');
        setProxyHost(cfg.proxy_host ?? '');
        setProxyPort(cfg.proxy_port != null ? String(cfg.proxy_port) : '');
        setProxyUser(cfg.proxy_user ?? '');
        setProxyPass(cfg.proxy_pass ?? '');
      })
      .catch((e) => {
        if (req !== advancedReqRef.current) return;
        Alert.alert('加载代理配置失败', (e as Error).message);
        setProxyVisible(false);
        setProxyAccount(null);
      })
      .finally(() => {
        if (req !== advancedReqRef.current) return;
        setProxyLoading(false);
      });
  }
  function closeProxy() {
    advancedReqRef.current += 1;
    setProxyVisible(false);
    setProxyAccount(null);
  }
  async function saveProxy() {
    if (!proxyAccount) return;
    if (proxyType !== 'none') {
      if (!proxyHost.trim()) {
        Alert.alert('缺少代理地址', '请输入代理地址');
        return;
      }
      const port = Number(proxyPort);
      if (!proxyPort || !Number.isFinite(port) || port <= 0) {
        Alert.alert('端口无效', '请输入有效的代理端口');
        return;
      }
    }
    setProxySaving(true);
    try {
      const config: ProxyConfig = {
        proxy_type: proxyType,
        proxy_host: proxyType !== 'none' ? proxyHost.trim() : undefined,
        proxy_port: proxyType !== 'none' ? Number(proxyPort) : undefined,
        proxy_user: proxyType !== 'none' && proxyUser.trim() ? proxyUser.trim() : undefined,
        proxy_pass: proxyType !== 'none' && proxyPass ? proxyPass : undefined,
      };
      await updateProxyConfig(proxyAccount.id, config);
      Alert.alert('成功', '代理配置已保存');
      closeProxy();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setProxySaving(false);
    }
  }

  // ---- 2. 消息等待时间 ----
  function openMessageExpireTime(account: AccountDetail) {
    setMsgExpireAccount(account);
    setMsgExpireValue(String(account.message_expire_time ?? 3600));
    setMsgExpireVisible(true);
  }
  function closeMsgExpire() {
    setMsgExpireVisible(false);
    setMsgExpireAccount(null);
  }
  async function saveMsgExpire() {
    if (!msgExpireAccount) return;
    const seconds = Number(msgExpireValue);
    if (!Number.isFinite(seconds) || seconds < 0) {
      Alert.alert('数值无效', '请输入不小于 0 的秒数');
      return;
    }
    setMsgExpireSaving(true);
    try {
      await updateMessageExpireTime(msgExpireAccount.id, Math.floor(seconds));
      Alert.alert('成功', '消息等待时间已保存');
      closeMsgExpire();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setMsgExpireSaving(false);
    }
  }

  // ---- 3. 回复延迟 ----
  function openReplyDelay(account: AccountDetail) {
    setReplyDelayAccount(account);
    setReplyDelayValue(String(account.reply_delay_seconds ?? 0));
    setReplyDelayVisible(true);
  }
  function closeReplyDelayModal() {
    setReplyDelayVisible(false);
    setReplyDelayAccount(null);
  }
  async function saveReplyDelayConfig() {
    if (!replyDelayAccount) return;
    const seconds = Number(replyDelayValue);
    if (!Number.isFinite(seconds) || seconds < 0) {
      Alert.alert('数值无效', '请输入不小于 0 的秒数');
      return;
    }
    setReplyDelaySaving(true);
    try {
      await updateReplyDelay(replyDelayAccount.id, Math.floor(seconds));
      Alert.alert('成功', '回复延迟已保存');
      closeReplyDelayModal();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setReplyDelaySaving(false);
    }
  }

  // ---- 4. 人脸验证截图 ----
  function openFaceVerification(account: AccountDetail) {
    const req = ++advancedReqRef.current;
    setFaceAccount(account);
    setFaceVisible(true);
    setFaceLoading(true);
    setFaceShot(null);
    getFaceVerificationScreenshot(account.id)
      .then((shot) => {
        if (req !== advancedReqRef.current) return;
        setFaceShot(shot);
      })
      .catch((e) => {
        if (req !== advancedReqRef.current) return;
        Alert.alert('获取验证截图失败', (e as Error).message);
      })
      .finally(() => {
        if (req !== advancedReqRef.current) return;
        setFaceLoading(false);
      });
  }
  function closeFace() {
    advancedReqRef.current += 1;
    setFaceVisible(false);
    setFaceAccount(null);
    setFaceShot(null);
  }
  async function deleteFaceShot() {
    if (!faceAccount) return;
    setFaceDeleting(true);
    try {
      await deleteFaceVerificationScreenshot(faceAccount.id);
      setFaceShot(null);
      Alert.alert('成功', '验证截图已删除');
    } catch (e) {
      Alert.alert('删除失败', (e as Error).message);
    } finally {
      setFaceDeleting(false);
    }
  }

  // ---- 5. 确认收货消息 ----
  function openConfirmReceipt(account: AccountDetail) {
    const req = ++advancedReqRef.current;
    setCrAccount(account);
    setCrVisible(true);
    setCrLoading(true);
    setCrEnabled(false);
    setCrContent('');
    setCrImage('');
    getConfirmReceiptMessage(account.id)
      .then((cfg) => {
        if (req !== advancedReqRef.current) return;
        setCrEnabled(cfg.enabled);
        setCrContent(cfg.message_content);
        setCrImage(cfg.message_image);
      })
      .catch((e) => {
        if (req !== advancedReqRef.current) return;
        Alert.alert('加载配置失败', (e as Error).message);
        setCrVisible(false);
        setCrAccount(null);
      })
      .finally(() => {
        if (req !== advancedReqRef.current) return;
        setCrLoading(false);
      });
  }
  function closeCr() {
    advancedReqRef.current += 1;
    setCrVisible(false);
    setCrAccount(null);
  }
  async function pickCrImage() {
    if (!crAccount) return;
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      allowsEditing: false,
      quality: 0.8,
    });
    if (result.canceled || !result.assets || result.assets.length === 0) return;
    const uri = result.assets[0].uri;
    setCrImgUploading(true);
    try {
      const url = await uploadConfirmReceiptImage(crAccount.id, uri);
      setCrImage(url);
      Alert.alert('成功', '图片上传成功');
    } catch (e) {
      Alert.alert('图片上传失败', (e as Error).message);
    } finally {
      setCrImgUploading(false);
    }
  }
  async function saveConfirmReceipt() {
    if (!crAccount) return;
    const cfg: ConfirmReceiptConfig = {
      enabled: crEnabled,
      message_content: crContent,
      message_image: crImage,
    };
    setCrSaving(true);
    try {
      await updateConfirmReceiptMessage(crAccount.id, cfg);
      Alert.alert('成功', '确认收货消息已保存');
      closeCr();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setCrSaving(false);
    }
  }

  // ---- 6. 自动评价 ----
  function openAutoRate(account: AccountDetail) {
    const req = ++advancedReqRef.current;
    setArAccount(account);
    setArVisible(true);
    setArLoading(true);
    setArEnabled(false);
    setArType('text');
    setArTextContent('不错的买家');
    setArApiUrl('');
    getAutoRateConfig(account.id)
      .then((cfg) => {
        if (req !== advancedReqRef.current) return;
        setArEnabled(cfg.enabled);
        setArType(cfg.rate_type === 'api' ? 'api' : 'text');
        setArTextContent(cfg.text_content || '不错的买家');
        setArApiUrl(cfg.api_url || '');
      })
      .catch((e) => {
        if (req !== advancedReqRef.current) return;
        Alert.alert('加载配置失败', (e as Error).message);
        setArVisible(false);
        setArAccount(null);
      })
      .finally(() => {
        if (req !== advancedReqRef.current) return;
        setArLoading(false);
      });
  }
  function closeAr() {
    advancedReqRef.current += 1;
    setArVisible(false);
    setArAccount(null);
  }
  async function saveAutoRate() {
    if (!arAccount) return;
    if (arEnabled) {
      if (arType === 'text' && !arTextContent.trim()) {
        Alert.alert('缺少评价内容', '请填写评价内容');
        return;
      }
      if (arType === 'api' && !arApiUrl.trim()) {
        Alert.alert('缺少API地址', '请填写API地址');
        return;
      }
    }
    const cfg: AutoRateConfig = {
      enabled: arEnabled,
      rate_type: arType,
      text_content: arTextContent,
      api_url: arApiUrl.trim(),
    };
    setArSaving(true);
    try {
      await updateAutoRateConfig(arAccount.id, cfg);
      Alert.alert('成功', '自动评价配置已保存');
      closeAr();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setArSaving(false);
    }
  }

  // ---- 7. 禁止发货规则 ----
  function openDeliveryDisabled(account: AccountDetail) {
    const req = ++advancedReqRef.current;
    setDdAccount(account);
    setDdVisible(true);
    setDdLoading(true);
    setDdRules([]);
    getDeliveryBlockRules(account.id)
      .then((rules) => {
        if (req !== advancedReqRef.current) return;
        setDdRules(rules);
      })
      .catch((e) => {
        if (req !== advancedReqRef.current) return;
        Alert.alert('加载规则失败', (e as Error).message);
        setDdVisible(false);
        setDdAccount(null);
      })
      .finally(() => {
        if (req !== advancedReqRef.current) return;
        setDdLoading(false);
      });
  }
  function closeDd() {
    advancedReqRef.current += 1;
    setDdVisible(false);
    setDdAccount(null);
    setDdRules([]);
  }
  // 更新单条规则字段；联动：关闭主动关闭订单时"关闭后只发卡券"强制关
  function updateDdRule(ruleCode: string, updates: Partial<DeliveryBlockRuleItem>) {
    setDdRules((prev) =>
      prev.map((r) => {
        if (r.rule_code !== ruleCode) return r;
        const updated = { ...r, ...updates };
        if ('auto_close_order' in updates && !updates.auto_close_order) {
          updated.only_card_after_close = false;
        }
        return updated;
      }),
    );
  }
  async function saveDeliveryDisabled() {
    if (!ddAccount) return;
    for (const rule of ddRules) {
      if (rule.enabled && rule.block_reason && rule.block_reason.length > 500) {
        Alert.alert('原因过长', `规则「${rule.rule_name}」的禁止发货原因不能超过500字`);
        return;
      }
    }
    setDdSaving(true);
    try {
      const payload: DeliveryBlockRulePayload[] = ddRules.map((r) => ({
        rule_code: r.rule_code,
        enabled: r.enabled,
        priority: r.priority,
        block_reason: r.enabled ? (r.block_reason.trim() || null) : null,
        auto_close_order: r.enabled ? r.auto_close_order : false,
        only_card_after_close:
          r.enabled && r.auto_close_order ? r.only_card_after_close : false,
        excluded_item_ids: r.enabled ? r.excluded_item_ids.filter(Boolean) : [],
        config: r.config ?? null,
      }));
      await updateDeliveryBlockRules(ddAccount.id, payload);
      Alert.alert('成功', '禁止发货规则已保存');
      closeDd();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setDdSaving(false);
    }
  }

  // ---- 8. 退款订单注销 ----
  function openRefundCancel(account: AccountDetail) {
    const req = ++advancedReqRef.current;
    setRcAccount(account);
    setRcVisible(true);
    setRcLoading(true);
    setRcEnabled(false);
    setRcUrl('');
    setRcTimeout('60');
    getRefundCancelConfig(account.id)
      .then((cfg) => {
        if (req !== advancedReqRef.current) return;
        setRcEnabled(cfg.enabled);
        setRcUrl(cfg.url ?? '');
        setRcTimeout(String(cfg.timeout ?? 60));
      })
      .catch((e) => {
        if (req !== advancedReqRef.current) return;
        Alert.alert('加载配置失败', (e as Error).message);
        setRcVisible(false);
        setRcAccount(null);
      })
      .finally(() => {
        if (req !== advancedReqRef.current) return;
        setRcLoading(false);
      });
  }
  function closeRc() {
    advancedReqRef.current += 1;
    setRcVisible(false);
    setRcAccount(null);
  }
  async function saveRefundCancel() {
    if (!rcAccount) return;
    if (rcEnabled && !rcUrl.trim()) {
      Alert.alert('缺少请求URL', '开启退款订单注销时，请求URL不能为空');
      return;
    }
    if (rcEnabled && !/^https?:\/\//i.test(rcUrl.trim())) {
      Alert.alert('URL无效', '请求URL必须以 http:// 或 https:// 开头');
      return;
    }
    const timeoutNum = Number(rcTimeout);
    if (!Number.isFinite(timeoutNum) || timeoutNum < 1) {
      Alert.alert('超时无效', '超时时间请输入大于 0 的秒数');
      return;
    }
    const cfg: RefundCancelConfig = {
      enabled: rcEnabled,
      url: rcEnabled ? rcUrl.trim() : null,
      timeout: Math.floor(timeoutNum),
    };
    setRcSaving(true);
    try {
      await updateRefundCancelConfig(rcAccount.id, cfg);
      Alert.alert('成功', '退款订单注销配置已保存');
      closeRc();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setRcSaving(false);
    }
  }

  // 高级配置开启 dispatcher：通过 ref 间接调用，保证 handleOpenAdvanced 引用稳定
  const openAdvancedImpl = (account: AccountDetail, key: AdvancedConfigKey) => {
    switch (key) {
      case 'proxy': openProxySettings(account); break;
      case 'messageExpireTime': openMessageExpireTime(account); break;
      case 'replyDelay': openReplyDelay(account); break;
      case 'faceVerification': openFaceVerification(account); break;
      case 'confirmReceipt': openConfirmReceipt(account); break;
      case 'autoRate': openAutoRate(account); break;
      case 'deliveryDisabled': openDeliveryDisabled(account); break;
      case 'refundCancel': openRefundCancel(account); break;
    }
  };
  const openAdvancedRef = useRef(openAdvancedImpl);
  openAdvancedRef.current = openAdvancedImpl;
  const handleOpenAdvanced = useCallback(
    (account: AccountDetail, key: AdvancedConfigKey) => {
      openAdvancedRef.current(account, key);
    },
    [],
  );

  // ---- 列表项稳定回调（配合 AccountCard 的 memo）----
  const handleCardPress = useCallback(
    (item: AccountDetail) => {
      if (multiSelect) toggleSelect(item.id);
    },
    [multiSelect, toggleSelect],
  );

  const handleCardLongPress = useCallback(
    (item: AccountDetail) => {
      if (!multiSelect) setMultiSelect(true);
      toggleSelect(item.id);
    },
    [multiSelect, toggleSelect],
  );

  // 函数式更新读取当前展开项，避免依赖 expandedPk 导致引用变化
  const handleCardToggleExpand = useCallback((pk: number) => {
    setExpandedPk((prev) => (prev === pk ? null : pk));
  }, []);

  const handleCardPasswordLogin = useCallback((account: AccountDetail) => {
    setPwdLoginAccount(account);
  }, []);

  const renderItem = useCallback<ListRenderItem<AccountDetail>>(
    ({ item }) => (
      <AccountCard
        item={item}
        c={c}
        multiSelect={multiSelect}
        selected={selectedIds.has(item.id)}
        expanded={expandedPk === item.pk}
        onPress={handleCardPress}
        onLongPress={handleCardLongPress}
        onToggle={handleToggle}
        onToggleFeature={handleToggleFeature}
        onEdit={openEdit}
        onDelete={handleDelete}
        onPasswordLogin={handleCardPasswordLogin}
        onToggleExpand={handleCardToggleExpand}
        onOpenAgreeConfig={openAgreeConfig}
        onOpenAiSettings={openAiSettings}
        onOpenDefaultReply={openDefaultReply}
        onOpenAdvanced={handleOpenAdvanced}
      />
    ),
    [
      c,
      multiSelect,
      selectedIds,
      expandedPk,
      handleCardPress,
      handleCardLongPress,
      handleToggle,
      handleToggleFeature,
      openEdit,
      handleDelete,
      handleCardPasswordLogin,
      handleCardToggleExpand,
      openAgreeConfig,
      openAiSettings,
      openDefaultReply,
      handleOpenAdvanced,
    ],
  );

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载账号..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <Button label="导入" onPress={handleImport} variant="secondary" />
      </View>

      {/* 筛选：状态 tab + 搜索（客户端过滤已加载列表） */}
      <FilterTabs
        tabs={FILTER_TABS.map((t) => ({ ...t, count: filterCounts[t.key] }))}
        active={filterTab}
        onChange={(k) => setFilterTab(k as AccountFilter)}
      />
      <View style={styles.searchWrap}>
        <Input
          value={searchKey}
          onChangeText={setSearchKey}
          placeholder="搜索账号ID/备注"
          autoCapitalize="none"
          autoCorrect={false}
        />
      </View>

      {/* 多选工具栏 */}
      {multiSelect && (
        <View style={[styles.batchBar, { backgroundColor: c.surface, borderBottomColor: c.border }]}>
          <Text style={[styles.batchCount, { color: c.text }]}>已选 {selectedIds.size} 个</Text>
          <View style={{ flexDirection: 'row', gap: spacing.xs, flexWrap: 'wrap' }}>
            <Button label="启用" onPress={() => handleBatch('enable')} variant="secondary" style={styles.batchBtn} />
            <Button label="禁用" onPress={() => handleBatch('disable')} variant="secondary" style={styles.batchBtn} />
            <Button label="清Token" onPress={() => handleBatch('clearToken')} variant="secondary" style={styles.batchBtn} />
            <Button label="关通知" onPress={() => handleBatch('closeNotice')} variant="secondary" style={styles.batchBtn} />
            <Button label="续期" onPress={() => handleBatch('renew')} variant="secondary" style={styles.batchBtn} />
            <Button label="导出" onPress={handleExport} variant="secondary" style={styles.batchBtn} />
            <Button label="取消" onPress={exitMultiSelect} variant="danger" style={styles.batchBtn} />
          </View>
        </View>
      )}

      <FlatList
        data={filteredAccounts}
        keyExtractor={(item) => String(item.pk)}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={() => loadAccounts(true)} />
        }
        onEndReached={() => {
          if (loading || refreshing || loadingMore) return;
          loadAccounts(false);
        }}
        onEndReachedThreshold={0.3}
        renderItem={renderItem}
        windowSize={7}
        removeClippedSubviews
        ListEmptyComponent={
          accounts.length > 0 ? (
            <View style={styles.empty}>
              <Text style={[styles.emptyText, { color: c.textMuted }]}>
                没有匹配的账号
              </Text>
            </View>
          ) : (
            <View style={styles.empty}>
              <Text style={[styles.emptyText, { color: c.textMuted }]}>
                暂无账号，请添加
              </Text>
            </View>
          )
        }
        ListFooterComponent={
          loadingMore ? (
            <Text style={[styles.loadingMore, { color: c.textMuted }]}>加载中...</Text>
          ) : null
        }
        contentContainerStyle={styles.listContent}
      />

      <FAB label="添加账号" onPress={startQrLogin} />

      {/* 扫码登录 Modal */}
      <Modal
        visible={qrVisible}
        transparent
        animationType="fade"
        onRequestClose={closeQr}
      >
        <Pressable style={styles.modalOverlay} onPress={closeQr}>
          <Pressable
            style={[styles.modalCard, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>扫码登录</Text>
              <Pressable onPress={closeQr} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>

            <View style={styles.qrContainer}>
              {qrCompleting ? (
                <>
                  <ActivityIndicator size="large" color={c.primary} />
                  <Text style={[styles.qrHint, { color: c.textSecondary }]}>
                    登录成功，正在保存...
                  </Text>
                </>
              ) : qrLoading ? (
                <>
                  <ActivityIndicator size="large" color={c.primary} />
                  <Text style={[styles.qrHint, { color: c.textSecondary }]}>
                    正在生成二维码...
                  </Text>
                </>
              ) : qrStatus === 'expired' ? (
                <View style={styles.qrPlaceholder}>
                  <Text style={[styles.qrPlaceholderText, { color: c.textMuted }]}>
                    二维码已过期
                  </Text>
                  <Button label="点击刷新" onPress={startQrLogin} variant="secondary" />
                </View>
              ) : qrStatus === 'error' ? (
                <View style={styles.qrPlaceholder}>
                  <Text style={[styles.qrPlaceholderText, { color: c.error }]}>
                    {qrMessage || '生成失败，请重试'}
                  </Text>
                  <Button label="重试" onPress={startQrLogin} variant="secondary" />
                </View>
              ) : qrStatus === 'verification_required' && qrSession?.face_qr_url ? (
                <>
                  <View style={styles.qrBox}>
                    <Image source={{ uri: qrSession.face_qr_url }} style={styles.qrImage} resizeMode="contain" />
                  </View>
                  <Text style={[styles.qrHint, { color: c.warning }]}>
                    需要人脸验证，请扫描二维码完成验证
                  </Text>
                </>
              ) : qrSession?.qr_code_url ? (
                <>
                  <View style={styles.qrBox}>
                    <Image source={{ uri: qrSession.qr_code_url }} style={styles.qrImage} resizeMode="contain" />
                  </View>
                  <Text style={[styles.qrHint, { color: c.textSecondary }]}>
                    {statusLabel(qrStatus)}
                  </Text>
                </>
              ) : (
                <>
                  <ActivityIndicator size="large" color={c.primary} />
                  <Text style={[styles.qrHint, { color: c.textSecondary }]}>
                    等待生成...
                  </Text>
                </>
              )}
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      {/* 编辑备注 Modal */}
      <Modal
        visible={editVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setEditVisible(false)}
      >
        <Pressable style={styles.modalOverlay} onPress={() => setEditVisible(false)}>
          <Pressable
            style={[styles.modalCard, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>编辑账号</Text>
              <Pressable onPress={() => setEditVisible(false)} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>

            <ScrollView
              style={styles.editScroll}
              contentContainerStyle={styles.editBody}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>备注</Text>
                <Input
                  value={editRemark}
                  onChangeText={setEditRemark}
                  placeholder="请输入备注名称"
                  autoFocus
                  maxLength={50}
                />
              </View>

              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>Cookie</Text>
                <Input
                  value={editCookie}
                  onChangeText={setEditCookie}
                  placeholder="粘贴账号 Cookie"
                  multiline
                  autoCapitalize="none"
                  autoCorrect={false}
                  style={[
                    styles.editTextarea,
                    { backgroundColor: c.background, color: c.text, borderColor: c.border },
                  ]}
                />
              </View>

              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>暂停时间(秒)</Text>
                <Input
                  value={editPauseDuration}
                  onChangeText={setEditPauseDuration}
                  placeholder="0"
                  keyboardType="number-pad"
                />
              </View>

              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>登录信息</Text>
                <Input
                  value={editUsername}
                  onChangeText={setEditUsername}
                  placeholder="登录用户名"
                  autoCapitalize="none"
                  autoCorrect={false}
                />
                <View style={styles.pwdWrap}>
                  <Input
                    value={editPassword}
                    onChangeText={setEditPassword}
                    placeholder="登录密码"
                    secureTextEntry={!editPasswordVisible}
                    autoCapitalize="none"
                    autoCorrect={false}
                  />
                  <Pressable
                    onPress={() => setEditPasswordVisible((v) => !v)}
                    hitSlop={8}
                    style={styles.pwdToggle}
                  >
                    {editPasswordVisible ? (
                      <EyeOff size={18} stroke={c.textMuted} />
                    ) : (
                      <Eye size={18} stroke={c.textMuted} />
                    )}
                  </Pressable>
                </View>
                <View style={[styles.switchRow, { borderTopColor: c.borderLight }]}>
                  <Text style={[styles.switchLabel, { color: c.text }]}>显示浏览器</Text>
                  <Switch
                    value={editShowBrowser}
                    onValueChange={setEditShowBrowser}
                    trackColor={{ false: c.border, true: c.primary }}
                    thumbColor="#FFFFFF"
                  />
                </View>
              </View>
            </ScrollView>

            <View style={styles.modalActions}>
              <Button
                label="取消"
                variant="ghost"
                onPress={() => setEditVisible(false)}
                style={styles.modalBtn}
              />
              <Button
                label="保存"
                onPress={saveEdit}
                loading={editSaving}
                disabled={editSaving}
                style={styles.modalBtn}
              />
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      {/* 同意后发货配置 Modal */}
      <Modal
        visible={agreeVisible}
        transparent
        animationType="fade"
        onRequestClose={closeAgree}
      >
        <Pressable style={styles.modalOverlay} onPress={closeAgree}>
          <Pressable
            style={[styles.modalCard, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>同意后发货</Text>
              <Pressable onPress={closeAgree} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>

            {agreeLoading ? (
              <View style={styles.agreeLoadingBox}>
                <ActivityIndicator size="large" color={c.primary} />
                <Text style={[styles.agreeLoadingText, { color: c.textSecondary }]}>
                  加载配置中...
                </Text>
              </View>
            ) : (
              <>
                <View style={styles.toggleRow}>
                  <Text style={[styles.toggleLabel, { color: c.text }]}>开启</Text>
                  <Switch
                    value={agreeEnabled}
                    onValueChange={setAgreeEnabled}
                    trackColor={{ false: c.border, true: c.primary }}
                    thumbColor="#FFFFFF"
                  />
                </View>

                <View style={styles.fieldGroup}>
                  <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>通知话术</Text>
                  <Input
                    value={agreeMessage}
                    onChangeText={setAgreeMessage}
                    placeholder="买家下单后收到的通知内容"
                    multiline
                    style={styles.agreeTextarea}
                  />
                </View>

                <View style={styles.fieldGroup}>
                  <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>提货页地址</Text>
                  <View style={styles.agreeUrlRow}>
                    <Input
                      value={agreeUrl}
                      onChangeText={setAgreeUrl}
                      placeholder="https://..."
                      autoCapitalize="none"
                      keyboardType="url"
                      style={styles.agreeUrlInput}
                    />
                    <Button
                      label="获取推荐"
                      variant="secondary"
                      onPress={handleSuggestPickupUrl}
                      loading={suggestLoading}
                      style={styles.agreeSuggestBtn}
                    />
                  </View>
                  {agreeEnabled && !agreeUrl.trim() ? (
                    <Text style={[styles.agreeUrlHint, { color: c.warning }]}>
                      开启后必须填写提货页地址
                    </Text>
                  ) : null}
                </View>

                <View style={styles.modalActions}>
                  <Button
                    label="取消"
                    variant="ghost"
                    onPress={closeAgree}
                    style={styles.modalBtn}
                  />
                  <Button
                    label="保存"
                    onPress={saveAgreeConfig}
                    loading={agreeSaving}
                    disabled={agreeSaving}
                    style={styles.modalBtn}
                  />
                </View>
              </>
            )}
          </Pressable>
        </Pressable>
      </Modal>

      {/* AI 设置 Modal */}
      <FormModal
        visible={aiVisible}
        onClose={closeAi}
        title="AI设置"
        contentStyle={styles.configSheet}
      >
        {aiLoading ? (
          <View style={styles.configLoadingBox}>
            <ActivityIndicator size="large" color={c.primary} />
            <Text style={[styles.configLoadingText, { color: c.textSecondary }]}>
              加载配置中...
            </Text>
          </View>
        ) : (
          <>
            <ScrollView
              style={styles.configScroll}
              contentContainerStyle={styles.configBody}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              <View style={[styles.switchRow, { borderTopColor: c.borderLight }]}>
                <Text style={[styles.switchLabel, { color: c.text }]}>开启AI回复</Text>
                <Switch
                  value={aiEnabled}
                  onValueChange={setAiEnabled}
                  trackColor={{ false: c.border, true: c.primary }}
                  thumbColor="#FFFFFF"
                />
              </View>

              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>服务商</Text>
                <View style={styles.chipRow}>
                  {AI_PROVIDER_OPTIONS.map((opt) => {
                    const active = aiProvider === opt.value;
                    return (
                      <Pressable
                        key={opt.value}
                        onPress={() => handleAiProviderChange(opt.value)}
                        style={[
                          styles.chip,
                          {
                            backgroundColor: active ? c.primary : c.background,
                            borderColor: active ? c.primary : c.border,
                          },
                        ]}
                      >
                        <Text
                          style={[styles.chipText, { color: active ? '#FFFFFF' : c.text }]}
                        >
                          {opt.label}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              </View>

              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>API地址</Text>
                <Input
                  value={aiApiUrl}
                  onChangeText={setAiApiUrl}
                  placeholder="https://..."
                  autoCapitalize="none"
                  autoCorrect={false}
                  keyboardType="url"
                />
              </View>

              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>API Key</Text>
                <Input
                  value={aiApiKey}
                  onChangeText={setAiApiKey}
                  placeholder="sk-..."
                  secureTextEntry
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>

              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>模型</Text>
                <Input
                  value={aiModel}
                  onChangeText={setAiModel}
                  placeholder="如 qwen-plus"
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>

              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>砍价轮数</Text>
                <Input
                  value={aiBargainRounds}
                  onChangeText={setAiBargainRounds}
                  placeholder="3"
                  keyboardType="number-pad"
                />
              </View>

              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>自定义提示词</Text>
                <Input
                  value={aiPrompts}
                  onChangeText={setAiPrompts}
                  placeholder="补充给AI的额外话术..."
                  multiline
                  style={styles.textarea}
                />
              </View>

              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>回复时间段</Text>
                <View style={styles.timeRow}>
                  <Input
                    value={aiTimeStart}
                    onChangeText={setAiTimeStart}
                    placeholder="08:00"
                    keyboardType="numbers-and-punctuation"
                    style={styles.timeInput}
                  />
                  <Text style={[styles.timeSep, { color: c.textMuted }]}>~</Text>
                  <Input
                    value={aiTimeEnd}
                    onChangeText={setAiTimeEnd}
                    placeholder="22:00"
                    keyboardType="numbers-and-punctuation"
                    style={styles.timeInput}
                  />
                </View>
              </View>
            </ScrollView>

            <View style={styles.configActions}>
              <Button
                label="测试连接"
                variant="secondary"
                onPress={testAiConnection}
                loading={aiTesting}
                disabled={aiTesting}
                style={styles.configBtn}
              />
              <Button
                label="保存"
                onPress={saveAiSettings}
                loading={aiSaving}
                disabled={aiSaving}
                style={styles.configBtn}
              />
            </View>
          </>
        )}
      </FormModal>

      {/* 默认回复 Modal */}
      <FormModal
        visible={replyVisible}
        onClose={closeReply}
        title="默认回复"
        contentStyle={styles.configSheet}
      >
        {replyLoading ? (
          <View style={styles.configLoadingBox}>
            <ActivityIndicator size="large" color={c.primary} />
            <Text style={[styles.configLoadingText, { color: c.textSecondary }]}>
              加载配置中...
            </Text>
          </View>
        ) : (
          <>
            <ScrollView
              style={styles.configScroll}
              contentContainerStyle={styles.configBody}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              <View style={[styles.switchRow, { borderTopColor: c.borderLight }]}>
                <Text style={[styles.switchLabel, { color: c.text }]}>开启</Text>
                <Switch
                  value={replyEnabled}
                  onValueChange={setReplyEnabled}
                  trackColor={{ false: c.border, true: c.primary }}
                  thumbColor="#FFFFFF"
                />
              </View>

              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>回复类型</Text>
                <View style={styles.chipRow}>
                  {([
                    { value: 'text', label: '文本' },
                    { value: 'api', label: 'API' },
                  ] as const).map((opt) => {
                    const active = replyType === opt.value;
                    return (
                      <Pressable
                        key={opt.value}
                        onPress={() => setReplyType(opt.value)}
                        style={[
                          styles.chip,
                          {
                            backgroundColor: active ? c.primary : c.background,
                            borderColor: active ? c.primary : c.border,
                          },
                        ]}
                      >
                        <Text style={[styles.chipText, { color: active ? '#FFFFFF' : c.text }]}>
                          {opt.label}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              </View>

              {replyType === 'text' ? (
                <View style={styles.fieldGroup}>
                  <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>回复文本</Text>
                  <Input
                    value={replyContent}
                    onChangeText={setReplyContent}
                    placeholder="未命中关键词时的默认回复..."
                    multiline
                    style={styles.textarea}
                  />
                </View>
              ) : (
                <>
                  <View style={styles.fieldGroup}>
                    <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>API 地址</Text>
                    <Input
                      value={replyApiUrl}
                      onChangeText={setReplyApiUrl}
                      placeholder="https://..."
                      autoCapitalize="none"
                      autoCorrect={false}
                      keyboardType="url"
                    />
                  </View>
                  <View style={styles.fieldGroup}>
                    <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>超时(秒)</Text>
                    <Input
                      value={replyApiTimeout}
                      onChangeText={setReplyApiTimeout}
                      placeholder="80"
                      keyboardType="number-pad"
                    />
                  </View>
                </>
              )}

              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>回复图片</Text>
                <View style={styles.imageRow}>
                  <Button
                    label={replyImage ? '重新选择' : '选择图片'}
                    variant="secondary"
                    onPress={pickReplyImage}
                    loading={replyImgUploading}
                    disabled={replyImgUploading}
                    style={styles.imageBtn}
                  />
                  {replyImage ? (
                    <Pressable onPress={() => setReplyImage('')} hitSlop={8}>
                      <Text style={[styles.clearLink, { color: c.error }]}>清除</Text>
                    </Pressable>
                  ) : null}
                </View>
                {replyImage ? (
                  <Text style={[styles.imageUrl, { color: c.textMuted }]} numberOfLines={1}>
                    {replyImage}
                  </Text>
                ) : null}
              </View>

              <View style={[styles.switchRow, { borderTopColor: c.borderLight }]}>
                <Text style={[styles.switchLabel, { color: c.text }]}>仅回复一次</Text>
                <Switch
                  value={replyOnce}
                  onValueChange={setReplyOnce}
                  trackColor={{ false: c.border, true: c.primary }}
                  thumbColor="#FFFFFF"
                />
              </View>
            </ScrollView>

            <View style={styles.configActions}>
              <Button
                label="保存"
                onPress={saveDefaultReply}
                loading={replySaving}
                disabled={replySaving}
                style={styles.configBtn}
              />
            </View>
          </>
        )}
      </FormModal>

      {/* 代理设置 Modal */}
      <FormModal
        visible={proxyVisible}
        onClose={closeProxy}
        title="代理设置"
        contentStyle={styles.configSheet}
      >
        {proxyLoading ? (
          <View style={styles.configLoadingBox}>
            <ActivityIndicator size="large" color={c.primary} />
            <Text style={[styles.configLoadingText, { color: c.textSecondary }]}>
              加载配置中...
            </Text>
          </View>
        ) : (
          <>
            <ScrollView
              style={styles.configScroll}
              contentContainerStyle={styles.configBody}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>代理类型</Text>
                <View style={styles.chipRow}>
                  {([
                    { value: 'none', label: '不使用' },
                    { value: 'http', label: 'HTTP' },
                    { value: 'https', label: 'HTTPS' },
                    { value: 'socks5', label: 'SOCKS5' },
                  ] as const).map((opt) => {
                    const active = proxyType === opt.value;
                    return (
                      <Pressable
                        key={opt.value}
                        onPress={() => setProxyType(opt.value)}
                        style={[
                          styles.chip,
                          {
                            backgroundColor: active ? c.primary : c.background,
                            borderColor: active ? c.primary : c.border,
                          },
                        ]}
                      >
                        <Text style={[styles.chipText, { color: active ? '#FFFFFF' : c.text }]}>
                          {opt.label}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              </View>

              {proxyType !== 'none' && (
                <>
                  <View style={styles.fieldGroup}>
                    <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>代理地址</Text>
                    <Input
                      value={proxyHost}
                      onChangeText={setProxyHost}
                      placeholder="如 127.0.0.1"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>
                  <View style={styles.fieldGroup}>
                    <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>端口</Text>
                    <Input
                      value={proxyPort}
                      onChangeText={setProxyPort}
                      placeholder="如 7890"
                      keyboardType="number-pad"
                    />
                  </View>
                  <View style={styles.fieldGroup}>
                    <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>用户名(可选)</Text>
                    <Input
                      value={proxyUser}
                      onChangeText={setProxyUser}
                      placeholder="留空表示不认证"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>
                  <View style={styles.fieldGroup}>
                    <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>密码(可选)</Text>
                    <Input
                      value={proxyPass}
                      onChangeText={setProxyPass}
                      placeholder="留空表示不认证"
                      secureTextEntry
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>
                </>
              )}
            </ScrollView>
            <View style={styles.configActions}>
              <Button
                label="保存"
                onPress={saveProxy}
                loading={proxySaving}
                disabled={proxySaving}
                style={styles.configBtn}
              />
            </View>
          </>
        )}
      </FormModal>

      {/* 消息等待时间 Modal */}
      <FormModal
        visible={msgExpireVisible}
        onClose={closeMsgExpire}
        title="消息等待时间"
        contentStyle={styles.configSheet}
      >
        <View style={styles.configBody}>
          <View style={styles.fieldGroup}>
            <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>相同消息等待时间(秒)</Text>
            <Input
              value={msgExpireValue}
              onChangeText={setMsgExpireValue}
              placeholder="3600"
              keyboardType="number-pad"
            />
            <Text style={[styles.hintText, { color: c.textMuted }]}>
              在此时间内收到相同消息将不再重复回复，0 表示不限制
            </Text>
          </View>
        </View>
        <View style={styles.configActions}>
          <Button
            label="保存"
            onPress={saveMsgExpire}
            loading={msgExpireSaving}
            disabled={msgExpireSaving}
            style={styles.configBtn}
          />
        </View>
      </FormModal>

      {/* 回复延迟 Modal */}
      <FormModal
        visible={replyDelayVisible}
        onClose={closeReplyDelayModal}
        title="回复延迟"
        contentStyle={styles.configSheet}
      >
        <View style={styles.configBody}>
          <View style={styles.fieldGroup}>
            <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>自动回复延迟(秒)</Text>
            <Input
              value={replyDelayValue}
              onChangeText={setReplyDelayValue}
              placeholder="0"
              keyboardType="number-pad"
            />
            <Text style={[styles.hintText, { color: c.textMuted }]}>
              收到消息后延迟若干秒再回复，0 表示立即回复
            </Text>
          </View>
        </View>
        <View style={styles.configActions}>
          <Button
            label="保存"
            onPress={saveReplyDelayConfig}
            loading={replyDelaySaving}
            disabled={replyDelaySaving}
            style={styles.configBtn}
          />
        </View>
      </FormModal>

      {/* 人脸验证截图 Modal */}
      <FormModal
        visible={faceVisible}
        onClose={closeFace}
        title="人脸验证截图"
        contentStyle={styles.configSheet}
      >
        {faceLoading ? (
          <View style={styles.configLoadingBox}>
            <ActivityIndicator size="large" color={c.primary} />
            <Text style={[styles.configLoadingText, { color: c.textSecondary }]}>
              加载中...
            </Text>
          </View>
        ) : faceShot ? (
          <View style={styles.configBody}>
            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>文件名</Text>
              <Text style={[styles.faceValue, { color: c.text }]}>{faceShot.filename}</Text>
            </View>
            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>创建时间</Text>
              <Text style={[styles.faceValue, { color: c.text }]}>{faceShot.created_time_str}</Text>
            </View>
            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>大小(字节)</Text>
              <Text style={[styles.faceValue, { color: c.text }]}>{faceShot.size}</Text>
            </View>
            <View style={styles.configActions}>
              <Button
                label="删除截图"
                variant="danger"
                onPress={deleteFaceShot}
                loading={faceDeleting}
                disabled={faceDeleting}
                style={styles.configBtn}
              />
            </View>
          </View>
        ) : (
          <View style={styles.configLoadingBox}>
            <Text style={[styles.configLoadingText, { color: c.textMuted }]}>
              暂无验证截图
            </Text>
          </View>
        )}
      </FormModal>

      {/* 确认收货消息 Modal */}
      <FormModal
        visible={crVisible}
        onClose={closeCr}
        title="确认收货消息"
        contentStyle={styles.configSheet}
      >
        {crLoading ? (
          <View style={styles.configLoadingBox}>
            <ActivityIndicator size="large" color={c.primary} />
            <Text style={[styles.configLoadingText, { color: c.textSecondary }]}>
              加载配置中...
            </Text>
          </View>
        ) : (
          <>
            <ScrollView
              style={styles.configScroll}
              contentContainerStyle={styles.configBody}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              <View style={[styles.switchRow, { borderTopColor: c.borderLight }]}>
                <Text style={[styles.switchLabel, { color: c.text }]}>开启</Text>
                <Switch
                  value={crEnabled}
                  onValueChange={setCrEnabled}
                  trackColor={{ false: c.border, true: c.primary }}
                  thumbColor="#FFFFFF"
                />
              </View>
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>确认收货话术</Text>
                <Input
                  value={crContent}
                  onChangeText={setCrContent}
                  placeholder="买家确认收货后收到的消息..."
                  multiline
                  style={styles.textarea}
                />
              </View>
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>消息图片</Text>
                <View style={styles.imageRow}>
                  <Button
                    label={crImage ? '重新选择' : '选择图片'}
                    variant="secondary"
                    onPress={pickCrImage}
                    loading={crImgUploading}
                    disabled={crImgUploading}
                    style={styles.imageBtn}
                  />
                  {crImage ? (
                    <Pressable onPress={() => setCrImage('')} hitSlop={8}>
                      <Text style={[styles.clearLink, { color: c.error }]}>清除</Text>
                    </Pressable>
                  ) : null}
                </View>
                {crImage ? (
                  <Text style={[styles.imageUrl, { color: c.textMuted }]} numberOfLines={1}>
                    {crImage}
                  </Text>
                ) : null}
              </View>
            </ScrollView>
            <View style={styles.configActions}>
              <Button
                label="保存"
                onPress={saveConfirmReceipt}
                loading={crSaving}
                disabled={crSaving}
                style={styles.configBtn}
              />
            </View>
          </>
        )}
      </FormModal>

      {/* 自动评价 Modal */}
      <FormModal
        visible={arVisible}
        onClose={closeAr}
        title="自动评价"
        contentStyle={styles.configSheet}
      >
        {arLoading ? (
          <View style={styles.configLoadingBox}>
            <ActivityIndicator size="large" color={c.primary} />
            <Text style={[styles.configLoadingText, { color: c.textSecondary }]}>
              加载配置中...
            </Text>
          </View>
        ) : (
          <>
            <ScrollView
              style={styles.configScroll}
              contentContainerStyle={styles.configBody}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              <View style={[styles.switchRow, { borderTopColor: c.borderLight }]}>
                <Text style={[styles.switchLabel, { color: c.text }]}>开启</Text>
                <Switch
                  value={arEnabled}
                  onValueChange={setArEnabled}
                  trackColor={{ false: c.border, true: c.primary }}
                  thumbColor="#FFFFFF"
                />
              </View>
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>评价类型</Text>
                <View style={styles.chipRow}>
                  {([
                    { value: 'text', label: '文本' },
                    { value: 'api', label: 'API' },
                  ] as const).map((opt) => {
                    const active = arType === opt.value;
                    return (
                      <Pressable
                        key={opt.value}
                        onPress={() => setArType(opt.value)}
                        style={[
                          styles.chip,
                          {
                            backgroundColor: active ? c.primary : c.background,
                            borderColor: active ? c.primary : c.border,
                          },
                        ]}
                      >
                        <Text style={[styles.chipText, { color: active ? '#FFFFFF' : c.text }]}>
                          {opt.label}
                        </Text>
                      </Pressable>
                    );
                  })}
                </View>
              </View>
              {arType === 'text' ? (
                <View style={styles.fieldGroup}>
                  <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>评价内容</Text>
                  <Input
                    value={arTextContent}
                    onChangeText={setArTextContent}
                    placeholder="如 不错的买家"
                    multiline
                    style={styles.textarea}
                  />
                </View>
              ) : (
                <View style={styles.fieldGroup}>
                  <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>API 地址</Text>
                  <Input
                    value={arApiUrl}
                    onChangeText={setArApiUrl}
                    placeholder="https://..."
                    autoCapitalize="none"
                    autoCorrect={false}
                    keyboardType="url"
                  />
                </View>
              )}
            </ScrollView>
            <View style={styles.configActions}>
              <Button
                label="保存"
                onPress={saveAutoRate}
                loading={arSaving}
                disabled={arSaving}
                style={styles.configBtn}
              />
            </View>
          </>
        )}
      </FormModal>

      {/* 禁止发货规则 Modal（多规则卡片） */}
      <FormModal
        visible={ddVisible}
        onClose={closeDd}
        title="禁止发货规则"
        contentStyle={styles.configSheet}
      >
        {ddLoading ? (
          <View style={styles.configLoadingBox}>
            <ActivityIndicator size="large" color={c.primary} />
            <Text style={[styles.configLoadingText, { color: c.textSecondary }]}>
              加载规则中...
            </Text>
          </View>
        ) : ddRules.length === 0 ? (
          <View style={styles.configLoadingBox}>
            <Text style={[styles.configLoadingText, { color: c.textMuted }]}>
              暂无可用规则
            </Text>
          </View>
        ) : (
          <>
            <ScrollView
              style={styles.configScroll}
              contentContainerStyle={styles.configBody}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              {ddRules.map((rule) => (
                <View key={rule.rule_code} style={[styles.ruleCard, { borderColor: c.border }]}>
                  <View style={styles.switchRow}>
                    <View style={styles.ruleTitleBox}>
                      <Text style={[styles.ruleName, { color: c.text }]} numberOfLines={1}>
                        {rule.rule_name}
                      </Text>
                      <Text style={[styles.ruleDesc, { color: c.textMuted }]} numberOfLines={2}>
                        {rule.rule_description}
                      </Text>
                    </View>
                    <Switch
                      value={rule.enabled}
                      onValueChange={(v) => updateDdRule(rule.rule_code, { enabled: v })}
                      trackColor={{ false: c.border, true: c.primary }}
                      thumbColor="#FFFFFF"
                    />
                  </View>
                  {rule.enabled && (
                    <>
                      <View style={styles.fieldGroup}>
                        <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>禁止发货原因</Text>
                        <Input
                          value={rule.block_reason}
                          onChangeText={(t) => updateDdRule(rule.rule_code, { block_reason: t })}
                          placeholder="命中规则时给买家的提示..."
                          multiline
                          style={styles.textarea}
                        />
                      </View>
                      <View style={styles.switchRow}>
                        <Text style={[styles.switchLabel, { color: c.text }]}>主动关闭订单</Text>
                        <Switch
                          value={rule.auto_close_order}
                          onValueChange={(v) => updateDdRule(rule.rule_code, { auto_close_order: v })}
                          trackColor={{ false: c.border, true: c.primary }}
                          thumbColor="#FFFFFF"
                        />
                      </View>
                      {rule.auto_close_order && (
                        <View style={styles.switchRow}>
                          <Text style={[styles.switchLabel, { color: c.text }]}>关闭后只发卡券</Text>
                          <Switch
                            value={rule.only_card_after_close}
                            onValueChange={(v) => updateDdRule(rule.rule_code, { only_card_after_close: v })}
                            trackColor={{ false: c.border, true: c.primary }}
                            thumbColor="#FFFFFF"
                          />
                        </View>
                      )}
                      <View style={styles.fieldGroup}>
                        <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>排除商品ID</Text>
                        <Input
                          value={rule.excluded_item_ids.join('\n')}
                          onChangeText={(t) =>
                            updateDdRule(rule.rule_code, { excluded_item_ids: t.split('\n') })
                          }
                          placeholder="每行一个商品ID，留空表示不排除"
                          multiline
                          style={styles.textarea}
                        />
                      </View>
                    </>
                  )}
                </View>
              ))}
            </ScrollView>
            <View style={styles.configActions}>
              <Button
                label="保存"
                onPress={saveDeliveryDisabled}
                loading={ddSaving}
                disabled={ddSaving}
                style={styles.configBtn}
              />
            </View>
          </>
        )}
      </FormModal>

      {/* 退款订单注销 Modal */}
      <FormModal
        visible={rcVisible}
        onClose={closeRc}
        title="退款订单注销"
        contentStyle={styles.configSheet}
      >
        {rcLoading ? (
          <View style={styles.configLoadingBox}>
            <ActivityIndicator size="large" color={c.primary} />
            <Text style={[styles.configLoadingText, { color: c.textSecondary }]}>
              加载配置中...
            </Text>
          </View>
        ) : (
          <>
            <ScrollView
              style={styles.configScroll}
              contentContainerStyle={styles.configBody}
              keyboardShouldPersistTaps="handled"
              showsVerticalScrollIndicator={false}
            >
              <View style={[styles.switchRow, { borderTopColor: c.borderLight }]}>
                <Text style={[styles.switchLabel, { color: c.text }]}>开启退款订单注销</Text>
                <Switch
                  value={rcEnabled}
                  onValueChange={setRcEnabled}
                  trackColor={{ false: c.border, true: c.primary }}
                  thumbColor="#FFFFFF"
                />
              </View>
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>请求URL</Text>
                <Input
                  value={rcUrl}
                  onChangeText={(t) => {
                    setRcUrl(t);
                    // URL 清空时自动关闭开关，保证"无URL时开关必关"
                    if (!t.trim() && rcEnabled) setRcEnabled(false);
                  }}
                  placeholder="https://example.com/cancel"
                  autoCapitalize="none"
                  autoCorrect={false}
                  keyboardType="url"
                />
                <Text style={[styles.hintText, { color: c.textMuted }]}>
                  POST 表单，参数 delivery_content、link_url，每个发货内容调一次
                </Text>
              </View>
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>超时时间(秒)</Text>
                <Input
                  value={rcTimeout}
                  onChangeText={setRcTimeout}
                  placeholder="60"
                  keyboardType="number-pad"
                />
              </View>
            </ScrollView>
            <View style={styles.configActions}>
              <Button
                label="保存"
                onPress={saveRefundCancel}
                loading={rcSaving}
                disabled={rcSaving}
                style={styles.configBtn}
              />
            </View>
          </>
        )}
      </FormModal>

      {/* 密码登录 Modal */}
      {pwdLoginAccount && (
        <PasswordLoginModal
          visible={!!pwdLoginAccount}
          accountId={pwdLoginAccount.id}
          onClose={() => setPwdLoginAccount(null)}
          onSuccess={() => { setPwdLoginAccount(null); loadAccounts(true); }}
        />
      )}
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
    paddingVertical: spacing.md,
  },
  listContent: { padding: spacing.lg, gap: spacing.md },
  card: { gap: spacing.md },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  cardInfo: { flex: 1, marginRight: spacing.md },
  nameRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  statusDot: { width: 8, height: 8, borderRadius: 4 },
  accountName: { ...typography.body, fontWeight: '600' },
  accountId: { ...typography.small, marginTop: spacing.xs },
  statsRow: {
    flexDirection: 'row',
    borderTopWidth: 1,
    paddingTop: spacing.md,
  },
  stat: { flex: 1, alignItems: 'center' },
  statValue: { ...typography.body, fontWeight: '600' },
  statLabel: { ...typography.small, marginTop: spacing.xs },
  disableReason: { ...typography.small },
  cardActions: { flexDirection: 'row', gap: spacing.sm },
  cardActionBtn: { flex: 1, minHeight: 40, borderRadius: radius.md, paddingHorizontal: spacing.xs, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  cardActionText: { ...typography.caption, fontWeight: '600' },
  empty: { alignItems: 'center', justifyContent: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  loadingMore: { textAlign: 'center', padding: spacing.md },
  // Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.lg,
  },
  modalCard: {
    width: '100%',
    maxWidth: 340,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.md,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  modalTitle: { ...typography.heading },
  closeBtn: { fontSize: 22, paddingHorizontal: spacing.xs },
  qrContainer: { alignItems: 'center', gap: spacing.md, paddingVertical: spacing.md },
  qrBox: {
    padding: spacing.sm,
    backgroundColor: '#FFFFFF',
    borderRadius: radius.md,
  },
  qrImage: { width: 220, height: 220 },
  qrHint: { ...typography.caption, textAlign: 'center' },
  qrPlaceholder: { alignItems: 'center', gap: spacing.md, paddingVertical: spacing.lg },
  qrPlaceholderText: { ...typography.body },
  fieldGroup: { gap: spacing.xs },
  fieldLabel: { ...typography.caption },
  modalActions: { flexDirection: 'row', gap: spacing.sm },
  modalBtn: { flex: 1 },
  selectIndicator: { width: 24, height: 24, borderRadius: 12, alignItems: 'center', justifyContent: 'center', marginBottom: spacing.xs },
  togglesContainer: { borderTopWidth: 1, paddingTop: spacing.sm, marginTop: spacing.sm, gap: spacing.xs },
  toggleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: spacing.xs },
  toggleLabel: { ...typography.body },
  batchBar: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderBottomWidth: 1, flexWrap: 'wrap' },
  batchCount: { ...typography.body, fontWeight: '600' },
  batchBtn: { minHeight: 36, paddingVertical: spacing.xs, paddingHorizontal: spacing.sm },
  // 同意后发货配置
  agreeEntryHint: { ...typography.caption },
  agreeLoadingBox: { alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.xl },
  agreeLoadingText: { ...typography.caption },
  agreeTextarea: { minHeight: 90, textAlignVertical: 'top', paddingTop: spacing.sm },
  agreeUrlRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  agreeUrlInput: { flex: 1 },
  agreeSuggestBtn: { minHeight: 50, paddingHorizontal: spacing.md },
  agreeUrlHint: { ...typography.small },
  // AI设置 / 默认回复 共用样式
  configSheet: { height: '85%' },
  configScroll: { flex: 1 },
  configBody: { gap: spacing.md, paddingBottom: spacing.sm },
  configLoadingBox: { alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.xl },
  configLoadingText: { ...typography.caption },
  switchRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: spacing.xs },
  switchLabel: { ...typography.body },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  chip: { paddingHorizontal: spacing.md, paddingVertical: spacing.xs, borderRadius: radius.full, borderWidth: 1 },
  chipText: { ...typography.small, fontWeight: '600' },
  textarea: { minHeight: 90, textAlignVertical: 'top', paddingTop: spacing.sm },
  timeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  timeInput: { flex: 1 },
  timeSep: { ...typography.body },
  imageRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  imageBtn: { flex: 1, minHeight: 44 },
  clearLink: { ...typography.small, fontWeight: '600' },
  imageUrl: { ...typography.small, marginTop: spacing.xs },
  configActions: { flexDirection: 'row', gap: spacing.sm },
  configBtn: { flex: 1 },
  // 顶部筛选 + 搜索
  searchWrap: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  // 编辑弹窗扩展字段
  editScroll: { maxHeight: 380 },
  editBody: { gap: spacing.md, paddingBottom: spacing.sm },
  editTextarea: {
    minHeight: 80,
    maxHeight: 140,
    textAlignVertical: 'top',
    paddingTop: spacing.sm,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
    ...typography.body,
  },
  pwdWrap: { position: 'relative' },
  pwdToggle: {
    position: 'absolute',
    right: 8,
    top: 0,
    bottom: 0,
    width: 40,
    alignItems: 'center',
    justifyContent: 'center',
  },
  // 8 项高级配置补充样式
  hintText: { ...typography.small, marginTop: spacing.xs },
  faceValue: { ...typography.body, fontWeight: '500' },
  ruleCard: {
    borderWidth: 1,
    borderRadius: radius.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  ruleTitleBox: { flex: 1, marginRight: spacing.sm, gap: spacing.xs },
  ruleName: { ...typography.body, fontWeight: '600' },
  ruleDesc: { ...typography.small },
});
