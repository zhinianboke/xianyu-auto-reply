/**
 * 商品监控分类 API
 *
 * 功能：
 * 1. 查询分类列表（普通用户仅见自己的分类，管理员可见全部）
 * 2. 新建、修改、删除分类（名称全局唯一，仅创建人或管理员可改删）
 */
import { get, post, put, del } from '@/utils/request'
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/product-monitor/categories'

export interface ListingMonitorCategory {
  id: number
  owner_id?: number | null
  name: string
  is_deleted?: boolean
  created_at?: string | null
  updated_at?: string | null
}

export const getListingMonitorCategories = (): Promise<ApiResponse<ListingMonitorCategory[]>> => {
  return get(`${PREFIX}`)
}

export const createListingMonitorCategory = (
  name: string
): Promise<ApiResponse<ListingMonitorCategory>> => {
  return post(`${PREFIX}`, { name })
}

export const updateListingMonitorCategory = (
  id: number,
  name: string
): Promise<ApiResponse<ListingMonitorCategory>> => {
  return put(`${PREFIX}/${id}`, { name })
}

export const deleteListingMonitorCategory = (id: number): Promise<ApiResponse<null>> => {
  return del(`${PREFIX}/${id}`)
}
