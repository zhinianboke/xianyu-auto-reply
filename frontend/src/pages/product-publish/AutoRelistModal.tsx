import { useEffect, useState } from 'react'
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw, X } from 'lucide-react'

import { getAccountDetails } from '@/api/accounts'
import { getAllCards, type CardData } from '@/api/cards'
import { getItems } from '@/api/items'
import {
  getAutoRelistEvents,
  getAutoRelistRule,
  saveAutoRelistRule,
  type AutoRelistEvent,
  type AutoRelistRule,
  type ProductMaterial,
} from '@/api/productPublish'
import { useUIStore } from '@/store/uiStore'
import type { AccountDetail, Item } from '@/types'

interface Props {
  material: ProductMaterial
  onClose: () => void
  onSaved: (rule: AutoRelistRule) => void
}

const STATUS_TEXT: Record<string, string> = {
  active: '监听中',
  disabled: '已关闭',
  waiting: '等待商品售罄',
  retrying: '等待重试',
  error: '需要处理',
  pending: '等待执行',
  publishing: '发布中',
  retry: '稍后重试',
  success: '续售成功',
  failed: '执行失败',
  skipped: '已跳过',
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
  const [rule, setRule] = useState<AutoRelistRule | null>(material.auto_relist || null)
  const [accountId, setAccountId] = useState(material.auto_relist?.account_id || '')
  const [itemId, setItemId] = useState(material.auto_relist?.current_item_id || '')
  const [cardId, setCardId] = useState(material.auto_relist?.card_id ? String(material.auto_relist.card_id) : '')
  const [enabled, setEnabled] = useState(material.auto_relist?.enabled ?? true)
  const [delaySeconds, setDelaySeconds] = useState(material.auto_relist?.delay_seconds || 60)

  useEffect(() => {
    let cancelled = false
    Promise.all([
      getAccountDetails(),
      getAllCards(),
      getAutoRelistRule(material.id),
      getAutoRelistEvents(material.id, 8),
    ]).then(([accountList, cardList, ruleResponse, eventResponse]) => {
      if (cancelled) return
      const loadedRule = ruleResponse.data || null
      const firstAccount = accountList.find(account => account.enabled)?.id || accountList[0]?.id || ''
      setAccounts(accountList)
      setCards(cardList.filter(card => card.enabled !== false && card.id))
      setRule(loadedRule)
      setEvents(eventResponse.data || [])
      setAccountId(loadedRule?.account_id || firstAccount)
      setItemId(loadedRule?.current_item_id || '')
      setCardId(loadedRule?.card_id ? String(loadedRule.card_id) : '')
      setEnabled(loadedRule?.enabled ?? true)
      setDelaySeconds(loadedRule?.delay_seconds || 60)
    }).catch(() => {
      addToast({ type: 'error', message: '自动续售配置加载失败' })
    }).finally(() => {
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [material.id])

  useEffect(() => {
    if (!accountId) {
      setItems([])
      return
    }
    let cancelled = false
    setItemsLoading(true)
    getItems(accountId).then(response => {
      if (cancelled) return
      setItems(response.data || [])
    }).catch(() => {
      if (!cancelled) addToast({ type: 'error', message: '商品列表加载失败，请先到商品管理获取商品' })
    }).finally(() => {
      if (!cancelled) setItemsLoading(false)
    })
    return () => { cancelled = true }
  }, [accountId])

  const handleSave = async () => {
    if (!accountId) return addToast({ type: 'warning', message: '请选择闲鱼账号' })
    if (!itemId) return addToast({ type: 'warning', message: '请选择当前在售商品' })
    if (!cardId) return addToast({ type: 'warning', message: '请选择自动发货卡券' })
    setSaving(true)
    try {
      const response = await saveAutoRelistRule(material.id, {
        account_id: accountId,
        current_item_id: itemId,
        card_id: Number(cardId),
        enabled,
        delay_seconds: delaySeconds,
      })
      if (!response.success || !response.data) {
        addToast({ type: 'error', message: response.message || '保存失败' })
        return
      }
      addToast({ type: 'success', message: response.message || '自动续售配置已保存' })
      onSaved(response.data)
    } catch {
      addToast({ type: 'error', message: '保存失败，请重试' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay z-50">
      <div className="modal-content max-w-2xl max-h-[92vh] flex flex-col">
        <div className="modal-header flex-shrink-0">
          <div>
            <h2 className="modal-title">自动续售</h2>
            <p className="mt-1 max-w-lg truncate text-xs text-slate-500" title={material.title}>{material.title}</p>
          </div>
          <button type="button" className="modal-close" title="关闭" onClick={onClose}><X className="w-5 h-5" /></button>
        </div>

        <div className="modal-body overflow-y-auto space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-16 text-slate-500"><Loader2 className="mr-2 h-5 w-5 animate-spin" />加载配置</div>
          ) : (
            <>
              <div className="rounded-xl border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800 dark:border-blue-800 dark:bg-blue-950/30 dark:text-blue-200">
                成交并自动发货后，系统确认旧商品已不在闲鱼在售列表，再用这份素材发布新商品，并把同一卡券绑定到新商品。
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="input-group">
                  <label className="input-label">闲鱼账号</label>
                  <select className="input-ios" value={accountId} onChange={(event) => { setAccountId(event.target.value); setItemId('') }}>
                    <option value="">请选择账号</option>
                    {accounts.map(account => <option key={account.id} value={account.id}>{account.note || account.id}{account.enabled ? '' : '（已停用）'}</option>)}
                  </select>
                </div>

                <div className="input-group">
                  <label className="input-label">当前在售商品</label>
                  <select className="input-ios" value={itemId} onChange={event => setItemId(event.target.value)} disabled={!accountId || itemsLoading}>
                    <option value="">{itemsLoading ? '正在加载商品…' : '请选择商品'}</option>
                    {items.map(item => <option key={item.item_id} value={item.item_id}>{item.title || item.item_title || item.item_id} · {item.item_id}</option>)}
                  </select>
                  {!itemsLoading && accountId && items.length === 0 && <p className="mt-1 text-xs text-amber-600">没有本地商品，请先到商品管理点击“获取闲鱼商品”。</p>}
                </div>

                <div className="input-group">
                  <label className="input-label">自动发货卡券</label>
                  <select className="input-ios" value={cardId} onChange={event => setCardId(event.target.value)}>
                    <option value="">请选择卡券</option>
                    {cards.map(card => <option key={card.id} value={card.id}>{card.name}（{card.type}）</option>)}
                  </select>
                </div>

                <div className="input-group">
                  <label className="input-label">售罄后确认等待</label>
                  <select className="input-ios" value={delaySeconds} onChange={event => setDelaySeconds(Number(event.target.value))}>
                    <option value={30}>30 秒</option>
                    <option value={60}>1 分钟</option>
                    <option value={120}>2 分钟</option>
                    <option value={300}>5 分钟</option>
                  </select>
                </div>
              </div>

              <label className="flex cursor-pointer items-center justify-between rounded-xl border border-slate-200 p-3 dark:border-slate-700">
                <div>
                  <p className="font-medium text-slate-800 dark:text-slate-100">启用自动续售</p>
                  <p className="text-xs text-slate-500">关闭后保留配置和历史记录，不再自动发布。</p>
                </div>
                <input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} className="h-5 w-5 rounded border-slate-300 text-blue-600 focus:ring-blue-500" />
              </label>

              {rule && (
                <div className={`rounded-xl border p-3 text-sm ${rule.status === 'error' ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30' : 'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/30'}`}>
                  <div className="flex items-center gap-2 font-medium">
                    {rule.status === 'error' ? <AlertTriangle className="h-4 w-4" /> : <CheckCircle2 className="h-4 w-4" />}
                    当前状态：{STATUS_TEXT[rule.status] || rule.status}
                  </div>
                  <p className="mt-1 break-all text-xs">监听商品：{rule.current_item_id}</p>
                  {rule.last_new_item_id && <p className="mt-1 break-all text-xs">最近续售：{rule.last_old_item_id} → {rule.last_new_item_id}</p>}
                  {rule.last_error && <p className="mt-1 break-words text-xs">{rule.last_error}</p>}
                </div>
              )}

              {events.length > 0 && (
                <div>
                  <h3 className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-800 dark:text-slate-100"><RefreshCw className="h-4 w-4" />最近执行记录</h3>
                  <div className="space-y-2">
                    {events.map(event => (
                      <div key={event.id} className="rounded-lg border border-slate-200 px-3 py-2 text-xs dark:border-slate-700">
                        <div className="flex items-center justify-between gap-3"><span className="font-medium">{STATUS_TEXT[event.status] || event.status}</span><span className="text-slate-400">{event.created_at ? new Date(event.created_at).toLocaleString('zh-CN') : ''}</span></div>
                        <p className="mt-1 break-all text-slate-500">{event.old_item_id}{event.new_item_id ? ` → ${event.new_item_id}` : ''}</p>
                        {event.error_message && <p className="mt-1 break-words text-red-500">{event.error_message}</p>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        <div className="modal-footer flex-shrink-0">
          <button type="button" className="btn-ios-secondary" onClick={onClose} disabled={saving}>取消</button>
          <button type="button" className="btn-ios-primary" onClick={handleSave} disabled={loading || saving}>
            {saving && <Loader2 className="h-4 w-4 animate-spin" />}{enabled ? '保存并启用' : '保存并关闭'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default AutoRelistModal
