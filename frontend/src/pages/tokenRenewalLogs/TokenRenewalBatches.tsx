/**
 * Token 续期执行记录页面。
 *
 * 功能：
 * 1. 显示 token_renewal 定时任务执行批次。
 * 2. 支持日期筛选和后端分页。
 * 3. 点击批次行进入逐账号明细。
 */
import {
  getTokenRenewalBatches,
  type TokenRenewalBatch,
} from '@/api/tokenRenewalLogs'
import {
  BatchLogList,
  renderFailedCount,
  renderPlainCount,
  renderRateCell,
  renderSuccessCount,
  type BatchLogColumn,
} from '@/components/common/BatchLogList'

const columns: BatchLogColumn<TokenRenewalBatch>[] = [
  {
    title: '处理账号数',
    render: (batch) => renderPlainCount(batch.total_accounts),
  },
  {
    title: '成功',
    render: (batch) => renderSuccessCount(batch.success_count),
  },
  {
    title: '失败',
    render: (batch) => renderFailedCount(batch.failed_count),
  },
  {
    title: '成功率',
    render: (batch) =>
      renderRateCell(batch.success_count, batch.failed_count, batch.total_accounts),
  },
]

export function TokenRenewalBatches() {
  return (
    <BatchLogList
      title="Token续期日志"
      description="查看 Token 续期定时任务执行记录"
      fetchBatches={getTokenRenewalBatches}
      columns={columns}
      detailPath={(batchId) => `/admin/token-renewal-batches/${batchId}`}
    />
  )
}
