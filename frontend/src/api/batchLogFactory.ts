/**
 * 批次日志 API 工厂
 *
 * 功能：
 * 1. 统一构建批次日志的列表查询、详情查询、清空日志接口
 * 2. 7 类批次日志 API（擦亮 / 补评价 / 补发货 / 求小红花 / 登录续期 / 消息通知关闭 / COOKIES 刷新）共享同一套查询逻辑，仅路径与统计字段不同
 * 3. 调用方提供具体的批次类型与详情类型，路径只需提供 ``batches`` 与可选 ``clearLogs``
 */
import { del, get } from '@/utils/request'

const ADMIN_PREFIX = '/api/v1/admin'

/**
 * 批次列表查询参数。
 */
export interface BatchListQuery {
  start_date?: string
  end_date?: string
  page?: number
  page_size?: number
}

/**
 * 批次列表响应结构。
 *
 * 与 ``frontend/src/components/common/BatchLogList`` 的同名类型保持结构一致；
 * TypeScript 结构兼容性会让两边互相可赋值。
 */
export interface BatchListResponse<TBatch> {
  success: boolean
  message?: string
  data: TBatch[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/**
 * 批次详情响应结构。
 *
 * 调用方可用 ``createBatchLogApi<TBatch, TDetail | null>`` 让 ``data`` 接受 null
 * （COOKIES 刷新批次详情接口存在批次不存在的情况）。
 */
export interface BatchDetailResponse<TDetail> {
  success: boolean
  message?: string
  data: TDetail
}

/**
 * 批次日志接口路径配置。
 *
 * @property batches 批次资源路径，例如 ``polish-batches``
 * @property clearLogs 清空日志路径，例如 ``polish-logs/clear``；不传则不暴露 clearLogs 函数
 */
export interface BatchLogPaths {
  batches: string
  clearLogs?: string
}

/**
 * 不带清空日志接口的工厂返回值。
 */
export interface BatchLogApi<TBatch, TDetail> {
  getBatches: (params?: BatchListQuery) => Promise<BatchListResponse<TBatch>>
  getBatchDetail: (batchId: string) => Promise<BatchDetailResponse<TDetail>>
}

/**
 * 带清空日志接口的工厂返回值。
 */
export interface BatchLogApiWithClear<TBatch, TDetail> extends BatchLogApi<TBatch, TDetail> {
  clearLogs: () => Promise<{ success: boolean; message?: string }>
}

interface UnifiedApiResponse<TData> {
  success: boolean
  code: number
  message: string
  data: TData | null
}

interface UnifiedBatchPage<TBatch> {
  items: TBatch[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

/**
 * 构造批次列表查询字符串。
 *
 * 行为与 7 个原始 API 文件中的 URLSearchParams 拼接逻辑完全一致：
 * 仅当字段为真值时才追加，page/page_size 转字符串。
 */
function buildBatchesQuery(params?: BatchListQuery): string {
  if (!params) return ''
  const searchParams = new URLSearchParams()
  if (params.start_date) searchParams.append('start_date', params.start_date)
  if (params.end_date) searchParams.append('end_date', params.end_date)
  if (params.page) searchParams.append('page', params.page.toString())
  if (params.page_size) searchParams.append('page_size', params.page_size.toString())
  const query = searchParams.toString()
  return query ? `?${query}` : ''
}

export function createBatchLogApi<TBatch, TDetail>(
  paths: BatchLogPaths & { clearLogs: string },
): BatchLogApiWithClear<TBatch, TDetail>
export function createBatchLogApi<TBatch, TDetail>(
  paths: BatchLogPaths,
): BatchLogApi<TBatch, TDetail>
export function createBatchLogApi<TBatch, TDetail>(
  paths: BatchLogPaths,
): BatchLogApi<TBatch, TDetail> | BatchLogApiWithClear<TBatch, TDetail> {
  const batchesUrl = `${ADMIN_PREFIX}/${paths.batches}`

  const getBatches = (params?: BatchListQuery) =>
    get<BatchListResponse<TBatch>>(`${batchesUrl}${buildBatchesQuery(params)}`)

  const getBatchDetail = (batchId: string) =>
    get<BatchDetailResponse<TDetail>>(`${batchesUrl}/${batchId}`)

  if (!paths.clearLogs) {
    return { getBatches, getBatchDetail }
  }

  const clearLogsUrl = `${ADMIN_PREFIX}/${paths.clearLogs}`
  const clearLogs = () =>
    del<{ success: boolean; message?: string }>(clearLogsUrl)

  return { getBatches, getBatchDetail, clearLogs }
}

/**
 * 构造使用项目统一响应体、且不提供清理入口的批次日志 API。
 */
export function createUnifiedBatchLogApi<TBatch, TDetail>(
  batchesPath: string,
): BatchLogApi<TBatch, TDetail> {
  const batchesUrl = `${ADMIN_PREFIX}/${batchesPath}`

  const getBatches = async (params?: BatchListQuery): Promise<BatchListResponse<TBatch>> => {
    const response = await get<UnifiedApiResponse<UnifiedBatchPage<TBatch>>>(
      `${batchesUrl}${buildBatchesQuery(params)}`,
    )
    if (!response.success || !response.data) {
      return {
        success: false,
        message: response.message,
        data: [],
        total: 0,
        page: params?.page ?? 1,
        page_size: params?.page_size ?? 20,
        total_pages: 0,
      }
    }
    return {
      success: true,
      message: response.message,
      data: response.data.items,
      total: response.data.total,
      page: response.data.page,
      page_size: response.data.page_size,
      total_pages: response.data.total_pages,
    }
  }

  const getBatchDetail = (batchId: string) =>
    get<BatchDetailResponse<TDetail>>(`${batchesUrl}/${batchId}`)

  return { getBatches, getBatchDetail }
}
