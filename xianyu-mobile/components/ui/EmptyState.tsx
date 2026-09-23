import React from 'react';
import { View, Text, StyleSheet, Pressable } from 'react-native';
import { useColorScheme } from 'react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';

interface EmptyStateProps {
  /** lucide 图标组件，如 MessageCircle */
  icon?: React.ComponentType<{ size?: number; stroke?: string }>;
  title: string;
  message?: string;
  /** 错误模式：图标/标题用 error 色，配合 onRetry 显示重试按钮 */
  error?: boolean;
  onRetry?: () => void;
  /** 主操作 CTA（如"添加监控商品"），主色实心按钮 */
  actionLabel?: string;
  onAction?: () => void;
}

export function EmptyState({
  icon: Icon,
  title,
  message,
  error = false,
  onRetry,
  actionLabel,
  onAction,
}: EmptyStateProps) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const tone = error ? c.error : c.textMuted;

  return (
    <View style={styles.container}>
      {Icon && <Icon size={48} stroke={tone} />}
      <Text style={[styles.title, { color: tone }]}>{title}</Text>
      {message ? (
        <Text style={[styles.message, { color: c.textMuted }]}>{message}</Text>
      ) : null}
      {error && onRetry ? (
        <Pressable
          onPress={onRetry}
          style={({ pressed }) => [
            styles.retryBtn,
            { borderColor: c.error, opacity: pressed ? 0.7 : 1 },
          ]}
        >
          <Text style={[styles.retryText, { color: c.error }]}>重试</Text>
        </Pressable>
      ) : null}
      {actionLabel && onAction ? (
        <Pressable
          onPress={onAction}
          style={({ pressed }) => [
            styles.ctaBtn,
            { backgroundColor: c.primary, opacity: pressed ? 0.85 : 1 },
          ]}
        >
          <Text style={styles.ctaText}>{actionLabel}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: spacing.xxxl,
    paddingHorizontal: spacing.xl,
    gap: spacing.sm,
  },
  title: { ...typography.body, textAlign: 'center' },
  message: { ...typography.caption, textAlign: 'center' },
  retryBtn: {
    marginTop: spacing.xs,
    paddingHorizontal: spacing.xl,
    paddingVertical: spacing.sm,
    borderRadius: radius.full,
    borderWidth: 1,
  },
  retryText: { ...typography.caption, fontWeight: '600' },
  ctaBtn: { marginTop: spacing.sm, paddingHorizontal: spacing.xl, paddingVertical: spacing.sm + 2, borderRadius: radius.md },
  ctaText: { color: '#FFFFFF', ...typography.caption, fontWeight: '600' },
});
