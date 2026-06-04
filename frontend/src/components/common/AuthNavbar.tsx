/**
 * 公共页面顶部导航栏组件
 *
 * 用于登录页、注册页、获取激活码、激活码续期等无需登录的页面
 * 包含：首页、获取激活码、激活码续期 三个菜单
 * 支持手机端响应式（汉堡菜单）
 */
import { Link, useLocation } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { Home, Key, RefreshCw, Monitor, Menu, X, MessageSquare, Code2, Sun, Moon } from 'lucide-react'
import { getDefaultLoginBrandingSettings, LOGIN_BRANDING_UPDATED_EVENT } from '@/api/settings'
import { getLoginBrandingSettings } from '@/api/auth'
import type { LoginBrandingSettings } from '@/types'
import { cn } from '@/utils/cn'
import { initializeThemeMode, toggleThemeMode } from '@/utils/theme'

/** 判断当前是否为线上正式环境 */
const isOnlineEnv = () => {
  return window.location.hostname === 'xy.zhinianboke.com'
}

/** 导航菜单项定义 */
const NAV_ITEMS = [
  { path: '/login', label: '首页', icon: Home, hideOnLocal: true },
  { path: '/get-activation', label: '获取激活码', icon: Key, hideOnLocal: true },
  { path: '/renew-activation', label: '激活码续期', icon: RefreshCw, hideOnLocal: true },
  { path: '/get-local-version', label: '获取本地版', icon: Monitor, hideOnLocal: true },
  { path: '/get-source-code', label: '获取源码', icon: Code2, hideOnLocal: true },
]

interface AuthNavbarProps {
  systemName?: string
}

const DEFAULT_SYSTEM_NAME = getDefaultLoginBrandingSettings()['login.system_name']

export function usePublicSystemName(systemName?: string): string {
  const [resolvedSystemName, setResolvedSystemName] = useState(() => {
    if (typeof systemName === 'string' && systemName.trim()) {
      return systemName.trim()
    }
    return DEFAULT_SYSTEM_NAME
  })

  useEffect(() => {
    if (typeof systemName === 'string' && systemName.trim()) {
      setResolvedSystemName(systemName.trim())
      return
    }

    let cancelled = false

    const loadSystemName = async () => {
      try {
        const brandingSettings = await getLoginBrandingSettings()
        if (!cancelled) {
          setResolvedSystemName(brandingSettings['login.system_name'])
        }
      } catch {
        if (!cancelled) {
          setResolvedSystemName(DEFAULT_SYSTEM_NAME)
        }
      }
    }

    const handleBrandingUpdated = (event: Event) => {
      const customEvent = event as CustomEvent<LoginBrandingSettings>
      const nextSystemName = customEvent.detail?.['login.system_name']
      if (typeof nextSystemName === 'string' && nextSystemName.trim()) {
        setResolvedSystemName(nextSystemName.trim())
        return
      }
      setResolvedSystemName(DEFAULT_SYSTEM_NAME)
    }

    loadSystemName()
    window.addEventListener(LOGIN_BRANDING_UPDATED_EVENT, handleBrandingUpdated as EventListener)

    return () => {
      cancelled = true
      window.removeEventListener(LOGIN_BRANDING_UPDATED_EVENT, handleBrandingUpdated as EventListener)
    }
  }, [systemName])

  return resolvedSystemName
}

export function PublicPageFooter({ systemName }: AuthNavbarProps) {
  const resolvedSystemName = usePublicSystemName(systemName)

  return (
    <p className="text-center mt-6 text-slate-400 dark:text-slate-500 text-xs">
      &copy; {new Date().getFullYear()} {resolvedSystemName}
    </p>
  )
}

export function AuthNavbar({ systemName }: AuthNavbarProps) {
  const location = useLocation()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)
  const resolvedSystemName = usePublicSystemName(systemName)
  const online = isOnlineEnv()
  /** 根据当前环境过滤菜单项：仅线上正式环境(xy.zhinianboke.com)显示受域名限制的菜单 */
  const filteredItems = NAV_ITEMS.filter(item => !item.hideOnLocal || online)

  // 主题切换（统一在 Navbar 内管理，避免各页面重复实现和遮挡手机端汉堡菜单）
  const [isDark, setIsDark] = useState(false)
  useEffect(() => {
    setIsDark(initializeThemeMode() === 'dark')
  }, [])
  const toggleTheme = () => {
    setIsDark(toggleThemeMode() === 'dark')
  }

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-white/95 dark:bg-slate-900/95 backdrop-blur-sm border-b border-slate-200 dark:border-slate-700">
      <div className="max-w-7xl mx-auto px-4 sm:px-6">
        <div className="flex items-center justify-between h-14">
          {/* Logo */}
          <Link to="/login" className="flex items-center gap-2 flex-shrink-0">
            <div className="w-8 h-8 rounded-lg bg-blue-500 flex items-center justify-center">
              <MessageSquare className="w-4 h-4 text-white" />
            </div>
            <span className="text-sm font-bold text-slate-900 dark:text-white hidden sm:inline">
              {resolvedSystemName}
            </span>
          </Link>

          {/* 桌面端菜单 */}
          <div className="hidden sm:flex items-center gap-1">
            {filteredItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path

              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={cn(
                    'flex items-center gap-1.5 px-3 py-2 rounded-md text-sm font-medium transition-colors',
                    isActive
                      ? 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30'
                      : 'text-slate-600 dark:text-slate-300 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                  )}
                >
                  <Icon className="w-4 h-4" />
                  {item.label}
                </Link>
              )
            })}
          </div>

          {/* 主题切换按钮（桌面和手机端都显示，放在汉堡菜单左侧避免遮挡） */}
          <div className="flex items-center gap-1">
            <button
              onClick={toggleTheme}
              className="p-2 rounded-md text-slate-600 dark:text-slate-300
                         hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              title={isDark ? '切换到亮色模式' : '切换到暗色模式'}
            >
              {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
            {/* 手机端汉堡菜单按钮 */}
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="sm:hidden p-2 rounded-md text-slate-600 dark:text-slate-300
                         hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            >
              {mobileMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>
      </div>

      {/* 手机端下拉菜单 */}
      {mobileMenuOpen && (
        <div className="sm:hidden border-t border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
          <div className="px-3 py-2 space-y-1">
            {filteredItems.map((item) => {
              const Icon = item.icon
              const isActive = location.pathname === item.path

              return (
                <Link
                  key={item.path}
                  to={item.path}
                  onClick={() => setMobileMenuOpen(false)}
                  className={cn(
                    'flex items-center gap-2 px-3 py-2.5 rounded-md text-sm font-medium transition-colors',
                    isActive
                      ? 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/30'
                      : 'text-slate-600 dark:text-slate-300 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-slate-100 dark:hover:bg-slate-800'
                  )}
                >
                  <Icon className="w-4 h-4" />
                  {item.label}
                </Link>
              )
            })}
          </div>
        </div>
      )}
    </nav>
  )
}
