/**
 * 个人发布地址库 API
 *
 * 功能：
 * 1. 查询个人地址库分页列表
 * 2. 新建、修改、批量删除个人地址（仅本人）
 * 3. 个人地址库 Excel 导入、导出
 */
import { get, post, put } from '@/utils/request'
import type { ApiResponse } from '@/types'

const PREFIX = '/api/v1/product-publish/personal-addresses'

export interface PersonalAddress {
  id: number
  address: string
  use_count: number
  last_used_at?: string | null
  created_at?: string | null
  updated_at?: string | null
}

export interface PersonalAddressListData {
  list: PersonalAddress[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface PersonalAddressBatchDeleteResult {
  success_count: number
  total_count: number
}

export interface PersonalAddressImportResult {
  created: number
  updated: number
}

export const getPersonalAddresses = (
  page = 1,
  pageSize = 20,
  params?: { keyword?: string }
): Promise<ApiResponse<PersonalAddressListData>> => {
  const searchParams = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  })
  if (params?.keyword) searchParams.append('keyword', params.keyword)
  return get(`${PREFIX}?${searchParams.toString()}`)
}

export const createPersonalAddress = (
  address: string
): Promise<ApiResponse<{ address: PersonalAddress }>> => {
  return post(`${PREFIX}`, { address })
}

export const updatePersonalAddress = (
  addressId: number,
  address: string
): Promise<ApiResponse<{ address: PersonalAddress }>> => {
  return put(`${PREFIX}/${addressId}`, { address })
}

export const batchDeletePersonalAddresses = (
  addressIds: number[]
): Promise<ApiResponse<PersonalAddressBatchDeleteResult>> => {
  return post(`${PREFIX}/batch-delete`, { ids: addressIds })
}

export const exportPersonalAddresses = async (): Promise<Blob> => {
  const token = localStorage.getItem('auth_token')
  const response = await fetch(`${PREFIX}/export`, {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!response.ok) throw new Error('导出失败')
  return response.blob()
}

export const importPersonalAddresses = (
  file: File
): Promise<ApiResponse<PersonalAddressImportResult>> => {
  const formData = new FormData()
  formData.append('file', file)
  return post(`${PREFIX}/import`, formData)
}
