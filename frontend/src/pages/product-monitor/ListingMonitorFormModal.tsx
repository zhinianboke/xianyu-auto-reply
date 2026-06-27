/**
 * 上新监控任务表单弹窗
 *
 * 功能：
 * 1. 新建上新监控任务
 * 2. 编辑上新监控任务
 * 3. 配置关键字、价格区间、任务间隔与关联账号（多选）
 */
import { useEffect, useMemo, useState } from 'react'
import { Check, ChevronDown, Loader2, X } from 'lucide-react'
import {
  createListingMonitorTask,
  updateListingMonitorTask,
  MONITOR_TYPE_OPTIONS,
  type ListingMonitorTask,
  type MonitorType,
} from '@/api/listingMonitor'
import { getAccountDetails } from '@/api/accounts'
import { getListingMonitorCategories } from '@/api/listingMonitorCategory'
import { Loading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

interface AccountOption {
  value: string
  label: string
  enabled: boolean
}

interface ListingMonitorFormModalProps {
  initial?: ListingMonitorTask | null
  onClose: () => void
  onSaved: (task: ListingMonitorTask, mode: 'create' | 'update') => void
}

interface ListingMonitorFormState {
  monitorType: MonitorType
  categoryId: string
  keyword: string
  priceMin: string
  priceMax: string
  publishDays: string
  intervalMinutes: string
  collectPages: string
  proxyUrl: string
  accountIds: string[]
  orderAccountIds: string[]
  dmContent: string
  dmBatchSize: string
  orderBatchSize: string
  directOrder: boolean
}

const buildInitialState = (initial?: ListingMonitorTask | null): ListingMonitorFormState => ({
  monitorType: initial?.monitor_type ?? 'listing',
  categoryId: initial?.category_id != null ? String(initial.category_id) : '',
  keyword: initial?.keyword ?? '',
  priceMin: initial?.price_min != null ? String(initial.price_min) : '',
  priceMax: initial?.price_max != null ? String(initial.price_max) : '',
  publishDays: initial?.publish_days != null ? String(initial.publish_days) : '',
  intervalMinutes: initial?.interval_minutes != null ? String(initial.interval_minutes) : '5',
  collectPages: initial?.collect_pages != null ? String(initial.collect_pages) : '1',
  proxyUrl: initial?.proxy_url ?? '',
  accountIds: initial?.account_ids ? [...initial.account_ids] : [],
  orderAccountIds: initial?.order_account_ids ? [...initial.order_account_ids] : [],
  dmContent: initial?.dm_content ?? '',
  dmBatchSize: initial?.dm_batch_size != null ? String(initial.dm_batch_size) : '5',
  orderBatchSize: initial?.order_batch_size != null ? String(initial.order_batch_size) : '5',
  directOrder: Boolean(initial?.direct_order),
})

export function ListingMonitorFormModal({ initial, onClose, onSaved }: ListingMonitorFormModalProps) {
  const { addToast } = useUIStore()
  const isEditMode = Boolean(initial)
  const [saving, setSaving] = useState(false)
  const [form, setForm] = useState<ListingMonitorFormState>(() => buildInitialState(initial))

  const [accountOptions, setAccountOptions] = useState<AccountOption[]>([])
  const [accountLoading, setAccountLoading] = useState(false)
  const [accountDropdownOpen, setAccountDropdownOpen] = useState(false)
  const [orderAccountDropdownOpen, setOrderAccountDropdownOpen] = useState(false)
  const [categoryOptions, setCategoryOptions] = useState<{ value: string; label: string }[]>([])

  // 加载分类下拉选项（普通用户仅见自己的分类，管理员可见全部）
  useEffect(() => {
    const loadCategories = async () => {
      try {
        const result = await getListingMonitorCategories()
        if (result.success && result.data) {
          setCategoryOptions(result.data.map((c) => ({ value: String(c.id), label: c.name })))
        }
      } catch (error) {
        addToast({ type: 'error', message: getApiErrorMessage(error, '加载分类列表失败') })
      }
    }
    void loadCategories()
  }, [addToast])

  // 加载账号下拉选项
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

  const selectedAccountLabels = useMemo(() => {
    if (form.accountIds.length === 0) return ''
    const labelMap = new Map(accountOptions.map((opt) => [opt.value, opt.label]))
    return form.accountIds.map((id) => labelMap.get(id) || id).join('，')
  }, [form.accountIds, accountOptions])

  // 下单账号取启用账号（多选，私信与下单共用）
  const enabledAccountOptions = useMemo(
    () => accountOptions.filter((o) => o.enabled),
    [accountOptions]
  )

  const selectedOrderAccountLabels = useMemo(() => {
    if (form.orderAccountIds.length === 0) return ''
    const labelMap = new Map(accountOptions.map((opt) => [opt.value, opt.label]))
    return form.orderAccountIds.map((id) => labelMap.get(id) || id).join('，')
  }, [form.orderAccountIds, accountOptions])

  const toggleAccount = (accountId: string) => {
    setForm((prev) => {
      const exists = prev.accountIds.includes(accountId)
      return {
        ...prev,
        accountIds: exists
          ? prev.accountIds.filter((id) => id !== accountId)
          : [...prev.accountIds, accountId],
      }
    })
  }

  const handleClearAccounts = () => {
    setForm((prev) => ({ ...prev, accountIds: [] }))
  }

  const handleSelectAllAccounts = () => {
    setForm((prev) => ({ ...prev, accountIds: enabledAccountOptions.map((opt) => opt.value) }))
  }

  const toggleOrderAccount = (accountId: string) => {
    setForm((prev) => {
      const exists = prev.orderAccountIds.includes(accountId)
      return {
        ...prev,
        orderAccountIds: exists
          ? prev.orderAccountIds.filter((id) => id !== accountId)
          : [...prev.orderAccountIds, accountId],
      }
    })
  }

  const handleClearOrderAccounts = () => {
    setForm((prev) => ({ ...prev, orderAccountIds: [] }))
  }

  const handleSelectAllOrderAccounts = () => {
    setForm((prev) => ({ ...prev, orderAccountIds: enabledAccountOptions.map((opt) => opt.value) }))
  }

  const handleSubmit = async () => {
    const keyword = form.keyword.trim()
    if (!keyword) {
      addToast({ type: 'warning', message: '请填写商品关键字' })
      return
    }

    if (!form.categoryId) {
      addToast({ type: 'warning', message: '请选择分类' })
      return
    }

    const priceMin = form.priceMin.trim() === '' ? null : Number(form.priceMin)
    const priceMax = form.priceMax.trim() === '' ? null : Number(form.priceMax)
    if (priceMin !== null && (Number.isNaN(priceMin) || priceMin < 0)) {
      addToast({ type: 'warning', message: '最低价格必须为大于等于0的数字' })
      return
    }
    if (priceMax !== null && (Number.isNaN(priceMax) || priceMax < 0)) {
      addToast({ type: 'warning', message: '最高价格必须为大于等于0的数字' })
      return
    }
    if (priceMin !== null && priceMax !== null && priceMin > priceMax) {
      addToast({ type: 'warning', message: '最低价格不能大于最高价格' })
      return
    }

    const intervalMinutes = Number(form.intervalMinutes)
    if (!Number.isInteger(intervalMinutes) || intervalMinutes < 1) {
      addToast({ type: 'warning', message: '任务间隔必须为大于等于1的整数分钟' })
      return
    }

    const collectPages = Number(form.collectPages)
    if (!Number.isInteger(collectPages) || collectPages < 1) {
      addToast({ type: 'warning', message: '采集页数必须为大于等于1的整数' })
      return
    }

    if (form.orderAccountIds.length > 0 && !form.dmContent.trim() && !form.directOrder) {
      addToast({ type: 'warning', message: '配置了下单账号后，私信内容必填（或开启采集后直接下单）' })
      return
    }

    if (form.directOrder && form.orderAccountIds.length === 0) {
      addToast({ type: 'warning', message: '开启采集后直接下单需配置下单账号' })
      return
    }

    const dmBatchSize = Number(form.dmBatchSize)
    if (!Number.isInteger(dmBatchSize) || dmBatchSize < 1 || dmBatchSize > 100) {
      addToast({ type: 'warning', message: '每次私信处理条数必须为 1~100 的整数' })
      return
    }

    const orderBatchSize = Number(form.orderBatchSize)
    if (!Number.isInteger(orderBatchSize) || orderBatchSize < 1 || orderBatchSize > 100) {
      addToast({ type: 'warning', message: '每次下单处理条数必须为 1~100 的整数' })
      return
    }

    setSaving(true)
    try {
      const payload = {
        monitor_type: form.monitorType,
        category_id: Number(form.categoryId),
        keyword,
        price_min: priceMin,
        price_max: priceMax,
        publish_days: form.monitorType === 'listing'
          ? (form.publishDays === '' ? null : Number(form.publishDays))
          : null,
        interval_minutes: intervalMinutes,
        collect_pages: collectPages,
        proxy_url: form.proxyUrl.trim() || null,
        account_ids: form.accountIds,
        order_account_ids: form.orderAccountIds,
        dm_content: form.dmContent.trim() || null,
        dm_batch_size: dmBatchSize,
        order_batch_size: orderBatchSize,
        direct_order: form.directOrder,
      }
      const result = isEditMode && initial
        ? await updateListingMonitorTask(initial.id, payload)
        : await createListingMonitorTask(payload)

      if (!result.success || !result.data?.task) {
        addToast({ type: 'error', message: result.message || (isEditMode ? '保存监控任务失败' : '创建监控任务失败') })
        return
      }

      addToast({
        type: 'success',
        message: result.message || (isEditMode ? '监控任务保存成功' : '监控任务创建成功'),
      })
      onSaved(result.data.task, isEditMode ? 'update' : 'create')
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, isEditMode ? '保存监控任务失败' : '创建监控任务失败') })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay">
      {saving && <Loading fullScreen text={isEditMode ? '正在保存监控任务...' : '正在创建监控任务...'} />}
      <div className="modal-content max-w-2xl">
        <div className="modal-header">
          <h2 className="modal-title">{isEditMode ? '编辑上新监控任务' : '新建上新监控任务'}</h2>
          <button className="modal-close" onClick={onClose} disabled={saving}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="modal-body">
          <div className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="input-group">
                <label className="input-label">监控类型 <span className="text-red-500">*</span></label>
                <Select
                  value={form.monitorType}
                  onChange={(value) => setForm((prev) => ({ ...prev, monitorType: value as MonitorType }))}
                  options={MONITOR_TYPE_OPTIONS}
                  placeholder="请选择监控类型"
                />
              </div>

              <div className="input-group">
                <label className="input-label">所属分类 <span className="text-red-500">*</span></label>
                <Select
                  value={form.categoryId}
                  onChange={(value) => setForm((prev) => ({ ...prev, categoryId: value }))}
                  options={categoryOptions}
                  placeholder={categoryOptions.length === 0 ? '暂无分类，请先到「监控分类」新建' : '请选择分类'}
                />
              </div>
            </div>

            <div className="input-group">
              <label className="input-label">商品关键字 <span className="text-red-500">*</span></label>
              <input
                className="input-ios"
                placeholder="如：iPhone 15 黄金"
                value={form.keyword}
                onChange={(e) => setForm((prev) => ({ ...prev, keyword: e.target.value }))}
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="input-group">
                <label className="input-label">商品价格最低</label>
                <input
                  className="input-ios"
                  type="number"
                  min={0}
                  step="0.01"
                  placeholder="不限则留空"
                  value={form.priceMin}
                  onChange={(e) => setForm((prev) => ({ ...prev, priceMin: e.target.value }))}
                />
              </div>
              <div className="input-group">
                <label className="input-label">商品价格最高</label>
                <input
                  className="input-ios"
                  type="number"
                  min={0}
                  step="0.01"
                  placeholder="不限则留空"
                  value={form.priceMax}
                  onChange={(e) => setForm((prev) => ({ ...prev, priceMax: e.target.value }))}
                />
              </div>
            </div>

            {form.monitorType === 'listing' && (
              <div className="input-group">
                <label className="input-label">
                  监控天数 <span className="text-red-500">*</span>
                  <span className="text-xs text-slate-400 ml-1">（上新监控按发布时间筛选；"最新"为不限天数仅按上新排序）</span>
                </label>
                <Select
                  value={form.publishDays}
                  onChange={(value) => setForm((prev) => ({ ...prev, publishDays: value }))}
                  options={[
                    { value: '', label: '最新' },
                    { value: '1', label: '1天内' },
                    { value: '3', label: '3天内' },
                    { value: '7', label: '7天内' },
                    { value: '14', label: '14天内' },
                  ]}
                  placeholder="最新"
                />
              </div>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="input-group">
                <label className="input-label">任务间隔（分钟） <span className="text-red-500">*</span></label>
                <input
                  className="input-ios"
                  type="number"
                  min={1}
                  step="1"
                  placeholder="如：5"
                  value={form.intervalMinutes}
                  onChange={(e) => setForm((prev) => ({ ...prev, intervalMinutes: e.target.value }))}
                />
              </div>
              <div className="input-group">
                <label className="input-label">采集页数 <span className="text-red-500">*</span></label>
                <input
                  className="input-ios"
                  type="number"
                  min={1}
                  step="1"
                  placeholder="默认 1"
                  value={form.collectPages}
                  onChange={(e) => setForm((prev) => ({ ...prev, collectPages: e.target.value }))}
                />
              </div>
            </div>

            <div className="input-group">
              <label className="input-label">
                代理API地址
                <span className="text-xs text-slate-400 ml-1">（选填；调用该API获取代理IP，采集与详情请求走代理。留空=直连）</span>
              </label>
              <input
                className="input-ios"
                placeholder="如：http://proxy-provider.com/get?type=text  （留空不使用代理）"
                value={form.proxyUrl}
                onChange={(e) => setForm((prev) => ({ ...prev, proxyUrl: e.target.value }))}
              />
            </div>

            <div className="input-group">
              <div className="flex items-center justify-between">
                <label className="input-label mb-0">
                  采集账号（可多选）
                  <span className="text-xs text-slate-400 ml-1">（非必填，未配置或失效时回退用户级兜底采集账号）</span>
                </label>
                {form.accountIds.length > 0 && (
                  <button
                    type="button"
                    onClick={handleClearAccounts}
                    className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    清空选中（{form.accountIds.length}）
                  </button>
                )}
              </div>
              <button
                type="button"
                onClick={() => setAccountDropdownOpen((prev) => !prev)}
                className="mt-1 w-full flex items-center justify-between gap-2 px-3 py-2 rounded-md text-sm text-left bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 hover:border-blue-400 dark:hover:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <span className={selectedAccountLabels ? 'truncate text-slate-900 dark:text-slate-100' : 'truncate text-slate-400'}>
                  {selectedAccountLabels || (accountLoading ? '正在加载账号...' : '不使用（请选择采集账号）')}
                </span>
                <ChevronDown className={`w-4 h-4 text-slate-400 flex-shrink-0 transition-transform duration-200 ${accountDropdownOpen ? 'rotate-180' : ''}`} />
              </button>

              {accountDropdownOpen && (
                <div className="mt-1 border border-slate-200 dark:border-slate-700 rounded-md bg-white dark:bg-slate-800">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200 dark:border-slate-700">
                    <span className="text-xs text-slate-500 dark:text-slate-400">共 {enabledAccountOptions.length} 个启用账号</span>
                    <div className="flex items-center gap-3">
                      <button type="button" onClick={handleSelectAllAccounts} className="text-xs text-blue-600 dark:text-blue-400 hover:underline" disabled={enabledAccountOptions.length === 0}>全选</button>
                      <button type="button" onClick={handleClearAccounts} className="text-xs text-slate-500 dark:text-slate-400 hover:underline" disabled={form.accountIds.length === 0}>清空</button>
                    </div>
                  </div>
                  <div className="max-h-48 overflow-auto">
                    {enabledAccountOptions.length === 0 ? (
                      <div className="px-3 py-2 text-sm text-slate-400 text-center">
                        {accountLoading ? '正在加载...' : '暂无启用账号'}
                      </div>
                    ) : (
                      enabledAccountOptions.map((option) => {
                        const checked = form.accountIds.includes(option.value)
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
              {form.accountIds.length > 0 && (
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">已选择 {form.accountIds.length} 个账号</p>
              )}
            </div>

            <div className="input-group">
              <div className="flex items-center justify-between">
                <label className="input-label mb-0">
                  下单账号（可多选）
                  <span className="text-xs text-slate-400 ml-1">（启用账号，私信与下单共用，非必填）</span>
                </label>
                {form.orderAccountIds.length > 0 && (
                  <button
                    type="button"
                    onClick={handleClearOrderAccounts}
                    className="text-xs text-blue-600 dark:text-blue-400 hover:underline"
                  >
                    清空选中（{form.orderAccountIds.length}）
                  </button>
                )}
              </div>
              <button
                type="button"
                onClick={() => setOrderAccountDropdownOpen((prev) => !prev)}
                className="mt-1 w-full flex items-center justify-between gap-2 px-3 py-2 rounded-md text-sm text-left bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 hover:border-blue-400 dark:hover:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <span className={selectedOrderAccountLabels ? 'truncate text-slate-900 dark:text-slate-100' : 'truncate text-slate-400'}>
                  {selectedOrderAccountLabels || (accountLoading ? '正在加载账号...' : '不使用（请选择下单账号）')}
                </span>
                <ChevronDown className={`w-4 h-4 text-slate-400 flex-shrink-0 transition-transform duration-200 ${orderAccountDropdownOpen ? 'rotate-180' : ''}`} />
              </button>

              {orderAccountDropdownOpen && (
                <div className="mt-1 border border-slate-200 dark:border-slate-700 rounded-md bg-white dark:bg-slate-800">
                  <div className="flex items-center justify-between px-3 py-2 border-b border-slate-200 dark:border-slate-700">
                    <span className="text-xs text-slate-500 dark:text-slate-400">共 {enabledAccountOptions.length} 个启用账号</span>
                    <div className="flex items-center gap-3">
                      <button type="button" onClick={handleSelectAllOrderAccounts} className="text-xs text-blue-600 dark:text-blue-400 hover:underline" disabled={enabledAccountOptions.length === 0}>全选</button>
                      <button type="button" onClick={handleClearOrderAccounts} className="text-xs text-slate-500 dark:text-slate-400 hover:underline" disabled={form.orderAccountIds.length === 0}>清空</button>
                    </div>
                  </div>
                  <div className="max-h-48 overflow-auto">
                    {enabledAccountOptions.length === 0 ? (
                      <div className="px-3 py-2 text-sm text-slate-400 text-center">
                        {accountLoading ? '正在加载...' : '暂无启用账号'}
                      </div>
                    ) : (
                      enabledAccountOptions.map((option) => {
                        const checked = form.orderAccountIds.includes(option.value)
                        return (
                          <button
                            key={option.value}
                            type="button"
                            onClick={() => toggleOrderAccount(option.value)}
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
              {form.orderAccountIds.length > 0 && (
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">已选择 {form.orderAccountIds.length} 个账号（私信成功后优先用该账号下单）</p>
              )}
            </div>

            <div className="input-group">
              <label className="input-label">
                私信内容
                {form.orderAccountIds.length > 0 ? <span className="text-red-500 ml-1">*</span> : <span className="text-xs text-slate-400 ml-1">（配置下单账号后必填）</span>}
              </label>
              <textarea
                className="input-ios"
                rows={3}
                placeholder="命中商品后向卖家发送的私信内容"
                value={form.dmContent}
                onChange={(e) => setForm((prev) => ({ ...prev, dmContent: e.target.value }))}
              />
            </div>

            <div className="input-group">
              <label className="input-label">
                每次私信处理条数 <span className="text-red-500">*</span>
                <span className="text-xs text-slate-400 ml-1">（定时私信任务每轮最多处理的商品数，1~100）</span>
              </label>
              <input
                className="input-ios"
                type="number"
                min={1}
                max={100}
                step="1"
                placeholder="默认 5"
                value={form.dmBatchSize}
                onChange={(e) => setForm((prev) => ({ ...prev, dmBatchSize: e.target.value }))}
              />
            </div>

            <div className="input-group">
              <label className="input-label">
                每次下单处理条数 <span className="text-red-500">*</span>
                <span className="text-xs text-slate-400 ml-1">（定时下单任务每轮最多处理的商品数，1~100）</span>
              </label>
              <input
                className="input-ios"
                type="number"
                min={1}
                max={100}
                step="1"
                placeholder="默认 5"
                value={form.orderBatchSize}
                onChange={(e) => setForm((prev) => ({ ...prev, orderBatchSize: e.target.value }))}
              />
            </div>

            <div className="input-group">
              <label className="flex items-center gap-2 cursor-pointer select-none">
                <input
                  type="checkbox"
                  className="w-4 h-4 rounded border-slate-300 text-blue-600 focus:ring-blue-500"
                  checked={form.directOrder}
                  onChange={(e) => setForm((prev) => ({ ...prev, directOrder: e.target.checked }))}
                />
                <span className="input-label mb-0">采集后直接下单</span>
              </label>
              <p className="text-xs text-slate-400 mt-1">开启后，新采集到的商品立即用下单账号下单（跳过私信），下单完成后再入库，避免与定时下单任务并发。需配置下单账号。</p>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-ios-secondary" onClick={onClose} disabled={saving}>取消</button>
          <button className="btn-ios-primary" onClick={handleSubmit} disabled={saving}>
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            {isEditMode ? '保存修改' : '确认新建'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default ListingMonitorFormModal
