/**
 * 关于页面
 * 
 * 功能：
 * 1. 显示系统信息与当前版本
 * 2. 检查是否有新版本，并展示更新详情
 * 3. 显示联系方式（微信群、QQ群）
 * 4. 显示主要功能介绍
 * 5. 显示贡献者和相关链接
 */
import { useCallback, useEffect, useState } from 'react'
import {
  ArrowUpCircle, BarChart3, Bell, Bot, Code, Github, Gift,
  Globe, Loader2, MessageCircle, MessageSquare, RefreshCw, Truck,
  UserCheck, Users, X,
} from 'lucide-react'
import { getQrcodeUrl } from '@/api/settings'
import { checkUpdate, type VersionCheckResult } from '@/api/version'
import { useUIStore } from '@/store/uiStore'
import { useVersionStore } from '@/store/versionStore'
import { UpdateModal } from './UpdateModal'

export function About() {
  const { addToast } = useUIStore()
  // 版本号统一由 versionStore 提供，与侧边栏共享同一取值
  const { currentVersion, setCurrentVersion, fetchCurrentVersion } = useVersionStore()

  const [previewImage, setPreviewImage] = useState<string | null>(null)
  const [totalUsers, setTotalUsers] = useState(0)

  // 群二维码
  const [wechatQrcode, setWechatQrcode] = useState<string | null>(null)
  const [qqQrcode, setQqQrcode] = useState<string | null>(null)
  const [wechatOfficialQrcode, setWechatOfficialQrcode] = useState<string | null>(null)
  const [telegramQrcode, setTelegramQrcode] = useState<string | null>(null)
  const [rewardQrcode, setRewardQrcode] = useState<string | null>(null)

  // 版本检测状态
  const [updateInfo, setUpdateInfo] = useState<VersionCheckResult | null>(null)
  const [hasUpdate, setHasUpdate] = useState(false)
  const [checkingUpdate, setCheckingUpdate] = useState(false)
  const [showUpdateModal, setShowUpdateModal] = useState(false)

  /**
   * 检查是否有新版本
   *
   * @param silent 静默模式。true=页面挂载时自动检查不弹 toast；false=用户手动点击需弹提示
   */
  const handleCheckUpdate = useCallback(async (silent = false) => {
    setCheckingUpdate(true)
    try {
      const result = await checkUpdate()
      const data = result.data

      // 无论成功或失败，后端都会返回 current_version，优先更新本地显示
      if (data?.current_version) {
        setCurrentVersion(data.current_version)
      }

      if (!result.success) {
        if (!silent) {
          addToast({ type: 'error', message: result.message || '检查更新失败' })
        }
        return
      }

      if (!data) {
        if (!silent) {
          addToast({ type: 'error', message: '更新服务器未返回有效数据' })
        }
        return
      }

      if (data.has_update) {
        setUpdateInfo(data)
        setHasUpdate(true)
        if (!silent) {
          setShowUpdateModal(true)
        }
      } else {
        setHasUpdate(false)
        setUpdateInfo(null)
        if (!silent) {
          addToast({
            type: 'success',
            message: `当前已是最新版本 v${data.current_version}`,
          })
        }
      }
    } finally {
      setCheckingUpdate(false)
    }
  }, [addToast, setCurrentVersion])

  useEffect(() => {
    // 获取使用人数
    fetch('/project-stats')
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data?.total_users) {
          setTotalUsers(data.total_users)
        }
      })
      .catch(() => {})

    // 加载群二维码
    getQrcodeUrl('wechat').then(res => {
      if (res.success && res.data?.image_url) {
        setWechatQrcode(res.data.image_url)
      }
    }).catch(() => {})
    getQrcodeUrl('qq').then(res => {
      if (res.success && res.data?.image_url) {
        setQqQrcode(res.data.image_url)
      }
    }).catch(() => {})
    getQrcodeUrl('wechat_official').then(res => {
      if (res.success && res.data?.image_url) {
        setWechatOfficialQrcode(res.data.image_url)
      }
    }).catch(() => {})
    getQrcodeUrl('telegram').then(res => {
      if (res.success && res.data?.image_url) {
        setTelegramQrcode(res.data.image_url)
      }
    }).catch(() => {})
    getQrcodeUrl('reward').then(res => {
      if (res.success && res.data?.image_url) {
        setRewardQrcode(res.data.image_url)
      }
    }).catch(() => {})

    // 先取本地版本号兜底（store 有缓存时不重复请求），保证远程检查更新失败时也能显示当前版本
    fetchCurrentVersion()

    // 页面挂载时静默检查版本（失败不弹 toast，避免无网环境干扰用户）
    handleCheckUpdate(true)
  }, [handleCheckUpdate, fetchCurrentVersion])

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      {/* Header */}
      <div className="text-center mb-6">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-600 mx-auto mb-4 flex items-center justify-center shadow-md">
          <MessageSquare className="w-8 h-8 text-white" />
        </div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
          闲鱼自动回复管理系统
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          智能管理您的闲鱼店铺，提升客服效率
        </p>
        {/* 版本和使用人数 */}
        <div className="flex items-center justify-center gap-3 mt-3 flex-wrap">
          {currentVersion && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gradient-to-r from-emerald-500/10 to-teal-500/10 text-emerald-600 dark:from-emerald-500/20 dark:to-teal-500/20 dark:text-emerald-400 border border-emerald-200/50 dark:border-emerald-500/30">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
              <span>v{currentVersion}</span>
            </div>
          )}
          {hasUpdate && updateInfo && (
            <button
              type="button"
              onClick={() => setShowUpdateModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gradient-to-r from-amber-500/10 to-orange-500/10 text-amber-600 dark:from-amber-500/20 dark:to-orange-500/20 dark:text-amber-400 border border-amber-200/50 dark:border-amber-500/30 hover:from-amber-500/20 hover:to-orange-500/20 transition-all cursor-pointer"
            >
              <ArrowUpCircle className="w-3.5 h-3.5" />
              <span>有更新 v{updateInfo.remote_version}</span>
            </button>
          )}
          {totalUsers > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gradient-to-r from-blue-500/10 to-cyan-500/10 text-blue-600 dark:from-blue-500/20 dark:to-cyan-500/20 dark:text-blue-400 border border-blue-200/50 dark:border-blue-500/30">
              <Globe className="w-3.5 h-3.5" />
              <span>{totalUsers.toLocaleString()} 人使用</span>
            </div>
          )}
        </div>
        {/* 操作按钮 */}
        <div className="flex items-center justify-center gap-2 mt-3">
          <button
            type="button"
            onClick={() => handleCheckUpdate(false)}
            disabled={checkingUpdate}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {checkingUpdate ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
            <span>{checkingUpdate ? '检查中...' : '检查更新'}</span>
          </button>
        </div>
      </div>

      {/* Contact Groups */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <div className="vben-card">
          <div className="vben-card-header">
            <h2 className="vben-card-title">
              <MessageCircle className="w-4 h-4 text-green-500" />
              微信群
            </h2>
          </div>
          <div className="vben-card-body text-center">
            <div
              className="w-[140px] h-[140px] mx-auto overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700 cursor-pointer transition-all duration-200 hover:scale-105 hover:shadow-lg hover:border-green-400"
              onClick={() => wechatQrcode && setPreviewImage(wechatQrcode)}
            >
              {wechatQrcode ? (
                <img
                  src={wechatQrcode}
                  alt="微信群二维码"
                  className="w-full h-full object-cover object-center"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none'
                    const parent = (e.target as HTMLImageElement).parentElement
                    if (parent) {
                      parent.innerHTML = '<p class="text-slate-400 dark:text-slate-500 py-12 text-sm">二维码未配置</p>'
                    }
                  }}
                />
              ) : (
                <p className="text-slate-400 dark:text-slate-500 py-14 text-sm">二维码未配置</p>
              )}
            </div>
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">扫码加入微信交流群</p>
          </div>
        </div>
        <div className="vben-card">
          <div className="vben-card-header">
            <h2 className="vben-card-title">
              <Users className="w-4 h-4 text-blue-500" />
              QQ群
            </h2>
          </div>
          <div className="vben-card-body text-center">
            <div
              className="w-[140px] h-[140px] mx-auto overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700 cursor-pointer transition-all duration-200 hover:scale-105 hover:shadow-lg hover:border-blue-400"
              onClick={() => qqQrcode && setPreviewImage(qqQrcode)}
            >
              {qqQrcode ? (
                <img
                  src={qqQrcode}
                  alt="QQ群二维码"
                  className="w-full h-full object-cover object-center"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none'
                    const parent = (e.target as HTMLImageElement).parentElement
                    if (parent) {
                      parent.innerHTML = '<p class="text-slate-400 dark:text-slate-500 py-12 text-sm">二维码未配置</p>'
                    }
                  }}
                />
              ) : (
                <p className="text-slate-400 dark:text-slate-500 py-14 text-sm">二维码未配置</p>
              )}
            </div>
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">扫码加入QQ交流群</p>
          </div>
        </div>
        <div className="vben-card">
          <div className="vben-card-header">
            <h2 className="vben-card-title">
              <MessageCircle className="w-4 h-4 text-green-600" />
              微信公众号
            </h2>
          </div>
          <div className="vben-card-body text-center">
            <div
              className="w-[140px] h-[140px] mx-auto overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700 cursor-pointer transition-all duration-200 hover:scale-105 hover:shadow-lg hover:border-green-500"
              onClick={() => wechatOfficialQrcode && setPreviewImage(wechatOfficialQrcode)}
            >
              {wechatOfficialQrcode ? (
                <img
                  src={wechatOfficialQrcode}
                  alt="微信公众号二维码"
                  className="w-full h-full object-cover object-center"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none'
                    const parent = (e.target as HTMLImageElement).parentElement
                    if (parent) {
                      parent.innerHTML = '<p class="text-slate-400 dark:text-slate-500 py-12 text-sm">二维码未配置</p>'
                    }
                  }}
                />
              ) : (
                <p className="text-slate-400 dark:text-slate-500 py-14 text-sm">二维码未配置</p>
              )}
            </div>
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">关注公众号发送 最新源码 获取最新代码</p>
          </div>
        </div>
        <div className="vben-card">
          <div className="vben-card-header">
            <h2 className="vben-card-title">
              <MessageCircle className="w-4 h-4 text-blue-400" />
              Telegram
            </h2>
          </div>
          <div className="vben-card-body text-center">
            <div
              className="w-[140px] h-[140px] mx-auto overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700 cursor-pointer transition-all duration-200 hover:scale-105 hover:shadow-lg hover:border-blue-400"
              onClick={() => telegramQrcode && setPreviewImage(telegramQrcode)}
            >
              {telegramQrcode ? (
                <img
                  src={telegramQrcode}
                  alt="Telegram二维码"
                  className="w-full h-full object-cover object-center"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none'
                    const parent = (e.target as HTMLImageElement).parentElement
                    if (parent) {
                      parent.innerHTML = '<p class="text-slate-400 dark:text-slate-500 py-12 text-sm">二维码未配置</p>'
                    }
                  }}
                />
              ) : (
                <p className="text-slate-400 dark:text-slate-500 py-14 text-sm">二维码未配置</p>
              )}
            </div>
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">扫码加入Telegram群</p>
          </div>
        </div>
        <div className="vben-card">
          <div className="vben-card-header">
            <h2 className="vben-card-title">
              <Gift className="w-4 h-4 text-red-500" />
              赞赏支持
            </h2>
          </div>
          <div className="vben-card-body text-center">
            <div
              className="w-[140px] h-[140px] mx-auto overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700 cursor-pointer transition-all duration-200 hover:scale-105 hover:shadow-lg hover:border-red-400"
              onClick={() => rewardQrcode && setPreviewImage(rewardQrcode)}
            >
              {rewardQrcode ? (
                <img
                  src={rewardQrcode}
                  alt="赞赏码"
                  className="w-full h-full object-cover object-center"
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.display = 'none'
                    const parent = (e.target as HTMLImageElement).parentElement
                    if (parent) {
                      parent.innerHTML = '<p class="text-slate-400 dark:text-slate-500 py-12 text-sm">赞赏码未配置</p>'
                    }
                  }}
                />
              ) : (
                <p className="text-slate-400 dark:text-slate-500 py-14 text-sm">赞赏码未配置</p>
              )}
            </div>
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">如果觉得好用，请作者喝杯咖啡</p>
          </div>
        </div>
      </div>

      {/* Features */}
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">主要功能</h2>
        </div>
        <div className="vben-card-body">
          <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
            {[
              { title: '多账号管理', desc: '同时管理多个账号', icon: UserCheck, color: 'text-blue-500' },
              { title: '智能回复', desc: '关键词自动回复', icon: MessageSquare, color: 'text-green-500' },
              { title: 'AI 助手', desc: '智能处理复杂问题', icon: Bot, color: 'text-purple-500' },
              { title: '自动发货', desc: '支持卡密发货', icon: Truck, color: 'text-orange-500' },
              { title: '消息通知', desc: '多渠道推送', icon: Bell, color: 'text-pink-500' },
              { title: '数据统计', desc: '订单商品分析', icon: BarChart3, color: 'text-cyan-500' },
            ].map((feature, index) => (
              <div
                key={index}
                className="p-4 rounded-lg bg-slate-50 dark:bg-slate-800 flex items-center gap-3"
              >
                <div className={`w-10 h-10 rounded-lg bg-white dark:bg-slate-700 flex items-center justify-center shadow-sm ${feature.color}`}>
                  <feature.icon className="w-5 h-5" />
                </div>
                <div className="text-left">
                  <p className="font-medium text-sm text-slate-900 dark:text-slate-100">{feature.title}</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">{feature.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Contributors */}
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">
            <Code className="w-4 h-4" />
            贡献者
          </h2>
        </div>
        <div className="vben-card-body">
          <div className="flex flex-wrap gap-3">
            <a
              href="https://github.com/zhinianboke"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
            >
              <Github className="w-4 h-4 text-slate-600 dark:text-slate-300" />
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">zhinianboke</span>
              <span className="text-xs text-slate-500 dark:text-slate-400">项目作者</span>
            </a>
            <a
              href="https://github.com/legeling"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
            >
              <Github className="w-4 h-4 text-slate-600 dark:text-slate-300" />
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">legeling</span>
              <span className="text-xs text-slate-500 dark:text-slate-400">前端重构</span>
            </a>
          </div>
        </div>
      </div>

      {/* Links */}
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">相关链接</h2>
        </div>
        <div className="vben-card-body">
          <div className="flex gap-3">
            <a
              href="https://github.com/zhinianboke/xianyu-auto-reply"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-900 text-white hover:bg-gray-800 transition-colors text-sm"
            >
              <Github className="w-4 h-4" />
              <span>GitHub</span>
            </a>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="text-center py-4 text-slate-500 dark:text-slate-400 text-sm">
        
      </div>

      {/* 更新详情弹窗（组件内已处理仅关闭按钮退出） */}
      {showUpdateModal && updateInfo && (
        <UpdateModal info={updateInfo} onClose={() => setShowUpdateModal(false)} />
      )}

      {/* 图片预览弹窗 */}
      {previewImage && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={() => setPreviewImage(null)}
        >
          <div className="relative max-w-[90vw] max-h-[90vh]">
            <button
              onClick={() => setPreviewImage(null)}
              className="absolute -top-10 right-0 p-2 text-white hover:text-gray-300 transition-colors"
            >
              <X className="w-6 h-6" />
            </button>
            <img
              src={previewImage}
              alt="预览"
              className="max-w-full max-h-[85vh] rounded-lg shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        </div>
      )}
    </div>
  )
}
