/**
 * 商品通用查询 - API 封装
 *
 * 说明：
 * - 管理接口（需登录）走 axios 封装，参照同目录 items.ts 的 get/put 模式。
 * - 公开接口（买家查询页，无需登录）使用原生 fetch，绕过 axios 的 token / 401 拦截
 *   （与提货页 agreePickup.ts 一致：买家打开页面时没有登录态，axios 拦截器会误触发跳转登录）。
 * - 后端统一返回 { success, message, data }，一律 HTTP 200，业务错误通过 success 传递。
 * - Cookie 只在请求中传给后端代理执行，后端不回传，前端不做任何持久化。
 * - 可用变量（服务端执行时替换）：{cookie} {account} {api_key} {line}
 */
import { get, put } from '@/utils/request'
import type { ApiResponse } from '@/types'

// ==================== 类型（与全局接口契约一致） ====================

/** 查询按钮配置（存商品 metadata_json.query_buttons 数组） */
export interface QueryButton {
  /** 按钮名称，如「查余额」 */
  name: string
  /** 请求方法，默认 GET；body 仅 POST 用 */
  method: 'GET' | 'POST'
  /** 请求地址，必须 http(s)，支持变量 */
  url: string
  /** 请求头（值支持变量） */
  headers: Record<string, string>
  /** POST 请求体模板（支持变量），GET 为 null */
  body: string | null
  /** 成功判定路径（JSON 点路径），与 success_value 都空则 HTTP 2xx 即成功 */
  success_path: string | null
  /** 成功判定值（与路径取出的值做字符串相等比较） */
  success_value: string | null
  /** 失败时从响应取错误消息的路径，可空 */
  error_path: string | null
  /** 结果字段列表 */
  result_fields: QueryResultField[]
}

export interface QueryResultField {
  /** 展示标签，如「可用余额」 */
  label: string
  /** JSON 点路径，数字段作数组下标 */
  path: string
  /** 主结果大字展示 */
  highlight?: boolean
  /** 值前缀，如 ¥ */
  prefix?: string
}

/** 执行结果（每个卡密行一条） */
export interface ExecResult {
  /** 账号（已脱敏，如 137****2162），Cookie 手动查询时为 null */
  account: string | null
  success: boolean
  error: string | null
  fields: ExecResultField[]
  /** ISO 时间字符串或空串 */
  as_of: string
}

export interface ExecResultField {
  label: string
  value: string
  highlight?: boolean
  prefix?: string
}

// ==================== 管理接口（需登录，axios） ====================

const ITEM_PREFIX = '/api/v1/items'

/** 获取商品查询按钮配置 */
export const getItemQueryButtons = (
  cookieId: string,
  itemId: string,
): Promise<ApiResponse<{ buttons: QueryButton[] }>> => {
  return get(`${ITEM_PREFIX}/${cookieId}/${itemId}/query-buttons`)
}

/** 保存商品查询按钮配置（整体覆盖） */
export const saveItemQueryButtons = (
  cookieId: string,
  itemId: string,
  buttons: QueryButton[],
): Promise<ApiResponse> => {
  return put(`${ITEM_PREFIX}/${cookieId}/${itemId}/query-buttons`, { buttons })
}

// ==================== 公开接口（无需登录，原生 fetch） ====================

const PUBLIC_PREFIX = '/api/v1/item-query'

/** 公开接口返回的按钮信息（只含名称与 cookie 标记，不含 URL/headers 等敏感配置） */
export interface PublicQueryButton {
  name: string
  /** 该按钮配置是否引用 {cookie} 变量（手动 Cookie 查询默认选中第一个 true 的按钮） */
  uses_cookie?: boolean
}

export interface PublicQueryButtonsData {
  buttons: PublicQueryButton[]
  /** 任一按钮配置含 {cookie} 变量时为 true，前端据此显示手动 Cookie 查询入口 */
  uses_cookie: boolean
}

/** 按订单号获取商品配置的查询按钮列表 */
export async function getQueryButtonsByOrder(
  orderNo: string,
): Promise<ApiResponse<PublicQueryButtonsData>> {
  const params = new URLSearchParams({ order_no: orderNo })
  const response = await fetch(`${PUBLIC_PREFIX}/buttons?${params.toString()}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' },
  })
  return response.json()
}

/**
 * 执行查询按钮
 * - cookieOverride 非空时跳过订单/发货内容校验，仅替换 {cookie} 执行一次
 * - 否则按订单发货内容逐行提取变量并发执行，每行一条 ExecResult
 */
export async function executeQueryButton(params: {
  orderNo?: string | null
  buttonIndex: number
  cookieOverride?: string | null
}): Promise<ApiResponse<{ results: ExecResult[] }>> {
  const response = await fetch(`${PUBLIC_PREFIX}/execute`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      order_no: params.orderNo || null,
      button_index: params.buttonIndex,
      cookie_override: params.cookieOverride || null,
    }),
  })
  return response.json()
}
