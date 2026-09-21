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
  /** 内联模式：不用 RN Modal（排查弹窗层是否吞触摸），改用页内绝对定位覆盖层 */
  inline?: boolean;
}

interface GeetestConfig {
  challenge: string;
  gt: string;
  new_captcha: boolean;
  offline: boolean;
}

/**
 * 极验滑块验证组件。
 * 可见时拉取极验配置（challenge / gt / new_captcha），在 WebView 中渲染 gt.js SDK，
 * 用户完成滑动后通过 onMessage 回传 validate / seccode，再调用 onSuccess。
 * 以底部弹出 Modal 形式展示，并适配深色模式。
 */
export function GeetestCaptcha({ visible, onClose, onSuccess, inline = false }: GeetestCaptchaProps) {
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

  const sheet = (
    <View style={styles.overlay} pointerEvents="box-none">
      <View style={[styles.sheet, { backgroundColor: c.surface }]}>
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
              scrollEnabled
              nestedScrollEnabled
              overScrollMode="never"
              bounces={false}
              mixedContentMode="compatibility"
              showsVerticalScrollIndicator={false}
              showsHorizontalScrollIndicator={false}
            />
          ) : null}
        </View>
      </View>
    </View>
  );

  if (inline) {
    if (!visible) return null;
    return (
      <View style={[StyleSheet.absoluteFill, styles.inlineRoot]}>
        {sheet}
      </View>
    );
  }

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      {sheet}
    </Modal>
  );
}

/**
 * 生成极验滑块 HTML。
 * - 强制 https（关键：WebView 页面 location.protocol 为 about:，
 *   不强制会让极验 SDK 拼出 about:// 地址、所有资源加载失败、永远卡在“加载验证码”）
 * - product 与 Web 端保持一致（bind 模式 + 自有按钮触发 verify()）
 * - SDK 加载失败 / 初始化超时均有明确错误回传，不再无限卡加载
 * - 成功/出错通过 postMessage 回传
 */
function buildCaptchaHtml(cfg: GeetestConfig, isDark: boolean): string {
  const bg = isDark ? '#1C1C1E' : '#FFFFFF';
  const textColor = isDark ? '#AEAEB2' : '#666666';
  const errorColor = isDark ? '#FF453A' : '#FF3B30';
  const challenge = JSON.stringify(cfg.challenge);
  const gt = JSON.stringify(cfg.gt);
  const newCaptcha = JSON.stringify(cfg.new_captcha);
  const offline = JSON.stringify(cfg.offline === true);

  return `<!DOCTYPE html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no">
  <style>
    * {
      box-sizing: border-box;
      -webkit-user-select: none;
      user-select: none;
      -webkit-touch-callout: none;
      -webkit-tap-highlight-color: transparent;
    }
    html, body {
      margin: 0;
      padding: 0;
      width: 100%;
      height: 100%;
      overflow: hidden;
      overscroll-behavior: none;
      touch-action: none;
    }
    body {
      padding: ${spacing.md}px;
      background: ${bg};
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
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
  <script>
    // 强制 touch 监听为非 passive：部分 WebView 默认 passive 会让 preventDefault 失效，导致滑块拖不动
    (function () {
      var orig = EventTarget.prototype.addEventListener;
      EventTarget.prototype.addEventListener = function (type, fn, opts) {
        if (type === 'touchstart' || type === 'touchmove' || type === 'touchend') {
          if (opts === undefined || opts === false || opts === true) {
            opts = { capture: !!opts, passive: false };
          } else if (typeof opts === 'object' && opts.passive === undefined) {
            opts = Object.assign({}, opts, { passive: false });
          }
        }
        return orig.call(this, type, fn, opts);
      };
    })();
  </script>
  <script src="https://static.geetest.com/static/tools/gt.js" onerror="window.__gtScriptFailed=true"></script>
</head>
<body>
  <div id="captcha"><div class="loading">加载验证码...</div></div>
  <script>
    var CHALLENGE = ${challenge};
    var GT = ${gt};
    var NEW_CAPTCHA = ${newCaptcha};
    var OFFLINE = ${offline};
    var errored = false;

    function post(msg) {
      try { window.ReactNativeWebView.postMessage(JSON.stringify(msg)); } catch (e) {}
    }

    function postError(msg) {
      if (errored) return;
      errored = true;
      post({ type: 'error', message: msg });
    }






    function showStartButton(captchaObj) {
      var root = document.getElementById('captcha');
      root.innerHTML = '';
      var btn = document.createElement('button');
      btn.textContent = '点击开始滑动验证';
      btn.style.cssText = 'display:block;width:100%;max-width:300px;margin:0 auto;padding:14px 24px;font-size:16px;font-weight:600;color:#fff;background:#2f7cf6;border:none;border-radius:10px;';
      btn.onclick = function () {
        try { captchaObj.verify(); } catch (e) { postError('无法打开滑动画板，请重试'); }
      };
      root.appendChild(btn);
    }

    function initWidget() {
      var inited = false;
      initGeetest({
        gt: GT,
        challenge: CHALLENGE,
        new_captcha: NEW_CAPTCHA,
        offline: OFFLINE,
        product: 'bind',
        width: '100%',
        lang: 'zh-cn',
        https: true,
        protocol: 'https://'
      }, function(captchaObj) {
        inited = true;
        showStartButton(captchaObj);
        captchaObj.onSuccess(function() {
          var result = captchaObj.getValidate();
          if (!result) return;
          post({
            type: 'success',
            challenge: CHALLENGE,
            validate: result.geetest_validate,
            seccode: result.geetest_seccode
          });
        });
        captchaObj.onError(function() { postError('验证码加载失败，请重试'); });
        captchaObj.onClose(function() {});
      });
      setTimeout(function() {
        if (!inited) postError('验证码初始化超时，请重试');
      }, 15000);
    }

    function tryInit(retries) {
      if (window.__gtScriptFailed) { postError('极验 SDK 加载失败，请检查网络后重试'); return; }
      if (typeof initGeetest === 'function') { initWidget(); return; }
      if (retries > 0) {
        setTimeout(function() { tryInit(retries - 1); }, 200);
      } else {
        postError('极验 SDK 加载失败，请检查网络后重试');
      }
    }
    tryInit(100);
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
  inlineRoot: {
    justifyContent: 'flex-end',
    zIndex: 9999,
    elevation: 9999,
  },
});
