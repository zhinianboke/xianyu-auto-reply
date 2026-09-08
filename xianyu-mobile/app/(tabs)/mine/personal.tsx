import { useState, useEffect, useCallback, useMemo } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Pressable,
  Alert,
  Modal,
  FlatList,
  ActivityIndicator,
  Linking,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { useRouter } from 'expo-router';
import { Card, Button, Input, Loading, FormModal, Badge } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { useAuthStore } from '@/stores/auth';
import {
  changePassword,
  recharge,
  withdraw,
  getFundFlows,
  getSystemSettings,
  getCurrentUserProfile,
  renewAccount,
  getSettlementRecords,
  type FundFlow,
  type UserProfile,
  type SettlementRecord,
} from '@/api/wrappers/settings';
import {
  User,
  KeyRound,
  Wallet,
  Eye,
  EyeOff,
  ArrowUpRight,
  ArrowDownRight,
  RefreshCw,
  CalendarClock,
  ScrollText,
} from 'lucide-react-native';

/** 提现收款方式预设 */
const PAYMENT_METHODS = ['支付宝', '微信', '银行卡'] as const;

/** 续期月数快捷选项 */
const RENEW_MONTH_OPTIONS = [1, 3, 6, 12] as const;

/** 续期单价的系统设置 key（普通用户可读，用于计算续期总价） */
const RENEW_MONTH_PRICE_KEY = 'user.renew_month_price';

/** 将金额字符串解析为浮点数（无法解析时返回 0） */
function parseAmount(v: string | undefined | null): number {
  const n = parseFloat(String(v ?? '0'));
  return Number.isFinite(n) ? n : 0;
}

/** 格式化金额为两位小数 */
function formatMoney(n: number): string {
  return n.toFixed(2);
}

/** 格式化时间字符串为可读形式 */
function formatTime(iso: string): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const pad = (x: number) => String(x).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// 格式化到期日展示（后端为北京时间 naive 字符串，无需做时区转换）
// 形如 '2026-06-25T14:30:00' -> '2026-06-25 14:30:00'；空值显示「永不过期」
function formatExpireAt(value?: string | null): string {
  if (!value) return '永不过期';
  return value.replace('T', ' ').slice(0, 19);
}

// 判断到期日是否已过期（到期日存在且早于当前时间）
function isExpired(value?: string | null): boolean {
  if (!value) return false;
  const t = new Date(value).getTime();
  return Number.isFinite(t) && t < Date.now();
}

/** 结算记录状态 -> 徽章文案 + 配色 */
function settlementStatusMeta(
  status: SettlementRecord['status'],
): { label: string; variant: 'warning' | 'primary' | 'success' | 'danger' | 'gray' } {
  switch (status) {
    case 'pending_review':
      return { label: '待审核', variant: 'warning' };
    case 'approved':
      return { label: '已通过', variant: 'primary' };
    case 'paid':
      return { label: '已打款', variant: 'success' };
    case 'rejected':
      return { label: '已拒绝', variant: 'danger' };
    default:
      return { label: status, variant: 'gray' };
  }
}

/** 结算记录收款方式文案 */
function paymentTypeLabel(rec: SettlementRecord): string {
  if (rec.payment_type === 'wechat') return '微信';
  if (rec.payment_type === 'alipay') return '支付宝';
  return rec.alipay_id ? '支付宝' : '-';
}

export default function PersonalSettingsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();
  const user = useAuthStore((s) => s.user);

  // 修改密码
  const [currentPwd, setCurrentPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [confirmPwd, setConfirmPwd] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [pwdSaving, setPwdSaving] = useState(false);

  // 余额与流水
  const [balance, setBalance] = useState<number | null>(null);
  const [flows, setFlows] = useState<FundFlow[]>([]);
  const [flowsLoading, setFlowsLoading] = useState(false);

  // 充值 Modal
  const [rechargeVisible, setRechargeVisible] = useState(false);
  const [rechargeAmount, setRechargeAmount] = useState('');
  const [rechargeSubmitting, setRechargeSubmitting] = useState(false);
  const [rechargeResult, setRechargeResult] = useState<{
    order_no: string;
    pay_url?: string;
  } | null>(null);

  // 提现 Modal
  const [withdrawVisible, setWithdrawVisible] = useState(false);
  const [withdrawAmount, setWithdrawAmount] = useState('');
  const [withdrawMethod, setWithdrawMethod] = useState<string>(PAYMENT_METHODS[0]);
  const [withdrawSubmitting, setWithdrawSubmitting] = useState(false);

  // 流水 Modal
  const [flowsVisible, setFlowsVisible] = useState(false);

  // 到期日与续期
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(false);
  const [renewPrice, setRenewPrice] = useState<string>('');
  const [renewVisible, setRenewVisible] = useState(false);
  const [renewMonths, setRenewMonths] = useState(1);
  const [renewSubmitting, setRenewSubmitting] = useState(false);

  // 结算记录
  const [settlementVisible, setSettlementVisible] = useState(false);
  const [settlementRecords, setSettlementRecords] = useState<SettlementRecord[]>([]);
  const [settlementLoading, setSettlementLoading] = useState(false);
  const [settlementPage, setSettlementPage] = useState(1);
  const [settlementPageSize] = useState(20);
  const [settlementTotal, setSettlementTotal] = useState(0);
  const [settlementTotalPages, setSettlementTotalPages] = useState(0);

  const loadFlows = useCallback(async () => {
    setFlowsLoading(true);
    try {
      const list = await getFundFlows();
      setFlows(list);
      setBalance(list.reduce((sum, f) => sum + parseAmount(f.amount), 0));
    } catch (e) {
      // 流水加载失败不阻断页面，余额保持未知
      setBalance(null);
      console.warn('加载资金流水失败', e);
    } finally {
      setFlowsLoading(false);
    }
  }, []);

  const loadProfile = useCallback(async () => {
    setProfileLoading(true);
    try {
      const p = await getCurrentUserProfile();
      setProfile(p);
    } catch (e) {
      // 到期日加载失败不阻断其他设置展示
      console.warn('加载用户资料失败', e);
    } finally {
      setProfileLoading(false);
    }
  }, []);

  // 加载续期单价（普通用户可读的系统设置项）
  const loadRenewPrice = useCallback(async () => {
    try {
      const settings = await getSystemSettings();
      setRenewPrice(String(settings[RENEW_MONTH_PRICE_KEY] ?? ''));
    } catch (e) {
      // 续期单价加载失败不阻断页面，续期入口降级为不可用
      setRenewPrice('');
      console.warn('加载续期单价失败', e);
    }
  }, []);

  const loadSettlement = useCallback(
    async (page: number = 1) => {
      setSettlementLoading(true);
      try {
        const r = await getSettlementRecords(page, settlementPageSize);
        if (r.success && r.data) {
          setSettlementRecords(r.data.list);
          setSettlementPage(r.data.page);
          setSettlementTotal(r.data.total);
          setSettlementTotalPages(r.data.total_pages);
        } else {
          setSettlementRecords([]);
          setSettlementTotal(0);
          setSettlementTotalPages(0);
          Alert.alert('加载失败', r.message ?? '加载结算记录失败');
        }
      } catch (e) {
        setSettlementRecords([]);
        setSettlementTotal(0);
        setSettlementTotalPages(0);
        Alert.alert('加载失败', (e as Error).message);
      } finally {
        setSettlementLoading(false);
      }
    },
    [settlementPageSize],
  );

  useEffect(() => {
    loadFlows();
    loadProfile();
    loadRenewPrice();
  }, [loadFlows, loadProfile, loadRenewPrice]);

  // ---- 修改密码 ----
  async function handleChangePassword() {
    if (!currentPwd || !newPwd || !confirmPwd) {
      Alert.alert('提示', '请填写完整的密码信息');
      return;
    }
    if (newPwd.length < 6) {
      Alert.alert('提示', '新密码至少 6 位');
      return;
    }
    if (newPwd !== confirmPwd) {
      Alert.alert('提示', '两次输入的新密码不一致');
      return;
    }
    if (newPwd === currentPwd) {
      Alert.alert('提示', '新密码不能与当前密码相同');
      return;
    }
    setPwdSaving(true);
    try {
      const r = await changePassword(currentPwd, newPwd);
      if (r.success) {
        Alert.alert('成功', '密码已修改，请重新登录');
        setCurrentPwd('');
        setNewPwd('');
        setConfirmPwd('');
        // 修改密码后 token 可能失效，跳转登录
        await useAuthStore.getState().logout();
        router.replace('/(onboarding)/login');
      } else {
        Alert.alert('修改失败', r.message ?? '请检查当前密码是否正确');
      }
    } catch (e) {
      Alert.alert('修改失败', (e as Error).message);
    } finally {
      setPwdSaving(false);
    }
  }

  // ---- 充值 ----
  function openRecharge() {
    setRechargeAmount('');
    setRechargeResult(null);
    setRechargeVisible(true);
  }

  async function submitRecharge() {
    const amount = rechargeAmount.trim();
    if (!amount || parseAmount(amount) <= 0) {
      Alert.alert('提示', '请输入有效金额');
      return;
    }
    setRechargeSubmitting(true);
    try {
      const r = await recharge(amount);
      setRechargeResult(r);
    } catch (e) {
      Alert.alert('充值失败', (e as Error).message);
    } finally {
      setRechargeSubmitting(false);
    }
  }

  function closeRecharge() {
    setRechargeVisible(false);
    setRechargeAmount('');
    setRechargeResult(null);
    // 充值后刷新余额与流水
    loadFlows();
  }

  // ---- 提现 ----
  function openWithdraw() {
    setWithdrawAmount('');
    setWithdrawMethod(PAYMENT_METHODS[0]);
    setWithdrawVisible(true);
  }

  async function submitWithdraw() {
    const amount = withdrawAmount.trim();
    if (!amount || parseAmount(amount) <= 0) {
      Alert.alert('提示', '请输入有效金额');
      return;
    }
    if (balance != null && parseAmount(amount) > balance) {
      Alert.alert('提示', '提现金额不能超过余额');
      return;
    }
    setWithdrawSubmitting(true);
    try {
      const r = await withdraw(amount, withdrawMethod);
      if (r.success) {
        Alert.alert('提现申请已提交', r.message ?? '请等待审核');
        setWithdrawVisible(false);
        setWithdrawAmount('');
        loadFlows();
      } else {
        Alert.alert('提现失败', r.message ?? '请稍后重试');
      }
    } catch (e) {
      Alert.alert('提现失败', (e as Error).message);
    } finally {
      setWithdrawSubmitting(false);
    }
  }

  // 打开支付链接
  function openPayUrl(url?: string) {
    if (!url) {
      Alert.alert('提示', '无支付链接');
      return;
    }
    Linking.openURL(url).catch(() => Alert.alert('打开失败', '无法打开支付链接'));
  }

  // ---- 续期 ----
  // 解析续期单价：非法或非正数视为未配置
  const parsedRenewPrice = useMemo(() => {
    const v = parseFloat(String(renewPrice ?? '').trim());
    return Number.isFinite(v) && v > 0 ? v : null;
  }, [renewPrice]);

  // 当前余额数值（余额未知时按 0 处理，续期会因余额不足被拦截）
  const currentBalance = balance ?? 0;
  const renewTotal =
    parsedRenewPrice != null ? parsedRenewPrice * renewMonths : null;
  const renewInsufficient = renewTotal != null && currentBalance < renewTotal;

  function openRenew() {
    setRenewMonths(1);
    setRenewVisible(true);
  }

  async function submitRenew() {
    if (renewSubmitting) return;
    if (parsedRenewPrice == null) {
      Alert.alert('提示', '续期功能未开放，请联系管理员配置续期单价');
      return;
    }
    if (!Number.isInteger(renewMonths) || renewMonths <= 0) {
      Alert.alert('提示', '请选择正确的续期月数');
      return;
    }
    if (renewMonths > 120) {
      Alert.alert('提示', '单次续期不能超过120个月');
      return;
    }
    if (renewInsufficient) {
      Alert.alert(
        '提示',
        `余额不足，本次续期需 ¥${formatMoney(renewTotal!)}，当前余额 ¥${formatMoney(currentBalance)}`,
      );
      return;
    }
    setRenewSubmitting(true);
    try {
      const r = await renewAccount(renewMonths);
      if (!r.success) {
        Alert.alert('续期失败', r.message ?? '请稍后重试');
        return;
      }
      Alert.alert('续期成功', r.message ?? '续期成功');
      // 续期会扣减余额并延长到期日：刷新资料与流水
      setRenewVisible(false);
      await Promise.all([loadProfile(), loadFlows()]);
    } catch (e) {
      Alert.alert('续期失败', (e as Error).message);
    } finally {
      setRenewSubmitting(false);
    }
  }

  // ---- 结算记录 ----
  function openSettlement() {
    setSettlementVisible(true);
    loadSettlement(1);
  }

  const balanceText =
    balance == null ? '—' : `¥${formatMoney(balance)}`;

  const expireAt = profile?.expire_at ?? null;
  const expired = isExpired(expireAt);

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: c.background }]}
      edges={['left', 'right', 'bottom']}
    >
      <ScrollView contentContainerStyle={styles.content}>
        {/* 账户信息 */}
        <Card style={styles.section}>
          <View style={styles.sectionTitleRow}>
            <User size={16} stroke={c.textSecondary} />
            <Text style={[styles.sectionTitle, { color: c.textSecondary }]}>
              账户信息
            </Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={[styles.infoLabel, { color: c.text }]}>用户名</Text>
            <Text style={[styles.infoValue, { color: c.textMuted }]}>
              {user?.username ?? '—'}
            </Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={[styles.infoLabel, { color: c.text }]}>角色</Text>
            <Text style={[styles.infoValue, { color: c.textMuted }]}>
              {user?.is_admin ? '管理员' : '普通用户'}
            </Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={[styles.infoLabel, { color: c.text }]}>账号限额</Text>
            <Text style={[styles.infoValue, { color: c.textMuted }]}>
              {user?.account_limit != null ? String(user.account_limit) : '不限'}
            </Text>
          </View>
          <View style={styles.infoRow}>
            <Text style={[styles.infoLabel, { color: c.text }]}>到期日</Text>
            <View style={styles.expireRow}>
              <Text
                style={[
                  styles.infoValue,
                  { color: expired ? c.error : c.textMuted, flexShrink: 1 },
                ]}
                numberOfLines={1}
              >
                {profileLoading ? '加载中...' : formatExpireAt(expireAt)}
              </Text>
              <Pressable
                onPress={openRenew}
                hitSlop={6}
                style={({ pressed }) => [
                  styles.renewBtn,
                  { backgroundColor: c.primary, opacity: pressed ? 0.7 : 1 },
                ]}
              >
                <CalendarClock size={13} stroke="#FFFFFF" />
                <Text style={styles.renewBtnText}>续期</Text>
              </Pressable>
            </View>
          </View>
          {expired && (
            <Text style={[styles.expireWarn, { color: c.error }]}>
              账户已到期，请尽快续期以恢复服务。
            </Text>
          )}
        </Card>

        {/* 余额管理 */}
        <Card style={styles.section}>
          <View style={styles.sectionTitleRow}>
            <Wallet size={16} stroke={c.textSecondary} />
            <Text style={[styles.sectionTitle, { color: c.textSecondary }]}>
              余额管理
            </Text>
            <Pressable
              onPress={loadFlows}
              hitSlop={8}
              disabled={flowsLoading}
              style={styles.refreshBtn}
            >
              {flowsLoading ? (
                <ActivityIndicator size="small" color={c.primary} />
              ) : (
                <RefreshCw size={16} stroke={c.textSecondary} />
              )}
            </Pressable>
          </View>

          <View style={styles.balanceRow}>
            <Text style={[styles.balanceLabel, { color: c.textSecondary }]}>
              当前余额
            </Text>
            <Text style={[styles.balanceValue, { color: c.text }]}>
              {balanceText}
            </Text>
          </View>

          <View style={styles.balanceActions}>
            <Button
              label="充值"
              variant="primary"
              onPress={openRecharge}
              style={styles.balanceBtn}
            />
            <Button
              label="提现"
              variant="secondary"
              onPress={openWithdraw}
              style={styles.balanceBtn}
            />
            <Button
              label="资金流水"
              variant="ghost"
              onPress={() => setFlowsVisible(true)}
              style={styles.balanceBtn}
            />
            <Button
              label="结算记录"
              variant="ghost"
              onPress={openSettlement}
              style={styles.balanceBtn}
            />
          </View>
        </Card>

        {/* 修改密码 */}
        <Card style={styles.section}>
          <View style={styles.sectionTitleRow}>
            <KeyRound size={16} stroke={c.textSecondary} />
            <Text style={[styles.sectionTitle, { color: c.textSecondary }]}>
              修改密码
            </Text>
          </View>

          <View style={styles.fieldGroup}>
            <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
              当前密码
            </Text>
            <Input
              value={currentPwd}
              onChangeText={setCurrentPwd}
              placeholder="请输入当前密码"
              secureTextEntry={!showPwd}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>
          <View style={styles.fieldGroup}>
            <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
              新密码
            </Text>
            <Input
              value={newPwd}
              onChangeText={setNewPwd}
              placeholder="至少 6 位"
              secureTextEntry={!showPwd}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>
          <View style={styles.fieldGroup}>
            <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
              确认新密码
            </Text>
            <Input
              value={confirmPwd}
              onChangeText={setConfirmPwd}
              placeholder="再次输入新密码"
              secureTextEntry={!showPwd}
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>

          <Pressable
            onPress={() => setShowPwd((v) => !v)}
            style={styles.showPwdRow}
          >
            {showPwd ? (
              <Eye size={16} stroke={c.textSecondary} />
            ) : (
              <EyeOff size={16} stroke={c.textSecondary} />
            )}
            <Text style={[styles.showPwdText, { color: c.textSecondary }]}>
              {showPwd ? '隐藏密码' : '显示密码'}
            </Text>
          </Pressable>

          <Button
            label="修改密码"
            onPress={handleChangePassword}
            loading={pwdSaving}
            disabled={pwdSaving}
            style={styles.pwdBtn}
          />
        </Card>
      </ScrollView>

      {/* 充值 Modal */}
      <FormModal visible={rechargeVisible} onClose={closeRecharge} title="充值">
        {rechargeResult ? (
          <View style={styles.resultGroup}>
            <Text style={[styles.resultText, { color: c.text }]}>
              充值订单已创建
            </Text>
            <Text style={[styles.resultSub, { color: c.textMuted }]}>
              订单号：{rechargeResult.order_no}
            </Text>
            {rechargeResult.pay_url ? (
              <Button
                label="打开支付链接"
                onPress={() => openPayUrl(rechargeResult.pay_url)}
                variant="primary"
                style={styles.modalBtn}
              />
            ) : (
              <Text style={[styles.resultSub, { color: c.textMuted }]}>
                暂无支付链接，请稍后在流水查看
              </Text>
            )}
          </View>
        ) : (
          <>
            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
                充值金额（元）
              </Text>
              <Input
                value={rechargeAmount}
                onChangeText={setRechargeAmount}
                placeholder="如 100"
                keyboardType="numeric"
                autoFocus
              />
            </View>
            <View style={styles.modalActions}>
              <Button
                label="取消"
                variant="ghost"
                onPress={closeRecharge}
                style={styles.modalBtn}
              />
              <Button
                label="充值"
                onPress={submitRecharge}
                loading={rechargeSubmitting}
                disabled={rechargeSubmitting}
                style={styles.modalBtn}
              />
            </View>
          </>
        )}
      </FormModal>

      {/* 提现 Modal */}
      <FormModal
        visible={withdrawVisible}
        onClose={() => setWithdrawVisible(false)}
        title="提现"
      >
        <View style={styles.fieldGroup}>
          <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
            提现金额（元）
          </Text>
          <Input
            value={withdrawAmount}
            onChangeText={setWithdrawAmount}
            placeholder={`可用余额 ${balance == null ? '—' : formatMoney(balance)}`}
            keyboardType="numeric"
            autoFocus
          />
        </View>
        <View style={styles.fieldGroup}>
          <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
            收款方式
          </Text>
          <View
            style={[
              styles.segmented,
              { backgroundColor: c.background, borderColor: c.border },
            ]}
          >
            {PAYMENT_METHODS.map((m) => {
              const active = withdrawMethod === m;
              return (
                <Pressable
                  key={m}
                  onPress={() => setWithdrawMethod(m)}
                  style={[styles.segment, active && { backgroundColor: c.primary }]}
                >
                  <Text
                    style={[
                      styles.segmentText,
                      { color: active ? '#FFF' : c.textSecondary },
                    ]}
                  >
                    {m}
                  </Text>
                </Pressable>
              );
            })}
          </View>
        </View>

        <View style={styles.modalActions}>
          <Button
            label="取消"
            variant="ghost"
            onPress={() => setWithdrawVisible(false)}
            style={styles.modalBtn}
          />
          <Button
            label="提现"
            onPress={submitWithdraw}
            loading={withdrawSubmitting}
            disabled={withdrawSubmitting}
            style={styles.modalBtn}
          />
        </View>
      </FormModal>

      {/* 续期 Modal */}
      <FormModal
        visible={renewVisible}
        onClose={() => setRenewVisible(false)}
        title="账户续期"
      >
        {parsedRenewPrice == null ? (
          <View style={styles.renewUnavailable}>
            <Text style={[styles.renewUnavailableText, { color: c.textMuted }]}>
              续期功能未开放，请联系管理员配置续期单价。
            </Text>
            <Button
              label="关闭"
              variant="ghost"
              onPress={() => setRenewVisible(false)}
              style={styles.modalBtn}
            />
          </View>
        ) : (
          <>
            <View style={styles.renewPriceRow}>
              <Text style={[styles.renewPriceLabel, { color: c.textSecondary }]}>
                续期单价
              </Text>
              <Text style={[styles.renewPriceValue, { color: c.text }]}>
                ¥{formatMoney(parsedRenewPrice)} / 月
              </Text>
            </View>

            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
                续期月数
              </Text>
              <View style={styles.monthOptions}>
                {RENEW_MONTH_OPTIONS.map((m) => {
                  const active = renewMonths === m;
                  return (
                    <Pressable
                      key={m}
                      onPress={() => setRenewMonths(m)}
                      style={[
                        styles.monthChip,
                        {
                          borderColor: active ? c.primary : c.border,
                          backgroundColor: active ? c.primary : c.surface,
                        },
                      ]}
                    >
                      <Text
                        style={[
                          styles.monthChipText,
                          { color: active ? '#FFFFFF' : c.textSecondary },
                        ]}
                      >
                        {m} 个月
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            </View>

            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
                自定义月数（1~120）
              </Text>
              <Input
                value={String(renewMonths)}
                onChangeText={(t) => {
                  const n = parseInt(t, 10);
                  if (Number.isNaN(n)) {
                    setRenewMonths(1);
                  } else {
                    setRenewMonths(Math.min(120, Math.max(1, n)));
                  }
                }}
                keyboardType="numeric"
              />
            </View>

            <View
              style={[styles.renewSummary, { backgroundColor: c.surfaceAlt }]}
            >
              <View style={styles.renewSummaryRow}>
                <Text
                  style={[styles.renewSummaryLabel, { color: c.textSecondary }]}
                >
                  当前余额
                </Text>
                <Text style={[styles.renewSummaryValue, { color: c.text }]}>
                  ¥{formatMoney(currentBalance)}
                </Text>
              </View>
              <View style={styles.renewSummaryRow}>
                <Text
                  style={[styles.renewSummaryLabel, { color: c.textSecondary }]}
                >
                  续期总价
                </Text>
                <Text
                  style={[
                    styles.renewSummaryValue,
                    { color: c.warning, fontWeight: '700' },
                  ]}
                >
                  ¥{renewTotal != null ? formatMoney(renewTotal) : '0.00'}
                </Text>
              </View>
              {renewInsufficient && (
                <Text style={[styles.renewInsufficient, { color: c.error }]}>
                  余额不足，请先充值后再续期。
                </Text>
              )}
            </View>

            <View style={styles.modalActions}>
              <Button
                label="取消"
                variant="ghost"
                onPress={() => setRenewVisible(false)}
                style={styles.modalBtn}
              />
              <Button
                label="确认续期"
                onPress={submitRenew}
                loading={renewSubmitting}
                disabled={renewSubmitting || renewInsufficient}
                style={styles.modalBtn}
              />
            </View>
          </>
        )}
      </FormModal>

      {/* 资金流水 Modal */}
      <Modal
        visible={flowsVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setFlowsVisible(false)}
      >
        <Pressable style={styles.modalOverlay} onPress={() => setFlowsVisible(false)}>
          <Pressable
            style={[styles.flowsCard, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>资金流水</Text>
              <Pressable onPress={() => setFlowsVisible(false)} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>

            {flowsLoading ? (
              <Loading label="加载流水..." />
            ) : flows.length === 0 ? (
              <View style={styles.empty}>
                <Text style={[styles.emptyText, { color: c.textMuted }]}>
                  暂无流水记录
                </Text>
              </View>
            ) : (
              <FlatList
                data={flows}
                keyExtractor={(item) => String(item.id)}
                renderItem={({ item }) => {
                  const amount = parseAmount(item.amount);
                  const positive = amount >= 0;
                  const Icon = positive ? ArrowDownRight : ArrowUpRight;
                  return (
                    <View
                      style={[
                        styles.flowItem,
                        { borderBottomColor: c.border, borderBottomWidth: 0.5 },
                      ]}
                    >
                      <View
                        style={[
                          styles.flowIcon,
                          { backgroundColor: positive ? c.success : c.error },
                        ]}
                      >
                        <Icon size={16} stroke="#FFF" />
                      </View>
                      <View style={styles.flowInfo}>
                        <Text
                          style={[styles.flowDesc, { color: c.text }]}
                          numberOfLines={1}
                        >
                          {item.description || item.type}
                        </Text>
                        <Text style={[styles.flowTime, { color: c.textMuted }]}>
                          {formatTime(item.created_at)}
                        </Text>
                      </View>
                      <Text
                        style={[
                          styles.flowAmount,
                          { color: positive ? c.success : c.error },
                        ]}
                      >
                        {positive ? '+' : ''}
                        {formatMoney(amount)}
                      </Text>
                    </View>
                  );
                }}
                style={styles.flowList}
              />
            )}
          </Pressable>
        </Pressable>
      </Modal>

      {/* 结算记录 Modal */}
      <Modal
        visible={settlementVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setSettlementVisible(false)}
      >
        <Pressable
          style={styles.modalOverlay}
          onPress={() => setSettlementVisible(false)}
        >
          <Pressable
            style={[styles.flowsCard, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            <View style={styles.modalHeader}>
              <View style={styles.settleTitleRow}>
                <ScrollText size={18} stroke={c.text} />
                <Text style={[styles.modalTitle, { color: c.text }]}>
                  结算记录
                </Text>
              </View>
              <Pressable onPress={() => setSettlementVisible(false)} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>

            {settlementLoading ? (
              <Loading label="加载记录..." />
            ) : settlementRecords.length === 0 ? (
              <View style={styles.empty}>
                <Text style={[styles.emptyText, { color: c.textMuted }]}>
                  暂无结算记录
                </Text>
              </View>
            ) : (
              <FlatList
                data={settlementRecords}
                keyExtractor={(item) => String(item.id)}
                renderItem={({ item }) => {
                  const meta = settlementStatusMeta(item.status);
                  return (
                    <View
                      style={[
                        styles.settleItem,
                        { borderBottomColor: c.border, borderBottomWidth: 0.5 },
                      ]}
                    >
                      <View style={styles.settleHeader}>
                        <Text style={[styles.settleAmount, { color: c.text }]}>
                          ¥{item.amount}
                        </Text>
                        <Badge label={meta.label} variant={meta.variant} />
                      </View>
                      <View style={styles.settleMeta}>
                        <Text
                          style={[styles.settleMetaText, { color: c.textMuted }]}
                          numberOfLines={1}
                        >
                          {paymentTypeLabel(item)} · #{item.id}
                        </Text>
                        <Text
                          style={[styles.settleMetaText, { color: c.textMuted }]}
                        >
                          {formatTime(item.created_at ?? '')}
                        </Text>
                      </View>
                      {item.reject_reason ? (
                        <Text
                          style={[styles.settleReason, { color: c.error }]}
                          numberOfLines={2}
                        >
                          拒绝原因：{item.reject_reason}
                        </Text>
                      ) : null}
                    </View>
                  );
                }}
                style={styles.flowList}
              />
            )}

            <View
              style={[
                styles.settlePager,
                { borderTopColor: c.border, borderTopWidth: 0.5 },
              ]}
            >
              <Pressable
                onPress={() => loadSettlement(settlementPage - 1)}
                disabled={settlementPage <= 1 || settlementLoading}
                style={[
                  styles.pageBtn,
                  { borderColor: c.border },
                  (settlementPage <= 1 || settlementLoading) && { opacity: 0.4 },
                ]}
              >
                <Text style={[styles.pageBtnText, { color: c.textSecondary }]}>
                  上一页
                </Text>
              </Pressable>
              <Text style={[styles.pageIndicator, { color: c.textMuted }]}>
                {settlementPage} / {settlementTotalPages || 1} · 共{settlementTotal}
              </Text>
              <Pressable
                onPress={() => loadSettlement(settlementPage + 1)}
                disabled={
                  settlementPage >= settlementTotalPages ||
                  settlementLoading ||
                  settlementTotalPages === 0
                }
                style={[
                  styles.pageBtn,
                  { borderColor: c.border },
                  (settlementPage >= settlementTotalPages ||
                    settlementLoading ||
                    settlementTotalPages === 0) && { opacity: 0.4 },
                ]}
              >
                <Text style={[styles.pageBtnText, { color: c.textSecondary }]}>
                  下一页
                </Text>
              </Pressable>
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  // 底部留白避让 tab 栏，避免"修改密码"表单末尾被遮挡
  content: { padding: spacing.lg, gap: spacing.lg, paddingBottom: 120 },
  section: { gap: spacing.md },
  sectionTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    justifyContent: 'space-between',
  },
  sectionTitle: { ...typography.caption, fontWeight: '600', flex: 1 },
  refreshBtn: { padding: spacing.xs },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.xs,
  },
  infoLabel: { ...typography.body },
  infoValue: { ...typography.body },
  // 到期日 + 续期按钮
  expireRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    flexShrink: 1,
  },
  renewBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 5,
    borderRadius: radius.sm,
  },
  renewBtnText: { color: '#FFFFFF', fontSize: 12, fontWeight: '600' },
  expireWarn: { ...typography.small, marginTop: 2 },
  balanceRow: {
    flexDirection: 'row',
    alignItems: 'baseline',
    justifyContent: 'space-between',
    paddingVertical: spacing.sm,
  },
  balanceLabel: { ...typography.body },
  balanceValue: { ...typography.title, fontSize: 26, fontWeight: '700' },
  // 4 个按钮按 2×2 排列，避免在窄屏挤一行
  balanceActions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  balanceBtn: { flexGrow: 1, flexBasis: '47%' },
  fieldGroup: { gap: spacing.xs },
  fieldLabel: { ...typography.caption },
  showPwdRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.xs,
  },
  showPwdText: { ...typography.small },
  pwdBtn: { marginTop: spacing.xs },
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
  flowsCard: {
    width: '100%',
    maxWidth: 380,
    maxHeight: '80%',
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  modalTitle: { ...typography.heading },
  closeBtn: { fontSize: 22, paddingHorizontal: spacing.xs },
  resultGroup: { gap: spacing.md, paddingVertical: spacing.sm },
  resultText: { ...typography.body, fontWeight: '600' },
  resultSub: { ...typography.small },
  modalActions: { flexDirection: 'row', gap: spacing.sm },
  modalBtn: { flex: 1 },
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
  flowList: { maxHeight: 400 },
  flowItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    gap: spacing.sm,
  },
  flowIcon: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  flowInfo: { flex: 1, gap: 2 },
  flowDesc: { ...typography.body },
  flowTime: { ...typography.small },
  flowAmount: { ...typography.body, fontWeight: '600' },
  empty: { alignItems: 'center', justifyContent: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  // 续期 Modal
  renewPriceRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  renewPriceLabel: { ...typography.body },
  renewPriceValue: { ...typography.body, fontWeight: '600' },
  monthOptions: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  monthChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  monthChipText: { ...typography.small, fontWeight: '600' },
  renewSummary: { borderRadius: radius.md, padding: spacing.md, gap: spacing.xs },
  renewSummaryRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  renewSummaryLabel: { ...typography.caption },
  renewSummaryValue: { ...typography.body, fontWeight: '600' },
  renewInsufficient: { ...typography.small, marginTop: spacing.xs },
  renewUnavailable: { gap: spacing.md, paddingVertical: spacing.sm },
  renewUnavailableText: { ...typography.body, textAlign: 'center' },
  // 结算记录 Modal
  settleTitleRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    flex: 1,
  },
  settleItem: { paddingVertical: spacing.sm, gap: spacing.xs },
  settleHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  settleAmount: { ...typography.body, fontWeight: '700' },
  settleMeta: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: spacing.sm,
  },
  settleMetaText: { ...typography.small, flexShrink: 1 },
  settleReason: { ...typography.small },
  settlePager: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: spacing.sm,
    marginTop: spacing.xs,
  },
  pageBtn: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  pageBtnText: { ...typography.small, fontWeight: '600' },
  pageIndicator: { ...typography.small },
});
