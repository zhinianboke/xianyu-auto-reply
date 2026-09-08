import { View, Text, StyleSheet } from 'react-native';
import { spacing, typography, type ThemeColors } from '@/lib/theme';

/** 订单详情弹窗中的「标签 + 值」展示行 */
export function DetailRow({
  label,
  value,
  c,
}: {
  label: string;
  value: string;
  c: ThemeColors;
}) {
  return (
    <View style={styles.detailRow}>
      <Text style={[styles.detailLabel, { color: c.textMuted }]}>{label}</Text>
      <Text style={[styles.detailValue, { color: c.text }]}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  detailRow: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
  },
  detailLabel: { ...typography.caption, width: 72, flexShrink: 0 },
  detailValue: { ...typography.body, flex: 1, flexWrap: 'wrap' },
});
