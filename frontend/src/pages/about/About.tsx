import { useCallback, useEffect, useState } from 'react'
import { ArrowUpCircle, BarChart3, Bell, Bot, CheckCircle, Code, FileText, Github, Globe, Heart, Loader2, MessageCircle, MessageSquare, RefreshCw, Truck, UserCheck, Users, X } from 'lucide-react'

interface UpdateInfo {
  version: string
  date?: string
  changes?: string[]
  download_url?: string
}

// 版本比较函数
function compareVersions(v1: string, v2: string): number {
  const normalize = (v: string) => v.replace(/^v/, '').split('.').map(Number)
  const parts1 = normalize(v1)
  const parts2 = normalize(v2)
  for (let i = 0; i < Math.max(parts1.length, parts2.length); i++) {
    const p1 = parts1[i] || 0
    const p2 = parts2[i] || 0
    if (p1 > p2) return 1
    if (p1 < p2) return -1
  }
  return 0
}

export function About() {
  const [previewImage, setPreviewImage] = useState<string | null>(null)
  const [version, setVersion] = useState('加载中...')
  const [totalUsers, setTotalUsers] = useState(0)

  // 更新检查相关状态
  const [latestVersion, setLatestVersion] = useState<string | null>(null)
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null)
  const [hasUpdate, setHasUpdate] = useState(false)
  const [checkingUpdate, setCheckingUpdate] = useState(false)
  const [showUpdateModal, setShowUpdateModal] = useState(false)
  const [showChangelogModal, setShowChangelogModal] = useState(false)
  const [changelog, setChangelog] = useState<UpdateInfo[]>([])
  const [changelogHtml, setChangelogHtml] = useState<string | null>(null)
  const [loadingChangelog, setLoadingChangelog] = useState(false)

  // 检查更新
  const checkForUpdate = useCallback(async (showToast = false) => {
    setCheckingUpdate(true)
    try {
      const response = await fetch('/api/version/check')
      const result = await response.json()

      if (result.error) {
        if (showToast) {
          console.error('获取版本信息失败:', result.message)
        }
        return
      }

      // 支持 {data: "v1.0.5"} 格式
      const remoteVersion = result.data || result.version || result.latest_version
      if (remoteVersion) {
        setLatestVersion(remoteVersion)
        setUpdateInfo({
          version: remoteVersion,
          date: result.date || result.release_date,
          changes: result.changes || result.changelog || [],
          download_url: result.download_url,
        })

        if (compareVersions(remoteVersion, version) > 0) {
          setHasUpdate(true)
          if (showToast) {
            setShowUpdateModal(true)
          }
        } else if (showToast) {
          // 已是最新版本的提示
          setHasUpdate(false)
        }
      }
    } catch (error) {
      console.error('检查更新失败:', error)
    } finally {
      setCheckingUpdate(false)
    }
  }, [version])

  // 获取更新日志
  const loadChangelog = useCallback(async () => {
    setLoadingChangelog(true)
    setChangelogHtml(null)
    setChangelog([])
    try {
      const response = await fetch('/api/version/changelog')
      const result = await response.json()

      if (result.error) {
        console.error('获取更新日志失败:', result.message)
        return
      }

      // 支持 {data: {updates: [...]}} 格式
      if (result.data && result.data.updates && Array.isArray(result.data.updates)) {
        // 将 updates 数组合并成 HTML 字符串
        const htmlContent = result.data.updates.join('<br/>')
        setChangelogHtml(htmlContent)
      } else if (result.html) {
        setChangelogHtml(result.html)
      } else if (result.changelog) {
        setChangelog(result.changelog)
      } else if (Array.isArray(result)) {
        setChangelog(result)
      }
    } catch (error) {
      console.error('获取更新日志失败:', error)
    } finally {
      setLoadingChangelog(false)
    }
  }, [])

  useEffect(() => {
    // 获取版本信息
    fetch('/static/version.txt')
      .then(res => res.ok ? res.text() : null)
      .then(text => {
        if (text && text.trim().startsWith('v')) {
          setVersion(text.trim())
        }
      })
      .catch(() => {})

    // 获取使用人数
    fetch('/project-stats')
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data?.total_users) {
          setTotalUsers(data.total_users)
        }
      })
      .catch(() => {})

    // 自动检查更新
    checkForUpdate(false)
  }, [checkForUpdate])

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
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gradient-to-r from-emerald-500/10 to-teal-500/10 text-emerald-600 dark:from-emerald-500/20 dark:to-teal-500/20 dark:text-emerald-400 border border-emerald-200/50 dark:border-emerald-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span>{version}</span>
          </div>
          {hasUpdate && latestVersion && (
            <button
              onClick={() => setShowUpdateModal(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gradient-to-r from-amber-500/10 to-orange-500/10 text-amber-600 dark:from-amber-500/20 dark:to-orange-500/20 dark:text-amber-400 border border-amber-200/50 dark:border-amber-500/30 hover:from-amber-500/20 hover:to-orange-500/20 transition-all cursor-pointer"
            >
              <ArrowUpCircle className="w-3.5 h-3.5" />
              <span>有更新 {latestVersion}</span>
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
            onClick={() => checkForUpdate(true)}
            disabled={checkingUpdate}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors disabled:opacity-50"
          >
            {checkingUpdate ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <RefreshCw className="w-3.5 h-3.5" />
            )}
            <span>{checkingUpdate ? '检查中...' : '检查更新'}</span>
          </button>
          <button
            onClick={() => {
              setShowChangelogModal(true)
              loadChangelog()
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
          >
            <FileText className="w-3.5 h-3.5" />
            <span>更新日志</span>
          </button>
        </div>
      </div>

      {/* Contact Groups */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="vben-card">
          <div className="vben-card-header">
            <h2 className="vben-card-title">
              <MessageCircle className="w-4 h-4 text-green-500" />
              微信群
            </h2>
          </div>
          <div className="vben-card-body text-center">
            <div
              className="w-[160px] h-[160px] mx-auto overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700 cursor-pointer transition-all duration-200 hover:scale-105 hover:shadow-lg hover:border-green-400"
              onClick={() => setPreviewImage('/static/wechat-group.png')}
            >
              <img
                src="/static/wechat-group.png"
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
            </div>
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">扫码加入微信技术交流群</p>
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
              className="w-[160px] h-[160px] mx-auto overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700 cursor-pointer transition-all duration-200 hover:scale-105 hover:shadow-lg hover:border-blue-400"
              onClick={() => setPreviewImage('/static/qq-group.png')}
            >
              <img
                src="/static/qq-group.png"
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
            </div>
            <p className="mt-3 text-sm text-slate-500 dark:text-slate-400">扫码加入QQ技术交流群</p>
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
              href="https://github.com/arkleselect"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-100 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
            >
              <Github className="w-4 h-4 text-slate-600 dark:text-slate-300" />
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">arkleselect</span>
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
        <p className="flex items-center justify-center gap-1">
          Made with <Heart className="w-3.5 h-3.5 text-red-500" /> by Open Source Community
        </p>
        <p className="mt-1 text-xs">
          赞助商：
          <a
            href="https://www.hsykj.com"
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-500 dark:text-blue-400 hover:underline ml-1"
          >
            划算云服务器
          </a>
        </p>
      </div>

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

      {/* 更新详情弹窗 */}
      {showUpdateModal && updateInfo && (
        <div className="modal-overlay" onClick={() => setShowUpdateModal(false)}>
          <div className="modal-content max-w-lg" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title flex items-center gap-2">
                <ArrowUpCircle className="w-5 h-5 text-amber-500" />
                发现新版本
              </h2>
              <button onClick={() => setShowUpdateModal(false)} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              <div className="flex items-center justify-between p-4 bg-gradient-to-r from-amber-50 to-orange-50 dark:from-amber-900/20 dark:to-orange-900/20 rounded-lg">
                <div>
                  <p className="text-sm text-slate-500 dark:text-slate-400">当前版本</p>
                  <p className="text-lg font-bold text-slate-700 dark:text-slate-200">{version}</p>
                </div>
                <div className="text-2xl text-slate-400">→</div>
                <div>
                  <p className="text-sm text-slate-500 dark:text-slate-400">最新版本</p>
                  <p className="text-lg font-bold text-emerald-600 dark:text-emerald-400">{updateInfo.version}</p>
                </div>
              </div>

              {updateInfo.date && (
                <p className="text-sm text-slate-500 dark:text-slate-400">
                  发布日期：{updateInfo.date}
                </p>
              )}

              {updateInfo.changes && updateInfo.changes.length > 0 && (
                <div>
                  <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2">更新内容：</h3>
                  <ul className="space-y-1.5">
                    {updateInfo.changes.map((change, index) => (
                      <li key={index} className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400">
                        <CheckCircle className="w-4 h-4 text-emerald-500 mt-0.5 flex-shrink-0" />
                        <span>{change}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                <p className="text-xs text-blue-600 dark:text-blue-400">
                  <strong>提示：</strong>请前往 GitHub 下载最新版本，或使用 git pull 更新代码。
                </p>
              </div>
            </div>
            <div className="modal-footer">
              <button onClick={() => setShowUpdateModal(false)} className="btn-ios-secondary">
                稍后再说
              </button>
              <a
                href={updateInfo.download_url || 'https://github.com/zhinianboke/xianyu-auto-reply/releases'}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-ios-primary"
              >
                <Github className="w-4 h-4" />
                前往下载
              </a>
            </div>
          </div>
        </div>
      )}

      {/* 更新日志弹窗 */}
      {showChangelogModal && (
        <div className="modal-overlay" onClick={() => setShowChangelogModal(false)}>
          <div className="modal-content max-w-2xl max-h-[80vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2 className="modal-title flex items-center gap-2">
                <FileText className="w-5 h-5 text-blue-500" />
                更新日志
              </h2>
              <button onClick={() => setShowChangelogModal(false)} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body flex-1 overflow-y-auto">
              {loadingChangelog ? (
                <div className="flex items-center justify-center py-12">
                  <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
                </div>
              ) : changelogHtml ? (
                <div 
                  className="changelog-html prose prose-sm dark:prose-invert max-w-none"
                  dangerouslySetInnerHTML={{ __html: changelogHtml }}
                />
              ) : changelog.length === 0 ? (
                <div className="text-center py-12 text-slate-500 dark:text-slate-400">
                  <FileText className="w-12 h-12 mx-auto mb-3 text-slate-300 dark:text-slate-600" />
                  <p>暂无更新日志</p>
                </div>
              ) : (
                <div className="space-y-4">
                  {changelog.map((item, index) => (
                    <div
                      key={index}
                      className="p-4 rounded-lg bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700"
                    >
                      <div className="flex items-center justify-between mb-2">
                        <span className="font-medium text-slate-900 dark:text-slate-100">
                          {item.version}
                        </span>
                        {item.date && (
                          <span className="text-xs text-slate-500 dark:text-slate-400">
                            {item.date}
                          </span>
                        )}
                      </div>
                      {item.changes && item.changes.length > 0 && (
                        <ul className="space-y-1">
                          {item.changes.map((change, changeIndex) => (
                            <li
                              key={changeIndex}
                              className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400"
                            >
                              <span className="text-emerald-500 mt-1">•</span>
                              <span>{change}</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button onClick={() => setShowChangelogModal(false)} className="btn-ios-secondary">
                关闭
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
