/**
 * 分销管理 API
 * 
 * 提供货源管理和对接记录管理相关接口
 */
import { get, post, put, del } from '@/utils/request'
import type { ApiResponse } from '@/types'

// 可对接卡券类型（公开信息）
export interface SupplyCard {
  id: number
  user_id?: number  // 卡券拥有者ID
  name: string
  type: 'api' | 'text' | 'data' | 'image'
  description?: string
  price?: string
  fee_payer?: string  // 手续费支付方式：distributor/dealer
  min_price?: string  // 最低售价
  is_multi_spec?: boolean
  spec_name?: string
  spec_value?: string
  is_docked?: boolean
  dock_record_id?: number
  created_at?: string
}

// 货源列表响应
export interface SupplyListResponse {
  list: SupplyCard[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// 对接记录类型
export interface DockRecord {
  id: number
  user_id: number
  owner_username?: string  // 记录归属用户名（管理员视图展示）
  card_id: number
  card_name?: string
  dock_name: string
  markup_amount: string
  card_price?: string
  fee_payer?: string  // 手续费支付方式：distributor/dealer
  min_price?: string  // 最低售价
  is_multi_spec?: boolean
  spec_name?: string
  spec_value?: string
  remark?: string
  delivery_count?: number  // 发货次数
  status: boolean
  disable_reason?: string  // 禁用原因
  level?: number           // 分销层级：1=一级分销，2=二级分销
  parent_dock_id?: number  // 上级对接记录ID
  source_user_id?: number  // 上级分销商用户ID
  allow_sub_dock?: boolean // 是否允许下级对接
  sub_dock_price?: string  // 给下级的对接价格
  sub_dock_visibility?: string  // 下级对接可见性：public/dealer_only
  created_at?: string
  updated_at?: string
  contact_wechat?: string  // 上游联系微信
  contact_qq?: string      // 上游联系QQ
  contact_email?: string   // 上游联系邮箱
}

// 对接记录列表响应
export interface DockRecordListResponse {
  list: DockRecord[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// 创建对接记录请求
export interface DockRecordCreateData {
  card_id: number
  dock_name: string
  markup_amount?: string
  remark?: string
}

// 更新对接记录请求
export interface DockRecordUpdateData {
  dock_name?: string
  markup_amount?: string
  remark?: string
  status?: boolean
}

// 分销商类型
export interface Dealer {
  user_id: number
  username: string
  email: string
  dock_count: number       // 对接卡券数量
  last_dock_time?: string  // 最近对接时间
  level_1_count?: number   // 一级对接数量
  level_2_count?: number   // 二级对接数量
}

// 分销商列表响应
export interface DealerListResponse {
  list: Dealer[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// 资金流水类型
export interface FundFlow {
  id: number
  user_id: number
  type: string            // income-收入，expense-支出
  amount: string          // 发生额
  balance_before: string  // 发生前余额
  balance_after: string   // 发生后余额
  order_id?: number       // 关联订单ID
  dock_record_id?: number // 关联对接记录ID
  description?: string    // 流水描述
  created_at?: string     // 发生时间
}

// 资金流水列表响应
export interface FundFlowListResponse {
  list: FundFlow[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// 二级分销货源记录类型
export interface SubSupplyRecord {
  id: number              // 一级对接记录ID
  source_user_id: number  // 一级分销商用户ID
  source_username: string // 一级分销商用户名
  card_id: number
  card_name: string
  card_price?: string
  sub_dock_price?: string  // 一级分销商给下级的对接价格
  dock_name: string
  markup_amount: string
  is_multi_spec?: boolean
  spec_name?: string
  spec_value?: string
  fee_payer?: string
  min_price?: string
  is_docked: boolean      // 当前用户是否已对接
}

// 二级分销货源列表响应
export interface SubSupplyListResponse {
  list: SubSupplyRecord[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// 创建二级对接记录请求
export interface SubDockRecordCreateData {
  parent_dock_id: number
  dock_name: string
  remark?: string
}

// ========== 货源管理 ==========

// 获取可对接卡券列表
export const getSupplyCards = (
  page: number = 1,
  pageSize: number = 20,
  search: string = '',
  cardType: string = '',
): Promise<SupplyListResponse> => {
  const params = new URLSearchParams()
  params.append('page', String(page))
  params.append('page_size', String(pageSize))
  if (search) params.append('search', search)
  if (cardType) params.append('type', cardType)
  return get(`/api/v1/distribution/supply?${params.toString()}`)
}

// ========== 对接记录管理 ==========

// 创建对接记录
export const createDockRecord = (data: DockRecordCreateData): Promise<ApiResponse> => {
  return post('/api/v1/distribution/dock-records', data)
}

// 更新对接记录
export const updateDockRecord = (id: number, data: DockRecordUpdateData): Promise<ApiResponse> => {
  return put(`/api/v1/distribution/dock-records/${id}`, data)
}

// 分销主更新对接记录（仅限状态和禁用原因）
export const updateDockRecordByOwner = (id: number, data: Record<string, unknown>): Promise<ApiResponse> => {
  return put(`/api/v1/distribution/dock-records/${id}/owner-update`, data)
}

// 删除对接记录
export const deleteDockRecord = (id: number): Promise<ApiResponse> => {
  return del(`/api/v1/distribution/dock-records/${id}`)
}

// ========== 分销商管理 ==========

// 获取分销商列表（对接了自己卡券的用户）
export const getDealers = (
  page: number = 1,
  pageSize: number = 20,
  search: string = '',
): Promise<DealerListResponse> => {
  const params = new URLSearchParams()
  params.append('page', String(page))
  params.append('page_size', String(pageSize))
  if (search) params.append('search', search)
  return get(`/api/v1/distribution/dealers?${params.toString()}`)
}

// 获取分销商对接卡券明细
export const getDealerDetails = (
  dealerUserId: number,
  page: number = 1,
  pageSize: number = 20,
): Promise<DockRecordListResponse> => {
  const params = new URLSearchParams()
  params.append('page', String(page))
  params.append('page_size', String(pageSize))
  return get(`/api/v1/distribution/dealers/${dealerUserId}/details?${params.toString()}`)
}

// ========== 资金流水 ==========

// 获取资金流水列表
export const getFundFlows = (
  page: number = 1,
  pageSize: number = 20,
  flowType: string = '',
): Promise<FundFlowListResponse> => {
  const params = new URLSearchParams()
  params.append('page', String(page))
  params.append('page_size', String(pageSize))
  if (flowType) params.append('type', flowType)
  return get(`/api/v1/distribution/fund-flows?${params.toString()}`)
}

// 对接记录筛选参数
export interface DockRecordFilterParams {
  status?: boolean | null           // 启用状态
  level?: number | null             // 分销层级：1/2
  allow_sub_dock?: boolean | null   // 是否开放下级对接
}

// 获取对接记录列表（支持状态/层级/开放对接筛选）
export const getDockRecords = (
  page: number = 1,
  pageSize: number = 20,
  search: string = '',
  filters: DockRecordFilterParams = {},
): Promise<DockRecordListResponse> => {
  const params = new URLSearchParams()
  params.append('page', String(page))
  params.append('page_size', String(pageSize))
  if (search) params.append('search', search)
  if (filters.status !== null && filters.status !== undefined) {
    params.append('status', String(filters.status))
  }
  if (filters.level !== null && filters.level !== undefined) {
    params.append('level', String(filters.level))
  }
  if (filters.allow_sub_dock !== null && filters.allow_sub_dock !== undefined) {
    params.append('allow_sub_dock', String(filters.allow_sub_dock))
  }
  return get(`/api/v1/distribution/dock-records?${params.toString()}`)
}

// ========== 二级分销 ==========

// 获取可对接的一级分销商记录列表（二级分销货源广场）
export const getSubSupplyRecords = (
  page: number = 1,
  pageSize: number = 20,
  search: string = '',
): Promise<SubSupplyListResponse> => {
  const params = new URLSearchParams()
  params.append('page', String(page))
  params.append('page_size', String(pageSize))
  if (search) params.append('search', search)
  return get(`/api/v1/distribution/sub-supply?${params.toString()}`)
}

// 创建二级对接记录
export const createSubDockRecord = (data: SubDockRecordCreateData): Promise<ApiResponse> => {
  return post('/api/v1/distribution/sub-dock-records', data)
}

// 开放/关闭下级对接
export const toggleSubDock = (recordId: number, allow: boolean, subDockPrice?: string, subDockVisibility?: string): Promise<ApiResponse> => {
  return put(`/api/v1/distribution/dock-records/${recordId}/toggle-sub-dock`, { allow, sub_dock_price: subDockPrice, sub_dock_visibility: subDockVisibility })
}

// 获取对接记录的提货地址（免认证GET链接）
export const getPickupUrl = (recordId: number): Promise<ApiResponse<{ pickup_url: string }>> => {
  return get(`/api/v1/distribution/dock-records/${recordId}/pickup-url`)
}

// 更新对接记录状态（带级联禁用下级）
export const cascadeUpdateStatus = (
  recordId: number,
  status: boolean,
  disableReason?: string,
): Promise<ApiResponse> => {
  return put(`/api/v1/distribution/dock-records/${recordId}/cascade-status`, {
    status,
    disable_reason: disableReason,
  })
}

// 获取下级分销商列表
export const getSubDealers = (
  page: number = 1,
  pageSize: number = 20,
  search: string = '',
): Promise<DealerListResponse> => {
  const params = new URLSearchParams()
  params.append('page', String(page))
  params.append('page_size', String(pageSize))
  if (search) params.append('search', search)
  return get(`/api/v1/distribution/sub-dealers?${params.toString()}`)
}

// 获取下级分销商对接明细
export const getSubDealerDetails = (
  dealerUserId: number,
  page: number = 1,
  pageSize: number = 20,
): Promise<DockRecordListResponse> => {
  const params = new URLSearchParams()
  params.append('page', String(page))
  params.append('page_size', String(pageSize))
  return get(`/api/v1/distribution/sub-dealers/${dealerUserId}/details?${params.toString()}`)
}

// 一级分销商禁用下级对接记录
export const disableSubDealer = (
  recordId: number,
  disableReason?: string,
): Promise<ApiResponse> => {
  const params = new URLSearchParams()
  if (disableReason) params.append('disable_reason', disableReason)
  return put(`/api/v1/distribution/sub-dealers/${recordId}/disable?${params.toString()}`)
}


// ========== 货源管理（对接码绑定） ==========

export interface SourceBinding {
  id: number
  dock_code: string
  target_user_id: number
  target_username: string
  created_at: string | null
}

// 获取已绑定的货源列表
export const getSourceBindings = (): Promise<{ success: boolean; data: SourceBinding[] }> => {
  return get('/api/v1/distribution/source-bindings')
}

// 绑定对接码
export const bindDockCode = (dockCode: string): Promise<ApiResponse> => {
  return post('/api/v1/distribution/source-bindings', { dock_code: dockCode })
}

// 解绑货源
export const unbindSource = (bindingId: number): Promise<ApiResponse> => {
  return del(`/api/v1/distribution/source-bindings/${bindingId}`)
}


// ========== 对接我的（供应商视角） ==========

export interface BoundUser {
  id: number
  user_id: number
  username: string
  dock_code: string
  dock_count: number
  created_at: string | null
}

// 获取对接我的列表
export const getBoundToMe = (): Promise<{ success: boolean; data: BoundUser[] }> => {
  return get('/api/v1/distribution/bound-to-me')
}

// 删除对接我的记录（级联删除对接记录）
export const removeBoundUser = (bindingId: number): Promise<ApiResponse> => {
  return del(`/api/v1/distribution/bound-to-me/${bindingId}`)
}


// ========== 代理订单 ==========

export interface AgentOrder {
  id: number
  order_no: string
  item_id: string
  card_id: number
  card_name?: string
  dock_record_id: number
  dock_name?: string
  dock_level: number
  sale_price: string
  dock_price: string
  card_price?: string
  level2_cost?: string
  profit: string
  fee_amount?: string
  fee_payer?: string
  owner_user_id?: number
  owner_name?: string
  delivery_content?: string
  buyer_id?: string
  user_id?: number
  user_name?: string
  dealer_user_id?: number
  dealer_name?: string
  upstream_user_id?: number
  upstream_name?: string
  status: string
  settle_remark?: string
  source?: string  // 来源：pickup-提货，order-闲鱼订单
  created_at?: string
  updated_at?: string
}

export interface AgentOrderListResponse {
  list: AgentOrder[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

// 获取我的代理订单（我作为分销商）
export const getMyAgentOrders = (
  page: number = 1,
  pageSize: number = 20,
  status: string = '',
): Promise<{ success: boolean; data: AgentOrderListResponse }> => {
  const params = new URLSearchParams()
  params.append('page', String(page))
  params.append('page_size', String(pageSize))
  if (status) params.append('status', status)
  return get(`/api/v1/distribution/agent-orders/my?${params.toString()}`)
}

// 获取代理我的订单（别人使用我的卡券）
export const getUpstreamAgentOrders = (
  page: number = 1,
  pageSize: number = 20,
  status: string = '',
): Promise<{ success: boolean; data: AgentOrderListResponse }> => {
  const params = new URLSearchParams()
  params.append('page', String(page))
  params.append('page_size', String(pageSize))
  if (status) params.append('status', status)
  return get(`/api/v1/distribution/agent-orders/upstream?${params.toString()}`)
}

// 获取代理订单明细
export const getAgentOrderDetail = (
  orderId: number,
): Promise<{ success: boolean; message?: string; data?: AgentOrder }> => {
  return get(`/api/v1/distribution/agent-orders/detail/${orderId}`)
}
