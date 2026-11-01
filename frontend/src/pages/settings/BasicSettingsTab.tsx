/** 基础与认证设置 Tab。 */
import { Save, Settings as SettingsIcon } from 'lucide-react'
import { ButtonLoading } from '@/components/common/Loading'
import { getExeForcedHiddenMenuKeys } from '@/config/navigation'
import { getHiddenMenuKeysFromSettings } from '@/api/settings'
import type { SystemSettings } from '@/types'
import { MenuVisibilitySettings } from './MenuVisibilitySettings'
import { PasswordLoginModeSetting } from './PasswordLoginModeSetting'
import { SliderModeSetting } from './SliderModeSetting'
import { TokenApiModeSetting } from './TokenApiModeSetting'
import type { SetSystemSettings } from './settingsTypes'

interface BasicSettingsTabProps {
  settings: SystemSettings | null
  setSettings: SetSystemSettings
  isExeMode: boolean
  basicSaving: boolean
  hiddenMenuSaving: boolean
  onBasicSave: () => void
  onHiddenMenusChange: (keys: string[]) => void
  onHiddenMenusSave: () => void
}

export function BasicSettingsTab({
  settings,
  setSettings,
  isExeMode,
  basicSaving,
  hiddenMenuSaving,
  onBasicSave,
  onHiddenMenusChange,
  onHiddenMenusSave,
}: BasicSettingsTabProps) {
  return (
    <div className="space-y-4">
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title"><SettingsIcon className="h-4 w-4" />基础设置</h2>
        </div>
        <div className="vben-card-body space-y-4">
          <div className="grid grid-cols-1 gap-x-8 md:grid-cols-2">
            <ToggleSetting
              title="允许用户注册"
              description="开启后允许新用户注册账号"
              checked={Boolean(settings?.registration_enabled ?? false)}
              onChange={(checked) => setSettings((current) => current ? { ...current, registration_enabled: checked } : null)}
            />
            <ToggleSetting
              title="显示默认登录信息"
              description="登录页面显示默认账号密码提示"
              checked={Boolean(settings?.show_default_login_info ?? false)}
              onChange={(checked) => setSettings((current) => current ? { ...current, show_default_login_info: checked } : null)}
            />
            <ToggleSetting
              title="登录滑动验证码"
              description="开启后账号密码登录需要完成滑动验证"
              checked={Boolean(settings?.login_captcha_enabled ?? true)}
              onChange={(checked) => setSettings((current) => current ? { ...current, login_captcha_enabled: checked } : null)}
            />
            <div className="flex min-h-20 items-center justify-between gap-4 border-b border-slate-100 py-3 dark:border-slate-700">
              <div>
                <p className="font-medium text-slate-900 dark:text-slate-100">日志保留天数</p>
                <p className="text-sm text-slate-500 dark:text-slate-400">所有模块日志保留天数，保存后生效（1~365天）</p>
              </div>
              <input
                type="number"
                min={1}
                max={365}
                value={settings?.['log.retention_days'] === undefined ? '7' : settings['log.retention_days']}
                onChange={(event) => {
                  const value = event.target.value
                  if (value === '' || /^\d+$/.test(value)) {
                    setSettings((current) => current ? { ...current, 'log.retention_days': value } : null)
                  }
                }}
                className="input-ios w-24 text-center"
              />
            </div>
            <ToggleSetting
              title="人脸验证超时自动禁用"
              description="关闭后人脸验证超时不会自动禁用账号"
              checked={Boolean(settings?.['account.face_verify_timeout_disable'] ?? true)}
              onChange={(checked) => setSettings((current) => current ? { ...current, 'account.face_verify_timeout_disable': checked } : null)}
              className="md:col-span-2"
            />
          </div>

          <PasswordLoginModeSetting
            value={settings?.['password_login.mode']}
            remoteUrl={settings?.['password_login.remote_url']}
            remoteSecretKey={settings?.['password_login.remote_secret_key']}
            onSaved={(mode, remoteUrl, remoteSecretKey) => setSettings((current) => current ? {
              ...current,
              'password_login.mode': mode,
              'password_login.remote_url': remoteUrl ?? String(current['password_login.remote_url'] || ''),
              'password_login.remote_secret_key': remoteSecretKey ?? String(current['password_login.remote_secret_key'] || ''),
            } : current)}
          />
          <SliderModeSetting
            value={settings?.['captcha.slider_mode']}
            onSaved={(mode) => setSettings((current) => current ? { ...current, 'captcha.slider_mode': mode } : current)}
          />
          <TokenApiModeSetting
            value={settings?.['token.api_mode']}
            remoteUrl={settings?.['token.remote_url']}
            remoteSecretKey={settings?.['token.remote_secret_key']}
            onSaved={(mode, remoteUrl, remoteSecretKey) => setSettings((current) => current ? {
              ...current,
              'token.api_mode': mode,
              'token.remote_url': remoteUrl ?? String(current['token.remote_url'] || ''),
              'token.remote_secret_key': remoteSecretKey ?? String(current['token.remote_secret_key'] || ''),
            } : current)}
          />
          <div className="flex justify-end border-t border-slate-100 pt-4 dark:border-slate-700">
            <button type="button" onClick={onBasicSave} disabled={basicSaving} className="btn-ios-primary">
              {basicSaving ? <ButtonLoading /> : <Save className="h-4 w-4" />}保存基础设置
            </button>
          </div>
        </div>
      </div>
      <MenuVisibilitySettings
        hiddenMenuKeys={getHiddenMenuKeysFromSettings(settings)}
        onChange={onHiddenMenusChange}
        onSave={onHiddenMenusSave}
        excludedMenuKeys={getExeForcedHiddenMenuKeys(isExeMode)}
        saving={hiddenMenuSaving}
      />
    </div>
  )
}

interface ToggleSettingProps {
  title: string
  description: string
  checked: boolean
  onChange: (checked: boolean) => void
  className?: string
}

function ToggleSetting({ title, description, checked, onChange, className = '' }: ToggleSettingProps) {
  return (
    <div className={`flex min-h-20 items-center justify-between gap-4 border-b border-slate-100 py-3 dark:border-slate-700 ${className}`}>
      <div>
        <p className="font-medium text-slate-900 dark:text-slate-100">{title}</p>
        <p className="text-sm text-slate-500 dark:text-slate-400">{description}</p>
      </div>
      <label className="switch-ios">
        <input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} />
        <span className="switch-slider" />
      </label>
    </div>
  )
}
