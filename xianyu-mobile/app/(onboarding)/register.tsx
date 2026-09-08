import { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Alert,
  ScrollView,
  Pressable,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useColorScheme } from 'react-native';
import { Eye, EyeOff } from 'lucide-react-native';
import { Button, Input, Card } from '@/components/ui';
import { colors, spacing, typography } from '@/lib/theme';
import { sendEmailCode, register } from '@/api/wrappers/auth';

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

export default function RegisterScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();

  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [code, setCode] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [sending, setSending] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const countdown = useCountdown();

  async function handleSendCode() {
    if (!email.trim()) {
      Alert.alert('提示', '请输入邮箱');
      return;
    }
    if (!isValidEmail(email.trim())) {
      Alert.alert('提示', '邮箱格式不正确');
      return;
    }
    if (countdown.running) return;
    setSending(true);
    try {
      const resp = await sendEmailCode(email.trim(), 'register');
      if (resp.success && resp.session_id) {
        setSessionId(resp.session_id);
        countdown.start();
        Alert.alert('已发送', '验证码已发送至邮箱');
      } else {
        Alert.alert('发送失败', '验证码发送失败，请稍后重试');
      }
    } catch (e) {
      Alert.alert('发送失败', (e as Error).message);
    } finally {
      setSending(false);
    }
  }

  async function handleRegister() {
    if (!username.trim()) {
      Alert.alert('提示', '请输入用户名');
      return;
    }
    if (!email.trim() || !isValidEmail(email.trim())) {
      Alert.alert('提示', '请输入正确的邮箱');
      return;
    }
    if (!password) {
      Alert.alert('提示', '请输入密码');
      return;
    }
    if (password.length < 6) {
      Alert.alert('提示', '密码长度至少 6 位');
      return;
    }
    if (password !== confirmPassword) {
      Alert.alert('提示', '两次输入的密码不一致');
      return;
    }
    if (!code.trim()) {
      Alert.alert('提示', '请输入邮箱验证码');
      return;
    }
    if (!sessionId) {
      Alert.alert('提示', '请先发送验证码');
      return;
    }
    setSubmitting(true);
    try {
      const resp = await register(
        username.trim(),
        email.trim(),
        password,
        code.trim(),
        sessionId,
      );
      if (resp.success) {
        Alert.alert('注册成功', '请使用新账号登录', [
          { text: '去登录', onPress: () => router.replace('/(onboarding)/login') },
        ]);
      } else {
        Alert.alert('注册失败', resp.message ?? '未知错误');
      }
    } catch (e) {
      Alert.alert('注册失败', (e as Error).message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
      <ScrollView
        contentContainerStyle={styles.content}
        keyboardShouldPersistTaps="handled"
      >
        <Text style={[styles.title, { color: c.text }]}>注册账号</Text>

        <Card style={styles.form}>
          <Text style={[styles.label, { color: c.textSecondary }]}>用户名</Text>
          <Input
            value={username}
            onChangeText={setUsername}
            placeholder="请输入用户名"
            autoCapitalize="none"
            autoCorrect={false}
            style={styles.input}
          />
          <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
            邮箱
          </Text>
          <Input
            value={email}
            onChangeText={setEmail}
            placeholder="you@example.com"
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="email-address"
            style={styles.input}
          />
          <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
            邮箱验证码
          </Text>
          <View style={styles.codeRow}>
            <Input
              value={code}
              onChangeText={setCode}
              placeholder="6 位验证码"
              keyboardType="number-pad"
              style={styles.codeInput}
            />
            <Button
              label={countdown.running ? `${countdown.countdown}s` : '发送验证码'}
              onPress={handleSendCode}
              loading={sending}
              disabled={countdown.running || sending}
              variant="secondary"
              style={styles.codeBtn}
            />
          </View>
          <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
            密码
          </Text>
          <View style={styles.passwordRow}>
            <Input
              value={password}
              onChangeText={setPassword}
              placeholder="至少 6 位"
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
          <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
            确认密码
          </Text>
          <View style={styles.passwordRow}>
            <Input
              value={confirmPassword}
              onChangeText={setConfirmPassword}
              placeholder="再次输入密码"
              secureTextEntry={!showPassword}
              style={styles.passwordInput}
            />
          </View>
        </Card>

        <Button label="注册" onPress={handleRegister} loading={submitting} />

        <View style={styles.linkWrap}>
          <Pressable onPress={() => router.replace('/(onboarding)/login')}>
            <Text style={[styles.link, { color: c.primary }]}>已有账号？去登录</Text>
          </Pressable>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.lg, flexGrow: 1 },
  title: { ...typography.title, textAlign: 'center', marginTop: spacing.xl },
  form: { gap: spacing.sm },
  label: { ...typography.caption },
  input: { marginTop: spacing.xs },
  codeRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.xs,
    gap: spacing.sm,
  },
  codeInput: { flex: 1, marginTop: 0 },
  codeBtn: { minHeight: 48 },
  passwordRow: {
    flexDirection: 'row',
    alignItems: 'center',
    marginTop: spacing.xs,
  },
  passwordInput: { flex: 1, marginTop: 0 },
  eyeBtn: { padding: spacing.sm },
  linkWrap: { alignItems: 'center', marginTop: spacing.xs },
  link: { ...typography.body, fontWeight: '500' },
});
