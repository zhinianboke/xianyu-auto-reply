/** 界面与文案设置 Tab。 */
import type {
  AuthFooterAdSettings,
  DisclaimerSettings,
  LoginBrandingSettings,
  ThemeAppearanceSettings,
  ThemeColorPreset,
  ThemeEffect,
  ThemeFontFamily,
  ThemeFontSettings,
} from '@/types'
import { AuthFooterAdSettingsCard } from './AuthFooterAdSettingsCard'
import { DisclaimerSettingsCard } from './DisclaimerSettingsCard'
import { LoginBrandingSettingsCard } from './LoginBrandingSettingsCard'
import { ThemeAppearanceSettingsCard } from './ThemeAppearanceSettingsCard'
import { ThemeFontSettingsCard } from './ThemeFontSettingsCard'

interface AppearanceSettingsTabProps {
  themeAppearanceSettings: ThemeAppearanceSettings
  themeFontSettings: ThemeFontSettings
  loginBrandingSettings: LoginBrandingSettings
  authFooterAdSettings: AuthFooterAdSettings
  disclaimerSettings: DisclaimerSettings
  themeAppearanceSaving: boolean
  themeFontSaving: boolean
  loginBrandingSaving: boolean
  authFooterAdSaving: boolean
  disclaimerSaving: boolean
  onThemeAppearanceChange: (key: keyof ThemeAppearanceSettings, value: ThemeEffect | ThemeColorPreset) => void
  onThemeAppearanceSave: () => void
  onThemeFontChange: (key: keyof ThemeFontSettings, value: ThemeFontFamily) => void
  onThemeFontSave: () => void
  onLoginBrandingChange: (key: keyof LoginBrandingSettings, value: string) => void
  onLoginBrandingSave: () => void
  onAuthFooterAdChange: (key: keyof AuthFooterAdSettings, value: string) => void
  onAuthFooterAdSave: () => void
  onDisclaimerChange: (key: keyof DisclaimerSettings, value: string) => void
  onDisclaimerSave: () => void
}

export function AppearanceSettingsTab(props: AppearanceSettingsTabProps) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <ThemeAppearanceSettingsCard settings={props.themeAppearanceSettings} saving={props.themeAppearanceSaving} onChange={props.onThemeAppearanceChange} onSave={props.onThemeAppearanceSave} />
        <ThemeFontSettingsCard settings={props.themeFontSettings} saving={props.themeFontSaving} onChange={props.onThemeFontChange} onSave={props.onThemeFontSave} />
      </div>
      <LoginBrandingSettingsCard settings={props.loginBrandingSettings} saving={props.loginBrandingSaving} onChange={props.onLoginBrandingChange} onSave={props.onLoginBrandingSave} />
      <AuthFooterAdSettingsCard settings={props.authFooterAdSettings} saving={props.authFooterAdSaving} onChange={props.onAuthFooterAdChange} onSave={props.onAuthFooterAdSave} />
      <DisclaimerSettingsCard settings={props.disclaimerSettings} saving={props.disclaimerSaving} onChange={props.onDisclaimerChange} onSave={props.onDisclaimerSave} />
    </div>
  )
}
