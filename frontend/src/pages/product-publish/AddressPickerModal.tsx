/**
 * 宝贝所在地选择弹窗。
 * 按闲鱼卖家工作台抓包调用高德 inputtips，候选数量和内容完全取接口返回数据。
 */
import { useEffect, useRef, useState } from 'react'
import { Loader2, MapPin, Search, X } from 'lucide-react'
import { searchAmapInputTips, type AmapInputTip } from '@/api/publishAddresses'

interface AddressPickerModalProps {
  open: boolean
  currentValue: string
  onSelect: (address: string, expectedText?: string) => void
  onClose: () => void
}

export function AddressPickerModal({ open, currentValue, onSelect, onClose }: AddressPickerModalProps) {
  const [keyword, setKeyword] = useState(currentValue)
  const [tips, setTips] = useState<AmapInputTip[]>([])
  const [loading, setLoading] = useState(false)
  const [searched, setSearched] = useState(false)
  const [error, setError] = useState('')
  const requestVersion = useRef(0)
  const debounceTimer = useRef<number | null>(null)

  const loadTips = async (query: string) => {
    const normalizedQuery = query.trim()
    if (!normalizedQuery) {
      requestVersion.current += 1
      setTips([])
      setLoading(false)
      setSearched(false)
      setError('')
      return
    }

    const version = ++requestVersion.current
    setLoading(true)
    setSearched(true)
    setError('')
    try {
      const result = await searchAmapInputTips(normalizedQuery)
      if (version !== requestVersion.current) return
      if (!result.success || !result.data) {
        setError(result.message || '所在地搜索失败')
        setTips([])
        return
      }
      setTips(result.data.tips || [])
    } catch {
      if (version !== requestVersion.current) return
      setError('所在地搜索请求失败，请稍后重试')
      setTips([])
    } finally {
      if (version === requestVersion.current) setLoading(false)
    }
  }

  useEffect(() => {
    if (!open) return
    setKeyword(currentValue)
    setTips([])
    setSearched(false)
    setError('')
  }, [open, currentValue])

  useEffect(() => {
    if (!open) return
    if (debounceTimer.current !== null) window.clearTimeout(debounceTimer.current)
    if (!keyword.trim()) {
      requestVersion.current += 1
      setTips([])
      setLoading(false)
      setSearched(false)
      setError('')
      return
    }
    debounceTimer.current = window.setTimeout(() => {
      void loadTips(keyword)
    }, 400)
    return () => {
      if (debounceTimer.current !== null) window.clearTimeout(debounceTimer.current)
    }
  }, [keyword, open])

  if (!open) return null

  const searchNow = () => {
    if (debounceTimer.current !== null) window.clearTimeout(debounceTimer.current)
    void loadTips(keyword)
  }

  const selectAddress = (item: AmapInputTip) => {
    if (!item.location.trim()) return
    onSelect(item.search_keyword || item.name, item.expected_text || item.name)
  }

  return (
    <div className="modal-overlay z-50">
      <div className="modal-content max-w-md max-h-[80vh] flex flex-col">
        <div className="modal-header flex-shrink-0">
          <div>
            <h2 className="modal-title">宝贝所在地</h2>
            <p className="text-xs text-slate-400 mt-1">选择精准地址，帮助推荐更多同城买家</p>
          </div>
          <button type="button" className="modal-close" title="关闭" onClick={onClose}><X className="w-5 h-5" /></button>
        </div>
        <div className="modal-body flex flex-col min-h-0">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
            <input
              autoFocus
              className="input-ios pl-9 pr-20"
              placeholder="搜索地址"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  searchNow()
                }
              }}
            />
            <button type="button" className="absolute right-1 top-1/2 -translate-y-1/2 btn-ios-primary px-2 py-1 text-xs" onClick={searchNow}>
              查询
            </button>
          </div>

          {loading ? (
            <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 animate-spin text-blue-500" /></div>
          ) : (
            <div className="mt-3 min-h-0 overflow-y-auto">
              {error ? (
                <p className="py-6 text-center text-sm text-red-500">{error}</p>
              ) : searched ? (
                <section>
                  <h3 className="mb-1 text-xs font-medium text-slate-500 dark:text-slate-400">搜索结果</h3>
                  <AddressList items={tips} onSelect={selectAddress} emptyText="高德地图未返回匹配的所在地" />
                </section>
              ) : (
                <p className="py-8 text-center text-sm text-slate-400">请输入关键词搜索宝贝所在地</p>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function AddressList({ items, onSelect, emptyText }: { items: AmapInputTip[]; onSelect: (item: AmapInputTip) => void; emptyText: string }) {
  if (!items.length) return <p className="text-sm text-slate-400 py-4 text-center">{emptyText}</p>
  return (
    <div className="divide-y divide-slate-100 dark:divide-slate-700 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden">
      {items.map((item, index) => {
        const selectable = Boolean(item.location.trim())
        return (
        <button
          type="button"
          key={`${item.id}-${item.name}-${index}`}
          disabled={!selectable}
          className={`w-full px-3 py-2.5 text-left transition-colors ${selectable ? 'hover:bg-blue-50 dark:hover:bg-blue-900/20' : 'cursor-not-allowed bg-slate-50/70 opacity-55 dark:bg-slate-800/40'}`}
          onClick={() => onSelect(item)}
        >
          <span className="flex items-start gap-2">
            <MapPin className="w-4 h-4 text-slate-400 mt-0.5 flex-shrink-0" />
            <span className="min-w-0">
              <span className="block text-sm text-slate-700 dark:text-slate-200 truncate">{item.name}</span>
              <span className="block text-xs text-slate-400 truncate mt-0.5">{[item.district, item.address].filter(Boolean).join(' · ')}</span>
              {!selectable && <span className="mt-0.5 block text-xs text-amber-600 dark:text-amber-400">暂无坐标，不可选择</span>}
            </span>
          </span>
        </button>
        )
      })}
    </div>
  )
}

export default AddressPickerModal
