/**
 * 新建或修改定时发布规则弹窗。
 *
 * 功能：
 * 1. 左右分栏多选账号和素材；
 * 2. 设置每日触发时间范围及随机间隔分钟范围；
 * 3. 保存并启用规则，由系统定时任务按配置自动发布商品。
 */
import { useEffect, useMemo, useState } from 'react'
import { Clock3, Image, Loader2, Search, Users, X } from 'lucide-react'
import { Loading } from '@/components/common/Loading'
import {
  createScheduledPublishRule,
  getScheduledPublishOptions,
  updateScheduledPublishRule,
  type ScheduledPublishAccountOption,
  type ScheduledPublishMaterialOption,
  type ScheduledPublishRule,
} from '@/api/scheduledPublish'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

interface ScheduledPublishRuleModalProps {
  rule?: ScheduledPublishRule | null
  onClose: () => void
  onSaved: () => void
}

const toggleSelection = <T extends string | number>(current: Set<T>, value: T): Set<T> => {
  const next = new Set(current)
  if (next.has(value)) next.delete(value)
  else next.add(value)
  return next
}

const MAX_ACCOUNT_SELECTION = 5000
const MAX_MATERIAL_SELECTION = 2000
const MAX_INTERVAL_MINUTES = 43200

export function ScheduledPublishRuleModal({ rule, onClose, onSaved }: ScheduledPublishRuleModalProps) {
  const { addToast } = useUIStore()
  const editing = Boolean(rule)
  const [ruleName, setRuleName] = useState(rule?.rule_name ?? '')
  const [triggerStartTime, setTriggerStartTime] = useState(rule?.trigger_start_time ?? '07:00')
  const [triggerEndTime, setTriggerEndTime] = useState(rule?.trigger_end_time ?? '20:00')
  const [intervalMinMinutes, setIntervalMinMinutes] = useState(String(rule?.interval_min_minutes ?? 1))
  const [intervalMaxMinutes, setIntervalMaxMinutes] = useState(String(rule?.interval_max_minutes ?? 3))
  const [accounts, setAccounts] = useState<ScheduledPublishAccountOption[]>([])
  const [materials, setMaterials] = useState<ScheduledPublishMaterialOption[]>([])
  const [selectedAccounts, setSelectedAccounts] = useState<Set<string>>(
    new Set(rule?.account_ids ?? []),
  )
  const [selectedMaterials, setSelectedMaterials] = useState<Set<number>>(
    new Set(rule?.material_ids ?? []),
  )
  const [accountKeyword, setAccountKeyword] = useState('')
  const [materialKeyword, setMaterialKeyword] = useState('')
  const [loadingOptions, setLoadingOptions] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let active = true
    const loadOptions = async () => {
      setLoadingOptions(true)
      try {
        const response = await getScheduledPublishOptions()
        if (!active) return
        if (!response.success || !response.data) {
          addToast({ type: 'error', message: response.message || '账号和素材加载失败' })
          return
        }
        setAccounts(response.data.accounts)
        setMaterials(response.data.materials)
        if (rule) {
          const availableAccountIds = new Set(response.data.accounts.map((item) => item.account_id))
          const availableMaterialIds = new Set(response.data.materials.map((item) => item.id))
          const validAccountIds = rule.account_ids.filter((id) => availableAccountIds.has(id))
          const validMaterialIds = rule.material_ids.filter((id) => availableMaterialIds.has(id))
          setSelectedAccounts(new Set(validAccountIds))
          setSelectedMaterials(new Set(validMaterialIds))
          if (
            validAccountIds.length !== rule.account_ids.length
            || validMaterialIds.length !== rule.material_ids.length
          ) {
            addToast({
              type: 'warning',
              message: '原规则中部分账号或素材已不可用，已从本次编辑选择中移除',
            })
          }
        }
      } catch (error) {
        if (active) addToast({ type: 'error', message: getApiErrorMessage(error, '账号和素材加载失败') })
      } finally {
        if (active) setLoadingOptions(false)
      }
    }
    void loadOptions()
    return () => { active = false }
  }, [addToast, rule])

  const filteredAccounts = useMemo(() => {
    const keyword = accountKeyword.trim().toLowerCase()
    if (!keyword) return accounts
    return accounts.filter((item) =>
      item.account_id.toLowerCase().includes(keyword)
      || item.display_name.toLowerCase().includes(keyword),
    )
  }, [accountKeyword, accounts])

  const filteredMaterials = useMemo(() => {
    const keyword = materialKeyword.trim().toLowerCase()
    if (!keyword) return materials
    return materials.filter((item) => item.title.toLowerCase().includes(keyword))
  }, [materialKeyword, materials])

  const toggleAllAccounts = () => {
    const ids = filteredAccounts.map((item) => item.account_id)
    const selectedVisibleCount = ids.filter((id) => selectedAccounts.has(id)).length
    const selectedOutsideCount = selectedAccounts.size - selectedVisibleCount
    const maxSelectableVisible = Math.min(
      ids.length,
      MAX_ACCOUNT_SELECTION - selectedOutsideCount,
    )
    const shouldClear = selectedVisibleCount > 0 && selectedVisibleCount >= maxSelectableVisible
    const next = new Set(selectedAccounts)
    if (shouldClear) ids.forEach((id) => next.delete(id))
    else ids.forEach((id) => { if (next.size < MAX_ACCOUNT_SELECTION) next.add(id) })
    setSelectedAccounts(next)
    if (!shouldClear && ids.some((id) => !next.has(id))) {
      addToast({ type: 'warning', message: `单条规则最多选择 ${MAX_ACCOUNT_SELECTION} 个账号` })
    }
  }

  const toggleAllMaterials = () => {
    const ids = filteredMaterials.map((item) => item.id)
    const selectedVisibleCount = ids.filter((id) => selectedMaterials.has(id)).length
    const selectedOutsideCount = selectedMaterials.size - selectedVisibleCount
    const maxSelectableVisible = Math.min(
      ids.length,
      MAX_MATERIAL_SELECTION - selectedOutsideCount,
    )
    const shouldClear = selectedVisibleCount > 0 && selectedVisibleCount >= maxSelectableVisible
    const next = new Set(selectedMaterials)
    if (shouldClear) ids.forEach((id) => next.delete(id))
    else ids.forEach((id) => { if (next.size < MAX_MATERIAL_SELECTION) next.add(id) })
    setSelectedMaterials(next)
    if (!shouldClear && ids.some((id) => !next.has(id))) {
      addToast({ type: 'warning', message: `单条规则最多选择 ${MAX_MATERIAL_SELECTION} 条素材` })
    }
  }

  const toggleAccount = (accountId: string) => {
    if (!selectedAccounts.has(accountId) && selectedAccounts.size >= MAX_ACCOUNT_SELECTION) {
      addToast({ type: 'warning', message: `单条规则最多选择 ${MAX_ACCOUNT_SELECTION} 个账号` })
      return
    }
    setSelectedAccounts((current) => toggleSelection(current, accountId))
  }

  const toggleMaterial = (materialId: number) => {
    if (!selectedMaterials.has(materialId) && selectedMaterials.size >= MAX_MATERIAL_SELECTION) {
      addToast({ type: 'warning', message: `单条规则最多选择 ${MAX_MATERIAL_SELECTION} 条素材` })
      return
    }
    setSelectedMaterials((current) => toggleSelection(current, materialId))
  }

  const handleSave = async () => {
    const minMinutes = Number(intervalMinMinutes)
    const maxMinutes = Number(intervalMaxMinutes)
    if (!ruleName.trim()) {
      addToast({ type: 'warning', message: '请输入规则名称' })
      return
    }
    if (selectedAccounts.size === 0) {
      addToast({ type: 'warning', message: '请至少选择一个账号' })
      return
    }
    if (selectedMaterials.size === 0) {
      addToast({ type: 'warning', message: '请至少选择一条素材' })
      return
    }
    if (!triggerStartTime || !triggerEndTime) {
      addToast({ type: 'warning', message: '请完整设置触发开始时间和结束时间' })
      return
    }
    if (triggerStartTime >= triggerEndTime) {
      addToast({ type: 'warning', message: '触发开始时间必须早于结束时间' })
      return
    }
    if (
      !Number.isInteger(minMinutes)
      || !Number.isInteger(maxMinutes)
      || minMinutes <= 0
      || maxMinutes <= 0
    ) {
      addToast({ type: 'warning', message: '随机时间范围必须填写大于0的整数分钟' })
      return
    }
    if (minMinutes > maxMinutes) {
      addToast({ type: 'warning', message: '随机时间最小值不能大于最大值' })
      return
    }
    if (minMinutes > MAX_INTERVAL_MINUTES || maxMinutes > MAX_INTERVAL_MINUTES) {
      addToast({ type: 'warning', message: `随机时间范围不能超过 ${MAX_INTERVAL_MINUTES} 分钟` })
      return
    }

    setSaving(true)
    try {
      const payload = {
        rule_name: ruleName.trim(),
        account_ids: Array.from(selectedAccounts),
        material_ids: Array.from(selectedMaterials),
        trigger_start_time: triggerStartTime,
        trigger_end_time: triggerEndTime,
        interval_min_minutes: minMinutes,
        interval_max_minutes: maxMinutes,
      }
      const response = editing && rule
        ? await updateScheduledPublishRule(rule.id, payload)
        : await createScheduledPublishRule(payload)
      if (!response.success) {
        addToast({ type: 'error', message: response.message || '定时发布规则保存失败' })
        return
      }
      addToast({
        type: 'success',
        message: response.message || (editing ? '定时发布规则修改成功' : '定时发布规则创建成功'),
      })
      onSaved()
      onClose()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '定时发布规则保存失败') })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label={editing ? '修改定时发布规则' : '新建定时发布规则'}>
      {saving && <Loading fullScreen text="正在保存定时发布规则..." />}
      <div className="modal-content max-w-5xl h-[min(92vh,760px)] max-h-[92vh]">
        <div className="modal-header">
          <div>
            <h2 className="modal-title">{editing ? '修改定时发布规则' : '新建定时发布规则'}</h2>
            <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
              {editing
                ? '修改不会改变当前下次触发时间，新配置将在后续计算下次触发时间时生效'
                : '规则保存后默认启用，系统将按设置的时间范围和随机间隔自动发布'}
            </p>
          </div>
          <button type="button" className="modal-close" onClick={onClose} disabled={saving} aria-label="关闭">
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="modal-body space-y-5">
          <div className="input-group">
            <label className="input-label">规则名称 <span className="text-red-500">*</span></label>
            <input
              className="input-ios"
              value={ruleName}
              onChange={(event) => setRuleName(event.target.value)}
              maxLength={120}
              placeholder="例如：白天多账号随机发布"
            />
          </div>

          <div className="relative grid grid-cols-1 gap-4 lg:grid-cols-2">
            {loadingOptions && (
              <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm">
                <Loading text="正在加载账号和素材..." />
              </div>
            )}
            <SelectionPanel
              title="选择账号"
              icon={<Users className="h-4 w-4" />}
              selectedCount={selectedAccounts.size}
              keyword={accountKeyword}
              onKeywordChange={setAccountKeyword}
              onToggleAll={toggleAllAccounts}
              emptyText={accounts.length === 0 ? '暂无账号，请先添加账号' : '没有匹配的账号'}
            >
              {filteredAccounts.map((account) => (
                <label key={account.account_id} className="flex cursor-pointer items-center gap-3 rounded-lg p-2.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-700/70">
                  <input
                    type="checkbox"
                    className="checkbox-ios"
                    checked={selectedAccounts.has(account.account_id)}
                    onChange={() => toggleAccount(account.account_id)}
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-slate-800 dark:text-slate-100">{account.display_name}</p>
                    <p className="truncate text-xs text-slate-500 dark:text-slate-400">{account.account_id}</p>
                  </div>
                  <span className={account.enabled ? 'badge-success' : 'badge-gray'}>{account.enabled ? '启用' : '停用'}</span>
                </label>
              ))}
            </SelectionPanel>

            <SelectionPanel
              title="选择素材"
              icon={<Image className="h-4 w-4" />}
              selectedCount={selectedMaterials.size}
              keyword={materialKeyword}
              onKeywordChange={setMaterialKeyword}
              onToggleAll={toggleAllMaterials}
              emptyText={materials.length === 0 ? '素材库为空，请先添加素材' : '没有匹配的素材'}
            >
              {filteredMaterials.map((material) => (
                <label key={material.id} className="flex cursor-pointer items-center gap-3 rounded-lg p-2.5 transition-colors hover:bg-slate-50 dark:hover:bg-slate-700/70">
                  <input
                    type="checkbox"
                    className="checkbox-ios"
                    checked={selectedMaterials.has(material.id)}
                    onChange={() => toggleMaterial(material.id)}
                  />
                  {material.image_url ? (
                    <img src={material.image_url} alt={material.title} className="h-10 w-10 flex-shrink-0 rounded-lg object-cover" />
                  ) : (
                    <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg bg-slate-100 text-xs text-slate-400 dark:bg-slate-700">无图</div>
                  )}
                  <p className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800 dark:text-slate-100">{material.title}</p>
                </label>
              ))}
            </SelectionPanel>
          </div>

          <div className="grid grid-cols-1 gap-4 rounded-lg border border-slate-200 bg-slate-50/70 p-4 dark:border-slate-700 dark:bg-slate-900/30 md:grid-cols-2">
            <div>
              <label className="input-label mb-2 flex items-center gap-2"><Clock3 className="h-4 w-4 text-blue-500" />每日触发时间范围</label>
              <div className="flex items-center gap-2">
                <input type="time" className="input-ios" value={triggerStartTime} onChange={(event) => setTriggerStartTime(event.target.value)} />
                <span className="text-sm text-slate-500">至</span>
                <input type="time" className="input-ios" value={triggerEndTime} onChange={(event) => setTriggerEndTime(event.target.value)} />
              </div>
              <p className="input-hint">例如 07:00 至 20:00，系统仅在每天该时间段内处理此规则。</p>
            </div>
            <div>
              <label className="input-label mb-2 flex items-center gap-2"><Clock3 className="h-4 w-4 text-blue-500" />随机时间范围</label>
              <div className="flex items-center gap-2">
                <input type="number" min="1" max={MAX_INTERVAL_MINUTES} step="1" className="input-ios" value={intervalMinMinutes} onChange={(event) => setIntervalMinMinutes(event.target.value)} />
                <span className="whitespace-nowrap text-sm text-slate-500">分钟 至</span>
                <input type="number" min="1" max={MAX_INTERVAL_MINUTES} step="1" className="input-ios" value={intervalMaxMinutes} onChange={(event) => setIntervalMaxMinutes(event.target.value)} />
                <span className="text-sm text-slate-500">分钟</span>
              </div>
              <p className="input-hint">例如 1 至 3 分钟；系统会在区间内随机生成下一次触发时间。</p>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button type="button" className="btn-ios-secondary" onClick={onClose} disabled={saving}>取消</button>
          <button type="button" className="btn-ios-primary" onClick={handleSave} disabled={saving || loadingOptions}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}
            {editing ? '保存修改' : '保存规则'}
          </button>
        </div>
      </div>
    </div>
  )
}

interface SelectionPanelProps {
  title: string
  icon: React.ReactNode
  selectedCount: number
  keyword: string
  onKeywordChange: (value: string) => void
  onToggleAll: () => void
  emptyText: string
  children: React.ReactNode
}

function SelectionPanel({
  title,
  icon,
  selectedCount,
  keyword,
  onKeywordChange,
  onToggleAll,
  emptyText,
  children,
}: SelectionPanelProps) {
  const hasItems = Array.isArray(children) ? children.length > 0 : Boolean(children)
  return (
    <section className="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-800">
      <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-700">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">{icon}{title}<span className="badge-primary">已选 {selectedCount}</span></h3>
        <button type="button" className="btn-ios-link text-sm" onClick={onToggleAll}>全选/取消</button>
      </div>
      <div className="p-3">
        <div className="relative mb-2">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <input className="input-ios pl-9" value={keyword} onChange={(event) => onKeywordChange(event.target.value)} placeholder={`搜索${title.replace('选择', '')}`} />
        </div>
        <div className="h-60 space-y-1 overflow-y-auto pr-1">
          {hasItems ? children : <p className="py-16 text-center text-sm text-slate-400">{emptyText}</p>}
        </div>
      </div>
    </section>
  )
}
