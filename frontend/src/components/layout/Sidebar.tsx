/**
 * 侧边栏导航组件
 * 
 * 功能：
 * 1. 主导航菜单
 * 2. 管理员菜单（支持二级菜单）
 * 3. 响应式设计（移动端抽屉模式）
 * 4. 侧边栏收缩/展开
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  Menu,
  MessageSquare,
  X,
  PanelLeftClose,
  PanelLeft,
  ChevronDown,
} from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import {
  adminNavItems,
  bottomNavItems,
  getVisibleBottomNavItems,
  getVisibleNavEntries,
  isNavGroup,
  mainNavItems,
  type NavGroup,
  type NavItem,
} from '@/config/navigation'
import { useMenuVisibilityStore } from '@/store/menuVisibilityStore'
import { useUIStore } from '@/store/uiStore'
import { cn } from '@/utils/cn'

interface SidebarProps {
  systemName?: string
}

export function Sidebar({ systemName = '闲鱼管理系统' }: SidebarProps) {
  const { user } = useAuthStore()
  const { hiddenMenuKeys, isExeMode } = useMenuVisibilityStore()
  const { sidebarCollapsed, sidebarMobileOpen, setSidebarMobileOpen, setSidebarCollapsed } = useUIStore()
  const location = useLocation()
  const navRef = useRef<HTMLElement>(null)
  const isAdmin = Boolean(user?.is_admin)
  const visibleMainNavItems = useMemo(
    () => getVisibleNavEntries(mainNavItems, hiddenMenuKeys, isAdmin, isExeMode),
    [hiddenMenuKeys, isAdmin, isExeMode]
  )
  const visibleAdminNavItems = useMemo(
    () => getVisibleNavEntries(adminNavItems, hiddenMenuKeys, isAdmin, isExeMode),
    [hiddenMenuKeys, isAdmin, isExeMode]
  )
  const visibleBottomNavItems = useMemo(
    () => getVisibleBottomNavItems(bottomNavItems, hiddenMenuKeys, isAdmin, isExeMode),
    [hiddenMenuKeys, isAdmin, isExeMode]
  )

  // 展开的分组菜单 - 使用 Set 来避免重复添加触发重渲染
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => {
    // 默认折叠所有分组
    return new Set<string>()
  })

  // 监听窗口大小变化
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

  // 路由变化时自动展开匹配的分组
  useEffect(() => {
    const allGroups = [...visibleMainNavItems, ...visibleAdminNavItems].filter(isNavGroup) as NavGroup[]
    for (const group of allGroups) {
      if (group.children.some((child) => location.pathname.startsWith(child.path))) {
        setExpandedGroups((prev) => {
          if (prev.has(group.key)) return prev
          const next = new Set(prev)
          next.add(group.key)
          return next
        })
      }
    }
  }, [location.pathname, visibleMainNavItems, visibleAdminNavItems])

  const closeMobileSidebar = () => {
    setSidebarMobileOpen(false)
  }

  const preserveSidebarScroll = () => {
    const nav = navRef.current
    if (!nav) return

    const scrollTop = nav.scrollTop
    window.requestAnimationFrame(() => {
      nav.scrollTop = scrollTop
      window.requestAnimationFrame(() => {
        nav.scrollTop = scrollTop
      })
    })
  }

  const handleNavLinkClick = () => {
    preserveSidebarScroll()
    closeMobileSidebar()
  }

  const toggleGroup = (groupKey: string) => {
    setExpandedGroups((prev) => {
      const newSet = new Set(prev)
      if (newSet.has(groupKey)) {
        newSet.delete(groupKey)
      } else {
        newSet.add(groupKey)
      }
      return newSet
    })
  }

  const showLabel = sidebarMobileOpen || !sidebarCollapsed

  // 单个菜单项组件
  const NavItemComponent = ({ item, indent = false }: { item: NavItem; indent?: boolean }) => {
    const Icon = item.icon
    return (
      <NavLink
        to={item.path}
        onClick={handleNavLinkClick}
        title={!showLabel ? item.label : undefined}
        className={({ isActive }) =>
          cn(
            'flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-all duration-150',
            !showLabel && 'justify-center px-2',
            indent && showLabel && 'pl-9',
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

  // 分组菜单组件
  const NavGroupComponent = ({ group }: { group: NavGroup }) => {
    const Icon = group.icon
    const isExpanded = expandedGroups.has(group.key)
    const currentPath = location.pathname
    const isChildActive = group.children.some((child) => currentPath.startsWith(child.path))

    // 收缩模式下，点击图标展开子菜单或跳转到第一个子菜单
    if (!showLabel) {
      return (
        <div className="relative group">
          <button
            onClick={() => toggleGroup(group.key)}
            title={group.label}
            className={cn(
              'flex items-center justify-center w-full px-2 py-2.5 rounded-md text-sm transition-all duration-150',
              isChildActive
                ? 'bg-blue-600 text-white'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/10'
            )}
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
          </button>
          {/* 悬浮子菜单 */}
          <div className="absolute left-full top-0 ml-2 hidden group-hover:block z-50">
            <div className="bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg py-1 min-w-[140px]">
              <div className="px-3 py-2 text-xs font-medium text-slate-400 border-b border-slate-100 dark:border-slate-700">
                {group.label}
              </div>
              {group.children.map((child) => (
                <NavLink
                  key={child.path}
                  to={child.path}
                  onClick={handleNavLinkClick}
                  className={({ isActive }) =>
                    cn(
                      'flex items-center gap-2 px-3 py-2 text-sm transition-colors',
                      isActive
                        ? 'bg-blue-50 text-blue-600 dark:bg-blue-900/20 dark:text-blue-400'
                        : 'text-slate-600 dark:text-slate-400 hover:bg-slate-50 dark:hover:bg-slate-700'
                    )
                  }
                >
                  <child.icon className="w-4 h-4" />
                  {child.label}
                </NavLink>
              ))}
            </div>
          </div>
        </div>
      )
    }

    return (
      <div>
        <button
          onClick={() => toggleGroup(group.key)}
          className={cn(
            'flex items-center gap-3 w-full px-3 py-2.5 rounded-md text-sm transition-all duration-150',
            isChildActive
              ? 'text-blue-600 dark:text-blue-400'
              : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-white/10'
          )}
        >
          <Icon className="w-4 h-4 flex-shrink-0" />
          <span className="truncate flex-1 text-left">{group.label}</span>
          <ChevronDown
            className={cn(
              'w-4 h-4 transition-transform duration-500',
              isExpanded && 'rotate-180'
            )}
          />
        </button>
        <motion.div
          initial={false}
          animate={{ height: isExpanded ? 'auto' : 0 }}
          transition={{ duration: 0.25, ease: 'easeInOut' }}
          className="overflow-hidden"
        >
          <div className="py-1 space-y-0.5">
            {group.children.map((child) => (
              <NavItemComponent key={child.path} item={child} indent />
            ))}
          </div>
        </motion.div>
      </div>
    )
  }

  return (
    <>
      {/* Mobile overlay */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: sidebarMobileOpen ? 1 : 0 }}
        transition={{ duration: 0.2 }}
        className={cn(
          'fixed inset-0 bg-black/60 z-40 sm:hidden',
          sidebarMobileOpen ? 'pointer-events-auto' : 'pointer-events-none'
        )}
        onClick={handleNavLinkClick}
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
          sidebarMobileOpen ? 'translate-x-0' : '-translate-x-full sm:translate-x-0',
          sidebarMobileOpen ? 'w-72' : sidebarCollapsed ? 'w-16' : 'w-56'
        )}
      >
        {/* Header */}
        <div
          className={cn(
            'h-14 flex items-center border-b border-slate-200 dark:border-slate-700',
            !showLabel ? 'justify-center px-2' : 'justify-between px-4'
          )}
        >
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-blue-500 flex items-center justify-center flex-shrink-0">
              <MessageSquare className="w-4 h-4 text-white" />
            </div>
            {showLabel && (
              <span className="font-semibold text-sm text-slate-900 dark:text-white truncate max-w-[140px]">
                {systemName}
              </span>
            )}
          </div>
          {sidebarMobileOpen && (
            <button
              onClick={handleNavLinkClick}
              className="sm:hidden p-1.5 hover:bg-slate-100 dark:hover:bg-white/10 rounded transition-colors text-slate-400 hover:text-slate-900 dark:hover:text-white"
            >
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Navigation */}
        <nav
          ref={navRef}
          style={{ overflowAnchor: 'none' }}
          className={cn(
            'flex-1 overflow-y-auto py-3 space-y-0.5 sidebar-scrollbar',
            !showLabel ? 'px-1.5' : 'px-2'
          )}
        >
          {visibleMainNavItems.map((entry) =>
              isNavGroup(entry) ? (
                <NavGroupComponent key={entry.key} group={entry} />
              ) : (
                <NavItemComponent key={entry.path} item={entry} />
              )
            )}

          {/* Admin section */}
          {isAdmin && (
            <>
              {showLabel && (
                <div className="pt-4 pb-2 px-3">
                  <p className="text-xs font-medium text-slate-400 dark:text-gray-500 uppercase tracking-wider">
                    管理员
                  </p>
                </div>
              )}
              {!showLabel && (
                <div className="pt-2 border-t border-slate-200 dark:border-slate-700 mt-2" />
              )}
              {visibleAdminNavItems.map((entry) =>
                isNavGroup(entry) ? (
                  <NavGroupComponent key={entry.key} group={entry} />
                ) : (
                  <NavItemComponent key={entry.path} item={entry} />
                )
              )}
            </>
          )}

          {showLabel && (
            <div className="pt-4 pb-2 px-3">
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">其他</p>
            </div>
          )}
          {!showLabel && (
            <div className="pt-2 border-t border-slate-200 dark:border-slate-700 mt-2" />
          )}
          {visibleBottomNavItems.map((item) => (
            <NavItemComponent key={item.path} item={item} />
          ))}
        </nav>

        {/* Collapse toggle button */}
        <div className="hidden lg:flex items-center justify-center p-2 border-t border-slate-200 dark:border-slate-700">
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-white/10 transition-colors text-slate-400 hover:text-slate-600 dark:hover:text-white"
            title={sidebarCollapsed ? '展开侧边栏' : '收起侧边栏'}
          >
            {sidebarCollapsed ? (
              <PanelLeft className="w-4 h-4" />
            ) : (
              <PanelLeftClose className="w-4 h-4" />
            )}
          </button>
        </div>
      </motion.aside>

      {/* Mobile toggle button */}
      <motion.button
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{
          opacity: sidebarMobileOpen ? 0 : 1,
          scale: sidebarMobileOpen ? 0.9 : 1,
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

