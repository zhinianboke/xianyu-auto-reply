import { Stack } from 'expo-router';
import { useColorScheme } from 'react-native';
import { colors, typography } from '@/lib/theme';

export default function MineStackLayout() {
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
      }}
    >
      <Stack.Screen name="index" options={{ headerShown: false }} />
      <Stack.Screen name="dashboard" options={{ title: '仪表盘' }} />
      <Stack.Screen name="search" options={{ title: '商品搜索' }} />
      <Stack.Screen name="accounts" options={{ title: '账号管理' }} />
      <Stack.Screen name="keywords" options={{ title: '关键词管理' }} />
      <Stack.Screen name="message-filters" options={{ title: '消息过滤' }} />
      <Stack.Screen name="notifications" options={{ title: '通知管理' }} />
      <Stack.Screen name="announcements" options={{ title: '公告' }} />
      <Stack.Screen name="data-analysis" options={{ title: '数据分析' }} />
      <Stack.Screen name="feedback" options={{ title: '反馈' }} />
      <Stack.Screen name="advertisements" options={{ title: '广告管理' }} />
      <Stack.Screen name="distribution" options={{ title: '分销管理' }} />
      <Stack.Screen name="distribution-supply" options={{ title: '货源广场' }} />
      <Stack.Screen name="distribution-pickup" options={{ title: '分销卡券' }} />
      <Stack.Screen name="distribution-sub-dealers" options={{ title: '下级分销商' }} />
      <Stack.Screen name="crawler" options={{ title: '爬虫任务' }} />
      <Stack.Screen name="listing-monitor" options={{ title: '上新监控' }} />
      <Stack.Screen name="monitor-categories" options={{ title: '监控分类' }} />
      <Stack.Screen name="monitor-logs" options={{ title: '监控日志' }} />
      <Stack.Screen name="monitor-fallback" options={{ title: '兜底账号' }} />
      <Stack.Screen name="product-publish" options={{ title: '商品发布' }} />
      <Stack.Screen name="items" options={{ title: '商品管理' }} />
      <Stack.Screen name="item-edit" options={{ title: '编辑商品' }} />
      <Stack.Screen name="shared-scan" options={{ title: '共享扫码' }} />
      <Stack.Screen name="settings" options={{ title: '系统设置' }} />
      <Stack.Screen name="personal" options={{ title: '个人设置' }} />
      <Stack.Screen name="logs" options={{ title: '日志查看' }} />
      <Stack.Screen name="app-logs" options={{ title: 'APP 日志' }} />
      <Stack.Screen name="admin-users" options={{ title: '用户管理' }} />
      <Stack.Screen name="disclaimer" options={{ title: '免责声明' }} />
      <Stack.Screen name="tutorial" options={{ title: '使用教程' }} />
      <Stack.Screen name="about" options={{ title: '关于' }} />
      <Stack.Screen name="cards" options={{ title: '卡券管理' }} />
      <Stack.Screen name="card-item-relation" options={{ title: '关联商品' }} />
      <Stack.Screen name="blacklist" options={{ title: '黑名单管理' }} />
      <Stack.Screen name="risk-logs" options={{ title: '风控日志' }} />
      <Stack.Screen name="notification-channels" options={{ title: '通知渠道' }} />
      <Stack.Screen name="message-notifications" options={{ title: '消息通知绑定' }} />
      <Stack.Screen name="ai-listing" options={{ title: 'AI 上架' }} />
      <Stack.Screen name="ai-listing-history" options={{ title: '上架历史' }} />
      <Stack.Screen name="ai-listing-configs" options={{ title: 'AI 配置' }} />
      <Stack.Screen name="scheduled-tasks" options={{ title: '定时任务' }} />
      <Stack.Screen name="data-management" options={{ title: '数据管理' }} />
      <Stack.Screen name="items" options={{ title: '商品管理' }} />
    </Stack>
  );
}
