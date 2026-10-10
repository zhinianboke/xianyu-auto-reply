/**
 * 公开关于页面
 *
 * 功能：
 * 1. 为未登录用户提供与登录后「关于」菜单完全一致的页面内容
 * 2. 复用公共顶部导航栏，保持登录页等公开页面的导航体验一致
 */
import { AuthNavbar } from '@/components/common/AuthNavbar'
import { About } from './About'

export function PublicAbout() {
  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors duration-200">
      <AuthNavbar />
      <main className="pt-20 pb-10 px-3 sm:px-4 lg:px-6">
        <About />
      </main>
    </div>
  )
}
