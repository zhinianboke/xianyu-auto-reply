/** 独立安全设置 Tab：完整读取后才允许保存，邮箱规则与 IP 封禁共用提示语。 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { RefreshCw, Save, ShieldCheck } from 'lucide-react'
import {
  getSecuritySettings,
  isSecuritySettings,
  isSecuritySettingsResponse,
  updateSecuritySettings,
  SECURITY_FREQUENCY_FIELDS,
} from '@/api/securitySettings'
import type { SecuritySettings } from '@/api/securitySettings'
import { Loading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

export function SecuritySettingsTab() {
  const { addToast } = useUIStore()
  const [settings, setSettings] = useState<SecuritySettings | null>(null)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [ready, setReady] = useState(false)
  const generation = useRef(0)
  const savingRef = useRef(false)

  const loadSettings = useCallback(() => {
    if (savingRef.current) return Promise.resolve()
    const requestId = ++generation.current
    setLoading(true)
    setReady(false)
    return getSecuritySettings().then((result) => {
      if (requestId !== generation.current) return
      if (!isSecuritySettingsResponse(result)) {
        addToast({ type: 'error', message: '安全设置响应格式错误，请重新加载，暂不能保存' })
        return
      }
      if (!result.success) {
        addToast({ type: 'error', message: result.message })
        return
      }
      if (!isSecuritySettings(result.data)) {
        addToast({ type: 'error', message: '安全设置响应不完整，请重新加载，暂不能保存' })
        return
      }
      setSettings(result.data)
      setReady(true)
    }, (error: unknown) => {
      if (requestId === generation.current) {
        addToast({ type: 'error', message: getApiErrorMessage(error, '加载安全设置失败') })
      }
    }).finally(() => {
      if (requestId === generation.current) setLoading(false)
    })
  }, [addToast])

  useEffect(() => {
    void loadSettings()
    return () => { generation.current += 1 }
  }, [loadSettings])

  const handleSave = () => {
    if (!ready || loading || savingRef.current || !settings) return
    if (!SECURITY_FREQUENCY_FIELDS.every(([key]) => Number.isSafeInteger(settings[key]) && settings[key] >= 0)) {
      addToast({ type: 'error', message: '频率必须为0至9007199254740991的非负整数，0表示关闭' })
      return
    }
    savingRef.current = true
    setSaving(true)
    const requestId = generation.current
    void updateSecuritySettings({ ...settings }).then((result) => {
      if (requestId !== generation.current) return
      if (!isSecuritySettingsResponse(result)) {
        setReady(false)
        addToast({ type: 'error', message: '保存响应格式错误，请重新加载确认安全设置，暂不能保存' })
        return
      }
      if (!result.success) {
        addToast({ type: 'error', message: result.message })
        return
      }
      if (!isSecuritySettings(result.data)) {
        setReady(false)
        addToast({ type: 'error', message: '保存响应不完整，请重新加载确认安全设置' })
        return
      }
      setSettings(result.data)
      addToast({ type: 'success', message: result.message })
    }, (error: unknown) => {
      if (requestId === generation.current) {
        addToast({ type: 'error', message: getApiErrorMessage(error, '保存安全设置失败') })
      }
    }).finally(() => {
      savingRef.current = false
      if (requestId === generation.current) setSaving(false)
    })
  }

  const updateField = (key: keyof SecuritySettings, value: string | number) => {
    setSettings((current) => current ? { ...current, [key]: value } : null)
  }
  const disabled = loading || saving || !ready

  return (
    <section className="vben-card relative" aria-busy={loading || saving}>
      {(loading || saving) && <div role="status" className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-white/80 dark:bg-slate-900/80"><Loading text={saving ? '正在保存安全设置…' : '正在加载安全设置…'} /></div>}
      <div className="vben-card-header flex flex-wrap items-center justify-between gap-3">
        <h2 className="vben-card-title"><ShieldCheck className="h-4 w-4" />安全设置</h2>
        <button type="button" onClick={() => void loadSettings()} disabled={loading || saving} className="btn-ios-secondary"><RefreshCw className="h-4 w-4" />重新加载</button>
      </div>
      <div className="vben-card-body space-y-4">
        {!ready && !loading && <p role="status" className="text-sm text-amber-700 dark:text-amber-300">安全设置未成功加载，已禁用保存；原配置不会被空值覆盖，请重新加载。</p>}
        <p className="text-sm text-slate-500 dark:text-slate-400">仅管理员可管理。邮箱和 IP 限制用于注册、登录及验证码发送，保存后对后续请求立即生效；已获取的验证码仍需符合当前规则。</p>
        <fieldset disabled={disabled} className="grid min-w-0 grid-cols-1 gap-4 lg:grid-cols-2 disabled:opacity-60">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3 lg:grid-cols-4 lg:col-span-2">
            {SECURITY_FREQUENCY_FIELDS.map(([key, label]) => <div className="input-group" key={key}>
              <label htmlFor={`security-${key}`} className="input-label">{label}</label>
              <input id={`security-${key}`} type="number" min="0" max="9007199254740991" step="1" value={Number.isNaN(settings?.[key]) ? '' : settings?.[key] ?? ''} onChange={(event) => updateField(key, event.target.value === '' ? NaN : Number(event.target.value))} className="input-ios" />
            </div>)}
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 lg:col-span-2">0表示关闭。每20秒检查最近1/5/10分钟和1/5/10/24小时的注册、邮件和登录日志；所有窗口从北京时间当天零点起统计，24小时档为当天累计。任一窗口达到阈值即违规，成功和失败均计数，注册验证码的两类审计分别计数。</p>
          <div className="input-group lg:col-span-2">
            <label htmlFor="security-common-suffixes" className="input-label">常见邮箱后缀</label>
            <textarea id="security-common-suffixes" rows={2} maxLength={60000} value={settings?.common_email_suffixes ?? ''} onChange={(event) => updateField('common_email_suffixes', event.target.value)} placeholder="例如 qq.com,@163.com，多个后缀用英文逗号分隔" className="input-ios" />
            <p className="text-xs text-slate-500 dark:text-slate-400">仅豁免完整域名的自动后缀封禁；IP仍独立计数和封禁，不豁免子域名，也不移除管理员原有禁止项。自动封禁只追加，不自动解封。</p>
          </div>
          <div className="input-group">
            <label htmlFor="security-email-denied" className="input-label">禁止邮箱后缀</label>
            <textarea id="security-email-denied" rows={3} maxLength={60000} value={settings?.email_denied_suffixes ?? ''} onChange={(event) => updateField('email_denied_suffixes', event.target.value)} placeholder="例如 qq.com,@example.com，多个后缀用英文逗号分隔" className="input-ios" />
            <p className="text-xs text-slate-500 dark:text-slate-400">禁止名单优先，按完整域名匹配；子域名需单独填写。</p>
          </div>
          <div className="input-group">
            <label htmlFor="security-email-allowed" className="input-label">允许邮箱后缀</label>
            <textarea id="security-email-allowed" rows={3} maxLength={60000} value={settings?.email_allowed_suffixes ?? ''} onChange={(event) => updateField('email_allowed_suffixes', event.target.value)} placeholder="例如 example.com，留空不限制允许范围" className="input-ios" />
            <p className="text-xs text-slate-500 dark:text-slate-400">填写后仅允许名单内且未被禁止的邮箱；两个名单均为空时不限制邮箱后缀。</p>
          </div>
          <div className="input-group lg:col-span-2">
            <label htmlFor="security-denied-ips" className="input-label">禁止 IP 列表（英文逗号分隔）</label>
            <textarea id="security-denied-ips" rows={3} maxLength={60000} value={settings?.denied_ips ?? ''} onChange={(event) => updateField('denied_ips', event.target.value)} placeholder="例如 198.51.100.,203.0.113.24,2001:db8::1" className="input-ios" />
            <p className="text-xs text-slate-500 dark:text-slate-400">支持完整 IPv4 / IPv6 或地址片段，逐项包含匹配，任一项命中即拒绝。IPv6 按规范化地址匹配；不支持 * 或 CIDR，勿使用中文逗号或空项，留空不限制 IP。</p>
          </div>
          <div className="input-group lg:col-span-2">
            <label htmlFor="security-denied-message" className="input-label">禁止提示语</label>
            <textarea id="security-denied-message" rows={2} maxLength={500} value={settings?.email_denied_message ?? ''} onChange={(event) => updateField('email_denied_message', event.target.value)} placeholder="邮箱后缀和 IP 限制共用的禁止提示语；留空使用默认提示" className="input-ios" />
            <p className="text-xs text-slate-500 dark:text-slate-400">留空时邮箱提示「该邮箱后缀不允许登录或注册，请更换邮箱」，IP 提示「该 IP 不允许登录或注册，请联系管理员」。提示语按普通文本保存。</p>
          </div>
        </fieldset>
        <div className="flex justify-end border-t border-slate-100 pt-4 dark:border-slate-700">
          <button type="button" onClick={handleSave} disabled={disabled || !settings} className="btn-ios-primary"><Save className="h-4 w-4" />保存安全设置</button>
        </div>
      </div>
    </section>
  )
}
