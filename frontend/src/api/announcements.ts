/**
 * 公告管理API
 * 
 * 功能：
 * 1. 获取公告列表
 * 2. 新增公告（管理员）
 * 3. 修改公告（管理员）
 * 4. 删除公告（管理员）
 */
import { get, post, put, del } from '@/utils/request'
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/announcements'

export interface Announcement {
  id: number
  title: string
  content: string
  created_at: string
  updated_at: string
  /** 公告来源：local-本站，remote-官方远程 */
  source?: 'local' | 'remote'
}

export interface AnnouncementListResponse {
  items: Announcement[]
  total: number
  page: number
  page_size: number
}

/** 获取系统顶部公告（公开接口，本地 + 远程官方合并） */
export const getPublicAnnouncements = async (): Promise<ApiResponse & { data?: { items: Announcement[] } }> => {
  return get(`${PREFIX}/public`)
}

/** 获取公告列表 */
export const getAnnouncements = async (params?: {
  page?: number
  page_size?: number
}): Promise<ApiResponse & { data?: AnnouncementListResponse }> => {
  const query = new URLSearchParams()
  if (params?.page) query.append('page', String(params.page))
  if (params?.page_size) query.append('page_size', String(params.page_size))
  return get(`${PREFIX}?${query.toString()}`)
}

/** 新增公告 */
export const createAnnouncement = async (data: {
  title: string
  content: string
}): Promise<ApiResponse> => {
  return post(PREFIX, data)
}

/** 修改公告 */
export const updateAnnouncement = async (
  id: number,
  data: { title: string; content: string }
): Promise<ApiResponse> => {
  return put(`${PREFIX}/${id}`, data)
}

/** 删除公告 */
export const deleteAnnouncement = async (id: number): Promise<ApiResponse> => {
  return del(`${PREFIX}/${id}`)
}
