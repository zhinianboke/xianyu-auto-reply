/**
 * 系统设置页面。
 *
 * 功能模块按 Tab 展示，各卡片使用独立保存入口，避免跨模块覆盖未保存内容。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Navigate } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'
import {
  buildHiddenMenuSettingsPayload,
  getHiddenMenuKeysFromSettings,
  getSystemSettings,
  normalizeAuthFooterAdSettings,
  normalizeDisclaimerSettings,
  normalizeLoginBrandingSettings,
  testEmailSend,
} from '@/api/settings'
import { PageLoading } from '@/components/common/Loading'
import { useAuthStore } from '@/store/authStore'
import { useMenuVisibilityStore } from '@/store/menuVisibilityStore'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import {
  applyThemeSettings,
  normalizeThemeAppearanceSettings,
  normalizeThemeFontSettings,
} from '@/utils/theme'
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
import { AppearanceSettingsTab } from './AppearanceSettingsTab'
import { BasicSettingsTab } from './BasicSettingsTab'
import { ContactSettingsTab } from './ContactSettingsTab'
import { PaymentSettingsTab } from './PaymentSettingsTab'
import { ServiceRestartCard } from './ServiceRestartCard'
import { SystemSettingsTabs } from './SystemSettingsTabs'
import { TestEmailModal } from './TestEmailModal'
import { UserNetworkSettingsTab } from './UserNetworkSettingsTab'
import { useQrcodeSettings } from './useQrcodeSettings'
import { useSettingsActions } from './useSettingsActions'
import type { SettingsTab } from './settingsTypes'

export function Settings() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated, user } = useAuthStore()
  const { isExeMode, setHiddenMenuKeys, setIsExeMode } = useMenuVisibilityStore()
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<SettingsTab>('basic')
  const [settings, setSettings] = useState<SystemSettings | null>(null)
  const [showTestEmailModal, setShowTestEmailModal] = useState(false)
  const [testEmail, setTestEmail] = useState('')
  const [sendingTestEmail, setSendingTestEmail] = useState(false)
  const settingsRef = useRef<SystemSettings | null>(null)
  const qrcodes = useQrcodeSettings()

  settingsRef.current = settings
  const getCurrentSettings = useCallback(() => settingsRef.current, [])
  const actions = useSettingsActions(getCurrentSettings)

  const loadSettings = useCallback(async () => {
    if (!_hasHydrated || !isAuthenticated || !token || !user?.is_admin) return
    setLoading(true)
    try {
      const result = await getSystemSettings()
      if (!result.success || !result.data) {
        addToast({ type: 'error', message: '加载系统设置失败' })
        return
      }
      applyThemeSettings(result.data)
      setSettings(result.data)
      setIsExeMode(Boolean(result.data['runtime.is_exe_mode']))
      setHiddenMenuKeys(getHiddenMenuKeysFromSettings(result.data))
      await qrcodes.loadQrcodes()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载系统设置失败') })
    } finally {
      setLoading(false)
    }
  }, [_hasHydrated, addToast, isAuthenticated, qrcodes.loadQrcodes, setHiddenMenuKeys, setIsExeMode, token, user?.is_admin])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    if (!user?.is_admin) {
      setLoading(false)
      return
    }
    void loadSettings()
  }, [_hasHydrated, isAuthenticated, loadSettings, token, user?.is_admin])

  const handleTestEmail = useCallback(async () => {
    const email = testEmail.trim()
    setSendingTestEmail(true)
    try {
      const result = await testEmailSend(email)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '测试邮件发送成功' })
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
  }, [addToast, testEmail])

  const handleThemeAppearanceChange = (key: keyof ThemeAppearanceSettings, value: ThemeEffect | ThemeColorPreset) => {
    setSettings((current) => {
      const next = { ...(current ?? {}), [key]: value }
      applyThemeSettings(next)
      return next
    })
  }

  const handleThemeFontChange = (key: keyof ThemeFontSettings, value: ThemeFontFamily) => {
    setSettings((current) => {
      const next = { ...(current ?? {}), [key]: value }
      applyThemeSettings(next)
      return next
    })
  }

  if (!user?.is_admin) return <Navigate to="/dashboard" replace />
  if (loading) return <PageLoading />

  const themeAppearance = normalizeThemeAppearanceSettings(settings)
  const themeFont = normalizeThemeFontSettings(settings)
  const loginBranding = normalizeLoginBrandingSettings(settings)
  const authFooterAd = normalizeAuthFooterAdSettings(settings)
  const disclaimer = normalizeDisclaimerSettings(settings)

  return (
    <div className="space-y-4">
      <div className="page-header flex-between flex-wrap gap-4">
        <div><h1 className="page-title">系统设置</h1><p className="page-description">配置系统全局设置</p></div>
        <button type="button" onClick={() => void loadSettings()} className="btn-ios-secondary"><RefreshCw className="h-4 w-4" />刷新</button>
      </div>

      <SystemSettingsTabs activeTab={activeTab} onChange={setActiveTab} />

      {activeTab === 'basic' && <BasicSettingsTab
        settings={settings}
        setSettings={setSettings}
        isExeMode={isExeMode}
        basicSaving={actions.saving('basic')}
        hiddenMenuSaving={actions.saving('menus')}
        onBasicSave={() => void actions.saveBasic()}
        onHiddenMenusChange={(keys) => setSettings((current) => current ? { ...current, ...buildHiddenMenuSettingsPayload(keys) } : null)}
        onHiddenMenusSave={() => void actions.saveHiddenMenus()}
      />}

      {activeTab === 'contact' && <ContactSettingsTab
        settings={settings}
        setSettings={setSettings}
        smtpSaving={actions.saving('smtp')}
        qrcodeUrls={qrcodes.urls}
        qrcodeUploading={qrcodes.uploading}
        onSmtpSave={() => void actions.saveSmtp()}
        onOpenTestEmail={() => setShowTestEmailModal(true)}
        onUploadQrcode={(type, file) => void qrcodes.upload(type, file)}
      />}

      {activeTab === 'appearance' && <AppearanceSettingsTab
        themeAppearanceSettings={themeAppearance}
        themeFontSettings={themeFont}
        loginBrandingSettings={loginBranding}
        authFooterAdSettings={authFooterAd}
        disclaimerSettings={disclaimer}
        themeAppearanceSaving={actions.saving('themeAppearance')}
        themeFontSaving={actions.saving('themeFont')}
        loginBrandingSaving={actions.saving('branding')}
        authFooterAdSaving={actions.saving('footerAd')}
        disclaimerSaving={actions.saving('disclaimer')}
        onThemeAppearanceChange={handleThemeAppearanceChange}
        onThemeAppearanceSave={() => void actions.saveThemeAppearance(themeAppearance)}
        onThemeFontChange={handleThemeFontChange}
        onThemeFontSave={() => void actions.saveThemeFont(themeFont)}
        onLoginBrandingChange={(key: keyof LoginBrandingSettings, value: string) => setSettings((current) => ({ ...(current ?? {}), [key]: value }))}
        onLoginBrandingSave={() => void actions.saveLoginBranding(loginBranding)}
        onAuthFooterAdChange={(key: keyof AuthFooterAdSettings, value: string) => setSettings((current) => ({ ...(current ?? {}), [key]: value }))}
        onAuthFooterAdSave={() => void actions.saveAuthFooterAd(authFooterAd)}
        onDisclaimerChange={(key: keyof DisclaimerSettings, value: string) => setSettings((current) => ({ ...(current ?? {}), [key]: value }))}
        onDisclaimerSave={() => void actions.saveDisclaimer(disclaimer)}
      />}

      {activeTab === 'payment' && <PaymentSettingsTab
        settings={settings}
        setSettings={setSettings}
        paymentSaving={actions.saving('payment')}
        adPriceSaving={actions.saving('adPrice')}
        withdrawSaving={actions.saving('withdraw')}
        distributionSaving={actions.saving('distribution')}
        onPaymentSave={() => void actions.savePayment()}
        onAdPriceSave={(payload) => void actions.saveAdPrices(payload)}
        onWithdrawSave={() => void actions.saveWithdraw()}
        onDistributionSave={() => void actions.saveDistribution()}
      />}

      {activeTab === 'user' && <UserNetworkSettingsTab
        settings={settings}
        setSettings={setSettings}
        userExpirySaving={actions.saving('expiry')}
        proxySaving={actions.saving('proxy')}
        onUserExpirySave={() => void actions.saveUserExpiry()}
        onProxySave={() => void actions.saveProxy()}
      />}

      {activeTab === 'runtime' && <ServiceRestartCard />}

      {showTestEmailModal && <TestEmailModal email={testEmail} sending={sendingTestEmail} onChange={setTestEmail} onClose={() => { setShowTestEmailModal(false); setTestEmail('') }} onSend={() => void handleTestEmail()} />}
    </div>
  )
}
