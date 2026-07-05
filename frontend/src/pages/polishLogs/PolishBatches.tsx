/**
 * 定时擦亮执行记录页面
 *
 * 功能：
 * 1. 显示所有定时任务执行批次列表
 * 2. 支持时间范围筛选
 * 3. 点击行跳转到批次详情页
 */
import { getPolishBatches, clearPolishLogs, type PolishBatch } from '@/api/polishLogs'
import {
  BatchLogList,
  renderFailedCount,
  renderPlainCount,
  renderRateCell,
  renderSuccessCount,
  type BatchLogColumn,
} from '@/components/common/BatchLogList'

const columns: BatchLogColumn<PolishBatch>[] = [
  {
    title: '处理商品数',
    render: (batch) => renderPlainCount(batch.total_items),
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
    render: (batch) => renderRateCell(batch.success_count, batch.failed_count, batch.total_items),
  },
]

export function PolishBatches() {
  return (
    <BatchLogList
      title="定时擦亮日志"
      description="查看定时任务执行记录"
      fetchBatches={getPolishBatches}
      clearLogs={clearPolishLogs}
      columns={columns}
      detailPath={(batchId) => `/admin/polish-batches/${batchId}`}
      clearConfirmMessage="此操作将清空10天前的擦亮日志数据，最近10天的日志将被保留。确定要继续吗？"
      showPageSizeSelector={false}
    />
  )
}
