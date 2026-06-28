/**
 * 弹窗公告API
 *
 * 功能：
 * 1. 获取启用中的弹窗公告（登录后弹窗展示）
 * 2. 弹窗公告管理（管理员）：列表、新增、修改、启停、删除
 */
import { get, post, put, del } from '@/utils/request'
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/popup-announcements'

export interface PopupAnnouncement {
  id: number
  title: string
  content: string
  link: string | null
  is_enabled: boolean
  created_at: string
  updated_at: string
  /** 弹窗公告来源：local-本站，remote-官方远程 */
  source?: 'local' | 'remote'
}

export interface PopupAnnouncementListResponse {
  items: PopupAnnouncement[]
  total: number
  page: number
  page_size: number
}

/** 获取启用中的弹窗公告（登录后弹窗展示） */
export const getPublicPopupAnnouncements = async (): Promise<ApiResponse & { data?: { items: PopupAnnouncement[] } }> => {
  return get(`${PREFIX}/public`)
}

/** 获取弹窗公告列表（管理员） */
export const getPopupAnnouncements = async (params?: {
  page?: number
  page_size?: number
}): Promise<ApiResponse & { data?: PopupAnnouncementListResponse }> => {
  const query = new URLSearchParams()
  if (params?.page) query.append('page', String(params.page))
  if (params?.page_size) query.append('page_size', String(params.page_size))
  return get(`${PREFIX}?${query.toString()}`)
}

/** 新增弹窗公告 */
export const createPopupAnnouncement = async (data: {
  title: string
  content: string
  link?: string
  is_enabled: boolean
}): Promise<ApiResponse> => {
  return post(PREFIX, data)
}

/** 修改弹窗公告 */
export const updatePopupAnnouncement = async (
  id: number,
  data: { title: string; content: string; link?: string; is_enabled: boolean }
): Promise<ApiResponse> => {
  return put(`${PREFIX}/${id}`, data)
}

/** 启用/停用弹窗公告 */
export const togglePopupAnnouncement = async (id: number): Promise<ApiResponse & { data?: { is_enabled: boolean } }> => {
  return put(`${PREFIX}/${id}/toggle`)
}

/** 删除弹窗公告 */
export const deletePopupAnnouncement = async (id: number): Promise<ApiResponse> => {
  return del(`${PREFIX}/${id}`)
}
