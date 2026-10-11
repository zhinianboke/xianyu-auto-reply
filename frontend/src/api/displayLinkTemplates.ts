/**
 * 通用展示入口模板 API（用户级，默认条目在提货页读取时自动合并）
 * 后端前缀: /api/v1/display-link-templates
 */
import { get, post, put, del } from '@/utils/request'
import type { ApiResponse } from '@/types'
import type { DisplayLink } from '@/api/itemQuery'

const PREFIX = '/api/v1/display-link-templates'

/** 模板 = 展示入口条目 + 主键 + 默认开关（联合类型用交叉类型而非 extends） */
export type DisplayLinkTemplate = DisplayLink & { id: number; is_default: boolean }

export interface DisplayLinkTemplatePayload {
  name?: string
  type?: string
  url?: string
  note?: string
  title?: string
  content?: string
  is_default?: boolean
}

export const getDisplayLinkTemplates = async (): Promise<DisplayLinkTemplate[]> => {
  const resp = await get<ApiResponse<{ templates: DisplayLinkTemplate[] }>>(PREFIX)
  if (!resp.success || !resp.data) throw new Error(resp.message || '获取通用展示入口失败')
  // 后端异常返回 data:{} 时兜底空数组，避免调用方 map 崩溃
  return Array.isArray(resp.data.templates) ? resp.data.templates : []
}

export const createDisplayLinkTemplate = (payload: DisplayLinkTemplatePayload) =>
  post<ApiResponse<DisplayLinkTemplate>>(PREFIX, payload)

export const updateDisplayLinkTemplate = (id: number, payload: DisplayLinkTemplatePayload) =>
  put<ApiResponse<DisplayLinkTemplate>>(`${PREFIX}/${id}`, payload)

export const deleteDisplayLinkTemplate = (id: number) =>
  del<ApiResponse>(`${PREFIX}/${id}`)

/** 上传模板图片，返回 image_url */
export const uploadDisplayLinkTemplateImage = async (file: File): Promise<string> => {
  const token = localStorage.getItem('auth_token')
  const formData = new FormData()
  formData.append('image', file)
  const resp = await fetch(`${PREFIX}/upload-image`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  })
  const body = await resp.json()
  if (!resp.ok || body?.success === false) {
    throw new Error(body?.message || body?.detail || '图片上传失败')
  }
  const url = body?.image_url ?? body?.data?.image_url
  if (!url) throw new Error('图片上传失败：响应缺少 image_url')
  return url
}
