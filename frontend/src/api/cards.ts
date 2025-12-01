import { get, post, put, del } from '@/utils/request'
import type { ApiResponse } from '@/types'

// 卡券类型定义 - 与后端 AIReplySettings 模型对应
export interface CardData {
  id?: number
  name: string
  type: 'api' | 'text' | 'data' | 'image'
  description?: string
  enabled?: boolean
  delay_seconds?: number
  is_multi_spec?: boolean
  spec_name?: string
  spec_value?: string
  // 根据类型的不同配置
  api_config?: {
    url: string
    method: string
    timeout?: number
    headers?: string
    params?: string
  }
  text_content?: string
  data_content?: string
  image_url?: string
  // 后端返回的额外字段
  created_at?: string
  updated_at?: string
  user_id?: number
}

// 获取卡券列表
export const getCards = async (_accountId?: string): Promise<{ success: boolean; data?: CardData[] }> => {
  const result = await get<CardData[] | { cards?: CardData[] }>('/cards')
  // 后端可能返回数组或 { cards: [...] } 格式
  const data = Array.isArray(result) ? result : (result.cards || [])
  return { success: true, data }
}

// 获取单个卡券
export const getCard = (cardId: string): Promise<CardData> => {
  return get(`/cards/${cardId}`)
}

// 创建卡券 - 匹配后端接口
export const createCard = (data: Omit<CardData, 'id' | 'created_at' | 'updated_at' | 'user_id'>): Promise<{ id: number; message: string }> => {
  return post('/cards', data)
}

// 更新卡券
export const updateCard = (cardId: string, data: Partial<CardData>): Promise<ApiResponse> => {
  return put(`/cards/${cardId}`, data)
}

// 删除卡券
export const deleteCard = (cardId: string): Promise<ApiResponse> => {
  return del(`/cards/${cardId}`)
}

// 批量删除卡券
export const batchDeleteCards = (cardIds: number[]): Promise<ApiResponse> => {
  return post('/cards/batch-delete', { ids: cardIds })
}

// 兼容旧接口 - 批量添加文本类型卡券
export const addCard = async (
  _accountId: string, 
  data: { item_id: string; cards: string[] }
): Promise<ApiResponse> => {
  // 为每个卡密创建一个文本类型卡券
  const results = await Promise.all(
    data.cards.map((cardContent, index) => 
      createCard({
        name: `商品${data.item_id}-卡密${index + 1}`,
        type: 'text',
        text_content: cardContent,
        description: `商品ID: ${data.item_id}`,
        enabled: true,
        delay_seconds: 0,
      })
    )
  )
  return { success: true, message: `成功添加 ${results.length} 张卡券` }
}

// 导入卡券（从文本）
export const importCards = (accountId: string, data: { item_id: string; content: string }): Promise<ApiResponse> => {
  const cards = data.content.split('\n').map(s => s.trim()).filter(Boolean)
  return addCard(accountId, { item_id: data.item_id, cards })
}
