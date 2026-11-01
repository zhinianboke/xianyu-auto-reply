import { Mail } from 'lucide-react'
import { ButtonLoading } from '@/components/common/Loading'

interface TestEmailModalProps {
  email: string
  sending: boolean
  onChange: (email: string) => void
  onClose: () => void
  onSend: () => void
}

export function TestEmailModal({ email, sending, onChange, onClose, onSend }: TestEmailModalProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="mx-4 w-full max-w-md rounded-xl bg-white p-6 shadow-xl dark:bg-slate-800">
        <h3 className="mb-4 text-lg font-semibold text-slate-900 dark:text-slate-100">发送测试邮件</h3>
        <div className="input-group mb-4">
          <label className="input-label">测试邮箱地址</label>
          <input type="email" value={email} onChange={(event) => onChange(event.target.value)} placeholder="请输入接收测试邮件的邮箱" className="input-ios" autoFocus />
        </div>
        <div className="flex justify-end gap-3">
          <button type="button" onClick={onClose} className="btn-ios-secondary" disabled={sending}>关闭</button>
          <button type="button" onClick={onSend} disabled={sending} className="btn-ios-primary">
            {sending ? <ButtonLoading /> : <Mail className="h-4 w-4" />}发送
          </button>
        </div>
      </div>
    </div>
  )
}
