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
import { sendEmailCode, resetPassword } from '@/api/wrappers/auth';

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

export default function ForgotPasswordScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();

  const [step, setStep] = useState<1 | 2>(1);
  const [email, setEmail] = useState('');
  const [sessionId, setSessionId] = useState('');
  const [code, setCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
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
      const resp = await sendEmailCode(email.trim(), 'reset_password');
      if (resp.success && resp.session_id) {
        setSessionId(resp.session_id);
        countdown.start();
        setStep(2);
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

  async function handleResend() {
    setSending(true);
    try {
      const resp = await sendEmailCode(email.trim(), 'reset_password');
      if (resp.success && resp.session_id) {
        setSessionId(resp.session_id);
        countdown.start();
      } else {
        Alert.alert('发送失败', '验证码发送失败，请稍后重试');
      }
    } catch (e) {
      Alert.alert('发送失败', (e as Error).message);
    } finally {
      setSending(false);
    }
  }

  async function handleReset() {
    if (!code.trim()) {
      Alert.alert('提示', '请输入验证码');
      return;
    }
    if (!newPassword) {
      Alert.alert('提示', '请输入新密码');
      return;
    }
    if (newPassword.length < 6) {
      Alert.alert('提示', '密码长度至少 6 位');
      return;
    }
    if (newPassword !== confirmPassword) {
      Alert.alert('提示', '两次输入的密码不一致');
      return;
    }
    if (!sessionId) {
      Alert.alert('提示', '请先发送验证码');
      return;
    }
    setSubmitting(true);
    try {
      const resp = await resetPassword(email.trim(), code.trim(), newPassword);
      if (resp.success) {
        Alert.alert('重置成功', '密码已重置，请使用新密码登录', [
          { text: '去登录', onPress: () => router.replace('/(onboarding)/login') },
        ]);
      } else {
        Alert.alert('重置失败', resp.message ?? '未知错误');
      }
    } catch (e) {
      Alert.alert('重置失败', (e as Error).message);
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
        <Text style={[styles.title, { color: c.text }]}>找回密码</Text>
        <Text style={[styles.subtitle, { color: c.textSecondary }]}>
          {step === 1 ? '输入邮箱获取验证码' : '输入验证码并设置新密码'}
        </Text>

        {step === 1 ? (
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
            <Button
              label={sending ? '发送中...' : '发送验证码'}
              onPress={handleSendCode}
              loading={sending}
              style={{ marginTop: spacing.md }}
            />
          </Card>
        ) : (
          <Card style={styles.form}>
            <Text style={[styles.label, { color: c.textSecondary }]}>
              邮箱：{email}
            </Text>
            <Text
              style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}
            >
              验证码
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
                label={countdown.running ? `${countdown.countdown}s` : '重发'}
                onPress={handleResend}
                loading={sending}
                disabled={countdown.running || sending}
                variant="secondary"
                style={styles.codeBtn}
              />
            </View>
            <Text
              style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}
            >
              新密码
            </Text>
            <View style={styles.passwordRow}>
              <Input
                value={newPassword}
                onChangeText={setNewPassword}
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
            <Text
              style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}
            >
              确认密码
            </Text>
            <View style={styles.passwordRow}>
              <Input
                value={confirmPassword}
                onChangeText={setConfirmPassword}
                placeholder="••••••••"
                secureTextEntry={!showPassword}
                style={styles.passwordInput}
              />
            </View>
            <Button
              label="重置密码"
              onPress={handleReset}
              loading={submitting}
              style={{ marginTop: spacing.lg }}
            />
          </Card>
        )}

        <View style={styles.linkWrap}>
          <Pressable onPress={() => router.replace('/(onboarding)/login')}>
            <Text style={[styles.link, { color: c.primary }]}>返回登录</Text>
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
  subtitle: { ...typography.caption, textAlign: 'center' },
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
  linkWrap: { alignItems: 'center', marginTop: spacing.sm },
  link: { ...typography.body, fontWeight: '500' },
});
