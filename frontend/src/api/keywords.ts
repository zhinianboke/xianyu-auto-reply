import { get, post, put } from '@/utils/request'
import type { Keyword, ApiResponse } from '@/types'

// 获取关键词列表（包含 item_id 和 type）
export const getKeywords = (cookieId: string): Promise<Keyword[]> => {
  return get(`/keywords-with-item-id/${cookieId}`)
}

// 保存关键词列表（替换整个列表）
// 后端接口: POST /keywords-with-item-id/{cid}
// 请求体: { keywords: [{ keyword, reply, item_id }, ...] }
export const saveKeywords = (cookieId: string, keywords: Keyword[]): Promise<ApiResponse> => {
  // 只发送文本类型的关键词，图片类型通过单独接口处理
  const textKeywords = keywords
    .filter(k => k.type !== 'image')
    .map(k => ({
      keyword: k.keyword,
      reply: k.reply || '',
      item_id: k.item_id || ''
    }))
  return post(`/keywords-with-item-id/${cookieId}`, { keywords: textKeywords })
}

// 添加关键词（先获取列表，添加后保存）
export const addKeyword = async (cookieId: string, data: Partial<Keyword>): Promise<ApiResponse> => {
  const keywords = await getKeywords(cookieId)
  // 检查是否已存在
  const exists = keywords.some(k => 
    k.keyword === data.keyword && 
    (k.item_id || '') === (data.item_id || '')
  )
  if (exists) {
    return { success: false, message: '该关键词已存在' }
  }
  keywords.push({
    keyword: data.keyword || '',
    reply: data.reply || '',
    item_id: data.item_id || '',
    type: 'text'
  } as Keyword)
  return saveKeywords(cookieId, keywords)
}

// 更新关键词
export const updateKeyword = async (
  cookieId: string, 
  oldKeyword: string, 
  oldItemId: string,
  data: Partial<Keyword>
): Promise<ApiResponse> => {
  const keywords = await getKeywords(cookieId)
  const index = keywords.findIndex(k => 
    k.keyword === oldKeyword && 
    (k.item_id || '') === (oldItemId || '')
  )
  if (index === -1) {
    return { success: false, message: '关键词不存在' }
  }
  // 检查新关键词是否与其他关键词重复
  if (data.keyword !== oldKeyword || data.item_id !== oldItemId) {
    const duplicate = keywords.some((k, i) => 
      i !== index && 
      k.keyword === data.keyword && 
      (k.item_id || '') === (data.item_id || '')
    )
    if (duplicate) {
      return { success: false, message: '该关键词已存在' }
    }
  }
  keywords[index] = { ...keywords[index], ...data }
  return saveKeywords(cookieId, keywords)
}

// 删除关键词
export const deleteKeyword = async (
  cookieId: string, 
  keyword: string, 
  itemId: string
): Promise<ApiResponse> => {
  const keywords = await getKeywords(cookieId)
  const filtered = keywords.filter(k => 
    !(k.keyword === keyword && (k.item_id || '') === (itemId || ''))
  )
  if (filtered.length === keywords.length) {
    return { success: false, message: '关键词不存在' }
  }
  return saveKeywords(cookieId, filtered)
}

// 批量添加关键词
export const batchAddKeywords = (cookieId: string, keywords: Partial<Keyword>[]): Promise<ApiResponse> => {
  return post(`/keywords/${cookieId}/batch`, { keywords })
}

// 批量删除关键词
export const batchDeleteKeywords = (cookieId: string, keywordIds: string[]): Promise<ApiResponse> => {
  return post(`/keywords/${cookieId}/batch-delete`, { keyword_ids: keywordIds })
}

// 获取默认回复
export const getDefaultReply = (cookieId: string): Promise<{ default_reply: string }> => {
  return get(`/default-reply/${cookieId}`)
}

// 更新默认回复
export const updateDefaultReply = (cookieId: string, defaultReply: string): Promise<ApiResponse> => {
  return put(`/default-reply/${cookieId}`, { default_reply: defaultReply })
}

// 导出关键词（Excel/模板），返回 Blob 供前端触发下载
export const exportKeywords = (cookieId: string): Promise<Blob> => {
  return get<Blob>(`/keywords-export/${cookieId}`, { responseType: 'blob' })
}

// 导入关键词（Excel），上传文件并返回导入结果
export const importKeywords = (
  cookieId: string,
  file: File
): Promise<ApiResponse<{ added: number; updated: number }>> => {
  const formData = new FormData()
  formData.append('file', file)
  return post<ApiResponse<{ added: number; updated: number }>>(`/keywords-import/${cookieId}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 添加图片关键词
export const addImageKeyword = (
  cookieId: string,
  keyword: string,
  image: File,
  itemId?: string
): Promise<ApiResponse<{ keyword: string; image_url: string; item_id?: string }>> => {
  const formData = new FormData()
  formData.append('keyword', keyword)
  formData.append('image', image)
  if (itemId) {
    formData.append('item_id', itemId)
  }
  return post(`/keywords/${cookieId}/image`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}
