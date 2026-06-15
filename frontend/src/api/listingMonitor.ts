/**
 * 商品上新监控任务 API
 *
 * 功能：
 * 1. 查询上新监控任务分页列表
 * 2. 新建、编辑、启停、批量删除监控任务
 */
import { get, post, put } from '@/utils/request'
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/product-monitor/listing-tasks'

export type MonitorType = 'listing' | 'price_drop'

// 监控类型选项（前端统一展示中文）
export const MONITOR_TYPE_OPTIONS: { value: MonitorType; label: string }[] = [
  { value: 'listing', label: '上新监控' },
  { value: 'price_drop', label: '降价监控' },
]

export const MONITOR_TYPE_LABELS: Record<string, string> = MONITOR_TYPE_OPTIONS.reduce(
  (acc, item) => {
    acc[item.value] = item.label
    return acc
  },
  {} as Record<string, string>
)

export interface ListingMonitorTask {
  id: number
  monitor_type: MonitorType
  keyword: string
  price_min?: number | null
  price_max?: number | null
  interval_minutes: number
  collect_pages: number
  account_ids: string[]
  dm_account_id?: string | null
  dm_content?: string | null
  order_account_id?: string | null
  is_enabled: boolean
  last_run_at?: string | null
  remark?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ListingMonitorTaskListData {
  list: ListingMonitorTask[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ListingMonitorTaskSaveParams {
  monitor_type: MonitorType
  keyword: string
  price_min?: number | null
  price_max?: number | null
  interval_minutes: number
  collect_pages: number
  account_ids: string[]
  dm_account_id?: string | null
  dm_content?: string | null
  order_account_id?: string | null
  is_enabled?: boolean
  remark?: string | null
}

export interface ListingMonitorBatchDeleteResult {
  success_count: number
  total_count: number
}

export const getListingMonitorTasks = (
  page = 1,
  pageSize = 20,
  params?: {
    keyword?: string
    isEnabled?: boolean
  }
): Promise<ApiResponse<ListingMonitorTaskListData>> => {
  const searchParams = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (params?.keyword) searchParams.append('keyword', params.keyword)
  if (params?.isEnabled !== undefined) searchParams.append('is_enabled', String(params.isEnabled))
  return get(`${PREFIX}?${searchParams.toString()}`)
}

export const createListingMonitorTask = (
  params: ListingMonitorTaskSaveParams
): Promise<ApiResponse<{ task: ListingMonitorTask }>> => {
  return post(`${PREFIX}`, params)
}

export const updateListingMonitorTask = (
  taskId: number,
  params: Partial<ListingMonitorTaskSaveParams>
): Promise<ApiResponse<{ task: ListingMonitorTask }>> => {
  return put(`${PREFIX}/${taskId}`, params)
}

export const updateListingMonitorTaskStatus = (
  taskId: number,
  isEnabled: boolean
): Promise<ApiResponse<{ task: ListingMonitorTask }>> => {
  return put(`${PREFIX}/${taskId}/status`, { is_enabled: isEnabled })
}

export const batchDeleteListingMonitorTasks = (
  taskIds: number[]
): Promise<ApiResponse<ListingMonitorBatchDeleteResult>> => {
  return post(`${PREFIX}/batch-delete`, { ids: taskIds })
}

// ==================== 监控任务下拉选项 ====================

export interface ListingMonitorTaskOption {
  id: number
  keyword: string
  monitor_type: MonitorType
}

export const getListingMonitorTaskOptions = (): Promise<ApiResponse<{ list: ListingMonitorTaskOption[] }>> => {
  return get(`${PREFIX}/options`)
}

// ==================== 监控日志 ====================

export interface ListingMonitorLog {
  id: number
  monitor_task_id: number
  monitor_type?: MonitorType | null
  keyword?: string | null
  account_id?: string | null
  used_account_ids: string[]
  pages: number
  fetched_count: number
  inserted_count: number
  updated_count: number
  status: string
  message?: string | null
  created_at?: string | null
}

export interface ListingMonitorLogListData {
  list: ListingMonitorLog[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export const getListingMonitorLogs = (
  page = 1,
  pageSize = 20,
  params?: { monitorTaskId?: number; status?: string; monitorType?: MonitorType }
): Promise<ApiResponse<ListingMonitorLogListData>> => {
  const searchParams = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (params?.monitorTaskId) searchParams.append('monitor_task_id', String(params.monitorTaskId))
  if (params?.status) searchParams.append('status', params.status)
  if (params?.monitorType) searchParams.append('monitor_type', params.monitorType)
  return get(`${PREFIX}/logs?${searchParams.toString()}`)
}

// ==================== 采集商品 ====================

export interface ListingMonitorItem {
  id: number
  monitor_task_id: number
  item_id: string
  title?: string | null
  price?: string | null
  area?: string | null
  pic_url?: string | null
  seller_id?: string | null
  seller_user_id?: string | null
  seller_nick?: string | null
  want_count?: string | null
  publish_time?: string | null
  target_url?: string | null
  has_detail?: boolean
  is_dm_sent: boolean
  is_ordered: boolean
  last_seen_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ListingMonitorItemListData {
  list: ListingMonitorItem[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export const getListingMonitorItems = (
  page = 1,
  pageSize = 20,
  params?: { monitorTaskId?: number; keyword?: string; area?: string; sellerNick?: string }
): Promise<ApiResponse<ListingMonitorItemListData>> => {
  const searchParams = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (params?.monitorTaskId) searchParams.append('monitor_task_id', String(params.monitorTaskId))
  if (params?.keyword) searchParams.append('keyword', params.keyword)
  if (params?.area) searchParams.append('area', params.area)
  if (params?.sellerNick) searchParams.append('seller_nick', params.sellerNick)
  return get(`${PREFIX}/items?${searchParams.toString()}`)
}
