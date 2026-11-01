import type { SettingsTab } from './settingsTypes'

interface SystemSettingsTabsProps {
  activeTab: SettingsTab
  onChange: (tab: SettingsTab) => void
}

const TABS: Array<[SettingsTab, string]> = [
  ['basic', '基础与认证'],
  ['contact', '邮件与联系'],
  ['appearance', '界面与文案'],
  ['payment', '支付与费用'],
  ['user', '用户与网络'],
  ['runtime', '运行维护'],
]

export function SystemSettingsTabs({ activeTab, onChange }: SystemSettingsTabsProps) {
  return (
    <div className="tabs -mx-1 overflow-x-auto px-1" role="tablist" aria-label="系统设置功能模块">
      {TABS.map(([tab, label]) => (
        <button
          key={tab}
          type="button"
          role="tab"
          aria-selected={activeTab === tab}
          onClick={() => onChange(tab)}
          className={activeTab === tab ? 'tab tab-active shrink-0' : 'tab shrink-0 dark:text-slate-400 dark:hover:text-slate-200'}
        >
          {label}
        </button>
      ))}
    </div>
  )
}
