import { useState, useEffect } from 'react'
import { MessageSquare, Github, Heart, Code, MessageCircle, Users, UserCheck, Bot, Truck, Bell, BarChart3, X, Globe } from 'lucide-react'

export function About() {
  const [previewImage, setPreviewImage] = useState<string | null>(null)
  const [version, setVersion] = useState('v1.0.4')
  const [totalUsers, setTotalUsers] = useState(0)

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
  }, [])

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      {/* Header */}
      <div className="text-center mb-6">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-blue-500 to-blue-600 
                    mx-auto mb-4 flex items-center justify-center shadow-md"
        >
          <MessageSquare className="w-8 h-8 text-white" />
        </div>
        <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">
          闲鱼自动回复管理系统
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
          智能管理您的闲鱼店铺，提升客服效率
        </p>
        {/* 版本和使用人数 */}
        <div className="flex items-center justify-center gap-3 mt-3">
          <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gradient-to-r from-emerald-500/10 to-teal-500/10 text-emerald-600 dark:from-emerald-500/20 dark:to-teal-500/20 dark:text-emerald-400 border border-emerald-200/50 dark:border-emerald-500/30">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
            <span>{version}</span>
          </div>
          {totalUsers > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-gradient-to-r from-blue-500/10 to-cyan-500/10 text-blue-600 dark:from-blue-500/20 dark:to-cyan-500/20 dark:text-blue-400 border border-blue-200/50 dark:border-blue-500/30">
              <Globe className="w-3.5 h-3.5" />
              <span>{totalUsers.toLocaleString()} 人使用</span>
            </div>
          )}
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
              className="w-[160px] h-[160px] mx-auto overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700 
                         cursor-pointer transition-all duration-200 hover:scale-105 hover:shadow-lg hover:border-green-400"
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
              className="w-[160px] h-[160px] mx-auto overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700
                         cursor-pointer transition-all duration-200 hover:scale-105 hover:shadow-lg hover:border-blue-400"
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
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-100 dark:bg-slate-700 
                       hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
            >
              <Github className="w-4 h-4 text-slate-600 dark:text-slate-300" />
              <span className="text-sm font-medium text-slate-700 dark:text-slate-200">zhinianboke</span>
              <span className="text-xs text-slate-500 dark:text-slate-400">项目作者</span>
            </a>
            <a
              href="https://github.com/legeling"
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-100 dark:bg-slate-700 
                       hover:bg-slate-200 dark:hover:bg-slate-600 transition-colors"
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
              className="flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-900 text-white 
                       hover:bg-gray-800 transition-colors text-sm"
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
    </div>
  )
}
