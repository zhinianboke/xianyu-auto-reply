// 用户相关类型
export type UserRole = 'ADMIN' | 'OPERATOR' | 'MEMBER'

export type UserStatus = 'ACTIVE' | 'INACTIVE' | 'SUSPENDED' | 'DELETED'

export interface User {
  user_id: number
  username: string
  is_admin: boolean
  email?: string
  phone?: string
  role?: UserRole
  status?: UserStatus
  account_limit?: number | null
}

export interface LoginRequest {
  username?: string
  password?: string
  email?: string
  verification_code?: string
  // 极验滑动验证码参数
  geetest_challenge?: string
  geetest_validate?: string
  geetest_seccode?: string
}

export interface LoginResponse {
  success: boolean
  message?: string
  token?: string
  refresh_token?: string
  user_id?: number
  username?: string
  is_admin?: boolean
  account_limit?: number | null
}

// 账号相关类型
export interface Account {
  pk?: number  // 数据库主键
  id: string
  owner_id?: number
  cookie: string
  enabled: boolean
  use_ai_reply: boolean
  use_default_reply: boolean
  auto_confirm: boolean
  scheduled_redelivery?: boolean
  scheduled_rate?: boolean
  auto_polish?: boolean
  confirm_before_send?: boolean
  send_before_confirm?: boolean
  auto_red_flower?: boolean
  ai_reply_block_ordered_users?: boolean
  delivery_disabled?: boolean
  delivery_disabled_reason?: string
  auto_close_order?: boolean
  delivery_only_card_after_close?: boolean
  // 禁止发货排除商品列表（命中此列表的 item_id 跳过禁止发货拦截，按正常流程发货）
  delivery_disabled_excluded_item_ids?: string[]
  note?: string
  remark?: string
  pause_duration?: number
  username?: string
  login_password?: string
  show_browser?: boolean
  disable_reason?: string
  created_at?: string
  updated_at?: string
}

export interface AccountDetail extends Account {
  keywords?: Keyword[]
  keywordCount?: number
  aiEnabled?: boolean
  message_expire_time?: number
  reply_delay_seconds?: number
  filter_count?: number  // 消息过滤规则数量
  today_reply_count?: number
  owner_username?: string  // 账号所属用户名（管理员查看全量时展示）
}

// 关键词相关类型
export interface Keyword {
  id?: string
  cookie_id?: string
  account_id?: string  // 查询全部账号时返回
  keyword: string
  reply: string
  item_id?: string      // 绑定的商品ID，空表示通用关键词
  type?: 'text' | 'image' | 'item' | 'normal'  // 关键词类型
  image_url?: string    // 图片类型关键词的图片URL
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
  is_polished?: boolean            // 是否擦亮
  is_multi_spec?: number | boolean
  multi_delivery?: boolean
  multi_quantity_delivery?: number | boolean
  default_reply_enabled?: boolean  // 默认回复是否启用
  has_default_reply?: boolean      // 是否配置了默认回复
  has_card?: boolean               // 是否配置了发货卡券
  ai_prompt?: string               // AI提示词
  has_ai_prompt?: boolean          // 是否配置了AI提示词
  created_at?: string
  updated_at?: string
}

// 订单相关类型
export interface Order {
  id: string
  order_id: string
  cookie_id: string
  item_id: string
  item_title?: string  // 商品标题
  buyer_id: string
  buyer_fish_nick?: string  // 买家闲鱼昵称（明文）
  chat_id?: string  // 聊天会话ID
  sku_info?: string
  quantity: number
  amount: string
  status: OrderStatus
  is_bargain?: boolean  // 是否小刀
  is_rated?: boolean  // 是否已评价
  is_red_flower?: boolean  // 是否已求小红花
  // 收货人信息
  receiver_name?: string  // 收货人姓名
  receiver_phone?: string  // 收货人手机号
  receiver_address?: string  // 收货地址
  // 发货信息
  delivery_method?: 'manual' | 'auto' | 'scheduled'  // 发货方式：manual-手动发货, auto-自动发货, scheduled-定时发货
  delivery_content?: string  // 发货内容（卡券内容）
  delivery_fail_reason?: string  // 发货失败原因
  delivery_send_status?: 'success' | 'failed' | 'unknown' | 'timeout' | null  // 关联消息日志：发送状态
  delivery_send_fail_reason?: string | null  // 关联消息日志：发送失败原因
  is_agent_order?: boolean  // 是否是代销订单
  source?: string  // 数据来源
  placed_at?: string  // 订单时间（下单时间）
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

// 通知渠道相关类型
export interface NotificationChannel {
  id: string
  cookie_id?: string
  name: string
  type: 'dingtalk' | 'feishu' | 'bark' | 'email' | 'webhook' | 'wechat' | 'telegram'
  channel_type?: string
  channel_name?: string
  channel_config?: string
  config?: Record<string, unknown>
  enabled: boolean
  created_at?: string
  updated_at?: string
}

// 消息通知相关类型 - 匹配后端接口
// 后端返回格式: { cookie_id: [ { id, channel_id, enabled, channel_name, ... } ] }
export interface MessageNotification {
  id: number
  cookie_id: string
  channel_id: number
  channel_name?: string
  enabled: boolean
}

// 系统设置相关类型
export interface DisclaimerSettings {
  'disclaimer.title': string
  'disclaimer.content': string
  'disclaimer.checkbox_text': string
  'disclaimer.agree_button_text': string
  'disclaimer.disagree_button_text': string
}

export interface LoginBrandingSettings {
  'login.system_name': string
  'login.system_title': string
  'login.system_description': string
}

export interface AuthFooterAdSettings {
  'auth.footer_ad_html': string
}

export type ThemeEffect = 'solid' | 'gradient'
export type ThemeColorPreset = 'ocean' | 'emerald' | 'violet' | 'indigo' | 'amber' | 'sunset' | 'aurora' | 'rose' | 'ruby'
export type ThemeFontFamily = 'system' | 'yahei' | 'heiti' | 'songti' | 'kaiti' | 'fangsong' | 'xingkai' | 'rounded' | 'monospace'

export interface ThemeAppearanceSettings {
  'theme.effect': ThemeEffect
  'theme.color_preset': ThemeColorPreset
}

export interface ThemeFontSettings {
  'theme.font_family': ThemeFontFamily
}

export type ThemeSettings = ThemeAppearanceSettings & ThemeFontSettings

export interface SystemSettings {
  ai_model?: string
  ai_api_key?: string
  ai_api_url?: string
  ai_base_url?: string
  'runtime.is_exe_mode'?: boolean
  default_reply?: string
  registration_enabled?: boolean
  show_default_login_info?: boolean
  login_captcha_enabled?: boolean
  'disclaimer.title'?: string
  'disclaimer.content'?: string
  'disclaimer.checkbox_text'?: string
  'disclaimer.agree_button_text'?: string
  'disclaimer.disagree_button_text'?: string
  'login.system_name'?: string
  'login.system_title'?: string
  'login.system_description'?: string
  'auth.footer_ad_html'?: string
  'theme.effect'?: ThemeEffect
  'theme.color_preset'?: ThemeColorPreset
  'theme.font_family'?: ThemeFontFamily
  // SMTP邮件配置
  smtp_server?: string
  smtp_port?: number
  smtp_user?: string
  smtp_password?: string
  smtp_from?: string
  smtp_use_tls?: boolean
  smtp_use_ssl?: boolean
  // 模块设置
  'distribution.fee_type'?: string  // fixed-固定金额, percent-百分比
  'distribution.fee_rate'?: string
  // 支付宝配置
  'alipay.app_id'?: string
  'alipay.private_key'?: string
  'alipay.alipay_public_key'?: string
  'alipay.gateway_url'?: string
  'alipay.notify_url'?: string
  // 提现配置
  'withdraw.notify_email'?: string
  'withdraw.min_amount'?: string
  // 日志配置
  'log.retention_days'?: string
  // 账号安全设置
  'account.face_verify_timeout_disable'?: boolean
  // 代理设置
  'proxy.api_url'?: string
  'proxy.enabled'?: boolean
  [key: string]: unknown
}

// API 响应类型
export interface ApiResponse<T = unknown> {
  success: boolean
  message?: string
  data?: T
  // 后端兼容字段
  msg?: string
  detail?: string
}

// 仪表盘统计类型
export interface DashboardStats {
  totalAccounts: number
  totalKeywords: number
  activeAccounts: number
  totalOrders: number
}

// 消息过滤规则类型
export type MessageFilterType = 'skip_reply' | 'skip_notify'

export interface MessageFilter {
  id: number
  account_id: string
  keyword: string
  filter_type: MessageFilterType
  enabled: boolean
  created_at?: string
  updated_at?: string
}

export interface MessageFilterCreate {
  account_id: string
  keyword: string
  filter_types: MessageFilterType[]
}

export interface MessageFilterBatchCreate {
  account_ids: string[]
  keyword: string
  filter_types: MessageFilterType[]
}

export interface MessageFilterUpdate {
  keyword?: string
  filter_type?: MessageFilterType
  enabled?: boolean
}
