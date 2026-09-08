import React from 'react';
import { View, StyleSheet, type ViewProps } from 'react-native';
import { useColorScheme } from 'react-native';
import { colors, spacing, radius, shadow } from '@/lib/theme';

export function Card({ children, style, ...props }: ViewProps) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  return (
    <View
      style={[
        styles.card,
        { backgroundColor: c.surface, borderColor: c.borderLight },
        shadow.card,
        style,
      ]}
      {...props}
    >
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radius.lg,
    padding: spacing.md,
    borderWidth: 1,
  },
});
