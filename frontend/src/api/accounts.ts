import { get, post, put, del } from '@/utils/request'
import type { Account, AccountDetail, ApiResponse } from '@/types'

// 获取账号列表（返回账号ID数组）
export const getAccounts = async (): Promise<Account[]> => {
  const ids: string[] = await get('/cookies')
  // 后端返回的是账号ID数组，转换为Account对象数组
  return ids.map(id => ({ 
    id, 
    cookie: '', 
    enabled: true,
    use_ai_reply: false,
    use_default_reply: false,
    auto_confirm: false
  }))
}

// 获取账号详情列表
export const getAccountDetails = async (): Promise<AccountDetail[]> => {
  interface BackendAccountDetail {
    id: string
    value: string
    enabled: boolean
    auto_confirm: boolean
    remark?: string
    pause_duration?: number
  }
  const data = await get<BackendAccountDetail[]>('/cookies/details')
  // 后端返回 value 字段，前端使用 cookie 字段
  return data.map((item) => ({
    id: item.id,
    cookie: item.value,
    enabled: item.enabled,
    auto_confirm: item.auto_confirm,
    note: item.remark,
    pause_duration: item.pause_duration,
    use_ai_reply: false,
    use_default_reply: false,
  }))
}

// 添加账号
export const addAccount = (data: { id: string; cookie: string }): Promise<ApiResponse> => {
  // 后端需要 id 和 value 字段
  return post('/cookies', { id: data.id, value: data.cookie })
}

// 更新账号 Cookie 值
export const updateAccountCookie = (id: string, value: string): Promise<ApiResponse> => {
  return put(`/cookies/${id}`, { id, value })
}

// 更新账号启用/禁用状态
export const updateAccountStatus = (id: string, enabled: boolean): Promise<ApiResponse> => {
  return put(`/cookies/${id}/status`, { enabled })
}

// 更新账号备注
export const updateAccountRemark = (id: string, remark: string): Promise<ApiResponse> => {
  return put(`/cookies/${id}/remark`, { remark })
}

// 更新账号自动确认设置
export const updateAccountAutoConfirm = (id: string, autoConfirm: boolean): Promise<ApiResponse> => {
  return put(`/cookies/${id}/auto-confirm`, { auto_confirm: autoConfirm })
}

// 更新账号暂停时间
export const updateAccountPauseDuration = (id: string, pauseDuration: number): Promise<ApiResponse> => {
  return put(`/cookies/${id}/pause-duration`, { pause_duration: pauseDuration })
}

// 删除账号
export const deleteAccount = (id: string): Promise<ApiResponse> => {
  return del(`/cookies/${id}`)
}

// 获取账号二维码登录
export const getQRCode = (accountId: string): Promise<{ success: boolean; qrcode_url?: string; token?: string }> => {
  return post('/qrcode/generate', { account_id: accountId })
}

// 检查二维码登录状态
export const checkQRCodeStatus = (token: string): Promise<{ success: boolean; status: string; cookie?: string }> => {
  return post('/qrcode/check', { token })
}

// 账号密码登录
export const passwordLogin = (data: { account_id: string; account: string; password: string; show_browser?: boolean }): Promise<ApiResponse> => {
  return post('/password-login', data)
}

// 生成扫码登录二维码
export const generateQRLogin = (): Promise<{ success: boolean; session_id?: string; qr_code_url?: string; message?: string }> => {
  return post('/qr-login/generate')
}

// 检查扫码登录状态
// 后端直接返回 { status: ..., message?: ..., account_info?: ... }，没有 success 字段
export const checkQRLoginStatus = async (sessionId: string): Promise<{
  success: boolean
  status: 'pending' | 'scanned' | 'success' | 'expired' | 'cancelled' | 'verification_required' | 'processing' | 'already_processed' | 'error'
  message?: string
  account_info?: {
    account_id: string
    is_new_account: boolean
  }
}> => {
  const result = await get<{
    status: string
    message?: string
    account_info?: { account_id: string; is_new_account: boolean }
  }>(`/qr-login/check/${sessionId}`)
  // 后端没有返回 success 字段，根据 status 判断
  return {
    success: result.status !== 'error',
    status: result.status as 'pending' | 'scanned' | 'success' | 'expired' | 'cancelled' | 'verification_required' | 'processing' | 'already_processed' | 'error',
    message: result.message,
    account_info: result.account_info,
  }
}

// 检查密码登录状态
export const checkPasswordLoginStatus = (sessionId: string): Promise<{
  success: boolean
  status: 'pending' | 'processing' | 'success' | 'failed' | 'verification_required'
  message?: string
  account_id?: string
}> => {
  return get(`/password-login/status/${sessionId}`)
}

// AI 回复设置接口 - 与后端 AIReplySettings 模型对应
export interface AIReplySettings {
  ai_enabled: boolean
  model_name?: string
  api_key?: string
  base_url?: string
  max_discount_percent?: number
  max_discount_amount?: number
  max_bargain_rounds?: number
  custom_prompts?: string
  // 兼容旧字段（前端内部使用）
  enabled?: boolean
}

// 获取AI回复设置
export const getAIReplySettings = (cookieId: string): Promise<AIReplySettings> => {
  return get(`/ai-reply-settings/${cookieId}`)
}

// 更新AI回复设置
export const updateAIReplySettings = (cookieId: string, settings: Partial<AIReplySettings>): Promise<ApiResponse> => {
  // 转换字段名以匹配后端
  const payload: Record<string, unknown> = {
    ai_enabled: settings.ai_enabled ?? settings.enabled ?? false,
    model_name: settings.model_name ?? 'qwen-plus',
    api_key: settings.api_key ?? '',
    base_url: settings.base_url ?? 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    max_discount_percent: settings.max_discount_percent ?? 10,
    max_discount_amount: settings.max_discount_amount ?? 100,
    max_bargain_rounds: settings.max_bargain_rounds ?? 3,
    custom_prompts: settings.custom_prompts ?? '',
  }
  return put(`/ai-reply-settings/${cookieId}`, payload)
}

// 获取所有账号的AI回复设置
export const getAllAIReplySettings = (): Promise<Record<string, AIReplySettings>> => {
  return get('/ai-reply-settings')
}
