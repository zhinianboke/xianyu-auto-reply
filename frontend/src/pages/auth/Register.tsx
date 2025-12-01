import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { MessageSquare, User, Lock, Mail, KeyRound, Eye, EyeOff } from 'lucide-react'
import { register, getRegistrationStatus, generateCaptcha, verifyCaptcha, sendVerificationCode } from '@/api/auth'
import { useUIStore } from '@/store/uiStore'
import { cn } from '@/utils/cn'
import { ButtonLoading } from '@/components/common/Loading'

export function Register() {
  const navigate = useNavigate()
  const { addToast } = useUIStore()

  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [registrationEnabled, setRegistrationEnabled] = useState(true)

  // Form states
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [captchaCode, setCaptchaCode] = useState('')
  const [verificationCode, setVerificationCode] = useState('')

  // Captcha states
  const [captchaImage, setCaptchaImage] = useState('')
  const [sessionId] = useState(() => `session_${Math.random().toString(36).substr(2, 9)}_${Date.now()}`)
  const [captchaVerified, setCaptchaVerified] = useState(false)
  const [countdown, setCountdown] = useState(0)

  useEffect(() => {
    getRegistrationStatus()
      .then((result) => {
        setRegistrationEnabled(result.enabled)
        if (!result.enabled) {
          addToast({ type: 'warning', message: '注册功能已关闭' })
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadCaptcha()
  }, [])

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
    if (!captchaVerified || !email || countdown > 0) return

    try {
      const result = await sendVerificationCode(email, 'register', sessionId)
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

    if (!username || !email || !password || !confirmPassword || !verificationCode) {
      addToast({ type: 'error', message: '请填写所有必填项' })
      return
    }

    if (password !== confirmPassword) {
      addToast({ type: 'error', message: '两次输入的密码不一致' })
      return
    }

    if (password.length < 6) {
      addToast({ type: 'error', message: '密码长度至少6位' })
      return
    }

    setLoading(true)

    try {
      const result = await register({
        username,
        email,
        password,
        verification_code: verificationCode,
        session_id: sessionId,
      })

      if (result.success) {
        addToast({ type: 'success', message: '注册成功，请登录' })
        navigate('/login')
      } else {
        addToast({ type: 'error', message: result.message || '注册失败' })
      }
    } catch {
      addToast({ type: 'error', message: '注册失败，请检查网络连接' })
    } finally {
      setLoading(false)
    }
  }

  if (!registrationEnabled) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center p-4">
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-8 text-center max-w-sm">
          <div className="w-14 h-14 rounded-full bg-amber-100 dark:bg-amber-900/30 mx-auto mb-4 flex items-center justify-center">
            <span className="text-2xl">🚫</span>
          </div>
          <h1 className="text-lg vben-card-title text-slate-900 dark:text-slate-100 mb-2">注册功能已关闭</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-6">管理员已关闭注册功能，如需账号请联系管理员</p>
          <Link to="/login" className="btn-ios-primary">
            返回登录
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center p-6 transition-colors">
      <div className="w-full max-w-md">
        {/* Mobile header */}
        <div className="text-center mb-6">
          <div className="w-12 h-12 rounded-xl bg-blue-600 text-white mx-auto mb-4 flex items-center justify-center">
            <MessageSquare className="w-6 h-6" />
          </div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">用户注册</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">创建您的账号以开始使用</p>
        </div>

        {/* Register Card */}
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Username */}
            <div className="input-group">
              <label className="input-label">用户名</label>
              <div className="relative">
                <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="请输入用户名"
                  className="input-ios pl-9"
                />
              </div>
            </div>

            {/* Email */}
            <div className="input-group">
              <label className="input-label">邮箱地址</label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="name@example.com"
                  className="input-ios pl-9"
                />
              </div>
            </div>

            {/* Password */}
            <div className="input-group">
              <label className="input-label">密码</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="至少6位字符"
                  className="input-ios pl-9 pr-9"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* Confirm Password */}
            <div className="input-group">
              <label className="input-label">确认密码</label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                <input
                  type={showPassword ? 'text' : 'password'}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="请再次输入密码"
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
                  className="h-[38px] rounded border border-slate-300 dark:border-slate-600 cursor-pointer hover:opacity-80 transition-opacity"
                />
              </div>
              <p className={cn(
                'text-xs',
                captchaVerified ? 'text-green-600 dark:text-green-400' : 'text-slate-400'
              )}>
                {captchaVerified ? '✓ 验证成功' : '点击图片更换验证码'}
              </p>
            </div>

            {/* Email code */}
            <div className="input-group">
              <label className="input-label">邮箱验证码</label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <KeyRound className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
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
                  disabled={!captchaVerified || !email || countdown > 0}
                  className="btn-ios-secondary whitespace-nowrap"
                >
                  {countdown > 0 ? `${countdown}s` : '发送'}
                </button>
              </div>
            </div>

            {/* Submit button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full btn-ios-primary"
            >
              {loading ? <ButtonLoading /> : '注 册'}
            </button>
          </form>

          {/* Login link */}
          <p className="text-center mt-6 text-slate-500 dark:text-slate-400 text-sm">
            已有账号？{' '}
            <Link to="/login" className="text-blue-600 dark:text-blue-400 font-medium hover:text-indigo-700">
              立即登录
            </Link>
          </p>
        </div>

        {/* Footer */}
        <p className="text-center mt-6 text-slate-400 text-xs">
          © {new Date().getFullYear()} 划算云服务器 · 
          <a href="https://www.hsykj.com" target="_blank" rel="noopener noreferrer" className="hover:text-blue-600 dark:text-blue-400 ml-1 transition-colors">
            www.hsykj.com
          </a>
        </p>
      </div>
    </div>
  )
}
