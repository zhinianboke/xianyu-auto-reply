// 用户相关类型
export interface User {
  user_id: number
  username: string
  is_admin: boolean
  email?: string
}

export interface LoginRequest {
  username?: string
  password?: string
  email?: string
  verification_code?: string
}

export interface LoginResponse {
  success: boolean
  message?: string
  token?: string
  user_id?: number
  username?: string
  is_admin?: boolean
}

// 账号相关类型
export interface Account {
  id: string
  cookie: string
  enabled: boolean
  use_ai_reply: boolean
  use_default_reply: boolean
  auto_confirm: boolean
  note?: string
  pause_duration?: number
  created_at?: string
  updated_at?: string
}

export interface AccountDetail extends Account {
  keywords?: Keyword[]
  keywordCount?: number
}

// 关键词相关类型
export interface Keyword {
  id?: string
  cookie_id?: string
  keyword: string
  reply: string
  item_id?: string      // 绑定的商品ID，空表示通用关键词
  type?: 'text' | 'image' | 'item' | 'normal'  // 关键词类型
  image_url?: string    // 图片类型关键词的图片URL
  fuzzy_match?: boolean
  created_at?: string
  updated_at?: string
}

// 商品相关类型
export interface Item {
  id: string | number
  cookie_id: string
  item_id: string
  title?: string
  item_title?: string
  desc?: string
  item_description?: string
  item_detail?: string
  item_category?: string
  price?: string
  item_price?: string
  has_sku?: boolean
  is_multi_spec?: number | boolean
  multi_delivery?: boolean
  multi_quantity_delivery?: number | boolean
  created_at?: string
  updated_at?: string
}

export interface ItemReply {
  id: string
  cookie_id: string
  item_id: string
  title?: string
  content?: string
  reply: string
  created_at?: string
  updated_at?: string
}

// 订单相关类型
export interface Order {
  id: string
  order_id: string
  cookie_id: string
  item_id: string
  buyer_id: string
  sku_info?: string
  quantity: number
  amount: string
  status: OrderStatus
  created_at?: string
  updated_at?: string
}

export type OrderStatus = 
  | 'processing' 
  | 'processed' 
  | 'shipped' 
  | 'completed' 
  | 'cancelled' 
  | 'unknown'

// 卡券相关类型
export interface Card {
  id: string
  cookie_id: string
  item_id: string
  keyword?: string
  card_content: string
  is_used: boolean
  used?: boolean
  order_id?: string
  created_at?: string
  updated_at?: string
}

// 发货规则相关类型 - 匹配后端接口
export interface DeliveryRule {
  id: number
  keyword: string
  card_id: number
  delivery_count: number
  enabled: boolean
  description?: string
  delivery_times?: number
  card_name?: string
  card_type?: string
  is_multi_spec?: boolean
  spec_name?: string
  spec_value?: string
  created_at?: string
  updated_at?: string
}

// 通知渠道相关类型
export interface NotificationChannel {
  id: string
  cookie_id?: string
  name: string
  type: 'qq' | 'dingtalk' | 'feishu' | 'bark' | 'email' | 'webhook' | 'wechat' | 'telegram'
  channel_type?: string
  channel_name?: string
  channel_config?: string
  config?: Record<string, unknown>
  enabled: boolean
  created_at?: string
  updated_at?: string
}

// 消息通知相关类型 - 匹配后端接口
// 后端返回格式: { cookie_id: { channel_id: { enabled: boolean, channel_name: string } } }
export interface MessageNotification {
  cookie_id: string
  channel_id: number
  channel_name?: string
  enabled: boolean
}

// 系统设置相关类型
export interface SystemSettings {
  ai_model?: string
  ai_api_key?: string
  ai_api_url?: string
  ai_base_url?: string
  default_reply?: string
  registration_enabled?: boolean
  show_default_login_info?: boolean
  login_captcha_enabled?: boolean
  // SMTP邮件配置
  smtp_server?: string
  smtp_port?: number
  smtp_user?: string
  smtp_password?: string
  smtp_from?: string
  smtp_use_tls?: boolean
  smtp_use_ssl?: boolean
  // API安全
  qq_reply_secret_key?: string
  [key: string]: unknown
}

// API 响应类型
export interface ApiResponse<T = unknown> {
  success: boolean
  message?: string
  data?: T
}

// 分页相关类型
export interface PaginationParams {
  page: number
  pageSize: number
}

export interface PaginatedResponse<T> {
  data: T[]
  total: number
  page: number
  pageSize: number
  totalPages: number
}

// 仪表盘统计类型
export interface DashboardStats {
  totalAccounts: number
  totalKeywords: number
  activeAccounts: number
  totalOrders: number
}
