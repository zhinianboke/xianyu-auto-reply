/** 文本与API关键词共用商品选择：新建搜索、多选和全选，编辑单选。 */
import { Search } from 'lucide-react'
import type { Dispatch, SetStateAction } from 'react'
import type { Item } from '@/types'

interface Props {
  items: Item[]
  multiple: boolean
  value: string[]
  onChange: Dispatch<SetStateAction<string[]>>
  search: string
  onSearchChange: (value: string) => void
  disabled?: boolean
}

export function KeywordItemSelector({ items, multiple, value, onChange, search, onSearchChange, disabled = false }: Props) {
  const searchText = search.toLowerCase()
  const filteredItems = items.filter(item => !searchText
    || (item.title || '').toLowerCase().includes(searchText) || item.item_id.includes(searchText))
  const allSelected = filteredItems.length > 0 && filteredItems.every(item => value.includes(item.item_id))
  const selectedItemId = value[0] || ''

  return <fieldset disabled={disabled} className="min-w-0 w-full max-w-full">
    <label className="input-label">商品ID（可选）</label>
    {!multiple ? <>
      <select value={selectedItemId} onChange={event => onChange(event.target.value ? [event.target.value] : [])}
        className="input-ios min-w-0 max-w-full truncate" aria-label="绑定商品">
        <option value="">通用关键词（所有商品）</option>
        {selectedItemId && !items.some(item => item.item_id === selectedItemId)
          && <option value={selectedItemId}>{selectedItemId}（当前绑定商品）</option>}
        {items.map(item => <option key={item.item_id} value={item.item_id}>{item.item_id} - {item.title}</option>)}
      </select>
      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">绑定商品ID后，此关键词仅在该商品对话中生效</p>
    </> : <>
      <div className="relative mb-2">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input type="text" value={search} onChange={event => onSearchChange(event.target.value)}
          placeholder="搜索商品..." aria-label="搜索商品" className="input-ios pl-9 py-2 text-sm" />
      </div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs text-slate-500 dark:text-slate-400">{value.length === 0 ? '未选择' : `已选 ${value.length} 个`}</span>
        <button type="button" disabled={filteredItems.length === 0} className="text-xs text-primary hover:underline disabled:opacity-50"
          onClick={() => onChange(allSelected ? [] : filteredItems.map(item => item.item_id))}>
          {allSelected ? '取消全选' : '全选商品'}
        </button>
      </div>
      <div className="min-w-0 max-w-full border border-slate-200 dark:border-slate-700 rounded-lg max-h-32 overflow-x-hidden overflow-y-auto">
        <label className="flex min-w-0 items-center gap-3 p-2 hover:bg-slate-50 dark:hover:bg-slate-800 cursor-pointer border-b border-slate-100 dark:border-slate-700">
          <input type="checkbox" checked={value.length === 0} onChange={() => onChange([])}
            className="w-4 h-4 shrink-0 rounded border-slate-300 accent-[rgb(var(--color-primary))]" />
          <span className="min-w-0 flex-1 truncate text-sm text-slate-700 dark:text-slate-300">通用关键词（所有商品）</span>
        </label>
        {filteredItems.map(item => <label key={item.item_id}
          className="flex min-w-0 items-center gap-3 p-2 hover:bg-slate-50 dark:hover:bg-slate-800 cursor-pointer border-b border-slate-100 dark:border-slate-700 last:border-b-0">
          <input type="checkbox" checked={value.includes(item.item_id)}
            onChange={() => onChange(previous => previous.includes(item.item_id)
              ? previous.filter(id => id !== item.item_id) : [...previous, item.item_id])}
            className="w-4 h-4 shrink-0 rounded border-slate-300 accent-[rgb(var(--color-primary))]" />
          <span className="min-w-0 flex-1 text-sm text-slate-700 dark:text-slate-300 truncate"
            title={`${item.item_id} - ${item.title || ''}`}>{item.item_id} - {item.title}</span>
        </label>)}
        {filteredItems.length === 0 && <p className="p-3 text-center text-xs text-slate-500 dark:text-slate-400">
          {search ? '没有匹配的商品' : '当前账号暂无商品'}
        </p>}
      </div>
      <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">{value.length === 0
        ? '未选择商品，将创建通用关键词' : `已选择 ${value.length} 个商品，将创建 ${value.length} 条关键词`}</p>
    </>}
  </fieldset>
}
