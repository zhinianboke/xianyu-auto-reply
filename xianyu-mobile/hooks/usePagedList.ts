import { useCallback, useEffect, useRef, useState } from 'react';

// ---------------------------------------------------------------------------
// 通用分页列表 Hook
//
// 统一项目内的两种分页模式：
// - offset 模式：fetchPage({ offset, limit })，如风控日志
// - page 模式：fetchPage({ page, limit })，如管理员日志
//
// 竞态防护沿用 risk-logs.tsx 的 listSeq 模式：
// - refresh 每次递增序号；loadMore 记录发起时的序号，响应回来若序号已过期则丢弃
// - loadingMore 在 finally 中无条件复位，避免过期分支提前 return 导致状态卡死
// ---------------------------------------------------------------------------

export type PagedListMode = 'offset' | 'page';

export interface FetchPageParams {
  offset?: number;
  page?: number;
  limit?: number;
}

export interface PageResult<T> {
  items: T[];
  total: number;
}

export interface UsePagedListOptions<T> {
  fetchPage: (params: FetchPageParams) => Promise<PageResult<T>>;
  /** 分页模式，默认 'offset' */
  mode?: PagedListMode;
  /** 每页条数，默认 20 */
  pageSize?: number;
  /** 挂载时自动请求第一页，默认 true；懒加载的 Tab 可设为 false */
  auto?: boolean;
  /** 提供后，loadMore 追加数据时按该 key 去重（refresh 始终整体替换） */
  dedupeBy?: (item: T) => string | number;
  /** 请求失败回调；缺省时仅 console.error */
  onError?: (error: Error, phase: 'refresh' | 'loadMore') => void;
}

export interface UsePagedListResult<T> {
  items: T[];
  total: number;
  /** 仅首次加载为 true */
  loading: boolean;
  refreshing: boolean;
  loadingMore: boolean;
  hasMore: boolean;
  /** 回到第一页（带竞态序号防护） */
  refresh: () => Promise<void>;
  /** 下一页（重入守卫 + 与 refresh 的竞态防护） */
  loadMore: () => Promise<void>;
  /** 本地清空回初始态（如"清除日志"后），并使在途请求失效 */
  reset: () => void;
}

const DEFAULT_PAGE_SIZE = 20;

export function usePagedList<T>(options: UsePagedListOptions<T>): UsePagedListResult<T> {
  const { mode = 'offset', pageSize = DEFAULT_PAGE_SIZE, auto = true } = options;

  const [items, setItems] = useState<T[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(auto);
  const [refreshing, setRefreshing] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);

  // 请求序号：refresh 递增，loadMore 记录发起时的序号，过期响应丢弃
  const seqRef = useRef(0);
  // 下一页页码（仅 page 模式使用）
  const pageRef = useRef(1);
  // items/hasMore/各 loading 标志的镜像，供 useCallback 内做同步守卫，避免闭包取旧值
  const itemsRef = useRef<T[]>([]);
  const hasMoreRef = useRef(false);
  const loadingRef = useRef(auto);
  const refreshingRef = useRef(false);
  const loadingMoreRef = useRef(false);

  // fetchPage / dedupeBy / onError 经 ref 透传，调用方传内联函数即可，无需 useCallback
  const optsRef = useRef(options);
  useEffect(() => {
    optsRef.current = options;
  });

  const handleError = useCallback((error: unknown, phase: 'refresh' | 'loadMore') => {
    const err = error instanceof Error ? error : new Error(String(error));
    const handler = optsRef.current.onError;
    if (handler) handler(err, phase);
    else console.error(`usePagedList ${phase} failed`, err);
  }, []);

  const applyPage = useCallback((result: PageResult<T>, append: boolean) => {
    let merged: T[];
    if (!append) {
      merged = result.items;
    } else {
      const dedupeBy = optsRef.current.dedupeBy;
      if (dedupeBy) {
        const seen = new Set(itemsRef.current.map(dedupeBy));
        merged = [...itemsRef.current, ...result.items.filter((it) => !seen.has(dedupeBy(it)))];
      } else {
        merged = [...itemsRef.current, ...result.items];
      }
    }
    itemsRef.current = merged;
    setItems(merged);
    setTotal(result.total);
    // 返回空页时收口，避免服务端 total 过期导致 onEndReached 反复触发空请求
    const more = result.items.length > 0 && merged.length < result.total;
    hasMoreRef.current = more;
    setHasMore(more);
  }, []);

  // 不设重入守卫：并发 refresh 靠序号"后来者胜"，过期响应连同其 finally 一并忽略
  const refresh = useCallback(async () => {
    const seq = ++seqRef.current;
    refreshingRef.current = true;
    setRefreshing(true);
    try {
      const params: FetchPageParams =
        mode === 'page' ? { page: 1, limit: pageSize } : { offset: 0, limit: pageSize };
      const result = await optsRef.current.fetchPage(params);
      if (seq !== seqRef.current) return;
      pageRef.current = 2;
      applyPage(result, false);
    } catch (error) {
      if (seq === seqRef.current) handleError(error, 'refresh');
    } finally {
      if (seq === seqRef.current) {
        refreshingRef.current = false;
        setRefreshing(false);
        // 首次加载一旦结束（无论成败）即不再回到 loading 态
        loadingRef.current = false;
        setLoading(false);
      }
    }
  }, [mode, pageSize, applyPage, handleError]);

  const loadMore = useCallback(async () => {
    if (loadingRef.current || refreshingRef.current || loadingMoreRef.current) return;
    if (!hasMoreRef.current || itemsRef.current.length === 0) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    const seq = seqRef.current; // 记录发起时序号，期间发生 refresh 则丢弃本响应
    try {
      const params: FetchPageParams =
        mode === 'page'
          ? { page: pageRef.current, limit: pageSize }
          : { offset: itemsRef.current.length, limit: pageSize };
      const result = await optsRef.current.fetchPage(params);
      if (seq !== seqRef.current) return; // 过期响应丢弃
      if (mode === 'page') pageRef.current += 1; // 仅在被采纳的响应后推进页码
      applyPage(result, true);
    } catch (error) {
      handleError(error, 'loadMore');
    } finally {
      // 无条件复位：过期的 loadMore 也必须释放标志，否则后续加载被永久卡死
      loadingMoreRef.current = false;
      setLoadingMore(false);
    }
  }, [mode, pageSize, applyPage, handleError]);

  // 仅挂载时拉取第一页；后续由调用方主动 refresh
  useEffect(() => {
    if (auto) refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reset = useCallback(() => {
    seqRef.current += 1; // 使在途请求过期
    pageRef.current = 1;
    itemsRef.current = [];
    hasMoreRef.current = false;
    loadingRef.current = false;
    refreshingRef.current = false;
    loadingMoreRef.current = false;
    setItems([]);
    setTotal(0);
    setHasMore(false);
    setLoading(false);
    setRefreshing(false);
    setLoadingMore(false);
  }, []);

  return {
    items,
    total,
    loading,
    refreshing,
    loadingMore,
    hasMore,
    refresh,
    loadMore,
    reset,
  };
}
