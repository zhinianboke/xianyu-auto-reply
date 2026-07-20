import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { Loader2, X } from 'lucide-react'
import { Loading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/request'
import type { Account, MessageFilter, MessageFilterType } from '@/types'

export type MessageFilterFormMode = 'create' | 'batch' | 'edit'

export interface MessageFilterFormValues {
  accountId?: string
  accountIds?: string[]
  keyword: string
  filterTypes: MessageFilterType[]
}

interface MessageFilterFormModalProps {
  mode: MessageFilterFormMode
  accounts: Account[]
  selectedAccount: string
  initialFilter?: MessageFilter | null
  filterTypeOptions: Array<{ value: MessageFilterType; label: string }>
  onClose: () => void
  onSubmit: (values: MessageFilterFormValues) => Promise<{ success: boolean; message?: string }>
}

const getAccountRemark = (account: Account) => account.note?.trim() || account.remark?.trim() || '-'

const getAccountDisplayText = (account: Account) => {
  const remark = getAccountRemark(account)
  return remark === '-' ? account.id : `${account.id} (${remark})`
}

export function MessageFilterFormModal({
  mode,
  accounts,
  selectedAccount,
  initialFilter,
  filterTypeOptions,
  onClose,
  onSubmit,
}: MessageFilterFormModalProps) {
  const { addToast } = useUIStore()
  const [keyword, setKeyword] = useState('')
  const [selectedFilterTypes, setSelectedFilterTypes] = useState<MessageFilterType[]>([])
  const [singleFilterType, setSingleFilterType] = useState<MessageFilterType | ''>('')
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([])
  const [saving, setSaving] = useState(false)

  const isEditMode = mode === 'edit'
  const isBatchMode = mode === 'batch'
  const fallbackErrorMessage = isEditMode ? '保存过滤规则失败' : isBatchMode ? '批量维护过滤规则失败' : '创建过滤规则失败'
  const successMessage = isEditMode ? '更新成功' : isBatchMode ? '批量维护成功' : '创建成功'
  const loadingText = isEditMode ? '正在保存过滤规则...' : isBatchMode ? '正在批量保存过滤规则...' : '正在创建过滤规则...'
  const modalTitle = isEditMode ? '编辑过滤规则' : isBatchMode ? '批量维护过滤规则' : '新建过滤规则'
  const submitText = isEditMode ? '保存修改' : isBatchMode ? '批量保存' : '保存'

  const selectedAccountText = useMemo(() => {
    if (initialFilter) {
      return initialFilter.account_id
    }
    const matchedAccount = accounts.find((account) => account.id === selectedAccount)
    if (matchedAccount) {
      return getAccountDisplayText(matchedAccount)
    }
    return selectedAccount || '-'
  }, [accounts, initialFilter, selectedAccount])

  useEffect(() => {
    setKeyword(initialFilter?.keyword || '')
    setSingleFilterType(initialFilter?.filter_type || '')
    setSelectedFilterTypes([])
    setSelectedAccountIds([])
  }, [initialFilter, mode, selectedAccount])

  const toggleFilterType = (filterType: MessageFilterType) => {
    setSelectedFilterTypes((prev) => (
      prev.includes(filterType)
        ? prev.filter((item) => item !== filterType)
        : [...prev, filterType]
    ))
  }

  const toggleAccount = (accountId: string) => {
    setSelectedAccountIds((prev) => (
      prev.includes(accountId)
        ? prev.filter((item) => item !== accountId)
        : [...prev, accountId]
    ))
  }

  const allAccountsSelected = accounts.length > 0 && selectedAccountIds.length === accounts.length
  const batchCombinationCount = selectedAccountIds.length * selectedFilterTypes.length

  const toggleSelectAllAccounts = () => {
    setSelectedAccountIds(allAccountsSelected ? [] : accounts.map((account) => account.id))
  }

  const handleSubmit = async (event: FormEvent) => {
    event.preventDefault()
    const normalizedKeyword = keyword.trim()
    if (!normalizedKeyword) {
      addToast({ type: 'warning', message: '请输入过滤关键词' })
      return
    }
    if (isBatchMode && selectedAccountIds.length === 0) {
      addToast({ type: 'warning', message: '请至少选择一个账号' })
      return
    }
    if (isEditMode) {
      if (!singleFilterType) {
        addToast({ type: 'warning', message: '请选择过滤类型' })
        return
      }
    } else if (selectedFilterTypes.length === 0) {
      addToast({ type: 'warning', message: '请选择至少一种过滤类型' })
      return
    }

    setSaving(true)
    try {
      const result = await onSubmit({
        accountId: selectedAccount,
        accountIds: isBatchMode ? selectedAccountIds : undefined,
        keyword: normalizedKeyword,
        filterTypes: isEditMode ? [singleFilterType as MessageFilterType] : selectedFilterTypes,
      })
      if (!result.success) {
        addToast({ type: 'error', message: result.message || fallbackErrorMessage })
        return
      }
      addToast({ type: 'success', message: result.message || successMessage })
      onClose()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, fallbackErrorMessage) })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay">
      {saving && <Loading fullScreen text={loadingText} />}
      <div className="modal-content max-w-3xl">
        <div className="modal-header flex items-center justify-between">
          <h2 className="text-lg font-semibold">{modalTitle}</h2>
          <button
            type="button"
            onClick={onClose}
            disabled={saving}
            className="p-1 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors disabled:opacity-50"
          >
            <X className="w-5 h-5 text-slate-500" />
          </button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="modal-body space-y-4">
            {isBatchMode ? (
              <div className="space-y-3">
                <div className="flex items-center justify-between gap-3">
                  <label className="input-label">选择账号</label>
                  <button
                    type="button"
                    onClick={toggleSelectAllAccounts}
                    className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    {allAccountsSelected ? '取消全选' : '全选'}
                  </button>
                </div>
                <div className="rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
                  <div className="grid grid-cols-[56px_minmax(0,1fr)_minmax(0,1fr)] bg-slate-50 dark:bg-slate-800/80 px-4 py-3 text-sm font-medium text-slate-600 dark:text-slate-300">
                    <span>选择</span>
                    <span>账号</span>
                    <span>备注</span>
                  </div>
                  <div className="max-h-64 overflow-y-auto divide-y divide-slate-200 dark:divide-slate-700">
                    {accounts.length === 0 ? (
                      <div className="px-4 py-8 text-center text-sm text-slate-500 dark:text-slate-400">暂无可选账号</div>
                    ) : accounts.map((account) => (
                      <label
                        key={account.pk?.toString() || account.id}
                        className="grid grid-cols-[56px_minmax(0,1fr)_minmax(0,1fr)] items-start gap-3 px-4 py-3 cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/60"
                      >
                        <input
                          type="checkbox"
                          checked={selectedAccountIds.includes(account.id)}
                          onChange={() => toggleAccount(account.id)}
                          className="mt-1 w-4 h-4 rounded border-gray-300"
                        />
                        <span className="text-sm font-medium text-slate-700 dark:text-slate-200 break-all">{account.id}</span>
                        <span className="text-sm text-slate-500 dark:text-slate-400 break-all">{getAccountRemark(account)}</span>
                      </label>
                    ))}
                  </div>
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  已选择 {selectedAccountIds.length} 个账号、{selectedFilterTypes.length} 种过滤类型，预计生成 {batchCombinationCount} 条规则。
                </p>
              </div>
            ) : (
              <div>
                <label className="input-label">所属账号</label>
                <input
                  type="text"
                  value={selectedAccountText}
                  disabled
                  className="input-ios bg-slate-100 dark:bg-slate-700 cursor-not-allowed"
                />
              </div>
            )}
            <div>
              <label className="input-label">过滤关键词</label>
              <input
                type="text"
                value={keyword}
                onChange={(event) => setKeyword(event.target.value)}
                className="input-ios"
                placeholder="请输入要过滤的关键词"
              />
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">当消息包含此关键词时，将触发过滤规则</p>
            </div>
            <div>
              <label className="input-label">过滤类型</label>
              {isEditMode ? (
                <select
                  value={singleFilterType}
                  onChange={(event) => setSingleFilterType(event.target.value as MessageFilterType | '')}
                  className="input-ios"
                >
                  <option value="">请选择过滤类型</option>
                  {filterTypeOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="space-y-2">
                  {filterTypeOptions.map((option) => (
                    <label
                      key={option.value}
                      className="flex items-center gap-3 p-3 border border-gray-200 dark:border-gray-700 rounded-lg cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-800"
                    >
                      <input
                        type="checkbox"
                        checked={selectedFilterTypes.includes(option.value)}
                        onChange={() => toggleFilterType(option.value)}
                        className="w-4 h-4 rounded border-gray-300"
                      />
                      <span className="text-sm text-gray-700 dark:text-gray-300">{option.label}</span>
                    </label>
                  ))}
                  <p className="text-xs text-slate-500 dark:text-slate-400">可多选，每种类型会生成一条独立的规则</p>
                </div>
              )}
              <div className="mt-3 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm text-blue-600 dark:text-blue-400">
                <strong>过滤类型说明：</strong>
                <ul className="list-disc list-inside mt-1 space-y-1">
                  <li><strong>跳过自动回复</strong>：匹配到关键词时，不触发自动回复（关键词回复、默认回复、AI回复都不会触发）</li>
                  <li><strong>跳过消息通知</strong>：匹配到关键词时，不发送消息通知到配置的通知渠道</li>
                  <li><strong>AI回复黑名单</strong>：AI生成的回复包含关键词时，直接拦截不发送给买家</li>
                </ul>
              </div>
            </div>
          </div>
          <div className="modal-footer">
            <button type="button" onClick={onClose} disabled={saving} className="btn-ios-secondary">取消</button>
            <button type="submit" disabled={saving} className="btn-ios-primary">
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              {submitText}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
