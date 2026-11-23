/** 管理员安全日志：组合查询、独立新增IP筛选、字典中文名称和完整详情，仅按钮关闭。 */
import { useEffect, useRef, useState } from 'react'
import { RefreshCw, Search, ShieldCheck } from 'lucide-react'
import { getSecurityLog, getSecurityLogs, securityLabel, type SecurityFilters, type SecurityLog } from '@/api/securityManagement'
import { Loading } from '@/components/common/Loading'
import { Pager } from '@/components/common/Pager'
import { useViewportContentHeight } from '@/components/common/useViewportContentHeight'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { formatBeijingDateTime } from '@/utils/date'
import { useSecurityPage } from './useSecurityPage'

const EMPTY_FILTERS: SecurityFilters = {}

export function SecurityLogs() {
  const { data, filters, loading, error, load, isCurrentSession, page, pageSize } = useSecurityPage(getSecurityLogs, EMPTY_FILTERS)
  const [draft, setDraft] = useState<SecurityFilters>({})
  const [detail, setDetail] = useState<SecurityLog | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)
  const detailPending = useRef(false)
  const detailGeneration = useRef(0)
  useEffect(() => {
    detailPending.current = false
    setDetailLoading(false)
    setDetail(null)
    setDraft({})
    return () => { detailGeneration.current += 1 }
  }, [isCurrentSession])
  const { addToast } = useUIStore()
  const { containerRef, height } = useViewportContentHeight<HTMLDivElement>()
  const dictionaries = data?.dictionaries || {}
  const hasFilters = Object.values(filters).some(Boolean)
  const canReset = hasFilters || Object.values(draft).some(Boolean)
  const showDetail = (id: number) => {
    if (detailPending.current || !isCurrentSession()) return
    detailPending.current = true
    setDetailLoading(true)
    const requestId = ++detailGeneration.current
    void getSecurityLog(id).then((response) => {
      if (requestId !== detailGeneration.current || !isCurrentSession()) return
      if (!response.success) return addToast({ type: 'error', message: response.message || '详情读取失败' })
      if (!response.data || !Object.prototype.hasOwnProperty.call(response.data, 'details')) {
        return addToast({ type: 'error', message: '安全日志详情响应不完整' })
      }
      setDetail(response.data)
    }).catch((reason: unknown) => {
      if (requestId === detailGeneration.current && isCurrentSession()) {
        addToast({ type: 'error', message: getApiErrorMessage(reason, '安全日志详情读取失败') })
      }
    }).finally(() => {
      if (requestId === detailGeneration.current && isCurrentSession()) { detailPending.current = false; setDetailLoading(false) }
    })
  }
  return <div ref={containerRef} style={{ height }} className="relative flex min-h-0 flex-col gap-4 overflow-hidden">
    {(loading || detailLoading) && <div className="absolute inset-0 z-20 flex items-center justify-center rounded-lg bg-white/80 dark:bg-slate-900/80"><Loading text={detailLoading ? '正在加载完整详情…' : '正在查询安全日志…'} /></div>}
    <div className="max-h-[48%] shrink-0 space-y-4 overflow-y-auto">
      <div className="flex items-center justify-between gap-3"><div><h1 className="page-title">安全日志</h1><p className="page-description">查看频率检查真实结果、实际新增封禁及完整统计，时间为北京时间。</p></div><button className="btn-ios-secondary" disabled={loading} onClick={() => load(page, pageSize, filters)}><RefreshCw className="h-4 w-4" />刷新</button></div>
      <section className="vben-card"><div className="vben-card-body"><form className="flex flex-wrap items-end gap-4" onSubmit={(event) => { event.preventDefault(); load(1, pageSize, { ...draft }) }}>
        {([['keyword', '关键字', '新增后缀 / 说明 / 执行编号'], ['added_ip', '新增 IP', '完整IP或地址片段']] as const).map(([key, label, placeholder]) => <div className="input-group min-w-0 flex-1" key={key}><label htmlFor={`security-log-${key}`} className="input-label">{label}</label><input id={`security-log-${key}`} value={draft[key] || ''} placeholder={placeholder} className="input-ios" onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} /></div>)}
        {([['execution_method', '执行方式', 'security_execution_method'], ['result', '结果', 'security_execution_result']] as const).map(([key, label, type]) => <div className="input-group" key={key}><label htmlFor={`security-log-${key}`} className="input-label">{label}</label><select id={`security-log-${key}`} className="input-ios" value={draft[key] || ''} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })}><option value="">全部</option>{dictionaries[type]?.filter((option) => option.enabled).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}</select></div>)}
        {([['start_date', '开始日期'], ['end_date', '结束日期']] as const).map(([key, label]) => <div className="input-group" key={key}><label htmlFor={`security-log-${key}`} className="input-label">{label}</label><input id={`security-log-${key}`} type="date" className="input-ios" value={draft[key] || ''} onChange={(event) => setDraft({ ...draft, [key]: event.target.value })} /></div>)}
        <div className="ml-auto flex gap-3"><button className="btn-ios-primary" disabled={loading}><Search className="h-4 w-4" />查询</button>{canReset && <button type="button" className="btn-ios-secondary" disabled={loading} onClick={() => { setDraft({}); load(1, pageSize, EMPTY_FILTERS) }}>重置</button>}</div>
      </form></div></section>
    </div>
    <section className="vben-card flex min-h-0 flex-1 flex-col overflow-hidden"><div className="vben-card-header"><h2 className="vben-card-title"><ShieldCheck className="h-4 w-4" />检查记录</h2></div>
      <div className="table-scroll"><table className="table-ios"><thead><tr><th>执行编号</th><th>执行方式</th><th>管理员</th><th>结果</th><th>实际新增后缀</th><th>实际新增 IP</th><th>说明</th><th>开始时间</th><th>结束时间</th><th>操作</th></tr></thead><tbody>
        {error || !data || !data.items.length ? <tr><td colSpan={10} className="py-10 text-center text-slate-500 dark:text-slate-400"><ShieldCheck className="mx-auto mb-2 h-8 w-8" />{error || (!data ? '安全日志尚未加载' : hasFilters ? '未找到符合条件的安全日志' : '暂无安全日志')}</td></tr> : data.items.map((log) => <tr key={log.id}>
          <td className="max-w-[180px] break-all">{log.execution_id}</td><td>{securityLabel(dictionaries, 'security_execution_method', log.execution_method)}</td><td>{log.owner_id ?? '-'}</td><td><span className={log.result === 'failed' ? 'badge-danger' : 'badge-success'}>{securityLabel(dictionaries, 'security_execution_result', log.result)}</span></td>
          <td className="max-w-[230px] break-all">{log.added_suffixes || '-'}</td><td className="max-w-[230px] break-all">{log.added_ips || '-'}</td><td className="max-w-[260px] break-words">{log.message}</td><td className="whitespace-nowrap">{formatBeijingDateTime(log.started_at)}</td><td className="whitespace-nowrap">{formatBeijingDateTime(log.finished_at)}</td><td><button className="btn-ios-secondary" onClick={() => showDetail(log.id)} disabled={detailLoading}>详情</button></td>
        </tr>)}
      </tbody></table></div>
      {data && !error && <div className="max-h-[50%] shrink-0 overflow-y-auto"><Pager page={data.page} pageSize={data.page_size} total={data.total} totalPages={data.pages} loading={loading} onPageChange={(page) => load(page, pageSize, filters)} onPageSizeChange={(size) => load(1, size, filters)} /></div>}
    </section>
    {detail && <div className="modal-overlay"><div className="modal-content flex max-h-[85vh] max-w-5xl flex-col"><div className="modal-header"><h2 className="modal-title">安全日志完整详情</h2></div><div className="modal-body min-h-0 overflow-auto"><p className="mb-3 break-all">执行编号：{detail.execution_id}</p><p className="mb-3 break-words">{detail.message}</p><pre className="whitespace-pre-wrap break-all text-xs text-slate-800 dark:text-slate-100">{JSON.stringify(detail, null, 2)}</pre></div><div className="modal-footer"><button className="btn-ios-secondary" onClick={() => setDetail(null)}>关闭</button></div></div></div>}
  </div>
}
