/**
 * 商品监控 - 下单账号（用户级兜底下单账号配置）页面
 *
 * 功能：
 * 1. 配置当前用户的兜底下单账号（多选，支持全选/清空）
 * 2. 当定时下单任务发现监控任务自身无可用下单账号（任务删除/禁用/未配置/账号失效）时，
 *    回退使用此处配置的账号下单；兜底也找不到才算下单失败
 * 3. 用户级配置：每个用户仅一条数据
 */
import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, Check, CheckCircle2, ChevronDown, Loader2, Save, Users } from 'lucide-react'
import {
  getOrderFallbackAccounts,
  saveOrderFallbackAccounts,
  type OrderFallbackAccountStatus,
} from '@/api/orderFallbackAccount'
import { getAccountDetails } from '@/api/accounts'
import { PageLoading, Loading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

interface AccountOption {
  value: string
  label: string
  enabled: boolean
}

export function OrderFallbackAccount() {
  const { addToast } = useUIStore()

  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [accountOptions, setAccountOptions] = useState<AccountOption[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [accountStatus, setAccountStatus] = useState<OrderFallbackAccountStatus[]>([])
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [updatedAt, setUpdatedAt] = useState<string | null>(null)

  // 兜底下单账号仅取启用账号
  const enabledAccountOptions = useMemo(
    () => accountOptions.filter((o) => o.enabled),
    [accountOptions]
  )

  const selectedLabels = useMemo(() => {
    if (selectedIds.length === 0) return ''
    const labelMap = new Map(accountOptions.map((opt) => [opt.value, opt.label]))
    return selectedIds.map((id) => labelMap.get(id) || id).join('，')
  }, [selectedIds, accountOptions])

  const loadData = async () => {
    try {
      // 账号选项与当前配置并行加载
      const [details, configResult] = await Promise.all([
        getAccountDetails(),
        getOrderFallbackAccounts(),
      ])
      setAccountOptions(
        details.map((item) => ({
          value: item.id,
          label: item.note ? `${item.note}（${item.id}）` : item.id,
          enabled: Boolean(item.enabled),
        }))
      )
      if (configResult.success && configResult.data) {
        setSelectedIds(configResult.data.account_ids || [])
        setAccountStatus(configResult.data.accounts || [])
        setUpdatedAt(configResult.data.updated_at || null)
      } else {
        addToast({ type: 'error', message: configResult.message || '加载兜底下单账号配置失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载兜底下单账号配置失败') })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const toggleAccount = (accountId: string) => {
    setSelectedIds((prev) =>
      prev.includes(accountId) ? prev.filter((id) => id !== accountId) : [...prev, accountId]
    )
  }

  const handleSelectAll = () => {
    setSelectedIds(enabledAccountOptions.map((opt) => opt.value))
  }

  const handleClear = () => {
    setSelectedIds([])
  }

  const handleSave = async () => {
    try {
      setSaving(true)
      const result = await saveOrderFallbackAccounts(selectedIds)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '保存失败' })
        return
      }
      addToast({ type: 'success', message: result.message || '兜底下单账号保存成功' })
      if (result.data) {
        setSelectedIds(result.data.account_ids || [])
        setAccountStatus(result.data.accounts || [])
        setUpdatedAt(result.data.updated_at || null)
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '保存兜底下单账号失败') })
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {saving && <Loading fullScreen text="正在保存兜底下单账号..." />}

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">下单账号</h1>
          <p className="page-description">
            配置用户级兜底下单账号。当监控任务自身的下单账号不可用（任务被删除、禁用、未配置或账号失效）时，
            定时下单任务会回退使用这里配置的账号下单；兜底账号也不可用才算下单失败。
          </p>
        </div>
      </div>

      <div className="vben-card">
        <div className="vben-card-header flex items-center justify-between">
          <h2 className="vben-card-title">
            <Users className="w-4 h-4" />
            兜底下单账号
          </h2>
          {updatedAt && (
            <span className="text-xs text-slate-400">
              最近更新：{new Date(updatedAt).toLocaleString('zh-CN')}
            </span>
          )}
        </div>

        <div className="vben-card-body space-y-4">
          <div className="input-group max-w-2xl">
            <div className="flex items-center justify-between">
              <label className="input-label mb-0">
                兜底下单账号（可多选）
                <span className="text-xs text-slate-400 ml-1">（仅启用账号，留空表示不配置兜底）</span>
              </label>
              {selectedIds.length > 0 && (
                <button
                  type="button"
                  onClick={handleClear}
                  className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                >
                  清空选中（{selectedIds.length}）
                </button>
              )}
            </div>
            <button
              type="button"
              onClick={() => setDropdownOpen((prev) => !prev)}
              className="mt-1 w-full flex items-center justify-between gap-2 px-3 py-2 rounded-md text-sm text-left bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 hover:border-blue-400 dark:hover:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              <span className={selectedLabels ? 'truncate text-slate-900 dark:text-slate-100' : 'truncate text-slate-400'}>
                {selectedLabels || '请选择兜底下单账号'}
              </span>
              <ChevronDown className={`w-4 h-4 text-slate-400 flex-shrink-0 transition-transform duration-200 ${dropdownOpen ? 'rotate-180' : ''}`} />
            </button>

            {dropdownOpen && (
              <div className="mt-1 border border-slate-200 dark:border-slate-700 rounded-md bg-white dark:bg-slate-800">
                <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200 dark:border-slate-700">
                  <span className="text-xs text-slate-500 dark:text-slate-400">共 {enabledAccountOptions.length} 个启用账号</span>
                  <div className="flex items-center gap-3">
                    <button type="button" onClick={handleSelectAll} className="text-xs text-blue-600 dark:text-blue-400 hover:underline" disabled={enabledAccountOptions.length === 0}>全选</button>
                    <button type="button" onClick={handleClear} className="text-xs text-slate-500 dark:text-slate-400 hover:underline" disabled={selectedIds.length === 0}>清空</button>
                  </div>
                </div>
                <div className="max-h-60 overflow-auto">
                  {enabledAccountOptions.length === 0 ? (
                    <div className="px-3 py-2 text-sm text-slate-400 text-center">暂无启用账号</div>
                  ) : (
                    enabledAccountOptions.map((option) => {
                      const checked = selectedIds.includes(option.value)
                      return (
                        <button
                          key={option.value}
                          type="button"
                          onClick={() => toggleAccount(option.value)}
                          className={`w-full flex items-center justify-between gap-2 px-3 py-2 text-sm text-left transition-colors duration-100 text-slate-700 dark:text-slate-200 hover:bg-blue-50 dark:hover:bg-slate-700 ${checked ? 'bg-blue-50 dark:bg-slate-700 text-blue-600 dark:text-blue-400' : ''}`}
                        >
                          <span className="truncate">{option.label}</span>
                          {checked && <Check className="w-4 h-4 text-blue-500 flex-shrink-0" />}
                        </button>
                      )
                    })
                  )}
                </div>
              </div>
            )}
            {selectedIds.length > 0 && (
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">已选择 {selectedIds.length} 个账号</p>
            )}
          </div>

          {/* 已配置账号的有效性提示 */}
          {accountStatus.length > 0 && (
            <div className="max-w-2xl">
              <p className="text-sm font-medium text-slate-700 dark:text-slate-200 mb-2">当前已保存账号状态</p>
              <div className="flex flex-col gap-1.5">
                {accountStatus.map((acc) => (
                  <div key={acc.account_id} className="flex items-center gap-2 text-sm">
                    {acc.valid ? (
                      <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0" />
                    ) : (
                      <AlertCircle className="w-4 h-4 text-orange-500 flex-shrink-0" />
                    )}
                    <span className="text-slate-700 dark:text-slate-200">{acc.account_id}</span>
                    {acc.valid ? (
                      <span className="text-xs text-green-600 dark:text-green-400">可用</span>
                    ) : (
                      <span className="text-xs text-orange-600 dark:text-orange-400">{acc.reason || '不可用'}</span>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          <div>
            <button className="btn-ios-primary" onClick={handleSave} disabled={saving}>
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              保存
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

export default OrderFallbackAccount
