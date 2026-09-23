import React from 'react';
import { View, Text, Pressable, StyleSheet } from 'react-native';
import { useColorScheme } from 'react-native';
import { colors, spacing, typography, radius, shadow } from '@/lib/theme';
import { ChevronRight } from 'lucide-react-native';

interface StatCardProps {
  label: string;
  value: string | number;
  /** lucide 图标组件 */
  icon?: React.ComponentType<{ size?: number; stroke?: string; color?: string }>;
  /** 图标底色背景 */
  accent?: string;
  /** 点击跳转（整卡可点） */
  onPress?: () => void;
}

/** 可点击统计卡：图标+大数值+标签+右箭头，对齐 web stat-card。 */
export function StatCard({ label, value, icon: Icon, accent, onPress }: StatCardProps) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const bg = accent ?? c.primaryLight;
  return (
    <Pressable
      onPress={onPress}
      disabled={!onPress}
      style={({ pressed }) => [
        styles.card,
        { backgroundColor: c.surface, borderColor: c.border, opacity: pressed ? 0.85 : 1 },
        shadow.card,
      ]}
    >
      <View style={styles.row}>
        {Icon && (
          <View style={[styles.icon, { backgroundColor: bg }]}>
            <Icon size={18} stroke={accent ? '#FFFFFF' : c.primary} />
          </View>
        )}
        <View style={styles.content}>
          <Text style={[styles.value, { color: c.text }]}>{value}</Text>
          <Text style={[styles.label, { color: c.textMuted }]}>{label}</Text>
        </View>
        {onPress && <ChevronRight size={16} stroke={c.textMuted} />}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: { flex: 1, borderRadius: radius.lg, padding: spacing.md, borderWidth: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  icon: { width: 36, height: 36, borderRadius: radius.md, alignItems: 'center', justifyContent: 'center' },
  content: { flex: 1 },
  value: { ...typography.title, fontWeight: '700' },
  label: { ...typography.small },
});
