/**
 * 邮件发送日志页面
 *
 * 功能：
 * 1. 展示系统每一次触发邮件发送的尝试（成功 / 失败 / 被限流或配置缺失都会有一条记录）
 * 2. 支持按收件邮箱关键字、触发操作、发送结果、时间区间筛选与后端分页
 * 3. 仅管理员可访问，菜单权限仅管理员（后端同样按管理员权限限制）
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Loader2, Mail, RefreshCw, RotateCcw, Search } from 'lucide-react'

import {
  getEmailLogOptions,
  getEmailLogs,
  type EmailLog,
  type EmailLogOption,
} from '@/api/emailLogs'
import { PageLoading } from '@/components/common/Loading'
import { Pager } from '@/components/common/Pager'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { formatDateTime } from '@/utils/date'
import { getApiErrorMessage } from '@/utils/request'

interface LogFilters {
  recipient_email?: string
  trigger_operation?: string
  send_result?: string
  start_date?: string
  end_date?: string
}

export function EmailLogs() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()

  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState<EmailLog[]>([])

  // 查询条件
  const [recipientEmail, setRecipientEmail] = useState('')
  const [triggerOperation, setTriggerOperation] = useState('')
  const [sendResult, setSendResult] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')
  const [appliedFilters, setAppliedFilters] = useState<LogFilters>({})
  const requestIdRef = useRef(0)

  // 筛选枚举（中文名称来自后端数据字典）
  const [triggerOperations, setTriggerOperations] = useState<EmailLogOption[]>([])
  const [sendResults, setSendResults] = useState<EmailLogOption[]>([])

  // 分页
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)

  const loadLogs = useCallback(
    async (
      nextPage: number,
      nextPageSize: number,
      filters: LogFilters = appliedFilters,
    ) => {
      if (!_hasHydrated || !isAuthenticated || !token) return
      const requestId = ++requestIdRef.current
      try {
        setLoading(true)
        const result = await getEmailLogs({
          page: nextPage,
          page_size: nextPageSize,
          ...filters,
        })
        if (requestId !== requestIdRef.current) return
        if (result.success) {
          setLogs(result.data?.list || [])
          setTotal(result.data?.total || 0)
          setCurrentPage(result.data?.page || nextPage)
          setPageSize(result.data?.page_size || nextPageSize)
        } else {
          setLogs([])
          setTotal(0)
          setCurrentPage(nextPage)
          setPageSize(nextPageSize)
          addToast({ type: 'error', message: result.message || '加载邮件发送日志失败' })
        }
      } catch (error) {
        if (requestId !== requestIdRef.current) return
        addToast({ type: 'error', message: getApiErrorMessage(error, '加载邮件发送日志失败') })
      } finally {
        if (requestId === requestIdRef.current) setLoading(false)
      }
    },
    [
      _hasHydrated,
      isAuthenticated,
      token,
      appliedFilters,
      addToast,
    ],
  )

  // 加载筛选枚举（失败时提示用户，不静默）
  const loadOptions = useCallback(async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const result = await getEmailLogOptions()
      if (result.success) {
        setTriggerOperations(result.data?.trigger_operations || [])
        setSendResults(result.data?.send_results || [])
      } else {
        addToast({ type: 'error', message: result.message || '加载邮件日志筛选项失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载邮件日志筛选项失败') })
    }
  }, [_hasHydrated, isAuthenticated, token, addToast])

  // 初始化：加载枚举与第一页
  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadOptions()
    loadLogs(1, pageSize, {})
    // 仅在认证态变更时初始化加载
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [_hasHydrated, isAuthenticated, token])

  const handleSearch = () => {
    const filters = {
      recipient_email: recipientEmail.trim() || undefined,
      trigger_operation: triggerOperation || undefined,
      send_result: sendResult || undefined,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
    }
    setAppliedFilters(filters)
    loadLogs(1, pageSize, filters)
  }

  const handleReset = () => {
    setRecipientEmail('')
    setTriggerOperation('')
    setSendResult('')
    setStartDate('')
    setEndDate('')
    setAppliedFilters({})
    loadLogs(1, pageSize, {})
  }

  const handlePageChange = (nextPage: number) => {
    loadLogs(nextPage, pageSize, appliedFilters)
  }

  const handlePageSizeChange = (nextPageSize: number) => {
    loadLogs(1, nextPageSize, appliedFilters)
  }

  const renderSendResult = (success: boolean) => {
    const value = success ? 'success' : 'failure'
    const label = sendResults.find((option) => option.value === value)?.label || value
    return (
      <span
        className={
          success
            ? 'inline-block text-xs px-2 py-1 rounded whitespace-nowrap bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
            : 'inline-block text-xs px-2 py-1 rounded whitespace-nowrap bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
        }
      >
        {label}
      </span>
    )
  }

  // 触发操作中文名称统一取后端数据字典，未命中时回退展示原始值
  const renderTriggerOperation = (operation: string) => {
    const matched = triggerOperations.find((option) => option.value === operation)
    return matched?.label || operation || '-'
  }

  if (loading && logs.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">邮件日志</h1>
          <p className="page-description">
            查看系统每一次触发邮件发送的结果（成功 / 失败 / 被限流或配置缺失，仅管理员可见）
          </p>
        </div>
        <div className="flex gap-3 flex-wrap">
          <button onClick={() => loadLogs(currentPage, pageSize)} disabled={loading} className="btn-ios-secondary">
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            刷新
          </button>
        </div>
      </div>

      {/* 查询条件 */}
      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-end gap-4">
            <div className="input-group min-w-[200px]">
              <label className="input-label">收件邮箱</label>
              <input
                type="text"
                value={recipientEmail}
                onChange={(event) => setRecipientEmail(event.target.value)}
                placeholder="邮箱关键字"
                className="input-ios"
              />
            </div>
            <div className="input-group min-w-[170px]">
              <label className="input-label">触发操作</label>
              <select
                value={triggerOperation}
                onChange={(event) => setTriggerOperation(event.target.value)}
                className="input-ios"
              >
                <option value="">全部操作</option>
                {triggerOperations.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="input-group min-w-[140px]">
              <label className="input-label">发送结果</label>
              <select
                value={sendResult}
                onChange={(event) => setSendResult(event.target.value)}
                className="input-ios"
              >
                <option value="">全部结果</option>
                {sendResults.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="input-group">
              <label className="input-label">开始日期</label>
              <input
                type="date"
                value={startDate}
                onChange={(event) => setStartDate(event.target.value)}
                className="input-ios"
              />
            </div>
            <div className="input-group">
              <label className="input-label">结束日期</label>
              <input
                type="date"
                value={endDate}
                onChange={(event) => setEndDate(event.target.value)}
                className="input-ios"
              />
            </div>
            <button onClick={handleSearch} disabled={loading} className="btn-ios-primary">
              <Search className="w-4 h-4" />
              查询
            </button>
            <button onClick={handleReset} disabled={loading} className="btn-ios-secondary">
              <RotateCcw className="w-4 h-4" />
              重置
            </button>
          </div>
        </div>
      </div>

      {/* 日志列表 */}
      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 340px)', minHeight: '400px' }}>
        <div className="vben-card-header flex-shrink-0">
          <h2 className="vben-card-title">
            <Mail className="w-4 h-4 text-blue-500" />
            邮件发送记录
          </h2>
          <span className="badge-primary">{total} 条记录</span>
        </div>

        {/* 表格容器：固定高度 + 内部滚动 + 表头吸顶 */}
        <div className="table-scroll">
          <table className="table-ios">
            <thead>
              <tr>
                <th className="min-w-[70px]">ID</th>
                <th className="min-w-[80px]">触发用户</th>
                <th className="min-w-[200px]">收件邮箱</th>
                <th className="min-w-[140px]">触发操作</th>
                <th className="min-w-[90px]">发送结果</th>
                <th className="min-w-[130px]">客户端IP</th>
                <th className="min-w-[240px]">结果说明</th>
                <th className="min-w-[170px]">发生时间</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={8} className="text-center py-8 text-slate-500 dark:text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <Mail className="w-8 h-8 text-slate-300 dark:text-slate-600" />
                      <p>暂无邮件发送日志</p>
                    </div>
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id}>
                    <td className="whitespace-nowrap">{log.id}</td>
                    <td className="whitespace-nowrap">{log.owner_id ?? '-'}</td>
                    <td className="whitespace-nowrap">{log.recipient_email || '-'}</td>
                    <td className="whitespace-nowrap">{renderTriggerOperation(log.trigger_operation)}</td>
                    <td className="whitespace-nowrap">{renderSendResult(log.success)}</td>
                    <td className="whitespace-nowrap">{log.client_ip || '-'}</td>
                    <td className="max-w-[320px] text-slate-500 dark:text-slate-400">
                      <span className="block truncate cursor-help" title={log.result_message || ''}>
                        {log.result_message || '-'}
                      </span>
                    </td>
                    <td className="text-slate-500 dark:text-slate-400 text-sm whitespace-nowrap">
                      {formatDateTime(log.created_at)}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* 分页：支持指定页码跳转 */}
        <Pager
          page={currentPage}
          pageSize={pageSize}
          total={total}
          loading={loading}
          onPageChange={handlePageChange}
          onPageSizeChange={handlePageSizeChange}
        />
      </div>
    </div>
  )
}
