import { useMemo, useState } from 'react'
import { Loader2, X } from 'lucide-react'
import { rechargeUser } from '@/api/admin'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/request'
import type { User } from '@/types'

interface Props {
  user: User
  onClose: () => void
  onSuccess: () => void
}

/**
 * 管理员余额调整弹窗
 *
 * 金额支持正负：正数为充值，负数为扣减。展示当前余额与调整后预估余额
 * （预估值按 当前余额 + 输入金额 实时计算，仅供参考，最终以后端返回为准）。
 */
export function UserRechargeModal({ user, onClose, onSuccess }: Props) {
  const { addToast } = useUIStore()
  const [amount, setAmount] = useState('')
  const [remark, setRemark] = useState('')
  const [saving, setSaving] = useState(false)

  const currentBalance = useMemo(() => {
    const val = Number(user.balance ?? '0')
    return Number.isFinite(val) ? val : 0
  }, [user.balance])

  const parsedAmount = useMemo(() => {
    const trimmed = amount.trim()
    if (trimmed === '' || trimmed === '-') return null
    const val = Number(trimmed)
    return Number.isFinite(val) ? val : null
  }, [amount])

  const estimatedBalance = useMemo(() => {
    if (parsedAmount === null) return null
    return currentBalance + parsedAmount
  }, [currentBalance, parsedAmount])

  const handleSave = async () => {
    const trimmed = amount.trim()
    if (trimmed === '' || trimmed === '-') {
      addToast({ type: 'warning', message: '请输入调整金额' })
      return
    }
    const val = Number(trimmed)
    if (!Number.isFinite(val)) {
      addToast({ type: 'warning', message: '请输入正确的金额' })
      return
    }
    if (val === 0) {
      addToast({ type: 'warning', message: '调整金额不能为0' })
      return
    }
    if (Math.abs(val) > 10000) {
      addToast({ type: 'warning', message: '单次调整金额不能超过10000元' })
      return
    }
    if (estimatedBalance !== null && estimatedBalance < 0) {
      addToast({ type: 'warning', message: `当前余额 ¥${currentBalance.toFixed(2)}，扣减后将为负，操作被拒绝` })
      return
    }

    setSaving(true)
    try {
      const result = await rechargeUser(user.user_id, { amount: trimmed, remark: remark.trim() })
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '余额调整失败' })
        return
      }
      addToast({ type: 'success', message: result.message || '余额调整成功' })
      onSuccess()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '余额调整失败') })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content max-w-md">
        <div className="modal-header">
          <h2 className="modal-title">余额调整</h2>
          <button className="modal-close" onClick={onClose} disabled={saving}>
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="modal-body">
          <div className="space-y-4">
            <div className="input-group">
              <label className="input-label">目标用户</label>
              <input className="input-ios" value={user.username} disabled readOnly />
            </div>
            <div className="flex items-center justify-between rounded-lg bg-slate-50 dark:bg-slate-700/40 px-4 py-3">
              <span className="text-sm text-slate-500 dark:text-slate-400">当前余额</span>
              <span className="font-medium text-slate-700 dark:text-slate-200 tabular-nums">¥{currentBalance.toFixed(2)}</span>
            </div>
            <div className="input-group">
              <label className="input-label">调整金额 <span className="text-red-500">*</span></label>
              <input
                className="input-ios"
                type="number"
                step="0.01"
                value={amount}
                onChange={(event) => setAmount(event.target.value)}
                placeholder="正数为充值，负数为扣减，如 10.00 或 -5.00"
              />
            </div>
            <div className="flex items-center justify-between rounded-lg bg-blue-50 dark:bg-blue-900/20 px-4 py-3">
              <span className="text-sm text-slate-500 dark:text-slate-400">调整后余额（预估）</span>
              <span className={`font-medium tabular-nums ${estimatedBalance !== null && estimatedBalance < 0 ? 'text-red-500' : 'text-blue-600 dark:text-blue-400'}`}>
                {estimatedBalance === null ? '—' : `¥${estimatedBalance.toFixed(2)}`}
              </span>
            </div>
            <div className="input-group">
              <label className="input-label">备注</label>
              <input
                className="input-ios"
                value={remark}
                onChange={(event) => setRemark(event.target.value)}
                placeholder="可选，记录本次调整原因"
                maxLength={200}
              />
            </div>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-ios-secondary" onClick={onClose} disabled={saving}>取消</button>
          <button className="btn-ios-primary" onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            确定
          </button>
        </div>
      </div>
    </div>
  )
}

export default UserRechargeModal
