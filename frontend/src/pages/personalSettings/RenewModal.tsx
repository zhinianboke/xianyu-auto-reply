/**
 * 账户续期弹窗组件
 *
 * 功能：
 * 1. 选择续期月数
 * 2. 根据系统设置的续期单价计算总价
 * 3. 确认后扣减余额并延长到期日
 */
import { useMemo, useState } from 'react'
import { X, Loader2, CalendarClock } from 'lucide-react'
import { renewMembership } from '@/api/settings'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/request'

interface RenewModalProps {
  visible: boolean
  /** 续期单价（元/月），空字符串表示未配置 */
  unitPrice: string
  /** 当前余额（元），用于校验是否足够 */
  balance: string
  onClose: () => void
  /** 续期成功回调，传回新的到期日 ISO 字符串（可能为 null） */
  onSuccess: (expireAt: string | null) => void
}

// 续期月数快捷选项
const MONTH_OPTIONS = [1, 3, 6, 12]

export function RenewModal({ visible, unitPrice, balance, onClose, onSuccess }: RenewModalProps) {
  const { addToast } = useUIStore()
  const [months, setMonths] = useState(1)
  const [submitting, setSubmitting] = useState(false)

  // 解析续期单价：非法或非正数视为未配置
  const parsedUnitPrice = useMemo(() => {
    const val = Number(String(unitPrice ?? '').trim())
    return Number.isFinite(val) && val > 0 ? val : null
  }, [unitPrice])

  // 当前余额数值
  const currentBalance = useMemo(() => {
    const val = Number(String(balance ?? '0').trim())
    return Number.isFinite(val) ? val : 0
  }, [balance])

  // 续期总价
  const totalPrice = useMemo(() => {
    if (parsedUnitPrice === null) return null
    return parsedUnitPrice * months
  }, [parsedUnitPrice, months])

  // 余额是否不足
  const insufficient = useMemo(() => {
    if (totalPrice === null) return false
    return currentBalance < totalPrice
  }, [currentBalance, totalPrice])

  const handleConfirm = async () => {
    if (submitting) return
    if (parsedUnitPrice === null) {
      addToast({ type: 'warning', message: '续期功能未开放，请联系管理员配置续期单价' })
      return
    }
    if (!Number.isInteger(months) || months <= 0) {
      addToast({ type: 'warning', message: '请选择正确的续期月数' })
      return
    }
    if (months > 120) {
      addToast({ type: 'warning', message: '单次续期不能超过120个月' })
      return
    }
    if (insufficient) {
      addToast({ type: 'warning', message: `余额不足，本次续期需 ¥${totalPrice!.toFixed(2)}，当前余额 ¥${currentBalance.toFixed(2)}` })
      return
    }

    setSubmitting(true)
    try {
      const result = await renewMembership(months)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '续期失败' })
        return
      }
      addToast({ type: 'success', message: result.message || '续期成功' })
      onSuccess(result.data?.expire_at ?? null)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '续期失败') })
    } finally {
      setSubmitting(false)
    }
  }

  if (!visible) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-slate-800 rounded-xl p-6 w-full max-w-md mx-4 shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 flex items-center gap-2">
            <CalendarClock className="w-5 h-5 text-blue-500" />
            账户续期
          </h3>
          <button
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {parsedUnitPrice === null ? (
          <div className="py-6 text-center text-sm text-slate-500 dark:text-slate-400">
            续期功能未开放，请联系管理员配置续期单价。
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex items-center justify-between text-sm">
              <span className="text-slate-500 dark:text-slate-400">续期单价</span>
              <span className="font-medium text-slate-900 dark:text-slate-100">
                ¥{parsedUnitPrice.toFixed(2)} / 月
              </span>
            </div>

            <div className="input-group">
              <label className="input-label">续期月数</label>
              <div className="flex flex-wrap gap-2">
                {MONTH_OPTIONS.map((m) => (
                  <button
                    key={m}
                    onClick={() => setMonths(m)}
                    className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      months === m
                        ? 'bg-blue-500 text-white'
                        : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600'
                    }`}
                  >
                    {m} 个月
                  </button>
                ))}
              </div>
            </div>

            <div className="input-group">
              <label className="input-label">自定义月数（1~120）</label>
              <input
                type="number"
                min={1}
                max={120}
                value={months}
                onChange={(e) => {
                  const val = parseInt(e.target.value, 10)
                  if (Number.isNaN(val)) {
                    setMonths(1)
                  } else {
                    setMonths(Math.min(120, Math.max(1, val)))
                  }
                }}
                className="input-ios"
              />
            </div>

            <div className="rounded-lg bg-slate-50 dark:bg-slate-700/50 p-3 space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-slate-500 dark:text-slate-400">当前余额</span>
                <span className="font-medium text-slate-900 dark:text-slate-100">
                  ¥{currentBalance.toFixed(2)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-500 dark:text-slate-400">续期总价</span>
                <span className="font-bold text-amber-600 dark:text-amber-400">
                  ¥{totalPrice!.toFixed(2)}
                </span>
              </div>
              {insufficient && (
                <div className="text-xs text-red-500">
                  余额不足，请先充值后再续期。
                </div>
              )}
            </div>

            <button
              onClick={handleConfirm}
              disabled={submitting || insufficient}
              className="btn-ios-primary w-full"
            >
              {submitting ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  续期中...
                </>
              ) : (
                '确认续期'
              )}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
