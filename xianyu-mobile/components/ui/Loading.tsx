import React from 'react';
import { View, ActivityIndicator, Text, StyleSheet } from 'react-native';
import { useColorScheme } from 'react-native';
import { colors, spacing, typography } from '@/lib/theme';

export function Loading({ label = '加载中...' }: { label?: string }) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  return (
    <View style={styles.container}>
      <ActivityIndicator size="large" color={c.primary} />
      <Text style={[styles.text, { color: c.textMuted }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: spacing.md },
  text: { ...typography.caption },
});
