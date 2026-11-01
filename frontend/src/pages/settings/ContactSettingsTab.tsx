/** 邮件与联系方式设置 Tab。 */
import { useRef } from 'react'
import { Copy, Heart, Mail, MessageCircle, Save, Upload, Users } from 'lucide-react'
import { ButtonLoading } from '@/components/common/Loading'
import { PasswordInput } from '@/components/common/PasswordInput'
import { copyToClipboard } from '@/utils/clipboard'
import { useUIStore } from '@/store/uiStore'
import type { SystemSettings } from '@/types'
import type { QrcodeType, QrcodeUploading, QrcodeUrls, SetSystemSettings } from './settingsTypes'

interface ContactSettingsTabProps {
  settings: SystemSettings | null
  setSettings: SetSystemSettings
  smtpSaving: boolean
  qrcodeUrls: QrcodeUrls
  qrcodeUploading: QrcodeUploading
  onSmtpSave: () => void
  onOpenTestEmail: () => void
  onUploadQrcode: (type: QrcodeType, file: File) => void
}

const QRCODE_ITEMS: Array<{ type: QrcodeType; label: string; icon: typeof MessageCircle; iconClass: string }> = [
  { type: 'wechat', label: '微信群', icon: MessageCircle, iconClass: 'text-green-500' },
  { type: 'qq', label: 'QQ群', icon: Users, iconClass: 'text-blue-500' },
  { type: 'wechat_official', label: '公众号', icon: MessageCircle, iconClass: 'text-green-600' },
  { type: 'telegram', label: 'Telegram', icon: MessageCircle, iconClass: 'text-blue-400' },
  { type: 'reward', label: '赞赏码', icon: Heart, iconClass: 'text-red-500' },
]

export function ContactSettingsTab({
  settings,
  setSettings,
  smtpSaving,
  qrcodeUrls,
  qrcodeUploading,
  onSmtpSave,
  onOpenTestEmail,
  onUploadQrcode,
}: ContactSettingsTabProps) {
  const { addToast } = useUIStore()
  return (
    <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <div className="vben-card">
        <div className="vben-card-header"><h2 className="vben-card-title"><Mail className="h-4 w-4" />SMTP邮件配置</h2></div>
        <div className="vben-card-body space-y-4">
          <p className="text-sm text-slate-500 dark:text-slate-400">配置SMTP服务器用于发送注册验证码等邮件通知</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <Field label="SMTP服务器">
              <input type="text" value={settings?.smtp_server || ''} onChange={(event) => setSettings((current) => current ? { ...current, smtp_server: event.target.value } : null)} placeholder="smtp.qq.com" className="input-ios" />
            </Field>
            <Field label="SMTP端口">
              <input type="number" min={1} max={65535} step={1} value={settings?.smtp_port === undefined ? 587 : settings.smtp_port} onChange={(event) => setSettings((current) => current ? { ...current, smtp_port: event.target.value } : null)} placeholder="587" className="input-ios" />
            </Field>
            <Field label="发件邮箱">
              <input type="email" value={settings?.smtp_user || ''} onChange={(event) => setSettings((current) => current ? { ...current, smtp_user: event.target.value } : null)} placeholder="your-email@qq.com" className="input-ios" />
            </Field>
            <Field label="邮箱密码/授权码">
              <div className="flex items-center gap-2">
                <PasswordInput value={settings?.smtp_password || ''} onChange={(value) => setSettings((current) => current ? { ...current, smtp_password: value } : null)} placeholder="输入密码或授权码" className="min-w-0 flex-1" showLabel="显示邮箱密码" hideLabel="隐藏邮箱密码" />
                <button type="button" onClick={async () => {
                  if (!settings?.smtp_password) {
                    addToast({ type: 'warning', message: '密码为空，无内容可复制' })
                    return
                  }
                  const copied = await copyToClipboard(settings.smtp_password)
                  addToast(copied ? { type: 'success', message: '已复制到剪贴板' } : { type: 'error', message: '复制失败，请手动选择文本复制' })
                }} className="btn-ios-secondary shrink-0 px-3" aria-label="复制邮箱密码" title="复制邮箱密码">
                  <Copy className="h-4 w-4" /><span className="hidden 2xl:inline">复制</span>
                </button>
              </div>
            </Field>
            <Field label="发件人显示名（可选）" className="sm:col-span-2">
              <input type="text" value={settings?.smtp_from || ''} onChange={(event) => setSettings((current) => current ? { ...current, smtp_from: event.target.value } : null)} placeholder="闲鱼自动回复系统" className="input-ios" />
            </Field>
          </div>
          <p className="text-xs text-slate-400">端口说明：25-无加密，465-SSL，587-TLS（推荐）</p>
          <button type="button" onClick={onOpenTestEmail} className="btn-ios-secondary">发送测试邮件</button>
          <div className="flex justify-end border-t border-slate-100 pt-4 dark:border-slate-700">
            <button type="button" onClick={onSmtpSave} disabled={smtpSaving} className="btn-ios-primary">
              {smtpSaving ? <ButtonLoading /> : <Save className="h-4 w-4" />}保存邮件配置
            </button>
          </div>
        </div>
      </div>

      <div className="vben-card">
        <div className="vben-card-header"><h2 className="vben-card-title"><MessageCircle className="h-4 w-4" />群二维码管理</h2></div>
        <div className="vben-card-body">
          <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">上传的二维码将显示在“关于”页面</p>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 2xl:grid-cols-5">
            {QRCODE_ITEMS.map((item) => <QrcodeItem key={item.type} {...item} imageUrl={qrcodeUrls[item.type]} uploading={qrcodeUploading[item.type]} onUpload={(file) => onUploadQrcode(item.type, file)} />)}
          </div>
        </div>
      </div>
    </div>
  )
}

function Field({ label, className = '', children }: { label: string; className?: string; children: React.ReactNode }) {
  return <div className={`input-group ${className}`}><label className="input-label">{label}</label>{children}</div>
}

interface QrcodeItemProps {
  label: string
  icon: typeof MessageCircle
  iconClass: string
  imageUrl: string
  uploading: boolean
  onUpload: (file: File) => void
}

function QrcodeItem({ label, icon: Icon, iconClass, imageUrl, uploading, onUpload }: QrcodeItemProps) {
  const fileRef = useRef<HTMLInputElement>(null)
  return (
    <div className="text-center">
      <p className="mb-2 flex items-center justify-center gap-1 text-sm font-medium text-slate-700 dark:text-slate-300"><Icon className={`h-4 w-4 ${iconClass}`} />{label}</p>
      <div className="mx-auto mb-2 h-24 w-24 overflow-hidden rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-700 dark:bg-slate-800">
        {imageUrl ? <img src={imageUrl} alt={label} className="h-full w-full object-cover" /> : <div className="flex h-full w-full items-center justify-center text-xs text-slate-400">未上传</div>}
      </div>
      <input ref={fileRef} type="file" accept="image/*" onChange={(event) => {
        const file = event.target.files?.[0]
        if (file) onUpload(file)
        event.target.value = ''
      }} className="hidden" />
      <button type="button" onClick={() => fileRef.current?.click()} disabled={uploading} className="btn-ios-secondary btn-sm">
        {uploading ? <ButtonLoading /> : <Upload className="h-3 w-3" />}上传
      </button>
    </div>
  )
}
