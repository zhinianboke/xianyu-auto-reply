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
        // 调用方 style 须放在背景色之后，否则 textarea 等传入的浅色背景会被覆盖
        props.style,
      ]}
      {...props}
    />
  );
}

const styles = StyleSheet.create({
  input: {
    ...typography.body,
    // 多行文本在部分安卓机型上受 50px 最小高度挤压导致前两行不可见，
    // 改用垂直内边距撑开高度，单行/多行都能正常显示
    paddingVertical: 12,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    borderWidth: 1,
  },
});
