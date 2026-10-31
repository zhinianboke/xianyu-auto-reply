/** 公开首页：复用公共导航及仪表盘广告组件，无需登录即可查看。 */
import { useEffect } from 'react'
import { AuthNavbar, PublicPageFooter } from '@/components/common/AuthNavbar'
import { PublicAdvertisements } from '@/components/common/PublicAdvertisements'
import { usePublicAdvertisements } from '@/components/common/usePublicAdvertisements'
import { HomeContacts } from './HomeContacts'

export function Home() {
  const advertisements = usePublicAdvertisements('home')
  const { loadAds } = advertisements

  useEffect(() => { void loadAds() }, [loadAds])

  return (
    <div className="min-h-screen bg-slate-50 transition-colors duration-200 dark:bg-slate-900">
      <AuthNavbar />
      <main className="mx-auto max-w-7xl px-3 pb-10 pt-20 sm:px-6">
        <PublicAdvertisements placement="home" {...advertisements} />
        <HomeContacts />
        <PublicPageFooter />
      </main>
    </div>
  )
}
