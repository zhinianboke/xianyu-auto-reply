/**
 * 商品发布随机地址池 API
 *
 * 功能：
 * 1. 查询随机地址池分页列表
 * 2. 查询可选账号列表
 * 3. 管理员新增、编辑、启停随机地址
 */
import { get, post, put } from '@/utils/request'
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/product-publish/addresses'

export type PublishAddressSource = 'material' | 'account_pool' | 'global_pool'
export type PublishAddressType = 'global' | 'account'

export interface PublishAddress {
  id: number
  address: string
  name: string
  search_keyword: string
  expected_text?: string | null
  account_id?: string | null
  weight: number
  sort_order: number
  is_enabled: boolean
  use_count: number
  last_used_at?: string | null
  created_by?: number | null
  remark?: string | null
  address_type: PublishAddressType
  created_at?: string | null
  updated_at?: string | null
}

export interface PublishAddressAccountOption {
  account_id: string
  label: string
  owner_id?: number
}

export interface PublishAddressListData {
  list: PublishAddress[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface AmapInputTip {
  id: string
  name: string
  district: string
  adcode: string
  location: string
  address: string
  typecode: string
  city: string
  search_keyword: string
  expected_text: string
}

export interface AmapInputTipsData {
  tips: AmapInputTip[]
  count: number
  keywords: string
}

export interface PublishAddressSaveParams {
  address: string
}

export interface PublishAddressBatchDeleteResult {
  success_count: number
  total_count: number
}

export const getPublishAddresses = (
  page = 1,
  pageSize = 20,
  params?: {
    keyword?: string
    accountId?: string
    isEnabled?: boolean
  }
): Promise<ApiResponse<PublishAddressListData>> => {
  const searchParams = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (params?.keyword) searchParams.append('keyword', params.keyword)
  if (params?.accountId) searchParams.append('account_id', params.accountId)
  if (params?.isEnabled !== undefined) searchParams.append('is_enabled', String(params.isEnabled))
  return get(`${PREFIX}?${searchParams.toString()}`)
}

export const getPublishAddressAccountOptions = async (): Promise<ApiResponse<{ list: PublishAddressAccountOption[] }>> => {
  return get(`${PREFIX}/account-options`)
}

export const searchAmapInputTips = async (
  keywords: string,
  city = '全国'
): Promise<ApiResponse<AmapInputTipsData>> => {
  const params = new URLSearchParams({ keywords, city })
  return get(`${PREFIX}/input-tips?${params.toString()}`)
}

export const createPublishAddress = async (params: PublishAddressSaveParams): Promise<ApiResponse<{ address: PublishAddress }>> => {
  return post(`${PREFIX}`, params)
}

export const updatePublishAddress = async (
  addressId: number,
  params: Partial<PublishAddressSaveParams>
): Promise<ApiResponse<{ address: PublishAddress }>> => {
  return put(`${PREFIX}/${addressId}`, params)
}

export const batchDeletePublishAddresses = async (
  addressIds: number[]
): Promise<ApiResponse<PublishAddressBatchDeleteResult>> => {
  return post(`${PREFIX}/batch-delete`, { ids: addressIds })
}

export const updatePublishAddressStatus = async (
  addressId: number,
  isEnabled: boolean
): Promise<ApiResponse<{ address: PublishAddress }>> => {
  return put(`${PREFIX}/${addressId}/status`, { is_enabled: isEnabled })
}
