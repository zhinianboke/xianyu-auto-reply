/** 支付渠道、费用与提现设置 Tab。 */
import { useEffect, useMemo, useState } from 'react'
import { CreditCard, Eye, EyeOff, Mail, Percent, QrCode, Save } from 'lucide-react'
import { ButtonLoading } from '@/components/common/Loading'
import { PasswordInput } from '@/components/common/PasswordInput'
import { getPaymentConfigOptions, type PaymentOption } from '@/api/payment'
import type { PaymentChannel, SystemSettings } from '@/types'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { AdPriceSettingsCard } from './AdPriceSettingsCard'
import type { SetSystemSettings } from './settingsTypes'

interface PaymentSettingsTabProps {
  settings: SystemSettings | null
  setSettings: SetSystemSettings
  paymentSaving: boolean
  adPriceSaving: boolean
  withdrawSaving: boolean
  distributionSaving: boolean
  onPaymentSave: () => void
  onAdPriceSave: (payload: Partial<SystemSettings>) => void
  onWithdrawSave: () => void
  onDistributionSave: () => void
}

export function PaymentSettingsTab(props: PaymentSettingsTabProps) {
  const { addToast } = useUIStore()
  const { settings, setSettings } = props
  const channel = (settings?.['payment.channel'] || 'alipay') as PaymentChannel
  const [channels, setChannels] = useState<Array<{ value: PaymentChannel; label: string }>>([])
  const [payTypes, setPayTypes] = useState<PaymentOption[]>([])
  const selectedPayTypes = useMemo(() => String(settings?.['zzcode.pay_types'] || 'alipay').split(',').filter(Boolean), [settings])

  useEffect(() => {
    getPaymentConfigOptions().then((result) => {
      if (!result.success || !result.data) {
        addToast({ type: 'error', message: result.message || '加载支付方式失败' })
        return
      }
      setChannels(result.data.channels)
      setPayTypes(result.data.pay_types)
    }).catch((error) => addToast({ type: 'error', message: getApiErrorMessage(error, '加载支付方式失败') }))
  }, [addToast])

  const update = (key: string, value: unknown) => setSettings((current) => current ? { ...current, [key]: value } : null)
  const togglePayType = (value: string) => {
    const next = selectedPayTypes.includes(value)
      ? selectedPayTypes.filter((item) => item !== value)
      : [...selectedPayTypes, value]
    update('zzcode.pay_types', next.join(','))
  }

  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <div className="vben-card xl:col-span-2">
        <div className="vben-card-header"><h2 className="vben-card-title"><CreditCard className="h-4 w-4" />支付配置</h2></div>
        <div className="vben-card-body space-y-5">
          <div className="input-group">
            <label className="input-label">启用的支付渠道</label>
            <div className="flex flex-wrap gap-3">
              {channels.map((item) => (
                <label key={item.value} className={`flex cursor-pointer items-center gap-2 rounded-lg border px-4 py-2.5 text-sm transition-colors ${channel === item.value ? 'border-[rgb(var(--color-primary))] bg-[rgb(var(--color-primary-light))] text-[rgb(var(--color-primary))]' : 'border-slate-200 text-slate-600 hover:border-slate-300 dark:border-slate-700 dark:text-slate-300'}`}>
                  <input type="radio" name="payment-channel" checked={channel === item.value} onChange={() => update('payment.channel', item.value)} />
                  {item.value === 'zzcode' ? <QrCode className="h-4 w-4" /> : <CreditCard className="h-4 w-4" />}{item.label}
                </label>
              ))}
            </div>
            <Hint>余额充值和广告付款都会使用当前启用的支付渠道。</Hint>
          </div>

          {channel === 'alipay' ? <AlipayFields settings={settings} update={update} /> : (
            <div className="space-y-4">
              <p className="text-sm text-slate-500 dark:text-slate-400">配置易支付兼容接口，支持异步回调自动入账。</p>
              <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
                <Field label="商户ID（pid）"><input value={String(settings?.['zzcode.pid'] || '')} onChange={(event) => update('zzcode.pid', event.target.value)} className="input-ios" placeholder="请输入码支付商户ID" /></Field>
                <Field label="商户密钥（KEY）"><PasswordInput value={String(settings?.['zzcode.key'] || '')} onChange={(value) => update('zzcode.key', value)} placeholder="请输入码支付商户密钥" showLabel="显示商户密钥" hideLabel="隐藏商户密钥" /></Field>
                <Field label="请求网关地址"><input value={String(settings?.['zzcode.gateway'] || '')} onChange={(event) => update('zzcode.gateway', event.target.value)} className="input-ios" placeholder="https://pay.example.com/mapi.php" /></Field>
                <Field label="异步通知地址"><input value={String(settings?.['zzcode.notify_url'] || '')} onChange={(event) => update('zzcode.notify_url', event.target.value)} className="input-ios" placeholder="https://example.com/api/v1/payment/zzcode/notify" /><Hint>外网可访问，固定路径为 /api/v1/payment/zzcode/notify。</Hint></Field>
                <Field label="页面跳转地址"><input value={String(settings?.['zzcode.return_url'] || '')} onChange={(event) => update('zzcode.return_url', event.target.value)} className="input-ios" placeholder="https://example.com/api/v1/payment/zzcode/return" /><Hint>支付完成后的提示页，实际入账以异步通知为准。</Hint></Field>
              </div>
              <div className="input-group">
                <label className="input-label">开启的支付方式</label>
                <div className="flex flex-wrap gap-2">
                  {payTypes.map((item) => {
                    const active = selectedPayTypes.includes(item.value)
                    return <label key={item.value} className={`flex cursor-pointer items-center gap-2 rounded-full border px-3 py-1.5 text-sm transition-colors ${active ? 'border-[rgb(var(--color-primary))] text-[rgb(var(--color-primary))]' : 'border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-300'}`}><input type="checkbox" checked={active} onChange={() => togglePayType(item.value)} />{item.label}</label>
                  })}
                </div>
                <Hint>至少开启一种；开启多种时，付款前需要用户选择。</Hint>
              </div>
            </div>
          )}
          <SaveButton saving={props.paymentSaving} onClick={props.onPaymentSave} label="保存支付配置" />
        </div>
      </div>

      <AdPriceSettingsCard settings={settings} saving={props.adPriceSaving} onChange={(key, value) => update(key, value)} onSave={props.onAdPriceSave} />
      <WithdrawCard settings={settings} update={update} saving={props.withdrawSaving} onSave={props.onWithdrawSave} />
      <DistributionCard settings={settings} update={update} saving={props.distributionSaving} onSave={props.onDistributionSave} />
    </div>
  )
}

function AlipayFields({ settings, update }: { settings: SystemSettings | null; update: (key: string, value: unknown) => void }) {
  const [privateKeyVisible, setPrivateKeyVisible] = useState(false)
  const [publicKeyVisible, setPublicKeyVisible] = useState(false)
  return <div className="space-y-4"><p className="text-sm text-slate-500 dark:text-slate-400">配置支付宝当面付（扫码支付）所需参数。</p><div className="grid grid-cols-1 gap-4 md:grid-cols-2">
    <Field label="应用ID（App ID）"><input value={String(settings?.['alipay.app_id'] || '')} onChange={(event) => update('alipay.app_id', event.target.value)} className="input-ios" /></Field>
    <Field label="网关地址"><input value={String(settings?.['alipay.gateway_url'] || '')} onChange={(event) => update('alipay.gateway_url', event.target.value)} className="input-ios" /></Field>
    <SecretTextarea label="应用私钥" value={String(settings?.['alipay.private_key'] || '')} visible={privateKeyVisible} onToggle={() => setPrivateKeyVisible((value) => !value)} onChange={(value) => update('alipay.private_key', value)} />
    <SecretTextarea label="支付宝公钥" value={String(settings?.['alipay.alipay_public_key'] || '')} visible={publicKeyVisible} onToggle={() => setPublicKeyVisible((value) => !value)} onChange={(value) => update('alipay.alipay_public_key', value)} />
    <Field label="异步通知地址"><input value={String(settings?.['alipay.notify_url'] || '')} onChange={(event) => update('alipay.notify_url', event.target.value)} className="input-ios" placeholder="https://example.com/api/v1/payment/alipay/notify" /></Field>
  </div></div>
}

function SecretTextarea({ label, value, visible, onToggle, onChange }: { label: string; value: string; visible: boolean; onToggle: () => void; onChange: (value: string) => void }) {
  return <div className="input-group"><label className="input-label">{label}</label><div className="relative"><textarea value={value} onChange={(event) => onChange(event.target.value)} className="input-ios min-h-[90px] resize-y pr-10" style={{ WebkitTextSecurity: visible ? 'none' : 'disc' } as React.CSSProperties} /><button type="button" tabIndex={-1} onClick={onToggle} className="absolute right-2 top-2 p-1.5 text-slate-400 transition-colors hover:text-slate-600 dark:hover:text-slate-300" aria-label={visible ? `隐藏${label}` : `显示${label}`}>{visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}</button></div></div>
}

interface CardProps { settings: SystemSettings | null; update: (key: string, value: unknown) => void; saving: boolean; onSave: () => void }
function WithdrawCard({ settings, update, saving, onSave }: CardProps) { return <div className="vben-card"><div className="vben-card-header"><h2 className="vben-card-title"><Mail className="h-4 w-4" />提现配置</h2></div><div className="vben-card-body space-y-4"><div className="grid grid-cols-1 gap-4 sm:grid-cols-2"><Field label="提现通知邮箱"><input type="email" value={String(settings?.['withdraw.notify_email'] || '')} onChange={(e) => update('withdraw.notify_email', e.target.value)} className="input-ios" /></Field><Field label="最低提现金额（元）"><input type="number" min="0" step="0.01" value={String(settings?.['withdraw.min_amount'] || '')} onChange={(e) => update('withdraw.min_amount', e.target.value)} className="input-ios" /></Field></div><SaveButton saving={saving} onClick={onSave} label="保存提现配置" /></div></div> }
function DistributionCard({ settings, update, saving, onSave }: CardProps) { return <div className="vben-card"><div className="vben-card-header"><h2 className="vben-card-title"><Percent className="h-4 w-4" />分销设置</h2></div><div className="vben-card-body space-y-4"><div className="grid grid-cols-1 gap-4 sm:grid-cols-2"><Field label="手续费类型"><select value={String(settings?.['distribution.fee_type'] || 'fixed')} onChange={(e) => update('distribution.fee_type', e.target.value)} className="input-ios"><option value="fixed">固定金额（元）</option><option value="percent">按订单金额百分比（%）</option></select></Field><Field label="手续费"><input value={String(settings?.['distribution.fee_rate'] || '')} onChange={(e) => update('distribution.fee_rate', e.target.value)} className="input-ios" /></Field></div><SaveButton saving={saving} onClick={onSave} label="保存分销设置" /></div></div> }
function Field({ label, children }: { label: string; children: React.ReactNode }) { return <div className="input-group"><label className="input-label">{label}</label>{children}</div> }
function Hint({ children }: { children: React.ReactNode }) { return <p className="mt-1 text-xs text-slate-400">{children}</p> }
function SaveButton({ saving, onClick, label }: { saving: boolean; onClick: () => void; label: string }) { return <div className="flex justify-end border-t border-slate-100 pt-4 dark:border-slate-700"><button type="button" onClick={onClick} disabled={saving} className="btn-ios-primary">{saving ? <ButtonLoading /> : <Save className="h-4 w-4" />}{label}</button></div> }
