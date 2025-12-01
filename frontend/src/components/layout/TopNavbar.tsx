import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Sun, Moon, LogOut, ChevronDown } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'
import { cn } from '@/utils/cn'

export function TopNavbar() {
  const navigate = useNavigate()
  const { user, clearAuth } = useAuthStore()
  const [isDark, setIsDark] = useState(false)
  const [showUserMenu, setShowUserMenu] = useState(false)

  // 初始化主题
  useEffect(() => {
    const savedTheme = localStorage.getItem('theme')
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
    const shouldBeDark = savedTheme === 'dark' || (!savedTheme && prefersDark)
    
    setIsDark(shouldBeDark)
    document.documentElement.classList.toggle('dark', shouldBeDark)
  }, [])

  const toggleTheme = () => {
    const newIsDark = !isDark
    setIsDark(newIsDark)
    document.documentElement.classList.toggle('dark', newIsDark)
    localStorage.setItem('theme', newIsDark ? 'dark' : 'light')
  }

  const handleLogout = () => {
    clearAuth()
    navigate('/login')
  }

  return (
    <div className="top-navbar">
      {/* 左侧 - 面包屑或标题（<640px 留空间给汉堡菜单） */}
      <div className="flex items-center gap-2 ml-12 sm:ml-0">
        <span className="text-sm text-slate-500 dark:text-slate-400 hidden sm:inline">欢迎使用闲鱼管理系统</span>
        <span className="text-sm text-slate-500 dark:text-slate-400 sm:hidden">闲鱼管理</span>
      </div>

      {/* 右侧 - 工具栏 */}
      <div className="flex items-center gap-1 sm:gap-2">
        {/* 主题切换 */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-md text-slate-500 dark:text-slate-400 
                     hover:bg-slate-100 dark:hover:bg-slate-700 
                     hover:text-slate-700 dark:hover:text-slate-200
                     transition-colors duration-150"
          title={isDark ? '切换到亮色模式' : '切换到暗色模式'}
        >
          {isDark ? <Sun className="w-5 h-5" /> : <Moon className="w-5 h-5" />}
        </button>

        {/* 用户菜单 */}
        <div className="relative">
          <button
            onClick={() => setShowUserMenu(!showUserMenu)}
            className="flex items-center gap-1 sm:gap-2 px-2 sm:px-3 py-1.5 rounded-md
                       text-slate-700 dark:text-slate-200
                       hover:bg-slate-100 dark:hover:bg-slate-700
                       transition-colors duration-150"
          >
            <div className="w-7 h-7 rounded-full bg-blue-500 flex items-center justify-center text-white text-xs font-medium">
              {(user?.username || 'U').charAt(0).toUpperCase()}
            </div>
            <span className="text-sm font-medium hidden sm:inline">{user?.username || '用户'}</span>
            <ChevronDown className="w-4 h-4 text-slate-400 hidden sm:block" />
          </button>

          {/* 下拉菜单 */}
          {showUserMenu && (
            <>
              <div 
                className="fixed inset-0 z-40" 
                onClick={() => setShowUserMenu(false)}
              />
              <div className="absolute right-0 mt-2 w-48 bg-white dark:bg-slate-800 
                              rounded-lg shadow-lg ring-1 ring-black/5 dark:ring-white/10
                              py-1 z-50 animate-fade-in">
                <div className="px-4 py-2 border-b border-slate-100 dark:border-slate-700">
                  <p className="text-sm font-medium text-slate-900 dark:text-slate-100">{user?.username}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    {user?.is_admin ? '管理员' : '普通用户'}
                  </p>
                </div>
                <button
                  onClick={handleLogout}
                  className={cn(
                    'w-full flex items-center gap-2 px-4 py-2 text-sm',
                    'text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20',
                    'transition-colors duration-150'
                  )}
                >
                  <LogOut className="w-4 h-4" />
                  退出登录
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
