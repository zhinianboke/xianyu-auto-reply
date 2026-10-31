/** 在公开首页广告下方展示与「关于」页面相同的联系方式和二维码。 */
import { useEffect, useState } from 'react'
import { Gift, Loader2, MessageCircle, Users, X } from 'lucide-react'
import { getQrcodeUrl } from '@/api/settings'
import { useUIStore } from '@/store/uiStore'

const CONTACTS = [
  { key: 'wechat', label: '微信群', description: '扫码加入微信交流群', icon: MessageCircle, color: 'text-green-500', hover: 'hover:border-green-400', fallback: 'https://xy.zhinianboke.com/static/qrcode/wechat-group.png' },
  { key: 'qq', label: 'QQ群', description: '扫码加入QQ交流群', icon: Users, color: 'text-blue-500', hover: 'hover:border-blue-400', fallback: 'https://xy.zhinianboke.com/static/qrcode/qq-group.jpg' },
  { key: 'wechat_official', label: '微信公众号', description: '关注公众号发送 最新源码 获取最新代码', icon: MessageCircle, color: 'text-green-600', hover: 'hover:border-green-500', fallback: 'https://xy.zhinianboke.com/static/qrcode/wechat-official-group.jpg' },
  { key: 'telegram', label: 'Telegram', description: '扫码加入Telegram群', icon: MessageCircle, color: 'text-blue-400', hover: 'hover:border-blue-400', fallback: 'https://xy.zhinianboke.com/static/qrcode/telegram-group.png' },
  { key: 'reward', label: '赞赏支持', description: '如果觉得好用，请作者喝杯咖啡', icon: Gift, color: 'text-red-500', hover: 'hover:border-red-400', fallback: 'https://xy.zhinianboke.com/static/qrcode/reward-group.png' },
] as const

type ContactKey = (typeof CONTACTS)[number]['key']
type ContactImage = { key: ContactKey; label: string; url: string }

/** 将后台返回的二维码地址限制为 HTTP(S)，并允许本站相对路径。 */
function resolveImageUrl(value: string): string | null {
  try {
    const url = new URL(value, window.location.origin)
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : null
  } catch {
    return null
  }
}

export function HomeContacts() {
  const { addToast } = useUIStore()
  const [images, setImages] = useState<Record<ContactKey, string>>(() =>
    Object.fromEntries(CONTACTS.map((contact) => [contact.key, contact.fallback])) as Record<ContactKey, string>,
  )
  const [loading, setLoading] = useState(true)
  const [failedImages, setFailedImages] = useState<Set<ContactKey>>(new Set())
  const [preview, setPreview] = useState<ContactImage | null>(null)
  const [previewFailed, setPreviewFailed] = useState(false)

  useEffect(() => {
    let active = true
    setLoading(true)

    Promise.all(CONTACTS.map(async (contact) => {
      try {
        const result = await getQrcodeUrl(contact.key)
        if (result.success && result.data?.image_url) {
          return { key: contact.key, url: resolveImageUrl(result.data.image_url) || contact.fallback }
        }
        return { key: contact.key, url: contact.fallback }
      } catch {
        return { key: contact.key, url: contact.fallback, failed: true }
      }
    })).then((results) => {
      if (!active) return
      setImages(Object.fromEntries(results.map((item) => [item.key, item.url])) as Record<ContactKey, string>)
      const failures = results.filter((item) => 'failed' in item)
      if (failures.length) {
        addToast({ type: 'error', message: `获取${failures.map((item) => CONTACTS.find((contact) => contact.key === item.key)?.label).filter(Boolean).join('、')}二维码失败，正在显示默认联系方式` })
      }
      setLoading(false)
    })

    return () => { active = false }
  }, [addToast])

  const openPreview = (contact: (typeof CONTACTS)[number]) => {
    const url = resolveImageUrl(images[contact.key])
    if (!url) {
      addToast({ type: 'error', message: `${contact.label}二维码地址无效` })
      return
    }
    setPreview({ key: contact.key, label: contact.label, url })
    setPreviewFailed(false)
  }

  return (
    <section className="relative mt-5" aria-label="联系方式" aria-busy={loading}>
      <div className="mb-3">
        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">联系方式</h2>
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-5">
        {CONTACTS.map((contact) => {
          const Icon = contact.icon
          return (
            <article key={contact.key} className="vben-card min-w-0">
              <div className="vben-card-header">
                <h3 className="vben-card-title"><Icon className={`h-4 w-4 ${contact.color}`} />{contact.label}</h3>
              </div>
              <div className="vben-card-body text-center">
                <button
                  type="button"
                  onClick={() => openPreview(contact)}
                  aria-label={`放大查看${contact.label}二维码`}
                  disabled={Boolean(failedImages.has(contact.key))}
                  className={`mx-auto block h-[156px] w-[156px] overflow-hidden rounded-lg border border-slate-200 transition-all duration-200 hover:scale-[1.02] hover:shadow-md dark:border-slate-700 ${contact.hover} disabled:cursor-default`}
                >
                  {failedImages.has(contact.key) ? (
                    <span className="flex h-full items-center justify-center px-3 text-sm text-slate-500 dark:text-slate-400">二维码加载失败</span>
                  ) : (
                    <img
                      src={images[contact.key]}
                      alt={`${contact.label}二维码`}
                      loading="lazy"
                      className="h-full w-full object-cover object-center"
                      onError={() => setFailedImages((previous) => new Set(previous).add(contact.key))}
                    />
                  )}
                </button>
                <p className="mt-3 min-h-10 text-sm text-slate-500 dark:text-slate-400">{contact.description}</p>
              </div>
            </article>
          )
        })}
      </div>
      {loading && (
        <div className="absolute inset-0 z-10 flex items-center justify-center gap-2 rounded-lg bg-white/75 text-sm text-slate-600 backdrop-blur-sm dark:bg-slate-900/75 dark:text-slate-300" role="status">
          <Loader2 className="h-5 w-5 animate-spin text-[rgb(var(--color-primary))]" />正在加载联系方式...
        </div>
      )}
      {preview && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-label={`${preview.label}二维码`}>
          <div className="relative max-h-[90vh] max-w-[90vw] rounded-lg bg-white p-3 shadow-2xl dark:bg-slate-800">
            <button type="button" onClick={() => setPreview(null)} aria-label="关闭二维码预览" className="absolute -right-2 -top-11 rounded-md p-2 text-white transition-colors hover:bg-white/10">
              <X className="h-6 w-6" />
            </button>
            {previewFailed ? (
              <p className="flex h-64 w-64 items-center justify-center text-sm text-slate-500 dark:text-slate-400">二维码加载失败</p>
            ) : (
              <img src={preview.url} alt={`${preview.label}二维码大图`} className="max-h-[82vh] max-w-[86vw] object-contain" onError={() => setPreviewFailed(true)} />
            )}
          </div>
        </div>
      )}
    </section>
  )
}
