import { LayoutTemplate, Save } from 'lucide-react'
import { ButtonLoading } from '@/components/common/Loading'
import type { LoginBrandingSettings } from '@/types'

interface LoginBrandingSettingsCardProps {
  settings: LoginBrandingSettings
  saving: boolean
  onChange: (key: keyof LoginBrandingSettings, value: string) => void
  onSave: () => void
}

export function LoginBrandingSettingsCard({ settings, saving, onChange, onSave }: LoginBrandingSettingsCardProps) {
  return (
    <div className="vben-card">
      <div className="vben-card-header flex items-center justify-between gap-3">
        <h2 className="vben-card-title">
          <LayoutTemplate className="w-4 h-4 text-blue-500" />
          系统描述维护
        </h2>
        <button onClick={onSave} disabled={saving} className="btn-ios-primary">
          {saving ? <ButtonLoading /> : <Save className="w-4 h-4" />}
          保存
        </button>
      </div>
      <div className="vben-card-body space-y-4">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          登录页面左侧品牌区和移动端标题，都会优先读取这里维护的系统名称、系统标题和系统描述。
        </p>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="input-group sm:col-span-2">
              <label className="input-label">系统名称</label>
              <input
                type="text"
                value={settings['login.system_name']}
                onChange={(event) => onChange('login.system_name', event.target.value)}
                placeholder="请输入系统名称"
                className="input-ios"
              />
            </div>

            <div className="input-group">
              <label className="input-label">系统标题</label>
              <textarea
                value={settings['login.system_title']}
                onChange={(event) => onChange('login.system_title', event.target.value)}
                placeholder="请输入系统标题"
                rows={3}
                className="input-ios min-h-[88px] resize-y"
              />
              <p className="text-xs text-slate-400 mt-1">支持换行，登录页会按换行展示标题。</p>
            </div>

            <div className="input-group">
              <label className="input-label">系统描述</label>
              <textarea
                value={settings['login.system_description']}
                onChange={(event) => onChange('login.system_description', event.target.value)}
                placeholder="请输入系统描述"
                rows={5}
                className="input-ios min-h-[120px] resize-y"
              />
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 p-4 space-y-4">
            <p className="text-sm font-medium text-slate-700 dark:text-slate-300">登录页预览</p>
            <div className="rounded-2xl overflow-hidden border border-slate-200 dark:border-slate-700 bg-slate-900 dark:bg-slate-950 min-h-[320px] relative">
              <div className="absolute inset-0 bg-gradient-to-br from-blue-600/20 to-transparent" />
              <div className="relative z-10 flex flex-col justify-center h-full px-6 py-8 space-y-5">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-blue-500 flex items-center justify-center text-white text-lg font-semibold">
                    鱼
                  </div>
                  <span className="text-xl font-bold text-white break-all">{settings['login.system_name']}</span>
                </div>
                <h3 className="text-3xl font-bold text-white leading-tight whitespace-pre-line">
                  {settings['login.system_title']}
                </h3>
                <p className="text-base text-slate-300 leading-7 whitespace-pre-line">
                  {settings['login.system_description']}
                </p>
              </div>
            </div>
            <div className="lg:hidden rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900/60 p-4 text-center">
              <p className="text-lg font-bold text-slate-900 dark:text-slate-100">{settings['login.system_name']}</p>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
