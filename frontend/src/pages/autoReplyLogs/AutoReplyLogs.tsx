import { useEffect, useMemo, useState } from 'react'
import { Calendar, ChevronLeft, ChevronRight, MessageSquare, RefreshCw } from 'lucide-react'
import { getAccountDetails } from '@/api/accounts'
import { getAutoReplyLogs, type AutoReplyLogItem } from '@/api/autoReplyLogs'
import { Select } from '@/components/common/Select'
import { PageLoading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/request'
import type { AccountDetail } from '@/types'

const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

const REPLY_STRATEGY_LABELS: Record<string, string> = {
  keyword: '关键词回复',
  ai: 'AI回复',
  default: '默认回复',
  auto_delivery: '自动发货',
}

const DEFAULT_SCOPE_LABELS: Record<string, string> = {
  item: '商品默认',
  account: '账号默认',
}

const REPLY_MODE_LABELS: Record<string, string> = {
  text: '文本',
  image: '图片',
  text_image: '图文',
}

const MATCHED_RULE_TYPE_LABELS: Record<string, string> = {
  keyword_item: '商品关键词',
  keyword_common: '通用关键词',
  ai: 'AI回复',
  default_item: '商品默认回复',
  default_account: '账号默认回复',
}

const DECISION_REASON_LABELS: Record<string, string> = {
  processing: '处理中',
  self_message: '本人发送消息',
  system_message: '系统消息',
  auto_delivery_trigger: '自动发货触发消息',
  item_not_belong: '商品不属于当前账号',
  duplicate_message: '重复消息',
  skip_reply_filter: '命中过滤规则',
  reply_sent: '已发送回复',
  send_failed: '发送失败',
  no_rule_matched: '未匹配回复规则',
  failed: '处理失败',
  auto_delivery: '自动发货',
  chat_paused: '会话已暂停',
  empty_reply: '回复内容为空',
  default_reply_once: '默认回复仅回复一次',
}

function formatDateTime(value?: string | null) {
  if (!value) {
    return '-'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return value
  }
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  })
}

function buildStrategyLabel(log: AutoReplyLogItem) {
  if (log.reply_strategy === 'default' && log.default_reply_scope) {
    return DEFAULT_SCOPE_LABELS[log.default_reply_scope] || `默认回复(${log.default_reply_scope})`
  }
  return REPLY_STRATEGY_LABELS[log.reply_strategy] || log.reply_strategy || '-'
}

function buildReplyModeLabel(value?: string | null) {
  if (!value) {
    return '-'
  }
  return REPLY_MODE_LABELS[value] || value
}

function buildMatchedRuleTypeLabel(value?: string | null) {
  if (!value) {
    return '-'
  }
  return MATCHED_RULE_TYPE_LABELS[value] || value
}

function buildDecisionReasonLabel(value?: string | null) {
  if (!value) {
    return '-'
  }
  return DECISION_REASON_LABELS[value] || value
}

const SEND_STATUS_LABELS: Record<string, string> = {
  success: '发送成功',
  failed: '发送失败',
  unknown: '待确认',
  timeout: '超时',
}

const SEND_STATUS_CLASSES: Record<string, string> = {
  success: 'text-green-600 dark:text-green-400',
  failed: 'text-red-600 dark:text-red-400',
  unknown: 'text-slate-500 dark:text-slate-400',
  timeout: 'text-amber-600 dark:text-amber-400',
}

function buildSendStatusLabel(value?: string | null) {
  const key = value || 'unknown'
  const label = SEND_STATUS_LABELS[key] || key
  const cls = SEND_STATUS_CLASSES[key] || SEND_STATUS_CLASSES.unknown
  return <span className={`font-medium ${cls}`}>{label}</span>
}

function renderText(value?: string | null) {
  if (!value) {
    return '-'
  }
  return value
}

export function AutoReplyLogs() {
  const { addToast } = useUIStore()
  const today = new Date().toISOString().split('T')[0]
  const [loading, setLoading] = useState(true)
  const [accountsLoading, setAccountsLoading] = useState(true)
  const [logs, setLogs] = useState<AutoReplyLogItem[]>([])
  const [accounts, setAccounts] = useState<AccountDetail[]>([])
  const [selectedAccount, setSelectedAccount] = useState('')
  const [selectedRuleType, setSelectedRuleType] = useState('')
  const [selectedSendStatus, setSelectedSendStatus] = useState('')
  const [messageType, setMessageType] = useState('auto_reply')
  const [startDate, setStartDate] = useState(today)
  const [endDate, setEndDate] = useState(today)
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)
  const [totalPages, setTotalPages] = useState(0)

  const accountOptions = useMemo(
    () => [
      { value: '', label: '全部账号', key: 'all' },
      ...accounts.map((account) => ({
        value: account.id,
        label: account.note ? `${account.id} (${account.note})` : account.id,
        key: account.pk?.toString() || account.id,
      })),
    ],
    [accounts]
  )

  const loadAccounts = async () => {
    try {
      setAccountsLoading(true)
      const data = await getAccountDetails()
      setAccounts(data)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载账号列表失败') })
    } finally {
      setAccountsLoading(false)
    }
  }

  const loadLogs = async (nextPage: number = page, nextPageSize: number = pageSize) => {
    try {
      setLoading(true)
      const result = await getAutoReplyLogs({
        account_id: selectedAccount || undefined,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        matched_rule_type: messageType === 'auto_delivery' ? undefined : (selectedRuleType || undefined),
        send_status: selectedSendStatus || undefined,
        message_type: messageType,
        page: nextPage,
        page_size: nextPageSize,
      })
      if (result.success) {
        setLogs(result.data || [])
        setPage(result.page)
        setPageSize(result.page_size)
        setTotal(result.total)
        setTotalPages(result.total_pages)
        return
      }
      setLogs([])
      setTotal(0)
      setTotalPages(0)
      addToast({ type: 'error', message: result.message || '加载消息日志失败' })
    } catch (error) {
      setLogs([])
      setTotal(0)
      setTotalPages(0)
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载消息日志失败') })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadAccounts()
  }, [])

  useEffect(() => {
    loadLogs(1, pageSize)
  }, [])

  const handleSearch = () => {
    loadLogs(1, pageSize)
  }

  const handlePageChange = (nextPage: number) => {
    if (nextPage < 1 || nextPage > totalPages) {
      return
    }
    loadLogs(nextPage, pageSize)
  }

  const handlePageSizeChange = (nextPageSize: number) => {
    loadLogs(1, nextPageSize)
  }

  if ((loading && logs.length === 0) || accountsLoading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      <div className="page-header flex-between">
        <div>
          <h1 className="page-title">消息日志</h1>
          <p className="page-description">查看账号自动回复成功明细，口径与账号管理今日回复一致</p>
        </div>
        <button onClick={() => loadLogs()} className="btn-ios-secondary" disabled={loading}>
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          刷新
        </button>
      </div>

      <div className="vben-card">
        <div className="vben-card-body">
          <div className="flex flex-wrap items-end gap-4">
            <div className="input-group min-w-[220px]">
              <label className="input-label">筛选账号</label>
              <Select
                value={selectedAccount}
                onChange={setSelectedAccount}
                options={accountOptions}
                placeholder="全部账号"
              />
            </div>
            <div className="input-group">
              <label className="input-label">开始日期</label>
              <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)} className="input-ios" />
            </div>
            <div className="input-group">
              <label className="input-label">结束日期</label>
              <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)} className="input-ios" />
            </div>
            <div className="input-group min-w-[160px]">
              <label className="input-label">消息类型</label>
              <select
                value={messageType}
                onChange={(e) => setMessageType(e.target.value)}
                className="input-ios"
              >
                <option value="auto_reply">自动回复</option>
                <option value="auto_delivery">自动发货</option>
              </select>
            </div>
            {messageType !== 'auto_delivery' && (
              <div className="input-group min-w-[160px]">
                <label className="input-label">规则类型</label>
                <select
                  value={selectedRuleType}
                  onChange={(e) => setSelectedRuleType(e.target.value)}
                  className="input-ios"
                >
                  <option value="">全部类型</option>
                  <option value="keyword_item">商品关键词</option>
                  <option value="keyword_common">通用关键词</option>
                  <option value="ai">AI回复</option>
                  <option value="default_item">商品默认回复</option>
                  <option value="default_account">账号默认回复</option>
                </select>
              </div>
            )}
            <div className="input-group min-w-[160px]">
              <label className="input-label">发送状态</label>
              <select
                value={selectedSendStatus}
                onChange={(e) => setSelectedSendStatus(e.target.value)}
                className="input-ios"
              >
                <option value="">全部状态</option>
                <option value="success">发送成功</option>
                <option value="failed">发送失败</option>
                <option value="unknown">待确认</option>
                <option value="timeout">超时</option>
              </select>
            </div>
            <button onClick={handleSearch} className="btn-ios-primary">
              <Calendar className="w-4 h-4" />
              查询
            </button>
          </div>
        </div>
      </div>

      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 340px)', minHeight: '420px' }}>
        <div className="vben-card-header flex-shrink-0 flex-between">
          <h2 className="vben-card-title">
            <MessageSquare className="w-4 h-4 text-blue-500" />
            回复明细
          </h2>
          <span className="badge-primary">{total} 条记录</span>
        </div>
        <div className="flex-1 overflow-auto relative">
          {loading ? (
            <div className="flex justify-center py-8">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : (
            <table className="table-ios min-w-[1800px]">
              <thead className="sticky top-0 bg-white dark:bg-slate-800 z-[1]">
                <tr>
                  <th>所属用户</th>
                  <th>账号</th>
                  <th>发送方</th>
                  <th>商品</th>
                  <th>订单号</th>
                  <th>策略</th>
                  <th>回复类型</th>
                  <th>命中关键词</th>
                  <th>规则类型</th>
                  <th>收到消息时间</th>
                  <th>收到消息</th>
                  <th>回复内容</th>
                  <th>发送状态</th>
                  <th>发送失败原因</th>
                  <th>AI模型</th>
                  <th>会话ID</th>
                  <th>消息ID</th>
                  <th>决策原因</th>
                  <th>创建时间</th>
                </tr>
              </thead>
              <tbody>
                {logs.length === 0 ? (
                  <tr>
                    <td colSpan={19}>
                      <div className="empty-state py-8">
                        <p className="text-slate-500 dark:text-slate-400">暂无消息日志</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  logs.map((log) => (
                    <tr key={log.id}>
                      <td className="align-top min-w-[140px]">
                        <div>{renderText(log.owner_username)}</div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">{renderText(log.owner_id?.toString())}</div>
                      </td>
                      <td className="align-top min-w-[180px]">
                        <div className="font-medium text-blue-600 dark:text-blue-400">{renderText(log.account_id)}</div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">{renderText(log.account_name)}</div>
                      </td>
                      <td className="align-top min-w-[180px]">
                        <div>{renderText(log.sender_user_name)}</div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">{renderText(log.sender_user_id)}</div>
                      </td>
                      <td className="align-top min-w-[220px]">
                        <div className="font-medium">{renderText(log.item_title)}</div>
                        <div className="text-xs text-slate-500 dark:text-slate-400 break-all">{renderText(log.item_id)}</div>
                      </td>
                      <td className="align-top min-w-[180px] break-all">{renderText(log.order_no)}</td>
                      <td className="align-top whitespace-nowrap">{buildStrategyLabel(log)}</td>
                      <td className="align-top whitespace-nowrap">{buildReplyModeLabel(log.reply_mode)}</td>
                      <td className="align-top min-w-[160px] break-all">{renderText(log.matched_keyword)}</td>
                      <td className="align-top whitespace-nowrap">{buildMatchedRuleTypeLabel(log.matched_rule_type)}</td>
                      <td className="align-top whitespace-nowrap">{formatDateTime(log.source_message_time)}</td>
                      <td className="align-top min-w-[260px] max-w-[320px] whitespace-pre-wrap break-words">{renderText(log.source_message)}</td>
                      <td className="align-top min-w-[300px] max-w-[360px] whitespace-pre-wrap break-words">
                        <div>{renderText(log.reply_text)}</div>
                        {log.reply_image_url ? (
                          <div className="mt-1 text-xs text-blue-600 dark:text-blue-400 break-all">{log.reply_image_url}</div>
                        ) : null}
                      </td>
                      <td className="align-top whitespace-nowrap">{buildSendStatusLabel(log.send_status)}</td>
                      <td className="align-top min-w-[220px] max-w-[320px] whitespace-pre-wrap break-words text-red-600 dark:text-red-400">{renderText(log.send_fail_reason)}</td>
                      <td className="align-top min-w-[180px]">
                        <div>{renderText(log.ai_model_name)}</div>
                        <div className="text-xs text-slate-500 dark:text-slate-400">{renderText(log.ai_provider_name)}</div>
                      </td>
                      <td className="align-top min-w-[180px] break-all">{renderText(log.chat_id)}</td>
                      <td className="align-top min-w-[180px] break-all">{renderText(log.source_message_id)}</td>
                      <td className="align-top min-w-[180px] break-all">{buildDecisionReasonLabel(log.decision_reason)}</td>
                      <td className="align-top whitespace-nowrap">{formatDateTime(log.created_at)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}
        </div>

        {total > 0 && (
          <div className="flex-shrink-0 flex flex-col lg:flex-row items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700 gap-3">
            <div className="flex items-center gap-3 text-sm text-gray-500">
              <span>共 {total} 条记录</span>
              <div className="flex items-center gap-2">
                <span>每页</span>
                <select
                  value={pageSize}
                  onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                  className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800"
                >
                  {PAGE_SIZE_OPTIONS.map((size) => (
                    <option key={size} value={size}>{size}</option>
                  ))}
                </select>
                <span>条</span>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">第 {page} / {totalPages || 1} 页</span>
              <button
                onClick={() => handlePageChange(page - 1)}
                disabled={page <= 1 || loading}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <button
                onClick={() => handlePageChange(page + 1)}
                disabled={page >= totalPages || loading}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
