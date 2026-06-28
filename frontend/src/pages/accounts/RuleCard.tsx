/**
 * 单条禁止发货规则卡片组件
 *
 * 功能：
 * 1. 展示规则开关、原因、主动关闭订单、关闭后只发卡券
 * 2. 排除商品列表选择器
 */
import { type RefObject } from 'react'
import {
  X, Package, Search, ChevronDown, ChevronUp,
  CheckSquare, Square,
} from 'lucide-react'
import type { DeliveryBlockRuleItem } from '@/api/accounts'
import type { Item } from '@/types'

interface Props {
  rule: DeliveryBlockRuleItem
  items: Item[]
  openDropdownCode: string | null
  itemSearch: string
  dropdownRef: RefObject<HTMLDivElement | null>
  getFilteredItems: () => Item[]
  onUpdate: (updates: Partial<DeliveryBlockRuleItem>) => void
  onToggleExcluded: (itemId: string) => void
  onRemoveExcluded: (itemId: string) => void
  onOpenDropdown: () => void
  onCloseDropdown: () => void
  onSearchChange: (value: string) => void
}

export function RuleCard({
  rule, items, openDropdownCode, itemSearch, dropdownRef,
  getFilteredItems, onUpdate, onToggleExcluded, onRemoveExcluded,
  onOpenDropdown, onCloseDropdown, onSearchChange,
}: Props) {
  const isDropdownOpen = openDropdownCode === rule.rule_code
  const filtered = isDropdownOpen ? getFilteredItems() : []

  return (
    <div className={`rounded-lg border transition-colors ${
      rule.enabled
        ? 'border-red-200 dark:border-red-800/50 bg-red-50/30 dark:bg-red-900/10'
        : 'border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800'
    }`}>
      {/* 规则头部：名称 + 开关 */}
      <div className="flex items-center justify-between px-4 py-3">
        <div className="flex-1">
          <div className="text-sm font-medium text-slate-700 dark:text-slate-200">
            {rule.rule_name}
          </div>
          {rule.rule_description && (
            <div className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              {rule.rule_description}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={() => onUpdate({ enabled: !rule.enabled })}
          className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0 ${
            rule.enabled ? 'bg-red-500' : 'bg-slate-300 dark:bg-slate-600'
          }`}
          aria-pressed={rule.enabled}
        >
          <span className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
            rule.enabled ? 'translate-x-6' : 'translate-x-1'
          }`} />
        </button>
      </div>

      {/* 规则详细配置（仅开启时展开） */}
      {rule.enabled && (
        <div className="px-4 pb-4 space-y-3 border-t border-slate-100 dark:border-slate-700/50 pt-3">
          {/* 禁止发货原因 */}
          <div>
            <label className="text-xs font-medium text-slate-600 dark:text-slate-300">禁止发货原因</label>
            <textarea
              value={rule.block_reason}
              onChange={(e) => onUpdate({ block_reason: e.target.value.slice(0, 500) })}
              className="input-ios min-h-[72px] mt-1 text-sm"
              rows={3}
              maxLength={500}
              placeholder="命中时发送给买家的消息（可选，最多500字）"
            />
            <div className="flex justify-between mt-0.5">
              <span className="text-xs text-slate-400">留空则不发送消息给买家</span>
              <span className="text-xs text-slate-400">{rule.block_reason.length}/500</span>
            </div>
          </div>

          {/* 规则专属参数配置 */}
          <RuleConfigSection rule={rule} onUpdate={onUpdate} />

          {/* 排除商品列表 */}
          <div>
            <label className="text-xs font-medium text-slate-600 dark:text-slate-300 flex items-center gap-1">
              <Package className="w-3 h-3 text-blue-500" />
              排除商品（命中后跳过本规则）
            </label>
            <div className="relative mt-1" ref={isDropdownOpen ? dropdownRef as React.RefObject<HTMLDivElement> : undefined}>
              <button
                type="button"
                onClick={() => isDropdownOpen ? onCloseDropdown() : onOpenDropdown()}
                className="w-full flex items-center justify-between rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 text-xs hover:border-blue-300 dark:hover:border-blue-600 bg-white dark:bg-slate-800 transition-colors"
              >
                <span className={rule.excluded_item_ids.length > 0 ? 'text-slate-700 dark:text-slate-200' : 'text-slate-400'}>
                  {rule.excluded_item_ids.length > 0
                    ? `已选 ${rule.excluded_item_ids.length} 个商品`
                    : '点击选择排除商品（可多选）'}
                </span>
                {isDropdownOpen
                  ? <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
                  : <ChevronDown className="w-3.5 h-3.5 text-slate-400" />}
              </button>

              {/* 下拉面板 */}
              {isDropdownOpen && (
                <div className="absolute z-20 left-0 right-0 mt-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 shadow-lg">
                  <div className="p-2 border-b border-slate-100 dark:border-slate-700">
                    <div className="relative">
                      <Search className="absolute left-2 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-400" />
                      <input
                        type="text"
                        value={itemSearch}
                        onChange={(e) => onSearchChange(e.target.value)}
                        placeholder="按商品ID或标题搜索..."
                        className="input-ios text-xs pl-7 py-1.5 w-full"
                        autoFocus
                      />
                    </div>
                    <div className="flex items-center justify-between mt-1.5 text-xs text-slate-500">
                      <span>共 {filtered.length} 个 · 已选 {rule.excluded_item_ids.length} 个</span>
                    </div>
                  </div>
                  <div className="max-h-48 overflow-y-auto">
                    {items.length === 0 ? (
                      <div className="flex flex-col items-center justify-center py-4 text-slate-400">
                        <Package className="w-5 h-5 mb-1" />
                        <p className="text-xs">该账号暂无商品</p>
                      </div>
                    ) : filtered.length === 0 ? (
                      <div className="flex flex-col items-center justify-center py-4 text-slate-400">
                        <Search className="w-4 h-4 mb-1" />
                        <p className="text-xs">无匹配结果</p>
                      </div>
                    ) : filtered.map(item => {
                      const checked = rule.excluded_item_ids.includes(item.item_id)
                      return (
                        <div
                          key={item.item_id}
                          onClick={() => onToggleExcluded(item.item_id)}
                          className={`flex items-center gap-2 px-3 py-1.5 border-b border-slate-100 dark:border-slate-700 last:border-b-0 cursor-pointer transition-colors ${
                            checked ? 'bg-blue-50 dark:bg-blue-900/20' : 'hover:bg-slate-50 dark:hover:bg-slate-700/50'
                          }`}
                        >
                          {checked
                            ? <CheckSquare className="w-3.5 h-3.5 text-blue-600 dark:text-blue-400 flex-shrink-0" />
                            : <Square className="w-3.5 h-3.5 text-slate-400 flex-shrink-0" />}
                          <div className="flex-1 min-w-0">
                            <p className="text-xs font-medium text-slate-700 dark:text-slate-200 truncate">
                              {item.title || item.item_title || item.item_id}
                            </p>
                            <p className="text-[10px] text-slate-500 truncate">
                              ID: {item.item_id}
                              {(item.price || item.item_price) ? ` · ¥${item.price || item.item_price}` : ''}
                            </p>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>

            {/* 已选 chip */}
            {rule.excluded_item_ids.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1 max-h-20 overflow-y-auto">
                {rule.excluded_item_ids.map(id => {
                  const matched = items.find(it => it.item_id === id)
                  const label = matched?.title || matched?.item_title || id
                  return (
                    <span
                      key={id}
                      className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300 text-[10px]"
                      title={`ID: ${id}`}
                    >
                      <span className="max-w-[120px] truncate">{label}</span>
                      <button
                        type="button"
                        onClick={() => onRemoveExcluded(id)}
                        className="p-0.5 hover:bg-blue-200/60 dark:hover:bg-blue-800/60 rounded"
                      >
                        <X className="w-2.5 h-2.5" />
                      </button>
                    </span>
                  )
                })}
              </div>
            )}
          </div>

          {/* 主动关闭订单 */}
          <div className="flex items-center justify-between rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2">
            <div>
              <p className="text-xs font-medium text-slate-700 dark:text-slate-200">命中后主动关闭订单</p>
              <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">
                调用闲鱼接口主动关闭订单
              </p>
            </div>
            <button
              type="button"
              onClick={() => onUpdate({ auto_close_order: !rule.auto_close_order })}
              className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors flex-shrink-0 ${
                rule.auto_close_order ? 'bg-red-500' : 'bg-slate-300 dark:bg-slate-600'
              }`}
              aria-pressed={rule.auto_close_order}
            >
              <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                rule.auto_close_order ? 'translate-x-[18px]' : 'translate-x-[3px]'
              }`} />
            </button>
          </div>

          {/* 关闭后只发卡券（嵌套依赖） */}
          {rule.auto_close_order && (
            <div className="flex items-center justify-between rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 ml-3">
              <div className="flex-1 mr-2">
                <p className="text-xs font-medium text-slate-700 dark:text-slate-200">关闭订单后继续发送卡券</p>
                <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-0.5">
                  跳过发货/免拼接口，仅发送卡券
                </p>
                <p className="text-[10px] text-amber-600 dark:text-amber-400 mt-0.5">
                  ⚠️ 仅自有卡券生效，对接卡券自动跳过
                </p>
              </div>
              <button
                type="button"
                onClick={() => onUpdate({ only_card_after_close: !rule.only_card_after_close })}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors flex-shrink-0 ${
                  rule.only_card_after_close ? 'bg-blue-500' : 'bg-slate-300 dark:bg-slate-600'
                }`}
                aria-pressed={rule.only_card_after_close}
              >
                <span className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white transition-transform ${
                  rule.only_card_after_close ? 'translate-x-[18px]' : 'translate-x-[3px]'
                }`} />
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/**
 * 规则专属参数配置区域
 * 根据 rule_code 展示不同的配置项
 */
function RuleConfigSection({ rule, onUpdate }: { rule: DeliveryBlockRuleItem; onUpdate: (updates: Partial<DeliveryBlockRuleItem>) => void }) {
  const config = rule.config || {}

  const updateConfig = (key: string, value: any) => {
    onUpdate({ config: { ...config, [key]: value } })
  }

  switch (rule.rule_code) {
    case 'buyer_credit_zero':
      return (
        <div className="rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2">
          <label className="text-xs font-medium text-slate-600 dark:text-slate-300">评价数阈值</label>
          <div className="flex items-center gap-2 mt-1">
            <input
              type="number"
              min={0}
              max={100}
              value={config.threshold ?? 0}
              onChange={(e) => updateConfig('threshold', Math.max(0, parseInt(e.target.value) || 0))}
              className="input-ios text-sm w-20"
            />
            <span className="text-xs text-slate-500">买家评价数 ≤ 此值时拦截（默认0）</span>
          </div>
        </div>
      )

    case 'buyer_has_order':
      return (
        <div className="rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2">
          <label className="text-xs font-medium text-slate-600 dark:text-slate-300">判断范围</label>
          <div className="flex items-center gap-4 mt-1.5">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="radio"
                name={`scope_${rule.rule_code}`}
                checked={!config.same_item_only}
                onChange={() => updateConfig('same_item_only', false)}
                className="w-3.5 h-3.5 text-blue-600"
              />
              <span className="text-xs text-slate-700 dark:text-slate-200">整个账户</span>
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="radio"
                name={`scope_${rule.rule_code}`}
                checked={!!config.same_item_only}
                onChange={() => updateConfig('same_item_only', true)}
                className="w-3.5 h-3.5 text-blue-600"
              />
              <span className="text-xs text-slate-700 dark:text-slate-200">仅同商品</span>
            </label>
          </div>
          <p className="text-[10px] text-slate-500 mt-1">
            {config.same_item_only
              ? '仅当买家在同一商品下有其他订单时拦截'
              : '买家在该卖家下有任何其他订单时拦截'}
          </p>
        </div>
      )

    case 'buyer_has_order_global':
      return (
        <div className="rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2">
          <label className="text-xs font-medium text-slate-600 dark:text-slate-300">判断范围</label>
          <div className="flex items-center gap-4 mt-1.5">
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="radio"
                name={`scope_${rule.rule_code}`}
                checked={!config.same_item_only}
                onChange={() => updateConfig('same_item_only', false)}
                className="w-3.5 h-3.5 text-blue-600"
              />
              <span className="text-xs text-slate-700 dark:text-slate-200">同用户全部账号</span>
            </label>
            <label className="flex items-center gap-1.5 cursor-pointer">
              <input
                type="radio"
                name={`scope_${rule.rule_code}`}
                checked={!!config.same_item_only}
                onChange={() => updateConfig('same_item_only', true)}
                className="w-3.5 h-3.5 text-blue-600"
              />
              <span className="text-xs text-slate-700 dark:text-slate-200">仅同商品</span>
            </label>
          </div>
          <p className="text-[10px] text-slate-500 mt-1">
            {config.same_item_only
              ? '仅当买家在同用户名下任一账号的同一商品下有其他订单时拦截'
              : '买家在同用户名下任一账号有任何其他订单时拦截'}
          </p>
        </div>
      )

    case 'buyer_unconfirmed':
      return (
        <div className="rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-2 space-y-2">
          <div>
            <label className="text-xs font-medium text-slate-600 dark:text-slate-300">未确认收货订单数阈值</label>
            <div className="flex items-center gap-2 mt-1">
              <input
                type="number"
                min={1}
                max={100}
                value={config.min_count ?? 1}
                onChange={(e) => updateConfig('min_count', Math.max(1, parseInt(e.target.value) || 1))}
                className="input-ios text-sm w-20"
              />
              <span className="text-xs text-slate-500">未确认收货订单数 ≥ 此值时拦截（默认1）</span>
            </div>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-600 dark:text-slate-300">判断范围</label>
            <div className="flex items-center gap-4 mt-1.5">
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name={`scope_${rule.rule_code}`}
                  checked={!config.same_item_only}
                  onChange={() => updateConfig('same_item_only', false)}
                  className="w-3.5 h-3.5 text-blue-600"
                />
                <span className="text-xs text-slate-700 dark:text-slate-200">整个账户</span>
              </label>
              <label className="flex items-center gap-1.5 cursor-pointer">
                <input
                  type="radio"
                  name={`scope_${rule.rule_code}`}
                  checked={!!config.same_item_only}
                  onChange={() => updateConfig('same_item_only', true)}
                  className="w-3.5 h-3.5 text-blue-600"
                />
                <span className="text-xs text-slate-700 dark:text-slate-200">仅同商品</span>
              </label>
            </div>
            <p className="text-[10px] text-slate-500 mt-1">
              {config.same_item_only
                ? '仅当买家在同一商品下有未确认收货订单时拦截'
                : '买家在该卖家下有任何未确认收货订单时拦截'}
            </p>
          </div>
        </div>
      )

    default:
      return null
  }
}
