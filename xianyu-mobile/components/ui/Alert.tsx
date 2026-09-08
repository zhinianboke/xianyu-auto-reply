/**
 * 可复制的弹框组件
 *
 * 替代原生 Alert.alert，支持：
 * 1. 长按消息文本复制到剪贴板
 * 2. 一键复制全部内容按钮
 * 3. 暗色模式
 *
 * AlertProvider 挂载时 monkey-patch 全局 RN Alert.alert，
 * 使所有页面的 Alert.alert(...) 调用自动显示本可复制弹框。
 */

import React, { useState, createContext, useContext, useCallback, useEffect, useRef } from 'react';
import { Modal, View, Text, StyleSheet, Pressable, Alert as RNAlert } from 'react-native';
import { useColorScheme } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { colors, spacing, typography, radius } from '@/lib/theme';

interface AlertOptions {
  title?: string;
  message: string;
  buttons?: { text: string; onPress?: () => void; style?: 'default' | 'cancel' | 'destructive' }[];
  copyable?: boolean; // 是否显示复制按钮，默认 true
}

type ShowAlertFn = (options: AlertOptions) => void;

const AlertContext = createContext<ShowAlertFn>(() => {});

export function useAlert() {
  return useContext(AlertContext);
}

// 供 monkey-patch 后调用的引用
let globalShowAlert: ShowAlertFn = () => {};

/**
 * 兜底：在 React 组件树外（如 API 层）调用 Alert 时使用。
 * 正常情况下页面代码中的 Alert.alert 已被 patch 拦截。
 */
export function showAlertGlobal(options: AlertOptions) {
  globalShowAlert(options);
}

export function AlertProvider({ children }: { children: React.ReactNode }) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const [visible, setVisible] = useState(false);
  const [options, setOptions] = useState<AlertOptions>({ message: '' });
  const [copied, setCopied] = useState(false);

  const show = useCallback((opts: AlertOptions) => {
    setOptions({ copyable: true, ...opts });
    setCopied(false);
    setVisible(true);
  }, []);

  const close = useCallback(() => setVisible(false), []);

  // Monkey-patch 全局 RN Alert.alert → 可复制弹框
  // 所有页面的 Alert.alert(...) 调用无需修改即获得复制功能
  useEffect(() => {
    globalShowAlert = show;
    const original = RNAlert.alert.bind(RNAlert);
    (RNAlert as { alert: unknown }).alert = (
      title?: string,
      message?: string,
      buttons?: { text: string; onPress?: () => void; style?: 'default' | 'cancel' | 'destructive' }[],
    ) => {
      show({
        title,
        message: message ?? '',
        buttons: buttons && buttons.length > 0 ? buttons : [{ text: '确定' }],
      });
    };
    return () => {
      RNAlert.alert = original;
    };
  }, [show]);

  const handleCopy = async () => {
    const text = `${options.title ? options.title + '\n' : ''}${options.message}`;
    try {
      await Clipboard.setStringAsync(text);
    } catch {
      // expo-clipboard native module not available in this build
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const buttons = options.buttons ?? [{ text: '确定', onPress: close }];

  return (
    <AlertContext.Provider value={show}>
      {children}
      <Modal visible={visible} transparent animationType="fade" onRequestClose={close}>
        <Pressable style={styles.overlay} onPress={close}>
          <Pressable
            style={[styles.dialog, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            {options.title && (
              <Text style={[styles.title, { color: c.text }]}>{options.title}</Text>
            )}
            <Text
              style={[styles.message, { color: c.textSecondary }]}
              selectable
              onLongPress={handleCopy}
            >
              {options.message}
            </Text>

            {options.copyable !== false && (
              <Pressable
                onPress={handleCopy}
                style={({ pressed }) => [
                  styles.copyBtn,
                  { backgroundColor: copied ? c.success : c.borderLight, borderColor: c.border },
                  pressed && { opacity: 0.7 },
                ]}
              >
                <Text style={[styles.copyText, { color: copied ? '#FFF' : c.textSecondary }]}>
                  {copied ? '✓ 已复制' : '复制全部'}
                </Text>
              </Pressable>
            )}

            <View style={[styles.btnRow, { borderTopColor: c.borderLight }]}>
              {buttons.map((btn, i) => (
                <Pressable
                  key={i}
                  onPress={() => {
                    close();
                    btn.onPress?.();
                  }}
                  style={({ pressed }) => [
                    styles.btn,
                    i > 0 && { borderLeftColor: c.borderLight, borderLeftWidth: 1 },
                    pressed && { backgroundColor: c.background },
                  ]}
                >
                  <Text
                    style={[
                      styles.btnText,
                      {
                        color: btn.style === 'destructive' ? c.error : c.primary,
                        fontWeight: btn.style === 'cancel' ? '400' : '600',
                      },
                    ]}
                  >
                    {btn.text}
                  </Text>
                </Pressable>
              ))}
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </AlertContext.Provider>
  );
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.4)',
    padding: 40,
  },
  dialog: {
    width: '100%',
    maxWidth: 320,
    borderRadius: radius.lg,
    overflow: 'hidden',
  },
  title: {
    ...typography.heading,
    paddingTop: spacing.lg,
    paddingHorizontal: spacing.lg,
    textAlign: 'center',
  },
  message: {
    ...typography.body,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.sm,
    lineHeight: 22,
  },
  copyBtn: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.sm,
    paddingVertical: spacing.sm,
    borderRadius: radius.sm,
    borderWidth: 1,
    alignItems: 'center',
  },
  copyText: {
    ...typography.caption,
    fontWeight: '500',
  },
  btnRow: {
    flexDirection: 'row',
    borderTopWidth: 1,
  },
  btn: {
    flex: 1,
    paddingVertical: spacing.md,
    alignItems: 'center',
  },
  btnText: {
    ...typography.body,
  },
});
