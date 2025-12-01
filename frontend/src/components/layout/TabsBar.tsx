import { useEffect } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { X, Home } from 'lucide-react'
import { create } from 'zustand'
import { persist, createJSONStorage } from 'zustand/middleware'
import { cn } from '@/utils/cn'

interface Tab {
  path: string
  title: string
  closable: boolean
}

interface TabsStore {
  tabs: Tab[]
  activeTab: string
  addTab: (tab: Tab) => void
  removeTab: (path: string) => void
  setActiveTab: (path: string) => void
}

// 路由标题映射
const routeTitles: Record<string, string> = {
  '/dashboard': '仪表盘',
  '/accounts': '账号管理',
  '/items': '商品管理',
  '/keywords': '自动回复',
  '/item-replies': '指定商品回复',
  '/orders': '订单管理',
  '/cards': '卡券管理',
  '/delivery': '自动发货',
  '/notification-channels': '通知渠道',
  '/message-notifications': '消息通知',
  '/item-search': '商品搜索',
  '/settings': '系统设置',
  '/admin/users': '用户管理',
  '/admin/logs': '系统日志',
  '/admin/risk-logs': '风控日志',
  '/admin/data': '数据管理',
  '/about': '关于',
}

export const useTabsStore = create<TabsStore>()(
  persist(
    (set, get) => ({
      tabs: [{ path: '/dashboard', title: '仪表盘', closable: false }],
      activeTab: '/dashboard',
      
      addTab: (tab) => {
        const { tabs } = get()
        const exists = tabs.find(t => t.path === tab.path)
        if (!exists) {
          set({ tabs: [...tabs, tab], activeTab: tab.path })
        } else {
          set({ activeTab: tab.path })
        }
      },
      
      removeTab: (path) => {
        const { tabs, activeTab } = get()
        const newTabs = tabs.filter(t => t.path !== path)
        
        // 如果关闭的是当前标签，切换到最后一个标签
        if (activeTab === path && newTabs.length > 0) {
          set({ tabs: newTabs, activeTab: newTabs[newTabs.length - 1].path })
        } else {
          set({ tabs: newTabs })
        }
      },
      
      setActiveTab: (path) => set({ activeTab: path }),
    }),
    {
      name: 'tabs-storage',
      storage: createJSONStorage(() => localStorage),
    }
  )
)

export function TabsBar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { tabs, activeTab, addTab, removeTab, setActiveTab } = useTabsStore()

  // 监听路由变化，自动添加标签
  useEffect(() => {
    const path = location.pathname
    const title = routeTitles[path]
    
    if (title) {
      addTab({
        path,
        title,
        closable: path !== '/dashboard',
      })
    }
  }, [location.pathname])

  const handleTabClick = (path: string) => {
    setActiveTab(path)
    navigate(path)
  }

  const handleTabClose = (e: React.MouseEvent, path: string) => {
    e.stopPropagation()
    removeTab(path)
    
    // 如果关闭的是当前标签，导航到新的活动标签
    if (activeTab === path) {
      const remainingTabs = tabs.filter(t => t.path !== path)
      if (remainingTabs.length > 0) {
        navigate(remainingTabs[remainingTabs.length - 1].path)
      }
    }
  }

  return (
    <div className="tabs-bar overflow-x-auto scrollbar-hide">
      <div className="flex min-w-max">
        {tabs.map((tab) => (
          <div
            key={tab.path}
            onClick={() => handleTabClick(tab.path)}
            className={cn(
              activeTab === tab.path ? 'tab-item-active' : 'tab-item',
              'whitespace-nowrap flex-shrink-0'
            )}
          >
            {tab.path === '/dashboard' && <Home className="w-3.5 h-3.5" />}
            <span className="text-xs sm:text-sm">{tab.title}</span>
            {tab.closable && (
              <button
                onClick={(e) => handleTabClose(e, tab.path)}
                className="tab-close"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
