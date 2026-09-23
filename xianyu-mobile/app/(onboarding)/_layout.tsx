import { Stack } from 'expo-router';
import { useColorScheme } from 'react-native';
import { colors, typography } from '@/lib/theme';

export default function OnboardingLayout() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  return (
    <Stack
      screenOptions={{
        headerShown: false,
        headerStyle: { backgroundColor: c.surface },
        headerTintColor: c.text,
        headerTitleStyle: { ...typography.heading },
        headerShadowVisible: false,
        headerBackButtonDisplayMode: 'minimal',
      }}
    >
      {/* 服务器配置页启用头部+返回按钮：从「我的」进入时可返回，首启无上一级则退出（可接受） */}
      <Stack.Screen name="server-config" options={{ headerShown: true, title: '服务器配置' }} />
    </Stack>
  );
}
