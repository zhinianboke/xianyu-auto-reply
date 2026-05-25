/**
 * 接口续期Cookies批次详情页面
 *
 * 功能：
 * 1. 显示批次汇总信息（账号数 / 成功 / Cookie更新 / 失败）
 * 2. 显示该批次所有账号的接口续期日志列表（含更新字段、接口返回内容、错误信息）
 * 3. 支持按状态筛选 + 客户端分页
 */
import { CheckCircle, Clock, RefreshCw, Users, XCircle } from 'lucide-react'
import {
  getApiCookieRenewBatchDetail,
  type ApiCookieRenewBatchDetail,
  type ApiCookieRenewLog,
} from '@/api/apiCookieRenewLogs'
import {
  BatchLogDetail,
  renderAccountIdCell,
  renderDateTimeText,
  renderStatusBadge,
  type BatchLogStatusInfo,
  type BatchLogSummaryCard,
  type BatchLogTableColumn,
} from '@/components/common/BatchLogDetail'

const summaryCards: BatchLogSummaryCard<ApiCookieRenewBatchDetail>[] = [
  {
    icon: Users,
    iconBgClass: 'bg-purple-100 dark:bg-purple-900/30',
    iconColorClass: 'text-purple-600 dark:text-purple-400',
    label: '处理账号数',
    value: (batch) => batch.total_accounts,
  },
  {
    icon: CheckCircle,
    iconBgClass: 'bg-green-100 dark:bg-green-900/30',
    iconColorClass: 'text-green-600 dark:text-green-400',
    label: '成功',
    value: (batch) => batch.success_count,
    valueClass: 'text-2xl font-bold text-green-600 dark:text-green-400',
  },
  {
    icon: RefreshCw,
    iconBgClass: 'bg-blue-100 dark:bg-blue-900/30',
    iconColorClass: 'text-blue-600 dark:text-blue-400',
    label: 'Cookie更新',
    value: (batch) => batch.cookie_updated_count,
    valueClass: 'text-2xl font-bold text-blue-600 dark:text-blue-400',
  },
  {
    icon: XCircle,
    iconBgClass: 'bg-red-100 dark:bg-red-900/30',
    iconColorClass: 'text-red-600 dark:text-red-400',
    label: '失败',
    value: (batch) => batch.failed_count,
    valueClass: 'text-2xl font-bold text-red-600 dark:text-red-400',
  },
]

const STATUS_INFO_MAP: Record<string, BatchLogStatusInfo> = {
  success: {
    label: '成功',
    color: 'text-green-600 dark:text-green-400',
    Icon: CheckCircle,
  },
  cookie_updated: {
    label: 'Cookie更新',
    color: 'text-blue-600 dark:text-blue-400',
    Icon: RefreshCw,
  },
  failed: {
    label: '失败',
    color: 'text-red-600 dark:text-red-400',
    Icon: XCircle,
  },
}

/**
 * 渲染更新字段名（鼠标悬停查看完整列表，超长截断显示）。
 */
function renderUpdatedCookieNames(log: ApiCookieRenewLog) {
  if (!log.updated_cookie_names || log.updated_cookie_count <= 0) {
    return <span className="text-slate-400">-</span>
  }
  const namesText = log.updated_cookie_names
  const displayText = namesText.length > 60 ? `${namesText.slice(0, 60)}...` : namesText
  return (
    <span
      className="text-xs text-blue-600 dark:text-blue-400 font-mono"
      title={namesText}
    >
      {displayText}
    </span>
  )
}

/**
 * 渲染失败时的接口返回内容（鼠标悬停查看完整内容，截断展示）。
 */
function renderResponseContent(log: ApiCookieRenewLog) {
  const content = log.response_content || log.error_message
  if (!content) {
    return <span className="text-slate-400">-</span>
  }
  const displayText = content.length > 80 ? `${content.slice(0, 80)}...` : content
  return (
    <span
      className="text-xs text-slate-600 dark:text-slate-400 break-all"
      title={content}
    >
      {displayText}
    </span>
  )
}

/**
 * 渲染账号状态标签。
 */
function renderAccountStatus(log: ApiCookieRenewLog) {
  const status = log.account_status || 'unknown'
  const statusMap: Record<string, { label: string; className: string }> = {
    active: { label: '启用', className: 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-900/20' },
    inactive: { label: '禁用', className: 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20' },
    disabled: { label: '禁用', className: 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-900/20' },
    suspended: { label: '暂停', className: 'text-orange-600 dark:text-orange-400 bg-orange-50 dark:bg-orange-900/20' },
    unknown: { label: '未知', className: 'text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800/30' },
  }
  const info = statusMap[status] || statusMap.unknown
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${info.className}`}>
      {info.label}
    </span>
  )
}

const columns: BatchLogTableColumn<ApiCookieRenewLog>[] = [
  { title: '账号ID', render: (log) => renderAccountIdCell(log.account_id) },
  { title: '账号状态', render: renderAccountStatus },
  {
    title: '状态',
    render: (log) =>
      renderStatusBadge(
        STATUS_INFO_MAP[log.status] ?? {
          label: log.status,
          color: 'text-slate-500 dark:text-slate-400',
          Icon: Clock,
        },
      ),
  },
  { title: '更新字段数', render: (log) => log.updated_cookie_count },
  { title: '更新字段名', render: renderUpdatedCookieNames },
  { title: '说明/接口返回', render: renderResponseContent },
  { title: '执行时间', render: (log) => renderDateTimeText(log.created_at) },
]

export function ApiCookieRenewBatchDetailPage() {
  return (
    <BatchLogDetail<ApiCookieRenewBatchDetail, ApiCookieRenewLog>
      fetchDetail={getApiCookieRenewBatchDetail}
      backPath="/admin/api-cookie-renew-batches"
      pageTitle="接口续期Cookies批次详情"
      summaryCards={summaryCards}
      summaryGridClass="grid-cols-2 md:grid-cols-4"
      logTitle="续期日志"
      statusOptions={[
        { value: 'all', label: '全部状态' },
        { value: 'success', label: '成功' },
        { value: 'cookie_updated', label: 'Cookie更新' },
        { value: 'failed', label: '失败' },
      ]}
      columns={columns}
      cardHeightStyle={{ height: 'calc(100vh - 380px)', minHeight: '320px' }}
      enableClientPagination
      defaultPageSize={20}
      loadErrorMessage="加载批次详情失败"
    />
  )
}
