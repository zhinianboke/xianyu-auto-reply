/**
 * 从商品列表项采集素材草稿的选择弹窗。
 * 账号下拉 → 加载该账号商品列表 → 选择商品 → 调采集接口，把草稿回填到素材表单。
 */
import { useEffect, useState } from 'react'
import { Loader2, X } from 'lucide-react'
import { getAccountDetails } from '@/api/accounts'
import { getItems } from '@/api/items'
import { collectMaterialFromItem, type CollectMaterialDraft } from '@/api/productPublish'
import { Select } from '@/components/common/Select'
import { useUIStore } from '@/store/uiStore'
import type { AccountDetail } from '@/types'
import type { Item } from '@/types'

interface Props {
  onClose: () => void
  onCollect: (draft: CollectMaterialDraft) => void
}

export function CollectFromItemModal({ onClose, onCollect }: Props) {
  const { addToast } = useUIStore()
  const [accounts, setAccounts] = useState<AccountDetail[]>([])
  const [accountId, setAccountId] = useState('')
  const [items, setItems] = useState<Item[]>([])
  const [itemId, setItemId] = useState('')
  const [loadingAccounts, setLoadingAccounts] = useState(true)
  const [loadingItems, setLoadingItems] = useState(false)
  const [collecting, setCollecting] = useState(false)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      setLoadingAccounts(true)
      try {
        const list = await getAccountDetails()
        if (cancelled) return
        setAccounts(list.filter((a) => a.enabled))
      } catch {
        if (!cancelled) addToast({ type: 'error', message: '加载账号失败，请重试' })
      } finally {
        if (!cancelled) setLoadingAccounts(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [addToast])

  useEffect(() => {
    let cancelled = false
    if (!accountId) {
      setItems([])
      setItemId('')
      return
    }
    const load = async () => {
      setLoadingItems(true)
      setItemId('')
      try {
        const res = await getItems(accountId)
        if (cancelled) return
        setItems(res.data || [])
      } catch {
        if (!cancelled) addToast({ type: 'error', message: '加载商品列表失败，请重试' })
      } finally {
        if (!cancelled) setLoadingItems(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [accountId, addToast])

  const handleConfirm = async () => {
    if (!itemId) return addToast({ type: 'warning', message: '请选择商品' })
    setCollecting(true)
    try {
      const res = await collectMaterialFromItem(itemId)
      if (!res.success || !res.data) {
        addToast({ type: 'error', message: res.message || '采集失败，请重试' })
        return
      }
      onCollect(res.data)
    } catch {
      addToast({ type: 'error', message: '采集失败，请重试' })
    } finally {
      setCollecting(false)
    }
  }

  const accountOptions = accounts.map((a) => ({
    value: a.id,
    label: a.note?.trim() || a.remark?.trim() || a.id,
  }))
  const itemOptions = items.map((it) => ({
    value: it.item_id,
    label: it.title || it.item_title || it.item_id,
  }))

  return (
    <div className="modal-overlay" style={{ zIndex: 60 }}>
      <div className="modal-content max-w-lg overflow-hidden flex flex-col">
        <div className="modal-header flex items-center justify-between flex-shrink-0">
          <h2 className="modal-title">从商品列表采集</h2>
          <button type="button" className="modal-close" title="关闭" onClick={onClose} disabled={collecting}>
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="modal-body flex-1 overflow-y-auto space-y-4">
          <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm text-blue-600 dark:text-blue-400">
            选择已有商品列表项，一键采集其标题/价格/图片/规格及商品列表配置（多数量发货/卡券/默认回复/AI提示/查询按钮）回填到当前素材。采集将覆盖当前表单内容。
          </div>

          <div className="input-group">
            <label className="input-label">账号</label>
            {loadingAccounts ? (
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <Loader2 className="w-4 h-4 animate-spin" /> 加载账号中...
              </div>
            ) : (
              <Select
                value={accountId}
                onChange={setAccountId}
                options={accountOptions}
                placeholder="选择账号"
              />
            )}
          </div>

          <div className="input-group">
            <label className="input-label">商品</label>
            {!accountId ? (
              <div className="text-sm text-slate-400">请先选择账号</div>
            ) : loadingItems ? (
              <div className="flex items-center gap-2 text-sm text-slate-400">
                <Loader2 className="w-4 h-4 animate-spin" /> 加载商品列表中...
              </div>
            ) : (
              <Select
                value={itemId}
                onChange={setItemId}
                options={itemOptions}
                placeholder="选择商品"
              />
            )}
          </div>
        </div>

        <div className="modal-footer flex-shrink-0 flex justify-end gap-2">
          <button type="button" className="btn-ios-secondary" onClick={onClose} disabled={collecting}>取消</button>
          <button type="button" className="btn-ios-primary" onClick={handleConfirm} disabled={collecting || !itemId}>
            {collecting && <Loader2 className="w-4 h-4 animate-spin" />}
            {collecting ? '采集中...' : '采集并回填'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default CollectFromItemModal
