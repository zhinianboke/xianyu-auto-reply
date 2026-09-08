import type { ReactNode } from 'react';
import {
  Modal,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  View,
  Text,
  StyleSheet,
  useColorScheme,
  type StyleProp,
  type ViewStyle,
} from 'react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';

export interface FormModalProps {
  visible: boolean;
  onClose: () => void;
  /** 标题栏文案；不传则不渲染标题栏（内容自带关闭入口） */
  title?: string;
  children: ReactNode;
  /** 覆盖内容容器样式（如自定义 maxHeight） */
  contentStyle?: StyleProp<ViewStyle>;
}

/**
 * 表单底部弹层：Modal + KeyboardAvoidingView，键盘弹出时输入区不会被遮挡。
 * iOS 用 padding 抬升弹层；Android 依赖系统 adjustResize，无需额外处理。
 */
export function FormModal({
  visible,
  onClose,
  title,
  children,
  contentStyle,
}: FormModalProps) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}
    >
      <KeyboardAvoidingView
        style={styles.avoid}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <Pressable style={styles.sheetOverlay} onPress={onClose}>
          <Pressable
            style={[styles.sheet, { backgroundColor: c.surface }, contentStyle]}
            onPress={() => {}}
          >
            <View style={[styles.handle, { backgroundColor: c.border }]} />
            {title ? (
              <View style={styles.header}>
                <Text style={[styles.title, { color: c.text }]}>{title}</Text>
                <Pressable onPress={onClose} hitSlop={8}>
                  <Text style={[styles.close, { color: c.textMuted }]}>✕</Text>
                </Pressable>
              </View>
            ) : null}
            {children}
          </Pressable>
        </Pressable>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  avoid: { flex: 1, justifyContent: 'flex-end' },
  sheetOverlay: {
    flex: 1,
    justifyContent: 'flex-end',
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  sheet: {
    maxHeight: '90%',
    borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl,
    padding: spacing.lg,
    paddingBottom: spacing.xl,
    gap: spacing.md,
    overflow: 'hidden',
  },
  handle: {
    width: 36,
    height: 4,
    borderRadius: 2,
    alignSelf: 'center',
    marginBottom: spacing.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: { ...typography.heading, flex: 1 },
  close: { fontSize: 22, paddingHorizontal: spacing.xs },
});
