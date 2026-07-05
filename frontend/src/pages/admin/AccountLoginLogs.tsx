/**
 * 账号登录日志页面
 *
 * 功能：
 * 1. 显示账号密码登录日志列表（每次 try_password_login_refresh 调用一条）
 * 2. 支持按账号、时间范围、登录状态筛选与分页查询
 * 3. 管理员支持「清理10天前」与「清空全部」两种清理操作
 */
import { useEffect, useMemo, useState } from 'react'
import {
  Calendar,
  ChevronLeft,
  ChevronRight,
  KeyRound,
  Loader2,
  RefreshCw,
  Trash2,
} from 'lucide-react'

import { clearAccountLoginLogs, getAccountLoginLogs, type AccountLoginLog } from '@/api/admin'
import { getAccountDetails } from '@/api/accounts'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { PageLoading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import type { Account } from '@/types'
import { getApiErrorMessage } from '@/utils/request'

// 账号状态中文映射 + 标签颜色
const ACCOUNT_STATUS_LABELS: Record<string, { text: string; cls: string }> = {
  active: {
    text: '启用',
    cls: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  },
  inactive: {
    text: '禁用',
    cls: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  },
  disabled: {
    text: '禁用',
    cls: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  },
  suspended: {
    text: '暂停',
    cls: 'bg-orange-100 text-orange-700 dark:bg-orange-900/30 dark:text-orange-400',
  },
  unknown: {
    text: '未知',
    cls: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
  },
}

// 登录状态中文映射 + 标签颜色
const LOGIN_STATUS_LABELS: Record<string, { text: string; cls: string }> = {
  success: {
    text: '成功',
    cls: 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400',
  },
  failed: {
    text: '失败',
    cls: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400',
  },
  skipped_cooldown: {
    text: '冷却跳过',
    cls: 'bg-yellow-100 text-yellow-700 dark:bg-yellow-900/30 dark:text-yellow-400',
  },
  no_credentials: {
    text: '未配置账密',
    cls: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
  },
}

// 失败/跳过细分原因中文映射
const FAILURE_REASON_LABELS: Record<string, string> = {
  bad_credentials: '账号或密码错误',
  baxia_punish_captcha: '风控图形验证（如找松鼠）',
  account_info_missing: '无法获取账号信息',
  no_credentials: '未配置账号或密码',
  cookie_already_updated_externally: 'Cookie已被外部更新',
  cookie_update_failed: 'Cookie更新或重启失败',
  login_no_cookie_returned: '登录未返回Cookie',
  login_cooldown: '密码登录冷却中',
  password_error_cooldown: '账密错误冷却中',
  exception: '其他异常',
}

export function AccountLoginLogs() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated, user } = useAuthStore()

  const [loading, setLoading] = useState(true)
  const [logs, setLogs] = useState<AccountLoginLog[]>([])
  const [accounts, setAccounts] = useState<Account[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')

  // 时间筛选 - 默认当天
  const today = new Date().toISOString().split('T')[0]
  const [startDate, setStartDate] = useState(today)
  const [endDate, setEndDate] = useState(today)

  // 登录状态筛选
  const [selectedStatus, setSelectedStatus] = useState('')

  // 分页
  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)

  // 清理确认弹窗
  type ClearMode = 'older_than_10d' | 'all' | null
  const [clearMode, setClearMode] = useState<ClearMode>(null)
  const [clearing, setClearing] = useState(false)

  const loadLogs = async (nextPage: number = currentPage, nextPageSize: number = pageSize) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getAccountLoginLogs({
        page: nextPage,
        pageSize: nextPageSize,
        cookie_id: selectedAccount || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        login_status: selectedStatus || undefined,
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
        addToast({ type: 'error', message: result.message || '加载账号登录日志失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载账号登录日志失败') })
    } finally {
      setLoading(false)
    }
  }

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      const data = await getAccountDetails()
      setAccounts(data)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载账号列表失败') })
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadAccounts()
    loadLogs(1, pageSize)
    // 仅在认证态变更时初始化加载
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [_hasHydrated, isAuthenticated, token])

  // 查询按钮
  const handleSearch = () => {
    loadLogs(1, pageSize)
  }

  // 分页计算
  const totalPages = Math.ceil(total / pageSize)
  const startIndex = total === 0 ? 0 : (currentPage - 1) * pageSize + 1
  const endIndex = Math.min(currentPage * pageSize, total)

  const handlePageChange = (nextPage: number) => {
    if (nextPage < 1 || nextPage > totalPages) {
      return
    }
    loadLogs(nextPage, pageSize)
  }

  const handlePageSizeChange = (nextPageSize: number) => {
    loadLogs(1, nextPageSize)
  }

  const handleClear = async () => {
    if (!clearMode) return
    setClearing(true)
    try {
      if (clearMode === 'older_than_10d') {
        await clearAccountLoginLogs({ days: 10 })
        addToast({ type: 'success', message: '已清理 10 天前的账号登录日志' })
      } else {
        await clearAccountLoginLogs()
        addToast({ type: 'success', message: '已清空所有账号登录日志' })
      }
      setClearMode(null)
      loadLogs(1, pageSize)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '清理失败') })
    } finally {
      setClearing(false)
    }
  }

  // 账号 cookie_id -> note 的映射，避免渲染时重复 find
  const accountNoteMap = useMemo(() => {
    const map = new Map<string, string>()
    accounts.forEach((acc) => {
      if (acc.note) map.set(acc.id, acc.note)
    })
    return map
  }, [accounts])

  const renderStatus = (status: string) => {
    const meta = LOGIN_STATUS_LABELS[status] || {
      text: status || '-',
      cls: 'bg-gray-100 text-gray-700 dark:bg-gray-700 dark:text-gray-300',
    }
    return (
      <span className={`inline-block text-xs px-2 py-1 rounded whitespace-nowrap ${meta.cls}`}>
        {meta.text}
      </span>
    )
  }

  const renderAccountStatus = (status: string) => {
    const meta = ACCOUNT_STATUS_LABELS[status] || ACCOUNT_STATUS_LABELS.unknown
    return (
      <span className={`inline-block text-xs px-2 py-1 rounded whitespace-nowrap ${meta.cls}`}>
        {meta.text}
      </span>
    )
  }

  const renderFailureReason = (reason: string | null) => {
    if (!reason) return '-'
    return FAILURE_REASON_LABELS[reason] || reason
  }

  const renderDuration = (ms: number | null) => {
    if (ms === null || ms === undefined) return '-'
    if (ms < 1000) return `${ms} ms`
    return `${(ms / 1000).toFixed(1)} s`
  }

  if (loading && logs.length === 0) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">账号登录日志</h1>
          <p className="page-description">查看账号密码登录每一次尝试的结果与失败原因</p>
        </div>
        <div className="flex gap-3 flex-wrap">
          {user?.is_admin ? (
            <>
              <button
                onClick={() => setClearMode('older_than_10d')}
                className="btn-ios-secondary"
              >
                <Trash2 className="w-4 h-4" />
                清理10天前
              </button>
              <button onClick={() => setClearMode('all')} className="btn-ios-danger">
                <Trash2 className="w-4 h-4" />
                清空全部
              </button>
            </>
          ) : null}
          <button onClick={() => loadLogs()} disabled={loading} className="btn-ios-secondary">
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            刷新
          </button>
        </div>
      </div>

      {/* Filter */}
      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-end gap-4">
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
            <div className="input-group">
              <label className="input-label">登录状态</label>
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value)}
                className="input-ios"
              >
                <option value="">全部状态</option>
                <option value="success">成功</option>
                <option value="failed">失败</option>
                <option value="skipped_cooldown">冷却跳过</option>
                <option value="no_credentials">未配置账密</option>
              </select>
            </div>
            <div className="input-group min-w-[200px]">
              <label className="input-label">筛选账号</label>
              <Select
                value={selectedAccount}
                onChange={setSelectedAccount}
                options={[
                  { value: '', label: '全部账号', key: 'all' },
                  ...accounts.map((account) => ({
                    value: account.id,
                    label: account.note ? `${account.id} (${account.note})` : account.id,
                    key: account.pk?.toString() || account.id,
                  })),
                ]}
                placeholder="全部账号"
              />
            </div>
            <button onClick={handleSearch} className="btn-ios-primary">
              <Calendar className="w-4 h-4" />
              查询
            </button>
          </div>
        </div>
      </div>

      {/* Logs List */}
      <div
        className="vben-card flex flex-col"
        style={{ height: 'calc(100vh - 380px)', minHeight: '400px' }}
      >
        <div className="vben-card-header flex-shrink-0">
          <h2 className="vben-card-title">
            <KeyRound className="w-4 h-4 text-blue-500" />
            登录尝试记录
          </h2>
          <span className="badge-primary">{total} 条记录</span>
        </div>
        <div className="flex-1 overflow-x-auto overflow-y-auto">
          <table className="table-ios">
            <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
              <tr>
                <th className="min-w-[130px]">账号ID</th>
                <th className="min-w-[80px]">账号状态</th>
                <th className="min-w-[120px]">禁用原因</th>
                <th className="min-w-[110px]">登录用户名</th>
                <th className="min-w-[120px]">触发原因</th>
                <th className="min-w-[100px]">状态</th>
                <th className="min-w-[130px]">失败原因</th>
                <th className="min-w-[180px]">更新Cookie</th>
                <th className="min-w-[250px]">错误详情</th>
                <th className="min-w-[70px]">耗时</th>
                <th className="min-w-[155px]">时间</th>
              </tr>
            </thead>
            <tbody>
              {logs.length === 0 ? (
                <tr>
                  <td
                    colSpan={11}
                    className="text-center py-8 text-slate-500 dark:text-slate-400"
                  >
                    <div className="flex flex-col items-center gap-2">
                      <KeyRound className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>暂无账号登录日志</p>
                    </div>
                  </td>
                </tr>
              ) : (
                logs.map((log) => {
                  const note = accountNoteMap.get(log.cookie_id)
                  return (
                    <tr key={log.id}>
                      <td className="font-medium text-blue-600 dark:text-blue-400">
                        {note ? `${log.cookie_id} (${note})` : log.cookie_id}
                      </td>
                      <td>{renderAccountStatus(log.account_status)}</td>
                      <td className="text-slate-500 dark:text-slate-400 max-w-[160px]">
                        <span className="block truncate cursor-help" title={log.disable_reason || ''}>
                          {log.disable_reason || '-'}
                        </span>
                      </td>
                      <td className="text-slate-600 dark:text-slate-300">
                        {log.username || '-'}
                      </td>
                      <td className="text-slate-500 dark:text-slate-400">
                        {log.trigger_reason || '-'}
                      </td>
                      <td className="whitespace-nowrap">{renderStatus(log.login_status)}</td>
                      <td className="text-slate-500 dark:text-slate-400">
                        {renderFailureReason(log.failure_reason)}
                      </td>
                      <td className="text-slate-500 dark:text-slate-400">
                        {log.updated_cookie_names ? (
                          <span
                            className="text-xs text-blue-600 dark:text-blue-400 font-mono cursor-help"
                            title={log.updated_cookie_names}
                          >
                            {log.updated_cookie_names.length > 40
                              ? `${log.updated_cookie_names.slice(0, 40)}...`
                              : log.updated_cookie_names}
                          </span>
                        ) : (
                          '-'
                        )}
                      </td>
                      <td className="max-w-[260px] text-slate-500 dark:text-slate-400">
                        <span
                          className="block truncate cursor-help"
                          title={log.error_message || ''}
                        >
                          {log.error_message || '-'}
                        </span>
                      </td>
                      <td className="text-slate-500 dark:text-slate-400 whitespace-nowrap">
                        {renderDuration(log.duration_ms)}
                      </td>
                      <td className="text-slate-500 dark:text-slate-400 text-sm whitespace-nowrap">
                        {new Date(log.created_at).toLocaleString()}
                      </td>
                    </tr>
                  )
                })
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

      {/* 清理确认弹窗 */}
      {user?.is_admin ? (
        <ConfirmModal
          isOpen={clearMode !== null}
          title={clearMode === 'older_than_10d' ? '清理确认' : '清空确认'}
          message={
            clearMode === 'older_than_10d'
              ? '将删除 10 天前的全部账号登录日志（保留最近 10 天数据），此操作不可恢复，是否继续？'
              : '将清空全部账号登录日志（包含历史所有数据），此操作不可恢复，是否继续？'
          }
          confirmText={clearMode === 'older_than_10d' ? '清理' : '清空'}
          cancelText="取消"
          type="danger"
          loading={clearing}
          onConfirm={handleClear}
          onCancel={() => (clearing ? null : setClearMode(null))}
        />
      ) : null}
    </div>
  )
}
