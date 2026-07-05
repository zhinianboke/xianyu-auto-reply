/**
 * 求小红花日志页面
 *
 * 功能：
 * 1. 显示所有求小红花执行批次列表
 * 2. 支持时间范围筛选
 * 3. 点击行跳转到批次详情页
 */
import { getRedFlowerBatches, clearRedFlowerLogs, type RedFlowerBatch } from '@/api/redFlowerLogs'
import {
  BatchLogList,
  renderFailedCount,
  renderPlainCount,
  renderRateCell,
  renderSuccessCount,
  type BatchLogColumn,
} from '@/components/common/BatchLogList'

const columns: BatchLogColumn<RedFlowerBatch>[] = [
  {
    title: '处理订单数',
    render: (batch) => renderPlainCount(batch.total_orders),
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
    render: (batch) => renderRateCell(batch.success_count, batch.failed_count, batch.total_orders),
  },
]

export function RedFlowerBatches() {
  return (
    <BatchLogList
      title="求小红花日志"
      description="查看求小红花定时任务执行记录"
      fetchBatches={getRedFlowerBatches}
      clearLogs={clearRedFlowerLogs}
      columns={columns}
      detailPath={(batchId) => `/admin/red-flower-batches/${batchId}`}
      clearConfirmMessage="此操作将清空10天前的求小红花日志数据，最近10天的日志将被保留。确定要继续吗？"
      showPageSizeSelector={false}
    />
  )
}
