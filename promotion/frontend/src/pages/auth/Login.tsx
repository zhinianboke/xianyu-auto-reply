/**
 * 推广返佣系统 - 登录页面
 *
 * 功能：
 * 1. 左侧品牌展示 + 右侧登录表单（参照现有项目风格）
 * 2. 用户名+密码登录（使用现有系统xy_users表）
 * 3. 极验滑动验证码（复用现有系统的验证码逻辑）
 * 4. 已登录自动跳转
 * 5. 暗黑模式切换
 * 6. 加载遮罩
 * 7. 响应式适配手机端
 */
import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { User, Lock, Eye, EyeOff, Layers, Sun, Moon } from 'lucide-react'
import { login, verifyToken } from '@/api/auth'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/request'
import request from '@/utils/request'
import { GeetestCaptcha, type GeetestResult } from '@/components/common/GeetestCaptcha'

export function Login() {
  const navigate = useNavigate()
  const { setAuth, isAuthenticated } = useAuthStore()
  const { addToast } = useUIStore()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [loading, setLoading] = useState(false)
  const [isDark, setIsDark] = useState(false)

  // 极验滑动验证码状态
  const [loginCaptchaEnabled, setLoginCaptchaEnabled] = useState<boolean | null>(null)
  const [geetestResult, setGeetestResult] = useState<GeetestResult | null>(null)
  const [geetestKey, setGeetestKey] = useState(0)

  /** 重置滑动验证码（登录失败时使用） */
  const resetGeetest = () => {
    setGeetestResult(null)
    setGeetestKey((k: number) => k + 1)
  }

  /** 检查是否已登录，已登录则跳转仪表盘 */
  useEffect(() => {
    setIsDark(document.documentElement.classList.contains('dark'))

    if (isAuthenticated) {
      navigate('/dashboard')
      return
    }
    const token = localStorage.getItem('auth_token')
    if (token) {
      verifyToken()
        .then((result) => {
          if (result.authenticated) {
            navigate('/dashboard')
          }
        })
        .catch(() => {
          localStorage.removeItem('auth_token')
        })
    }
  }, [isAuthenticated, navigate])

  /** 加载验证码开关状态 */
  useEffect(() => {
    request.get('/api/v1/settings/public')
      .then((res) => {
        if (res.data?.success && res.data?.data) {
          const val = res.data.data.login_captcha_enabled
          // 未配置或true/1时默认开启
          setLoginCaptchaEnabled(val === undefined || val === null || val === 'true' || val === '1' || val === true)
        }
      })
      .catch(() => {
        // 获取失败默认开启
      })
  }, [])

  /** 切换暗黑模式 */
  const toggleDarkMode = () => {
    const newDark = !isDark
    setIsDark(newDark)
    if (newDark) {
      document.documentElement.classList.add('dark')
      localStorage.setItem('theme', 'dark')
    } else {
      document.documentElement.classList.remove('dark')
      localStorage.setItem('theme', 'light')
    }
  }

  /** 极验验证成功回调 */
  const handleGeetestSuccess = (result: GeetestResult) => {
    setGeetestResult(result)
  }

  /** 提交登录 */
  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!username.trim()) {
      addToast({ message: '请输入用户名', type: 'warning' })
      return
    }
    if (!password.trim()) {
      addToast({ message: '请输入密码', type: 'warning' })
      return
    }

    // 检查滑动验证码（仅确认开启时前端校验）
    if (loginCaptchaEnabled === true && !geetestResult) {
      addToast({ message: '请完成滑动验证', type: 'warning' })
      return
    }

    setLoading(true)
    try {
      const res = await login({
        username: username.trim(),
        password,
        geetest_challenge: geetestResult?.challenge,
        geetest_validate: geetestResult?.validate,
        geetest_seccode: geetestResult?.seccode,
      })
      if (res.success && res.token && res.refresh_token) {
        setAuth(res.token, res.refresh_token, {
          user_id: res.user_id!,
          username: res.username!,
          is_admin: res.is_admin ?? false,
          account_limit: res.account_limit,
        })
        addToast({ message: res.message ?? '登录成功', type: 'success' })
        navigate('/dashboard')
      } else {
        addToast({ message: res.message || '登录失败', type: 'error' })
        // 登录失败，重置滑动验证
        resetGeetest()
      }
    } catch (err) {
      addToast({ message: getApiErrorMessage(err), type: 'error' })
      // 登录失败，重置滑动验证
      resetGeetest()
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-900 transition-colors duration-200">
      {/* 顶部导航栏 */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-white/95 dark:bg-slate-900/95 backdrop-blur-sm border-b border-slate-200 dark:border-slate-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6">
          <div className="flex items-center justify-between h-14">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-lg bg-blue-500 flex items-center justify-center">
                <Layers className="w-4 h-4 text-white" />
              </div>
              <span className="text-sm font-bold text-slate-900 dark:text-white">推广返佣系统</span>
            </div>
            <button
              onClick={toggleDarkMode}
              className="p-2 rounded-md text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              title={isDark ? '切换到亮色模式' : '切换到暗色模式'}
            >
              {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
            </button>
          </div>
        </div>
      </nav>

      {/* 主体内容：左右分栏 */}
      <div className="flex-1 flex pt-14">
        {/* 左侧 - 品牌展示（仅桌面端） */}
        <div className="hidden lg:flex lg:w-1/2 bg-slate-900 dark:bg-slate-950 relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-blue-600/20 to-transparent" />
          <div className="relative z-10 flex flex-col justify-center px-16">
            <div className="flex items-center gap-3 mb-8">
              <div className="w-12 h-12 rounded-xl bg-blue-500 flex items-center justify-center">
                <Layers className="w-6 h-6 text-white" />
              </div>
              <span className="text-2xl font-bold text-white">推广返佣系统</span>
            </div>
            <h1 className="text-4xl font-bold text-white mb-4 leading-tight">
              高效管理<br />推广与返佣
            </h1>
            <p className="text-slate-400 text-lg max-w-md">
              一站式推广返佣管理平台，轻松管理您的推广账号和返佣数据。
            </p>
          </div>
          {/* 装饰圆 */}
          <div className="absolute -bottom-32 -left-32 w-96 h-96 rounded-full bg-blue-600/10" />
          <div className="absolute -top-32 -right-32 w-96 h-96 rounded-full bg-blue-600/5" />
        </div>

        {/* 右侧 - 登录表单 */}
        <div className="flex-1 flex items-center justify-center p-4 sm:p-6">
          <div className="w-full max-w-md">
            {/* 移动端Logo */}
            <div className="lg:hidden text-center mb-8">
              <div className="w-12 h-12 rounded-xl bg-blue-500 text-white mx-auto mb-4 flex items-center justify-center">
                <Layers className="w-6 h-6" />
              </div>
              <h1 className="text-xl font-bold text-slate-900 dark:text-white">推广返佣系统</h1>
            </div>

            {/* 登录卡片 */}
            <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-5 sm:p-8">
              <div className="mb-6">
                <h2 className="text-xl font-semibold text-slate-900 dark:text-white">登录</h2>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">欢迎回来，请登录您的账号</p>
              </div>

              <form onSubmit={handleLogin} className="space-y-4">
                {/* 用户名 */}
                <div className="input-group">
                  <label className="input-label">用户名</label>
                  <div className="relative">
                    <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                      type="text"
                      className="input-ios pl-9"
                      placeholder="请输入用户名"
                      value={username}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setUsername(e.target.value)}
                      autoComplete="username"
                      autoFocus
                      disabled={loading}
                    />
                  </div>
                </div>

                {/* 密码 */}
                <div className="input-group">
                  <label className="input-label">密码</label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      className="input-ios pl-9 pr-9"
                      placeholder="请输入密码"
                      value={password}
                      onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
                      autoComplete="current-password"
                      disabled={loading}
                    />
                    <button
                      type="button"
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                      onClick={() => setShowPassword(!showPassword)}
                      tabIndex={-1}
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* 滑动验证码 */}
                {loginCaptchaEnabled === true && (
                  <div className="input-group">
                    <label className="input-label">滑动验证</label>
                    <GeetestCaptcha
                      key={geetestKey}
                      onSuccess={handleGeetestSuccess}
                      onError={(err) => addToast({ type: 'error', message: err })}
                      disabled={loading}
                    />
                  </div>
                )}

                {/* 登录按钮 */}
                <button
                  type="submit"
                  className="w-full btn-ios-primary"
                  disabled={loading}
                >
                  {loading ? (
                    <div className="flex items-center justify-center gap-2">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white" />
                      <span>登录中...</span>
                    </div>
                  ) : (
                    '登 录'
                  )}
                </button>
              </form>
            </div>

            {/* 底部信息 */}
            <p className="text-center text-xs text-slate-400 dark:text-slate-500 mt-6">
              &copy; {new Date().getFullYear()} 推广返佣系统
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
