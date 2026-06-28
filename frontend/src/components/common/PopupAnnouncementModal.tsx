/**
 * 登录弹窗公告组件
 *
 * 功能：
 * 1. 用户每次登录后弹窗展示启用中的公告
 * 2. 样式参照仪表盘「文字广告」模块（标题可跳转 + 内容展示）
 * 3. 同一登录会话内仅弹一次（sessionStorage 标记），重新登录后再次弹出
 * 4. 仅可通过「关闭」按钮关闭，禁止点击遮罩关闭
 */
import { useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Megaphone, ExternalLink, X } from 'lucide-react'
import { getPublicPopupAnnouncements, type PopupAnnouncement } from '@/api/popupAnnouncements'
import { useAuthStore } from '@/store/authStore'

// 同一登录会话内的弹窗展示标记；登录时（authStore.setAuth）会清除该标记
export const POPUP_ANNOUNCEMENT_SHOWN_KEY = 'popup_announcement_shown'

export function PopupAnnouncementModal() {
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [items, setItems] = useState<PopupAnnouncement[]>([])
  const [visible, setVisible] = useState(false)

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    // 本次登录会话已展示过则不再拉取
    if (sessionStorage.getItem(POPUP_ANNOUNCEMENT_SHOWN_KEY)) return

    let cancelled = false
    const load = async () => {
      try {
        const result = await getPublicPopupAnnouncements()
        // 无论是否有公告，本次会话都标记为已处理，避免重复拉取
        sessionStorage.setItem(POPUP_ANNOUNCEMENT_SHOWN_KEY, '1')
        if (!cancelled && result.success && result.data && result.data.items.length > 0) {
          setItems(result.data.items)
          setVisible(true)
        }
      } catch {
        // 拉取失败时静默处理，不影响主流程
      }
    }
    load()

    return () => {
      cancelled = true
    }
  }, [_hasHydrated, isAuthenticated, token])

  const handleClose = () => {
    setVisible(false)
  }

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <motion.div
            className="w-full max-w-lg rounded-2xl bg-white dark:bg-slate-800 shadow-xl overflow-hidden"
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            transition={{ duration: 0.2 }}
          >
            {/* 头部 */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100 dark:border-slate-700">
              <h2 className="flex items-center gap-2 text-lg font-semibold text-slate-900 dark:text-slate-100">
                <Megaphone className="w-5 h-5 text-blue-500" />
                系统公告
              </h2>
              <button
                onClick={handleClose}
                className="p-1 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-lg transition-colors"
                title="关闭"
              >
                <X className="w-5 h-5 text-slate-500" />
              </button>
            </div>

            {/* 公告列表（样式参照仪表盘「文字广告」模块） */}
            <div className="px-5 py-4 space-y-2 max-h-[60vh] overflow-y-auto">
              {items.map((item) => (
                <div
                  key={item.id}
                  className="border border-slate-200 dark:border-slate-700 rounded-lg overflow-hidden"
                >
                  <div className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-800">
                    {item.link ? (
                      <a
                        href={item.link}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex-1 text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline flex items-center gap-1"
                      >
                        {item.source === 'remote' && (
                          <span className="flex-shrink-0 px-1.5 py-0.5 text-[10px] leading-none rounded bg-blue-100 text-blue-600 dark:bg-blue-900/40 dark:text-blue-300">官方</span>
                        )}
                        {item.title}
                        <ExternalLink className="w-3 h-3 flex-shrink-0" />
                      </a>
                    ) : (
                      <span className="flex-1 text-sm font-medium text-slate-900 dark:text-slate-100 flex items-center gap-1">
                        {item.source === 'remote' && (
                          <span className="flex-shrink-0 px-1.5 py-0.5 text-[10px] leading-none rounded bg-blue-100 text-blue-600 dark:bg-blue-900/40 dark:text-blue-300">官方</span>
                        )}
                        {item.title}
                      </span>
                    )}
                  </div>
                  <p className="p-3 text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap border-t border-slate-200 dark:border-slate-700">
                    {item.content}
                  </p>
                </div>
              ))}
            </div>

            {/* 底部 */}
            <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-700 flex justify-end">
              <button onClick={handleClose} className="btn-ios-primary">
                我知道了
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
