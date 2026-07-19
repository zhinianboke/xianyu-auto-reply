/**
 * 批次日志详情通用组件
 *
 * 功能：
 * 1. 统一封装 7 类批次日志的详情页（擦亮 / 补评价 / 补发货 / 求小红花 / 登录续期 / 消息通知关闭 / COOKIES 刷新）
 * 2. 统一处理：详情数据加载、加载遮罩、批次不存在态、Header、汇总卡片、状态筛选、固定高度滚动表格、可选客户端分页
 * 3. 通过配置项区分：返回路径、汇总卡布局、状态筛选 UI、表格列、卡片高度、错误处理等
 *
 * 设计约束：
 * - 不改变原 7 个详情页的视觉与行为；调用方只需提供配置即可保持原样
 * - 不替前端包装错误信息：直接把后端 message / 异常 message 透传到 toast
 * - 客户端分页仅在 enableClientPagination 为 true 时启用
 */
import { ReactNode, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  type LucideIcon,
} from 'lucide-react'
import { useUIStore } from '@/store/uiStore'
import { PageLoading } from '@/components/common/Loading'
import { formatDateTime } from '@/utils/date'

// 重新导出 helpers，保持原有 `import { ... } from '@/components/common/BatchLogDetail'` 路径不变
export {
  renderAccountIdCell,
  renderDateTimeText,
  renderDescriptionCell,
  renderFullError,
  renderMonoCell,
  renderStatusBadge,
  renderSuccessFailedBadge,
  renderTruncatedError,
  type BatchLogStatusInfo,
} from './BatchLogDetailHelpers'

/**
 * 详情接口返回的数据结构。
 *
 * 与 ``frontend/src/api/batchLogFactory`` 的 BatchDetailResponse 兼容。
 */
export interface BatchLogDetailFetchResult<TBatch> {
  success: boolean
  message?: string
  data: TBatch | null
}

/**
 * 状态筛选选项：状态筛选下拉/胶囊按钮使用。
 *
 * 第一项约定为 ``{ value: 'all', label: '全部状态' }`` 或类似全部选项。
 */
export interface BatchLogStatusOption {
  value: string
  label: string
}

/**
 * 汇总卡片配置。
 */
export interface BatchLogSummaryCard<TBatch> {
  /** 图标组件（lucide-react）。 */
  icon: LucideIcon
  /** 图标背景色 class（仅 inline 布局使用）。 */
  iconBgClass?: string
  /** 图标颜色 class。 */
  iconColorClass: string
  /** 卡片左侧/底部的标签文字。 */
  label: string
  /** 卡片中间或顶部展示的值，可以是数字也可以是富文本。 */
  value: (batch: TBatch) => ReactNode
  /** 自定义值的样式。如不传，按 layout 给出默认样式。 */
  valueClass?: string
}

/**
 * 表格列配置。
 */
export interface BatchLogTableColumn<TLog> {
  title: string
  className?: string
  render: (log: TLog) => ReactNode
}

/**
 * 通用详情组件 Props。
 */
export interface BatchLogDetailProps<
  TBatch extends { executed_at: string; logs: TLog[] },
  TLog extends { id: number; status: string },
> {
  /** 详情请求函数。 */
  fetchDetail: (batchId: string) => Promise<BatchLogDetailFetchResult<TBatch>>
  /** 返回列表的路由路径，例如 ``/admin/polish-batches`` 。 */
  backPath: string
  /** 页面主标题，默认 ``批次详情`` 。 */
  pageTitle?: string
  /**
   * 页面描述。默认渲染 ``执行时间：...`` 。
   * 如传函数则使用调用方提供的描述（例如静态文本）。
   */
  pageDescription?: (batch: TBatch) => ReactNode
  /** 汇总卡片配置。 */
  summaryCards: BatchLogSummaryCard<TBatch>[]
  /** 汇总卡 grid 类，默认 ``grid-cols-1 md:grid-cols-4`` 。 */
  summaryGridClass?: string
  /** 汇总卡布局，默认 ``inline`` 。 */
  summaryCardLayout?: 'inline' | 'centered'
  /** 日志区域标题。 */
  logTitle: string
  /** 状态筛选选项。 */
  statusOptions: BatchLogStatusOption[]
  /** 状态筛选 UI 风格，默认 ``select`` 。 */
  filterStyle?: 'select' | 'pill'
  /** 日志表格列。 */
  columns: BatchLogTableColumn<TLog>[]
  /** 空记录提示文字，默认 ``暂无日志记录`` 。 */
  emptyText?: string
  /** 日志卡的高度样式，默认 ``calc(100vh - 400px)`` / ``300px`` 。 */
  cardHeightStyle?: { height?: string; minHeight?: string }
  /** 是否启用客户端分页（仅 COOKIES 刷新使用）。 */
  enableClientPagination?: boolean
  /** 默认每页条数，默认 20。 */
  defaultPageSize?: number
  /** 每页条数选项，默认 ``[10, 20, 50, 100]`` 。 */
  pageSizeOptions?: number[]
  /** 加载失败兜底文案，默认 ``加载数据失败`` 。 */
  loadErrorMessage?: string
  /** Header 风格，默认 ``left-back`` （左侧返回 + 标题 + 右侧刷新）。 */
  headerLayout?: 'left-back' | 'right-back'
}

const DEFAULT_PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

export function BatchLogDetail<
  TBatch extends { executed_at: string; logs: TLog[] },
  TLog extends { id: number; status: string },
>({
  fetchDetail,
  backPath,
  pageTitle = '批次详情',
  pageDescription,
  summaryCards,
  summaryGridClass = 'grid-cols-1 md:grid-cols-4',
  summaryCardLayout = 'inline',
  logTitle,
  statusOptions,
  filterStyle = 'select',
  columns,
  emptyText = '暂无日志记录',
  cardHeightStyle,
  enableClientPagination = false,
  defaultPageSize = 20,
  pageSizeOptions = DEFAULT_PAGE_SIZE_OPTIONS,
  loadErrorMessage = '加载数据失败',
  headerLayout = 'left-back',
}: BatchLogDetailProps<TBatch, TLog>) {
  const { batchId } = useParams<{ batchId: string }>()
  const navigate = useNavigate()
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [batchDetail, setBatchDetail] = useState<TBatch | null>(null)
  const [statusFilter, setStatusFilter] = useState<string>('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(defaultPageSize)

  const loadBatchDetail = async () => {
    if (!batchId) return
    try {
      setLoading(true)
      const result = await fetchDetail(batchId)
      if (result.success && result.data) {
        setBatchDetail(result.data)
      } else {
        setBatchDetail(null)
        addToast({ type: 'error', message: result.message || loadErrorMessage })
      }
    } catch (error: unknown) {
      setBatchDetail(null)
      const msg = error instanceof Error ? error.message : loadErrorMessage
      addToast({ type: 'error', message: msg })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadBatchDetail()
  }, [batchId])

  useEffect(() => {
    if (enableClientPagination) {
      setPage(1)
    }
  }, [statusFilter, pageSize, enableClientPagination])

  const filteredLogs = useMemo(() => {
    if (!batchDetail) return []
    return batchDetail.logs.filter((log) => statusFilter === 'all' || log.status === statusFilter)
  }, [batchDetail, statusFilter])

  const totalPages = enableClientPagination && filteredLogs.length > 0
    ? Math.ceil(filteredLogs.length / pageSize)
    : 0
  const visibleLogs = enableClientPagination
    ? filteredLogs.slice((page - 1) * pageSize, page * pageSize)
    : filteredLogs

  if (loading) {
    return <PageLoading />
  }

  if (!batchDetail) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <p className="text-slate-500 dark:text-slate-400 mb-4">批次不存在</p>
        <button onClick={() => navigate(backPath)} className="btn-ios-secondary">
          <ArrowLeft className="w-4 h-4" />
          返回列表
        </button>
      </div>
    )
  }

  const titleNode = (
    <div>
      <h1 className="page-title">{pageTitle}</h1>
      <p className="page-description">
        {pageDescription
          ? pageDescription(batchDetail)
          : `执行时间：${formatDateTime(batchDetail.executed_at)}`}
      </p>
    </div>
  )

  const renderHeader = () => {
    if (headerLayout === 'right-back') {
      return (
        <div className="page-header flex-between">
          {titleNode}
          <div className="flex gap-2">
            <button onClick={loadBatchDetail} className="btn-ios-secondary">
              <RefreshCw className="w-4 h-4" />
              刷新
            </button>
            <button onClick={() => navigate(backPath)} className="btn-ios-secondary">
              <ArrowLeft className="w-4 h-4" />
              返回列表
            </button>
          </div>
        </div>
      )
    }
    return (
      <div className="page-header flex-between">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate(backPath)}
            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          {titleNode}
        </div>
        <button onClick={loadBatchDetail} className="btn-ios-secondary">
          <RefreshCw className="w-4 h-4" />
          刷新
        </button>
      </div>
    )
  }

  const renderSummaryCards = () => {
    const cards = summaryCards.map((card, idx) => {
      const Icon = card.icon
      const value = card.value(batchDetail)
      if (summaryCardLayout === 'centered') {
        return (
          <div key={idx} className="vben-card">
            <div className="vben-card-body text-center">
              <div className="flex justify-center mb-2">
                <Icon className={`w-6 h-6 ${card.iconColorClass}`} />
              </div>
              <div className={card.valueClass ?? 'text-2xl font-bold text-slate-800 dark:text-slate-100'}>
                {value}
              </div>
              <div className="text-sm text-slate-500 dark:text-slate-400 mt-1">{card.label}</div>
            </div>
          </div>
        )
      }
      return (
        <div key={idx} className="vben-card">
          <div className="vben-card-body flex items-center gap-4">
            <div
              className={`w-12 h-12 rounded-lg ${card.iconBgClass ?? ''} flex items-center justify-center`}
            >
              <Icon className={`w-6 h-6 ${card.iconColorClass}`} />
            </div>
            <div>
              <p className="text-sm text-slate-500 dark:text-slate-400">{card.label}</p>
              <p className={card.valueClass ?? 'text-2xl font-bold text-slate-900 dark:text-slate-100'}>
                {value}
              </p>
            </div>
          </div>
        </div>
      )
    })
    return <div className={`grid gap-4 ${summaryGridClass}`}>{cards}</div>
  }

  const renderStatusFilter = () => {
    if (filterStyle === 'pill') {
      return (
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-500">筛选：</span>
          {statusOptions.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setStatusFilter(opt.value)}
              className={`px-3 py-1 rounded-full text-sm font-medium transition-colors ${
                statusFilter === opt.value
                  ? 'bg-blue-500 text-white'
                  : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600'
              }`}
            >
              {opt.label}
            </button>
          ))}
          <span className="badge-primary">{filteredLogs.length} 条</span>
        </div>
      )
    }
    return (
      <div className="flex flex-wrap items-center gap-2">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-sm"
        >
          {statusOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
        {enableClientPagination && (
          <select
            value={pageSize}
            onChange={(e) => setPageSize(Number(e.target.value))}
            className="px-3 py-1.5 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-sm"
          >
            {pageSizeOptions.map((size) => (
              <option key={size} value={size}>
                {size} 条/页
              </option>
            ))}
          </select>
        )}
        <span className="badge-primary">{filteredLogs.length} 条记录</span>
      </div>
    )
  }

  const renderLogsTable = () => (
    <div
      className="vben-card flex flex-col"
      style={{
        height: cardHeightStyle?.height ?? 'calc(100vh - 400px)',
        minHeight: cardHeightStyle?.minHeight ?? '300px',
      }}
    >
      <div
        className={`vben-card-header flex-shrink-0 ${filterStyle === 'pill' ? '' : 'flex-between'}`}
      >
        <h2 className="vben-card-title">{logTitle}</h2>
        {renderStatusFilter()}
      </div>
      <div className="table-scroll">
        <table className="table-ios">
          <thead>
            <tr>
              {columns.map((col, idx) => (
                <th key={idx} className={col.className}>
                  {col.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {visibleLogs.length === 0 ? (
              <tr>
                <td colSpan={columns.length}>
                  <div className="empty-state py-8">
                    <p className="text-slate-500 dark:text-slate-400">{emptyText}</p>
                  </div>
                </td>
              </tr>
            ) : (
              visibleLogs.map((log) => (
                <tr key={log.id}>
                  {columns.map((col, idx) => (
                    <td key={idx} className={col.className}>
                      {col.render(log)}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      {enableClientPagination && filteredLogs.length > 0 && (
        <div className="flex-shrink-0 flex flex-col lg:flex-row items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700 gap-3">
          <div className="text-sm text-gray-500">共 {filteredLogs.length} 条记录</div>
          <div className="flex items-center gap-2">
            <span className="text-sm text-gray-500">
              第 {page} / {totalPages} 页
            </span>
            <button
              onClick={() => setPage((current) => Math.max(1, current - 1))}
              disabled={page <= 1}
              className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage((current) => Math.min(totalPages, current + 1))}
              disabled={page >= totalPages}
              className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )

  return (
    <div className="space-y-4">
      {renderHeader()}
      {renderSummaryCards()}
      {renderLogsTable()}
    </div>
  )
}
