/**
 * 用户登录日志页面
 *
 * 功能：
 * 1. 展示系统用户登录本系统的每一次尝试（成功 / 失败都会有一条记录）
 * 2. 支持按关键字（登录账号）、登录方式、时间区间筛选与后端分页
 * 3. 仅管理员可访问，可查看全部用户的登录记录（由后端按权限限制）
 */
import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight, Loader2, LogIn, RefreshCw, RotateCcw, Search } from 'lucide-react'

import { getUserLoginLogs, LOGIN_METHOD_LABELS, type UserLoginLog } from '@/api/userLoginLogs'
import { PageLoading } from '@/components/common/Loading'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/request'

// 登录方式下拉选项（中文名称统一来自 api 模块，避免页面硬编码）
const LOGIN_METHOD_OPTIONS = Object.entries(LOGIN_METHOD_LABELS).map(([value, label]) => ({ value, label }))

export function UserLoginLogs() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()

  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState<UserLoginLog[]>([])

  // 查询条件
  const [keyword, setKeyword] = useState('')
  const [loginMethod, setLoginMethod] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  // 分页
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)

  const loadLogs = async (
    nextPage: number = currentPage,
    nextPageSize: number = pageSize,
    // 支持显式传入筛选条件（重置时传空对象），避免用到闭包里的旧状态
    overrideFilters?: { keyword?: string; login_method?: string; start_date?: string; end_date?: string },
  ) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    const filters = overrideFilters ?? {
      keyword: keyword.trim() || undefined,
      login_method: loginMethod || undefined,
      start_date: startDate || undefined,
      end_date: endDate || undefined,
    }
    try {
      setLoading(true)
      const result = await getUserLoginLogs({
        page: nextPage,
        pageSize: nextPageSize,
        ...filters,
      })
      if (result.success) {
        setLogs(result.data || [])
        setCurrentPage(nextPage)
        setPageSize(nextPageSize)
        setTotal(result.total || 0)
      } else {
        setLogs([])
        setCurrentPage(nextPage)
        setPageSize(nextPageSize)
        setTotal(0)
        addToast({ type: 'error', message: result.message || '加载用户登录日志失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载用户登录日志失败') })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadLogs(1, pageSize)
    // 仅在认证态变更时初始化加载
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [_hasHydrated, isAuthenticated, token])

  // 查询按钮
  const handleSearch = () => {
    loadLogs(1, pageSize)
  }

  // 重置按钮
  const handleReset = () => {
    setKeyword('')
    setLoginMethod('')
    setStartDate('')
    setEndDate('')
    // 重置后按空条件重新查询（显式传空筛选，避免用到闭包里的旧状态）
    loadLogs(1, pageSize, {})
  }

  // 分页计算
  const totalPages = Math.ceil(total / pageSize)
  const startIndex = total === 0 ? 0 : (currentPage - 1) * pageSize + 1
  const endIndex = Math.min(currentPage * pageSize, total)

  const handlePageChange = (nextPage: number) => {
    if (nextPage < 1 || nextPage > totalPages) return
    loadLogs(nextPage, pageSize)
  }

  const handlePageSizeChange = (nextPageSize: number) => {
    loadLogs(1, nextPageSize)
  }

  const renderResult = (success: boolean) => (
    <span
      className={
        success
          ? 'inline-block text-xs px-2 py-1 rounded whitespace-nowrap bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400'
          : 'inline-block text-xs px-2 py-1 rounded whitespace-nowrap bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
      }
    >
      {success ? '成功' : '失败'}
    </span>
  )

  const renderLoginMethod = (method: string) => LOGIN_METHOD_LABELS[method] || method || '-'

  if (loading && logs.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">用户登录日志</h1>
          <p className="page-description">
            查看系统用户登录本系统的每一次尝试结果（仅管理员可见）
          </p>
        </div>
        <div className="flex gap-3 flex-wrap">
          <button onClick={() => loadLogs()} disabled={loading} className="btn-ios-secondary">
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
              <label className="input-label">关键字</label>
              <input
                type="text"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
                placeholder="登录账号 / 用户ID"
                className="input-ios"
              />
            </div>
            <div className="input-group">
              <label className="input-label">登录方式</label>
              <select
                value={loginMethod}
                onChange={(e) => setLoginMethod(e.target.value)}
                className="input-ios"
              >
                <option value="">全部方式</option>
                {LOGIN_METHOD_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="input-group">
              <label className="input-label">开始日期</label>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="input-ios"
              />
            </div>
            <div className="input-group">
              <label className="input-label">结束日期</label>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="input-ios"
              />
            </div>
            <button onClick={handleSearch} className="btn-ios-primary">
              <Search className="w-4 h-4" />
              查询
            </button>
            <button onClick={handleReset} className="btn-ios-secondary">
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
            <LogIn className="w-4 h-4 text-blue-500" />
            登录记录
          </h2>
          <span className="badge-primary">{total} 条记录</span>
        </div>

        {/* 表格容器：固定高度 + 内部滚动 + 表头吸顶 */}
        <div className="table-scroll">
          <table className="table-ios">
            <thead>
              <tr>
                <th className="min-w-[80px]">用户ID</th>
                <th className="min-w-[160px]">登录账号</th>
                <th className="min-w-[110px]">登录方式</th>
                <th className="min-w-[80px]">登录结果</th>
                <th className="min-w-[130px]">客户端IP</th>
                <th className="min-w-[220px]">结果说明</th>
                <th className="min-w-[170px]">时间</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="text-center py-8 text-slate-500 dark:text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <LogIn className="w-8 h-8 text-slate-300 dark:text-slate-600" />
                      <p>暂无用户登录日志</p>
                    </div>
                  </td>
                </tr>
              ) : (
                logs.map((log) => (
                  <tr key={log.id}>
                    <td className="whitespace-nowrap">{log.owner_id ?? '-'}</td>
                    <td className="whitespace-nowrap">{log.login_account || '-'}</td>
                    <td className="whitespace-nowrap">{renderLoginMethod(log.login_method)}</td>
                    <td className="whitespace-nowrap">{renderResult(log.success)}</td>
                    <td className="whitespace-nowrap">{log.client_ip || '-'}</td>
                    <td className="max-w-[320px] text-slate-500 dark:text-slate-400">
                      <span className="block truncate cursor-help" title={log.result_message || ''}>
                        {log.result_message || '-'}
                      </span>
                    </td>
                    <td className="text-slate-500 dark:text-slate-400 text-sm whitespace-nowrap">
                      {log.created_at ? new Date(log.created_at).toLocaleString() : '-'}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* 分页 */}
        {total > 0 && (
          <div className="flex-shrink-0 vben-card-footer flex flex-col sm:flex-row items-center justify-between gap-4 px-4 py-3 border-t border-slate-200 dark:border-slate-700">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                className="px-2 py-1 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>条</span>
              <span className="ml-2">
                显示 {startIndex}-{endIndex} 条，共 {total} 条
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handlePageChange(currentPage - 1)}
                disabled={currentPage === 1}
                className="p-2 rounded border border-slate-300 dark:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-700"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-3 py-1 text-sm text-slate-600 dark:text-slate-400">
                第 {currentPage} / {totalPages || 1} 页
              </span>
              <button
                onClick={() => handlePageChange(currentPage + 1)}
                disabled={currentPage >= totalPages}
                className="p-2 rounded border border-slate-300 dark:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-700"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}