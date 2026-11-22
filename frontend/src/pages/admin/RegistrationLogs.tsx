/**
 * 管理员注册日志页面：注册提交和注册发码审计，组合筛选、数据库字典与后端分页。
 * 编辑条件只在查询或回车时应用；分页、条数切换及刷新保留已应用条件。
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { RefreshCw, RotateCcw, Search, UserPlus } from 'lucide-react'
import { getRegistrationLogs, type RegistrationLogFilters, type RegistrationLogPage } from '@/api/registrationLogs'
import { Loading } from '@/components/common/Loading'
import { Pager } from '@/components/common/Pager'
import { useViewportContentHeight } from '@/components/common/useViewportContentHeight'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { formatBeijingDateTime } from '@/utils/date'

/** 校验列表与字典的必要数据，响应缺失不能伪装成暂无日志。 */
function isCompletePage(data: RegistrationLogPage | undefined): data is RegistrationLogPage {
  return Boolean(data && Array.isArray(data.items) && Array.isArray(data.operation_options)
    && Array.isArray(data.status_options) && Number.isInteger(data.total) && data.total >= 0
    && Number.isInteger(data.page) && data.page >= 1 && Number.isInteger(data.pages) && data.pages >= 0
    && [10, 20, 50, 100].includes(data.page_size)
    && [...data.operation_options, ...data.status_options].every((option) => option
      && typeof option.value === 'string' && typeof option.label === 'string' && typeof option.enabled === 'boolean')
    && ['register_submit', 'register_code'].every((value) => data.operation_options.some((option) => option.value === value))
    && ['success', 'failed'].every((value) => data.status_options.some((option) => option.value === value))
    && data.items.every((log) => log && Number.isInteger(log.id) && log.id > 0
      && (log.owner_id === null || Number.isInteger(log.owner_id))
      && (log.operation === null || typeof log.operation === 'string')
      && (log.success === null || typeof log.success === 'boolean')
      && ['owner_username', 'username', 'email', 'client_ip', 'message', 'created_at'].every((key) => {
        const value = log[key as keyof typeof log]
        return value === null || typeof value === 'string'
      })))
}

export function RegistrationLogs() {
  const { containerRef, height } = useViewportContentHeight<HTMLDivElement>()
  const { addToast } = useUIStore()
  const { user, token, _hasHydrated, isAuthenticated } = useAuthStore()
  const canLoad = _hasHydrated && isAuthenticated && Boolean(token) && Boolean(user?.is_admin)
  const generation = useRef(0)
  const loadingRef = useRef(false)
  const [loading, setLoading] = useState(true)
  const [pageData, setPageData] = useState<RegistrationLogPage | null>(null)
  const [errorMessage, setErrorMessage] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [keyword, setKeyword] = useState('')
  const [clientIp, setClientIp] = useState('')
  const [operation, setOperation] = useState('')
  const [status, setStatus] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [appliedFilters, setAppliedFilters] = useState<RegistrationLogFilters>({})

  // 独立请求代次隔离卸载、身份变化和过期响应，不能让旧结果覆盖新查询。
  const loadPage = useCallback((nextPage: number, nextSize: number, filters: RegistrationLogFilters) => {
    if (!canLoad || loadingRef.current) return
    const requestId = ++generation.current
    loadingRef.current = true
    setLoading(true)
    setErrorMessage('')
    setCurrentPage(nextPage)
    setPageSize(nextSize)
    const fail = (message: string) => {
      if (requestId !== generation.current) return
      setErrorMessage(message)
      addToast({ type: 'error', message })
    }
    void getRegistrationLogs({ ...filters, page: nextPage, page_size: nextSize }).then((result) => {
      if (requestId !== generation.current) return
      if (!result || typeof result !== 'object') {
        fail('注册日志响应不完整，请重新加载')
        return
      }
      if (!result.success) {
        fail(result.message || '注册日志响应缺少错误信息，请重新加载')
        return
      }
      if (!isCompletePage(result.data)) {
        fail('注册日志响应不完整，请重新加载')
        return
      }
      setPageData(result.data)
      setCurrentPage(result.data.page)
      setPageSize(result.data.page_size)
    }, (error: unknown) => fail(getApiErrorMessage(error, '加载注册日志失败'))).finally(() => {
      if (requestId === generation.current) {
        loadingRef.current = false
        setLoading(false)
      }
    })
  }, [addToast, canLoad])

  useEffect(() => {
    setPageData(null)
    setAppliedFilters({})
    setKeyword('')
    setClientIp('')
    setOperation('')
    setStatus('')
    setStartDate('')
    setEndDate('')
    loadPage(1, 20, {})
    return () => {
      generation.current += 1
      loadingRef.current = false
    }
  }, [loadPage, user?.user_id])

  const handleSearch = () => {
    if (loadingRef.current) return
    const filters: RegistrationLogFilters = {
      keyword: keyword.trim() || undefined,
      client_ip: clientIp.trim() || undefined,
      operation: operation || undefined,
      status: status || undefined,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
    }
    setAppliedFilters(filters)
    loadPage(1, pageSize, filters)
  }

  const handleReset = () => {
    if (loadingRef.current) return
    setKeyword('')
    setClientIp('')
    setOperation('')
    setStatus('')
    setStartDate('')
    setEndDate('')
    setAppliedFilters({})
    loadPage(1, pageSize, {})
  }

  const hasFilters = Object.values(appliedFilters).some(Boolean)
  const operationOptions = pageData?.operation_options ?? []
  const statusOptions = pageData?.status_options ?? []
  const operationLabels = Object.fromEntries(operationOptions.map((option) => [option.value, option.label]))
  const statusLabels = Object.fromEntries(statusOptions.map((option) => [option.value, option.label]))

  return (
    <div ref={containerRef} style={{ height }} className="relative flex min-h-0 flex-col gap-4 overflow-hidden" aria-busy={loading}>
      {loading && <div role="status" className="absolute inset-0 z-20 flex items-center justify-center rounded-lg bg-white/80 dark:bg-slate-900/80"><Loading text="正在加载注册日志…" /></div>}
      {/* 窄屏筛选换行时只滚动查询区，给表格和分页保留可视空间。 */}
      <div className="max-h-[50%] min-h-0 flex-shrink-0 space-y-4 overflow-y-auto">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <nav aria-label="面包屑" className="mb-1 text-xs text-slate-500 dark:text-slate-400">日志管理 / 注册日志</nav>
            <h1 className="page-title">注册日志</h1>
            <p className="page-description">查看注册提交及注册验证码发送的真实结果，仅管理员可见。</p>
          </div>
          <button type="button" onClick={() => loadPage(currentPage, pageSize, appliedFilters)} disabled={loading} className="btn-ios-secondary"><RefreshCw className="h-4 w-4" />刷新</button>
        </div>
        <section className="vben-card">
          <div className="vben-card-body">
            <form className="flex flex-wrap items-end gap-4" onSubmit={(event) => { event.preventDefault(); handleSearch() }}>
              <div className="input-group min-w-0 flex-1 sm:min-w-[180px]">
                <label htmlFor="registration-keyword" className="input-label">关键字</label>
                <input id="registration-keyword" value={keyword} onChange={(event) => setKeyword(event.target.value)} placeholder="用户名 / 邮箱 / 关联用户" className="input-ios" />
              </div>
              <div className="input-group min-w-0 flex-1 sm:min-w-[180px]">
                <label htmlFor="registration-client-ip" className="input-label">客户端 IP</label>
                <input id="registration-client-ip" value={clientIp} onChange={(event) => setClientIp(event.target.value)} placeholder="完整 IP 或地址片段" className="input-ios" />
              </div>
              <div className="input-group">
                <label htmlFor="registration-operation" className="input-label">注册操作</label>
                <select id="registration-operation" value={operation} onChange={(event) => setOperation(event.target.value)} className="input-ios">
                  <option value="">全部操作</option>
                  {operationOptions.filter((option) => option.enabled).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </div>
              <div className="input-group">
                <label htmlFor="registration-status" className="input-label">结果</label>
                <select id="registration-status" value={status} onChange={(event) => setStatus(event.target.value)} className="input-ios">
                  <option value="">全部结果</option>
                  {statusOptions.filter((option) => option.enabled).map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </div>
              <div className="input-group">
                <label htmlFor="registration-start-date" className="input-label">开始日期</label>
                <input id="registration-start-date" type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="input-ios" />
              </div>
              <div className="input-group">
                <label htmlFor="registration-end-date" className="input-label">结束日期</label>
                <input id="registration-end-date" type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className="input-ios" />
              </div>
              <div className="ml-auto flex gap-3">
                <button type="submit" disabled={loading} className="btn-ios-primary"><Search className="h-4 w-4" />查询</button>
                {hasFilters && <button type="button" onClick={handleReset} disabled={loading} className="btn-ios-secondary"><RotateCcw className="h-4 w-4" />重置</button>}
              </div>
            </form>
          </div>
        </section>
      </div>
      <section className="vben-card flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="max-h-[25%] flex-shrink-0 overflow-y-auto">
          <div className="vben-card-header">
            <h2 className="vben-card-title"><UserPlus className="h-4 w-4" />注册记录</h2>
            {pageData && !errorMessage && <span className="badge-primary">{pageData.total} 条记录</span>}
          </div>
        </div>
        <div className="table-scroll">
          <table className="table-ios">
            <thead><tr><th>关联用户</th><th>提交用户名</th><th>注册邮箱</th><th>注册操作</th><th>结果</th><th>客户端 IP</th><th>结果说明</th><th>时间（北京时间）</th></tr></thead>
            <tbody>
              {errorMessage || !pageData || pageData.items.length === 0 ? (
                <tr><td colSpan={8} className="py-10 text-center text-slate-500 dark:text-slate-400">
                  <div className="flex flex-col items-center gap-2"><UserPlus className="h-8 w-8 text-slate-300 dark:text-slate-600" /><p>{errorMessage || (pageData ? (hasFilters ? '未找到符合条件的注册日志' : '暂无注册日志') : '注册日志尚未加载')}</p></div>
                </td></tr>
              ) : pageData.items.map((log) => (
                <tr key={log.id}>
                  <td className="whitespace-nowrap">{log.owner_username ? `${log.owner_username}（${log.owner_id}）` : log.owner_id ?? '-'}</td>
                  <td className="max-w-[200px] break-all">{log.username || '-'}</td>
                  <td className="max-w-[260px] break-all">{log.email || '-'}</td>
                  <td className="whitespace-nowrap">{log.operation ? operationLabels[log.operation] || '-' : '-'}</td>
                  <td className="whitespace-nowrap">{log.success === null ? '-' : <span className={log.success ? 'badge-success' : 'badge-danger'}>{statusLabels[log.success ? 'success' : 'failed'] || '-'}</span>}</td>
                  <td className="whitespace-nowrap">{log.client_ip || '-'}</td>
                  <td className="max-w-[360px] break-words text-slate-500 dark:text-slate-400">{log.message || '-'}</td>
                  <td className="whitespace-nowrap text-slate-500 dark:text-slate-400">{formatBeijingDateTime(log.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {pageData && !errorMessage && (
          <div className="max-h-[50%] flex-shrink-0 overflow-y-auto">
            <Pager page={currentPage} pageSize={pageSize} total={pageData.total} totalPages={pageData.pages} loading={loading} onPageChange={(page) => loadPage(page, pageSize, appliedFilters)} onPageSizeChange={(size) => loadPage(1, size, appliedFilters)} />
          </div>
        )}
      </section>
    </div>
  )
}
