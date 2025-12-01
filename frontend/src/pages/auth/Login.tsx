import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { MessageSquare, User, Lock, Mail, KeyRound, Eye, EyeOff, Sun, Moon } from 'lucide-react'
import { login, verifyToken, getRegistrationStatus, getLoginInfoStatus, generateCaptcha, verifyCaptcha, sendVerificationCode } from '@/api/auth'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { cn } from '@/utils/cn'
import { ButtonLoading } from '@/components/common/Loading'

type LoginType = 'username' | 'email-password' | 'email-code'

export function Login() {
  const navigate = useNavigate()
  const { setAuth, isAuthenticated } = useAuthStore()
  const { addToast } = useUIStore()

  const [loginType, setLoginType] = useState<LoginType>('username')
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [registrationEnabled, setRegistrationEnabled] = useState(true)
  const [showDefaultLogin, setShowDefaultLogin] = useState(true)
  const [isDark, setIsDark] = useState(false)

  // Form states
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [emailPassword, setEmailPassword] = useState('')
  const [emailForCode, setEmailForCode] = useState('')
  const [captchaCode, setCaptchaCode] = useState('')
  const [verificationCode, setVerificationCode] = useState('')

  // Captcha states
  const [captchaImage, setCaptchaImage] = useState('')
  const [sessionId] = useState(() => `session_${Math.random().toString(36).substr(2, 9)}_${Date.now()}`)
  const [captchaVerified, setCaptchaVerified] = useState(false)
  const [countdown, setCountdown] = useState(0)

  // 初始化主题
  useEffect(() => {
    const savedTheme = localStorage.getItem('theme')
    // 默认使用白天模式
    const shouldBeDark = savedTheme === 'dark'
    setIsDark(shouldBeDark)
    document.documentElement.classList.toggle('dark', shouldBeDark)
  }, [])

  const toggleTheme = () => {
    const newIsDark = !isDark
    setIsDark(newIsDark)
    document.documentElement.classList.toggle('dark', newIsDark)
    localStorage.setItem('theme', newIsDark ? 'dark' : 'light')
  }

  // Check if already logged in
  useEffect(() => {
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

  // Load initial states
  useEffect(() => {
    getRegistrationStatus()
      .then((result) => setRegistrationEnabled(result.enabled))
      .catch(() => {})

    getLoginInfoStatus()
      .then((result) => setShowDefaultLogin(result.enabled))
      .catch(() => {})
  }, [])

  // Load captcha when switching to email-code
  useEffect(() => {
    if (loginType === 'email-code') {
      loadCaptcha()
    }
  }, [loginType])

  // Countdown timer
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [countdown])

  const loadCaptcha = async () => {
    try {
      const result = await generateCaptcha(sessionId)
      if (result.success && result.captcha_image) {
        setCaptchaImage(result.captcha_image)
        setCaptchaVerified(false)
        setCaptchaCode('')
      }
    } catch {
      addToast({ type: 'error', message: '加载验证码失败' })
    }
  }

  const handleVerifyCaptcha = async () => {
    if (captchaCode.length !== 4) return

    try {
      const result = await verifyCaptcha(sessionId, captchaCode)
      if (result.success) {
        setCaptchaVerified(true)
        addToast({ type: 'success', message: '验证码验证成功' })
      } else {
        setCaptchaVerified(false)
        loadCaptcha()
        addToast({ type: 'error', message: '验证码错误' })
      }
    } catch {
      addToast({ type: 'error', message: '验证失败' })
    }
  }

  const handleSendCode = async () => {
    if (!captchaVerified || !emailForCode || countdown > 0) return

    try {
      const result = await sendVerificationCode(emailForCode, 'login', sessionId)
      if (result.success) {
        setCountdown(60)
        addToast({ type: 'success', message: '验证码已发送' })
      } else {
        addToast({ type: 'error', message: result.message || '发送失败' })
      }
    } catch {
      addToast({ type: 'error', message: '发送验证码失败' })
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLoading(true)

    try {
      let loginData = {}

      if (loginType === 'username') {
        if (!username || !password) {
          addToast({ type: 'error', message: '请输入用户名和密码' })
          return
        }
        loginData = { username, password }
      } else if (loginType === 'email-password') {
        if (!email || !emailPassword) {
          addToast({ type: 'error', message: '请输入邮箱和密码' })
          return
        }
        loginData = { email, password: emailPassword }
      } else {
        if (!emailForCode || !verificationCode) {
          addToast({ type: 'error', message: '请输入邮箱和验证码' })
          return
        }
        loginData = { email: emailForCode, verification_code: verificationCode }
      }

      const result = await login(loginData)

      if (result.success && result.token) {
        setAuth(result.token, {
          user_id: result.user_id!,
          username: result.username!,
          is_admin: result.is_admin!,
        })
        addToast({ type: 'success', message: '登录成功' })
        navigate('/dashboard')
      } else {
        addToast({ type: 'error', message: result.message || '登录失败' })
      }
    } catch {
      addToast({ type: 'error', message: '登录失败，请检查网络连接' })
    } finally {
      setLoading(false)
    }
  }

  const fillDefaultCredentials = () => {
    setLoginType('username')
    setUsername('admin')
    setPassword('admin123')
  }

  return (
    <div className="min-h-screen flex bg-slate-50 dark:bg-slate-900 transition-colors duration-200">
      {/* 右上角主题切换 */}
      <button
        onClick={toggleTheme}
        className="fixed top-4 right-4 z-50 p-2.5 rounded-lg
                   bg-white dark:bg-slate-800 shadow-sm border border-slate-200 dark:border-slate-700
                   text-slate-600 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white
                   transition-colors duration-150"
        title={isDark ? '切换到亮色模式' : '切换到暗色模式'}
      >
        {isDark ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
      </button>

      {/* Left side - Branding */}
      <motion.div 
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.5 }}
        className="hidden lg:flex lg:w-1/2 bg-slate-900 dark:bg-slate-950 relative overflow-hidden"
      >
        <div className="absolute inset-0 bg-gradient-to-br from-blue-600/20 to-transparent" />
        <div className="relative z-10 flex flex-col justify-center px-16">
          <motion.div 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2, duration: 0.5 }}
            className="flex items-center gap-3 mb-8"
          >
            <div className="w-12 h-12 rounded-xl bg-blue-500 flex items-center justify-center">
              <MessageSquare className="w-6 h-6 text-white" />
            </div>
            <span className="text-2xl font-bold text-white">闲鱼管理系统</span>
          </motion.div>
          <motion.h1 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3, duration: 0.5 }}
            className="text-4xl font-bold text-white mb-4 leading-tight"
          >
            高效专业的<br />闲鱼自动化管理平台
          </motion.h1>
          <motion.p 
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4, duration: 0.5 }}
            className="text-slate-400 text-lg max-w-md"
          >
            自动回复、智能客服、订单管理、数据分析，一站式解决闲鱼运营难题
          </motion.p>
        </div>
        {/* Decorative circles */}
        <div className="absolute -bottom-32 -left-32 w-96 h-96 rounded-full bg-blue-600/10" />
        <div className="absolute -top-32 -right-32 w-96 h-96 rounded-full bg-blue-600/5" />
      </motion.div>

      {/* Right side - Login form */}
      <div className="flex-1 flex items-center justify-center p-4 sm:p-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="w-full max-w-md"
        >
          {/* Mobile header */}
          <motion.div 
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1, duration: 0.4 }}
            className="lg:hidden text-center mb-8"
          >
            <div className="w-12 h-12 rounded-xl bg-blue-500 text-white mx-auto mb-4 flex items-center justify-center">
              <MessageSquare className="w-6 h-6" />
            </div>
            <h1 className="text-xl font-bold text-slate-900 dark:text-white">闲鱼管理系统</h1>
          </motion.div>

          {/* Login Card */}
          <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-5 sm:p-8">
            <div className="mb-6">
              <h2 className="text-xl vben-card-title text-slate-900 dark:text-white">登录</h2>
              <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">欢迎回来，请登录您的账号</p>
            </div>

            {/* Login type tabs */}
            <div className="flex border-b border-slate-200 dark:border-slate-700 mb-4 sm:mb-6 overflow-x-auto scrollbar-hide">
              {[
                { type: 'username' as const, label: '账号登录' },
                { type: 'email-password' as const, label: '邮箱密码' },
                { type: 'email-code' as const, label: '验证码' },
              ].map((tab) => (
                <button
                  key={tab.type}
                  onClick={() => setLoginType(tab.type)}
                  className={cn(
                    'px-3 sm:px-4 py-2 sm:py-2.5 text-xs sm:text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap flex-shrink-0',
                    loginType === tab.type
                      ? 'text-blue-600 dark:text-blue-400 border-blue-600 dark:border-blue-400'
                      : 'text-slate-500 dark:text-slate-400 border-transparent hover:text-slate-700 dark:hover:text-slate-300'
                  )}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <form onSubmit={handleSubmit} className="space-y-3 sm:space-y-4">
              {/* Username login */}
              {loginType === 'username' && (
                <>
                  <div className="input-group">
                    <label className="input-label">用户名</label>
                    <div className="relative">
                      <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <input
                        type="text"
                        value={username}
                        onChange={(e) => setUsername(e.target.value)}
                        placeholder="请输入用户名"
                        className="input-ios pl-9"
                      />
                    </div>
                  </div>
                  <div className="input-group">
                    <label className="input-label">密码</label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <input
                        type={showPassword ? 'text' : 'password'}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="请输入密码"
                        className="input-ios pl-9 pr-9"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                      >
                        {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                </>
              )}

              {/* Email password login */}
              {loginType === 'email-password' && (
                <>
                  <div className="input-group">
                    <label className="input-label">邮箱地址</label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="name@example.com"
                        className="input-ios pl-9"
                      />
                    </div>
                  </div>
                  <div className="input-group">
                    <label className="input-label">密码</label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <input
                        type={showPassword ? 'text' : 'password'}
                        value={emailPassword}
                        onChange={(e) => setEmailPassword(e.target.value)}
                        placeholder="请输入密码"
                        className="input-ios pl-9 pr-9"
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
                      >
                        {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                </>
              )}

              {/* Email code login */}
              {loginType === 'email-code' && (
                <>
                  <div className="input-group">
                    <label className="input-label">邮箱地址</label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <input
                        type="email"
                        value={emailForCode}
                        onChange={(e) => setEmailForCode(e.target.value)}
                        placeholder="name@example.com"
                        className="input-ios pl-9"
                      />
                    </div>
                  </div>

                  {/* Captcha */}
                  <div className="input-group">
                    <label className="input-label">图形验证码</label>
                    <div className="flex gap-2">
                      <input
                        type="text"
                        value={captchaCode}
                        onChange={(e) => {
                          setCaptchaCode(e.target.value)
                          if (e.target.value.length === 4) {
                            setTimeout(handleVerifyCaptcha, 100)
                          }
                        }}
                        placeholder="输入验证码"
                        maxLength={4}
                        className="input-ios flex-1"
                      />
                      <img
                        src={captchaImage}
                        alt="验证码"
                        onClick={loadCaptcha}
                        className="h-[38px] rounded border border-gray-300 cursor-pointer hover:opacity-80 transition-opacity"
                      />
                    </div>
                    <p className={cn(
                      'text-xs',
                      captchaVerified ? 'text-green-600' : 'text-gray-400'
                    )}>
                      {captchaVerified ? '✓ 验证成功' : '点击图片更换验证码'}
                    </p>
                  </div>

                  {/* Email code */}
                  <div className="input-group">
                    <label className="input-label">邮箱验证码</label>
                    <div className="flex gap-2">
                      <div className="relative flex-1">
                        <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                        <input
                          type="text"
                          value={verificationCode}
                          onChange={(e) => setVerificationCode(e.target.value)}
                          placeholder="6位数字验证码"
                          maxLength={6}
                          className="input-ios pl-9"
                        />
                      </div>
                      <button
                        type="button"
                        onClick={handleSendCode}
                        disabled={!captchaVerified || !emailForCode || countdown > 0}
                        className="btn-ios-secondary whitespace-nowrap"
                      >
                        {countdown > 0 ? `${countdown}s` : '发送'}
                      </button>
                    </div>
                  </div>
                </>
              )}

              {/* Submit button */}
              <button
                type="submit"
                disabled={loading}
                className="w-full btn-ios-primary"
              >
                {loading ? <ButtonLoading /> : '登 录'}
              </button>
            </form>

            {/* Register link */}
            {registrationEnabled && (
              <p className="text-center mt-6 text-slate-500 dark:text-slate-400 text-sm">
                还没有账号？{' '}
                <Link to="/register" className="text-blue-600 dark:text-blue-400 font-medium hover:text-blue-700 dark:hover:text-blue-300">
                  立即注册
                </Link>
              </p>
            )}

            {/* Default credentials */}
            {showDefaultLogin && (
              <div className="mt-6 pt-6 border-t border-slate-100 dark:border-slate-700">
                <button
                  type="button"
                  onClick={fillDefaultCredentials}
                  className="w-full flex items-center justify-between p-3 rounded-md 
                             bg-slate-50 dark:bg-slate-700/50 hover:bg-slate-100 dark:hover:bg-slate-700 
                             transition-colors text-sm"
                >
                  <div className="text-left">
                    <p className="text-slate-500 dark:text-slate-400">演示账号</p>
                    <p className="text-slate-900 dark:text-white font-medium">admin / admin123</p>
                  </div>
                  <span className="text-blue-600 dark:text-blue-400">一键填充 →</span>
                </button>
              </div>
            )}
          </div>

          {/* Footer */}
          <p className="text-center mt-6 text-slate-400 dark:text-slate-500 text-xs">
            © {new Date().getFullYear()} 划算云服务器 · 
            <a href="https://www.hsykj.com" target="_blank" rel="noopener noreferrer" className="hover:text-blue-600 dark:hover:text-blue-400 ml-1 transition-colors">
              www.hsykj.com
            </a>
          </p>
        </motion.div>
      </div>
    </div>
  )
}
