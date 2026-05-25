/**
 * 禁止发货规则设置弹窗组件
 *
 * 功能：
 * 1. 展示所有可用的禁止发货规则（卡片列表形式）
 * 2. 每条规则独立配置：开关、原因、主动关闭订单、关闭后只发卡券、排除商品列表
 * 3. 调用后端 API 加载和保存规则配置
 */
import { useEffect, useRef, useState } from 'react'
import {
  X, Loader2, Ban, ShieldCheck,
} from 'lucide-react'
import { getDeliveryBlockRules, updateDeliveryBlockRules, type DeliveryBlockRuleItem } from '@/api/accounts'
import { getItems } from '@/api/items'
import type { Item } from '@/types'
import { getApiErrorMessage } from '@/utils/request'
import { useUIStore } from '@/store/uiStore'
import { RuleCard } from './RuleCard'

interface Props {
  accountId: string
  accountDisplayId: string
  onClose: () => void
}

export function DeliveryBlockRulesModal({ accountId, accountDisplayId, onClose }: Props) {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [rules, setRules] = useState<DeliveryBlockRuleItem[]>([])
  const [items, setItems] = useState<Item[]>([])

  // 每条规则的排除商品下拉状态
  const [openDropdownCode, setOpenDropdownCode] = useState<string | null>(null)
  const [itemSearch, setItemSearch] = useState('')
  const dropdownRef = useRef<HTMLDivElement | null>(null)

  // 加载规则和商品列表
  useEffect(() => {
    loadData()
  }, [accountId])

  // 点击外部关闭下拉
  useEffect(() => {
    if (!openDropdownCode) return
    const handleClickOutside = (event: MouseEvent) => {
      const node = dropdownRef.current
      if (node && !node.contains(event.target as Node)) {
        setOpenDropdownCode(null)
        setItemSearch('')
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [openDropdownCode])

  const loadData = async () => {
    setLoading(true)
    try {
      const [rulesRes, itemsRes] = await Promise.all([
        getDeliveryBlockRules(accountId),
        getItems(accountId).catch(() => ({ data: [] })),
      ])
      if (rulesRes.success && rulesRes.data) {
        setRules(rulesRes.data)
      } else {
        addToast({ type: 'error', message: rulesRes.message || '加载规则失败' })
      }
      setItems(itemsRes.data || [])
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载数据失败') })
    } finally {
      setLoading(false)
    }
  }

  // 更新某条规则的字段
  const updateRule = (ruleCode: string, updates: Partial<DeliveryBlockRuleItem>) => {
    setRules(prev => prev.map(r => {
      if (r.rule_code !== ruleCode) return r
      const updated = { ...r, ...updates }
      // 联动：auto_close 关闭时 only_card 强制关闭
      if ('auto_close_order' in updates && !updates.auto_close_order) {
        updated.only_card_after_close = false
      }
      return updated
    }))
  }

  // 切换排除商品
  const toggleExcludedItem = (ruleCode: string, itemId: string) => {
    setRules(prev => prev.map(r => {
      if (r.rule_code !== ruleCode) return r
      const ids = r.excluded_item_ids.includes(itemId)
        ? r.excluded_item_ids.filter(id => id !== itemId)
        : [...r.excluded_item_ids, itemId]
      return { ...r, excluded_item_ids: ids }
    }))
  }

  // 移除排除商品
  const removeExcludedItem = (ruleCode: string, itemId: string) => {
    setRules(prev => prev.map(r => {
      if (r.rule_code !== ruleCode) return r
      return { ...r, excluded_item_ids: r.excluded_item_ids.filter(id => id !== itemId) }
    }))
  }

  // 保存
  const handleSave = async () => {
    // 校验
    for (const rule of rules) {
      if (rule.enabled && rule.block_reason && rule.block_reason.length > 500) {
        addToast({ type: 'warning', message: `规则「${rule.rule_name}」的禁止发货原因不能超过500字` })
        return
      }
    }

    setSaving(true)
    try {
      const payload = rules.map(r => ({
        rule_code: r.rule_code,
        enabled: r.enabled,
        priority: r.priority,
        block_reason: r.enabled ? (r.block_reason?.trim() || null) : null,
        auto_close_order: r.enabled ? r.auto_close_order : false,
        only_card_after_close: r.enabled && r.auto_close_order ? r.only_card_after_close : false,
        excluded_item_ids: r.enabled ? r.excluded_item_ids.filter(Boolean) : [],
        config: r.config || null,
      }))
      const result = await updateDeliveryBlockRules(accountId, payload)
      if (result.success) {
        addToast({ type: 'success', message: '禁止发货规则已保存' })
        onClose()
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '保存失败') })
    } finally {
      setSaving(false)
    }
  }

  // 过滤商品
  const getFilteredItems = () => {
    const kw = itemSearch.trim().toLowerCase()
    if (!kw) return items
    return items.filter(it =>
      (it.item_id || '').toLowerCase().includes(kw)
      || (it.title || it.item_title || '').toLowerCase().includes(kw)
    )
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content max-w-lg max-h-[90vh] flex flex-col">
        <div className="modal-header">
          <h2 className="modal-title flex items-center gap-2">
            <Ban className="w-4 h-4 text-red-500" />
            禁止发货规则设置
          </h2>
          <button onClick={onClose} className="modal-close">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="modal-body flex-1 overflow-y-auto space-y-4">
          {/* 账号信息 */}
          <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 text-sm text-blue-700 dark:text-blue-300">
            <p>账号: <span className="font-medium">{accountDisplayId}</span></p>
            <p className="text-xs mt-1 opacity-80">按优先级顺序执行规则，首条命中即拦截</p>
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
              <span className="ml-2 text-sm text-slate-500">加载规则配置中...</span>
            </div>
          ) : rules.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-slate-400">
              <ShieldCheck className="w-8 h-8 mb-2" />
              <p className="text-sm">暂无可用规则</p>
            </div>
          ) : (
            <div className="space-y-3">
              {rules.map((rule) => (
                <RuleCard
                  key={rule.rule_code}
                  rule={rule}
                  items={items}
                  openDropdownCode={openDropdownCode}
                  itemSearch={itemSearch}
                  dropdownRef={dropdownRef}
                  getFilteredItems={getFilteredItems}
                  onUpdate={(updates) => updateRule(rule.rule_code, updates)}
                  onToggleExcluded={(itemId) => toggleExcludedItem(rule.rule_code, itemId)}
                  onRemoveExcluded={(itemId) => removeExcludedItem(rule.rule_code, itemId)}
                  onOpenDropdown={() => { setOpenDropdownCode(rule.rule_code); setItemSearch('') }}
                  onCloseDropdown={() => { setOpenDropdownCode(null); setItemSearch('') }}
                  onSearchChange={setItemSearch}
                />
              ))}
            </div>
          )}
        </div>

        <div className="modal-footer">
          <button type="button" onClick={onClose} className="btn-ios-secondary" disabled={saving}>
            取消
          </button>
          <button
            onClick={handleSave}
            className="btn-ios-primary"
            disabled={saving || loading}
          >
            {saving ? (
              <span className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                保存中...
              </span>
            ) : '保存'}
          </button>
        </div>
      </div>
    </div>
  )
}
