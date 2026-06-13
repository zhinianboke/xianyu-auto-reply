/**
 * 分销卡券（对接上游卡券系统）API
 *
 * 说明：
 * - API 密钥由后台从系统设置（分销设置-对接卡密秘钥）统一读取，前端无需传入
 * - 所有数据均通过后台代理调用上游卡券系统实时获取
 */
import { get, post } from '@/utils/request'

const CARD_DOCK_PREFIX = '/api/v1/card-dock'

// 上游统一响应结构
export interface CardDockResponse<T = unknown> {
  success: boolean
  code: number
  message?: string
  data?: T
}

// 卡券商
export interface CardSource {
  source_code: string
  source_name: string
}

// 商品规格
export interface CardSub {
  id: number
  name: string
  docking_price?: string | number
  price?: string | number
}

// 商品
export interface CardGoods {
  id: number
  picture?: string
  name: string
  description?: string
  docking_price?: string | number
  price?: string | number
  sales_volume?: number
  type_name?: string
  subs?: CardSub[]
}

// 商品列表数据
export interface CardGoodsListData {
  data: CardGoods[]
  total: number | string
  current_page: number | string
}

// 商品详情
export interface CardGoodsDetail {
  picture?: string
  name?: string
  description?: string
  detail?: string
  usage_instructions?: string
  docking_price?: string | number
  price?: string | number
  type_name?: string
  require_login?: boolean
}

// 规格库存项
export interface CardStockSub {
  sub_id: number
  sub_name: string
  docking_price?: string | number
  price?: string | number
  stock?: number | string
}

// 库存数据
export interface CardStockData {
  subs: CardStockSub[]
}

// 提货结果
export interface CardPurchaseResult {
  order_sn?: string
  status_text?: string
  cards?: string
}

// 获取卡券商下拉列表
export const getCardSources = (): Promise<CardDockResponse<CardSource[]>> => {
  return get(`${CARD_DOCK_PREFIX}/sources`)
}

// 获取卡券商品列表（后端分页）
export const getCardGoods = (
  sourceCode: string,
  page: number = 1,
  perPage: number = 20,
  search: string = '',
): Promise<CardDockResponse<CardGoodsListData>> => {
  return get(`${CARD_DOCK_PREFIX}/goods`, {
    params: { source_code: sourceCode, page, per_page: perPage, search: search || undefined },
  })
}

// 获取商品详情
export const getCardGoodsDetail = (
  sourceCode: string,
  goodsId: number,
): Promise<CardDockResponse<CardGoodsDetail>> => {
  return get(`${CARD_DOCK_PREFIX}/goods/${goodsId}`, {
    params: { source_code: sourceCode },
  })
}

// 获取商品规格库存
export const getCardGoodsStock = (
  sourceCode: string,
  goodsId: number,
): Promise<CardDockResponse<CardStockData>> => {
  return get(`${CARD_DOCK_PREFIX}/goods/${goodsId}/stock`, {
    params: { source_code: sourceCode },
  })
}

// 提货
export const purchaseCard = (
  sourceCode: string,
  goodsId: number,
  subId: number,
  quantity: number,
): Promise<CardDockResponse<CardPurchaseResult>> => {
  return post(`${CARD_DOCK_PREFIX}/purchase`, {
    source_code: sourceCode,
    goods_id: goodsId,
    sub_id: subId,
    quantity,
  })
}

// 获取可直接 GET 调用的提货地址（含 api_key），用于「复制提货api」
export const getCardPurchaseUrl = (
  sourceCode: string,
  goodsId: number,
  subId: number,
  quantity: number = 1,
): Promise<CardDockResponse<{ url: string }>> => {
  return get(`${CARD_DOCK_PREFIX}/purchase-url`, {
    params: { source_code: sourceCode, goods_id: goodsId, sub_id: subId, quantity },
  })
}
