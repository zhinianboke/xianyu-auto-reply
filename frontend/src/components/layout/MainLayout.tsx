import { Suspense } from 'react'
import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { TopNavbar } from './TopNavbar'
import { TabsBar } from './TabsBar'
import { useUIStore } from '@/store/uiStore'
import { cn } from '@/utils/cn'
import { Loading } from '@/components/common/Loading'

function PageContentLoading() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center">
      <Loading />
    </div>
  )
}

export function MainLayout() {
  const { sidebarCollapsed } = useUIStore()

  return (
    <div className="min-h-screen xianyu-wms-shell text-slate-800 dark:text-[#d4d4d4] transition-colors duration-200">
      <Sidebar />
      
      {/* Main content area - 响应侧边栏收缩状态 */}
      <div className={cn(
        'min-h-screen flex flex-col transition-[margin] duration-200',
        // <640px 无边距，>=640px 根据收缩状态调整
        'ml-0 sm:ml-16',
        !sidebarCollapsed && 'sm:ml-[230px]'
      )}>
        {/* Fixed header area */}
        <div className="sticky top-0 z-30 xianyu-wms-sticky">
          {/* Top navbar */}
          <TopNavbar />

          {/* Tabs bar */}
          <TabsBar />
        </div>
        
        {/* Page content */}
        <main className="flex-1 overflow-x-hidden" style={{ padding: '14px 16px' }}>
          <Suspense fallback={<PageContentLoading />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  )
}
