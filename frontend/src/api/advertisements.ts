/**
 * 广告管理API
 * 
 * 功能：
 * 1. 广告管理（管理员）：获取所有广告、复核、删除
 * 2. 广告申请（所有用户）：新建、修改、删除自己的广告
 */
import { get, post, put, del } from '@/utils/request'
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/advertisements'

export type AdvertisementType = 'carousel' | 'text' | 'home_carousel' | 'home_text'
export type AdvertisementPlacement = 'dashboard' | 'home'
export interface AdvertisementTypeOption {
  value: AdvertisementType
  label: string
  price_key: string
}

export interface Advertisement {
  id: number
  user_id: number
  title: string
  content: string | null
  link: string | null
  expire_date: string | null
  image_url: string | null
  ad_type: AdvertisementType
  ad_type_label?: string
  months: number | null
  total_amount: string | null
  status: 'unpaid' | 'pending' | 'approved'
  /** 已生成支付订单或已复核的申请不可编辑。 */
  can_edit?: boolean
  created_at: string | null
  updated_at: string | null
  /** 广告来源：local-本站，remote-官方远程 */
  source?: 'local' | 'remote'
}

export interface AdListResponse {
  items: Advertisement[]
  total: number
  page: number
  page_size: number
}

export interface PublicAdsResponse {
  carousel: Advertisement[]
  text: Advertisement[]
}

// ==================== 公开接口（首页与仪表盘展示） ====================

/** 获取已复核的广告（公开接口） */
export const getPublicAds = async (placement: AdvertisementPlacement = 'dashboard'): Promise<ApiResponse & { data?: PublicAdsResponse }> => {
  return get(`${PREFIX}/public`, { params: { placement } })
}

/** 从后端数据字典读取类型中文名称和费用设置键。 */
export const getAdvertisementTypes = (): Promise<ApiResponse<AdvertisementTypeOption[]>> => get(`${PREFIX}/types`)

// ==================== 广告管理（管理员） ====================

/** 获取所有广告列表（管理员） */
export const getAllAds = async (params?: {
  page?: number
  page_size?: number
  status?: string
  ad_type?: string
}): Promise<ApiResponse & { data?: AdListResponse }> => {
  const query = new URLSearchParams()
  if (params?.page) query.append('page', String(params.page))
  if (params?.page_size) query.append('page_size', String(params.page_size))
  if (params?.status) query.append('status', params.status)
  if (params?.ad_type) query.append('ad_type', params.ad_type)
  return get(`${PREFIX}/admin?${query.toString()}`)
}

/** 复核广告（管理员） */
export const approveAd = async (id: number): Promise<ApiResponse> => {
  return put(`${PREFIX}/admin/${id}/approve`)
}

/** 取消复核（管理员） */
export const rejectAd = async (id: number): Promise<ApiResponse> => {
  return put(`${PREFIX}/admin/${id}/reject`)
}

/** 删除广告（管理员） */
export const deleteAdAdmin = async (id: number): Promise<ApiResponse> => {
  return del(`${PREFIX}/admin/${id}`)
}

/** 修改广告（管理员） */
export const updateAdAdmin = async (id: number, data: {
  title: string
  ad_type: string
  content?: string
  link?: string
  expire_date?: string
  image_url?: string
  status?: string
}): Promise<ApiResponse> => {
  const query = new URLSearchParams()
  query.append('title', data.title)
  query.append('ad_type', data.ad_type)
  if (data.content) query.append('content', data.content)
  if (data.link) query.append('link', data.link)
  if (data.expire_date) query.append('expire_date', data.expire_date)
  if (data.image_url) query.append('image_url', data.image_url)
  if (data.status) query.append('status', data.status)
  return put(`${PREFIX}/admin/${id}?${query.toString()}`)
}

// ==================== 广告申请（所有用户） ====================

/** 获取我的广告列表 */
export const getMyAds = async (params?: {
  page?: number
  page_size?: number
}): Promise<ApiResponse & { data?: AdListResponse }> => {
  const query = new URLSearchParams()
  if (params?.page) query.append('page', String(params.page))
  if (params?.page_size) query.append('page_size', String(params.page_size))
  return get(`${PREFIX}?${query.toString()}`)
}

/** 获取各广告类型的单月价格 */
export const getAdPrices = async (): Promise<ApiResponse & { data?: Record<string, string> }> => {
  return get(`${PREFIX}/prices`)
}

/** 新建广告申请 */
export const createAd = async (data: {
  title: string
  ad_type: string
  months: number
  content?: string
  link?: string
  image_url?: string
}): Promise<ApiResponse> => {
  const query = new URLSearchParams()
  query.append('title', data.title)
  query.append('ad_type', data.ad_type)
  query.append('months', String(data.months))
  if (data.content) query.append('content', data.content)
  if (data.link) query.append('link', data.link)
  if (data.image_url) query.append('image_url', data.image_url)
  return post(`${PREFIX}?${query.toString()}`)
}

/** 修改我的广告 */
export const updateMyAd = async (id: number, data: {
  title: string
  ad_type: string
  months: number
  content?: string
  link?: string
  image_url?: string
}): Promise<ApiResponse> => {
  const query = new URLSearchParams()
  query.append('title', data.title)
  query.append('ad_type', data.ad_type)
  query.append('months', String(data.months))
  if (data.content) query.append('content', data.content)
  if (data.link) query.append('link', data.link)
  if (data.image_url) query.append('image_url', data.image_url)
  return put(`${PREFIX}/${id}?${query.toString()}`)
}

/** 删除我的广告 */
export const deleteMyAd = async (id: number): Promise<ApiResponse> => {
  return del(`${PREFIX}/${id}`)
}

/** 创建广告付款订单 */
export const createAdPayment = async (adId: number): Promise<ApiResponse & { data?: { order_no: string; amount: string; qr_code: string; ad_id: number } }> => {
  return post(`${PREFIX}/${adId}/pay`)
}

/** 轮询广告付款状态 */
export const checkAdPaymentStatus = async (adId: number, orderNo: string): Promise<ApiResponse & { data?: { status: string; paid?: boolean } }> => {
  return post(`${PREFIX}/${adId}/pay/notify?order_no=${encodeURIComponent(orderNo)}`)
}
