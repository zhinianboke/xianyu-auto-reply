import { AlertTriangle, Save } from 'lucide-react'
import { ButtonLoading } from '@/components/common/Loading'
import { SystemDisclaimerContent } from '@/components/common/SystemDisclaimerContent'
import type { DisclaimerSettings } from '@/types'

interface DisclaimerSettingsCardProps {
  settings: DisclaimerSettings
  saving: boolean
  onChange: (key: keyof DisclaimerSettings, value: string) => void
  onSave: () => void
}

const TEXT_INPUT_FIELDS: Array<{
  key: Exclude<keyof DisclaimerSettings, 'disclaimer.content'>
  label: string
  placeholder: string
}> = [
  {
    key: 'disclaimer.title',
    label: '标题',
    placeholder: '请输入免责声明标题',
  },
  {
    key: 'disclaimer.checkbox_text',
    label: '勾选提示文案',
    placeholder: '请输入勾选提示文案',
  },
  {
    key: 'disclaimer.agree_button_text',
    label: '同意按钮文案',
    placeholder: '请输入同意按钮文案',
  },
  {
    key: 'disclaimer.disagree_button_text',
    label: '不同意按钮文案',
    placeholder: '请输入不同意按钮文案',
  },
]

export function DisclaimerSettingsCard({ settings, saving, onChange, onSave }: DisclaimerSettingsCardProps) {
  return (
    <div className="vben-card">
      <div className="vben-card-header flex items-center justify-between gap-3">
        <h2 className="vben-card-title">
          <AlertTriangle className="w-4 h-4 text-amber-500" />
          免责声明维护
        </h2>
        <button onClick={onSave} disabled={saving} className="btn-ios-primary">
          {saving ? <ButtonLoading /> : <Save className="w-4 h-4" />}
          保存
        </button>
      </div>
      <div className="vben-card-body space-y-4">
        <p className="text-sm text-slate-500 dark:text-slate-400">
          登录后的免责声明弹窗和免责声明页面，都会读取这里维护的文案。
        </p>

        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {TEXT_INPUT_FIELDS.map((field) => (
              <div key={field.key} className="input-group">
                <label className="input-label">{field.label}</label>
                <input
                  type="text"
                  value={settings[field.key]}
                  onChange={(event) => onChange(field.key, event.target.value)}
                  placeholder={field.placeholder}
                  className="input-ios"
                />
              </div>
            ))}

            <div className="input-group sm:col-span-2">
              <label className="input-label">正文内容</label>
              <textarea
                value={settings['disclaimer.content']}
                onChange={(event) => onChange('disclaimer.content', event.target.value)}
                placeholder="请输入免责声明正文内容"
                rows={16}
                className="input-ios min-h-[320px] resize-y"
              />
            </div>
          </div>

          <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800/60 p-4 space-y-4">
            <div className="flex items-center gap-2 text-slate-900 dark:text-slate-100">
              <AlertTriangle className="w-5 h-5 text-amber-500" />
              <h3 className="text-lg font-semibold">{settings['disclaimer.title']}</h3>
            </div>
            <div className="max-h-[420px] overflow-y-auto rounded-lg bg-white dark:bg-slate-900/50 p-4 border border-slate-200 dark:border-slate-700">
              <SystemDisclaimerContent content={settings['disclaimer.content']} />
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
              <input type="checkbox" checked readOnly className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
              <span>{settings['disclaimer.checkbox_text']}</span>
            </label>
            <div className="grid grid-cols-2 gap-3">
              <button type="button" className="px-4 py-2.5 rounded-lg font-medium bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300">
                {settings['disclaimer.disagree_button_text']}
              </button>
              <button type="button" className="px-4 py-2.5 rounded-lg font-medium bg-blue-600 text-white">
                {settings['disclaimer.agree_button_text']}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
