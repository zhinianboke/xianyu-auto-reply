/**
 * 账号消息通知关闭日志批次列表页面
 *
 * 功能：
 * 1. 显示所有定时任务执行批次列表
 * 2. 支持时间范围筛选
 * 3. 点击行跳转到批次详情页
 * 4. 支持清空10天前的日志
 */
import { getCloseNoticeBatches, clearCloseNoticeLogs, type CloseNoticeBatch } from '@/api/closeNoticeLogs'
import {
  BatchLogList,
  renderFailedCount,
  renderPlainCount,
  renderRateCell,
  renderSuccessCount,
  type BatchLogColumn,
} from '@/components/common/BatchLogList'

const columns: BatchLogColumn<CloseNoticeBatch>[] = [
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
    render: (batch) => renderRateCell(batch.success_count, batch.failed_count, batch.total_accounts),
  },
]

export function CloseNoticeBatches() {
  return (
    <BatchLogList
      title="消息通知关闭日志"
      description="查看关闭账号消息通知定时任务执行记录"
      fetchBatches={getCloseNoticeBatches}
      clearLogs={clearCloseNoticeLogs}
      columns={columns}
      detailPath={(batchId) => `/admin/close-notice-batches/${batchId}`}
      clearConfirmMessage="此操作将清空10天前的消息通知关闭日志数据，最近10天的日志将被保留。确定要继续吗？"
      showPageSizeSelector={false}
    />
  )
}
