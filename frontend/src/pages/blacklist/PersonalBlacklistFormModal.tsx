/**
 * 个人黑名单新建弹窗
 * 
 * 功能：
 * - 账号ID下拉框（非必填，显示用户所有账号）
 * - 买家ID输入框（必填，英文逗号分隔）
 * - 商品ID下拉框（选择账号后显示该账号商品，支持ID和名称筛选）
 * - 拉黑原因
 * - 是否启用
 * - 切换账号时清空商品ID
 */
import { useState, useEffect, useMemo, useRef } from 'react'
import { X } from 'lucide-react'
import { getAccountDetails } from '@/api/accounts'
import { getItems } from '@/api/items'
import { createPersonalBlacklist } from '@/api/blacklist'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/request'
import type { AccountDetail, Item } from '@/types'

interface Props {
  onClose: () => void
  onSuccess: () => void
}

export function PersonalBlacklistFormModal({ onClose, onSuccess }: Props) {
  const { addToast } = useUIStore()
  const [submitting, setSubmitting] = useState(false)

  // 表单数据
  const [accountId, setAccountId] = useState<string>('')
  const [buyerIds, setBuyerIds] = useState('')
  const [itemId, setItemId] = useState<string>('')
  const [reason, setReason] = useState('')
  const [isEnabled, setIsEnabled] = useState(true)

  // 下拉数据
  const [accounts, setAccounts] = useState<AccountDetail[]>([])
  const [items, setItems] = useState<Item[]>([])
  const [loadingItems, setLoadingItems] = useState(false)

  // 商品筛选
  const [itemSearch, setItemSearch] = useState('')
  const [itemDropdownOpen, setItemDropdownOpen] = useState(false)
  const itemDropdownRef = useRef<HTMLDivElement>(null)

  // 点击外部关闭下拉
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (itemDropdownRef.current && !itemDropdownRef.current.contains(e.target as Node)) {
        setItemDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // 加载账号列表
  useEffect(() => {
    const load = async () => {
      try {
        const data = await getAccountDetails()
        setAccounts(data)
      } catch (error) {
        addToast({ type: 'error', message: getApiErrorMessage(error, '加载账号列表失败') })
      }
    }
    load()
  }, [addToast])

  // 切换账号时加载商品并清空商品ID
  useEffect(() => {
    setItemId('')
    setItemSearch('')
    if (!accountId) {
      setItems([])
      return
    }
    const loadItems = async () => {
      setLoadingItems(true)
      try {
        const res = await getItems(accountId)
        if (res.success) {
          setItems(res.data)
        }
      } catch (error) {
        addToast({ type: 'error', message: getApiErrorMessage(error, '加载商品列表失败') })
      } finally {
        setLoadingItems(false)
      }
    }
    loadItems()
  }, [accountId, addToast])

  // 商品筛选（支持ID和名称）
  const filteredItems = useMemo(() => {
    if (!itemSearch) return items
    const keyword = itemSearch.toLowerCase()
    return items.filter(
      (item) =>
        (item.item_id || '').toLowerCase().includes(keyword) ||
        (item.title || item.item_title || '').toLowerCase().includes(keyword)
    )
  }, [items, itemSearch])

  const handleSubmit = async () => {
    if (!buyerIds.trim()) {
      addToast({ type: 'error', message: '买家ID不能为空' })
      return
    }
    setSubmitting(true)
    try {
      const res = await createPersonalBlacklist({
        account_id: accountId || null,
        buyer_ids: buyerIds.trim(),
        item_id: itemId || null,
        reason: reason || null,
        is_enabled: isEnabled,
      })
      if (res.success) {
        addToast({ type: 'success', message: res.message || '创建成功' })
        onSuccess()
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '创建失败') })
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-slate-800 rounded-lg shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        {/* 头部 */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-200 dark:border-slate-700">
          <h3 className="text-lg font-medium text-slate-800 dark:text-slate-100">新建黑名单</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 表单 */}
        <div className="px-6 py-4 space-y-4">
          {/* 账号ID */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              账号ID <span className="text-slate-400 text-xs">（非必填）</span>
            </label>
            <select
              value={accountId}
              onChange={(e) => setAccountId(e.target.value)}
              className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">不选择</option>
              {accounts.map((acc) => (
                <option key={acc.id} value={acc.id}>
                  {acc.id}{acc.note ? ` (${acc.note})` : ''}
                </option>
              ))}
            </select>
          </div>

          {/* 买家ID */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              买家ID <span className="text-red-500">*</span>
            </label>
            <textarea
              value={buyerIds}
              onChange={(e) => setBuyerIds(e.target.value)}
              placeholder="输入买家ID，多个请用英文逗号分隔"
              rows={3}
              className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500 resize-none"
            />
            <p className="mt-1 text-xs text-slate-400 dark:text-slate-500">
              多个买家ID请用英文逗号（,）分隔，例如：buyer1,buyer2,buyer3
            </p>
          </div>

          {/* 商品ID（仅选择了账号才显示） */}
          {accountId && (
            <div ref={itemDropdownRef}>
              <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
                商品ID <span className="text-slate-400 text-xs">（非必填）</span>
              </label>
              {loadingItems ? (
                <p className="text-xs text-slate-400">加载商品中...</p>
              ) : (
                <div className="relative">
                  {/* 已选中显示 / 点击展开 */}
                  <div
                    onClick={() => setItemDropdownOpen(!itemDropdownOpen)}
                    className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 cursor-pointer flex items-center justify-between min-h-[38px]"
                  >
                    {itemId ? (
                      <span className="truncate">
                        {itemId} - {items.find((i) => i.item_id === itemId)?.title || items.find((i) => i.item_id === itemId)?.item_title || '未命名'}
                      </span>
                    ) : (
                      <span className="text-slate-400 dark:text-slate-500">点击选择商品</span>
                    )}
                    <div className="flex items-center gap-1 flex-shrink-0">
                      {itemId && (
                        <button
                          type="button"
                          onClick={(e) => { e.stopPropagation(); setItemId(''); }}
                          className="p-0.5 hover:bg-slate-200 dark:hover:bg-slate-600 rounded"
                        >
                          <X className="w-3.5 h-3.5 text-slate-400" />
                        </button>
                      )}
                      <svg className={`w-4 h-4 text-slate-400 transition-transform ${itemDropdownOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </div>
                  </div>

                  {/* 下拉面板 */}
                  {itemDropdownOpen && (
                    <div className="absolute z-50 mt-1 w-full bg-white dark:bg-slate-700 border border-slate-300 dark:border-slate-600 rounded-md shadow-lg">
                      {/* 搜索框 */}
                      <div className="p-2 border-b border-slate-200 dark:border-slate-600">
                        <input
                          type="text"
                          placeholder="搜索商品ID或名称..."
                          value={itemSearch}
                          onChange={(e) => setItemSearch(e.target.value)}
                          className="w-full px-2.5 py-1.5 text-sm border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
                          autoFocus
                        />
                      </div>
                      {/* 选项列表 */}
                      <div className="max-h-48 overflow-y-auto">
                        {filteredItems.length === 0 ? (
                          <div className="px-3 py-2 text-xs text-slate-400 text-center">无匹配商品</div>
                        ) : (
                          filteredItems.map((item) => (
                            <div
                              key={item.item_id}
                              onClick={() => { setItemId(item.item_id); setItemDropdownOpen(false); setItemSearch(''); }}
                              className={`px-3 py-2 text-sm cursor-pointer hover:bg-blue-50 dark:hover:bg-blue-900/20 ${
                                itemId === item.item_id ? 'bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400' : 'text-slate-700 dark:text-slate-200'
                              }`}
                            >
                              <span className="font-mono text-xs text-slate-500 dark:text-slate-400">{item.item_id}</span>
                              <span className="ml-2">{item.title || item.item_title || '未命名'}</span>
                            </div>
                          ))
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* 拉黑原因 */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1">
              拉黑原因
            </label>
            <input
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="输入拉黑原因（可选）"
              className="w-full px-3 py-2 text-sm border border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-700 text-slate-700 dark:text-slate-200 focus:outline-none focus:ring-1 focus:ring-blue-500"
            />
          </div>

          {/* 是否启用 */}
          <div className="flex items-center gap-3">
            <label className="text-sm font-medium text-slate-700 dark:text-slate-300">是否启用</label>
            <button
              type="button"
              onClick={() => setIsEnabled(!isEnabled)}
              className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                isEnabled ? 'bg-blue-500' : 'bg-slate-300 dark:bg-slate-600'
              }`}
            >
              <span
                className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                  isEnabled ? 'translate-x-6' : 'translate-x-1'
                }`}
              />
            </button>
          </div>
        </div>

        {/* 底部按钮 */}
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-200 dark:border-slate-700">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-600 dark:text-slate-300 border border-slate-300 dark:border-slate-600 rounded-md hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
          >
            取消
          </button>
          <button
            onClick={handleSubmit}
            disabled={submitting}
            className="px-4 py-2 text-sm bg-blue-500 text-white rounded-md hover:bg-blue-600 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? '保存中...' : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}
