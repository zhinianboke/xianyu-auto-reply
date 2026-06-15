import { post } from '@/utils/request'

// API前缀
const SEARCH_PREFIX = '/api/v1/items'

// 搜索结果项类型
export interface SearchResultItem {
  item_id: string
  title: string
  price: string
  seller_name?: string
  item_url?: string
  main_image?: string
  publish_time?: string
  tags?: string[]
  area?: string
  want_count?: number
}

// 搜索商品
export const searchItems = async (
  keyword: string, 
  page: number = 1, 
  pageSize: number = 20,
  cookieId?: string
): Promise<{ success: boolean; data: SearchResultItem[]; total?: number; error?: string }> => {
  const result = await post<{ 
    success: boolean
    data?: SearchResultItem[]
    total?: number
    error?: string 
  }>(`${SEARCH_PREFIX}/search`, { keyword, page, page_size: pageSize, cookie_id: cookieId })
  return { 
    success: result.success, 
    data: result.data || [], 
    total: result.total,
    error: result.error
  }
}

export interface InteractionDraftOptions {
  cookie_id: string
  item: SearchResultItem
  word_count: number
  tone: 'friendly' | 'question' | 'concise'
  include_detail: boolean
}

export interface InteractionDraftResult {
  success: boolean
  draft: string
  usage?: {
    prompt_tokens?: number
    completion_tokens?: number
    total_tokens?: number
    estimated?: boolean
  }
  included_detail?: boolean
}

export const generateInteractionCommentDraft = (
  data: InteractionDraftOptions
): Promise<InteractionDraftResult> => {
  return post('/items/interaction-comment-draft', data)
}

export interface InteractionCommentOptions {
  cookie_id: string
  item: SearchResultItem
  comment: string
}

export interface InteractionCommentResult {
  success: boolean
  item_url?: string
}

export const publishInteractionComment = (
  data: InteractionCommentOptions
): Promise<InteractionCommentResult> => {
  return post('/items/interaction-comment', data)
}
