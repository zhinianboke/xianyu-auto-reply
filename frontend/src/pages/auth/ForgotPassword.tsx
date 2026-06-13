import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { MessageSquare, Mail, Lock, KeyRound, Eye, EyeOff } from 'lucide-react'
import { AuthNavbar } from '@/components/common/AuthNavbar'
import { SafeHtml } from '@/components/common/SafeHtml'
import { getDefaultAuthFooterAdSettings } from '@/api/settings'
import { sendResetPasswordCode, resetPassword, generateCaptcha, verifyCaptcha, getAuthFooterAdSettings } from '@/api/auth'
import { useUIStore } from '@/store/uiStore'
import { cn } from '@/utils/cn'
import { ButtonLoading } from '@/components/common/Loading'

export function ForgotPassword() {
  const navigate = useNavigate()
  const { addToast } = useUIStore()

  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [authFooterAd, setAuthFooterAd] = useState(() => getDefaultAuthFooterAdSettings())
  const [step, setStep] = useState<'email' | 'code' | 'done'>('email')

  // Form states
  const [email, setEmail] = useState('')
  const [verificationCode, setVerificationCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  // Captcha states
  const [captchaImage, setCaptchaImage] = useState('')
  const [sessionId] = useState(() => `session_${Math.random().toString(36).substr(2, 9)}_${Date.now()}`)
  const [captchaVerified, setCaptchaVerified] = useState(false)
  const [countdown, setCountdown] = useState(0)
  const [verifying, setVerifying] = useState(false)
  const [captchaCode, setCaptchaCode] = useState('')

  useEffect(() => {
    getAuthFooterAdSettings()
      .then((result) => setAuthFooterAd(result))
      .catch(() => {})
    loadCaptcha()
  }, [])

  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [countdown])

  // Auto-verify captcha
  useEffect(() => {
    if (captchaCode.length === 4 && !captchaVerified && !verifying) {
      handleVerifyCaptchaAuto()
    }
  }, [captchaCode])

  const handleVerifyCaptchaAuto = async () => {
    if (captchaCode.length !== 4 || verifying) return
    setVerifying(true)
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
    } finally {
      setVerifying(false)
    }
  }

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

  const handleSendCode = async () => {
    if (!email.trim()) {
      addToast({ type: 'warning', message: '请先输入邮箱地址' })
      return
    }
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(email)) {
      addToast({ type: 'warning', message: '请输入正确的邮箱格式' })
      return
    }
    if (!captchaVerified) {
      addToast({ type: 'warning', message: '请先完成图形验证码验证' })
      return
    }
    if (countdown > 0) return

    try {
      const result = await sendResetPasswordCode(email, sessionId)
      if (result.success) {
        setCountdown(60)
        setStep('code')
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

    if (!verificationCode) {
      addToast({ type: 'error', message: '请输入验证码' })
      return
    }
    if (!newPassword) {
      addToast({ type: 'error', message: '请输入新密码' })
      return
    }
    if (newPassword.length < 6) {
      addToast({ type: 'error', message: '密码长度至少6位' })
      return
    }
    if (newPassword !== confirmPassword) {
      addToast({ type: 'error', message: '两次输入的密码不一致' })
      return
    }

    setLoading(true)

    try {
      const result = await resetPassword({
        email,
        verification_code: verificationCode,
        new_password: newPassword,
      })

      if (result.success) {
        addToast({ type: 'success', message: '密码重置成功，请登录' })
        navigate('/login')
      } else {
        addToast({ type: 'error', message: result.message || '重置失败' })
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string; message?: string } } }
      const errorMsg = err?.response?.data?.detail || err?.response?.data?.message || '重置失败，请检查网络连接'
      addToast({ type: 'error', message: errorMsg })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900 transition-colors">
      <AuthNavbar />
      <div className="pt-20 pb-10 px-4 sm:px-6 flex items-start justify-center min-h-screen">
      <div className="w-full max-w-md">
        {/* Mobile header */}
        <div className="text-center mb-6">
          <div className="w-12 h-12 rounded-xl bg-blue-600 text-white mx-auto mb-4 flex items-center justify-center">
            <MessageSquare className="w-6 h-6" />
          </div>
          <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">忘记密码</h1>
          <p className="text-sm text-slate-500 dark:text-slate-400">
            {step === 'email' && '通过邮箱验证码重置您的密码'}
            {step === 'code' && '请输入验证码和新密码'}
          </p>
        </div>

        {/* Forgot Password Card */}
        <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
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
                  disabled={step === 'code'}
                />
              </div>
            </div>

            {/* Captcha - show in email step */}
            {step === 'email' && (
              <>
                <div className="input-group">
                  <label className="input-label">图形验证码</label>
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={captchaCode}
                      onChange={(e) => setCaptchaCode(e.target.value)}
                      placeholder="输入验证码"
                      maxLength={4}
                      className="input-ios flex-1"
                      disabled={captchaVerified}
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
                    captchaVerified ? 'text-green-600 dark:text-green-400' : verifying ? 'text-blue-500' : 'text-slate-400'
                  )}>
                    {captchaVerified ? '✓ 验证成功' : verifying ? '验证中...' : '点击图片更换验证码'}
                  </p>
                </div>

                <button
                  type="button"
                  onClick={handleSendCode}
                  disabled={!captchaVerified || !email || countdown > 0}
                  className="w-full btn-ios-primary"
                >
                  {countdown > 0 ? `重新发送 (${countdown}s)` : '发送验证码'}
                </button>
              </>
            )}

            {/* Verification code + new password - show in code step */}
            {step === 'code' && (
              <>
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
                      disabled={countdown > 0}
                      className="btn-ios-secondary whitespace-nowrap"
                    >
                      {countdown > 0 ? `${countdown}s` : '重发'}
                    </button>
                  </div>
                </div>

                <div className="input-group">
                  <label className="input-label">新密码</label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
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

                <div className="input-group">
                  <label className="input-label">确认新密码</label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                    <input
                      type={showPassword ? 'text' : 'password'}
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="请再次输入新密码"
                      className="input-ios pl-9"
                    />
                  </div>
                </div>

                {/* Submit button */}
                <button
                  type="submit"
                  disabled={loading}
                  className="w-full btn-ios-primary"
                >
                  {loading ? <ButtonLoading /> : '重置密码'}
                </button>
              </>
            )}
          </form>

          {/* Back to login link */}
          <p className="text-center mt-6 text-slate-500 dark:text-slate-400 text-sm">
            <Link to="/login" className="text-blue-600 dark:text-blue-400 font-medium hover:text-blue-700 dark:hover:text-blue-300">
              返回登录
            </Link>
          </p>
        </div>

        {/* Footer */}
        <SafeHtml
          html={authFooterAd['auth.footer_ad_html']}
          className="mt-6 text-center text-xs text-slate-400 dark:text-slate-500"
        />
      </div>
      </div>
    </div>
  )
}
