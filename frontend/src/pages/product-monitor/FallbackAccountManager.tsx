/**
 * 兜底账号配置管理（按分类）通用组件
 *
 * 供「下单账号」「采集账号」两个页面复用：
 * 1. 列出当前用户已配置的兜底账号（按分类，含无分类那条）
 * 2. 新建配置：选择分类（或无分类）+ 多选账号（每个分类仅一条、无分类仅一条）
 * 3. 修改/删除已配置项
 *
 * 说明：弹窗只能通过按钮关闭（不点击遮罩关闭）。
 */
import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, Check, CheckCircle2, ChevronDown, Loader2, Pencil, Plus, RefreshCw, Trash2, Users, X } from 'lucide-react'
import { getAccountDetails } from '@/api/accounts'
import { getListingMonitorCategories } from '@/api/listingMonitorCategory'
import { Select } from '@/components/common/Select'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { PageLoading, Loading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { getApiErrorMessage } from '@/utils/apiError'
import type { ApiResponse } from '@/types'

export interface FallbackAccountStatus {
  account_id: string
  valid: boolean
  reason?: string | null
}

export interface FallbackConfig {
  id: number | null
  owner_id?: number | null
  owner_username?: string | null
  category_id: number | null
  category_name?: string | null
  account_ids: string[]
  accounts: FallbackAccountStatus[]
  created_at?: string | null
  updated_at?: string | null
}

interface FallbackAccountManagerProps {
  title: string
  description: string
  /** 账号类别中文，如"采集""下单" */
  accountKind: string
  list: () => Promise<ApiResponse<FallbackConfig[]>>
  /** 保存配置；ownerId 仅管理员编辑其他用户配置时传入 */
  save: (categoryId: number | null, accountIds: string[], ownerId?: number | null) => Promise<ApiResponse<FallbackConfig>>
  /** 删除配置；ownerId 仅管理员删除其他用户配置时传入 */
  remove: (categoryId: number | null, ownerId?: number | null) => Promise<ApiResponse<null>>
}

interface AccountOption {
  value: string
  label: string
  enabled: boolean
}

const NONE_VALUE = '__none__'

export function FallbackAccountManager({
  title,
  description,
  accountKind,
  list,
  save,
  remove,
}: FallbackAccountManagerProps) {
  const { addToast } = useUIStore()
  const { user } = useAuthStore()
  // 管理员可查看/编辑/删除全部用户的兜底配置，需展示所属用户列
  const isAdmin = Boolean(user?.is_admin)
  const currentUserId = user?.user_id

  const [loading, setLoading] = useState(true)
  const [tableLoading, setTableLoading] = useState(false)
  const [configs, setConfigs] = useState<FallbackConfig[]>([])
  const [categories, setCategories] = useState<{ id: number; name: string }[]>([])
  const [accountOptions, setAccountOptions] = useState<AccountOption[]>([])

  // 新建/编辑弹窗
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<FallbackConfig | null>(null)
  const [formCategory, setFormCategory] = useState('') // '' 未选 / NONE_VALUE 无分类 / 数字字符串
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const [saving, setSaving] = useState(false)

  // 删除确认
  const [deleteTarget, setDeleteTarget] = useState<FallbackConfig | null>(null)
  const [deleting, setDeleting] = useState(false)

  const enabledAccountOptions = useMemo(() => accountOptions.filter((o) => o.enabled), [accountOptions])
  const accountLabelMap = useMemo(
    () => new Map(accountOptions.map((opt) => [opt.value, opt.label])),
    [accountOptions]
  )
  const selectedLabels = useMemo(() => {
    if (selectedIds.length === 0) return ''
    return selectedIds.map((id) => accountLabelMap.get(id) || id).join('，')
  }, [selectedIds, accountLabelMap])

  const loadData = async () => {
    try {
      setTableLoading(true)
      const [configResult, categoryResult, details] = await Promise.all([
        list(),
        getListingMonitorCategories(),
        getAccountDetails(),
      ])
      if (configResult.success && configResult.data) {
        setConfigs(configResult.data)
      } else {
        addToast({ type: 'error', message: configResult.message || '加载兜底账号配置失败' })
      }
      if (categoryResult.success && categoryResult.data) {
        setCategories(categoryResult.data.map((c) => ({ id: c.id, name: c.name })))
      } else {
        addToast({ type: 'error', message: categoryResult.message || '加载分类列表失败' })
      }
      setAccountOptions(
        details.map((item) => ({
          value: item.id,
          label: item.note ? `${item.note}（${item.id}）` : item.id,
          enabled: Boolean(item.enabled),
        }))
      )
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载兜底账号配置失败') })
    } finally {
      setLoading(false)
      setTableLoading(false)
    }
  }

  useEffect(() => {
    void loadData()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // 新建时可选分类：排除已配置的分类；无分类未配置时提供"无分类"项
  // 管理员查看全量时，新建仅针对自身，故按当前用户自身已配置的分类来排除
  const availableCategoryOptions = useMemo(() => {
    const ownConfigs = isAdmin ? configs.filter((c) => c.owner_id === currentUserId) : configs
    const configuredIds = new Set(ownConfigs.filter((c) => c.category_id != null).map((c) => c.category_id))
    const hasNoCategory = ownConfigs.some((c) => c.category_id == null)
    const options: { value: string; label: string }[] = []
    if (!hasNoCategory) {
      options.push({ value: NONE_VALUE, label: '无分类（全局兜底）' })
    }
    categories
      .filter((c) => !configuredIds.has(c.id))
      .forEach((c) => options.push({ value: String(c.id), label: c.name }))
    return options
  }, [configs, categories, isAdmin, currentUserId])

  const handleOpenCreate = () => {
    setEditing(null)
    setFormCategory('')
    setSelectedIds([])
    setDropdownOpen(false)
    setShowModal(true)
  }

  const handleOpenEdit = (config: FallbackConfig) => {
    setEditing(config)
    setFormCategory(config.category_id != null ? String(config.category_id) : NONE_VALUE)
    setSelectedIds([...config.account_ids])
    setDropdownOpen(false)
    setShowModal(true)
  }

  const toggleAccount = (accountId: string) => {
    setSelectedIds((prev) =>
      prev.includes(accountId) ? prev.filter((id) => id !== accountId) : [...prev, accountId]
    )
  }

  const handleSubmit = async () => {
    if (!editing && !formCategory) {
      addToast({ type: 'warning', message: '请选择分类（或无分类）' })
      return
    }
    const categoryId = formCategory === NONE_VALUE ? null : Number(formCategory)
    setSaving(true)
    try {
      // 编辑时沿用该配置的所属用户（管理员可编辑他人配置）；新建时归属当前用户
      const result = await save(categoryId, selectedIds, editing?.owner_id ?? undefined)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '保存失败' })
        return
      }
      addToast({ type: 'success', message: result.message || '保存成功' })
      setShowModal(false)
      setEditing(null)
      await loadData()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '保存兜底账号失败') })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      // 管理员删除他人配置时需指定所属用户
      const result = await remove(deleteTarget.category_id, deleteTarget.owner_id ?? undefined)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '删除失败' })
        return
      }
      addToast({ type: 'success', message: result.message || '删除成功' })
      setDeleteTarget(null)
      await loadData()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '删除失败') })
    } finally {
      setDeleting(false)
    }
  }

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {saving && <Loading fullScreen text="正在保存兜底账号..." />}

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">{title}</h1>
          <p className="page-description">{description}</p>
        </div>
        <div className="flex gap-3 flex-wrap">
          <button className="btn-ios-primary" onClick={handleOpenCreate}>
            <Plus className="w-4 h-4" />
            新建配置
          </button>
          <button className="btn-ios-secondary" onClick={() => void loadData()} disabled={tableLoading}>
            {tableLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            刷新
          </button>
        </div>
      </div>

      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 280px)', minHeight: '420px' }}>
        <div className="vben-card-header flex items-center justify-between">
          <h2 className="vben-card-title">
            <Users className="w-4 h-4" />
            兜底{accountKind}账号配置
          </h2>
          <span className="badge-primary">共 {configs.length} 条</span>
        </div>

        <div className="flex-1 overflow-auto">
          <table className={`table-ios ${isAdmin ? 'min-w-[840px]' : 'min-w-[720px]'}`}>
            <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
              <tr>
                <th>分类</th>
                {isAdmin && <th className="whitespace-nowrap min-w-[120px]">所属用户</th>}
                <th>兜底账号</th>
                <th>账号状态</th>
                <th>更新时间</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {tableLoading ? (
                <tr>
                  <td colSpan={isAdmin ? 6 : 5} className="text-center py-12">
                    <Loader2 className="w-6 h-6 animate-spin text-blue-500 mx-auto" />
                  </td>
                </tr>
              ) : configs.length === 0 ? (
                <tr>
                  <td colSpan={isAdmin ? 6 : 5} className="text-center py-12 text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <Users className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>暂无兜底配置，点击右上角新建</p>
                    </div>
                  </td>
                </tr>
              ) : (
                configs.map((config) => {
                  const invalidCount = config.accounts.filter((a) => !a.valid).length
                  return (
                    <tr key={config.id ?? `${config.category_id}`}>
                      <td className="whitespace-nowrap font-medium text-slate-800 dark:text-slate-100">
                        {config.category_id == null ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs bg-slate-100 text-slate-600 dark:bg-slate-700 dark:text-slate-300">无分类</span>
                        ) : (
                          config.category_name || `#${config.category_id}`
                        )}
                      </td>
                      {isAdmin && (
                        <td className="whitespace-nowrap text-sm text-slate-600 dark:text-slate-400">
                          {config.owner_username || (config.owner_id != null ? `#${config.owner_id}` : '-')}
                        </td>
                      )}
                      <td className="whitespace-nowrap">{config.account_ids.length} 个账号</td>
                      <td className="whitespace-nowrap">
                        {config.account_ids.length === 0 ? (
                          <span className="text-slate-400">未配置</span>
                        ) : invalidCount > 0 ? (
                          <span className="inline-flex items-center gap-1 text-orange-600 dark:text-orange-400">
                            <AlertCircle className="w-4 h-4" />{invalidCount} 个失效
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-green-600 dark:text-green-400">
                            <CheckCircle2 className="w-4 h-4" />全部可用
                          </span>
                        )}
                      </td>
                      <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">
                        {config.updated_at ? new Date(config.updated_at).toLocaleString('zh-CN') : '-'}
                      </td>
                      <td className="whitespace-nowrap">
                        <div className="flex items-center gap-1">
                          <button
                            onClick={() => handleOpenEdit(config)}
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 text-blue-600 dark:text-blue-400 transition-colors"
                          >
                            <Pencil className="w-4 h-4" />编辑
                          </button>
                          <button
                            onClick={() => setDeleteTarget(config)}
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-600 dark:text-red-400 transition-colors"
                          >
                            <Trash2 className="w-4 h-4" />删除
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {showModal && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg">
            <div className="modal-header">
              <h2 className="modal-title">{editing ? '编辑兜底配置' : '新建兜底配置'}</h2>
              <button className="modal-close" onClick={() => setShowModal(false)} disabled={saving}>
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              {isAdmin && editing?.owner_username && (
                <div className="input-group">
                  <label className="input-label">所属用户</label>
                  <div className="input-ios bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                    {editing.owner_username}
                  </div>
                </div>
              )}
              <div className="input-group">
                <label className="input-label">分类 <span className="text-red-500">*</span></label>
                {editing ? (
                  <div className="input-ios bg-slate-50 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                    {editing.category_id == null ? '无分类（全局兜底）' : (editing.category_name || `#${editing.category_id}`)}
                  </div>
                ) : (
                  <Select
                    value={formCategory}
                    onChange={setFormCategory}
                    options={availableCategoryOptions}
                    placeholder={availableCategoryOptions.length === 0 ? '所有分类均已配置' : '请选择分类'}
                  />
                )}
              </div>

              <div className="input-group">
                <div className="flex items-center justify-between">
                  <label className="input-label mb-0">
                    兜底{accountKind}账号（可多选）
                    <span className="text-xs text-slate-400 ml-1">（仅启用账号，留空表示不配置）</span>
                  </label>
                  {selectedIds.length > 0 && (
                    <button type="button" onClick={() => setSelectedIds([])} className="text-xs text-blue-600 dark:text-blue-400 hover:underline">
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
                    {selectedLabels || '请选择账号'}
                  </span>
                  <ChevronDown className={`w-4 h-4 text-slate-400 flex-shrink-0 transition-transform duration-200 ${dropdownOpen ? 'rotate-180' : ''}`} />
                </button>
                {dropdownOpen && (
                  <div className="mt-1 border border-slate-200 dark:border-slate-700 rounded-md bg-white dark:bg-slate-800">
                    <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200 dark:border-slate-700">
                      <span className="text-xs text-slate-500 dark:text-slate-400">共 {enabledAccountOptions.length} 个启用账号</span>
                      <div className="flex items-center gap-3">
                        <button type="button" onClick={() => setSelectedIds(enabledAccountOptions.map((o) => o.value))} className="text-xs text-blue-600 dark:text-blue-400 hover:underline" disabled={enabledAccountOptions.length === 0}>全选</button>
                        <button type="button" onClick={() => setSelectedIds([])} className="text-xs text-slate-500 dark:text-slate-400 hover:underline" disabled={selectedIds.length === 0}>清空</button>
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
            </div>
            <div className="modal-footer">
              <button className="btn-ios-secondary" onClick={() => setShowModal(false)} disabled={saving}>取消</button>
              <button className="btn-ios-primary" onClick={() => void handleSubmit()} disabled={saving}>
                {saving && <Loader2 className="w-4 h-4 animate-spin" />}
                {editing ? '保存修改' : '确认新建'}
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmModal
        isOpen={Boolean(deleteTarget)}
        title="删除兜底配置确认"
        message={`确定删除${isAdmin && deleteTarget?.owner_username ? `用户「${deleteTarget.owner_username}」` : ''}该分类（${deleteTarget?.category_id == null ? '无分类' : (deleteTarget?.category_name || '#' + deleteTarget?.category_id)}）的兜底${accountKind}账号配置吗？`}
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={() => void handleDelete()}
        onCancel={() => {
          if (!deleting) setDeleteTarget(null)
        }}
      />
    </div>
  )
}

export default FallbackAccountManager
