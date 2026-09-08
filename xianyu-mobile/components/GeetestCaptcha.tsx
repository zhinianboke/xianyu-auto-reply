import React, { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  Pressable,
  ActivityIndicator,
  useColorScheme,
  Dimensions,
} from 'react-native';
import { WebView, type WebViewMessageEvent } from 'react-native-webview';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { getGeetestConfig } from '@/api/wrappers/auth';

interface GeetestCaptchaProps {
  visible: boolean;
  onClose: () => void;
  onSuccess: (challenge: string, validate: string, seccode: string) => void;
}

interface GeetestConfig {
  challenge: string;
  gt: string;
  new_captcha: boolean;
}

/**
 * 极验滑块验证组件。
 * 可见时拉取极验配置（challenge / gt / new_captcha），在 WebView 中渲染 gt.js SDK，
 * 用户完成滑动后通过 onMessage 回传 validate / seccode，再调用 onSuccess。
 * 以底部弹出 Modal 形式展示，并适配深色模式。
 */
export function GeetestCaptcha({ visible, onClose, onSuccess }: GeetestCaptchaProps) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const isDark = scheme === 'dark';

  const [config, setConfig] = useState<GeetestConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    setConfig(null);
    try {
      const cfg = await getGeetestConfig();
      setConfig(cfg);
    } catch (e) {
      setError((e as Error).message || '获取验证码配置失败');
    } finally {
      setLoading(false);
    }
  }, []);

  // 弹窗打开时拉取配置，关闭时重置状态
  useEffect(() => {
    if (!visible) {
      setConfig(null);
      setError(null);
      setLoading(false);
      return;
    }
    void fetchConfig();
  }, [visible, fetchConfig]);

  const handleMessage = useCallback(
    (event: WebViewMessageEvent) => {
      try {
        const data = JSON.parse(event.nativeEvent.data) as {
          type: string;
          challenge?: string;
          validate?: string;
          seccode?: string;
          message?: string;
        };
        if (data.type === 'success' && data.challenge && data.validate && data.seccode) {
          onSuccess(data.challenge, data.validate, data.seccode);
          return;
        }
        if (data.type === 'close') {
          onClose();
          return;
        }
        if (data.type === 'error') {
          setError(data.message || '验证码加载失败');
        }
      } catch {
        // 忽略无法解析的消息
      }
    },
    [onSuccess, onClose],
  );

  // 构造 WebView 渲染的 HTML，使用 JSON.stringify 安全注入配置
  const html = config
    ? buildCaptchaHtml(config, isDark)
    : '';

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <Pressable style={styles.overlay} onPress={onClose}>
        <Pressable
          style={[styles.sheet, { backgroundColor: c.surface }]}
          onPress={() => {}}
        >
          <View style={[styles.header, { borderBottomColor: c.border }]}>
            <Text style={[styles.title, { color: c.text }]}>滑块验证</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
            </Pressable>
          </View>

          <View style={styles.body}>
            {loading ? (
              <View style={styles.centerBox}>
                <ActivityIndicator size="large" color={c.primary} />
                <Text style={[styles.hint, { color: c.textSecondary }]}>
                  正在加载验证码...
                </Text>
              </View>
            ) : error ? (
              <View style={styles.centerBox}>
                <Text style={[styles.errorText, { color: c.error }]}>{error}</Text>
                <Pressable
                  style={[styles.retryBtn, { borderColor: c.primary }]}
                  onPress={() => void fetchConfig()}
                >
                  <Text style={[styles.retryText, { color: c.primary }]}>重试</Text>
                </Pressable>
              </View>
            ) : config ? (
              <WebView
                source={{ html }}
                onMessage={handleMessage}
                style={styles.webview}
                originWhitelist={['*']}
                javaScriptEnabled
                domStorageEnabled
                scrollEnabled={false}
                showsVerticalScrollIndicator={false}
                showsHorizontalScrollIndicator={false}
              />
            ) : null}
          </View>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

/**
 * 生成极验滑块 HTML。
 * - 使用 product: 'embed' 内嵌渲染，适配 WebView 环境
 * - SDK 加载后通过 tryInit 轮询等待 initGeetest 就绪
 * - 成功/出错/关闭均通过 postMessage 回传
 */
function buildCaptchaHtml(cfg: GeetestConfig, isDark: boolean): string {
  const bg = isDark ? '#1C1C1E' : '#FFFFFF';
  const textColor = isDark ? '#AEAEB2' : '#666666';
  const errorColor = isDark ? '#FF453A' : '#FF3B30';
  const challenge = JSON.stringify(cfg.challenge);
  const gt = JSON.stringify(cfg.gt);
  const newCaptcha = JSON.stringify(cfg.new_captcha);

  return `<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      padding: ${spacing.md}px;
      background: ${bg};
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
      overflow: hidden;
    }
    #captcha {
      min-height: 240px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .loading {
      color: ${textColor};
      text-align: center;
      padding: 20px;
      font-size: 14px;
    }
    .error {
      color: ${errorColor};
      text-align: center;
      padding: 20px;
      font-size: 14px;
    }
  </style>
  <script src="https://static.geetest.com/static/tools/gt.js"></script>
</head>
<body>
  <div id="captcha"><div class="loading">加载验证码...</div></div>
  <script>
    var CHALLENGE = ${challenge};
    var GT = ${gt};
    var NEW_CAPTCHA = ${newCaptcha};

    function postError(msg) {
      window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'error', message: msg }));
    }

    function tryInit(retries) {
      if (typeof initGeetest === 'function') {
        initGeetest({
          gt: GT,
          challenge: CHALLENGE,
          new_captcha: NEW_CAPTCHA,
          offline: false,
          product: 'embed',
        }, function(captchaObj) {
          document.getElementById('captcha').innerHTML = '';
          captchaObj.appendTo('#captcha');
          captchaObj.onSuccess(function() {
            var result = captchaObj.getValidate();
            window.ReactNativeWebView.postMessage(JSON.stringify({
              type: 'success',
              challenge: CHALLENGE,
              validate: result.geetest_validate,
              seccode: result.geetest_seccode,
            }));
          });
          captchaObj.onError(function() {
            postError('验证码加载失败，请重试');
          });
          captchaObj.onClose(function() {
            window.ReactNativeWebView.postMessage(JSON.stringify({ type: 'close' }));
          });
        });
      } else if (retries > 0) {
        setTimeout(function() { tryInit(retries - 1); }, 100);
      } else {
        postError('极验 SDK 加载失败，请检查网络后重试');
      }
    }
    tryInit(30);
  </script>
</body>
</html>`;
}

const SHEET_HEIGHT = Math.round(Dimensions.get('window').height * 0.5);

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'flex-end',
  },
  sheet: {
    height: SHEET_HEIGHT,
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
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
  body: { flex: 1 },
  webview: { flex: 1, backgroundColor: 'transparent' },
  centerBox: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: spacing.md,
    padding: spacing.lg,
  },
  hint: { ...typography.body, textAlign: 'center' },
  errorText: { ...typography.body, textAlign: 'center' },
  retryBtn: {
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  retryText: { ...typography.body, fontWeight: '600' },
});
