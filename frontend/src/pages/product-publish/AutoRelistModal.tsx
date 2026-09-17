import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, X } from 'lucide-react'

import { getAccountDetails } from '@/api/accounts'
import { getAllCards, type CardData } from '@/api/cards'
import { getItems } from '@/api/items'
import {
  getAutoRelistEvents,
  getAutoRelistRule,
  markAutoRelistEventFailed,
  reconcileAutoRelistEvent,
  saveAutoRelistRule,
  type AutoRelistEvent,
  type AutoRelistRule,
  type ProductMaterial,
} from '@/api/productPublish'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import type { AccountDetail, Item } from '@/types'
import { ConfirmModal } from '@/components/common/ConfirmModal'

interface Props {
  material: ProductMaterial
  onClose: () => void
  onSaved: (rule: AutoRelistRule) => void
}

export function AutoRelistModal({ material, onClose, onSaved }: Props) {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [itemsLoading, setItemsLoading] = useState(false)
  const [accounts, setAccounts] = useState<AccountDetail[]>([])
  const [items, setItems] = useState<Item[]>([])
  const [cards, setCards] = useState<CardData[]>([])
  const [events, setEvents] = useState<AutoRelistEvent[]>([])
  const [eventsLoading, setEventsLoading] = useState(false)
  const [eventPage, setEventPage] = useState(1)
  const [eventPageSize, setEventPageSize] = useState(20)
  const [eventTotal, setEventTotal] = useState(0)
  const [eventTotalPages, setEventTotalPages] = useState(0)
  const [reconcileEventId, setReconcileEventId] = useState<number | null>(null)
  const [reconcileItemId, setReconcileItemId] = useState('')
  const [reconciling, setReconciling] = useState(false)
  const [markFailedEvent, setMarkFailedEvent] = useState<AutoRelistEvent | null>(null)
  const [rule, setRule] = useState<AutoRelistRule | null>(material.auto_relist || null)
  const [accountId, setAccountId] = useState(material.auto_relist?.account_id || '')
  const [itemId, setItemId] = useState(material.auto_relist?.current_item_id || '')
  const [cardId, setCardId] = useState(material.auto_relist?.card_id ? String(material.auto_relist.card_id) : '')
  const [enabled, setEnabled] = useState(material.auto_relist?.enabled ?? false)
  const [delaySeconds, setDelaySeconds] = useState(String(material.auto_relist?.delay_seconds || 60))
  const canConfigure = material.auto_relist_can_configure !== false && (rule?.can_configure !== false)

  useEffect(() => {
    let cancelled = false
    const canLoadEditableResources = material.auto_relist_can_configure !== false
    Promise.all([
      canLoadEditableResources ? getAccountDetails() : Promise.resolve([] as AccountDetail[]),
      canLoadEditableResources ? getAllCards() : Promise.resolve([] as CardData[]),
      getAutoRelistRule(material.id),
      getAutoRelistEvents(material.id, 1, 20),
    ])
      .then(([accountList, cardList, ruleResponse, eventResponse]) => {
        if (cancelled) return
        if (!ruleResponse.success) {
          addToast({ type: 'error', message: ruleResponse.message || '自动续售配置加载失败' })
          return
        }
        if (!eventResponse.success) {
          addToast({ type: 'error', message: eventResponse.message || '自动续售记录加载失败' })
          return
        }
        const loadedRule = ruleResponse.data || null
        const firstAccount = accountList.find(account => account.enabled)?.id || accountList[0]?.id || ''
        setAccounts(accountList)
        setCards(cardList.filter(card => card.enabled !== false && card.id))
        setRule(loadedRule)
        setEvents(eventResponse.data?.list || [])
        setEventPage(eventResponse.data?.page || 1)
        setEventPageSize(eventResponse.data?.page_size || 20)
        setEventTotal(eventResponse.data?.total || 0)
        setEventTotalPages(eventResponse.data?.total_pages || 0)
        setAccountId(loadedRule?.account_id || firstAccount)
        setItemId(loadedRule?.current_item_id || '')
        setCardId(loadedRule?.card_id ? String(loadedRule.card_id) : '')
        setEnabled(loadedRule?.enabled ?? false)
        setDelaySeconds(String(loadedRule?.delay_seconds || 60))
      })
      .catch((error) => addToast({ type: 'error', message: getApiErrorMessage(error, '自动续售配置加载失败，请重试') }))
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [material.id, material.auto_relist_can_configure, addToast])

  const loadEvents = (page: number, pageSize: number) => {
    setEventsLoading(true)
    getAutoRelistEvents(material.id, page, pageSize).then(response => {
      if (!response.success) {
        addToast({ type: 'error', message: response.message || '自动续售记录加载失败' })
        return
      }
      setEvents(response.data?.list || [])
      setEventPage(response.data?.page || page)
      setEventPageSize(response.data?.page_size || pageSize)
      setEventTotal(response.data?.total || 0)
      setEventTotalPages(response.data?.total_pages || 0)
    }).catch((error) => {
      addToast({ type: 'error', message: getApiErrorMessage(error, '自动续售记录加载失败，请重试') })
    }).finally(() => setEventsLoading(false))
  }

  const handleReconcile = async (event: AutoRelistEvent) => {
    const itemId = reconcileItemId.trim()
    if (!itemId) {
      addToast({ type: 'warning', message: '请选择已发布的新商品' })
      return
    }
    setReconciling(true)
    try {
      const response = await reconcileAutoRelistEvent(material.id, event.id, {
        outcome: 'published',
        new_item_id: itemId,
      })
      if (!response.success || !response.data) {
        addToast({ type: 'error', message: response.message || '人工对账失败' })
        return
      }
      addToast({ type: 'success', message: response.message || '对账成功' })
      setReconcileEventId(null)
      setReconcileItemId('')
      loadEvents(eventPage, eventPageSize)
      const ruleResponse = await getAutoRelistRule(material.id)
      if (ruleResponse.success) setRule(ruleResponse.data || null)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '人工对账失败，请重试') })
    } finally {
      setReconciling(false)
    }
  }

  const handleConfirmNotPublished = async (event: AutoRelistEvent) => {
    setReconciling(true)
    try {
      const response = await reconcileAutoRelistEvent(material.id, event.id, {
        outcome: 'not_published',
      })
      if (!response.success || !response.data) {
        addToast({ type: 'error', message: response.message || '确认未发布失败' })
        return
      }
      addToast({ type: 'success', message: response.message || '已确认本次续售失败，系统将继续重试发布' })
      setReconcileEventId(null)
      setReconcileItemId('')
      loadEvents(eventPage, eventPageSize)
      const ruleResponse = await getAutoRelistRule(material.id)
      if (ruleResponse.success) setRule(ruleResponse.data || null)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '确认未发布失败，请重试') })
    } finally {
      setReconciling(false)
    }
  }

  const handleMarkFailed = async (event: AutoRelistEvent) => {
    setReconciling(true)
    try {
      const response = await markAutoRelistEventFailed(material.id, event.id)
      if (!response.success || !response.data) {
        addToast({ type: 'error', message: response.message || '标记失败操作失败' })
        return
      }
      addToast({ type: 'success', message: response.message || '已标记本次续售失败，系统将继续重试发布；后续订单将继续自动续售' })
      setMarkFailedEvent(null)
      setReconcileEventId(null)
      setReconcileItemId('')
      loadEvents(eventPage, eventPageSize)
      const ruleResponse = await getAutoRelistRule(material.id)
      if (ruleResponse.success) setRule(ruleResponse.data || null)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '标记失败操作失败，请重试') })
    } finally {
      setReconciling(false)
    }
  }

  useEffect(() => {
    if (!accountId || !canConfigure) { setItems([]); return }
    let cancelled = false
    setItemsLoading(true)
    getItems(accountId).then(response => {
      if (cancelled) return
      if (!response.success) {
        addToast({ type: 'error', message: response.message || '商品列表加载失败' })
        setItems([])
        return
      }
      setItems(response.data || [])
    }).catch((error) => {
      if (!cancelled) addToast({ type: 'error', message: getApiErrorMessage(error, '商品列表加载失败，请先获取账号商品') })
    }).finally(() => { if (!cancelled) setItemsLoading(false) })
    return () => { cancelled = true }
  }, [accountId, canConfigure, addToast])

  const handleSave = async () => {
    if (!enabled) {
      setSaving(true)
    } else {
      if (!accountId) return addToast({ type: 'warning', message: '请选择闲鱼账号' })
      if (!itemId) return addToast({ type: 'warning', message: '请选择当前在售商品' })
      if (!cardId) return addToast({ type: 'warning', message: '请选择自动发货卡券' })
      const trimmedDelay = delaySeconds.trim()
      if (!trimmedDelay) return addToast({ type: 'warning', message: '请输入售罄后确认等待时间（秒）' })
      const delayValue = Number(trimmedDelay)
      if (!Number.isInteger(delayValue) || delayValue < 1) {
        return addToast({ type: 'warning', message: '售罄后确认等待时间需为不小于 1 的整数秒' })
      }
      setSaving(true)
    }
    try {
      const response = await saveAutoRelistRule(material.id, {
        account_id: enabled ? accountId : null,
        current_item_id: enabled ? itemId : null,
        card_id: enabled ? Number(cardId) : null,
        enabled,
        delay_seconds: Number(delaySeconds),
        expected_version: rule?.version,
      })
      if (!response.success || !response.data) {
        addToast({ type: 'error', message: response.message || '保存失败' })
        return
      }
      addToast({ type: 'success', message: response.message || '自动续售配置已保存' })
      onSaved(response.data)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '保存失败，请重试') })
    } finally { setSaving(false) }
  }

  return (
    <div className="modal-overlay z-50">
      <div className="modal-content max-w-2xl max-h-[92vh] flex flex-col">
        <div className="modal-header flex-shrink-0">
          <div><h2 className="modal-title">自动续售</h2><p className="mt-1 max-w-lg truncate text-xs text-slate-500" title={material.title}>{material.title}</p></div>
          <button type="button" className="modal-close" title="关闭" onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <div className="modal-body overflow-y-auto space-y-4">
          {loading ? <div className="flex items-center justify-center py-16 text-slate-500"><Loader2 className="mr-2 h-5 w-5 animate-spin" />加载配置中</div> : <>
            {!canConfigure && <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm text-amber-700">当前为管理员只读视图，仅素材所有者可以配置自动续售。</div>}
            {canConfigure && <label className="flex items-center justify-between rounded-lg border border-blue-200 bg-blue-50/60 p-3 dark:border-blue-800 dark:bg-blue-950/20"><div><p className="font-medium text-slate-800 dark:text-slate-100">启用自动续售</p><p className="text-xs text-slate-500">关闭后保留配置和历史记录。</p></div><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} className="h-5 w-5 rounded border-slate-300 text-blue-600 focus:ring-blue-500" /></label>}
            <div className="rounded-lg border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-200">成交并完成发货后，系统确认旧商品已下架，再使用原素材发布新商品并继承持续配置。</div>
            {canConfigure ? <>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="input-group"><label className="input-label">闲鱼账号</label><select className="input-ios" disabled={!enabled} value={accountId} onChange={event => { setAccountId(event.target.value); setItemId('') }}><option value="">请选择账号</option>{accounts.map(account => <option key={account.id} value={account.id}>{account.note || account.id}{account.enabled ? '' : '（已停用）'}</option>)}</select></div>
                <div className="input-group"><label className="input-label">当前在售商品</label><select className="input-ios" disabled={!enabled || !accountId || itemsLoading} value={itemId} onChange={event => setItemId(event.target.value)}><option value="">{itemsLoading ? '正在加载商品…' : '请选择商品'}</option>{items.map(item => <option key={item.item_id} value={item.item_id}>{item.title || item.item_title || item.item_id} · {item.item_id}</option>)}</select></div>
                <div className="input-group"><label className="input-label">自动发货卡券</label><select className="input-ios" disabled={!enabled} value={cardId} onChange={event => setCardId(event.target.value)}><option value="">请选择卡券</option>{cards.map(card => <option key={card.id} value={card.id}>{card.name}（{card.type}）</option>)}</select></div>
                <div className="input-group"><label className="input-label">售罄后确认等待（秒）<span className="text-red-500">*</span></label><input type="number" inputMode="numeric" min={1} step={1} className="input-ios" disabled={!enabled} value={delaySeconds} placeholder="请输入等待秒数" onChange={event => setDelaySeconds(event.target.value)} /></div>
              </div>
            </> : <div className="grid gap-3 rounded-lg border border-slate-200 p-3 text-sm dark:border-slate-700 sm:grid-cols-2"><div><span className="text-slate-500">闲鱼账号</span><p className="mt-1 break-all">{rule?.account_id || '-'}</p></div><div><span className="text-slate-500">当前商品</span><p className="mt-1 break-all">{rule?.current_item_id || '-'}</p></div><div><span className="text-slate-500">自动发货卡券</span><p className="mt-1 break-all">{rule?.card_id || '-'}</p></div><div><span className="text-slate-500">售罄后确认等待</span><p className="mt-1">{rule?.delay_seconds || 60} 秒</p></div></div>}
            {rule && <div className={`rounded-lg border p-3 text-sm ${['error', 'paused'].includes(rule.status) ? 'border-red-200 bg-red-50 text-red-700' : 'border-emerald-200 bg-emerald-50 text-emerald-700'}`}><div className="flex items-center gap-2 font-medium">{['error', 'paused'].includes(rule.status) ? <AlertTriangle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}当前状态：{rule.status_text || rule.status}</div><p className="mt-1 break-all text-xs">监听商品：{rule.current_item_id || '-'}</p>{rule.last_new_item_id && <p className="mt-1 break-all text-xs">最近续售：{rule.last_old_item_id} → {rule.last_new_item_id}</p>}{(rule.last_error || rule.paused_reason) && <p className="mt-1 break-words text-xs">{rule.last_error || rule.paused_reason}</p>}</div>}
           {(eventsLoading || events.length > 0 || eventTotal === 0) && <div><h3 className="mb-2 flex items-center gap-2 text-sm font-medium"><RefreshCw className="h-4 w-4" />最近执行记录</h3>{eventsLoading ? <div className="flex items-center justify-center py-6 text-slate-500"><Loader2 className="mr-2 h-4 w-4 animate-spin" />加载记录中</div> : events.length > 0 ? <div className="space-y-2">{events.map(event => <div key={event.id} className="rounded-lg border border-slate-200 px-3 py-2 text-xs dark:border-slate-700"><div className="flex items-center justify-between gap-3"><span className="font-medium">{event.status_text || event.status}</span><span className="text-slate-400">{event.created_at ? new Date(event.created_at).toLocaleString('zh-CN') : ''}</span></div><p className="mt-1 break-all text-slate-500">{event.old_item_id}{event.new_item_id ? ` → ${event.new_item_id}` : ''}</p>{event.result_unknown && <><p className="mt-1 text-amber-600">发布结果未知，请完成对账，或标记失败以继续后续续售</p>{canConfigure && (reconcileEventId === event.id ? <div className="mt-2 flex flex-col gap-2 sm:flex-row"><select className="input-ios min-w-0 flex-1" disabled={reconciling || itemsLoading || items.length === 0} value={reconcileItemId} onChange={inputEvent => setReconcileItemId(inputEvent.target.value)}><option value="">{itemsLoading ? '正在加载商品…' : items.length === 0 ? '暂无当前在售商品' : '请选择已发布的新商品'}</option>{items.map(item => <option key={item.item_id} value={item.item_id}>{item.title || item.item_title || item.item_id} · {item.item_id}</option>)}</select><button type="button" className="btn-ios-primary inline-flex items-center justify-center gap-1 px-3 py-1" disabled={reconciling || !reconcileItemId} onClick={() => handleReconcile(event)}>{reconciling && <Loader2 className="h-3.5 w-3.5 animate-spin" />}确认对账</button><button type="button" className="btn-ios-secondary px-3 py-1" disabled={reconciling} onClick={() => { setReconcileEventId(null); setReconcileItemId('') }}>取消</button></div> : <div className="mt-2 flex flex-wrap items-center gap-2"><button type="button" className="btn-ios-secondary inline-flex items-center gap-1 px-3 py-1" onClick={() => { setReconcileEventId(event.id); setReconcileItemId(event.new_item_id && items.some(item => item.item_id === event.new_item_id) ? event.new_item_id : '') }}><CheckCircle2 className="h-3.5 w-3.5" />人工对账</button><button type="button" className="btn-ios-secondary inline-flex items-center gap-1 px-3 py-1 text-red-600 hover:text-red-700" disabled={reconciling} onClick={() => setMarkFailedEvent(event)}><AlertTriangle className="h-3.5 w-3.5" />标记失败</button></div>)}</>}{event.error_message && <p className="mt-1 break-words text-red-500">{event.error_message}</p>}</div>)}</div> : <p className="py-6 text-center text-sm text-slate-400">暂无执行记录</p>}{eventTotal > 0 && <div className="mt-3 flex flex-col gap-2 border-t border-slate-200 pt-3 text-xs dark:border-slate-700 sm:flex-row sm:items-center sm:justify-between"><span>共 {eventTotal} 条，第 {eventPage} / {eventTotalPages} 页</span><div className="flex items-center gap-2"><select className="input-ios w-auto py-1 text-xs" value={eventPageSize} onChange={event => { const size = Number(event.target.value); loadEvents(1, size) }}><option value={10}>10 条/页</option><option value={20}>20 条/页</option><option value={50}>50 条/页</option><option value={100}>100 条/页</option></select><button type="button" className="btn-ios-secondary px-2 py-1" disabled={eventPage <= 1 || eventsLoading} onClick={() => loadEvents(eventPage - 1, eventPageSize)}>上一页</button><button type="button" className="btn-ios-secondary px-2 py-1" disabled={eventPage >= eventTotalPages || eventsLoading} onClick={() => loadEvents(eventPage + 1, eventPageSize)}>下一页</button></div></div>}</div>}
          </>}
        </div>
        <div className="modal-footer flex-shrink-0"><button type="button" className="btn-ios-secondary" onClick={onClose} disabled={saving}>关闭</button>{canConfigure && reconcileEventId !== null && <button type="button" className="btn-ios-secondary" onClick={() => { const event = events.find(item => item.id === reconcileEventId); if (event) handleConfirmNotPublished(event) }} disabled={reconciling}>确认未发布</button>}{canConfigure && <button type="button" className="btn-ios-primary" onClick={handleSave} disabled={loading || saving}>{saving && <Loader2 className="h-4 w-4 animate-spin" />}{enabled ? '保存并启用' : '保存并关闭'}</button>}</div>
      </div>
      <ConfirmModal
        isOpen={markFailedEvent !== null}
        title="确认标记失败"
        message="标记后本次续售将进入重试队列，系统会继续尝试发布当前订单；已启用的规则也会继续处理后续订单。确定继续吗？"
        confirmText="标记失败"
        type="danger"
        loading={reconciling}
        onConfirm={() => { if (markFailedEvent) handleMarkFailed(markFailedEvent) }}
        onCancel={() => { if (!reconciling) setMarkFailedEvent(null) }}
      />
    </div>
  )
}

export default AutoRelistModal
