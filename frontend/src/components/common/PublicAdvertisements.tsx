/** 公开广告展示组件：左侧推荐轮播，右侧可展开的文字广告，供首页和仪表盘复用。 */
import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { ChevronDown, ChevronUp, ExternalLink, Loader2, RefreshCw } from 'lucide-react'
import type { AdvertisementPlacement, PublicAdsResponse } from '@/api/advertisements'

interface PublicAdvertisementsProps {
  placement: AdvertisementPlacement
  adsData: PublicAdsResponse
  adsLoading: boolean
  adsError: string
  loadAds: () => Promise<void>
}

/** 仅允许 HTTP(S) 或相对地址，防止广告链接和图片执行不可信协议。 */
function getAdUrl(value: string | null): string | undefined {
  if (!value?.trim()) return undefined
  try {
    const url = new URL(value.trim(), window.location.origin)
    return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined
  } catch {
    return undefined
  }
}

/** 在卡片内容区提供遮罩与加载提示。 */
function AdsLoading() {
  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center gap-2 bg-white/80 text-sm text-slate-600 backdrop-blur-sm dark:bg-slate-900/80 dark:text-slate-300" role="status">
      <Loader2 className="h-6 w-6 animate-spin text-[rgb(var(--color-primary))]" />
      广告加载中...
    </div>
  )
}

/** 展示实际公开广告，并支持轮播选择、文字展开及失败后重试。 */
export function PublicAdvertisements({ placement, adsData, adsLoading, adsError, loadAds }: PublicAdvertisementsProps) {
  const [carouselIndex, setCarouselIndex] = useState(0)
  const [expandedTextAds, setExpandedTextAds] = useState<Set<number>>(new Set())
  const [failedImageUrl, setFailedImageUrl] = useState<string | null>(null)
  const currentAd = adsData.carousel[carouselIndex] || adsData.carousel[0]
  const currentImageUrl = getAdUrl(currentAd?.image_url || null)
  const carouselHeightClass = placement === 'home' ? 'h-80 sm:h-[30rem]' : 'h-48 sm:h-56'
  const textAdsHeightClass = placement === 'home' ? 'h-80 sm:h-[30rem]' : 'max-h-48 sm:max-h-56'

  useEffect(() => {
    setCarouselIndex(0)
    setExpandedTextAds(new Set())
    setFailedImageUrl(null)
  }, [adsData])

  useEffect(() => {
    if (adsLoading || adsData.carousel.length <= 1) return
    const timer = setInterval(() => {
      setCarouselIndex((previous) => (previous + 1) % adsData.carousel.length)
    }, 4000)
    return () => clearInterval(timer)
  }, [adsData.carousel.length, adsLoading])

  /** 切换指定文字广告的展开状态，不影响其他广告。 */
  const toggleTextAd = (id: number) => {
    setExpandedTextAds((previous) => {
      const next = new Set(previous)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  return (
    <div className="space-y-3" aria-busy={adsLoading}>
      {adsError && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-600 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-400" role="alert">
          <span className="min-w-0 break-words">{adsError}</span>
          <button type="button" onClick={() => void loadAds()} disabled={adsLoading} className="btn-ios-secondary btn-sm">
            <RefreshCw className="h-4 w-4" />重新加载
          </button>
        </div>
      )}
      <motion.div initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.2 }} className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <section className="vben-card min-w-0" aria-label="推荐广告">
          <div className="vben-card-header"><h2 className="vben-card-title">推荐广告</h2></div>
          <div className="vben-card-body !p-0">
            <div className={`relative ${carouselHeightClass} overflow-hidden rounded-b-lg bg-slate-100 dark:bg-slate-800`}>
              {adsLoading && <AdsLoading />}
              {currentAd ? (
                <AnimatePresence mode="wait">
                  <motion.a
                    key={`${currentAd.source || 'local'}-${currentAd.id}`}
                    href={getAdUrl(currentAd.link)} target="_blank" rel="noopener noreferrer"
                    className="absolute inset-0 block bg-slate-100 dark:bg-slate-800"
                    initial={{ y: '100%', opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: '-100%', opacity: 0 }}
                    transition={{ duration: 0.4, ease: 'easeInOut' }}
                  >
                    {currentImageUrl && failedImageUrl !== currentImageUrl ? (
                      <img src={currentImageUrl} alt={currentAd.title} className="h-full w-full object-contain" onError={() => setFailedImageUrl(currentImageUrl)} />
                    ) : (
                      <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-slate-100 px-4 text-center text-slate-800 dark:bg-slate-800 dark:text-slate-100">
                        <span className="break-words text-xl font-bold">{currentAd.title}</span>
                        {currentAd.image_url && <span className="text-sm">广告图片加载失败</span>}
                      </div>
                    )}
                    <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/80 to-transparent p-3">
                      <h3 className="flex items-center gap-1.5 text-sm font-medium text-white">
                        {currentAd.source === 'remote' && <span className="shrink-0 rounded bg-[rgb(var(--color-primary))] px-1.5 py-0.5 text-[10px] leading-none">官方</span>}
                        <span className="truncate">{currentAd.title}</span>
                      </h3>
                      {currentAd.content && <p className="mt-1 line-clamp-2 text-xs text-white/90">{currentAd.content}</p>}
                    </div>
                  </motion.a>
                </AnimatePresence>
              ) : !adsLoading && (
                <div className="flex h-full items-center justify-center text-sm text-slate-500 dark:text-slate-400">
                  {adsError ? '推荐广告加载失败' : '暂无轮播广告'}
                </div>
              )}
              {adsData.carousel.length > 1 && (
                <div className="absolute inset-x-0 top-3 z-10 flex justify-center gap-1.5">
                  {adsData.carousel.map((ad, index) => (
                    <button key={ad.id} type="button" onClick={() => setCarouselIndex(index)} disabled={adsLoading} aria-label={`查看第${index + 1}条推荐广告`} aria-pressed={index === carouselIndex} className={`h-2.5 w-2.5 rounded-full ring-1 ring-black/20 transition-colors ${index === carouselIndex ? 'bg-white' : 'bg-white/40'}`} />
                  ))}
                </div>
              )}
            </div>
          </div>
        </section>
        <section className="vben-card min-w-0" aria-label="文字广告">
          <div className="vben-card-header"><h2 className="vben-card-title">文字广告</h2></div>
          <div className="vben-card-body relative">
            {adsLoading && <AdsLoading />}
            <div className={`${textAdsHeightClass} space-y-2 overflow-y-auto`}>
              {adsData.text.length > 0 ? adsData.text.map((ad) => (
                <div key={ad.id} className="overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700">
                  <div className="flex items-center justify-between bg-slate-50 p-3 dark:bg-slate-800">
                    <a href={getAdUrl(ad.link)} target="_blank" rel="noopener noreferrer" className="flex min-w-0 flex-1 items-center gap-1 text-sm font-medium text-[rgb(var(--color-primary))] hover:underline">
                      {ad.source === 'remote' && <span className="shrink-0 rounded bg-[rgb(var(--color-primary-light))] px-1.5 py-0.5 text-[10px] leading-none">官方</span>}
                      <span className="truncate">{ad.title}</span>
                      {getAdUrl(ad.link) && <ExternalLink className="h-3 w-3 shrink-0" />}
                    </a>
                    {ad.content && (
                      <button type="button" onClick={() => toggleTextAd(ad.id)} aria-label={`${expandedTextAds.has(ad.id) ? '收起' : '展开'}文字广告：${ad.title}`} aria-expanded={expandedTextAds.has(ad.id)} className="ml-2 rounded p-1 text-slate-500 transition-colors hover:bg-slate-200 dark:text-slate-400 dark:hover:bg-slate-700">
                        {expandedTextAds.has(ad.id) ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                      </button>
                    )}
                  </div>
                  <AnimatePresence>
                    {expandedTextAds.has(ad.id) && ad.content && (
                      <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }} transition={{ duration: 0.2 }} className="overflow-hidden">
                        <p className="whitespace-pre-wrap break-words border-t border-slate-200 p-3 text-sm text-slate-600 dark:border-slate-700 dark:text-slate-400">{ad.content}</p>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )) : (
                <div className="flex h-32 items-center justify-center rounded-lg border border-dashed border-slate-300 text-sm text-slate-500 dark:border-slate-600 dark:text-slate-400">
                  {!adsLoading && (adsError ? '文字广告加载失败' : '广告位招租')}
                </div>
              )}
            </div>
          </div>
        </section>
      </motion.div>
    </div>
  )
}
