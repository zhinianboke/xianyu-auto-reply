/** 支付与费用设置 Tab。 */
import { useState } from 'react'
import { CreditCard, Eye, EyeOff, Mail, Percent, Save } from 'lucide-react'
import { ButtonLoading } from '@/components/common/Loading'
import type { SystemSettings } from '@/types'
import { AdPriceSettingsCard } from './AdPriceSettingsCard'
import type { SetSystemSettings } from './settingsTypes'

interface PaymentSettingsTabProps {
  settings: SystemSettings | null
  setSettings: SetSystemSettings
  alipaySaving: boolean
  adPriceSaving: boolean
  withdrawSaving: boolean
  distributionSaving: boolean
  onAlipaySave: () => void
  onAdPriceSave: (payload: Partial<SystemSettings>) => void
  onWithdrawSave: () => void
  onDistributionSave: () => void
}

export function PaymentSettingsTab(props: PaymentSettingsTabProps) {
  const [showPrivateKey, setShowPrivateKey] = useState(false)
  const [showPublicKey, setShowPublicKey] = useState(false)
  const { settings, setSettings } = props

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <div className="vben-card xl:col-span-2">
        <div className="vben-card-header"><h2 className="vben-card-title"><CreditCard className="h-4 w-4" />支付宝配置</h2></div>
        <div className="vben-card-body space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">配置支付宝当面付（扫码支付）所需参数，用于订单收款</p>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Field label="应用ID（App ID）"><input type="text" value={settings?.['alipay.app_id'] || ''} onChange={(event) => setSettings((current) => current ? { ...current, 'alipay.app_id': event.target.value } : null)} placeholder="请输入支付宝应用ID" className="input-ios" /></Field>
            <Field label="网关地址">
              <input type="text" value={settings?.['alipay.gateway_url'] || ''} onChange={(event) => setSettings((current) => current ? { ...current, 'alipay.gateway_url': event.target.value } : null)} placeholder="https://openapi.alipay.com/gateway.do" className="input-ios" />
              <p className="mt-1 text-xs text-slate-400">正式环境：https://openapi.alipay.com/gateway.do，沙箱环境：https://openapi-sandbox.dl.alipaydev.com/gateway.do</p>
            </Field>
            <SecretField label="应用私钥" value={String(settings?.['alipay.private_key'] || '')} visible={showPrivateKey} onToggle={() => setShowPrivateKey((visible) => !visible)} onChange={(value) => setSettings((current) => current ? { ...current, 'alipay.private_key': value } : null)} placeholder="请输入RSA2应用私钥" />
            <SecretField label="支付宝公钥" value={String(settings?.['alipay.alipay_public_key'] || '')} visible={showPublicKey} onToggle={() => setShowPublicKey((visible) => !visible)} onChange={(value) => setSettings((current) => current ? { ...current, 'alipay.alipay_public_key': value } : null)} placeholder="请输入支付宝公钥" />
            <Field label="异步通知地址（Notify URL）">
              <input type="text" value={settings?.['alipay.notify_url'] || ''} onChange={(event) => setSettings((current) => current ? { ...current, 'alipay.notify_url': event.target.value } : null)} placeholder="例如：https://yourdomain.com/api/v1/payment/alipay/notify" className="input-ios" />
              <p className="mt-1 text-xs text-slate-400">支付成功后支付宝回调的地址，需要外网可访问</p>
            </Field>
          </div>
          <SaveButton saving={props.alipaySaving} onClick={props.onAlipaySave} label="保存支付宝配置" />
        </div>
      </div>

      <AdPriceSettingsCard settings={settings} saving={props.adPriceSaving} onChange={(key, value) => setSettings((current) => current ? { ...current, [key]: value } : null)} onSave={props.onAdPriceSave} />

      <div className="vben-card">
        <div className="vben-card-header"><h2 className="vben-card-title"><Mail className="h-4 w-4" />提现配置</h2></div>
        <div className="vben-card-body space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">配置提现相关参数，用于接收提现审核通知邮件</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="提现通知邮箱">
              <input type="email" value={settings?.['withdraw.notify_email'] || ''} onChange={(event) => setSettings((current) => current ? { ...current, 'withdraw.notify_email': event.target.value } : null)} placeholder="请输入接收提现申请通知的邮箱地址" className="input-ios" />
              <p className="mt-1 text-xs text-slate-400">用户申请提现时，通知邮件将发送至此邮箱。未配置则禁止提现。</p>
            </Field>
            <Field label="最低提现金额（元）">
              <input type="number" min="0" step="0.01" value={settings?.['withdraw.min_amount'] || ''} onChange={(event) => setSettings((current) => current ? { ...current, 'withdraw.min_amount': event.target.value } : null)} placeholder="不填则不限制最低金额" className="input-ios" />
              <p className="mt-1 text-xs text-slate-400">用户每次提现金额不得低于此值，不填则不限制。</p>
            </Field>
          </div>
          <SaveButton saving={props.withdrawSaving} onClick={props.onWithdrawSave} label="保存提现配置" />
        </div>
      </div>

      <div className="vben-card">
        <div className="vben-card-header"><h2 className="vben-card-title"><Percent className="h-4 w-4" />分销设置</h2></div>
        <div className="vben-card-body space-y-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="手续费类型">
              <select value={settings?.['distribution.fee_type'] || 'fixed'} onChange={(event) => setSettings((current) => current ? { ...current, 'distribution.fee_type': event.target.value } : null)} className="input-ios">
                <option value="fixed">固定金额（元）</option><option value="percent">按订单金额百分比（%）</option>
              </select>
            </Field>
            <Field label={settings?.['distribution.fee_type'] === 'percent' ? '手续费百分比（%）' : '手续费金额（元）'}>
              <input type="text" value={settings?.['distribution.fee_rate'] || ''} onChange={(event) => {
                const value = event.target.value
                if (value === '' || /^\d*\.?\d{0,2}$/.test(value)) setSettings((current) => current ? { ...current, 'distribution.fee_rate': value } : null)
              }} placeholder={settings?.['distribution.fee_type'] === 'percent' ? '请输入百分比，例如：5 表示 5%' : '请输入手续费金额，例如：2.00'} className="input-ios" />
              <p className="mt-1 text-xs text-slate-400">{settings?.['distribution.fee_type'] === 'percent' ? '按订单金额的百分比收取手续费，例如输入 5 表示每笔收取订单金额的 5%' : '分销交易时收取的固定手续费金额，例如输入 2.00 表示每笔收取 2 元'}</p>
            </Field>
          </div>
          <SaveButton saving={props.distributionSaving} onClick={props.onDistributionSave} label="保存分销设置" />
        </div>
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return <div className="input-group"><label className="input-label">{label}</label>{children}</div>
}

function SecretField({ label, value, visible, onToggle, onChange, placeholder }: { label: string; value: string; visible: boolean; onToggle: () => void; onChange: (value: string) => void; placeholder: string }) {
  return (
    <div className="input-group md:col-span-2">
      <label className="input-label">{label}</label>
      <div className="relative">
        <textarea value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} className="input-ios min-h-[80px] resize-y pr-10" style={{ WebkitTextSecurity: visible ? 'none' : 'disc' } as React.CSSProperties} />
        <button type="button" tabIndex={-1} onClick={onToggle} className="absolute right-2 top-2 p-1.5 text-slate-400 transition-colors hover:text-slate-600 dark:hover:text-slate-300" title={visible ? '隐藏' : '显示'} aria-label={visible ? `隐藏${label}` : `显示${label}`}>
          {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
        </button>
      </div>
    </div>
  )
}

function SaveButton({ saving, onClick, label }: { saving: boolean; onClick: () => void; label: string }) {
  return <div className="flex justify-end border-t border-slate-100 pt-4 dark:border-slate-700"><button type="button" onClick={onClick} disabled={saving} className="btn-ios-primary">{saving ? <ButtonLoading /> : <Save className="h-4 w-4" />}{label}</button></div>
}
