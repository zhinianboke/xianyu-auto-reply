import { useEffect, useState, useRef } from 'react'
import { createPortal } from 'react-dom'
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
  removeTabsToRight: (path: string) => void
  removeTabsToLeft: (path: string) => void
  removeAllTabs: () => void
  setActiveTab: (path: string) => void
}

// 路由标题映射
const routeTitles: Record<string, string> = {
  '/dashboard': '仪表盘',
  '/accounts': '闲鱼账号',
  '/items': '商品',
  '/online-chat-new': '在线聊天',
  '/keywords': '关键词回复',
  '/item-replies': '商品回复',
  '/message-logs': '消息日志',
  '/message-filters': '消息过滤',
  '/orders': '订单',
  '/cards': '卡密库存',
  '/delivery': '自动发货',
  '/notification-channels': '通知渠道',
  '/message-notifications': '消息记录',
  '/item-search': '商品搜索',
  '/data-analysis/overview': '数据总览',
  '/goofish-compass': 'Goofish 罗盘',
  '/goofish-scheduled-crawler': '定时采集',
  '/auto-review': '订单评价',
  '/interaction/items': '商品互动助手',
  '/distribution/sources': '货源管理',
  '/distribution/supply': '货源广场',
  '/distribution/card-pickup': '分销卡券',
  '/distribution/docked': '对接商品',
  '/distribution/agent-orders': '代理订单',
  '/distribution/dealers': '分销商管理',
  '/distribution/sub-dealers': '下级分销商',
  '/product-publish/materials': '素材库',
  '/product-publish/single': '单品发布',
  '/product-publish/batch': '批量发布',
  '/product-publish/addresses': '随机地址库',
  '/product-publish/logs': '发布日志',
  '/blacklist': '黑名单管理',
  '/personal-settings': '个人设置',
  '/settings': '系统设置',
  '/settings/ai': 'AI 设置',
  '/settings/profile': '个人资料',
  '/settings/backup': '数据备份',
  '/ai/calls': '调用明细',
  '/ai/tokens': 'Token统计',
  '/settings/reply-safety': '回复安全设置',
  '/tools/reply-simulator': '回复模拟',
  '/admin/announcements': '公告管理',
  '/admin/ad-manage': '广告管理',
  '/admin/scheduled-tasks': '定时任务',
  '/admin/users': '用户管理',
  '/admin/logs': '系统日志',
  '/admin/account-login-logs': '账号登录日志',
  '/admin/db-backup-logs': '数据库备份日志',
  '/admin/fund-flows': '资金流水',
  '/admin/risk-logs': '风控日志',
  '/risk-logs': '风控日志',
  '/admin/data': '数据管理',
  '/admin/health': '系统健康',
  '/admin/account-exceptions': '账号异常',
  '/admin/redelivery-batches': '补发货日志',
  '/admin/rate-batches': '补评价日志',
  '/admin/polish-batches': '擦亮日志',
  '/admin/login-renew-batches': '登录续期日志',
  '/admin/cookies-refresh-batches': 'Cookies 刷新日志',
  '/admin/api-cookie-renew-batches': '接口续期日志',
  '/admin/close-notice-batches': '通知关闭日志',
  '/admin/red-flower-batches': '求小红花日志',
  '/tutorial': '使用教程',
  '/feedback': '意见反馈',
  '/ad-apply': '广告申请',
  '/disclaimer': '免责声明',
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
        
        if (activeTab === path && newTabs.length > 0) {
          set({ tabs: newTabs, activeTab: newTabs[newTabs.length - 1].path })
        } else {
          set({ tabs: newTabs })
        }
      },
      
      removeTabsToRight: (path) => {
        const { tabs, activeTab } = get()
        const index = tabs.findIndex(t => t.path === path)
        if (index === -1) return
        
        const newTabs = tabs.slice(0, index + 1)
        const activeIndex = tabs.findIndex(t => t.path === activeTab)
        
        if (activeIndex > index) {
          set({ tabs: newTabs, activeTab: path })
        } else {
          set({ tabs: newTabs })
        }
      },
      
      removeTabsToLeft: (path) => {
        const { tabs, activeTab } = get()
        const index = tabs.findIndex(t => t.path === path)
        if (index === -1) return
        
        // 保留仪表盘和当前标签及右侧的标签
        const newTabs = [tabs[0], ...tabs.slice(index).filter(t => t.path !== '/dashboard')]
        const activeIndex = tabs.findIndex(t => t.path === activeTab)
        
        if (activeIndex < index && activeTab !== '/dashboard') {
          set({ tabs: newTabs, activeTab: path })
        } else {
          set({ tabs: newTabs })
        }
      },
      
      removeAllTabs: () => {
        set({ 
          tabs: [{ path: '/dashboard', title: '仪表盘', closable: false }],
          activeTab: '/dashboard'
        })
      },
      
      setActiveTab: (path) => set({ activeTab: path }),
    }),
    {
      name: 'tabs-storage',
      storage: createJSONStorage(() => localStorage),
    }
  )
)

interface ContextMenuState {
  visible: boolean
  x: number
  y: number
  targetPath: string
}

const CONTEXT_MENU_WIDTH = 144
const CONTEXT_MENU_HEIGHT = 132
const CONTEXT_MENU_MARGIN = 8

export function TabsBar() {
  const location = useLocation()
  const navigate = useNavigate()
  const { tabs, activeTab, addTab, removeTab, removeTabsToRight, removeTabsToLeft, removeAllTabs, setActiveTab } = useTabsStore()
  const [contextMenu, setContextMenu] = useState<ContextMenuState>({
    visible: false,
    x: 0,
    y: 0,
    targetPath: ''
  })
  const menuRef = useRef<HTMLDivElement>(null)

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

  // 点击其他地方关闭右键菜单
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setContextMenu(prev => ({ ...prev, visible: false }))
      }
    }
    
    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [])

  const handleTabClick = (path: string) => {
    setContextMenu(prev => ({ ...prev, visible: false }))
    setActiveTab(path)
    navigate(path)
  }

  const handleTabClose = (e: React.MouseEvent, path: string) => {
    e.stopPropagation()
    removeTab(path)
    
    if (activeTab === path) {
      const remainingTabs = tabs.filter(t => t.path !== path)
      if (remainingTabs.length > 0) {
        navigate(remainingTabs[remainingTabs.length - 1].path)
      }
    }
  }

  const handleContextMenu = (e: React.MouseEvent, path: string) => {
    e.preventDefault()
    e.stopPropagation()
    const maxX = window.innerWidth - CONTEXT_MENU_WIDTH - CONTEXT_MENU_MARGIN
    const maxY = window.innerHeight - CONTEXT_MENU_HEIGHT - CONTEXT_MENU_MARGIN
    const preferredX = e.clientX
    const preferredY = e.clientY

    setContextMenu({
      visible: true,
      x: Math.max(CONTEXT_MENU_MARGIN, Math.min(preferredX, maxX)),
      y: Math.max(CONTEXT_MENU_MARGIN, Math.min(preferredY, maxY)),
      targetPath: path
    })
  }

  const handleCloseCurrentTab = () => {
    const { targetPath } = contextMenu
    if (targetPath !== '/dashboard') {
      removeTab(targetPath)
      if (activeTab === targetPath) {
        navigate('/dashboard')
      }
    }
    setContextMenu(prev => ({ ...prev, visible: false }))
  }

  const handleCloseRightTabs = () => {
    removeTabsToRight(contextMenu.targetPath)
    setContextMenu(prev => ({ ...prev, visible: false }))
  }

  const handleCloseLeftTabs = () => {
    removeTabsToLeft(contextMenu.targetPath)
    setContextMenu(prev => ({ ...prev, visible: false }))
  }

  const handleCloseAllTabs = () => {
    removeAllTabs()
    navigate('/dashboard')
    setContextMenu(prev => ({ ...prev, visible: false }))
  }

  const targetIndex = tabs.findIndex(t => t.path === contextMenu.targetPath)
  const hasRightTabs = targetIndex < tabs.length - 1
  const hasLeftTabs = targetIndex > 1 || (targetIndex === 1 && tabs[0].path === '/dashboard')

  return (
    <>
      <div className="tabs-bar overflow-x-auto scrollbar-hide">
        <div className="flex min-w-max">
          {tabs.map((tab) => (
            <div
              key={tab.path}
              onClick={() => handleTabClick(tab.path)}
              onContextMenu={(e) => handleContextMenu(e, tab.path)}
              className={cn(
                activeTab === tab.path ? 'tab-item-active' : 'tab-item',
                'whitespace-nowrap flex-shrink-0'
              )}
            >
              {tab.path === '/dashboard' && <Home className="w-3.5 h-3.5" />}
              <span className="text-xs sm:text-sm">{routeTitles[tab.path] || tab.title}</span>
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

      {/* 右键菜单 */}
      {contextMenu.visible && createPortal(
        <div
          ref={menuRef}
          className="fixed z-50 w-36 bg-white dark:bg-[#252526]/95 border border-gray-200 dark:border-white/10 rounded-lg shadow-xl py-1 text-xs dark:backdrop-blur-xl"
          style={{ left: `${contextMenu.x}px`, top: `${contextMenu.y}px` }}
        >
          <button
            onClick={handleCloseCurrentTab}
            disabled={contextMenu.targetPath === '/dashboard'}
            className="w-full px-3 py-1 text-left hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            关闭当前
          </button>
          <button
            onClick={handleCloseRightTabs}
            disabled={!hasRightTabs}
            className="w-full px-3 py-1 text-left hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            关闭右侧
          </button>
          <button
            onClick={handleCloseLeftTabs}
            disabled={!hasLeftTabs}
            className="w-full px-3 py-1 text-left hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            关闭左侧
          </button>
          <div className="border-t border-gray-200 dark:border-gray-700 my-0.5" />
          <button
            onClick={handleCloseAllTabs}
            className="w-full px-3 py-1 text-left hover:bg-gray-100 dark:hover:bg-gray-700 text-red-500"
          >
            关闭所有
          </button>
        </div>,
        document.body
      )}
    </>
  )
}
