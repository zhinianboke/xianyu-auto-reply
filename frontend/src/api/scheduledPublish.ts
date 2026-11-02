/**
 * 商品定时发布规则 API。
 *
 * 提供规则保存、分页查询以及新建表单选项查询；规则由后端定时任务自动执行。
 */
import { get, post, put } from '@/utils/request'
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/product-publish/scheduled-rules'

export interface ScheduledPublishAccountOption {
  account_id: string
  display_name: string
  enabled: boolean
}

export interface ScheduledPublishMaterialOption {
  id: number
  title: string
  image_url?: string | null
}

export interface ScheduledPublishOptions {
  accounts: ScheduledPublishAccountOption[]
  materials: ScheduledPublishMaterialOption[]
}

export interface ScheduledPublishRule {
  id: number
  rule_name: string
  account_ids: string[]
  account_names: string[]
  material_ids: number[]
  material_titles: string[]
  trigger_start_time: string
  trigger_end_time: string
  interval_min_minutes: number
  interval_max_minutes: number
  is_enabled: boolean
  created_at?: string | null
  updated_at?: string | null
}

export interface ScheduledPublishRulePage {
  list: ScheduledPublishRule[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ScheduledPublishRuleCreateParams {
  rule_name: string
  account_ids: string[]
  material_ids: number[]
  trigger_start_time: string
  trigger_end_time: string
  interval_min_minutes: number
  interval_max_minutes: number
}

export interface ScheduledPublishRecord {
  id: number
  rule_id: number
  account_id: string
  account_name: string
  material_id: number | null
  material_title: string
  publish_result: string
  publish_result_text: string
  failure_reason?: string | null
  publish_date?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ScheduledPublishTriggerRecord {
  id: number
  rule_id: number
  account_id: string
  account_name: string
  schedule_date?: string | null
  next_trigger_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface ScheduledPublishPage<T> {
  list: T[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface ScheduledPublishTriggerDeleteResult {
  success_count: number
  total_count: number
}

/** 查询新建规则可选的账号和素材。 */
export const getScheduledPublishOptions = (): Promise<ApiResponse<ScheduledPublishOptions>> =>
  get(`${PREFIX}/options`)

/** 分页查询定时发布规则。 */
export const getScheduledPublishRules = (
  page = 1,
  pageSize = 20,
  keyword = '',
): Promise<ApiResponse<ScheduledPublishRulePage>> => {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (keyword.trim()) params.set('keyword', keyword.trim())
  return get(`${PREFIX}?${params.toString()}`)
}

/** 新建定时发布规则。 */
export const createScheduledPublishRule = (
  params: ScheduledPublishRuleCreateParams,
): Promise<ApiResponse<{ id: number }>> => post(PREFIX, params)

/** 修改定时发布规则。 */
export const updateScheduledPublishRule = (
  ruleId: number,
  params: ScheduledPublishRuleCreateParams,
): Promise<ApiResponse<{ id: number }>> => put(`${PREFIX}/${ruleId}`, params)

/** 分页查询指定规则的发布记录。 */
export const getScheduledPublishRecords = (
  ruleId: number,
  page = 1,
  pageSize = 20,
): Promise<ApiResponse<ScheduledPublishPage<ScheduledPublishRecord>>> =>
  get(`${PREFIX}/${ruleId}/publish-records?page=${page}&page_size=${pageSize}`)

/** 分页查询指定规则的触发记录。 */
export const getScheduledPublishTriggerRecords = (
  ruleId: number,
  page = 1,
  pageSize = 20,
): Promise<ApiResponse<ScheduledPublishPage<ScheduledPublishTriggerRecord>>> =>
  get(`${PREFIX}/${ruleId}/trigger-records?page=${page}&page_size=${pageSize}`)

/** 单条或批量软删除指定规则的触发记录。 */
export const deleteScheduledPublishTriggerRecords = (
  ruleId: number,
  ids: number[],
): Promise<ApiResponse<ScheduledPublishTriggerDeleteResult>> =>
  post(`${PREFIX}/${ruleId}/trigger-records/batch-delete`, { ids })
