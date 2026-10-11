import { Tabs } from 'expo-router';
import { useColorScheme } from 'react-native';
import { colors, typography } from '@/lib/theme';
import { MessageCircle, ClipboardList, ShoppingBag, User } from 'lucide-react-native';

export default function TabsLayout() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  // 切 tab 时把该 tab 的内层 Stack 弹回根页。
  // 不能用 StackActions.popToTop()+target：expo-router 内联 stack router 不响应该 action，
  // 实测无效；navigate 到栈中必然存在的根路由 'index' 会触发回退（pop）到它。
  const popTabToRoot = (navigation: { navigate: (name: string, params: object) => void }) => (name: string) => {
    (navigation as unknown as { navigate: (name: string, params: object) => void }).navigate(name, { screen: 'index' });
  };

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
        listeners={({ navigation }) => ({
          tabPress: () => popTabToRoot(navigation as never)('messages'),
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
          tabPress: () => popTabToRoot(navigation as never)('mine'),
        })}
      />
    </Tabs>
  );
}
