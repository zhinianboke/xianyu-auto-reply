import { get, post, put, del } from '@/utils/request'
import type { Item, ItemReply, ApiResponse } from '@/types'

// 获取商品列表
export const getItems = async (cookieId?: string): Promise<{ success: boolean; data: Item[] }> => {
  const url = cookieId ? `/items/cookie/${cookieId}` : '/items'
  const result = await get<{ items?: Item[] } | Item[]>(url)
  // 后端返回 { items: [...] } 或直接返回数组
  const items = Array.isArray(result) ? result : (result.items || [])
  return { success: true, data: items }
}

// 删除商品
export const deleteItem = (cookieId: string, itemId: string): Promise<ApiResponse> => {
  return del(`/items/${cookieId}/${itemId}`)
}

// 批量删除商品
export const batchDeleteItems = (ids: { cookie_id: string; item_id: string }[]): Promise<ApiResponse> => {
  return del('/items/batch', { data: { items: ids } })
}

// 从账号获取商品（分页）
export const fetchItemsFromAccount = (cookieId: string, page?: number): Promise<ApiResponse> => {
  return post('/items/get-by-page', { cookie_id: cookieId, page: page || 1 })
}

// 获取账号所有页商品
export const fetchAllItemsFromAccount = (cookieId: string): Promise<ApiResponse> => {
  return post('/items/get-all-from-account', { cookie_id: cookieId })
}

// 更新商品
export const updateItem = (cookieId: string, itemId: string, data: Partial<Item>): Promise<ApiResponse> => {
  return put(`/items/${cookieId}/${itemId}`, data)
}

// 获取商品回复列表
export const getItemReplies = async (cookieId?: string): Promise<{ success: boolean; data: ItemReply[] }> => {
  const params = cookieId ? `/cookie/${cookieId}` : ''
  const result = await get<{ items?: ItemReply[] } | ItemReply[]>(`/itemReplays${params}`)
  // 后端返回 { items: [...] } 格式
  const items = Array.isArray(result) ? result : (result.items || [])
  return { success: true, data: items }
}

// 添加商品回复
export const addItemReply = (cookieId: string, itemId: string, data: Partial<ItemReply>): Promise<ApiResponse> => {
  return put(`/item-reply/${cookieId}/${itemId}`, data)
}

// 更新商品回复
export const updateItemReply = (cookieId: string, itemId: string, data: Partial<ItemReply>): Promise<ApiResponse> => {
  return put(`/item-reply/${cookieId}/${itemId}`, data)
}

// 删除商品回复
export const deleteItemReply = (cookieId: string, itemId: string): Promise<ApiResponse> => {
  return del(`/item-reply/${cookieId}/${itemId}`)
}

// 批量删除商品回复
export const batchDeleteItemReplies = (items: { cookie_id: string; item_id: string }[]): Promise<ApiResponse> => {
  return del('/item-reply/batch', { data: { items } })
}
