/** 用户与网络设置 Tab。 */
import { CalendarClock, Globe, Save } from 'lucide-react'
import { ButtonLoading } from '@/components/common/Loading'
import type { SystemSettings } from '@/types'
import type { SetSystemSettings } from './settingsTypes'

interface UserNetworkSettingsTabProps {
  settings: SystemSettings | null
  setSettings: SetSystemSettings
  userExpirySaving: boolean
  proxySaving: boolean
  onUserExpirySave: () => void
  onProxySave: () => void
}

export function UserNetworkSettingsTab(props: UserNetworkSettingsTabProps) {
  const { settings, setSettings } = props
  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="vben-card">
        <div className="vben-card-header"><h2 className="vben-card-title"><CalendarClock className="h-4 w-4" />用户到期设置</h2></div>
        <div className="vben-card-body space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">配置用户续期单价与注册默认有效天数。注册默认天数留空时，新注册用户不设置到期日（永不过期）。</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="input-group">
              <label className="input-label">续期一个月的价格（元）</label>
              <input type="text" value={String(settings?.['user.renew_month_price'] || '')} onChange={(event) => {
                const value = event.target.value
                if (value === '' || /^\d*\.?\d{0,2}$/.test(value)) setSettings((current) => current ? { ...current, 'user.renew_month_price': value } : null)
              }} placeholder="请输入续期一个月的价格，例如：30.00" className="input-ios" />
              <p className="mt-1 text-xs text-slate-400">用户在个人设置中续期时，按「单价 × 续期月数」计算总价并扣减余额。留空则续期功能不可用。</p>
            </div>
            <div className="input-group">
              <label className="input-label">注册用户默认天数（天）</label>
              <input type="text" value={String(settings?.['user.register_default_days'] || '')} onChange={(event) => {
                const value = event.target.value
                if (value === '' || /^\d*$/.test(value)) setSettings((current) => current ? { ...current, 'user.register_default_days': value } : null)
              }} placeholder="留空表示注册不设置到期日" className="input-ios" />
              <p className="mt-1 text-xs text-slate-400">新用户注册时，到期日 = 注册时间 + 默认天数。留空则新用户永不过期。</p>
            </div>
          </div>
          <SaveButton saving={props.userExpirySaving} onClick={props.onUserExpirySave} label="保存到期设置" />
        </div>
      </div>

      <div className="vben-card">
        <div className="vben-card-header"><h2 className="vben-card-title"><Globe className="h-4 w-4" />代理设置</h2></div>
        <div className="vben-card-body space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">配置网络请求的代理 API，启用后系统会通过该代理转发请求</p>
          <div className="flex items-center justify-between border-b border-slate-100 py-3 dark:border-slate-700">
            <div><p className="font-medium text-slate-900 dark:text-slate-100">启用代理</p><p className="text-sm text-slate-500 dark:text-slate-400">开启后系统将通过下方配置的代理 API 转发网络请求</p></div>
            <label className="switch-ios"><input type="checkbox" checked={Boolean(settings?.['proxy.enabled'] ?? false)} onChange={(event) => setSettings((current) => current ? { ...current, 'proxy.enabled': event.target.checked } : null)} /><span className="switch-slider" /></label>
          </div>
          <div className="input-group">
            <label className="input-label">代理 API 的 URL</label>
            <textarea value={String(settings?.['proxy.api_url'] || '')} onChange={(event) => setSettings((current) => current ? { ...current, 'proxy.api_url': event.target.value } : null)} placeholder="请输入代理 API 的 URL，例如：https://example.com/proxy?token=xxx&region=cn" className="input-ios min-h-[72px] resize-y break-all" />
            <p className="mt-1 text-xs text-slate-400">代理 API 的完整地址，支持长链接</p>
          </div>
          <SaveButton saving={props.proxySaving} onClick={props.onProxySave} label="保存代理设置" />
        </div>
      </div>
    </div>
  )
}

function SaveButton({ saving, onClick, label }: { saving: boolean; onClick: () => void; label: string }) {
  return <div className="flex justify-end pt-2"><button type="button" onClick={onClick} disabled={saving} className="btn-ios-primary">{saving ? <ButtonLoading /> : <Save className="h-4 w-4" />}{label}</button></div>
}
