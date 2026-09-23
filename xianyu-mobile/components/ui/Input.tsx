import React from 'react';
import { TextInput, StyleSheet, type TextInputProps } from 'react-native';
import { useColorScheme } from 'react-native';
import { colors, typography, radius, spacing } from '@/lib/theme';

export function Input(props: TextInputProps) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  return (
    <TextInput
      placeholderTextColor={c.textMuted}
      style={[
        styles.input,
        { backgroundColor: c.background, color: c.text, borderColor: c.border },
      ]}
      {...props}
    />
  );
}

const styles = StyleSheet.create({
  input: {
    ...typography.body,
    minHeight: 50,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
  },
});
