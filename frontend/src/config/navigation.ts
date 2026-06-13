import type React from 'react'
import {
  AlertTriangle,
  Ban,
  BarChart3,
  Bell,
  BellOff,
  BookOpen,
  Database,
  FileText,
  Filter,
  Flower2,
  Image,
  Info,
  Key,
  Layers,
  LayoutDashboard,
  LineChart,
  Link2,
  LogIn,
  MapPin,
  Megaphone,
  MessageCircle,
  MessageSquare,
  MessageSquarePlus,
  Package,
  PackageCheck,
  PackageSearch,
  Repeat,
  ScrollText,
  Send,
  Settings,
  Shield,
  ShoppingCart,
  Star,
  Store,
  Ticket,
  Timer,
  UserCog,
  Users,
  Wallet,
} from 'lucide-react'

export interface NavItem {
  key: string
  icon: React.ElementType
  label: string
  path: string
  adminOnly?: boolean
}

export interface NavGroup {
  key: string
  icon: React.ElementType
  label: string
  adminOnly?: boolean
  children: NavItem[]
}

export type NavEntry = NavItem | NavGroup

export interface FirstLevelMenuOption {
  key: string
  label: string
}

export const HIDDEN_MENU_SETTING_KEY = 'navigation.hidden_menu_keys'
export const EXE_FORCED_HIDDEN_MENU_KEYS = ['product-publish'] as const

const EXE_BLOCKED_PATH_PREFIXES = ['/accounts/shared-scan', '/shared-scan']

export function isNavGroup(entry: NavEntry): entry is NavGroup {
  return 'children' in entry
}

export const mainNavItems: NavEntry[] = [
  { key: 'dashboard', icon: LayoutDashboard, label: '仪表盘', path: '/dashboard' },
  {
    key: 'data-analysis',
    icon: BarChart3,
    label: '数据分析',
    children: [
      { key: 'data-overview', icon: LineChart, label: '数据总览', path: '/data-analysis/overview' },
    ],
  },
  { key: 'accounts', icon: Users, label: '账号管理', path: '/accounts' },
  { key: 'online-chat-new', icon: MessageSquare, label: '在线聊天', path: '/online-chat-new' },
  { key: 'items', icon: Package, label: '商品管理', path: '/items' },
  { key: 'cards', icon: Ticket, label: '卡券管理', path: '/cards' },
  { key: 'orders', icon: ShoppingCart, label: '订单管理', path: '/orders' },
  {
    key: 'distribution',
    icon: PackageSearch,
    label: '分销管理',
    children: [
      { key: 'distribution-sources', icon: Link2, label: '货源管理', path: '/distribution/sources' },
      { key: 'distribution-supply', icon: PackageSearch, label: '货源广场', path: '/distribution/supply' },
      { key: 'distribution-card-pickup', icon: Ticket, label: '分销卡券', path: '/distribution/card-pickup' },
      { key: 'distribution-docked', icon: PackageCheck, label: '对接的商品', path: '/distribution/docked' },
      { key: 'distribution-agent-orders', icon: ShoppingCart, label: '代理订单', path: '/distribution/agent-orders' },
      { key: 'distribution-dealers', icon: Users, label: '分销商管理', path: '/distribution/dealers' },
      { key: 'distribution-sub-dealers', icon: Users, label: '下级分销商', path: '/distribution/sub-dealers' },
    ],
  },
  {
    key: 'product-publish',
    icon: Store,
    label: '商品发布',
    children: [
      { key: 'product-publish-materials', icon: Image, label: '素材库', path: '/product-publish/materials' },
      { key: 'product-publish-single', icon: Send, label: '单品发布', path: '/product-publish/single' },
      { key: 'product-publish-batch', icon: Layers, label: '批量发布', path: '/product-publish/batch' },
      { key: 'product-publish-addresses', icon: MapPin, label: '随机地址库', path: '/product-publish/addresses' },
      { key: 'product-publish-logs', icon: ScrollText, label: '发布日志', path: '/product-publish/logs' },
    ],
  },
  { key: 'keywords', icon: MessageSquare, label: '自动回复', path: '/keywords' },
  { key: 'message-logs', icon: ScrollText, label: '消息日志', path: '/message-logs' },
  { key: 'risk-logs', icon: Shield, label: '风控日志', path: '/risk-logs' },
  { key: 'message-filters', icon: Filter, label: '消息过滤', path: '/message-filters' },
  { key: 'notification-channels', icon: Bell, label: '通知渠道', path: '/notification-channels' },
  { key: 'message-notifications', icon: MessageCircle, label: '消息通知', path: '/message-notifications' },
  { key: 'blacklist', icon: Ban, label: '黑名单管理', path: '/blacklist' },
  { key: 'personal-settings', icon: UserCog, label: '个人设置', path: '/personal-settings' },
]

export const adminNavItems: NavEntry[] = [
  { key: 'settings', icon: Settings, label: '系统设置', path: '/settings', adminOnly: true },
  { key: 'admin-users', icon: UserCog, label: '用户管理', path: '/admin/users', adminOnly: true },
  {
    key: 'admin-logs',
    icon: ScrollText,
    label: '日志管理',
    adminOnly: true,
    children: [
      { key: 'admin-system-logs', icon: FileText, label: '系统日志', path: '/admin/logs', adminOnly: true },
      { key: 'admin-redelivery-batches', icon: Repeat, label: '补发货日志', path: '/admin/redelivery-batches', adminOnly: true },
      { key: 'admin-account-login-logs', icon: LogIn, label: '账号登录日志', path: '/admin/account-login-logs', adminOnly: true },
      { key: 'admin-rate-batches', icon: Star, label: '补评价日志', path: '/admin/rate-batches', adminOnly: true },
      { key: 'admin-polish-batches', icon: Star, label: '擦亮日志', path: '/admin/polish-batches', adminOnly: true },
      { key: 'admin-login-renew-batches', icon: Key, label: '登录续期日志', path: '/admin/login-renew-batches', adminOnly: true },
      { key: 'admin-cookies-refresh-batches', icon: Key, label: 'COOKIES刷新日志', path: '/admin/cookies-refresh-batches', adminOnly: true },
      { key: 'admin-api-cookie-renew-batches', icon: Key, label: '接口续期Cookies日志', path: '/admin/api-cookie-renew-batches', adminOnly: true },
      { key: 'admin-close-notice-batches', icon: BellOff, label: '消息通知关闭日志', path: '/admin/close-notice-batches', adminOnly: true },
      { key: 'admin-red-flower-batches', icon: Flower2, label: '求小红花日志', path: '/admin/red-flower-batches', adminOnly: true },
      { key: 'admin-db-backup-logs', icon: Database, label: '数据库备份日志', path: '/admin/db-backup-logs', adminOnly: true },
    ],
  },
  { key: 'admin-scheduled-tasks', icon: Timer, label: '定时任务', path: '/admin/scheduled-tasks', adminOnly: true },
  { key: 'admin-announcements', icon: Megaphone, label: '公告管理', path: '/admin/announcements', adminOnly: true },
  { key: 'admin-ad-manage', icon: Image, label: '广告管理', path: '/admin/ad-manage', adminOnly: true },
  { key: 'admin-fund-flows', icon: Wallet, label: '资金流水', path: '/admin/fund-flows', adminOnly: true },
]

export const bottomNavItems: NavItem[] = [
  { key: 'tutorial', icon: BookOpen, label: '使用教程', path: '/tutorial' },
  { key: 'feedback', icon: MessageSquarePlus, label: '意见反馈', path: '/feedback' },
  { key: 'ad-apply', icon: Image, label: '广告申请', path: '/ad-apply' },
  { key: 'disclaimer', icon: AlertTriangle, label: '免责声明', path: '/disclaimer' },
  { key: 'about', icon: Info, label: '关于', path: '/about' },
]

const hideableFirstLevelMenuOptions: FirstLevelMenuOption[] = [...mainNavItems, ...bottomNavItems]
  .filter((entry) => !('adminOnly' in entry && entry.adminOnly))
  .map((entry) => ({ key: entry.key, label: entry.label }))

function matchesPath(currentPath: string, targetPath: string): boolean {
  return currentPath === targetPath || currentPath.startsWith(`${targetPath}/`)
}

export function getExeForcedHiddenMenuKeys(isExeMode: boolean): string[] {
  return isExeMode ? Array.from(EXE_FORCED_HIDDEN_MENU_KEYS) : []
}

function isExeBlockedPath(path: string, isExeMode: boolean): boolean {
  if (!isExeMode) {
    return false
  }
  return EXE_BLOCKED_PATH_PREFIXES.some((targetPath) => matchesPath(path, targetPath))
}

export function getHideableFirstLevelMenuOptions(excludedMenuKeys: string[] = []): FirstLevelMenuOption[] {
  if (excludedMenuKeys.length === 0) {
    return hideableFirstLevelMenuOptions
  }
  return hideableFirstLevelMenuOptions.filter((option) => !excludedMenuKeys.includes(option.key))
}

export function getVisibleNavEntries(entries: NavEntry[], hiddenMenuKeys: string[], isAdmin: boolean, isExeMode: boolean = false): NavEntry[] {
  const forcedHiddenMenuKeys = getExeForcedHiddenMenuKeys(isExeMode)
  return entries.filter((entry) => {
    if (forcedHiddenMenuKeys.includes(entry.key)) {
      return false
    }
    if (entry.adminOnly && !isAdmin) {
      return false
    }
    if (!isAdmin && hiddenMenuKeys.includes(entry.key)) {
      return false
    }
    return true
  })
}

export function getVisibleBottomNavItems(items: NavItem[], hiddenMenuKeys: string[], isAdmin: boolean, isExeMode: boolean = false): NavItem[] {
  const forcedHiddenMenuKeys = getExeForcedHiddenMenuKeys(isExeMode)
  if (isAdmin) {
    return items.filter((item) => !forcedHiddenMenuKeys.includes(item.key))
  }
  return items.filter((item) => !hiddenMenuKeys.includes(item.key) && !forcedHiddenMenuKeys.includes(item.key))
}

const routeParentKeyMap: Record<string, string> = {
  '/accounts/shared-scan': 'accounts',
  '/shared-scan': 'accounts',
}

function getRouteParentEntry(path: string): NavEntry | NavItem | null {
  const parentKey = Object.entries(routeParentKeyMap).find(([routePath]) => matchesPath(path, routePath))?.[1]
  if (!parentKey) {
    return null
  }

  const allEntries: Array<NavEntry | NavItem> = [...mainNavItems, ...adminNavItems, ...bottomNavItems]
  return allEntries.find((entry) => entry.key === parentKey) || null
}

export function getTopLevelMenuEntryByPath(path: string): NavEntry | NavItem | null {
  const routeParentEntry = getRouteParentEntry(path)
  if (routeParentEntry) {
    return routeParentEntry
  }

  const allEntries: NavEntry[] = [...mainNavItems, ...adminNavItems]
  for (const entry of allEntries) {
    if (isNavGroup(entry)) {
      if (entry.children.some((child) => matchesPath(path, child.path))) {
        return entry
      }
      continue
    }
    if (matchesPath(path, entry.path)) {
      return entry
    }
  }

  for (const item of bottomNavItems) {
    if (matchesPath(path, item.path)) {
      return item
    }
  }

  return null
}

export function findTopLevelMenuKeyByPath(path: string): string | null {
  return getTopLevelMenuEntryByPath(path)?.key || null
}

export function isPathBlockedForUser(path: string, hiddenMenuKeys: string[], isAdmin: boolean, isExeMode: boolean = false): boolean {
  if (isExeBlockedPath(path, isExeMode)) {
    return true
  }

  const topLevelEntry = getTopLevelMenuEntryByPath(path)
  if (!topLevelEntry) {
    return false
  }

  const forcedHiddenMenuKeys = getExeForcedHiddenMenuKeys(isExeMode)
  if (forcedHiddenMenuKeys.includes(topLevelEntry.key)) {
    return true
  }

  if (topLevelEntry.adminOnly && !isAdmin) {
    return true
  }

  if (isAdmin) {
    return false
  }

  return hiddenMenuKeys.includes(topLevelEntry.key)
}

export function getMenuAccessFallbackPath(hiddenMenuKeys: string[], isAdmin: boolean, isExeMode: boolean = false): string {
  if (isAdmin) {
    return '/dashboard'
  }

  const forcedHiddenMenuKeys = getExeForcedHiddenMenuKeys(isExeMode)
  const visibleMain = mainNavItems.find((entry) => !hiddenMenuKeys.includes(entry.key) && !forcedHiddenMenuKeys.includes(entry.key) && !('adminOnly' in entry && entry.adminOnly))
  if (visibleMain) {
    if (isNavGroup(visibleMain)) {
      return visibleMain.children[0]?.path || '/dashboard'
    }
    return visibleMain.path
  }

  const visibleBottom = bottomNavItems.find((item) => !hiddenMenuKeys.includes(item.key) && !forcedHiddenMenuKeys.includes(item.key))
  return visibleBottom?.path || '/dashboard'
}
