/** 卡密提交日志管理页面。 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2, RefreshCw, RotateCcw, Search } from 'lucide-react'

import {
  getCardSubmitLogOptions,
  getCardSubmitLogs,
  type CardSubmitLog,
  type CardSubmitLogOption,
} from '@/api/cardSubmitLogs'
import { PageLoading } from '@/components/common/Loading'
import { Pager } from '@/components/common/Pager'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { formatDateTime } from '@/utils/date'
import { getApiErrorMessage } from '@/utils/request'
import { getUserSetting, updateUserSetting } from '@/api/settings'


interface LogFilters {
  order_no?: string
  submit_result?: string
  start_date?: string
  end_date?: string
}


export function CardSubmitLogs() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const requestIdRef = useRef(0)
  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState<CardSubmitLog[]>([])
  const [orderNo, setOrderNo] = useState('')
  const [submitResult, setSubmitResult] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [appliedFilters, setAppliedFilters] = useState<LogFilters>({})
  const [resultOptions, setResultOptions] = useState<CardSubmitLogOption[]>([])
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [keywordOpen, setKeywordOpen] = useState(false)
  const [queryKeywords, setQueryKeywords] = useState('')
  const [inviteKeywordOpen, setInviteKeywordOpen] = useState(false)
  const [inviteKeywords, setInviteKeywords] = useState('')
  const [inviteKeywordSaving, setInviteKeywordSaving] = useState(false)
  const [keywordSaving, setKeywordSaving] = useState(false)

  const loadQueryKeywords = useCallback(async () => {
    const result = await getUserSetting('card_push.query_keywords')
    if (result.success) setQueryKeywords(result.value || '')
  }, [])

  const saveQueryKeywords = async () => {
    const value = queryKeywords.split(',').map((item) => item.trim()).filter(Boolean).join(',')
    setKeywordSaving(true)
    const result = await updateUserSetting('card_push.query_keywords', value, '卡密查询关键词')
    setKeywordSaving(false)
    if (!result.success) {
      addToast({ type: 'error', message: result.message || '保存卡密查询关键词失败' })
      return
    }
    setQueryKeywords(value)
    setKeywordOpen(false)
    addToast({ type: 'success', message: '卡密查询关键词已保存' })
  }

  const loadInviteKeywords = useCallback(async () => {
    const result = await getUserSetting('card_push.invite_keywords')
    if (result.success) setInviteKeywords(result.value || '')
  }, [])

  const saveInviteKeywords = async () => {
    const value = inviteKeywords.split(',').map((item) => item.trim()).filter(Boolean).join(',')
    setInviteKeywordSaving(true)
    const result = await updateUserSetting('card_push.invite_keywords', value, '邀请码触发关键词')
    setInviteKeywordSaving(false)
    if (!result.success) {
      addToast({ type: 'error', message: result.message || '保存邀请码触发关键词失败' })
      return
    }
    setInviteKeywords(value)
    setInviteKeywordOpen(false)
    addToast({ type: 'success', message: '邀请码触发关键词已保存' })
  }

  const loadLogs = useCallback(async (
    nextPage: number,
    nextPageSize: number,
    filters: LogFilters = appliedFilters,
  ) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    const requestId = ++requestIdRef.current
    setLoading(true)
    try {
      const result = await getCardSubmitLogs({
        page: nextPage,
        page_size: nextPageSize,
        ...filters,
      })
      if (requestId !== requestIdRef.current) return
      if (!result.success) {
        setLogs([])
        setTotal(0)
        addToast({ type: 'error', message: result.message || '加载卡密提交日志失败' })
        return
      }
      setLogs(result.data?.list || [])
      setTotal(result.data?.total || 0)
      setCurrentPage(result.data?.page || nextPage)
      setPageSize(result.data?.page_size || nextPageSize)
    } catch (error) {
      if (requestId === requestIdRef.current) {
        addToast({ type: 'error', message: getApiErrorMessage(error, '加载卡密提交日志失败') })
      }
    } finally {
      if (requestId === requestIdRef.current) setLoading(false)
    }
  }, [_hasHydrated, isAuthenticated, token, appliedFilters, addToast])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    void loadQueryKeywords()
    void loadInviteKeywords()
    void getCardSubmitLogOptions().then((result) => {
      if (result.success) {
        setResultOptions(result.data?.submit_results || [])
      } else {
        addToast({ type: 'error', message: result.message || '加载提交结果筛选项失败' })
      }
    }).catch((error: unknown) => {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载提交结果筛选项失败') })
    })
    void loadLogs(1, pageSize, {})
    // 认证状态变化时重新初始化。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [_hasHydrated, isAuthenticated, token])

  const handleSearch = () => {
    const filters: LogFilters = {
      order_no: orderNo.trim() || undefined,
      submit_result: submitResult || undefined,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
    }
    setAppliedFilters(filters)
    void loadLogs(1, pageSize, filters)
  }

  const handleReset = () => {
    setOrderNo('')
    setSubmitResult('')
    setStartDate('')
    setEndDate('')
    setAppliedFilters({})
    void loadLogs(1, pageSize, {})
  }

  const resultLabel = (success: boolean) => {
    const value = success ? 'success' : 'failure'
    return resultOptions.find((item) => item.value === value)?.label || value
  }

  if (loading && logs.length === 0) return <PageLoading />

  return (
    <div className="space-y-4">
      {keywordOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="vben-card w-full max-w-lg">
            <div className="vben-card-header"><h2 className="vben-card-title">触发卡密查询关键词</h2></div>
            <div className="vben-card-body space-y-4">
              <p className="text-sm text-slate-500">多个关键词使用英文逗号分隔，用户只能保存一条配置。</p>
              <input className="input-ios w-full" value={queryKeywords} onChange={(event) => setQueryKeywords(event.target.value)} placeholder="例如：查询该笔订单状态：,订单状态：" />
              <div className="flex justify-end gap-2">
                <button type="button" className="btn-ios-secondary" onClick={() => setKeywordOpen(false)}>关闭</button>
                <button type="button" className="btn-ios-primary" disabled={keywordSaving} onClick={() => void saveQueryKeywords()}>{keywordSaving ? '保存中...' : '保存'}</button>
              </div>
            </div>
          </div>
        </div>
      )}
      {inviteKeywordOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="vben-card w-full max-w-lg">
            <div className="vben-card-header"><h2 className="vben-card-title">邀请码触发关键词</h2></div>
            <div className="vben-card-body space-y-4">
              <p className="text-sm text-slate-500">多个关键词使用英文逗号分隔，用户只能保存一条配置。</p>
              <input className="input-ios w-full" value={inviteKeywords} onChange={(event) => setInviteKeywords(event.target.value)} placeholder="例如：查询邀请码：,邀请码状态：" />
              <div className="flex justify-end gap-2">
                <button type="button" className="btn-ios-secondary" onClick={() => setInviteKeywordOpen(false)}>关闭</button>
                <button type="button" className="btn-ios-primary" disabled={inviteKeywordSaving} onClick={() => void saveInviteKeywords()}>{inviteKeywordSaving ? '保存中...' : '保存'}</button>
              </div>
            </div>
          </div>
        </div>
      )}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="page-title">卡密提交日志</h1>
          <p className="page-description">查看订单卡密远程提交的接口返回值与处理结果</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
        <button type="button" onClick={() => setKeywordOpen(true)} className="btn-ios-primary">
          触发卡密查询关键词
        </button>
        <button type="button" onClick={() => setInviteKeywordOpen(true)} className="btn-ios-primary">
          邀请码触发关键词
        </button>
        <button
          type="button"
          onClick={() => void loadLogs(currentPage, pageSize)}
          disabled={loading}
          className="btn-ios-secondary"
        >
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          刷新
        </button>
        </div>
      </div>

      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-end gap-4">
            <div className="input-group min-w-[220px]">
              <label className="input-label">订单号</label>
              <input
                value={orderNo}
                onChange={(event) => setOrderNo(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') handleSearch() }}
                className="input-ios"
                placeholder="请输入订单号关键字"
              />
            </div>
            <div className="input-group min-w-[150px]">
              <label className="input-label">提交结果</label>
              <select
                value={submitResult}
                onChange={(event) => setSubmitResult(event.target.value)}
                className="input-ios"
              >
                <option value="">全部结果</option>
                {resultOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
            <div className="input-group min-w-[150px]">
              <label className="input-label">开始日期</label>
              <input type="date" value={startDate} onChange={(event) => setStartDate(event.target.value)} className="input-ios" />
            </div>
            <div className="input-group min-w-[150px]">
              <label className="input-label">结束日期</label>
              <input type="date" value={endDate} onChange={(event) => setEndDate(event.target.value)} className="input-ios" />
            </div>
            <div className="ml-auto flex gap-2">
              {(orderNo || submitResult || startDate || endDate) && (
                <button type="button" onClick={handleReset} disabled={loading} className="btn-ios-secondary">
                  <RotateCcw className="h-4 w-4" />重置
                </button>
              )}
              <button type="button" onClick={handleSearch} disabled={loading} className="btn-ios-primary">
                <Search className="h-4 w-4" />查询
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="vben-card relative">
        <div className="table-scroll">
          <table className="w-full">
            <thead>
              <tr>
                <th>订单号</th>
                <th>提交结果</th>
                <th>处理说明</th>
                <th>接口返回值</th>
                <th>提交时间</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr><td colSpan={5} className="py-12 text-center text-slate-500">暂无卡密提交日志</td></tr>
              ) : logs.map((log) => (
                <tr key={log.id}>
                  <td className="whitespace-nowrap font-medium text-slate-800 dark:text-slate-100">{log.order_no}</td>
                  <td className="whitespace-nowrap">
                    <span className={log.success ? 'badge-success' : 'badge-danger'}>{resultLabel(log.success)}</span>
                  </td>
                  <td className="min-w-[180px] max-w-[280px] whitespace-normal break-words">{log.result_message || '-'}</td>
                  <td className="min-w-[320px] max-w-[560px]">
                    <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-all rounded-md bg-slate-50 p-2 text-xs text-slate-700 dark:bg-slate-900 dark:text-slate-300">{log.response_body}</pre>
                  </td>
                  <td className="whitespace-nowrap">{formatDateTime(log.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Pager
          page={currentPage}
          total={total}
          pageSize={pageSize}
          loading={loading}
          onPageChange={(page) => void loadLogs(page, pageSize)}
          onPageSizeChange={(size) => void loadLogs(1, size)}
        />
        {loading && logs.length > 0 && (
          <div className="absolute inset-0 z-10 flex items-center justify-center rounded-lg bg-white/70 backdrop-blur-sm dark:bg-slate-800/70">
            <Loader2 className="h-7 w-7 animate-spin text-primary-500" />
          </div>
        )}
      </div>
    </div>
  )
}
