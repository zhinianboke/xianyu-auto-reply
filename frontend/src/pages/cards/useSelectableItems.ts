/** 待选商品轻量分页：显式查询、重复商品合并及过期请求隔离。 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { getSelectableItemsPaginated, type SelectableItem } from '@/api/items'
import { getApiErrorMessage } from '@/utils/apiError'
import { useUIStore } from '@/store/uiStore'

export interface LightItem {
  item_id: string
  title: string
  price: string | null
}

/** 把真实后端选择项转换为列表字段；缺失标题时显示商品标识。 */
export const selectableToLight = (item: SelectableItem): LightItem => ({
  item_id: item.item_id,
  title: item.title || item.item_id,
  price: item.price ?? null,
})

const PAGE_SIZE = 20

/** 按商品标识合并数据，保留时间排序靠前的记录。 */
function mergeItems(previous: LightItem[], incoming: LightItem[]): LightItem[] {
  const merged = new Map(previous.map(item => [item.item_id, item]))
  for (const item of incoming) if (!merged.has(item.item_id)) merged.set(item.item_id, item)
  return Array.from(merged.values())
}

/** 加载待选页并把真实商品交给缓存回调；返回列表状态和查询/加载方法。 */
export function useSelectableItems(onLoaded: (items: LightItem[]) => void) {
  const { addToast } = useUIStore()
  const [items, setItems] = useState<LightItem[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const [appliedSearch, setAppliedSearch] = useState('')
  const [errorMessage, setErrorMessage] = useState('')
  const queryRef = useRef({ version: 0, page: 0, search: '', busy: false, hasMore: false })

  const loadFirstPage = useCallback((keyword: string) => {
    const search = keyword.trim()
    const version = queryRef.current.version + 1
    queryRef.current = { version, page: 0, search, busy: true, hasMore: false }
    setAppliedSearch(search)
    setLoading(true)
    setLoadingMore(false)
    setItems([])
    setTotal(0)
    setHasMore(false)
    setErrorMessage('')
    const finish = () => {
      if (queryRef.current.version !== version) return
      queryRef.current.busy = false
      setLoading(false)
    }
    const fail = (message: string) => {
      if (queryRef.current.version !== version) return
      setErrorMessage(message)
      addToast({ type: 'error', message })
    }
    return getSelectableItemsPaginated(1, PAGE_SIZE, search).then(result => {
      if (queryRef.current.version !== version) return
      if (!result.success || !result.data) {
        fail(result.message || '商品查询失败')
        return
      }
      const page = result.data
      const rows = page.list.map(selectableToLight)
      setItems(mergeItems([], rows))
      setTotal(page.total)
      setHasMore(page.has_more)
      queryRef.current.page = page.page
      queryRef.current.hasMore = page.has_more
      onLoaded(rows)
    }, error => fail(getApiErrorMessage(error, '商品查询失败'))).finally(finish)
  }, [addToast, onLoaded])

  useEffect(() => {
    void loadFirstPage('')
    return () => {
      queryRef.current = { ...queryRef.current, version: queryRef.current.version + 1 }
    }
  }, [loadFirstPage])

  const loadMore = () => {
    const query = queryRef.current
    if (query.busy || !query.hasMore) return
    query.busy = true
    setLoadingMore(true)
    setErrorMessage('')
    return getSelectableItemsPaginated(query.page + 1, PAGE_SIZE, query.search).then(result => {
      if (queryRef.current !== query) return
      if (!result.success || !result.data) {
        const message = result.message || '加载更多商品失败'
        setErrorMessage(message)
        addToast({ type: 'error', message })
        return
      }
      const page = result.data
      const rows = page.list.map(selectableToLight)
      setItems(previous => mergeItems(previous, rows))
      query.page = page.page
      query.hasMore = page.has_more
      setHasMore(page.has_more)
      setTotal(page.total)
      onLoaded(rows)
    }, error => {
      if (queryRef.current !== query || queryRef.current.version !== query.version) return
      const message = getApiErrorMessage(error, '加载更多商品失败')
      setErrorMessage(message)
      addToast({ type: 'error', message })
    }).finally(() => {
      if (queryRef.current !== query) return
      query.busy = false
      setLoadingMore(false)
    })
  }

  return { items, total, loading, loadingMore, hasMore, appliedSearch, errorMessage,
    loadFirstPage, loadMore }
}
