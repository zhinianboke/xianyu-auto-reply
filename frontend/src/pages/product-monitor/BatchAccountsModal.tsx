/**
 * 批量修改监控任务账号弹窗
 *
 * 功能：
 * 1. 对勾选的多个监控任务，批量设置"采集账号"或"下单账号"
 * 2. 账号多选，确认后调用后端批量修改接口
 * 3. 允许清空（采集账号→回退兜底；下单账号→不下单），清空时二次确认
 * 说明：弹窗只能通过按钮关闭（不点击遮罩关闭）。
 */
import { useEffect, useMemo, useState } from 'react'
import { Check, ChevronDown, Loader2, X } from 'lucide-react'
import { batchUpdateListingMonitorAccounts } from '@/api/listingMonitor'
import { getAccountDetails } from '@/api/accounts'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

interface AccountOption {
  value: string
  label: string
  enabled: boolean
}

export type BatchAccountField = 'account_ids' | 'order_account_ids'

interface BatchAccountsModalProps {
  field: BatchAccountField
  taskIds: number[]
  onClose: () => void
  onSaved: () => void
}

const FIELD_LABELS: Record<BatchAccountField, string> = {
  account_ids: '采集账号',
  order_account_ids: '下单账号',
}

export function BatchAccountsModal({ field, taskIds, onClose, onSaved }: BatchAccountsModalProps) {
  const { addToast } = useUIStore()
  const label = FIELD_LABELS[field]

  const [accountOptions, setAccountOptions] = useState<AccountOption[]>([])
  const [accountLoading, setAccountLoading] = useState(false)
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [saving, setSaving] = useState(false)
  const [showClearConfirm, setShowClearConfirm] = useState(false)

  useEffect(() => {
    const loadAccounts = async () => {
      try {
        setAccountLoading(true)
        const details = await getAccountDetails()
        setAccountOptions(
          details.map((item) => ({
            value: item.id,
            label: item.note ? `${item.note}（${item.id}）` : item.id,
            enabled: Boolean(item.enabled),
          }))
        )
      } catch (error) {
        addToast({ type: 'error', message: getApiErrorMessage(error, '加载账号列表失败') })
      } finally {
        setAccountLoading(false)
      }
    }
    void loadAccounts()
  }, [addToast])

  // 下单账号仅可选启用账号；监控账号可选全部账号
  const visibleOptions = useMemo(
    () => (field === 'order_account_ids' ? accountOptions.filter((o) => o.enabled) : accountOptions),
    [accountOptions, field]
  )

  const selectedLabels = useMemo(() => {
    if (selectedIds.length === 0) return ''
    const labelMap = new Map(accountOptions.map((opt) => [opt.value, opt.label]))
    return selectedIds.map((id) => labelMap.get(id) || id).join('，')
  }, [selectedIds, accountOptions])

  const toggleAccount = (accountId: string) => {
    setSelectedIds((prev) =>
      prev.includes(accountId) ? prev.filter((id) => id !== accountId) : [...prev, accountId]
    )
  }

  const handleSelectAll = () => {
    setSelectedIds(visibleOptions.map((opt) => opt.value))
  }

  const handleClearAll = () => {
    setSelectedIds([])
  }

  const handleSave = async () => {
    // 未选任何账号：弹确认对话框，确认后清空该字段配置
    if (selectedIds.length === 0) {
      setShowClearConfirm(true)
      return
    }
    await doSave()
  }

  const doSave = async () => {
    setSaving(true)
    try {
      const result = await batchUpdateListingMonitorAccounts(taskIds, field, selectedIds)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || `批量修改${label}失败` })
        return
      }
      addToast({ type: 'success', message: result.message || `批量修改${label}成功` })
      onSaved()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, `批量修改${label}失败`) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <ConfirmModal
        isOpen={showClearConfirm}
        title="确认清空"
        message={
          field === 'account_ids'
            ? `确定将 ${taskIds.length} 条监控任务的采集账号清空吗？清空后将按分类兜底链回退使用兜底采集账号（本分类→无分类→管理员）。`
            : `确定将 ${taskIds.length} 条监控任务的下单账号清空吗？清空后这些任务将不再自动下单。`
        }
        onCancel={() => setShowClearConfirm(false)}
        onConfirm={() => {
          setShowClearConfirm(false)
          void doSave()
        }}
      />

      <div className="w-full max-w-lg bg-white dark:bg-slate-800 rounded-2xl shadow-xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 dark:border-slate-700">
          <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">
            批量修改{label}
          </h3>
          <button
            onClick={onClose}
            disabled={saving}
            className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500 disabled:opacity-50"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            已选中 <span className="font-semibold text-blue-600 dark:text-blue-400">{taskIds.length}</span> 条监控任务，
            将统一把它们的{label}修改为下方所选账号。
          </p>

          <div className="input-group">
            <label className="input-label">{label}（多选）</label>
            <div className="relative">
              <button
                type="button"
                onClick={() => setDropdownOpen((v) => !v)}
                className="input-ios w-full flex items-center justify-between text-left"
              >
                <span className={`truncate ${selectedLabels ? '' : 'text-slate-400'}`}>
                  {accountLoading ? '加载账号中...' : selectedLabels || `请选择${label}`}
                </span>
                <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
              </button>

              {dropdownOpen && (
                <div className="absolute z-10 mt-1 w-full rounded-lg border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 shadow-lg">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200 dark:border-slate-700">
                    <span className="text-xs text-slate-500 dark:text-slate-400">共 {visibleOptions.length} 个账号</span>
                    <div className="flex items-center gap-3">
                      <button
                        type="button"
                        onClick={handleSelectAll}
                        className="text-xs text-blue-600 dark:text-blue-400 hover:underline disabled:opacity-50"
                        disabled={visibleOptions.length === 0}
                      >
                        全选
                      </button>
                      <button
                        type="button"
                        onClick={handleClearAll}
                        className="text-xs text-slate-500 dark:text-slate-400 hover:underline disabled:opacity-50"
                        disabled={selectedIds.length === 0}
                      >
                        取消全选
                      </button>
                    </div>
                  </div>
                  <div className="max-h-60 overflow-auto">
                    {visibleOptions.length === 0 ? (
                      <div className="px-3 py-3 text-sm text-slate-400 text-center">
                        {accountLoading ? '正在加载...' : '暂无可选账号'}
                      </div>
                    ) : (
                      visibleOptions.map((opt) => {
                        const checked = selectedIds.includes(opt.value)
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            onClick={() => toggleAccount(opt.value)}
                            className="w-full flex items-center justify-between px-3 py-2 text-sm hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200"
                          >
                            <span className="truncate flex items-center gap-2">
                              {opt.label}
                              {!opt.enabled && (
                                <span className="text-xs text-slate-400">(已停用)</span>
                              )}
                            </span>
                            {checked && <Check className="w-4 h-4 text-blue-600 dark:text-blue-400 shrink-0" />}
                          </button>
                        )
                      })
                    )}
                  </div>
                </div>
              )}
            </div>
            {field === 'order_account_ids' && (
              <p className="mt-1 text-xs text-slate-400">下单账号仅可选择启用状态的账号（私信与下单共用）。</p>
            )}
          </div>
        </div>

        <div className="flex justify-end gap-3 px-5 py-4 border-t border-slate-200 dark:border-slate-700">
          <button onClick={onClose} disabled={saving} className="btn-ios-secondary">
            取消
          </button>
          <button onClick={() => void handleSave()} disabled={saving} className="btn-ios-primary">
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            确认修改
          </button>
        </div>
      </div>
    </div>
  )
}

export default BatchAccountsModal
