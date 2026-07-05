/**
 * 接口续期Cookies批次列表页面
 *
 * 功能：
 * 1. 显示接口续期Cookies批次列表（每行代表一次定时任务执行）
 * 2. 支持按日期范围筛选和分页查看
 * 3. 支持清空 10 天前的历史日志
 */
import { RefreshCw } from 'lucide-react'
import {
  clearApiCookieRenewLogs,
  getApiCookieRenewBatches,
  type ApiCookieRenewBatch,
} from '@/api/apiCookieRenewLogs'
import {
  BatchLogList,
  renderFailedCount,
  renderIconCount,
  renderPlainCount,
  renderSuccessCount,
  type BatchLogColumn,
} from '@/components/common/BatchLogList'

const columns: BatchLogColumn<ApiCookieRenewBatch>[] = [
  {
    title: '处理账号数',
    render: (batch) => renderPlainCount(batch.total_accounts),
  },
  {
    title: '成功',
    render: (batch) => renderSuccessCount(batch.success_count),
  },
  {
    title: 'Cookie更新',
    render: (batch) =>
      renderIconCount(batch.cookie_updated_count, RefreshCw, 'text-blue-600 dark:text-blue-400'),
  },
  {
    title: '失败',
    render: (batch) => renderFailedCount(batch.failed_count),
  },
]

export function ApiCookieRenewBatches() {
  return (
    <BatchLogList
      title="接口续期Cookies日志"
      description="查看通过  接口定时续期 Cookies 的执行记录"
      fetchBatches={getApiCookieRenewBatches}
      columns={columns}
      detailPath={(batchId) => `/admin/api-cookie-renew-batches/${batchId}`}
      clearLogs={clearApiCookieRenewLogs}
      loadErrorMessage="加载接口续期Cookies日志失败"
    />
  )
}
