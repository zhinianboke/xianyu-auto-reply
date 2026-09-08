import { useState } from 'react';
import { View, Text, StyleSheet, Pressable, ScrollView, TextInput } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useColorScheme } from 'react-native';
import { Card, Button } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { useAuthStore } from '@/stores/auth';
import { useConfigStore } from '@/stores/config';
import {
  User,
  Settings,
  Server,
  Info,
  LogOut,
  ChevronRight,
  MessageSquare,
  Filter,
  LayoutDashboard,
  Bell,
  BellOff,
  Megaphone,
  BarChart3,
  HelpCircle,
  FileText,
  ShoppingCart,
  Bug,
  Radar,
  Users,
  FolderTree,
  ScrollText,
  Share2,
  MessageCircle,
  Package,
  Wallet,
  Search,
  Terminal,
  UserCog,
  Shield,
  Send,
  Ticket,
  Ban,
  Sparkles,
  History,
  SlidersHorizontal,
  Clock,
  Database,
} from 'lucide-react-native';

type MenuItem = { label: string; icon: typeof User; onPress: () => void; adminOnly?: boolean };
type MenuSection = { title: string; items: MenuItem[] };

export default function MineScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const serverUrl = useConfigStore((s) => s.serverUrl);

  // 分组菜单（adminOnly: true 项仅管理员可见，与 Web 端导航一致；组内保持功能顺序）
  const menuSections: MenuSection[] = [
    {
      title: '核心功能',
      items: [
        { label: '仪表盘', icon: LayoutDashboard, onPress: () => router.push('/(tabs)/mine/dashboard') },
        { label: '商品搜索', icon: Search, onPress: () => router.push('/(tabs)/mine/search') },
        { label: '账号管理', icon: User, onPress: () => router.push('/(tabs)/mine/accounts') },
      ],
    },
    {
      title: '消息与回复',
      items: [
        { label: '关键词管理', icon: MessageSquare, onPress: () => router.push('/(tabs)/mine/keywords') },
        { label: '消息过滤', icon: Filter, onPress: () => router.push('/(tabs)/mine/message-filters') },
        { label: '卡券管理', icon: Ticket, onPress: () => router.push('/(tabs)/mine/cards') },
        { label: '黑名单管理', icon: Ban, onPress: () => router.push('/(tabs)/mine/blacklist') },
      ],
    },
    {
      title: '通知',
      items: [
        { label: '通知渠道', icon: Bell, onPress: () => router.push('/(tabs)/mine/notification-channels') },
        { label: '消息通知绑定', icon: Send, onPress: () => router.push('/(tabs)/mine/message-notifications') },
        { label: '通知管理', icon: BellOff, onPress: () => router.push('/(tabs)/mine/notifications') },
      ],
    },
    {
      title: '运营',
      items: [
        { label: '公告', icon: Megaphone, onPress: () => router.push('/(tabs)/mine/announcements') },
        { label: '数据分析', icon: BarChart3, onPress: () => router.push('/(tabs)/mine/data-analysis') },
        { label: '风控日志', icon: Shield, onPress: () => router.push('/(tabs)/mine/risk-logs') },
        { label: '反馈', icon: MessageCircle, onPress: () => router.push('/(tabs)/mine/feedback') },
        { label: '广告管理', icon: Megaphone, onPress: () => router.push('/(tabs)/mine/advertisements') },
      ],
    },
    {
      title: '分销与推广',
      items: [
        { label: '分销管理', icon: Wallet, onPress: () => router.push('/(tabs)/mine/distribution') },
        { label: '爬虫任务', icon: Bug, onPress: () => router.push('/(tabs)/mine/crawler') },
        { label: '上新监控', icon: Radar, onPress: () => router.push('/(tabs)/mine/listing-monitor') },
        { label: '监控分类', icon: FolderTree, onPress: () => router.push('/(tabs)/mine/monitor-categories') },
        { label: '监控日志', icon: ScrollText, onPress: () => router.push('/(tabs)/mine/monitor-logs') },
        { label: '兜底账号', icon: Users, onPress: () => router.push('/(tabs)/mine/monitor-fallback') },
        { label: '商品发布', icon: ShoppingCart, onPress: () => router.push('/(tabs)/mine/product-publish') },
        { label: '商品管理', icon: Package, onPress: () => router.push('/(tabs)/mine/items') },
        { label: 'AI 上架', icon: Sparkles, onPress: () => router.push('/(tabs)/mine/ai-listing') },
        { label: '上架历史', icon: History, onPress: () => router.push('/(tabs)/mine/ai-listing-history') },
        { label: 'AI 配置', icon: SlidersHorizontal, onPress: () => router.push('/(tabs)/mine/ai-listing-configs') },
        { label: '共享扫码', icon: Share2, onPress: () => router.push('/(tabs)/mine/shared-scan') },
      ],
    },
    {
      title: '设置',
      items: [
        { label: '系统设置', icon: Settings, onPress: () => router.push('/(tabs)/mine/settings'), adminOnly: true },
        { label: '个人设置', icon: UserCog, onPress: () => router.push('/(tabs)/mine/personal') },
      ],
    },
    {
      title: '日志',
      items: [
        { label: '日志查看', icon: ScrollText, onPress: () => router.push('/(tabs)/mine/logs'), adminOnly: true },
        { label: 'APP 日志', icon: Terminal, onPress: () => router.push('/(tabs)/mine/app-logs') },
      ],
    },
    {
      title: '管理',
      items: [
        { label: '用户管理', icon: Users, onPress: () => router.push('/(tabs)/mine/admin-users'), adminOnly: true },
        { label: '定时任务', icon: Clock, onPress: () => router.push('/(tabs)/mine/scheduled-tasks'), adminOnly: true },
        { label: '数据管理', icon: Database, onPress: () => router.push('/(tabs)/mine/data-management'), adminOnly: true },
      ],
    },
    {
      title: '其他',
      items: [
        { label: '免责声明', icon: FileText, onPress: () => router.push('/(tabs)/mine/disclaimer') },
        { label: '使用教程', icon: HelpCircle, onPress: () => router.push('/(tabs)/mine/tutorial') },
        { label: '关于', icon: Info, onPress: () => router.push('/(tabs)/mine/about') },
        { label: '服务器配置', icon: Server, onPress: () => router.push('/(onboarding)/server-config') },
      ],
    },
  ];

  // 按角色过滤：普通用户不显示管理员页面（与 Web 端 adminOnly 逻辑一致）；过滤后为空的组整体隐藏
  const [menuSearch, setMenuSearch] = useState('');
  const q = menuSearch.trim().toLowerCase();
  const visibleSections = menuSections
    .map((section) => ({
      ...section,
      items: (user?.is_admin ? section.items : section.items.filter((item) => !item.adminOnly))
        .filter((item) => !q || item.label.toLowerCase().includes(q)),
    }))
    .filter((section) => section.items.length > 0);

  async function handleLogout() {
    await logout();
    router.replace('/(onboarding)/login');
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: c.text }]}>我的</Text>
      </View>
      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        {/* 用户信息卡片 */}
        <View style={[styles.userCard, { backgroundColor: c.surface }]}>
          <View style={[styles.avatar, { backgroundColor: c.primary }]}>
            <Text style={styles.avatarText}>
              {user?.username?.charAt(0).toUpperCase() || '?'}
            </Text>
          </View>
          <View style={styles.userInfo}>
            <Text style={[styles.userName, { color: c.text }]}>
              {user?.username ?? '未知用户'}
            </Text>
            <View style={styles.tags}>
              <View style={[styles.tag, { backgroundColor: user?.is_admin ? c.primary : c.border }]}>
                <Text style={[styles.tagText, { color: user?.is_admin ? '#FFF' : c.textSecondary }]}>
                  {user?.is_admin ? '管理员' : '用户'}
                </Text>
              </View>
              {serverUrl && (
                <Text style={[styles.serverUrl, { color: c.textMuted }]} numberOfLines={1}>
                  {serverUrl}
                </Text>
              )}
            </View>
          </View>
        </View>

        {/* 菜单搜索（29 项过长，便于快速定位） */}
        <View style={[styles.menuSearch, { backgroundColor: c.surface, borderColor: c.border }]}>
          <Search size={16} stroke={c.textMuted} />
          <TextInput
            value={menuSearch}
            onChangeText={setMenuSearch}
            placeholder="搜索功能…"
            placeholderTextColor={c.textMuted}
            style={[styles.menuSearchInput, { color: c.text }]}
          />
          {menuSearch ? (
            <Pressable onPress={() => setMenuSearch('')} hitSlop={8}>
              <Text style={{ color: c.textMuted, fontSize: 18 }}>×</Text>
            </Pressable>
          ) : null}
        </View>

        {/* 菜单分组 */}
        {visibleSections.length > 0 ? visibleSections.map((section) => (
          <View key={section.title}>
            <Text style={[styles.sectionTitle, { color: c.textMuted }]}>{section.title}</Text>
            <View style={[styles.menuContainer, { backgroundColor: c.surface }]}>
              {section.items.map((item, index) => {
                const Icon = item.icon;
                return (
                  <Pressable
                    key={item.label}
                    onPress={item.onPress}
                    style={({ pressed }) => [
                      styles.menuItem,
                      index > 0 && { borderTopColor: c.borderLight, borderTopWidth: 1 },
                      pressed && { backgroundColor: c.background },
                    ]}
                  >
                    <Icon size={20} stroke={c.textSecondary} />
                    <Text style={[styles.menuLabel, { color: c.text }]}>{item.label}</Text>
                    <ChevronRight size={18} stroke={c.textMuted} />
                  </Pressable>
                );
              })}
            </View>
          </View>
        ))
        : (
          <View style={styles.menuContainer}>
            <Text style={[styles.menuLabel, { color: c.textMuted, paddingVertical: spacing.lg, textAlign: 'center' }]}>
              未找到匹配的功能
            </Text>
          </View>
        )}

        {/* 退出登录 */}
        <Button label="退出登录" onPress={handleLogout} variant="danger" style={styles.logoutBtn} />
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  title: { ...typography.title },
  // 菜单搜索栏
  menuSearch: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 8, borderWidth: 1, marginBottom: spacing.sm },
  menuSearchInput: { flex: 1, fontSize: 14, paddingVertical: 4 },
  content: { padding: spacing.lg, gap: spacing.lg, paddingBottom: 80 },
  userCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    borderRadius: radius.lg,
    padding: spacing.lg,
  },
  avatar: {
    width: 52,
    height: 52,
    borderRadius: 26,
    alignItems: 'center',
    justifyContent: 'center',
  },
  avatarText: { color: '#FFF', fontSize: 24, fontWeight: '700' },
  userInfo: { flex: 1, gap: spacing.xs },
  userName: { ...typography.title, fontSize: 18 },
  tags: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  tag: { paddingHorizontal: spacing.sm, paddingVertical: 3, borderRadius: 6 },
  tagText: { fontSize: 11, fontWeight: '600' },
  serverUrl: { ...typography.small, flex: 1 },
  sectionTitle: {
    ...typography.caption,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    marginBottom: spacing.sm,
    paddingHorizontal: spacing.xs,
  },
  menuContainer: {
    borderRadius: radius.lg,
    padding: 0,
    overflow: 'hidden',
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    gap: spacing.md,
  },
  menuLabel: { ...typography.body, flex: 1 },
  logoutBtn: { marginTop: spacing.xs },
});
