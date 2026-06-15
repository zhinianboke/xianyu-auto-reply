import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Button, Input } from '@arco-design/web-react'
import { login, verifyToken, getRegistrationStatus, getLoginInfoStatus, getLoginCaptchaStatus } from '@/api/auth'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { GeetestCaptcha, type GeetestResult } from '@/components/common/GeetestCaptcha'
import devingIllustration from '@/assets/illustrations/deving.svg'

export function Login() {
  const navigate = useNavigate()
  const { setAuth, isAuthenticated } = useAuthStore()
  const { addToast } = useUIStore()

  const [loading, setLoading] = useState(false)
  const [registrationEnabled, setRegistrationEnabled] = useState(false)
  const [showDefaultLogin, setShowDefaultLogin] = useState(false)
  const [loginCaptchaEnabled, setLoginCaptchaEnabled] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [geetestResult, setGeetestResult] = useState<GeetestResult | null>(null)
  const [geetestKey, setGeetestKey] = useState(0)

  const resetGeetest = () => {
    setGeetestResult(null)
    setGeetestKey((k) => k + 1)
  }

  useEffect(() => {
    document.documentElement.classList.remove('dark')
    localStorage.setItem('theme', 'light')
  }, [])

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/dashboard')
      return
    }

    const token = localStorage.getItem('auth_token')
    if (token) {
      verifyToken()
        .then((result) => {
          if (result.authenticated) navigate('/dashboard')
        })
        .catch(() => localStorage.removeItem('auth_token'))
    }
  }, [isAuthenticated, navigate])

  useEffect(() => {
    getRegistrationStatus().then((result) => setRegistrationEnabled(result.enabled)).catch(() => {})
    getLoginInfoStatus().then((result) => setShowDefaultLogin(result.enabled)).catch(() => {})
    getLoginCaptchaStatus().then((result) => setLoginCaptchaEnabled(result.enabled)).catch(() => {})
  }, [])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!username || !password) {
      addToast({ type: 'error', message: '请输入用户名和密码' })
      return
    }

    if (loginCaptchaEnabled && !geetestResult) {
      addToast({ type: 'error', message: '请完成滑动验证' })
      return
    }

    setLoading(true)
    try {
      const loginData = {
        username,
        password,
        geetest_challenge: geetestResult?.challenge,
        geetest_validate: geetestResult?.validate,
        geetest_seccode: geetestResult?.seccode,
      }
      const result = await login(loginData as Parameters<typeof login>[0])

      if (result.success && result.token) {
        setAuth(result.token, {
          user_id: result.user_id!,
          username: result.username!,
          is_admin: result.is_admin!,
        })
        addToast({ type: 'success', message: '登录成功' })
        navigate('/dashboard')
        return
      }

      addToast({ type: 'error', message: result.message || '登录失败' })
      resetGeetest()
    } catch {
      addToast({ type: 'error', message: '登录失败，请检查网络连接' })
      resetGeetest()
    } finally {
      setLoading(false)
    }
  }

  const fillDefaultCredentials = () => {
    setUsername('admin')
    setPassword('admin123')
  }

  return (
    <div className="mywms-login-page">
      <div className="mywms-login-panel">
        <section className="mywms-login-intro">
          <div className="mywms-login-copy">
            <h1>闲鱼管理系统</h1>
            <p>轻量、专业、可扩展的闲鱼自动化管理基础平台</p>
          </div>
          <img className="mywms-login-illustration" src={devingIllustration} alt="闲鱼管理系统插画" />
        </section>

        <section className="mywms-login-form-wrap">
          <div className="mywms-login-card">
            <div className="arco-card-header">
              <div className="arco-card-header-title">账号登录</div>
            </div>
            <form onSubmit={handleSubmit} className="mywms-login-form">
              <label>
                <span>用户名</span>
                <Input
                  value={username}
                  onChange={setUsername}
                  placeholder="请输入用户名"
                  autoComplete="username"
                />
              </label>

              <label>
                <span>密码</span>
                <Input.Password
                  value={password}
                  onChange={setPassword}
                  placeholder="请输入密码"
                  autoComplete="current-password"
                />
              </label>

              {loginCaptchaEnabled && (
                <label>
                  <span>滑动验证</span>
                  <GeetestCaptcha
                    key={`username-${geetestKey}`}
                    onSuccess={setGeetestResult}
                    onError={(err) => addToast({ type: 'error', message: err })}
                    disabled={loading}
                  />
                </label>
              )}

              <Button type="primary" htmlType="submit" long loading={loading} className="mywms-login-submit">
                登录
              </Button>
            </form>

            {showDefaultLogin && (
              <button type="button" className="mywms-login-tips" onClick={fillDefaultCredentials}>
                默认账号：admin / admin123
              </button>
            )}

            {registrationEnabled && (
              <p className="mywms-login-register">
                还没有账号？<Link to="/register">立即注册</Link>
              </p>
            )}
          </div>
        </section>
      </div>
    </div>
  )
}
