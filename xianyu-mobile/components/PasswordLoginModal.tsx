import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Pressable,
  Modal,
  ActivityIndicator,
  ScrollView,
  Linking,
} from 'react-native';
import { useColorScheme } from 'react-native';
import QRCode from 'react-native-qrcode-svg';
import { Button, Input } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  startPasswordLogin,
  checkPasswordLoginStatus,
  cancelPasswordLogin,
  type PasswordLoginSession,
} from '@/api/wrappers/password-login';

const POLL_INTERVAL = 2000;
// 轮询总时长上限：后端会话可能卡在 processing，避免无限轮询
const POLL_MAX_DURATION_MS = 2 * 60 * 1000;

interface PasswordLoginModalProps {
  visible: boolean;
  accountId: string;
  onClose: () => void;
  onSuccess: () => void;
}

/**
 * 闲鱼账号密码登录弹窗。
 * 输入密码后发起登录，轮询状态直至 success/failed；
 * verification_required 时展示人脸二维码或验证链接。
 */
export function PasswordLoginModal({
  visible,
  accountId,
  onClose,
  onSuccess,
}: PasswordLoginModalProps) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [password, setPassword] = useState('');
  const [starting, setStarting] = useState(false);
  const [session, setSession] = useState<PasswordLoginSession | null>(null);
  const [status, setStatus] = useState<PasswordLoginSession['status']>('idle');
  const [message, setMessage] = useState('');
  const [cancelling, setCancelling] = useState(false);

  // 保持最新回调引用，避免轮询 effect 因回调变化而频繁重建
  const onSuccessRef = useRef(onSuccess);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onSuccessRef.current = onSuccess;
    onCloseRef.current = onClose;
  });

  // 弹窗打开时重置全部状态
  useEffect(() => {
    if (visible) {
      setPassword('');
      setStarting(false);
      setSession(null);
      setStatus('idle');
      setMessage('');
      setCancelling(false);
    }
  }, [visible]);

  const startLogin = useCallback(async () => {
    const pwd = password.trim();
    if (!pwd || !accountId || starting) return;
    setStarting(true);
    setMessage('');
    setStatus('idle');
    setSession(null);
    try {
      const s = await startPasswordLogin(accountId, pwd);
      if (!s.session_id) {
        setMessage('登录会话创建失败');
        setStatus('failed');
        return;
      }
      setSession(s);
      setStatus(s.status || 'processing');
      if (s.message) setMessage(s.message);
    } catch (e) {
      setMessage((e as Error).message || '发起登录失败');
      setStatus('failed');
    } finally {
      setStarting(false);
    }
  }, [password, accountId, starting]);

  // 轮询登录状态：基于 session_id 驱动，递归 setTimeout 避免并发
  useEffect(() => {
    if (!visible) return;
    const sessionId = session?.session_id;
    if (!sessionId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const startedAt = Date.now();

    const poll = async () => {
      if (cancelled) return;
      if (Date.now() - startedAt >= POLL_MAX_DURATION_MS) {
        setStatus('failed');
        setMessage('登录超时，请重试');
        return; // 停止轮询
      }
      try {
        const s = await checkPasswordLoginStatus(sessionId);
        if (cancelled) return;
        // 合并而非替换：status 响应可能不含 session_id，保留原值以维持轮询
        setSession((prev) => (prev ? { ...prev, ...s } : s));
        setStatus(s.status);
        if (s.message) setMessage(s.message);

        if (s.status === 'success') {
          onSuccessRef.current();
          onCloseRef.current();
          return; // 停止轮询
        }
        if (s.status === 'failed') {
          return; // 停止轮询，等待用户重试
        }
      } catch (e) {
        if (cancelled) return;
        setMessage((e as Error).message);
      }
      if (cancelled) return;
      timer = setTimeout(poll, POLL_INTERVAL);
    };

    timer = setTimeout(poll, POLL_INTERVAL);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [visible, session?.session_id]);

  const handleCancel = useCallback(async () => {
    const sid = session?.session_id;
    if (sid) {
      setCancelling(true);
      try {
        await cancelPasswordLogin(sid);
      } catch (e) {
        console.error('取消登录失败', e);
      } finally {
        setCancelling(false);
      }
    }
    onClose();
  }, [session?.session_id, onClose]);

  const showForm = status === 'idle' || status === 'failed';

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={onClose}
    >
      <Pressable style={styles.overlay} onPress={onClose}>
        <Pressable
          style={[styles.card, { backgroundColor: c.surface, borderColor: c.border }]}
          onPress={() => {}}
        >
          {/* Header */}
          <View style={[styles.header, { borderBottomColor: c.border }]}>
            <Text style={[styles.title, { color: c.text }]}>闲鱼账号密码登录</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
            </Pressable>
          </View>

          {/* Body */}
          <ScrollView
            style={styles.body}
            contentContainerStyle={styles.bodyContent}
            keyboardShouldPersistTaps="handled"
          >
            {showForm ? (
              <>
                <Text style={[styles.label, { color: c.textSecondary }]}>
                  请输入闲鱼账号密码
                </Text>
                <Input
                  value={password}
                  onChangeText={setPassword}
                  placeholder="请输入密码"
                  secureTextEntry
                  autoCapitalize="none"
                  autoCorrect={false}
                  editable={!starting}
                />
                {status === 'failed' && message ? (
                  <Text style={[styles.errorText, { color: c.error }]}>
                    {message}
                  </Text>
                ) : null}
                <Button
                  label={status === 'failed' ? '重试' : '开始登录'}
                  onPress={startLogin}
                  loading={starting}
                  disabled={starting || !password.trim()}
                />
              </>
            ) : status === 'processing' ? (
              <View style={styles.statusBox}>
                <ActivityIndicator size="large" color={c.primary} />
                <Text style={[styles.statusText, { color: c.textSecondary }]}>
                  {message || '登录中，请稍候...'}
                </Text>
              </View>
            ) : status === 'verification_required' ? (
              <View style={styles.statusBox}>
                <Text style={[styles.statusText, { color: c.warning }]}>
                  {message || '需要身份验证'}
                </Text>
                {session?.face_qr_url ? (
                  <View style={styles.qrBox}>
                    <QRCode
                      value={session.face_qr_url}
                      size={200}
                      color="#1A1A1A"
                      backgroundColor="#FFFFFF"
                      quietZone={10}
                    />
                  </View>
                ) : session?.verification_url ? (
                  <Pressable
                    style={[styles.linkBtn, { borderColor: c.primary }]}
                    onPress={() => {
                      if (session?.verification_url) {
                        Linking.openURL(session.verification_url).catch(() => {});
                      }
                    }}
                  >
                    <Text style={[styles.linkText, { color: c.primary }]}>
                      点击打开验证链接
                    </Text>
                  </Pressable>
                ) : null}
              </View>
            ) : status === 'success' ? (
              <View style={styles.statusBox}>
                <ActivityIndicator size="large" color={c.success} />
                <Text style={[styles.statusText, { color: c.success }]}>
                  登录成功
                </Text>
              </View>
            ) : null}
          </ScrollView>

          {/* Footer */}
          <View style={[styles.footer, { borderTopColor: c.border }]}>
            <Button
              label={cancelling ? '取消中...' : '取消'}
              variant="ghost"
              onPress={handleCancel}
              loading={cancelling}
              disabled={cancelling}
            />
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.lg,
  },
  card: {
    width: '100%',
    maxWidth: 380,
    borderRadius: radius.lg,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: StyleSheet.hairlineWidth,
  },
  title: { ...typography.heading, fontSize: 16 },
  closeBtn: { fontSize: 22, paddingHorizontal: spacing.xs },
  body: { maxHeight: 420 },
  bodyContent: { padding: spacing.lg, gap: spacing.md },
  label: { ...typography.caption },
  errorText: { ...typography.small },
  statusBox: { alignItems: 'center', gap: spacing.md, paddingVertical: spacing.lg },
  statusText: { ...typography.body, textAlign: 'center' },
  qrBox: {
    padding: spacing.sm,
    backgroundColor: '#FFFFFF',
    borderRadius: radius.md,
  },
  linkBtn: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  linkText: { ...typography.body, fontWeight: '600' },
  footer: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderTopWidth: StyleSheet.hairlineWidth,
  },
});
