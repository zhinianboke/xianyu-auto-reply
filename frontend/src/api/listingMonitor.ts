/**
 * 商品上新监控任务 API
 *
 * 功能：
 * 1. 查询上新监控任务分页列表
 * 2. 新建、编辑、启停、批量删除监控任务
 */
import { del, get, post, put } from '@/utils/request'
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
  category_id?: number | null
  monitor_type: MonitorType
  keyword: string
  price_min?: number | null
  price_max?: number | null
  publish_days?: number | null
  interval_minutes: number
  collect_pages: number
  account_ids: string[]
  order_account_ids?: string[]
  dm_content?: string | null
  dm_batch_size?: number
  order_batch_size?: number
  direct_order?: boolean
  is_enabled: boolean
  last_run_at?: string | null
  remark?: string | null
  proxy_url?: string | null
  dm_sent_count?: number
  ordered_count?: number
  duplicate_count?: number
  owner_id?: number | null
  owner_username?: string | null
  created_at?: string | null
  updated_at?: string | null
}

// 商品监控总览统计
export interface ListingMonitorOverview {
  total_tasks: number
  enabled_tasks: number
  disabled_tasks: number
  today_run_total: number
  today_run_success: number
  today_run_partial: number
  today_run_failed: number
  today_collected: number
  today_new: number
  today_dm: number
  today_dm_failed: number
  today_ordered: number
  today_order_failed: number
  today_order_duplicate: number
  total_items: number
  total_dm: number
  total_ordered: number
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
  category_id: number
  keyword: string
  price_min?: number | null
  price_max?: number | null
  publish_days?: number | null
  interval_minutes: number
  collect_pages: number
  account_ids: string[]
  order_account_ids?: string[]
  dm_content?: string | null
  dm_batch_size?: number
  order_batch_size?: number
  direct_order?: boolean
  is_enabled?: boolean
  remark?: string | null
  proxy_url?: string | null
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
    categoryId?: number
  }
): Promise<ApiResponse<ListingMonitorTaskListData>> => {
  const searchParams = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (params?.keyword) searchParams.append('keyword', params.keyword)
  if (params?.isEnabled !== undefined) searchParams.append('is_enabled', String(params.isEnabled))
  if (params?.categoryId !== undefined) searchParams.append('category_id', String(params.categoryId))
  return get(`${PREFIX}?${searchParams.toString()}`)
}

// 查询商品监控总览统计
export const getListingMonitorOverview = (): Promise<ApiResponse<ListingMonitorOverview>> => {
  return get(`${PREFIX}/overview`)
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

// 批量修改监控任务的账号（采集账号 account_ids 或下单账号 order_account_ids）
export const batchUpdateListingMonitorAccounts = (
  taskIds: number[],
  field: 'account_ids' | 'order_account_ids',
  accountIds: string[]
): Promise<ApiResponse<ListingMonitorBatchDeleteResult>> => {
  return post(`${PREFIX}/batch-update-accounts`, { ids: taskIds, field, account_ids: accountIds })
}

// 批量修改监控任务的所属分类
export const batchUpdateListingMonitorCategory = (
  taskIds: number[],
  categoryId: number
): Promise<ApiResponse<ListingMonitorBatchDeleteResult>> => {
  return post(`${PREFIX}/batch-update-category`, { ids: taskIds, category_id: categoryId })
}

// 批量修改监控任务的私信内容
export const batchUpdateListingMonitorDmContent = (
  taskIds: number[],
  dmContent: string
): Promise<ApiResponse<ListingMonitorBatchDeleteResult>> => {
  return post(`${PREFIX}/batch-update-dm-content`, { ids: taskIds, dm_content: dmContent })
}

// 监控日志账号Cookie复制项
export interface ListingMonitorLogCookieItem {
  account_id: string
  cookies: string
  secret_key: string
}

// 复制选中监控日志涉及的账号Cookie（去重，返回账号ID/Cookie/分销秘钥）
export const copyListingMonitorLogCookies = (
  logIds: number[]
): Promise<ApiResponse<{ list: ListingMonitorLogCookieItem[] }>> => {
  return post(`${PREFIX}/logs/copy-cookies`, { ids: logIds })
}

// 手动执行单个监控任务采集（立即执行一次）
export const runListingMonitorTask = (
  taskId: number
): Promise<ApiResponse<null>> => {
  return post(`${PREFIX}/${taskId}/run`, {})
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
  trigger_type?: string | null
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

// 清空监控日志（只清空10天前的数据，保留最近10天）
export const clearListingMonitorLogs = (): Promise<ApiResponse<{ deleted_count: number }>> => {
  return del(`${PREFIX}/logs/clear`)
}

// ==================== 采集商品 ====================

export interface ListingMonitorItem {
  id: number
  monitor_task_id: number
  monitor_task_keyword?: string | null
  item_id: string
  title?: string | null
  price?: string | null
  area?: string | null
  pic_url?: string | null
  seller_id?: string | null
  seller_user_id?: string | null
  seller_nick?: string | null
  seller_avatar?: string | null
  want_count?: string | null
  tags?: string | null
  publish_time?: string | null
  target_url?: string | null
  has_detail?: boolean
  seller_fill_status?: string | null
  seller_fill_fail_reason?: string | null
  is_dm_sent: boolean
  dm_account_id?: string | null
  dm_chat_id?: string | null
  dm_status?: string | null
  dm_fail_reason?: string | null
  dm_attempts?: number
  is_ordered: boolean
  order_id?: string | null
  order_account_id?: string | null
  order_status?: string | null
  order_fail_reason?: string | null
  order_attempts?: number
  ordered_at?: string | null
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
  params?: {
    monitorTaskId?: number
    keyword?: string
    area?: string
    sellerNick?: string
    itemId?: string
    isDmSent?: boolean
    isOrdered?: boolean
    sellerFill?: string
    hasDetail?: boolean
    dmState?: string
    orderState?: string
    createdStart?: string
    createdEnd?: string
  }
): Promise<ApiResponse<ListingMonitorItemListData>> => {
  const searchParams = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
  if (params?.monitorTaskId) searchParams.append('monitor_task_id', String(params.monitorTaskId))
  if (params?.keyword) searchParams.append('keyword', params.keyword)
  if (params?.area) searchParams.append('area', params.area)
  if (params?.sellerNick) searchParams.append('seller_nick', params.sellerNick)
  if (params?.itemId) searchParams.append('item_id', params.itemId)
  if (params?.isDmSent !== undefined) searchParams.append('is_dm_sent', String(params.isDmSent))
  if (params?.isOrdered !== undefined) searchParams.append('is_ordered', String(params.isOrdered))
  if (params?.sellerFill) searchParams.append('seller_fill', params.sellerFill)
  if (params?.hasDetail !== undefined) searchParams.append('has_detail', String(params.hasDetail))
  if (params?.dmState) searchParams.append('dm_state', params.dmState)
  if (params?.orderState) searchParams.append('order_state', params.orderState)
  if (params?.createdStart) searchParams.append('created_start', params.createdStart)
  if (params?.createdEnd) searchParams.append('created_end', params.createdEnd)
  return get(`${PREFIX}/items?${searchParams.toString()}`)
}

// 批量将选中的"私信失败"采集商品重置为"未私信"，等待定时任务重试
export const resetListingMonitorItemsDm = (
  itemIds: number[]
): Promise<ApiResponse<ListingMonitorBatchDeleteResult>> => {
  return post(`${PREFIX}/items/reset-dm`, { ids: itemIds })
}

// 采集商品完整详情（含数据库存储的原始详情/搜索数据）
export interface ListingMonitorItemDetail extends ListingMonitorItem {
  detail_json?: unknown
  raw_json?: unknown
}

export const getListingMonitorItemDetail = (
  itemPk: number
): Promise<ApiResponse<{ item: ListingMonitorItemDetail }>> => {
  return get(`${PREFIX}/items/${itemPk}`)
}
