import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Avatar, Button, Dropdown, Menu, Space } from '@arco-design/web-react'
import { Sun, Moon, LogOut, User as UserIcon } from 'lucide-react'
import { useAuthStore } from '@/store/authStore'

export function TopNavbar() {
  const navigate = useNavigate()
  const { user, clearAuth } = useAuthStore()
  const [isDark, setIsDark] = useState(false)

  useEffect(() => {
    const savedTheme = localStorage.getItem('theme') || 'light'
    const shouldBeDark = savedTheme === 'dark'

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

  const userMenu = (
    <Menu className="xianyu-user-dropdown">
      <Menu.Item key="profile" disabled>
        <div className="xianyu-user-dropdown-profile">
          <div className="font-medium text-slate-900">{user?.username || '用户'}</div>
          <div className="text-xs text-slate-500">{user?.is_admin ? '管理员' : '普通用户'}</div>
        </div>
      </Menu.Item>
      <Menu.Item key="logout" onClick={handleLogout}>
        <span className="inline-flex items-center gap-2 text-red-600">
          <LogOut className="w-4 h-4" />
          退出登录
        </span>
      </Menu.Item>
    </Menu>
  )

  return (
    <div className="top-navbar xianyu-arco-header">
      <div className="flex items-center gap-2 ml-12 sm:ml-0 min-w-0">
      </div>

      <Space size={12}>
        <Button
          type="text"
          shape="circle"
          icon={isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          onClick={toggleTheme}
          title={isDark ? '切换到亮色模式' : '切换到暗色模式'}
        />

        <Dropdown droplist={userMenu} trigger="click" position="br">
          <button className="xianyu-user-entry">
            <Avatar size={30} className="xianyu-user-avatar">
              {(user?.username || 'U').charAt(0).toUpperCase()}
            </Avatar>
            <span className="hidden sm:inline">{user?.username || '用户'}</span>
            <UserIcon className="hidden sm:block w-4 h-4 text-slate-400" />
          </button>
        </Dropdown>
      </Space>
    </div>
  )
}
