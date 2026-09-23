import React from 'react';
import { Pressable, Text, StyleSheet } from 'react-native';
import { useColorScheme } from 'react-native';
import { colors, typography, radius, shadow } from '@/lib/theme';
import { Plus } from 'lucide-react-native';

interface FABProps {
  onPress: () => void;
  label?: string;
}

/** 悬浮主操作按钮（添加…），右下角，对齐 web "新建" CTA 提升可达性。 */
export function FAB({ onPress, label }: FABProps) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  if (label) {
    return (
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [
          styles.extended,
          { backgroundColor: c.primary, opacity: pressed ? 0.85 : 1 },
          shadow.floating,
        ]}
      >
        <Plus size={20} stroke="#FFFFFF" />
        <Text style={styles.label}>{label}</Text>
      </Pressable>
    );
  }
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        styles.round,
        { backgroundColor: c.primary, opacity: pressed ? 0.85 : 1 },
        shadow.floating,
      ]}
    >
      <Plus size={24} stroke="#FFFFFF" />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  round: { position: 'absolute', right: 16, bottom: 76, width: 56, height: 56, borderRadius: 28, alignItems: 'center', justifyContent: 'center' },
  extended: { position: 'absolute', right: 16, bottom: 76, height: 48, paddingHorizontal: 16, borderRadius: 24, flexDirection: 'row', alignItems: 'center', gap: 6 },
  label: { color: '#FFFFFF', ...typography.body, fontWeight: '600' },
});
