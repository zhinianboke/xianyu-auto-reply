import React from 'react';
import { View, Text, Pressable, StyleSheet, ScrollView } from 'react-native';
import { useColorScheme } from 'react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';

export interface FilterTab {
  key: string;
  label: string;
  count?: number;
}

interface FilterTabsProps {
  tabs: FilterTab[];
  active: string;
  onChange: (key: string) => void;
}

/** 横向状态筛选 tab（全部/待发货/已完成…），对齐 web 顶栏 tab 风格。 */
export function FilterTabs({ tabs, active, onChange }: FilterTabsProps) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.container}>
      {tabs.map((t) => {
        const on = active === t.key;
        return (
          <Pressable
            key={t.key}
            onPress={() => onChange(t.key)}
            style={[
              styles.tab,
              { backgroundColor: on ? c.primary : c.surface, borderColor: on ? c.primary : c.border },
            ]}
          >
            <Text style={[styles.label, { color: on ? '#FFFFFF' : c.textSecondary }]}>
              {t.label}
              {t.count != null ? ` ${t.count}` : ''}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: { paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, gap: spacing.sm, alignItems: 'center' },
  tab: { paddingHorizontal: spacing.md, height: 34, borderRadius: radius.full, borderWidth: 1, alignItems: 'center', justifyContent: 'center' },
  label: { fontSize: 13, fontWeight: '500', lineHeight: 18 },
});
