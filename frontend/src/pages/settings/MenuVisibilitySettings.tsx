import { EyeOff, Save } from 'lucide-react'
import { ButtonLoading } from '@/components/common/Loading'
import { getHideableFirstLevelMenuOptions } from '@/config/navigation'

interface MenuVisibilitySettingsProps {
  hiddenMenuKeys: string[]
  onChange: (keys: string[]) => void
  onSave: () => void
  excludedMenuKeys?: string[]
  saving?: boolean
}

export function MenuVisibilitySettings({ hiddenMenuKeys, onChange, onSave, excludedMenuKeys = [], saving = false }: MenuVisibilitySettingsProps) {
  const menuOptions = getHideableFirstLevelMenuOptions(excludedMenuKeys)
  const hiddenCount = hiddenMenuKeys.filter((key) => menuOptions.some((option) => option.key === key)).length

  const handleToggle = (menuKey: string, checked: boolean) => {
    if (checked) {
      onChange([...hiddenMenuKeys, menuKey])
      return
    }
    onChange(hiddenMenuKeys.filter((key) => key !== menuKey))
  }

  return (
    <div className="vben-card">
      <div className="vben-card-header flex items-center justify-between gap-3">
        <h2 className="vben-card-title">
          <EyeOff className="w-4 h-4" />
          隐藏菜单设置
        </h2>
        <div className="flex items-center gap-3">
          <span className="text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
            {`已隐藏 ${hiddenCount}/${menuOptions.length} 项`}
          </span>
          <button type="button" onClick={onSave} disabled={saving} className="btn-ios-primary">
            {saving ? <ButtonLoading /> : <Save className="w-4 h-4" />}
            保存菜单设置
          </button>
        </div>
      </div>
      <div className="vben-card-body space-y-3">
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-700 dark:border-amber-900/50 dark:bg-amber-900/20 dark:text-amber-300">
          仅支持设置一级菜单。一级菜单隐藏后，普通用户将无法查看该菜单，且该菜单下所有二级菜单会自动隐藏。
        </div>
        <div className="rounded-md border border-slate-200 dark:border-slate-700 overflow-hidden">
          <div className="max-h-64 overflow-y-auto divide-y divide-slate-200 dark:divide-slate-700">
          {menuOptions.map((option) => {
            const checked = hiddenMenuKeys.includes(option.key)
            return (
              <div
                key={option.key}
                className="flex items-center justify-between gap-3 px-3 py-2.5 bg-white dark:bg-slate-800/50"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium leading-5 text-slate-700 dark:text-slate-200 truncate">{option.label}</div>
                  <div className="text-xs text-slate-500 dark:text-slate-400">{checked ? '普通用户已隐藏' : '普通用户可见'}</div>
                </div>
                <div className="flex items-center gap-3 flex-shrink-0">
                  <span className={checked ? 'text-xs text-amber-600 dark:text-amber-400' : 'text-xs text-emerald-600 dark:text-emerald-400'}>
                    {checked ? '已隐藏' : '显示中'}
                  </span>
                  <label className="switch-ios">
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={saving}
                      onChange={(e) => handleToggle(option.key, e.target.checked)}
                    />
                    <span className="switch-slider"></span>
                  </label>
                </div>
              </div>
            )
          })}
          </div>
        </div>
      </div>
    </div>
  )
}
