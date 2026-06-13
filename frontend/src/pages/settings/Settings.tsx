import { useState, useEffect, useRef, useCallback } from 'react'
import { Navigate } from 'react-router-dom'
import { Settings as SettingsIcon, Save, Mail, RefreshCw, Eye, EyeOff, Copy, Upload, MessageCircle, Users, Percent, CreditCard, Megaphone, Heart, Globe } from 'lucide-react'
import {
  buildHiddenMenuSettingsPayload,
  getHiddenMenuKeysFromSettings,
  getSystemSettings,
  normalizeAuthFooterAdSettings,
  normalizeDisclaimerSettings,
  normalizeLoginBrandingSettings,
  updateAuthFooterAdSettings,
  updateSystemSettings,
  updateDisclaimerSettings,
  updateLoginBrandingSettings,
  updateProxySettings,
  updateDistributionSettings,
  updateThemeAppearanceSettings,
  updateThemeFontSettings,
  testEmailSend,
  uploadQrcode,
  getQrcodeUrl,
} from '@/api/settings'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading, ButtonLoading } from '@/components/common/Loading'
import { getApiErrorMessage } from '@/utils/apiError'
import { copyToClipboard } from '@/utils/clipboard'
import { getExeForcedHiddenMenuKeys } from '@/config/navigation'
import { applyThemeSettings, normalizeThemeAppearanceSettings, normalizeThemeFontSettings } from '@/utils/theme'
import { DisclaimerSettingsCard } from './DisclaimerSettingsCard'
import { AuthFooterAdSettingsCard } from './AuthFooterAdSettingsCard'
import { LoginBrandingSettingsCard } from './LoginBrandingSettingsCard'
import { MenuVisibilitySettings } from './MenuVisibilitySettings'
import { ThemeAppearanceSettingsCard } from './ThemeAppearanceSettingsCard'
import { ThemeFontSettingsCard } from './ThemeFontSettingsCard'
import { useMenuVisibilityStore } from '@/store/menuVisibilityStore'
import type {
  AuthFooterAdSettings,
  DisclaimerSettings,
  LoginBrandingSettings,
  SystemSettings,
  ThemeAppearanceSettings,
  ThemeColorPreset,
  ThemeEffect,
  ThemeFontFamily,
  ThemeFontSettings,
} from '@/types'

export function Settings() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated, user } = useAuthStore()
  const { isExeMode, setHiddenMenuKeys, setIsExeMode } = useMenuVisibilityStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [loginBrandingSaving, setLoginBrandingSaving] = useState(false)
  const [authFooterAdSaving, setAuthFooterAdSaving] = useState(false)
  const [disclaimerSaving, setDisclaimerSaving] = useState(false)
  const [hiddenMenuSaving, setHiddenMenuSaving] = useState(false)
  const [themeAppearanceSaving, setThemeAppearanceSaving] = useState(false)
  const [themeFontSaving, setThemeFontSaving] = useState(false)
  // 代理设置独立保存状态：与页面右上角"保存设置"按钮的 saving 分离，互不影响
  const [proxySaving, setProxySaving] = useState(false)
  // 分销设置独立保存状态：与页面右上角"保存设置"按钮的 saving 分离，互不影响
  const [distributionSaving, setDistributionSaving] = useState(false)
  const [settings, setSettings] = useState<SystemSettings | null>(null)

  // SMTP密码显示状态
  const [showSmtpPassword, setShowSmtpPassword] = useState(false)
  // 支付宝密钥显示状态
  const [showAlipayPrivateKey, setShowAlipayPrivateKey] = useState(false)
  const [showAlipayPublicKey, setShowAlipayPublicKey] = useState(false)

  // 群二维码状态
  const [wechatQrcode, setWechatQrcode] = useState<string>('')
  const [qqQrcode, setQqQrcode] = useState<string>('')
  const [wechatOfficialQrcode, setWechatOfficialQrcode] = useState<string>('')
  const [telegramQrcode, setTelegramQrcode] = useState<string>('')
  const [rewardQrcode, setRewardQrcode] = useState<string>('')
  const [uploadingWechat, setUploadingWechat] = useState(false)
  const [uploadingQq, setUploadingQq] = useState(false)
  const [uploadingWechatOfficial, setUploadingWechatOfficial] = useState(false)
  const [uploadingTelegram, setUploadingTelegram] = useState(false)
  const [uploadingReward, setUploadingReward] = useState(false)
  const wechatFileRef = useRef<HTMLInputElement>(null)
  const qqFileRef = useRef<HTMLInputElement>(null)
  const wechatOfficialFileRef = useRef<HTMLInputElement>(null)
  const telegramFileRef = useRef<HTMLInputElement>(null)
  const rewardFileRef = useRef<HTMLInputElement>(null)

  // 测试邮件弹窗状态
  const [showTestEmailModal, setShowTestEmailModal] = useState(false)
  const [testEmail, setTestEmail] = useState('')
  const [sendingTestEmail, setSendingTestEmail] = useState(false)
  const loginBrandingSettings = normalizeLoginBrandingSettings(settings)
  const authFooterAdSettings = normalizeAuthFooterAdSettings(settings)
  const disclaimerSettings = normalizeDisclaimerSettings(settings)
  const themeAppearanceSettings = normalizeThemeAppearanceSettings(settings)
  const themeFontSettings = normalizeThemeFontSettings(settings)

  const loadSettings = async () => {
    if (!_hasHydrated || !isAuthenticated || !token || !user?.is_admin) return
    try {
      setLoading(true)
      const result = await getSystemSettings()
      if (result.success && result.data) {
        applyThemeSettings(result.data)
        setSettings(result.data)
        setIsExeMode(Boolean(result.data['runtime.is_exe_mode']))
        setHiddenMenuKeys(getHiddenMenuKeysFromSettings(result.data))
      }
      // 加载群二维码
      const [wechatRes, qqRes, wechatOfficialRes, telegramRes, rewardRes] = await Promise.all([
        getQrcodeUrl('wechat'),
        getQrcodeUrl('qq'),
        getQrcodeUrl('wechat_official'),
        getQrcodeUrl('telegram'),
        getQrcodeUrl('reward')
      ])
      if (wechatRes.success && wechatRes.data?.image_url) {
        setWechatQrcode(wechatRes.data.image_url)
      }
      if (qqRes.success && qqRes.data?.image_url) {
        setQqQrcode(qqRes.data.image_url)
      }
      if (wechatOfficialRes.success && wechatOfficialRes.data?.image_url) {
        setWechatOfficialQrcode(wechatOfficialRes.data.image_url)
      }
      if (telegramRes.success && telegramRes.data?.image_url) {
        setTelegramQrcode(telegramRes.data.image_url)
      }
      if (rewardRes.success && rewardRes.data?.image_url) {
        setRewardQrcode(rewardRes.data.image_url)
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载系统设置失败') })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    if (!user?.is_admin) {
      setLoading(false)
      return
    }
    loadSettings()
  }, [_hasHydrated, isAuthenticated, token, user?.is_admin])

  const handleSave = async () => {
    if (!settings) return
    try {
      setSaving(true)
      const result = await updateSystemSettings(settings)
      if (result.success) {
        applyThemeSettings(settings)
        setHiddenMenuKeys(getHiddenMenuKeysFromSettings(settings))
        addToast({ type: 'success', message: '设置保存成功' })
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '保存设置失败') })
    } finally {
      setSaving(false)
    }
  }

  const handleLoginBrandingChange = (key: keyof LoginBrandingSettings, value: string) => {
    setSettings((current) => ({
      ...(current ?? {}),
      [key]: value,
    }))
  }

  const handleLoginBrandingSave = async () => {
    if (!settings) {
      return
    }

    try {
      setLoginBrandingSaving(true)
      const result = await updateLoginBrandingSettings(settings)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '登录品牌设置保存成功' })
      } else {
        addToast({ type: 'error', message: result.message || '登录品牌设置保存失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '登录品牌设置保存失败') })
    } finally {
      setLoginBrandingSaving(false)
    }
  }

  const handleAuthFooterAdChange = (key: keyof AuthFooterAdSettings, value: string) => {
    setSettings((current) => ({
      ...(current ?? {}),
      [key]: value,
    }))
  }

  const handleAuthFooterAdSave = async () => {
    if (!settings) {
      return
    }

    try {
      setAuthFooterAdSaving(true)
      const result = await updateAuthFooterAdSettings(settings)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '底部广告设置保存成功' })
      } else {
        addToast({ type: 'error', message: result.message || '底部广告设置保存失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '底部广告设置保存失败') })
    } finally {
      setAuthFooterAdSaving(false)
    }
  }

  const handleThemeAppearanceChange = (key: keyof ThemeAppearanceSettings, value: ThemeEffect | ThemeColorPreset) => {
    setSettings((current) => {
      const nextSettings = {
        ...(current ?? {}),
        [key]: value,
      }
      applyThemeSettings(nextSettings)
      return nextSettings
    })
  }

  const handleThemeAppearanceSave = async () => {
    if (!settings) {
      return
    }

    try {
      setThemeAppearanceSaving(true)
      const result = await updateThemeAppearanceSettings(settings)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '主题外观保存成功' })
      } else {
        addToast({ type: 'error', message: result.message || '主题外观保存失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '主题外观保存失败') })
    } finally {
      setThemeAppearanceSaving(false)
    }
  }

  const handleThemeFontChange = (key: keyof ThemeFontSettings, value: ThemeFontFamily) => {
    setSettings((current) => {
      const nextSettings = {
        ...(current ?? {}),
        [key]: value,
      }
      applyThemeSettings(nextSettings)
      return nextSettings
    })
  }

  const handleThemeFontSave = async () => {
    if (!settings) {
      return
    }

    try {
      setThemeFontSaving(true)
      const result = await updateThemeFontSettings(settings)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '主题字体保存成功' })
      } else {
        addToast({ type: 'error', message: result.message || '主题字体保存失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '主题字体保存失败') })
    } finally {
      setThemeFontSaving(false)
    }
  }

  const handleDisclaimerChange = (key: keyof DisclaimerSettings, value: string) => {
    setSettings((current) => ({
      ...(current ?? {}),
      [key]: value,
    }))
  }

  const handleDisclaimerSave = async () => {
    if (!settings) {
      return
    }

    try {
      setDisclaimerSaving(true)
      const result = await updateDisclaimerSettings(settings)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '免责声明保存成功' })
      } else {
        addToast({ type: 'error', message: result.message || '免责声明保存失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '免责声明保存失败') })
    } finally {
      setDisclaimerSaving(false)
    }
  }

  // 代理设置独立保存：只 PUT proxy.api_url / proxy.enabled 两个键
  // 不使用页面右上角"保存设置"按钮，避免影响其他未改动的设置
  const handleProxySave = async () => {
    if (!settings) {
      return
    }

    // 业务校验：开启代理前必须先填写代理 API 的 URL
    // 用 trim 判断仅空白字符的输入也当作"未配置"，否则开启后调用方拿到无效 URL
    const apiUrl = ((settings['proxy.api_url'] as string) || '').trim()
    const enabled = Boolean(settings['proxy.enabled'])
    if (enabled && !apiUrl) {
      addToast({ type: 'error', message: '开启代理前请先填写代理 API 的 URL' })
      return
    }

    try {
      setProxySaving(true)
      const result = await updateProxySettings(settings)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '代理设置保存成功' })
      } else {
        addToast({ type: 'error', message: result.message || '代理设置保存失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '代理设置保存失败') })
    } finally {
      setProxySaving(false)
    }
  }

  // 分销设置独立保存：只 PUT distribution.* 相关键
  // 不使用页面右上角"保存设置"按钮，避免影响其他未改动的设置
  const handleDistributionSave = async () => {
    if (!settings) {
      return
    }

    try {
      setDistributionSaving(true)
      const result = await updateDistributionSettings(settings)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '分销设置保存成功' })
      } else {
        addToast({ type: 'error', message: result.message || '分销设置保存失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '分销设置保存失败') })
    } finally {
      setDistributionSaving(false)
    }
  }

  const handleTestEmail = useCallback(async () => {
    if (!testEmail) {
      addToast({ type: 'warning', message: '请输入测试邮箱地址' })
      return
    }
    try {
      setSendingTestEmail(true)
      const result = await testEmailSend(testEmail)
      if (result.success) {
        addToast({ type: 'success', message: '测试邮件发送成功' })
        setShowTestEmailModal(false)
        setTestEmail('')
      } else {
        addToast({ type: 'error', message: result.message || '发送测试邮件失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '发送测试邮件失败') })
    } finally {
      setSendingTestEmail(false)
    }
  }, [testEmail, addToast])

  const handleHiddenMenusChange = async (keys: string[]) => {
    if (!settings || hiddenMenuSaving) {
      return
    }

    const previousKeys = getHiddenMenuKeysFromSettings(settings)
    const hiddenMenuPayload = buildHiddenMenuSettingsPayload(keys)
    const nextSettings = {
      ...settings,
      ...hiddenMenuPayload,
    }

    setSettings(nextSettings)
    setHiddenMenuKeys(keys)

    try {
      setHiddenMenuSaving(true)
      const result = await updateSystemSettings(hiddenMenuPayload)
      if (!result.success) {
        throw new Error(result.message || '隐藏菜单设置保存失败')
      }
    } catch (error) {
      const rollbackPayload = buildHiddenMenuSettingsPayload(previousKeys)
      setSettings((current) => current ? { ...current, ...rollbackPayload } : current)
      setHiddenMenuKeys(previousKeys)
      addToast({
        type: 'error',
        message: getApiErrorMessage(error, '隐藏菜单设置保存失败'),
      })
    } finally {
      setHiddenMenuSaving(false)
    }
  }

  // 上传微信群二维码
  const handleUploadWechatQrcode = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      setUploadingWechat(true)
      const result = await uploadQrcode('wechat', file)
      if (result.success && result.data?.image_url) {
        setWechatQrcode(result.data.image_url + '?t=' + Date.now())
        addToast({ type: 'success', message: '微信群二维码上传成功' })
      } else {
        addToast({ type: 'error', message: result.message || '上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '上传失败' })
    } finally {
      setUploadingWechat(false)
      e.target.value = ''
    }
  }

  // 上传QQ群二维码
  const handleUploadQqQrcode = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      setUploadingQq(true)
      const result = await uploadQrcode('qq', file)
      if (result.success && result.data?.image_url) {
        setQqQrcode(result.data.image_url + '?t=' + Date.now())
        addToast({ type: 'success', message: 'QQ群二维码上传成功' })
      } else {
        addToast({ type: 'error', message: result.message || '上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '上传失败' })
    } finally {
      setUploadingQq(false)
      e.target.value = ''
    }
  }

  // 上传微信公众号二维码
  const handleUploadWechatOfficialQrcode = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      setUploadingWechatOfficial(true)
      const result = await uploadQrcode('wechat_official', file)
      if (result.success && result.data?.image_url) {
        setWechatOfficialQrcode(result.data.image_url + '?t=' + Date.now())
        addToast({ type: 'success', message: '微信公众号二维码上传成功' })
      } else {
        addToast({ type: 'error', message: result.message || '上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '上传失败' })
    } finally {
      setUploadingWechatOfficial(false)
      e.target.value = ''
    }
  }

  // 上传TG二维码
  const handleUploadTelegramQrcode = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      setUploadingTelegram(true)
      const result = await uploadQrcode('telegram', file)
      if (result.success && result.data?.image_url) {
        setTelegramQrcode(result.data.image_url + '?t=' + Date.now())
        addToast({ type: 'success', message: 'TG二维码上传成功' })
      } else {
        addToast({ type: 'error', message: result.message || '上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '上传失败' })
    } finally {
      setUploadingTelegram(false)
      e.target.value = ''
    }
  }

  // 上传赞赏码
  const handleUploadRewardQrcode = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      setUploadingReward(true)
      const result = await uploadQrcode('reward', file)
      if (result.success && result.data?.image_url) {
        setRewardQrcode(result.data.image_url + '?t=' + Date.now())
        addToast({ type: 'success', message: '赞赏码上传成功' })
      } else {
        addToast({ type: 'error', message: result.message || '上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '上传失败' })
    } finally {
      setUploadingReward(false)
      e.target.value = ''
    }
  }

  if (!user?.is_admin) {
    return <Navigate to="/dashboard" replace />
  }

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="page-header flex-between flex-wrap gap-4">
        <div>
          <h1 className="page-title">系统设置</h1>
          <p className="page-description">配置系统全局设置</p>
        </div>
        <div className="flex gap-2">
          <button onClick={loadSettings} className="btn-ios-secondary">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
          <button onClick={handleSave} disabled={saving} className="btn-ios-primary">
            {saving ? <ButtonLoading /> : <Save className="w-4 h-4" />}
            保存设置
          </button>
        </div>
      </div>

      {/* 基础设置 + SMTP邮件配置（仅管理员可见） */}
      {user?.is_admin && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {/* 基础设置 */}
          <div className="vben-card">
            <div className="vben-card-header">
              <h2 className="vben-card-title">
                <SettingsIcon className="w-4 h-4" />
                基础设置
              </h2>
            </div>
            <div className="vben-card-body space-y-4">
              <div className="flex items-center justify-between py-3 border-b border-slate-100 dark:border-slate-700">
                <div>
                  <p className="font-medium text-slate-900 dark:text-slate-100">允许用户注册</p>
                  <p className="text-sm text-slate-500 dark:text-slate-400">开启后允许新用户注册账号</p>
                </div>
                <label className="switch-ios">
                  <input
                    type="checkbox"
                    checked={Boolean(settings?.registration_enabled ?? false)}
                    onChange={(e) => setSettings(s => s ? { ...s, registration_enabled: e.target.checked } : null)}
                  />
                  <span className="switch-slider"></span>
                </label>
              </div>
              <div className="flex items-center justify-between py-3">
                <div>
                  <p className="font-medium text-slate-900 dark:text-slate-100">显示默认登录信息</p>
                  <p className="text-sm text-slate-500 dark:text-slate-400">登录页面显示默认账号密码提示</p>
                </div>
                <label className="switch-ios">
                  <input
                    type="checkbox"
                    checked={Boolean(settings?.show_default_login_info ?? false)}
                    onChange={(e) => setSettings(s => s ? { ...s, show_default_login_info: e.target.checked } : null)}
                  />
                  <span className="switch-slider"></span>
                </label>
              </div>
              <div className="flex items-center justify-between py-3 border-t border-slate-100 dark:border-slate-700">
                <div>
                  <p className="font-medium text-slate-900 dark:text-slate-100">登录滑动验证码</p>
                  <p className="text-sm text-slate-500 dark:text-slate-400">开启后账号密码登录需要完成滑动验证</p>
                </div>
                <label className="switch-ios">
                  <input
                    type="checkbox"
                    checked={Boolean(settings?.login_captcha_enabled ?? true)}
                    onChange={(e) => setSettings(s => s ? { ...s, login_captcha_enabled: e.target.checked } : null)}
                  />
                  <span className="switch-slider"></span>
                </label>
              </div>
              <div className="flex items-center justify-between py-3 border-t border-slate-100 dark:border-slate-700">
                <div>
                  <p className="font-medium text-slate-900 dark:text-slate-100">日志保留天数</p>
                  <p className="text-sm text-slate-500 dark:text-slate-400">所有模块日志保留天数，修改后实时生效（1~365天）</p>
                </div>
                <input
                  type="number"
                  min={1}
                  max={365}
                  value={settings?.['log.retention_days'] || '7'}
                  onChange={(e) => {
                    const val = e.target.value
                    if (val === '' || /^\d+$/.test(val)) {
                      setSettings(s => s ? { ...s, 'log.retention_days': val } : null)
                    }
                  }}
                  className="input-ios w-24 text-center"
                />
              </div>
              <div className="flex items-center justify-between py-3 border-t border-slate-100 dark:border-slate-700">
                <div>
                  <p className="font-medium text-slate-900 dark:text-slate-100">人脸验证超时自动禁用</p>
                  <p className="text-sm text-slate-500 dark:text-slate-400">关闭后人脸验证超时不会自动禁用账号</p>
                </div>
                <label className="switch-ios">
                  <input
                    type="checkbox"
                    checked={Boolean(settings?.['account.face_verify_timeout_disable'] ?? true)}
                    onChange={(e) => setSettings(s => s ? { ...s, 'account.face_verify_timeout_disable': e.target.checked } : null)}
                  />
                  <span className="switch-slider"></span>
                </label>
              </div>
            </div>
          </div>
          {/* SMTP邮件配置 */}
          <div className="vben-card">
            <div className="vben-card-header">
              <h2 className="vben-card-title">
                <Mail className="w-4 h-4" />
                SMTP邮件配置
              </h2>
            </div>
            <div className="vben-card-body space-y-4">
              <p className="text-sm text-slate-500 dark:text-slate-400">配置SMTP服务器用于发送注册验证码等邮件通知</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="input-group">
                  <label className="input-label">SMTP服务器</label>
                  <input
                    type="text"
                    value={settings?.smtp_server || ''}
                    onChange={(e) => setSettings(s => s ? { ...s, smtp_server: e.target.value } : null)}
                    placeholder="smtp.qq.com"
                    className="input-ios"
                  />
                </div>
                <div className="input-group">
                  <label className="input-label">SMTP端口</label>
                  <input
                    type="number"
                    value={settings?.smtp_port || 587}
                    onChange={(e) => setSettings(s => s ? { ...s, smtp_port: parseInt(e.target.value) } : null)}
                    placeholder="587"
                    className="input-ios"
                  />
                </div>
                <div className="input-group">
                  <label className="input-label">发件邮箱</label>
                  <input
                    type="email"
                    value={settings?.smtp_user || ''}
                    onChange={(e) => setSettings(s => s ? { ...s, smtp_user: e.target.value } : null)}
                    placeholder="your-email@qq.com"
                    className="input-ios"
                  />
                </div>
                <div className="input-group">
                  <label className="input-label">邮箱密码/授权码</label>
                  <div className="relative">
                    <input
                      type={showSmtpPassword ? 'text' : 'password'}
                      value={settings?.smtp_password || ''}
                      onChange={(e) => setSettings(s => s ? { ...s, smtp_password: e.target.value } : null)}
                      placeholder="输入密码或授权码"
                      className="input-ios pr-20"
                    />
                    <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1">
                      <button
                        type="button"
                        onClick={() => setShowSmtpPassword(!showSmtpPassword)}
                        className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                        title={showSmtpPassword ? '隐藏' : '显示'}
                      >
                        {showSmtpPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                      <button
                        type="button"
                        onClick={async () => {
                          // 先校验是否有内容可复制，避免误操作
                          if (!settings?.smtp_password) {
                            addToast({ type: 'warning', message: '密码为空，无内容可复制' })
                            return
                          }
                          // 使用 copyToClipboard 工具：自动 fallback execCommand，
                          // 兼容 HTTP 部署（非 secure context）以及 navigator.clipboard 不可用的场景。
                          // 旧实现直接 navigator.clipboard.writeText 且未捕获 Promise，
                          // 在 HTTP 环境下会静默失败但 toast 仍显示成功，误导用户。
                          const ok = await copyToClipboard(settings.smtp_password)
                          if (ok) {
                            addToast({ type: 'success', message: '已复制到剪贴板' })
                          } else {
                            addToast({ type: 'error', message: '复制失败，请手动选择文本复制' })
                          }
                        }}
                        className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                        title="复制"
                      >
                        <Copy className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
                <div className="input-group">
                  <label className="input-label">发件人显示名（可选）</label>
                  <input
                    type="text"
                    value={settings?.smtp_from || ''}
                    onChange={(e) => setSettings(s => s ? { ...s, smtp_from: e.target.value } : null)}
                    placeholder="闲鱼自动回复系统"
                    className="input-ios"
                  />
                </div>
              </div>
              <p className="text-xs text-slate-400">端口说明：25-无加密，465-SSL，587-TLS（推荐）</p>
              <button onClick={() => setShowTestEmailModal(true)} className="btn-ios-secondary">
                发送测试邮件
              </button>
            </div>
          </div>

          {/* 群二维码管理 */}
          <div className="vben-card lg:col-span-2">
            <div className="vben-card-header">
              <h2 className="vben-card-title">
                <MessageCircle className="w-4 h-4" />
                群二维码管理
              </h2>
            </div>
            <div className="vben-card-body">
              <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">上传的二维码将显示在"关于"页面</p>
              <div className="grid grid-cols-5 gap-4">
                {/* 微信群 */}
                <div className="text-center">
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 flex items-center justify-center gap-1">
                    <MessageCircle className="w-4 h-4 text-green-500" />
                    微信群
                  </p>
                  <div className="w-24 h-24 mx-auto mb-2 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden bg-slate-50 dark:bg-slate-800">
                    {wechatQrcode ? (
                      <img src={wechatQrcode} alt="微信群" className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-slate-400 text-xs">未上传</div>
                    )}
                  </div>
                  <input
                    ref={wechatFileRef}
                    type="file"
                    accept="image/*"
                    onChange={handleUploadWechatQrcode}
                    className="hidden"
                  />
                  <button
                    onClick={() => wechatFileRef.current?.click()}
                    disabled={uploadingWechat}
                    className="btn-ios-secondary btn-sm"
                  >
                    {uploadingWechat ? <ButtonLoading /> : <Upload className="w-3 h-3" />}
                    上传
                  </button>
                </div>
                {/* QQ群 */}
                <div className="text-center">
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 flex items-center justify-center gap-1">
                    <Users className="w-4 h-4 text-blue-500" />
                    QQ群
                  </p>
                  <div className="w-24 h-24 mx-auto mb-2 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden bg-slate-50 dark:bg-slate-800">
                    {qqQrcode ? (
                      <img src={qqQrcode} alt="QQ群" className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-slate-400 text-xs">未上传</div>
                    )}
                  </div>
                  <input
                    ref={qqFileRef}
                    type="file"
                    accept="image/*"
                    onChange={handleUploadQqQrcode}
                    className="hidden"
                  />
                  <button
                    onClick={() => qqFileRef.current?.click()}
                    disabled={uploadingQq}
                    className="btn-ios-secondary btn-sm"
                  >
                    {uploadingQq ? <ButtonLoading /> : <Upload className="w-3 h-3" />}
                    上传
                  </button>
                </div>
                {/* 微信公众号 */}
                <div className="text-center">
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 flex items-center justify-center gap-1">
                    <MessageCircle className="w-4 h-4 text-green-600" />
                    公众号
                  </p>
                  <div className="w-24 h-24 mx-auto mb-2 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden bg-slate-50 dark:bg-slate-800">
                    {wechatOfficialQrcode ? (
                      <img src={wechatOfficialQrcode} alt="微信公众号" className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-slate-400 text-xs">未上传</div>
                    )}
                  </div>
                  <input
                    ref={wechatOfficialFileRef}
                    type="file"
                    accept="image/*"
                    onChange={handleUploadWechatOfficialQrcode}
                    className="hidden"
                  />
                  <button
                    onClick={() => wechatOfficialFileRef.current?.click()}
                    disabled={uploadingWechatOfficial}
                    className="btn-ios-secondary btn-sm"
                  >
                    {uploadingWechatOfficial ? <ButtonLoading /> : <Upload className="w-3 h-3" />}
                    上传
                  </button>
                </div>
                {/* TG */}
                <div className="text-center">
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 flex items-center justify-center gap-1">
                    <MessageCircle className="w-4 h-4 text-blue-400" />
                    Telegram
                  </p>
                  <div className="w-24 h-24 mx-auto mb-2 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden bg-slate-50 dark:bg-slate-800">
                    {telegramQrcode ? (
                      <img src={telegramQrcode} alt="Telegram" className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-slate-400 text-xs">未上传</div>
                    )}
                  </div>
                  <input
                    ref={telegramFileRef}
                    type="file"
                    accept="image/*"
                    onChange={handleUploadTelegramQrcode}
                    className="hidden"
                  />
                  <button
                    onClick={() => telegramFileRef.current?.click()}
                    disabled={uploadingTelegram}
                    className="btn-ios-secondary btn-sm"
                  >
                    {uploadingTelegram ? <ButtonLoading /> : <Upload className="w-3 h-3" />}
                    上传
                  </button>
                </div>
                {/* 赞赏码 */}
                <div className="text-center">
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-2 flex items-center justify-center gap-1">
                    <Heart className="w-4 h-4 text-red-500" />
                    赞赏码
                  </p>
                  <div className="w-24 h-24 mx-auto mb-2 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden bg-slate-50 dark:bg-slate-800">
                    {rewardQrcode ? (
                      <img src={rewardQrcode} alt="赞赏码" className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-slate-400 text-xs">未上传</div>
                    )}
                  </div>
                  <input
                    ref={rewardFileRef}
                    type="file"
                    accept="image/*"
                    onChange={handleUploadRewardQrcode}
                    className="hidden"
                  />
                  <button
                    onClick={() => rewardFileRef.current?.click()}
                    disabled={uploadingReward}
                    className="btn-ios-secondary btn-sm"
                  >
                    {uploadingReward ? <ButtonLoading /> : <Upload className="w-3 h-3" />}
                    上传
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {user?.is_admin && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <ThemeAppearanceSettingsCard
            settings={themeAppearanceSettings}
            saving={themeAppearanceSaving}
            onChange={handleThemeAppearanceChange}
            onSave={handleThemeAppearanceSave}
          />
          <ThemeFontSettingsCard
            settings={themeFontSettings}
            saving={themeFontSaving}
            onChange={handleThemeFontChange}
            onSave={handleThemeFontSave}
          />
        </div>
      )}

      {user?.is_admin && (
        <LoginBrandingSettingsCard
          settings={loginBrandingSettings}
          saving={loginBrandingSaving}
          onChange={handleLoginBrandingChange}
          onSave={handleLoginBrandingSave}
        />
      )}

      {user?.is_admin && (
        <AuthFooterAdSettingsCard
          settings={authFooterAdSettings}
          saving={authFooterAdSaving}
          onChange={handleAuthFooterAdChange}
          onSave={handleAuthFooterAdSave}
        />
      )}

      {user?.is_admin && (
        <DisclaimerSettingsCard
          settings={disclaimerSettings}
          saving={disclaimerSaving}
          onChange={handleDisclaimerChange}
          onSave={handleDisclaimerSave}
        />
      )}

      {user?.is_admin && (
        <MenuVisibilitySettings
          hiddenMenuKeys={getHiddenMenuKeysFromSettings(settings)}
          onChange={handleHiddenMenusChange}
          excludedMenuKeys={getExeForcedHiddenMenuKeys(isExeMode)}
          saving={hiddenMenuSaving}
        />
      )}

      {/* 第三行：支付宝配置（仅管理员可见） */}
      {user?.is_admin && (
        <div className="grid grid-cols-1 gap-4">
          <div className="vben-card">
            <div className="vben-card-header">
              <h2 className="vben-card-title">
                <CreditCard className="w-4 h-4" />
                支付宝配置
              </h2>
            </div>
            <div className="vben-card-body space-y-4">
              <p className="text-sm text-slate-500 dark:text-slate-400">配置支付宝当面付（扫码支付）所需参数，用于订单收款</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="input-group">
                  <label className="input-label">应用ID（App ID）</label>
                  <input
                    type="text"
                    value={settings?.['alipay.app_id'] || ''}
                    onChange={(e) => setSettings(s => s ? { ...s, 'alipay.app_id': e.target.value } : null)}
                    placeholder="请输入支付宝应用ID"
                    className="input-ios"
                  />
                </div>
                <div className="input-group">
                  <label className="input-label">网关地址</label>
                  <input
                    type="text"
                    value={settings?.['alipay.gateway_url'] || ''}
                    onChange={(e) => setSettings(s => s ? { ...s, 'alipay.gateway_url': e.target.value } : null)}
                    placeholder="https://openapi.alipay.com/gateway.do"
                    className="input-ios"
                  />
                  <p className="text-xs text-slate-400 mt-1">正式环境：https://openapi.alipay.com/gateway.do，沙箱环境：https://openapi-sandbox.dl.alipaydev.com/gateway.do</p>
                </div>
                <div className="input-group md:col-span-2">
                  <label className="input-label">应用私钥</label>
                  <div className="relative">
                    <textarea
                      value={settings?.['alipay.private_key'] || ''}
                      onChange={(e) => setSettings(s => s ? { ...s, 'alipay.private_key': e.target.value } : null)}
                      placeholder="请输入RSA2应用私钥"
                      className="input-ios pr-10 min-h-[80px] resize-y"
                      style={{ WebkitTextSecurity: showAlipayPrivateKey ? 'none' : 'disc' } as React.CSSProperties}
                    />
                    <button
                      type="button"
                      onClick={() => setShowAlipayPrivateKey(!showAlipayPrivateKey)}
                      className="absolute right-2 top-2 p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                      title={showAlipayPrivateKey ? '隐藏' : '显示'}
                    >
                      {showAlipayPrivateKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                <div className="input-group md:col-span-2">
                  <label className="input-label">支付宝公钥</label>
                  <div className="relative">
                    <textarea
                      value={settings?.['alipay.alipay_public_key'] || ''}
                      onChange={(e) => setSettings(s => s ? { ...s, 'alipay.alipay_public_key': e.target.value } : null)}
                      placeholder="请输入支付宝公钥"
                      className="input-ios pr-10 min-h-[80px] resize-y"
                      style={{ WebkitTextSecurity: showAlipayPublicKey ? 'none' : 'disc' } as React.CSSProperties}
                    />
                    <button
                      type="button"
                      onClick={() => setShowAlipayPublicKey(!showAlipayPublicKey)}
                      className="absolute right-2 top-2 p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                      title={showAlipayPublicKey ? '隐藏' : '显示'}
                    >
                      {showAlipayPublicKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>
                <div className="input-group">
                  <label className="input-label">异步通知地址（Notify URL）</label>
                  <input
                    type="text"
                    value={settings?.['alipay.notify_url'] || ''}
                    onChange={(e) => setSettings(s => s ? { ...s, 'alipay.notify_url': e.target.value } : null)}
                    placeholder="例如：https://yourdomain.com/api/v1/payment/alipay/notify"
                    className="input-ios"
                  />
                  <p className="text-xs text-slate-400 mt-1">支付成功后支付宝回调的地址，需要外网可访问</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 提现配置（仅管理员可见） */}
      {user?.is_admin && (
        <div className="grid grid-cols-1 gap-4">
          <div className="vben-card">
            <div className="vben-card-header">
              <h2 className="vben-card-title">
                <Mail className="w-4 h-4" />
                提现配置
              </h2>
            </div>
            <div className="vben-card-body space-y-4">
              <p className="text-sm text-slate-500 dark:text-slate-400">配置提现相关参数，用于接收提现审核通知邮件</p>
              <div className="input-group">
                <label className="input-label">提现通知邮箱</label>
                <input
                  type="email"
                  value={settings?.['withdraw.notify_email'] || ''}
                  onChange={(e) => setSettings(s => s ? { ...s, 'withdraw.notify_email': e.target.value } : null)}
                  placeholder="请输入接收提现申请通知的邮箱地址"
                  className="input-ios"
                />
                <p className="text-xs text-slate-400 mt-1">用户申请提现时，通知邮件将发送至此邮箱。未配置则禁止提现。</p>
              </div>
              <div className="input-group">
                <label className="input-label">最低提现金额（元）</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={settings?.['withdraw.min_amount'] || ''}
                  onChange={(e) => setSettings(s => s ? { ...s, 'withdraw.min_amount': e.target.value } : null)}
                  placeholder="不填则不限制最低金额"
                  className="input-ios"
                />
                <p className="text-xs text-slate-400 mt-1">用户每次提现金额不得低于此値，不填则不限制。</p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 广告费用管理（仅管理员可见） */}
      {user?.is_admin && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="vben-card">
            <div className="vben-card-header">
              <h2 className="vben-card-title">
                <Megaphone className="w-4 h-4" />
                广告费用管理
              </h2>
            </div>
            <div className="vben-card-body space-y-4">
              <p className="text-sm text-slate-500 dark:text-slate-400">按广告类型设置每月费用，用户申请广告时会根据此价格计算总费用</p>
              <div className="input-group">
                <label className="input-label">轮播图广告（元/月）</label>
                <input
                  type="text"
                  value={(settings?.['ad_price.carousel'] as string) || ''}
                  onChange={(e) => {
                    const val = e.target.value
                    if (val === '' || /^\d*\.?\d{0,2}$/.test(val)) {
                      setSettings(s => s ? { ...s, 'ad_price.carousel': val } : null)
                    }
                  }}
                  placeholder="请输入轮播图广告每月价格"
                  className="input-ios"
                />
              </div>
              <div className="input-group">
                <label className="input-label">文字广告（元/月）</label>
                <input
                  type="text"
                  value={(settings?.['ad_price.text'] as string) || ''}
                  onChange={(e) => {
                    const val = e.target.value
                    if (val === '' || /^\d*\.?\d{0,2}$/.test(val)) {
                      setSettings(s => s ? { ...s, 'ad_price.text': val } : null)
                    }
                  }}
                  placeholder="请输入文字广告每月价格"
                  className="input-ios"
                />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 第四行：分销设置（仅管理员可见） */}
      {user?.is_admin && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className="vben-card">
            <div className="vben-card-header">
              <h2 className="vben-card-title">
                <Percent className="w-4 h-4" />
                分销设置
              </h2>
            </div>
            <div className="vben-card-body space-y-4">
              <div className="input-group">
                <label className="input-label">手续费类型</label>
                <select
                  value={settings?.['distribution.fee_type'] || 'fixed'}
                  onChange={(e) => setSettings(s => s ? { ...s, 'distribution.fee_type': e.target.value } : null)}
                  className="input-ios"
                >
                  <option value="fixed">固定金额（元）</option>
                  <option value="percent">按订单金额百分比（%）</option>
                </select>
              </div>
              <div className="input-group">
                <label className="input-label">
                  {settings?.['distribution.fee_type'] === 'percent' ? '手续费百分比（%）' : '手续费金额（元）'}
                </label>
                <input
                  type="text"
                  value={settings?.['distribution.fee_rate'] || ''}
                  onChange={(e) => {
                    const val = e.target.value
                    if (val === '' || /^\d*\.?\d{0,2}$/.test(val)) {
                      setSettings(s => s ? { ...s, 'distribution.fee_rate': val } : null)
                    }
                  }}
                  placeholder={settings?.['distribution.fee_type'] === 'percent' ? '请输入百分比，例如：5 表示 5%' : '请输入手续费金额，例如：2.00'}
                  className="input-ios"
                />
                <p className="text-xs text-slate-400 mt-1">
                  {settings?.['distribution.fee_type'] === 'percent'
                    ? '按订单金额的百分比收取手续费，例如输入 5 表示每笔收取订单金额的 5%'
                    : '分销交易时收取的固定手续费金额，例如输入 2.00 表示每笔收取 2 元'}
                </p>
              </div>
              {/* 独立保存按钮：只提交分销相关设置，不影响页面其他未改动字段 */}
              <div className="flex justify-end pt-2">
                <button
                  onClick={handleDistributionSave}
                  disabled={distributionSaving}
                  className="btn-ios-primary"
                >
                  {distributionSaving ? <ButtonLoading /> : <Save className="w-4 h-4" />}
                  保存分销设置
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 代理设置（仅管理员可见） */}
      {user?.is_admin && (
        <div className="grid grid-cols-1 gap-4">
          <div className="vben-card">
            <div className="vben-card-header">
              <h2 className="vben-card-title">
                <Globe className="w-4 h-4" />
                代理设置
              </h2>
            </div>
            <div className="vben-card-body space-y-4">
              <p className="text-sm text-slate-500 dark:text-slate-400">配置网络请求的代理 API，启用后系统会通过该代理转发请求</p>
              <div className="flex items-center justify-between py-3 border-b border-slate-100 dark:border-slate-700">
                <div>
                  <p className="font-medium text-slate-900 dark:text-slate-100">启用代理</p>
                  <p className="text-sm text-slate-500 dark:text-slate-400">开启后系统将通过下方配置的代理 API 转发网络请求</p>
                </div>
                <label className="switch-ios">
                  <input
                    type="checkbox"
                    checked={Boolean(settings?.['proxy.enabled'] ?? false)}
                    onChange={(e) => setSettings(s => s ? { ...s, 'proxy.enabled': e.target.checked } : null)}
                  />
                  <span className="switch-slider"></span>
                </label>
              </div>
              <div className="input-group">
                <label className="input-label">代理 API 的 URL</label>
                {/* 用 textarea 支持长 URL（包含较多查询参数时单行 input 显示不全） */}
                <textarea
                  value={(settings?.['proxy.api_url'] as string) || ''}
                  onChange={(e) => setSettings(s => s ? { ...s, 'proxy.api_url': e.target.value } : null)}
                  placeholder="请输入代理 API 的 URL，例如：https://example.com/proxy?token=xxx&region=cn"
                  className="input-ios min-h-[72px] resize-y break-all"
                />
                <p className="text-xs text-slate-400 mt-1">代理 API 的完整地址，支持长链接</p>
              </div>
              {/* 独立保存按钮：只提交代理两项设置，不影响页面其他未改动字段 */}
              <div className="flex justify-end pt-2">
                <button
                  onClick={handleProxySave}
                  disabled={proxySaving}
                  className="btn-ios-primary"
                >
                  {proxySaving ? <ButtonLoading /> : <Save className="w-4 h-4" />}
                  保存代理设置
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 测试邮件弹窗 */}
      {showTestEmailModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
          <div className="bg-white dark:bg-slate-800 rounded-xl p-6 w-full max-w-md mx-4 shadow-xl">
            <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 mb-4">发送测试邮件</h3>
            <div className="input-group mb-4">
              <label className="input-label">测试邮箱地址</label>
              <input
                type="email"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                placeholder="请输入接收测试邮件的邮箱"
                className="input-ios"
                autoFocus
              />
            </div>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => {
                  setShowTestEmailModal(false)
                  setTestEmail('')
                }}
                className="btn-ios-secondary"
                disabled={sendingTestEmail}
              >
                取消
              </button>
              <button
                onClick={handleTestEmail}
                disabled={sendingTestEmail}
                className="btn-ios-primary"
              >
                {sendingTestEmail ? <ButtonLoading /> : <Mail className="w-4 h-4" />}
                发送
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  )
}
