import { get, post, del as httpDel, patch } from '@/utils/request'

const PREFIX = '/api/v1/blacklist'

// ==================== 类型定义 ====================

export interface PersonalBlacklistItem {
  id: number
  owner_id: number
  account_id: string | null
  buyer_id: string
  buyer_nick: string | null
  item_id: string | null
  reason: string | null
  is_enabled: boolean
  created_at: string | null
  updated_at: string | null
}

export interface PlatformBlacklistItem {
  id: number
  owner_id: number
  owner_username: string
  buyer_id: string
  buyer_nick: string | null
  created_at: string | null
  updated_at: string | null
}

export interface PersonalBlacklistListResponse {
  success: boolean
  data: PersonalBlacklistItem[]
  total: number
  page: number
  page_size: number
}

export interface PlatformBlacklistListResponse {
  success: boolean
  data: PlatformBlacklistItem[]
  total: number
  page: number
  page_size: number
}

export interface CreatePersonalBlacklistRequest {
  account_id?: string | null
  buyer_ids: string
  item_id?: string | null
  reason?: string | null
  is_enabled: boolean
}

// ==================== 个人黑名单 ====================

export const getPersonalBlacklist = (params: {
  buyer_id?: string
  buyer_nick?: string
  page?: number
  page_size?: number
}): Promise<PersonalBlacklistListResponse> => {
  const searchParams = new URLSearchParams()
  if (params.buyer_id) searchParams.append('buyer_id', params.buyer_id)
  if (params.buyer_nick) searchParams.append('buyer_nick', params.buyer_nick)
  searchParams.append('page', String(params.page || 1))
  searchParams.append('page_size', String(params.page_size || 20))
  return get(`${PREFIX}/personal?${searchParams.toString()}`)
}

export const createPersonalBlacklist = (data: CreatePersonalBlacklistRequest): Promise<{ success: boolean; message: string }> => {
  return post(`${PREFIX}/personal`, data)
}

export const deletePersonalBlacklist = (id: number): Promise<{ success: boolean; message: string }> => {
  return httpDel(`${PREFIX}/personal/${id}`)
}

export const batchDeletePersonalBlacklist = (ids: number[]): Promise<{ success: boolean; message: string }> => {
  return post(`${PREFIX}/personal/batch-delete`, { ids })
}

export const exportPersonalBlacklist = async (): Promise<Blob> => {
  const token = localStorage.getItem('auth_token')
  const response = await fetch(`${PREFIX}/personal/export`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error('导出失败')
  return response.blob()
}

export const importPersonalBlacklist = async (file: File): Promise<{ success: boolean; message: string }> => {
  const formData = new FormData()
  formData.append('file', file)
  return post(`${PREFIX}/personal/import`, formData)
}

export const togglePersonalBlacklist = (id: number, isEnabled: boolean): Promise<{ success: boolean; message: string }> => {
  return patch(`${PREFIX}/personal/${id}/toggle`, { is_enabled: isEnabled })
}

// ==================== 闲鱼黑名单 ====================

export const getPlatformBlacklist = (params: {
  page?: number
  page_size?: number
}): Promise<PlatformBlacklistListResponse> => {
  const searchParams = new URLSearchParams()
  searchParams.append('page', String(params.page || 1))
  searchParams.append('page_size', String(params.page_size || 20))
  return get(`${PREFIX}/platform?${searchParams.toString()}`)
}
