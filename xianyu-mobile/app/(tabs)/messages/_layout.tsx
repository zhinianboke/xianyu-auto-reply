import { Stack } from 'expo-router';
import { useColorScheme } from 'react-native';
import { colors, typography } from '@/lib/theme';

export default function MessagesStackLayout() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: c.surface },
        headerTintColor: c.text,
        headerTitleStyle: { ...typography.heading },
        headerShadowVisible: false,
        headerBackButtonDisplayMode: 'minimal',
        // 安卓全屏手势返回
        gestureEnabled: true,
        fullScreenGestureEnabled: true,
      }}
    >
      <Stack.Screen name="index" options={{ headerShown: false }} />
      <Stack.Screen name="[id]" options={{ title: '聊天' }} />
    </Stack>
  );
}
