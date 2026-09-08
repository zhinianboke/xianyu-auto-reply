import React from 'react';
import { View, Text, StyleSheet } from 'react-native';
import { useColorScheme } from 'react-native';
import { colors, typography, radius } from '@/lib/theme';

type BadgeVariant = 'primary' | 'success' | 'warning' | 'danger' | 'info' | 'gray';

interface BadgeProps {
  label: string;
  variant?: BadgeVariant;
  style?: object;
}

/** 状态徽章，对齐 web badge-ios：100 底 + 800 字，rounded sm，text-xs 500。 */
export function Badge({ label, variant = 'gray', style }: BadgeProps) {
  const scheme = useColorScheme();
  const dark = scheme === 'dark';
  const palette: Record<BadgeVariant, { bg: string; fg: string }> = {
    primary: { bg: dark ? '#1E3A8F' : '#DBEAFE', fg: dark ? '#BFDBFE' : '#1E40AF' },
    success: { bg: dark ? '#052E16' : '#DCFCE7', fg: dark ? '#86EFAC' : '#166534' },
    warning: { bg: dark ? '#422006' : '#FEF3C7', fg: dark ? '#FCD34D' : '#92400E' },
    danger: { bg: dark ? '#450A0A' : '#FEE2E2', fg: dark ? '#FCA5A5' : '#991B1B' },
    info: { bg: dark ? '#082F49' : '#E0F2FE', fg: dark ? '#7DD3FC' : '#075985' },
    gray: { bg: dark ? '#334155' : '#F1F5F9', fg: dark ? '#CBD5E1' : '#475569' },
  };
  const p = palette[variant];
  return (
    <View style={[styles.badge, { backgroundColor: p.bg }, style]}>
      <Text style={[styles.text, { color: p.fg }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: radius.sm,
    alignSelf: 'flex-start',
  },
  text: { ...typography.small, fontWeight: '500', fontSize: 11 },
});
