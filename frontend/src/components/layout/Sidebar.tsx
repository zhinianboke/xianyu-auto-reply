import { useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  LayoutDashboard,
  Users,
  Package,
  ShoppingCart,
  MessageSquare,
  CreditCard,
  Truck,
  Bell,
  MessageCircle,
  Search,
  Settings,
  UserCog,
  FileText,
  Shield,
  Database,
  Info,
  Menu,
  X,
  PanelLeftClose,
  PanelLeft,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { cn } from '@/utils/cn'

interface NavItem {
  icon: React.ElementType
  label: string
  path: string
  adminOnly?: boolean
}

const mainNavItems: NavItem[] = [
  { icon: LayoutDashboard, label: '仪表盘', path: '/dashboard' },
  { icon: Users, label: '账号管理', path: '/accounts' },
  { icon: Package, label: '商品管理', path: '/items' },
  { icon: ShoppingCart, label: '订单管理', path: '/orders' },
  { icon: MessageSquare, label: '自动回复', path: '/keywords' },
  { icon: MessageCircle, label: '指定商品回复', path: '/item-replies' },
  { icon: CreditCard, label: '卡券管理', path: '/cards' },
  { icon: Truck, label: '自动发货', path: '/delivery' },
  { icon: Bell, label: '通知渠道', path: '/notification-channels' },
  { icon: MessageCircle, label: '消息通知', path: '/message-notifications' },
  { icon: Search, label: '商品搜索', path: '/item-search' },
  { icon: Settings, label: '系统设置', path: '/settings' },
]

const adminNavItems: NavItem[] = [
  { icon: UserCog, label: '用户管理', path: '/admin/users', adminOnly: true },
  { icon: FileText, label: '系统日志', path: '/admin/logs', adminOnly: true },
  { icon: Shield, label: '风控日志', path: '/admin/risk-logs', adminOnly: true },
  { icon: Database, label: '数据管理', path: '/admin/data', adminOnly: true },
]

const bottomNavItems: NavItem[] = [
  { icon: Info, label: '关于', path: '/about' },
]

export function Sidebar() {
  const { user } = useAuthStore()
  const { sidebarCollapsed, sidebarMobileOpen, setSidebarMobileOpen, setSidebarCollapsed } = useUIStore()

  // 监听窗口大小变化：
  // <640px 抽屉（不依赖 collapsed）；640-1024px 自动收缩；>1024px 展开
  useEffect(() => {
    const handleResize = () => {
      const width = window.innerWidth
      if (width >= 640 && width < 1024) {
        setSidebarCollapsed(true)
      } else if (width >= 1024) {
        setSidebarCollapsed(false)
      }
    }

    handleResize() // 初始化
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [setSidebarCollapsed])

  const closeMobileSidebar = () => {
    setSidebarMobileOpen(false)
  }

  const NavItemComponent = ({ item }: { item: NavItem }) => {
    const Icon = item.icon
    // 移动端抽屉模式下，始终显示文字
    const showLabel = sidebarMobileOpen || !sidebarCollapsed
    return (
      <NavLink
        to={item.path}
        onClick={closeMobileSidebar}
        title={!showLabel ? item.label : undefined}
        className={({ isActive }) =>
          cn(
            'flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-all duration-150',
            !showLabel && 'justify-center px-2',
            isActive 
              ? 'bg-blue-600 text-white dark:text-white hover:text-white hover:bg-blue-700 shadow-sm'
              : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/10'
          )
        }
      >
        <Icon className="w-4 h-4 flex-shrink-0" />
        {showLabel && <span className="truncate">{item.label}</span>}
      </NavLink>
    )
  }

  return (
    <>
      {/* Mobile overlay - 点击关闭侧边栏（仅在 <640px 显示） */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: sidebarMobileOpen ? 1 : 0 }}
        transition={{ duration: 0.2 }}
        className={cn(
          'fixed inset-0 bg-black/60 z-40 sm:hidden',
          sidebarMobileOpen ? 'pointer-events-auto' : 'pointer-events-none'
        )}
        onClick={closeMobileSidebar}
      />

      {/* Sidebar */}
      <motion.aside
        initial={false}
        className={cn(
          'fixed top-0 left-0 h-screen z-50',
          'bg-white dark:bg-[#001529]',
          'flex flex-col',
          'transition-transform duration-200 ease-out',
          'border-r border-slate-200 dark:border-slate-700',
          // <640px 抽屉：根据 sidebarMobileOpen 控制显隐；>=640px 常驻
          sidebarMobileOpen ? 'translate-x-0' : '-translate-x-full sm:translate-x-0',
          // 宽度：移动端抽屉 288px，桌面根据收缩状态
          sidebarMobileOpen ? 'w-72' : sidebarCollapsed ? 'w-16' : 'w-56'
        )}
      >
        {/* Header */}
        <div className={cn(
          'h-14 flex items-center border-b border-slate-200 dark:border-slate-700',
          (!sidebarMobileOpen && sidebarCollapsed) ? 'justify-center px-2' : 'justify-between px-4'
        )}>
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-500 flex items-center justify-center flex-shrink-0">
              <MessageSquare className="w-4 h-4 text-white" />
            </div>
            {(sidebarMobileOpen || !sidebarCollapsed) && (
              <span className="font-semibold text-sm text-slate-900 dark:text-white whitespace-nowrap">闲鱼管理系统</span>
            )}
          </div>
          {/* 移动端抽屉打开时显示关闭按钮 */}
          {sidebarMobileOpen && (
            <button
              onClick={closeMobileSidebar}
              className="sm:hidden p-1.5 hover:bg-slate-100 dark:hover:bg-white/10 rounded transition-colors text-slate-400 hover:text-slate-900 dark:hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Navigation */}
        <nav className={cn(
          'flex-1 overflow-y-auto py-3 space-y-0.5 sidebar-scrollbar',
          (!sidebarMobileOpen && sidebarCollapsed) ? 'px-1.5' : 'px-2'
        )}>
          {mainNavItems.map((item) => (
            <NavItemComponent key={item.path} item={item} />
          ))}

          {/* Admin section */}
          {user?.is_admin && (
            <>
              {(sidebarMobileOpen || !sidebarCollapsed) && (
                <div className="pt-4 pb-2 px-3">
                  <p className="text-xs font-medium text-slate-400 dark:text-gray-500 uppercase tracking-wider">
                    管理员
                  </p>
                </div>
              )}
              {(!sidebarMobileOpen && sidebarCollapsed) && <div className="pt-2 border-t border-slate-200 dark:border-slate-700 mt-2" />}
              {adminNavItems.map((item) => (
                <NavItemComponent key={item.path} item={item} />
              ))}
            </>
          )}

          {(sidebarMobileOpen || !sidebarCollapsed) && (
            <div className="pt-4 pb-2 px-3">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                其他
              </p>
            </div>
          )}
          {(!sidebarMobileOpen && sidebarCollapsed) && <div className="pt-2 border-t border-slate-200 dark:border-slate-700 mt-2" />}
          {bottomNavItems.map((item) => (
            <NavItemComponent key={item.path} item={item} />
          ))}
        </nav>

        {/* Collapse toggle button - 只在 lg 以上显示 */}
        <div className="hidden lg:flex items-center justify-center p-2 border-t border-slate-200 dark:border-slate-700">
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/10 transition-colors text-slate-400 hover:text-slate-600 dark:hover:text-white"
            title={sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'}
          >
            {sidebarCollapsed ? <PanelLeft className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
          </button>
        </div>
      </motion.aside>

      {/* Mobile toggle button - 只在 <640px 且侧边栏关闭时显示 */}
      <motion.button
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ 
          opacity: sidebarMobileOpen ? 0 : 1, 
          scale: sidebarMobileOpen ? 0.9 : 1
        }}
        transition={{ duration: 0.15 }}
        onClick={() => setSidebarMobileOpen(true)}
        className={cn(
          'fixed top-2.5 left-2.5 z-50 sm:hidden',
          'w-8 h-8 rounded-md',
          'bg-blue-500 text-white shadow-md',
          'flex items-center justify-center',
          'hover:bg-blue-600 active:scale-95 transition-all',
          sidebarMobileOpen && 'pointer-events-none'
        )}
      >
        <Menu className="w-4 h-4" />
      </motion.button>
    </>
  )
}
