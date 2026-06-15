import { useCallback, useEffect, useMemo, useState, type DragEvent, type MouseEvent as ReactMouseEvent } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { Button, Menu } from '@arco-design/web-react'
import {
  LayoutDashboard,
  Users,
  Package,
  ShoppingCart,
  MessageSquareQuote,
  CreditCard,
  Truck,
  Bell,
  MessageCircle,
  MessageSquareText,
  Settings,
  UserCog,
  FileText,
  Shield,
  Database,
  Info,
  Menu as MenuIcon,
  X,
  ChevronLeft,
  ChevronRight,
  AlertTriangle,
  Activity,
  Ban,
  Bot,
  BarChart3,
  BellOff,
  BookOpen,
  Filter,
  Flower2,
  Image,
  Key,
  Layers,
  Link2,
  LogIn,
  MapPin,
  Megaphone,
  PackageCheck,
  PackageSearch,
  Repeat,
  ScrollText,
  Search,
  Send,
  Star,
  Store,
  Ticket,
  Timer,
  Wallet,
  GripVertical,
  Pin,
  PinOff,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { cn } from '@/utils/cn'
import devingIllustration from '@/assets/illustrations/deving.svg'

const MenuItem = Menu.Item
const SubMenu = Menu.SubMenu

interface NavItem {
  icon: React.ElementType
  label: string
  path: string
  adminOnly?: boolean
}

interface NavGroup {
  label: string
  path: string
  items: NavItem[]
}

interface NavSection {
  label: string
  icon: React.ElementType
  path: string
  items?: NavItem[]
  groups?: NavGroup[]
}

type SidebarMenuEntry =
  | { id: string; type: 'item'; item: NavItem }
  | { id: string; type: 'section'; section: NavSection }

interface SidebarMenuPreferences {
  orderKeys: string[]
  pinnedKeys: string[]
}

type SidebarMenuCategory = 'pinned' | 'common' | 'business' | 'admin' | 'other'

interface SidebarMenuGroup {
  key: SidebarMenuCategory
  label: string
  entries: SidebarMenuEntry[]
}

const topNavItems: NavItem[] = [
  { icon: LayoutDashboard, label: '仪表盘', path: '/dashboard' },
]

const xianyuSection: NavSection = {
  label: '闲鱼管理',
  icon: Package,
  path: '/section/xianyu',
  items: [
    { icon: Users, label: '闲鱼账号', path: '/accounts' },
    { icon: MessageSquareText, label: '在线聊天', path: '/online-chat-new' },
    { icon: Package, label: '商品管理', path: '/items' },
    { icon: ShoppingCart, label: '订单管理', path: '/orders' },
    { icon: Search, label: '商品搜索', path: '/item-search' },
  ],
}

const dataSection: NavSection = {
  label: '数据分析',
  icon: BarChart3,
  path: '/section/data',
  items: [
    { icon: BarChart3, label: '数据总览', path: '/data-analysis/overview' },
    { icon: BarChart3, label: 'Goofish 罗盘', path: '/goofish-compass' },
    { icon: Search, label: '定时采集', path: '/goofish-scheduled-crawler' },
  ],
}

const automationSection: NavSection = {
  label: '自动回复',
  icon: MessageSquareQuote,
  path: '/section/auto-reply',
  items: [
    { icon: MessageSquareQuote, label: '关键词回复', path: '/keywords' },
    { icon: MessageCircle, label: '商品回复', path: '/item-replies' },
    { icon: ScrollText, label: '消息日志', path: '/message-logs' },
    { icon: Filter, label: '消息过滤', path: '/message-filters' },
    { icon: Shield, label: '回复安全设置', path: '/settings/reply-safety' },
    { icon: Bot, label: '回复模拟', path: '/tools/reply-simulator' },
    { icon: MessageCircle, label: '消息通知', path: '/message-notifications' },
  ],
}

const aiSection: NavSection = {
  label: 'AI 配置',
  icon: Bot,
  path: '/section/ai',
  items: [
    { icon: MessageSquareQuote, label: 'AI 设置', path: '/settings/ai' },
    { icon: FileText, label: '调用明细', path: '/ai/calls' },
    { icon: BarChart3, label: 'Token 统计', path: '/ai/tokens' },
  ],
}

const autoReviewSection: NavSection = {
  label: '互动助手',
  icon: MessageSquareText,
  path: '/section/auto-review',
  items: [
    { icon: MessageSquareText, label: '订单评价', path: '/auto-review' },
    { icon: Search, label: '商品互动助手', path: '/interaction/items' },
  ],
}

const fulfillmentSection: NavSection = {
  label: '交易履约',
  icon: Truck,
  path: '/section/fulfillment',
  items: [
    { icon: Truck, label: '自动发货规则', path: '/delivery' },
    { icon: CreditCard, label: '卡密库存管理', path: '/cards' },
  ],
}

const distributionSection: NavSection = {
  label: '分销管理',
  icon: PackageSearch,
  path: '/section/distribution',
  items: [
    { icon: Link2, label: '货源管理', path: '/distribution/sources' },
    { icon: PackageSearch, label: '货源广场', path: '/distribution/supply' },
    { icon: Ticket, label: '分销卡券', path: '/distribution/card-pickup' },
    { icon: PackageCheck, label: '对接商品', path: '/distribution/docked' },
    { icon: ShoppingCart, label: '代理订单', path: '/distribution/agent-orders' },
    { icon: Users, label: '分销商管理', path: '/distribution/dealers' },
    { icon: Users, label: '下级分销商', path: '/distribution/sub-dealers' },
  ],
}

const publishSection: NavSection = {
  label: '商品发布',
  icon: Store,
  path: '/section/product-publish',
  items: [
    { icon: Image, label: '素材库', path: '/product-publish/materials' },
    { icon: Send, label: '单品发布', path: '/product-publish/single' },
    { icon: Layers, label: '批量发布', path: '/product-publish/batch' },
    { icon: MapPin, label: '随机地址库', path: '/product-publish/addresses' },
    { icon: ScrollText, label: '发布日志', path: '/product-publish/logs' },
  ],
}

const mainNavItems: NavItem[] = [
  ...topNavItems,
  { icon: Bell, label: '通知渠道', path: '/notification-channels' },
  { icon: Ban, label: '黑名单管理', path: '/blacklist' },
  { icon: UserCog, label: '个人设置', path: '/personal-settings' },
]

const systemSection: NavSection = {
  label: '系统设置',
  icon: Settings,
  path: '/section/system',
  items: [
    { icon: Settings, label: '系统设置', path: '/settings' },
    { icon: Megaphone, label: '公告管理', path: '/admin/announcements', adminOnly: true },
    { icon: Image, label: '广告管理', path: '/admin/ad-manage', adminOnly: true },
    { icon: Timer, label: '定时任务', path: '/admin/scheduled-tasks', adminOnly: true },
  ],
  groups: [
    {
      label: '账号与权限',
      path: '/section/system/account-access',
      items: [
        { icon: UserCog, label: '个人资料', path: '/settings/profile' },
        { icon: UserCog, label: '用户管理', path: '/admin/users', adminOnly: true },
      ],
    },
    {
      label: '数据与维护',
      path: '/section/system/data-maintenance',
      items: [
        { icon: Database, label: '数据管理', path: '/admin/data', adminOnly: true },
        { icon: Database, label: '数据备份', path: '/settings/backup' },
        { icon: Wallet, label: '资金流水', path: '/admin/fund-flows', adminOnly: true },
      ],
    },
  ],
}

const logSection: NavSection = {
  label: '运维中心',
  icon: Activity,
  path: '/section/operations',
  items: [
    { icon: Activity, label: '系统健康', path: '/admin/health', adminOnly: true },
    { icon: AlertTriangle, label: '账号异常', path: '/admin/account-exceptions', adminOnly: true },
    { icon: Shield, label: '风控日志', path: '/risk-logs' },
  ],
  groups: [
    {
      label: '系统日志',
      path: '/section/operations/system-logs',
      items: [
        { icon: FileText, label: '系统日志', path: '/admin/logs', adminOnly: true },
        { icon: LogIn, label: '账号登录日志', path: '/admin/account-login-logs', adminOnly: true },
        { icon: Database, label: '数据库备份日志', path: '/admin/db-backup-logs', adminOnly: true },
      ],
    },
    {
      label: '批处理日志',
      path: '/section/operations/batch-logs',
      items: [
        { icon: Repeat, label: '补发货日志', path: '/admin/redelivery-batches', adminOnly: true },
        { icon: Star, label: '补评价日志', path: '/admin/rate-batches', adminOnly: true },
        { icon: Star, label: '擦亮日志', path: '/admin/polish-batches', adminOnly: true },
        { icon: Key, label: '登录续期日志', path: '/admin/login-renew-batches', adminOnly: true },
        { icon: Key, label: 'Cookies 刷新日志', path: '/admin/cookies-refresh-batches', adminOnly: true },
        { icon: Key, label: '接口续期日志', path: '/admin/api-cookie-renew-batches', adminOnly: true },
        { icon: BellOff, label: '通知关闭日志', path: '/admin/close-notice-batches', adminOnly: true },
        { icon: Flower2, label: '求小红花日志', path: '/admin/red-flower-batches', adminOnly: true },
      ],
    },
  ],
}

const infoSection: NavSection = {
  label: '系统信息',
  icon: Info,
  path: '/section/info',
  items: [
    { icon: BookOpen, label: '使用教程', path: '/tutorial' },
    { icon: MessageSquareQuote, label: '意见反馈', path: '/feedback' },
    { icon: Image, label: '广告申请', path: '/ad-apply' },
    { icon: AlertTriangle, label: '免责声明', path: '/disclaimer' },
    { icon: Info, label: '关于', path: '/about' },
  ],
}

const navSections: NavSection[] = [
  {
    label: '主菜单',
    icon: LayoutDashboard,
    path: '/section/main',
    items: mainNavItems,
  },
  xianyuSection,
  dataSection,
  automationSection,
  aiSection,
  autoReviewSection,
  fulfillmentSection,
  distributionSection,
  publishSection,
  systemSection,
  logSection,
  infoSection,
]

const SIDEBAR_MENU_PREFERENCES_KEY = 'xianyu_sidebar_menu_preferences_v1'
const SIDEBAR_MENU_CATEGORY_ORDER: SidebarMenuCategory[] = ['common', 'business', 'admin', 'other']
const SIDEBAR_MENU_CATEGORY_LABELS: Record<SidebarMenuCategory, string> = {
  pinned: '置顶',
  common: '常用',
  business: '业务',
  admin: '管理员',
  other: '其他',
}

function getSidebarMenuCategory(entry: SidebarMenuEntry): SidebarMenuCategory {
  if (entry.type === 'item') {
    return 'common'
  }

  if (entry.section.path === '/section/system' || entry.section.path === '/section/operations') {
    return 'admin'
  }

  if (entry.section.path === '/section/info') {
    return 'other'
  }

  return 'business'
}

function readSidebarMenuPreferences(): SidebarMenuPreferences {
  if (typeof window === 'undefined') {
    return { orderKeys: [], pinnedKeys: [] }
  }

  try {
    const raw = window.localStorage.getItem(SIDEBAR_MENU_PREFERENCES_KEY)
    if (!raw) return { orderKeys: [], pinnedKeys: [] }
    const parsed = JSON.parse(raw) as Partial<SidebarMenuPreferences>
    return {
      orderKeys: Array.isArray(parsed.orderKeys) ? parsed.orderKeys.filter((key): key is string => typeof key === 'string') : [],
      pinnedKeys: Array.isArray(parsed.pinnedKeys) ? parsed.pinnedKeys.filter((key): key is string => typeof key === 'string') : [],
    }
  } catch {
    return { orderKeys: [], pinnedKeys: [] }
  }
}

function saveSidebarMenuPreferences(preferences: SidebarMenuPreferences) {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(SIDEBAR_MENU_PREFERENCES_KEY, JSON.stringify(preferences))
}

function normalizeMenuKeys(keys: string[], validKeys: string[]) {
  const validSet = new Set(validKeys)
  const nextKeys: string[] = []
  keys.forEach((key) => {
    if (validSet.has(key) && !nextKeys.includes(key)) {
      nextKeys.push(key)
    }
  })
  return nextKeys
}

function orderSidebarEntries(entries: SidebarMenuEntry[], orderKeys: string[], pinnedKeys: string[]) {
  const orderRank = new Map(orderKeys.map((key, index) => [key, index]))
  const pinnedSet = new Set(pinnedKeys)

  return entries
    .map((entry, index) => ({ entry, index }))
    .sort((a, b) => {
      const aPinned = pinnedSet.has(a.entry.id)
      const bPinned = pinnedSet.has(b.entry.id)
      if (aPinned !== bPinned) return aPinned ? -1 : 1

      const aRank = orderRank.get(a.entry.id)
      const bRank = orderRank.get(b.entry.id)
      if (aRank !== undefined && bRank !== undefined) return aRank - bRank
      if (aRank !== undefined) return -1
      if (bRank !== undefined) return 1
      return a.index - b.index
    })
    .map(({ entry }) => entry)
}

export function Sidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { user } = useAuthStore()
  const { sidebarCollapsed, sidebarMobileOpen, setSidebarMobileOpen, setSidebarCollapsed } = useUIStore()
  const [openKeys, setOpenKeys] = useState<string[]>([])
  const [menuPreferences, setMenuPreferences] = useState<SidebarMenuPreferences>(() => readSidebarMenuPreferences())
  const [draggingEntryId, setDraggingEntryId] = useState<string | null>(null)
  const [dragOverEntryId, setDragOverEntryId] = useState<string | null>(null)
  const sidebarExpanded = sidebarMobileOpen || !sidebarCollapsed

  const visibleSections = useMemo(
    () => navSections
      .map((section) => ({
        ...section,
        items: (section.items || []).filter((item) => !item.adminOnly || user?.is_admin),
        groups: section.groups
          ?.map((group) => ({
            ...group,
            items: group.items.filter((item) => !item.adminOnly || user?.is_admin),
          }))
          .filter((group) => group.items.length > 0),
      }))
      .filter((section) => (section.items?.length || 0) > 0 || (section.groups?.length || 0) > 0),
    [user?.is_admin]
  )

  const topLevelEntries = useMemo<SidebarMenuEntry[]>(() => {
    const entries: SidebarMenuEntry[] = []
    visibleSections.forEach((section) => {
      if (section.path === '/section/main') {
        const sectionItems = section.items || []
        sectionItems.forEach((item) => {
          entries.push({ id: item.path, type: 'item', item })
        })
        return
      }
      entries.push({ id: section.path, type: 'section', section })
    })
    return entries
  }, [visibleSections])

  const orderedEntries = useMemo(
    () => orderSidebarEntries(topLevelEntries, menuPreferences.orderKeys, menuPreferences.pinnedKeys),
    [menuPreferences.orderKeys, menuPreferences.pinnedKeys, topLevelEntries]
  )

  const pinnedEntryIds = useMemo(() => new Set(menuPreferences.pinnedKeys), [menuPreferences.pinnedKeys])

  const sidebarMenuGroups = useMemo<SidebarMenuGroup[]>(() => {
    const pinnedEntries = orderedEntries.filter((entry) => pinnedEntryIds.has(entry.id))
    const unpinnedEntries = orderedEntries.filter((entry) => !pinnedEntryIds.has(entry.id))
    const groups: SidebarMenuGroup[] = []

    if (pinnedEntries.length > 0) {
      groups.push({
        key: 'pinned',
        label: SIDEBAR_MENU_CATEGORY_LABELS.pinned,
        entries: pinnedEntries,
      })
    }

    SIDEBAR_MENU_CATEGORY_ORDER.forEach((category) => {
      const entries = unpinnedEntries.filter((entry) => getSidebarMenuCategory(entry) === category)
      if (entries.length > 0) {
        groups.push({
          key: category,
          label: SIDEBAR_MENU_CATEGORY_LABELS[category],
          entries,
        })
      }
    })

    return groups
  }, [orderedEntries, pinnedEntryIds])

  const updateMenuPreferences = useCallback((
    updater: (current: SidebarMenuPreferences) => SidebarMenuPreferences
  ) => {
    const validKeys = topLevelEntries.map((entry) => entry.id)
    setMenuPreferences((current) => {
      const next = updater(current)
      const normalized = {
        orderKeys: normalizeMenuKeys(next.orderKeys, validKeys),
        pinnedKeys: normalizeMenuKeys(next.pinnedKeys, validKeys),
      }
      saveSidebarMenuPreferences(normalized)
      return normalized
    })
  }, [topLevelEntries])

  useEffect(() => {
    const validKeys = topLevelEntries.map((entry) => entry.id)
    const normalized = {
      orderKeys: normalizeMenuKeys(menuPreferences.orderKeys, validKeys),
      pinnedKeys: normalizeMenuKeys(menuPreferences.pinnedKeys, validKeys),
    }

    if (
      normalized.orderKeys.length !== menuPreferences.orderKeys.length
      || normalized.pinnedKeys.length !== menuPreferences.pinnedKeys.length
    ) {
      setMenuPreferences(normalized)
      saveSidebarMenuPreferences(normalized)
    }
  }, [menuPreferences.orderKeys, menuPreferences.pinnedKeys, topLevelEntries])

  useEffect(() => {
    const handleResize = () => {
      const width = window.innerWidth
      if (width >= 640 && width < 1024) {
        setSidebarCollapsed(true)
      } else if (width >= 1024) {
        setSidebarCollapsed(false)
      }
    }

    handleResize()
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [setSidebarCollapsed])

  useEffect(() => {
    const activeSection = visibleSections.find((section) =>
      [
        ...(section.items || []),
        ...((section.groups || []).flatMap((group) => group.items)),
      ].some((item) => location.pathname === item.path || location.pathname.startsWith(`${item.path}/`))
    )

    if (activeSection && !sidebarCollapsed) {
      setOpenKeys((current) => current.includes(activeSection.path) ? current : [...current, activeSection.path])
    }
  }, [location.pathname, sidebarCollapsed, visibleSections])

  const closeMobileSidebar = () => {
    setSidebarMobileOpen(false)
  }

  const selectedKeys = useMemo(() => {
    const activeItems = visibleSections
      .flatMap((section) => [
        ...(section.items || []),
        ...((section.groups || []).flatMap((group) => group.items)),
      ])
      .filter((item) => location.pathname === item.path || location.pathname.startsWith(`${item.path}/`))
      .sort((a, b) => b.path.length - a.path.length)
    const activeItem = activeItems[0]
    return activeItem ? [activeItem.path] : []
  }, [location.pathname, visibleSections])

  const handleEntryDragStart = (event: DragEvent<HTMLSpanElement>, entryId: string) => {
    if (!sidebarExpanded) {
      event.preventDefault()
      return
    }
    event.stopPropagation()
    event.dataTransfer.effectAllowed = 'move'
    event.dataTransfer.setData('text/plain', entryId)
    setDraggingEntryId(entryId)
    setDragOverEntryId(null)
  }

  const handleEntryDragOver = (event: DragEvent<HTMLSpanElement>, entryId: string) => {
    if (!draggingEntryId || draggingEntryId === entryId) return
    event.preventDefault()
    event.stopPropagation()
    event.dataTransfer.dropEffect = 'move'
    setDragOverEntryId(entryId)
  }

  const handleEntryDrop = (event: DragEvent<HTMLSpanElement>, entryId: string) => {
    event.preventDefault()
    event.stopPropagation()

    const sourceId = draggingEntryId || event.dataTransfer.getData('text/plain')
    setDraggingEntryId(null)
    setDragOverEntryId(null)
    if (!sourceId || sourceId === entryId) return

    const currentOrder = orderedEntries.map((entry) => entry.id)
    const sourceIndex = currentOrder.indexOf(sourceId)
    const targetIndex = currentOrder.indexOf(entryId)
    if (sourceIndex === -1 || targetIndex === -1) return

    const nextOrder = [...currentOrder]
    nextOrder.splice(sourceIndex, 1)
    const nextTargetIndex = nextOrder.indexOf(entryId)
    nextOrder.splice(nextTargetIndex, 0, sourceId)

    updateMenuPreferences((current) => ({
      ...current,
      orderKeys: nextOrder,
    }))
  }

  const handleEntryDragEnd = () => {
    setDraggingEntryId(null)
    setDragOverEntryId(null)
  }

  const handleToggleEntryPin = (event: ReactMouseEvent<HTMLButtonElement>, entryId: string) => {
    event.preventDefault()
    event.stopPropagation()

    updateMenuPreferences((current) => {
      const isPinned = current.pinnedKeys.includes(entryId)
      const currentOrder = orderedEntries.map((entry) => entry.id)
      if (isPinned) {
        return {
          orderKeys: currentOrder,
          pinnedKeys: current.pinnedKeys.filter((key) => key !== entryId),
        }
      }

      return {
        orderKeys: [entryId, ...currentOrder.filter((key) => key !== entryId)],
        pinnedKeys: [entryId, ...current.pinnedKeys.filter((key) => key !== entryId)],
      }
    })
  }

  const renderTopLevelTitle = (entry: SidebarMenuEntry, Icon: React.ElementType, label: string) => {
    const isPinned = pinnedEntryIds.has(entry.id)

    return (
      <span
        className={cn(
          'xianyu-menu-title xianyu-menu-title-configurable',
          isPinned && 'xianyu-menu-title-pinned',
          draggingEntryId === entry.id && 'xianyu-menu-title-dragging',
          dragOverEntryId === entry.id && 'xianyu-menu-title-drag-over'
        )}
        onDragOver={(event) => handleEntryDragOver(event, entry.id)}
        onDrop={(event) => handleEntryDrop(event, entry.id)}
      >
        <span
          className="xianyu-menu-drag-handle"
          draggable={sidebarExpanded}
          title="拖动排序"
          onMouseDown={(event) => event.stopPropagation()}
          onClick={(event) => {
            event.preventDefault()
            event.stopPropagation()
          }}
          onDragStart={(event) => handleEntryDragStart(event, entry.id)}
          onDragEnd={handleEntryDragEnd}
        >
          <GripVertical />
        </span>
        <Icon className="xianyu-menu-icon" />
        <span>{label}</span>
        {sidebarExpanded && (
          <button
            type="button"
            className={cn('xianyu-menu-pin-btn', isPinned && 'is-pinned')}
            title={isPinned ? '取消置顶' : '置顶'}
            aria-label={isPinned ? `取消置顶${label}` : `置顶${label}`}
            onClick={(event) => handleToggleEntryPin(event, entry.id)}
          >
            {isPinned ? <PinOff /> : <Pin />}
          </button>
        )}
      </span>
    )
  }

  const renderSidebarMenuEntry = (entry: SidebarMenuEntry) => {
    if (entry.type === 'item') {
      return (
        <MenuItem key={entry.item.path} renderItemInTooltip={() => entry.item.label}>
          {renderTopLevelTitle(entry, entry.item.icon, entry.item.label)}
        </MenuItem>
      )
    }

    return (
      <SubMenu
        key={entry.section.path}
        title={renderTopLevelTitle(entry, entry.section.icon, entry.section.label)}
      >
        {(entry.section.items || []).map((item) => (
          <MenuItem key={item.path} renderItemInTooltip={() => item.label}>
            <span className="xianyu-menu-text xianyu-menu-text-secondary">{item.label}</span>
          </MenuItem>
        ))}
        {(entry.section.groups || []).map((group) => (
          <SubMenu
            key={group.path}
            title={group.label}
          >
            {group.items.map((item) => (
              <MenuItem key={item.path} renderItemInTooltip={() => item.label}>
                <span className="xianyu-menu-text xianyu-menu-text-tertiary">{item.label}</span>
              </MenuItem>
            ))}
          </SubMenu>
        ))}
      </SubMenu>
    )
  }

  return (
    <>
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: sidebarMobileOpen ? 1 : 0 }}
        transition={{ duration: 0.2 }}
        className={cn(
          'fixed inset-0 bg-black/45 z-40 sm:hidden',
          sidebarMobileOpen ? 'pointer-events-auto' : 'pointer-events-none'
        )}
        onClick={closeMobileSidebar}
      />

      <motion.aside
        initial={false}
        className={cn(
          'fixed top-0 left-0 h-screen z-50 flex flex-col',
          'xianyu-arco-sider',
          (!sidebarMobileOpen && sidebarCollapsed) && 'xianyu-arco-sider-collapsed',
          'transition-transform duration-200 ease-out',
          sidebarMobileOpen ? 'translate-x-0' : '-translate-x-full sm:translate-x-0',
          sidebarMobileOpen ? 'w-[230px]' : sidebarCollapsed ? 'w-16' : 'w-[230px]'
        )}
      >
        <div className={cn(
          'xianyu-arco-logo',
          (!sidebarMobileOpen && sidebarCollapsed) && 'xianyu-arco-logo-collapsed'
        )}>
          {(!sidebarMobileOpen && sidebarCollapsed) && (
            <div className="xianyu-arco-logo-mark">
              <img src={devingIllustration} alt="闲鱼管理系统" />
            </div>
          )}
          {(sidebarMobileOpen || !sidebarCollapsed) && (
            <div className="xianyu-arco-logo-brand">
              <img src={devingIllustration} alt="闲鱼管理系统" />
              <span className="xianyu-arco-logo-text">闲鱼管理系统</span>
            </div>
          )}
          {sidebarMobileOpen && (
            <Button
              type="text"
              size="mini"
              className="xianyu-arco-logo-close sm:hidden"
              icon={<X className="w-4 h-4" />}
              onClick={closeMobileSidebar}
            />
          )}
        </div>

        <div className="xianyu-arco-menu-wrap sidebar-scrollbar">
          <div className="xianyu-sidebar-menu-sections">
            {sidebarMenuGroups.map((group) => (
              <div key={group.key} className="xianyu-sidebar-menu-section">
                {sidebarExpanded && (
                  <div className="xianyu-sidebar-section-heading">
                    <span>{group.label}</span>
                  </div>
                )}
                <Menu
                  mode="vertical"
                  theme="light"
                  collapse={!sidebarMobileOpen && sidebarCollapsed}
                  selectedKeys={selectedKeys}
                  openKeys={(!sidebarMobileOpen && sidebarCollapsed) ? [] : openKeys}
                  onClickMenuItem={(key) => {
                    navigate(key)
                    closeMobileSidebar()
                  }}
                  onClickSubMenu={(_, keys) => setOpenKeys(keys)}
                  className="xianyu-arco-menu"
                  autoScrollIntoView
                >
                  {group.entries.map(renderSidebarMenuEntry)}
                </Menu>
              </div>
            ))}
          </div>
        </div>

        <div className="xianyu-arco-sider-footer hidden lg:flex">
          <button
            type="button"
            className="xianyu-sidebar-collapse-trigger"
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            aria-label={sidebarCollapsed ? '展开菜单' : '收起菜单'}
          >
            {sidebarCollapsed ? <ChevronRight className="w-5 h-5" /> : <ChevronLeft className="w-5 h-5" />}
          </button>
        </div>
      </motion.aside>

      <motion.button
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{
          opacity: sidebarMobileOpen ? 0 : 1,
          scale: sidebarMobileOpen ? 0.9 : 1
        }}
        transition={{ duration: 0.15 }}
        onClick={() => setSidebarMobileOpen(true)}
        className={cn(
          'fixed top-3 left-3 z-50 sm:hidden',
          'w-9 h-9 rounded-lg bg-white text-slate-700 shadow-md ring-1 ring-slate-200',
          'flex items-center justify-center active:scale-95 transition-all',
          sidebarMobileOpen && 'pointer-events-none'
        )}
      >
        <MenuIcon className="w-4 h-4" />
      </motion.button>
    </>
  )
}
