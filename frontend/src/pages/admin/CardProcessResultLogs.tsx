import { useCallback, useEffect, useState } from 'react'
import { Loader2, RefreshCw, Search } from 'lucide-react'
import { getCardProcessResultLogs, type CardProcessResultLog } from '@/api/cardProcessResultLogs'
import { PageLoading } from '@/components/common/Loading'
import { Pager } from '@/components/common/Pager'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { formatDateTime } from '@/utils/date'

export function CardProcessResultLogs() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState<CardProcessResultLog[]>([])
  const [orderNo, setOrderNo] = useState('')
  const [scene, setScene] = useState('')
  const [result, setResult] = useState('')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [applied, setApplied] = useState<{order_no?: string; trigger_scene?: string; success?: boolean}>({})

  const load = useCallback(async (p: number, size: number, filters = applied) => {
    setLoading(true)
    const response = await getCardProcessResultLogs({ page: p, page_size: size, ...filters })
    if (!response.success || !response.data) {
      addToast({ type: 'error', message: response.message || '加载卡密处理结果日志失败' })
      setLoading(false)
      return
    }
    setLogs(response.data.list); setTotal(response.data.total); setPage(response.data.page); setPageSize(response.data.page_size); setLoading(false)
  }, [addToast, applied])

  useEffect(() => { if (_hasHydrated && isAuthenticated && token) void load(1, pageSize, {}) }, [_hasHydrated, isAuthenticated, token])
  if (loading && logs.length === 0) return <PageLoading />
  const search = () => { const f: typeof applied = { order_no: orderNo || undefined, trigger_scene: scene || undefined, success: result === '' ? undefined : result === 'true' }; setApplied(f); void load(1, pageSize, f) }
  return <div className="space-y-4">
    <div className="flex items-center justify-between"><div><h1 className="page-title">卡密处理结果日志</h1><p className="page-description">查看卡密状态查询请求、返回值和触发场景</p></div><button className="btn-ios-secondary" onClick={() => void load(page, pageSize)} disabled={loading}>{loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}刷新</button></div>
    <div className="vben-card"><div className="vben-card-body flex flex-wrap items-end gap-3"><div className="input-group"><label className="input-label">订单号</label><input className="input-ios" value={orderNo} onChange={e => setOrderNo(e.target.value)} /></div><div className="input-group"><label className="input-label">触发场景</label><select className="input-ios" value={scene} onChange={e => setScene(e.target.value)}><option value="">全部</option><option value="scheduled">定时任务</option><option value="buyer">买家触发</option></select></div><div className="input-group"><label className="input-label">结果</label><select className="input-ios" value={result} onChange={e => setResult(e.target.value)}><option value="">全部</option><option value="true">成功</option><option value="false">失败</option></select></div><button className="btn-ios-primary" onClick={search}><Search className="h-4 w-4" />查询</button></div></div>
    <div className="vben-card"><div className="table-scroll"><table className="w-full"><thead><tr><th>订单号</th><th>触发场景</th><th>结果</th><th>请求参数</th><th>接口返回值</th><th>结果说明</th><th>创建时间</th></tr></thead><tbody>{logs.map(log => <tr key={log.id}><td>{log.order_no}</td><td>{log.trigger_scene === 'buyer' ? '买家触发' : '定时任务'}</td><td>{log.success ? '成功' : '失败'}</td><td className="max-w-xs whitespace-pre-wrap break-all">{log.request_body}</td><td className="max-w-xs whitespace-pre-wrap break-all">{log.response_body}</td><td>{log.result_message}</td><td>{formatDateTime(log.created_at)}</td></tr>)}</tbody></table></div><Pager page={page} pageSize={pageSize} total={total} onPageChange={p => void load(p, pageSize)} onPageSizeChange={s => void load(1, s)} /></div>
  </div>
}
