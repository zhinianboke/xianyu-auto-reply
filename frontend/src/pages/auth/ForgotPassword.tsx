import { useState, useEffect } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { MessageSquare, Mail, KeyRound, Lock, Eye, EyeOff, ArrowLeft } from 'lucide-react'
import { AuthNavbar } from '@/components/common/AuthNavbar'
import { SafeHtml } from '@/components/common/SafeHtml'
import { getDefaultAuthFooterAdSettings, getDefaultLoginBrandingSettings } from '@/api/settings'
import { sendResetPasswordCode, resetPassword, getLoginBrandingSettings, getAuthFooterAdSettings } from '@/api/auth'
import { useUIStore } from '@/store/uiStore'
import { ButtonLoading } from '@/components/common/Loading'

export function ForgotPassword() {
  const navigate = useNavigate()
  const { addToast } = useUIStore()

  const [step, setStep] = useState<1 | 2>(1)
  const [loading, setLoading] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [loginBranding, setLoginBranding] = useState(() => getDefaultLoginBrandingSettings())
  const [authFooterAd, setAuthFooterAd] = useState(() => getDefaultAuthFooterAdSettings())

  // Form states
  const [email, setEmail] = useState('')
  const [verificationCode, setVerificationCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  // Countdown
  const [countdown, setCountdown] = useState(0)

  // Load branding settings
  useEffect(() => {
    getLoginBrandingSettings()
      .then((result) => setLoginBranding(result))
      .catch(() => {})
    getAuthFooterAdSettings()
      .then((result) => setAuthFooterAd(result))
      .catch(() => {})
  }, [])

  // Countdown timer
  useEffect(() => {
    if (countdown > 0) {
      const timer = setTimeout(() => setCountdown(countdown - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [countdown])

  const handleSendCode = async () => {
    if (!email || countdown > 0) return

    setLoading(true)
    try {
      const result = await sendResetPasswordCode(email)
      if (result.success) {
        setCountdown(60)
        addToast({ type: 'success', message: '验证码已发送到您的邮箱' })
        setStep(2)
      } else {
        addToast({ type: 'error', message: result.message || '发送失败' })
      }
    } catch {
      addToast({ type: 'error', message: '发送验证码失败，请检查网络连接' })
    } finally {
      setLoading(false)
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
      addToast({ type: 'error', message: '密码长度不能少于6位' })
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
    } catch {
      addToast({ type: 'error', message: '密码重置失败，请检查网络连接' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col bg-slate-50 dark:bg-slate-900 transition-colors duration-200">
      <AuthNavbar systemName={loginBranding['login.system_name']} />

      <div className="flex-1 flex pt-14">
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
              <span className="text-2xl font-bold text-white">{loginBranding['login.system_name']}</span>
            </motion.div>
            <motion.h1
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.5 }}
              className="text-4xl font-bold text-white mb-4 leading-tight whitespace-pre-line"
            >
              {loginBranding['login.system_title']}
            </motion.h1>
            <motion.p
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4, duration: 0.5 }}
              className="text-slate-400 text-lg max-w-md"
            >
              {loginBranding['login.system_description']}
            </motion.p>
          </div>
          {/* Decorative circles */}
          <div className="absolute -bottom-32 -left-32 w-96 h-96 rounded-full bg-blue-600/10" />
          <div className="absolute -top-32 -right-32 w-96 h-96 rounded-full bg-blue-600/5" />
        </motion.div>

        {/* Right side - Form */}
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
              <h1 className="text-xl font-bold text-slate-900 dark:text-white">{loginBranding['login.system_name']}</h1>
            </motion.div>

            {/* Card */}
            <div className="bg-white dark:bg-slate-800 rounded-lg shadow-sm border border-slate-200 dark:border-slate-700 p-5 sm:p-8">
              <div className="mb-6">
                <h2 className="text-xl vben-card-title text-slate-900 dark:text-white">忘记密码</h2>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                  {step === 1 ? '输入您的邮箱地址，我们将发送验证码' : '输入验证码和新密码'}
                </p>
              </div>

              {/* Step indicator */}
              <div className="flex items-center gap-2 mb-6">
                <div className={`flex-1 h-1 rounded-full ${step >= 1 ? 'bg-blue-500' : 'bg-slate-200 dark:bg-slate-700'}`} />
                <div className={`flex-1 h-1 rounded-full ${step >= 2 ? 'bg-blue-500' : 'bg-slate-200 dark:bg-slate-700'}`} />
              </div>

              {step === 1 ? (
                /* Step 1: Email */
                <div className="space-y-4">
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
                        onKeyDown={(e) => e.key === 'Enter' && handleSendCode()}
                      />
                    </div>
                  </div>

                  <button
                    type="button"
                    onClick={handleSendCode}
                    disabled={loading || !email}
                    className="w-full btn-ios-primary"
                  >
                    {loading ? <ButtonLoading /> : '发送验证码'}
                  </button>
                </div>
              ) : (
                /* Step 2: Code + New Password */
                <form onSubmit={handleSubmit} className="space-y-4">
                  {/* Email (readonly display) */}
                  <div className="input-group">
                    <label className="input-label">邮箱地址</label>
                    <div className="relative">
                      <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <input
                        type="email"
                        value={email}
                        readOnly
                        className="input-ios pl-9 bg-slate-50 dark:bg-slate-700/50"
                      />
                    </div>
                  </div>

                  {/* Verification code */}
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
                        disabled={countdown > 0 || loading}
                        className="btn-ios-secondary whitespace-nowrap"
                      >
                        {countdown > 0 ? `${countdown}s` : '重新发送'}
                      </button>
                    </div>
                  </div>

                  {/* New password */}
                  <div className="input-group">
                    <label className="input-label">新密码</label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <input
                        type={showPassword ? 'text' : 'password'}
                        value={newPassword}
                        onChange={(e) => setNewPassword(e.target.value)}
                        placeholder="请输入新密码（至少6位）"
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

                  {/* Confirm password */}
                  <div className="input-group">
                    <label className="input-label">确认密码</label>
                    <div className="relative">
                      <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <input
                        type={showPassword ? 'text' : 'password'}
                        value={confirmPassword}
                        onChange={(e) => setConfirmPassword(e.target.value)}
                        placeholder="请再次输入新密码"
                        className="input-ios pl-9 pr-9"
                      />
                    </div>
                  </div>

                  <button
                    type="submit"
                    disabled={loading}
                    className="w-full btn-ios-primary"
                  >
                    {loading ? <ButtonLoading /> : '重置密码'}
                  </button>
                </form>
              )}

              {/* Back to login */}
              <p className="text-center mt-6 text-slate-500 dark:text-slate-400 text-sm">
                <Link to="/login" className="inline-flex items-center gap-1 text-blue-600 dark:text-blue-400 font-medium hover:text-blue-700 dark:hover:text-blue-300">
                  <ArrowLeft className="w-4 h-4" />
                  返回登录
                </Link>
              </p>
            </div>

            {/* Footer */}
            <SafeHtml
              html={authFooterAd['auth.footer_ad_html']}
              className="mt-6 text-center text-xs text-slate-400 dark:text-slate-500"
            />
          </motion.div>
        </div>
      </div>
    </div>
  )
}
