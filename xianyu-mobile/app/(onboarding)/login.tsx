import { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  Pressable,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useColorScheme } from 'react-native';
import { Eye, EyeOff } from 'lucide-react-native';
import { Button, Input, Card } from '@/components/ui';
import { GeetestCaptcha } from '@/components/GeetestCaptcha';
import { colors, spacing, typography } from '@/lib/theme';
import { isTimeoutError, withTimeout } from '@/lib/timeout';
import { useAuthStore } from '@/stores/auth';
import { useConfigStore } from '@/stores/config';
import {
  login,
  loginWithEmail,
  loginWithVerificationCode,
  sendEmailCode,
  getPublicSettings,
  extractUser,
  type LoginResponse,
} from '@/api/wrappers/auth';

type Tab = 'account' | 'email' | 'code';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function isValidEmail(email: string) {
  return EMAIL_RE.test(email);
}

/** 60 秒倒计时 hook */
function useCountdown() {
  const [countdown, setCountdown] = useState(0);
  useEffect(() => {
    if (countdown <= 0) return;
    const t = setTimeout(() => setCountdown((c) => c - 1), 1000);
    return () => clearTimeout(t);
  }, [countdown]);
  const start = useCallback(() => setCountdown(60), []);
  return { countdown, start, running: countdown > 0 };
}

export default function LoginScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);
  const serverUrl = useConfigStore((s) => s.serverUrl);

  const [tab, setTab] = useState<Tab>('account');

  // 公共设置
  const [captchaEnabled, setCaptchaEnabled] = useState(false);
  const [registrationEnabled, setRegistrationEnabled] = useState(false);

  // 账号登录
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  // 邮箱登录
  const [email, setEmail] = useState('');
  const [emailPassword, setEmailPassword] = useState('');
  const [showEmailPassword, setShowEmailPassword] = useState(false);

  // 验证码登录
  const [codeEmail, setCodeEmail] = useState('');
  const [verificationCode, setVerificationCode] = useState('');
  const [emailSessionId, setEmailSessionId] = useState('');
  const codeCountdown = useCountdown();
  const [sendingCode, setSendingCode] = useState(false);

  const [loading, setLoading] = useState(false);

  // 极验滑块验证
  const [captchaVisible, setCaptchaVisible] = useState(false);
  const [geetestResult, setGeetestResult] = useState<{
    challenge: string;
    validate: string;
    seccode: string;
  } | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const settings = await getPublicSettings();
        if (cancelled) return;
        setCaptchaEnabled(settings.login_captcha_enabled === true || settings.login_captcha_enabled === 'true');
        setRegistrationEnabled(settings.registration_enabled === true || settings.registration_enabled === 'true');
      } catch {
        // 读取失败时保持默认（无滑块、不显示注册入口），不阻塞登录
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  async function applyLoginResponse(resp: LoginResponse) {
    if (resp.success && resp.token) {
      const user = extractUser(resp);
      if (user) {
        await setAuth(resp.token, resp.refresh_token ?? '', user);
        router.replace('/(tabs)/messages');
      } else {
        Alert.alert('登录失败', '响应数据不完整');
      }
    } else {
      Alert.alert('登录失败', resp.message ?? '未知错误');
    }
  }

  /** 判断响应消息是否与滑块验证相关（失效/未完成/校验失败） */
  function isCaptchaError(message?: string | null) {
    if (!message) return false;
    return (
      message.includes('验证') ||
      message.includes('滑块') ||
      message.includes('challenge') ||
      message.includes('极验')
    );
  }

  /** 滑块验证成功：存储结果并关闭弹窗 */
  function handleCaptchaSuccess(
    challenge: string,
    validate: string,
    seccode: string,
  ) {
    setGeetestResult({ challenge, validate, seccode });
    setCaptchaVisible(false);
  }

  /** 登录返回滑块相关错误时，提示并重置验证结果以便重新完成 */
  function handleCaptchaFailure(message: string) {
    setGeetestResult(null);
    Alert.alert('验证失效', `${message}，请重新完成滑块验证`, [
      { text: '知道了' },
    ]);
  }

  // 账号登录
  async function handleAccountLogin() {
    if (!username.trim() || !password.trim()) {
      Alert.alert('提示', '请输入用户名和密码');
      return;
    }
    if (captchaEnabled && !geetestResult) {
      Alert.alert('提示', '请先完成滑块验证');
      return;
    }
    setLoading(true);
    try {
      // 超时保护：15 秒 UI 报错（IPv6 黑洞防护），不 cancel 底层请求
      const resp = await withTimeout(
        login(username.trim(), password, geetestResult?.challenge),
        15000,
        'TIMEOUT_15S',
      );
      if (!resp.success && isCaptchaError(resp.message)) {
        handleCaptchaFailure(resp.message ?? '滑块验证已失效');
        return;
      }
      await applyLoginResponse(resp);
    } catch (e) {
      const msg = (e as Error).message;
      if (isTimeoutError(e)) {
        Alert.alert('登录超时', '连接服务器超时（15秒）。\n\n常见原因：域名解析到了不可达的 IPv6 地址。\n建议：返回服务器配置页改用 IP 地址连接');
      } else {
        Alert.alert('登录失败', msg);
      }
    } finally {
      setLoading(false);
    }
  }

  // 邮箱登录
  async function handleEmailLogin() {
    if (!email.trim() || !emailPassword.trim()) {
      Alert.alert('提示', '请输入邮箱和密码');
      return;
    }
    if (!isValidEmail(email.trim())) {
      Alert.alert('提示', '邮箱格式不正确');
      return;
    }
    if (captchaEnabled && !geetestResult) {
      Alert.alert('提示', '请先完成滑块验证');
      return;
    }
    setLoading(true);
    try {
      const resp = await withTimeout(
        loginWithEmail(email.trim(), emailPassword, geetestResult?.challenge),
        15000,
        'TIMEOUT_15S',
      );
      if (!resp.success && isCaptchaError(resp.message)) {
        handleCaptchaFailure(resp.message ?? '滑块验证已失效');
        return;
      }
      await applyLoginResponse(resp);
    } catch (e) {
      const msg = (e as Error).message;
      if (isTimeoutError(e)) {
        Alert.alert('登录超时', '连接服务器超时（15秒）。\n\n建议：返回服务器配置页改用 IP 地址连接');
      } else {
        Alert.alert('登录失败', msg);
      }
    } finally {
      setLoading(false);
    }
  }

  // 发送验证码（用于验证码登录）
  async function handleSendCode() {
    if (!codeEmail.trim()) {
      Alert.alert('提示', '请输入邮箱');
      return;
    }
    if (!isValidEmail(codeEmail.trim())) {
      Alert.alert('提示', '邮箱格式不正确');
      return;
    }
    if (codeCountdown.running) return;
    setSendingCode(true);
    try {
      const resp = await sendEmailCode(codeEmail.trim(), 'login');
      if (resp.success && resp.session_id) {
        setEmailSessionId(resp.session_id);
        codeCountdown.start();
        Alert.alert('已发送', '验证码已发送至邮箱');
      } else {
        Alert.alert('发送失败', '验证码发送失败，请稍后重试');
      }
    } catch (e) {
      Alert.alert('发送失败', (e as Error).message);
    } finally {
      setSendingCode(false);
    }
  }

  // 验证码登录
  async function handleCodeLogin() {
    if (!codeEmail.trim() || !verificationCode.trim()) {
      Alert.alert('提示', '请输入邮箱和验证码');
      return;
    }
    if (!isValidEmail(codeEmail.trim())) {
      Alert.alert('提示', '邮箱格式不正确');
      return;
    }
    if (!emailSessionId) {
      Alert.alert('提示', '请先发送验证码');
      return;
    }
    setLoading(true);
    try {
      const resp = await withTimeout(
        loginWithVerificationCode(codeEmail.trim(), verificationCode.trim(), emailSessionId),
        15000,
        'TIMEOUT_15S',
      );
      await applyLoginResponse(resp);
    } catch (e) {
      const msg = (e as Error).message;
      if (isTimeoutError(e)) {
        Alert.alert('登录超时', '连接服务器超时（15秒）。\n\n建议：返回服务器配置页改用 IP 地址连接');
      } else {
        Alert.alert('登录失败', msg);
      }
    } finally {
      setLoading(false);
    }
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'account', label: '账号登录' },
    { key: 'email', label: '邮箱登录' },
    { key: 'code', label: '验证码登录' },
  ];

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.content}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
        >
          <Text style={[styles.title, { color: c.text }]}>闲鱼管家</Text>
          <Text style={[styles.subtitle, { color: c.textSecondary }]}>
            {serverUrl ?? '未配置服务器'}
          </Text>

          <View style={styles.tabBar}>
            {tabs.map((t) => {
              const active = t.key === tab;
              return (
                <Pressable
                  key={t.key}
                  onPress={() => setTab(t.key)}
                  style={styles.tab}
                >
                  <Text
                    style={[
                      styles.tabLabel,
                      { color: active ? c.primary : c.textSecondary },
                      active && styles.tabLabelActive,
                    ]}
                  >
                    {t.label}
                  </Text>
                  {active && (
                    <View
                      style={[styles.tabIndicator, { backgroundColor: c.primary }]}
                    />
                  )}
                </Pressable>
              );
            })}
          </View>

          {tab === 'account' && (
            <Card style={styles.form}>
              <Text style={[styles.label, { color: c.textSecondary }]}>
                用户名
              </Text>
              <Input
                value={username}
                onChangeText={setUsername}
                placeholder="admin"
                autoCapitalize="none"
                autoCorrect={false}
                style={styles.input}
              />
              <Text
                style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}
              >
                密码
              </Text>
              <View style={styles.passwordRow}>
                <Input
                  value={password}
                  onChangeText={setPassword}
                  placeholder="••••••••"
                  secureTextEntry={!showPassword}
                  style={styles.passwordInput}
                />
                <Pressable
                  onPress={() => setShowPassword(!showPassword)}
                  style={styles.eyeBtn}
                >
                  {showPassword ? (
                    <Eye size={20} stroke={c.textSecondary} />
                  ) : (
                    <EyeOff size={20} stroke={c.textSecondary} />
                  )}
                </Pressable>
              </View>
            </Card>
          )}

          {tab === 'email' && (
            <Card style={styles.form}>
              <Text style={[styles.label, { color: c.textSecondary }]}>邮箱</Text>
              <Input
                value={email}
                onChangeText={setEmail}
                placeholder="you@example.com"
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                style={styles.input}
              />
              <Text
                style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}
              >
                密码
              </Text>
              <View style={styles.passwordRow}>
                <Input
                  value={emailPassword}
                  onChangeText={setEmailPassword}
                  placeholder="••••••••"
                  secureTextEntry={!showEmailPassword}
                  style={styles.passwordInput}
                />
                <Pressable
                  onPress={() => setShowEmailPassword(!showEmailPassword)}
                  style={styles.eyeBtn}
                >
                  {showEmailPassword ? (
                    <Eye size={20} stroke={c.textSecondary} />
                  ) : (
                    <EyeOff size={20} stroke={c.textSecondary} />
                  )}
                </Pressable>
              </View>
            </Card>
          )}

          {tab === 'code' && (
            <Card style={styles.form}>
              <Text style={[styles.label, { color: c.textSecondary }]}>邮箱</Text>
              <Input
                value={codeEmail}
                onChangeText={setCodeEmail}
                placeholder="you@example.com"
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                style={styles.input}
              />
              <Text
                style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}
              >
                验证码
              </Text>
              <View style={styles.codeRow}>
                <Input
                  value={verificationCode}
                  onChangeText={setVerificationCode}
                  placeholder="6 位验证码"
                  keyboardType="number-pad"
                  style={styles.codeInput}
                />
                <Button
                  label={codeCountdown.running ? `${codeCountdown.countdown}s` : '发送验证码'}
                  onPress={handleSendCode}
                  loading={sendingCode}
                  disabled={codeCountdown.running || sendingCode}
                  variant="secondary"
                  style={styles.codeBtn}
                />
              </View>
            </Card>
          )}

          {tab === 'account' && captchaEnabled && (
            <Button
              label={geetestResult ? '✓ 已完成滑块验证' : '完成滑块验证'}
              onPress={() => setCaptchaVisible(true)}
              variant={geetestResult ? 'secondary' : 'primary'}
              disabled={!!geetestResult}
            />
          )}
          {tab === 'account' && (
            <Button label="登录" onPress={handleAccountLogin} loading={loading} />
          )}
          {tab === 'email' && captchaEnabled && (
            <Button
              label={geetestResult ? '✓ 已完成滑块验证' : '完成滑块验证'}
              onPress={() => setCaptchaVisible(true)}
              variant={geetestResult ? 'secondary' : 'primary'}
              disabled={!!geetestResult}
            />
          )}
          {tab === 'email' && (
            <Button label="登录" onPress={handleEmailLogin} loading={loading} />
          )}
          {tab === 'code' && (
            <Button label="登录" onPress={handleCodeLogin} loading={loading} />
          )}

          <View style={styles.links}>
            <Pressable onPress={() => router.push('/(onboarding)/forgot-password')}>
              <Text style={[styles.link, { color: c.primary }]}>忘记密码？</Text>
            </Pressable>
            {registrationEnabled && (
              <Pressable onPress={() => router.push('/(onboarding)/register')}>
                <Text style={[styles.link, { color: c.primary }]}>注册账号</Text>
              </Pressable>
            )}
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
      <GeetestCaptcha
        visible={captchaVisible}
        onClose={() => setCaptchaVisible(false)}
        onSuccess={handleCaptchaSuccess}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { flex: 1 },
  scroll: { padding: spacing.lg, gap: spacing.lg, flexGrow: 1 },
  title: { ...typography.title, textAlign: 'center', marginTop: spacing.xl },
  subtitle: { ...typography.caption, textAlign: 'center' },
  tabBar: {
    flexDirection: 'row',
    borderBottomWidth: 1,
    borderColor: 'rgba(0,0,0,0.06)',
  },
  tab: { flex: 1, alignItems: 'center', paddingVertical: spacing.sm },
  tabLabel: { ...typography.body },
  tabLabelActive: { fontWeight: '700' },
  tabIndicator: {
    position: 'absolute',
    bottom: 0,
    width: 32,
    height: 3,
    borderRadius: 2,
  },
  form: { gap: spacing.sm },
  label: { ...typography.caption },
  input: { marginTop: spacing.xs },
  passwordRow: { flexDirection: 'row', alignItems: 'center', marginTop: spacing.xs },
  passwordInput: { flex: 1, marginTop: 0 },
  eyeBtn: { padding: spacing.sm },
  codeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.xs,
    gap: spacing.sm,
  },
  codeInput: { flex: 1, marginTop: 0 },
  codeBtn: { minHeight: 48 },
  links: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginTop: spacing.xs,
  },
  link: { ...typography.body, fontWeight: '500' },
});
