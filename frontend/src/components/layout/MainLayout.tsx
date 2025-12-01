import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { TopNavbar } from './TopNavbar'
import { TabsBar } from './TabsBar'
import { Toast } from '@/components/common/Toast'
import { useUIStore } from '@/store/uiStore'
import { cn } from '@/utils/cn'

export function MainLayout() {
  const { sidebarCollapsed } = useUIStore()

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors duration-200">
      <Sidebar />
      
      {/* Main content area - 响应侧边栏收缩状态 */}
      <div className={cn(
        'min-h-screen flex flex-col transition-[margin] duration-200',
        // <640px 无边距，>=640px 根据收缩状态调整（16px / 56px）
        'ml-0 sm:ml-16',
        !sidebarCollapsed && 'sm:ml-56'
      )}>
        {/* Fixed header area */}
        <div className="sticky top-0 z-30 bg-slate-50 dark:bg-slate-900">
          {/* Top navbar */}
          <TopNavbar />
          
          {/* Tabs bar */}
          <TabsBar />
        </div>
        
        {/* Page content */}
        <main className="flex-1 p-3 sm:p-4 lg:p-6 overflow-x-hidden">
          <Outlet />
        </main>
      </div>

      {/* Toast notifications */}
      <Toast />
    </div>
  )
}
