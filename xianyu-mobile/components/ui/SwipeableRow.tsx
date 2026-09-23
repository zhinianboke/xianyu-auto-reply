import React, { useRef } from 'react';
import { View, Text, Pressable, StyleSheet, PanResponder, Animated, type ViewStyle } from 'react-native';
import { useColorScheme } from 'react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';

export interface SwipeAction {
  label: string;
  onPress: () => void;
  bg: string;
  fg?: string;
}

interface SwipeableRowProps {
  children: React.ReactNode;
  /** 右滑显露的右侧操作按钮（从外到内） */
  actions?: SwipeAction[];
  style?: ViewStyle;
  onPress?: () => void;
}

/**
 * 左滑显露操作按钮的列表行。轻量自实现（PanResponder + Animated），
 * 不引入 react-native-gesture-handler/swipeable，保持依赖不变。
 */
export function SwipeableRow({ children, actions = [], style, onPress }: SwipeableRowProps) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const translateX = useRef(new Animated.Value(0)).current;
  const openWidth = actions.length * 72;

  const pan = useRef(
    PanResponder.create({
      onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dx) > 8 && Math.abs(g.dx) > Math.abs(g.dy),
      onPanResponderMove: (_, g) => {
        const next = Math.min(0, Math.max(-openWidth, g.dx));
        translateX.setValue(next);
      },
      onPanResponderRelease: (_, g) => {
        if (g.dx < -openWidth / 2) {
          Animated.spring(translateX, { toValue: -openWidth, useNativeDriver: false, friction: 8 }).start();
        } else {
          Animated.spring(translateX, { toValue: 0, useNativeDriver: false, friction: 8 }).start();
        }
      },
    }),
  ).current;

  return (
    <View style={[styles.container, style]}>
      {actions.length > 0 && (
        <View style={styles.actions} pointerEvents="box-none">
          {actions.map((a) => (
            <Pressable
              key={a.label}
              onPress={() => {
                Animated.spring(translateX, { toValue: 0, useNativeDriver: false }).start();
                a.onPress();
              }}
              style={[styles.action, { backgroundColor: a.bg }]}
            >
              <Text style={[styles.actionText, { color: a.fg ?? '#FFFFFF' }]}>{a.label}</Text>
            </Pressable>
          ))}
        </View>
      )}
      <Animated.View
        {...pan.panHandlers}
        style={[styles.row, { backgroundColor: c.surface, transform: [{ translateX }] }]}
      >
        {onPress ? (
          <Pressable onPress={onPress} style={styles.rowInner}>
            {children}
          </Pressable>
        ) : (
          children
        )}
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { position: 'relative', overflow: 'hidden' },
  actions: {
    position: 'absolute', top: 0, right: 0, bottom: 0,
    flexDirection: 'row',
  },
  action: { width: 72, justifyContent: 'center', alignItems: 'center' },
  actionText: { ...typography.small, fontWeight: '600' },
  row: { flex: 1 },
  rowInner: { flex: 1 },
});
