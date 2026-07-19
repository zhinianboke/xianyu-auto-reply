/**
 * Token 续期批次详情页面。
 *
 * 功能：
 * 1. 显示批次总数、成功数、失败数和成功率。
 * 2. 显示逐账号续期状态、到期时间及结果说明。
 * 3. 支持按成功、失败状态筛选明细。
 */
import { CheckCircle, Clock, KeyRound, XCircle } from 'lucide-react'
import {
  getTokenRenewalBatchDetail,
  type TokenRenewalBatchDetail,
  type TokenRenewalLog,
} from '@/api/tokenRenewalLogs'
import {
  BatchLogDetail,
  renderAccountIdCell,
  renderDateTimeText,
  renderDescriptionCell,
  renderMonoCell,
  renderSuccessFailedBadge,
  type BatchLogSummaryCard,
  type BatchLogTableColumn,
} from '@/components/common/BatchLogDetail'

const summaryCards: BatchLogSummaryCard<TokenRenewalBatchDetail>[] = [
  {
    icon: KeyRound,
    iconBgClass: 'bg-blue-100 dark:bg-blue-900/30',
    iconColorClass: 'text-blue-600 dark:text-blue-400',
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
    icon: XCircle,
    iconBgClass: 'bg-red-100 dark:bg-red-900/30',
    iconColorClass: 'text-red-600 dark:text-red-400',
    label: '失败',
    value: (batch) => batch.failed_count,
    valueClass: 'text-2xl font-bold text-red-600 dark:text-red-400',
  },
  {
    icon: Clock,
    iconBgClass: 'bg-amber-100 dark:bg-amber-900/30',
    iconColorClass: 'text-amber-600 dark:text-amber-400',
    label: '成功率',
    value: (batch) =>
      `${batch.total_accounts > 0
        ? ((batch.success_count / batch.total_accounts) * 100).toFixed(1)
        : 0}%`,
    valueClass: 'text-2xl font-bold text-amber-600 dark:text-amber-400',
  },
]

const columns: BatchLogTableColumn<TokenRenewalLog>[] = [
  { title: '账号ID', render: (log) => renderAccountIdCell(log.account_id) },
  { title: 'Token用户ID', render: (log) => renderMonoCell(log.token_user_id) },
  { title: '状态', render: (log) => renderSuccessFailedBadge(log.status) },
  {
    title: '续期到期时间',
    render: (log) => renderDateTimeText(log.renew_expire_at),
  },
  { title: '结果说明', render: (log) => renderDescriptionCell(log.error_message, 60) },
  { title: '执行时间', render: (log) => renderDateTimeText(log.created_at) },
]

export function TokenRenewalBatchDetailPage() {
  return (
    <BatchLogDetail<TokenRenewalBatchDetail, TokenRenewalLog>
      fetchDetail={getTokenRenewalBatchDetail}
      backPath="/admin/token-renewal-batches"
      summaryCards={summaryCards}
      summaryGridClass="grid-cols-2 md:grid-cols-4"
      logTitle="Token续期明细"
      statusOptions={[
        { value: 'all', label: '全部状态' },
        { value: 'success', label: '成功' },
        { value: 'failed', label: '失败' },
      ]}
      columns={columns}
    />
  )
}
