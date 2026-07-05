/**
 * 登录续期执行记录页面
 *
 * 功能：
 * 1. 显示所有定时任务执行批次列表
 * 2. 支持时间范围筛选
 * 3. 点击行跳转到批次详情页
 */
import { AlertTriangle, Key } from 'lucide-react'
import { getLoginRenewBatches, clearLoginRenewLogs, type LoginRenewBatch } from '@/api/loginRenewLogs'
import {
  BatchLogList,
  renderFailedCount,
  renderIconCount,
  renderPlainCount,
  renderSuccessCount,
  type BatchLogColumn,
} from '@/components/common/BatchLogList'

const columns: BatchLogColumn<LoginRenewBatch>[] = [
  {
    title: '处理账号数',
    render: (batch) => renderPlainCount(batch.total_accounts),
  },
  {
    title: '正常',
    render: (batch) => renderSuccessCount(batch.success_count),
  },
  {
    title: '令牌刷新',
    render: (batch) => renderIconCount(batch.token_refreshed_count, Key, 'text-blue-600 dark:text-blue-400'),
  },
  {
    title: 'Session过期',
    render: (batch) => renderIconCount(batch.session_expired_count, AlertTriangle, 'text-amber-600 dark:text-amber-400'),
  },
  {
    title: '失败',
    render: (batch) => renderFailedCount(batch.failed_count),
  },
]

export function LoginRenewBatches() {
  return (
    <BatchLogList
      title="登录续期日志"
      description="查看登录状态续期定时任务执行记录"
      fetchBatches={getLoginRenewBatches}
      clearLogs={clearLoginRenewLogs}
      columns={columns}
      detailPath={(batchId) => `/admin/login-renew-batches/${batchId}`}
      clearConfirmMessage="此操作将清空10天前的登录续期日志数据，最近10天的日志将被保留。确定要继续吗？"
      showPageSizeSelector={false}
    />
  )
}
