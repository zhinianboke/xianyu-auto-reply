/** 逐条编辑结算结果：选项来自数据库字典，修改说明追加到原记录审计备注。 */
import { useState } from 'react'
import { Loader2 } from 'lucide-react'
import type { AdminSettlementRecord, SettlementOption, SettlementUpdate } from '@/api/adminSettlements'

interface Props {
  record: AdminSettlementRecord
  options: SettlementOption[]
  saving: boolean
  error: string
  onClose: () => void
  onSave: (payload: SettlementUpdate) => void
}

/** 仅修改结果和拒绝原因；提交记录版本以防并发覆盖，保存中禁止关闭和重复操作。 */
export function SettlementResultModal({ record, options, saving, error, onClose, onSave }: Props) {
  const [status, setStatus] = useState<string>(record.status)
  const [rejectReason, setRejectReason] = useState(record.reject_reason || '')
  const [remark, setRemark] = useState('')
  const unchanged = status === record.status && (status === 'rejected' ? rejectReason.trim() : '') === (record.reject_reason || '') && !remark.trim()
  const allowed = options.some(option => option.value === status && option.enabled)

  return (
    <div className="modal-overlay z-[210]">
      <div role="dialog" aria-modal="true" aria-labelledby="settlement-result-title" className="modal-content max-w-md">
        <div className="modal-header"><h2 id="settlement-result-title" className="modal-title">修改结算结果 · #{record.id}</h2></div>
        <form onSubmit={event => {
          event.preventDefault()
          if (saving || unchanged || !allowed) return
          onSave({ status, expected_revision: record.revision, reject_reason: status === 'rejected' ? rejectReason.trim() : '', remark: remark.trim() })
        }}>
          <div className="modal-body space-y-4">
            {error && <p role="alert" className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">{error}</p>}
            <p className="text-sm text-slate-600 dark:text-slate-300">提现金额：<span className="font-medium tabular-nums">¥{record.amount}</span> · 当前结果：{record.status_label}</p>
            <label className="input-group"><span className="input-label">结算结果</span>
              <select className="input-ios" value={status} disabled={saving} onChange={event => setStatus(event.target.value)}>
                {!options.some(option => option.value === status) && <option value={status} disabled>{record.status_label}</option>}
                {options.map(option => <option key={option.value} value={option.value} disabled={!option.enabled}>{option.label}</option>)}
              </select>
            </label>
            {status === 'rejected' && <label className="input-group"><span className="input-label">拒绝原因</span>
              <textarea className="input-ios resize-y" rows={3} required maxLength={512} value={rejectReason} disabled={saving} onChange={event => setRejectReason(event.target.value)} placeholder="请填写拒绝原因" />
            </label>}
            <label className="input-group"><span className="input-label">修改说明（选填）</span>
              <textarea className="input-ios resize-y" rows={3} maxLength={500} value={remark} disabled={saving} onChange={event => setRemark(event.target.value)} placeholder="说明会追加保存到记录备注中" />
            </label>
            <p className="text-xs text-slate-500 dark:text-slate-400">此操作修改结算结果。标记已打款前请确认实际付款；修改结果不会自动付款、扣款或退还余额。</p>
          </div>
          <div className="modal-footer">
            <button type="button" className="btn-ios-secondary" disabled={saving} onClick={onClose}>关闭</button>
            <button type="submit" className="btn-ios-primary" disabled={saving || unchanged || !allowed || (status === 'rejected' && !rejectReason.trim())}>
              {saving && <Loader2 className="h-4 w-4 animate-spin" />}{saving ? '保存中…' : '保存结果'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
