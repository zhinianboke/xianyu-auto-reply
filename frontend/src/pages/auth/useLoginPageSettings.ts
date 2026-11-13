/** 登录页登录状态检查及原有品牌、页脚、验证码设置加载。 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { verifyToken, getLoginInfoStatus, getLoginCaptchaStatus, getLoginBrandingSettings, getAuthFooterAdSettings } from '@/api/auth'
import { getDefaultAuthFooterAdSettings, getDefaultLoginBrandingSettings } from '@/api/settings'

export function useLoginPageSettings(isAuthenticated: boolean) {
  const navigate = useNavigate()
  const [showDefaultLogin, setShowDefaultLogin] = useState(true)
  const [loginCaptchaEnabled, setLoginCaptchaEnabled] = useState<boolean | null>(null)
  const [loginBranding, setLoginBranding] = useState(() => getDefaultLoginBrandingSettings())
  const [authFooterAd, setAuthFooterAd] = useState(() => getDefaultAuthFooterAdSettings())

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
    getLoginInfoStatus()
      .then((result) => setShowDefaultLogin(result.enabled))
      .catch(() => {})

    getLoginCaptchaStatus()
      .then((result) => setLoginCaptchaEnabled(result.enabled))
      .catch(() => {})

    getLoginBrandingSettings()
      .then((result) => setLoginBranding(result))
      .catch(() => {})

    getAuthFooterAdSettings()
      .then((result) => setAuthFooterAd(result))
      .catch(() => {})
  }, [])


  return { showDefaultLogin, loginCaptchaEnabled, loginBranding, authFooterAd }
}

