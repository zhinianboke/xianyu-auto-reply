import { Tabs } from 'expo-router';
import { useColorScheme } from 'react-native';
// StackActions 未在 expo-router 顶层导出，从其内置 react-navigation routers 取用
import { StackActions } from 'expo-router/build/react-navigation/routers';
import { colors, typography } from '@/lib/theme';
import { MessageCircle, ClipboardList, ShoppingBag, User } from 'lucide-react-native';

export default function TabsLayout() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  return (
    <Tabs
      screenOptions={{
        // Tab 层不再显示头部：内层原生 Stack 头部会自己处理状态栏，
        // 若两层头部同时显示，二级页顶部会出现一条状态栏高度的死区
        headerShown: false,
        tabBarStyle: {
          backgroundColor: c.surface,
          borderTopColor: c.borderLight,
          borderTopWidth: 1,
          elevation: 0,
          height: 56,
          paddingBottom: 4,
          paddingTop: 4,
        },
        tabBarActiveTintColor: c.primary,
        tabBarInactiveTintColor: c.textMuted,
        tabBarLabelStyle: { ...typography.micro, marginTop: 2 },
      }}
    >
      <Tabs.Screen
        name="messages"
        options={{ title: '消息', tabBarIcon: ({ color }) => <MessageCircle size={22} stroke={color} /> }}
        // 切到"消息"tab 时把内层 messages Stack 弹回根(会话列表)，避免停在某个聊天详情
        listeners={({ navigation }: { navigation: { getState: () => { routes: { name: string; state?: { key?: string } }[] }; dispatch: (a: unknown) => void } }) => ({
          tabPress: () => {
            const route = navigation.getState().routes.find((r) => r.name === 'messages');
            const nestedKey = route?.state?.key;
            if (nestedKey) {
              navigation.dispatch({ ...StackActions.popToTop(), target: nestedKey });
            }
          },
        })}
      />
      <Tabs.Screen
        name="orders"
        options={{ title: '订单', tabBarIcon: ({ color }) => <ClipboardList size={22} stroke={color} /> }}
      />
      <Tabs.Screen
        name="products"
        options={{ title: '商品', tabBarIcon: ({ color }) => <ShoppingBag size={22} stroke={color} /> }}
      />
      <Tabs.Screen
        name="mine"
        options={{ title: '我的', tabBarIcon: ({ color }) => <User size={22} stroke={color} /> }}
        listeners={({ navigation }) => ({
          tabPress: () => {
            // 切到"我的"tab 时把内层 mine Stack 弹回根(菜单)，避免停在子页显示其他页面
            const mineRoute = navigation
              .getState()
              .routes.find((r: { name: string; state?: { key?: string } }) => r.name === 'mine');
            const nestedKey = mineRoute?.state?.key;
            if (nestedKey) {
              navigation.dispatch({ ...StackActions.popToTop(), target: nestedKey });
            }
          },
        })}
      />
    </Tabs>
  );
}
