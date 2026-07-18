import { get, post, put } from '@/utils/request'
import type {
  ApiResponse,
  AuthFooterAdSettings,
  DisclaimerSettings,
  LoginBrandingSettings,
  SystemSettings,
  ThemeAppearanceSettings,
  ThemeFontSettings,
} from '@/types'
import {
  dispatchThemeSettingsUpdated,
  normalizeThemeAppearanceSettings,
  normalizeThemeFontSettings,
} from '@/utils/theme'

// API前缀
const SYSTEM_SETTINGS_PREFIX = '/api/v1/system-settings'
const PUBLIC_SYSTEM_SETTINGS_PREFIX = `${SYSTEM_SETTINGS_PREFIX}/public`
const AI_SETTINGS_PREFIX = '/api/v1/ai-reply-settings'
const ADMIN_PREFIX = '/api/v1/admin'
const USERS_PREFIX = '/api/v1/users'
const MENU_HIDDEN_SETTING_KEY = 'navigation.hidden_menu_keys'
const READONLY_SYSTEM_SETTING_KEYS = ['runtime.is_exe_mode']
const INDEPENDENT_SYSTEM_SETTING_KEYS = ['password_login.mode', 'captcha.slider_mode']
const DEFAULT_DISCLAIMER_SETTINGS: DisclaimerSettings = {
  'disclaimer.title': '免责声明',
  'disclaimer.content': '数据存储说明\n1. 本系统在运行过程中，为保障服务正常运行，会存储用户账号密码、登录 Cookie、商品信息、卡券信息等业务数据。\n2. 上述数据仅用于系统功能运行、自动化处理和业务管理，不作为其他用途。\n3. 请您自行确认服务器环境、账号权限和数据保管措施的安全性。\n\n用户须知\n1. 用户应确保使用本系统的行为符合相关平台规则和法律法规。\n2. 因用户自身违规操作、账号共享、密码泄露、服务器安全问题导致的损失，由用户自行承担。\n3. 建议用户定期备份重要数据，因系统故障、第三方平台变更、不可抗力等导致的异常或损失，本系统不承担责任。\n4. 本系统依赖第三方平台接口和网络环境，无法保证服务始终连续、稳定、无中断。\n\n隐私与风险提示\n1. 请勿在未充分评估风险的情况下接入生产环境或敏感账号。\n2. 使用本系统即表示您已充分理解并接受相关风险，并愿意自行承担相应责任。',
  'disclaimer.checkbox_text': '我已阅读并同意以上免责声明',
  'disclaimer.agree_button_text': '同意并继续',
  'disclaimer.disagree_button_text': '不同意',
}

const DEFAULT_LOGIN_BRANDING_SETTINGS: LoginBrandingSettings = {
  'login.system_name': '闲鱼管理系统',
  'login.system_title': '高效专业的\n闲鱼自动化管理平台',
  'login.system_description': '自动回复、智能客服、订单管理、数据分析，一站式解决闲鱼运营难题',
}

const DEFAULT_AUTH_FOOTER_AD_SETTINGS: AuthFooterAdSettings = {
  'auth.footer_ad_html': '© 2026 划算云服务器 ·<a href="http://www.hsykj.com" target="_BLANK">www.hsykj.com</a>',
}

const DISCLAIMER_SETTING_KEYS: Array<keyof DisclaimerSettings> = [
  'disclaimer.title',
  'disclaimer.content',
  'disclaimer.checkbox_text',
  'disclaimer.agree_button_text',
  'disclaimer.disagree_button_text',
]

const LOGIN_BRANDING_SETTING_KEYS: Array<keyof LoginBrandingSettings> = [
  'login.system_name',
  'login.system_title',
  'login.system_description',
]

const AUTH_FOOTER_AD_SETTING_KEYS: Array<keyof AuthFooterAdSettings> = [
  'auth.footer_ad_html',
]

const BOOLEAN_SYSTEM_SETTING_KEYS = ['registration_enabled', 'show_default_login_info', 'login_captcha_enabled', 'smtp_use_tls', 'smtp_use_ssl', 'runtime.is_exe_mode', 'account.face_verify_timeout_disable', 'proxy.enabled']

export const LOGIN_BRANDING_UPDATED_EVENT = 'login-branding-updated'

const convertSystemSettings = (data: Record<string, unknown>): SystemSettings => {
  const converted: SystemSettings = {}
  for (const [key, value] of Object.entries(data)) {
    if (BOOLEAN_SYSTEM_SETTING_KEYS.includes(key)) {
      converted[key] = value === true || value === 'true'
    } else {
      converted[key] = value
    }
  }
  return converted
}

// 获取系统设置
export const getSystemSettings = async (): Promise<{ success: boolean; data?: SystemSettings }> => {
  const data = await get<Record<string, unknown>>(SYSTEM_SETTINGS_PREFIX)
  return { success: true, data: convertSystemSettings(data) }
}

export const getPublicSystemSettings = async (): Promise<{ success: boolean; data?: SystemSettings }> => {
  const data = await get<Record<string, unknown>>(PUBLIC_SYSTEM_SETTINGS_PREFIX)
  return { success: true, data: convertSystemSettings(data) }
}

// 更新系统设置
export const updateSystemSettings = async (data: Partial<SystemSettings>): Promise<ApiResponse> => {
  // 逐个更新设置项，确保 value 是字符串
  const promises = Object.entries(data)
    .filter(([key]) => (
      !READONLY_SYSTEM_SETTING_KEYS.includes(key)
      && !INDEPENDENT_SYSTEM_SETTING_KEYS.includes(key)
    ))
    .map(([key, value]) => {
    // 将布尔值和数字转换为字符串
    let stringValue: string
    if (typeof value === 'boolean') {
      stringValue = value ? 'true' : 'false'
    } else if (typeof value === 'number') {
      stringValue = String(value)
    } else {
      stringValue = value as string
    }
      return put(`${SYSTEM_SETTINGS_PREFIX}/${key}`, { value: stringValue })
    })
  await Promise.all(promises)
  return { success: true, message: '设置已保存' }
}

export const getDefaultDisclaimerSettings = (): DisclaimerSettings => ({ ...DEFAULT_DISCLAIMER_SETTINGS })

export const normalizeDisclaimerSettings = (settings?: Partial<SystemSettings> | null): DisclaimerSettings => {
  return {
    'disclaimer.title': String(settings?.['disclaimer.title'] ?? DEFAULT_DISCLAIMER_SETTINGS['disclaimer.title']),
    'disclaimer.content': String(settings?.['disclaimer.content'] ?? DEFAULT_DISCLAIMER_SETTINGS['disclaimer.content']),
    'disclaimer.checkbox_text': String(settings?.['disclaimer.checkbox_text'] ?? DEFAULT_DISCLAIMER_SETTINGS['disclaimer.checkbox_text']),
    'disclaimer.agree_button_text': String(settings?.['disclaimer.agree_button_text'] ?? DEFAULT_DISCLAIMER_SETTINGS['disclaimer.agree_button_text']),
    'disclaimer.disagree_button_text': String(settings?.['disclaimer.disagree_button_text'] ?? DEFAULT_DISCLAIMER_SETTINGS['disclaimer.disagree_button_text']),
  }
}

export const buildDisclaimerSettingsPayload = (settings?: Partial<SystemSettings> | null): DisclaimerSettings => {
  const normalized = normalizeDisclaimerSettings(settings)
  return DISCLAIMER_SETTING_KEYS.reduce((payload, key) => {
    payload[key] = normalized[key]
    return payload
  }, {} as DisclaimerSettings)
}

export const updateDisclaimerSettings = async (settings?: Partial<SystemSettings> | null): Promise<ApiResponse> => {
  return updateSystemSettings(buildDisclaimerSettingsPayload(settings) as Partial<SystemSettings>)
}

export const getDefaultLoginBrandingSettings = (): LoginBrandingSettings => ({ ...DEFAULT_LOGIN_BRANDING_SETTINGS })

export const normalizeLoginBrandingSettings = (settings?: Partial<SystemSettings> | null): LoginBrandingSettings => {
  const systemName = settings?.['login.system_name']
  const systemTitle = settings?.['login.system_title']
  const systemDescription = settings?.['login.system_description']

  return {
    'login.system_name': typeof systemName === 'string' && systemName.trim() ? systemName : DEFAULT_LOGIN_BRANDING_SETTINGS['login.system_name'],
    'login.system_title': typeof systemTitle === 'string' && systemTitle.trim() ? systemTitle : DEFAULT_LOGIN_BRANDING_SETTINGS['login.system_title'],
    'login.system_description': typeof systemDescription === 'string' && systemDescription.trim() ? systemDescription : DEFAULT_LOGIN_BRANDING_SETTINGS['login.system_description'],
  }
}

export const dispatchLoginBrandingUpdated = (settings?: Partial<SystemSettings> | null): void => {
  if (typeof window === 'undefined') {
    return
  }

  const normalized = normalizeLoginBrandingSettings(settings)
  window.dispatchEvent(new CustomEvent<LoginBrandingSettings>(LOGIN_BRANDING_UPDATED_EVENT, { detail: normalized }))
}

export const buildLoginBrandingSettingsPayload = (settings?: Partial<SystemSettings> | null): LoginBrandingSettings => {
  const normalized = normalizeLoginBrandingSettings(settings)
  return LOGIN_BRANDING_SETTING_KEYS.reduce((payload, key) => {
    payload[key] = normalized[key]
    return payload
  }, {} as LoginBrandingSettings)
}

export const updateLoginBrandingSettings = async (settings?: Partial<SystemSettings> | null): Promise<ApiResponse> => {
  const response = await updateSystemSettings(buildLoginBrandingSettingsPayload(settings) as Partial<SystemSettings>)
  if (response.success) {
    dispatchLoginBrandingUpdated(settings)
  }
  return response
}

export const getDefaultAuthFooterAdSettings = (): AuthFooterAdSettings => ({ ...DEFAULT_AUTH_FOOTER_AD_SETTINGS })

export const normalizeAuthFooterAdSettings = (settings?: Partial<SystemSettings> | null): AuthFooterAdSettings => {
  const footerAdHtml = settings?.['auth.footer_ad_html']

  return {
    'auth.footer_ad_html': typeof footerAdHtml === 'string' && footerAdHtml.trim()
      ? footerAdHtml
      : DEFAULT_AUTH_FOOTER_AD_SETTINGS['auth.footer_ad_html'],
  }
}

export const buildAuthFooterAdSettingsPayload = (settings?: Partial<SystemSettings> | null): AuthFooterAdSettings => {
  const normalized = normalizeAuthFooterAdSettings(settings)
  return AUTH_FOOTER_AD_SETTING_KEYS.reduce((payload, key) => {
    payload[key] = normalized[key]
    return payload
  }, {} as AuthFooterAdSettings)
}

export const updateAuthFooterAdSettings = async (settings?: Partial<SystemSettings> | null): Promise<ApiResponse> => {
  return updateSystemSettings(buildAuthFooterAdSettingsPayload(settings) as Partial<SystemSettings>)
}

export const buildThemeAppearanceSettingsPayload = (settings?: Partial<SystemSettings> | null): ThemeAppearanceSettings => {
  const normalized = normalizeThemeAppearanceSettings(settings)
  return {
    'theme.effect': normalized['theme.effect'],
    'theme.color_preset': normalized['theme.color_preset'],
  }
}

export const updateThemeAppearanceSettings = async (settings?: Partial<SystemSettings> | null): Promise<ApiResponse> => {
  const payload = buildThemeAppearanceSettingsPayload(settings)
  const response = await updateSystemSettings(payload as Partial<SystemSettings>)
  if (response.success) {
    dispatchThemeSettingsUpdated(settings)
  }
  return response
}

export const buildThemeFontSettingsPayload = (settings?: Partial<SystemSettings> | null): ThemeFontSettings => {
  const normalized = normalizeThemeFontSettings(settings)
  return {
    'theme.font_family': normalized['theme.font_family'],
  }
}

export const updateThemeFontSettings = async (settings?: Partial<SystemSettings> | null): Promise<ApiResponse> => {
  const payload = buildThemeFontSettingsPayload(settings)
  const response = await updateSystemSettings(payload as Partial<SystemSettings>)
  if (response.success) {
    dispatchThemeSettingsUpdated(settings)
  }
  return response
}

export const parseHiddenMenuKeys = (value: unknown): string[] => {
  if (!value) {
    return []
  }

  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean)
  }

  if (typeof value !== 'string') {
    return []
  }

  const trimmedValue = value.trim()
  if (!trimmedValue) {
    return []
  }

  try {
    const parsed = JSON.parse(trimmedValue)
    if (Array.isArray(parsed)) {
      return parsed.map((item) => String(item).trim()).filter(Boolean)
    }
  } catch {
    return trimmedValue.split(',').map((item) => item.trim()).filter(Boolean)
  }

  return []
}

export const serializeHiddenMenuKeys = (keys: string[]): string => {
  return JSON.stringify(Array.from(new Set(keys.filter(Boolean))))
}

export const getHiddenMenuKeysFromSettings = (settings?: SystemSettings | null): string[] => {
  return parseHiddenMenuKeys(settings?.[MENU_HIDDEN_SETTING_KEY])
}

export const buildHiddenMenuSettingsPayload = (keys: string[]): Partial<SystemSettings> => {
  return {
    [MENU_HIDDEN_SETTING_KEY]: serializeHiddenMenuKeys(keys),
  }
}

// 获取 AI 设置
export const getAISettings = (): Promise<{ success: boolean; data?: Record<string, unknown> }> => {
  return get(AI_SETTINGS_PREFIX)
}

// 更新 AI 设置
export const updateAISettings = (data: Record<string, unknown>): Promise<ApiResponse> => {
  return put(AI_SETTINGS_PREFIX, data)
}

export const testEmailSend = async (email: string): Promise<ApiResponse> => {
  return post(`${SYSTEM_SETTINGS_PREFIX}/test-email?email=${encodeURIComponent(email)}`)
}

// ========== 代理设置（独立保存） ==========

export interface ProxySettingsPayload {
  'proxy.api_url': string
  'proxy.enabled': boolean
}

// 从全局 settings 中提取代理设置，兼容字符串/布尔回读
// enabled 在 BOOLEAN_SYSTEM_SETTING_KEYS 白名单中，convertSystemSettings 会把字符串 'true'/'false' 转成 boolean；
// 但 Partial<SystemSettings> 泛型意义下可能被外部传入未转换的原始值，这里用 unknown 宽泛判断兜底。
export const normalizeProxySettings = (settings?: Partial<SystemSettings> | null): ProxySettingsPayload => {
  const apiUrl = settings?.['proxy.api_url']
  const enabled = settings?.['proxy.enabled'] as unknown
  return {
    'proxy.api_url': typeof apiUrl === 'string' ? apiUrl : '',
    'proxy.enabled': enabled === true || enabled === 'true',
  }
}

// 独立保存代理设置：只提交 proxy.api_url 和 proxy.enabled，不触碰其他设置
// 不复用 updateSystemSettings 的原因：
// 1) 后端对代理做了跨键校验（开启代理时 URL 必须非空；代理启用中不允许清空 URL），
//    Promise.all 并发 PUT 会让后端读到对方未落库的旧值导致误拒
// 2) updateSystemSettings 不检查 PUT 返回的 success 字段，后端校验错误消息无法回传前端
export const updateProxySettings = async (settings?: Partial<SystemSettings> | null): Promise<ApiResponse> => {
  const normalized = normalizeProxySettings(settings)
  const putUrl = (): Promise<ApiResponse> =>
    put<ApiResponse>(`${SYSTEM_SETTINGS_PREFIX}/proxy.api_url`, { value: normalized['proxy.api_url'] })
  const putEnabled = (): Promise<ApiResponse> =>
    put<ApiResponse>(
      `${SYSTEM_SETTINGS_PREFIX}/proxy.enabled`,
      { value: normalized['proxy.enabled'] ? 'true' : 'false' },
    )

  // 按目标状态编排 PUT 顺序，确保后端跨键校验总能通过：
  // - 目标启用：先写 URL（前置条件）再开启开关
  // - 目标禁用：先关闭开关再清空/保留 URL
  const operations = normalized['proxy.enabled'] ? [putUrl, putEnabled] : [putEnabled, putUrl]

  for (const op of operations) {
    try {
      const result = await op()
      if (!result?.success) {
        return result || { success: false, message: '代理设置保存失败' }
      }
    } catch (error) {
      return { success: false, message: (error as Error)?.message || '代理设置保存失败' }
    }
  }

  return { success: true, message: '代理设置已保存' }
}

// ========== 分销设置（独立保存） ==========

// 独立保存分销设置：只提交 distribution.* 相关键，不触碰其他设置
// 与页面右上角"保存设置"按钮分离，避免影响其他未改动的设置
export const updateDistributionSettings = async (settings?: Partial<SystemSettings> | null): Promise<ApiResponse> => {
  const feeType = settings?.['distribution.fee_type']
  const feeRate = settings?.['distribution.fee_rate']

  const payload: Record<string, string> = {
    'distribution.fee_type': typeof feeType === 'string' && feeType ? feeType : 'fixed',
    'distribution.fee_rate': typeof feeRate === 'string' ? feeRate : '',
  }

  for (const [key, value] of Object.entries(payload)) {
    try {
      const result = await put<ApiResponse>(`${SYSTEM_SETTINGS_PREFIX}/${key}`, { value })
      if (!result?.success) {
        return result || { success: false, message: '分销设置保存失败' }
      }
    } catch (error) {
      return { success: false, message: (error as Error)?.message || '分销设置保存失败' }
    }
  }

  return { success: true, message: '分销设置已保存' }
}

// 修改密码
export const changePassword = async (data: { current_password: string; new_password: string }): Promise<ApiResponse> => {
  return post(`${USERS_PREFIX}/change-password`, data)
}

// 获取当前登录用户信息（含到期日）
export interface CurrentUserProfile {
  id: number
  username: string
  email?: string
  phone?: string
  role?: string
  status?: string
  account_limit?: number | null
  last_login_at?: string | null
  expire_at?: string | null
}

export const getCurrentUserProfile = async (): Promise<CurrentUserProfile> => {
  return get(`${USERS_PREFIX}/me`)
}

// 账户续期：按系统设置的续期单价扣减余额并延长到期日
export interface RenewMembershipResult {
  months: number
  unit_price: string
  total: string
  balance_before: string
  balance_after: string
  expire_at: string | null
}

export const renewMembership = async (months: number): Promise<ApiResponse<RenewMembershipResult>> => {
  return post(`${USERS_PREFIX}/renew`, { months })
}

// 获取备份文件列表（管理员）
export const getBackupList = async (): Promise<{ backups: Array<{ filename: string; size: number; size_mb: number; modified_time: string }>; total: number }> => {
  return get(`${ADMIN_PREFIX}/backup/list`)
}

// 下载数据库备份（管理员）
export const downloadDatabaseBackup = (): string => {
  const token = localStorage.getItem('auth_token')
  return `${ADMIN_PREFIX}/backup/download?token=${token}`
}

// 上传数据库备份（管理员）
export const uploadDatabaseBackup = async (file: File): Promise<ApiResponse> => {
  const formData = new FormData()
  formData.append('backup_file', file)
  return post(`${ADMIN_PREFIX}/backup/upload`, formData)
}

// 导出用户备份
export const exportUserBackup = (): string => {
  const token = localStorage.getItem('auth_token')
  return `/api/v1/backup/export?token=${token}`
}

// 导入用户备份
export const importUserBackup = async (file: File): Promise<ApiResponse> => {
  const formData = new FormData()
  formData.append('file', file)
  return post('/api/v1/backup/import', formData)
}

// ========== 用户设置 ==========

// 获取单个用户设置
export const getUserSetting = async (key: string): Promise<{ success: boolean; value?: string }> => {
  try {
    const data = await get<{ value: string }>(`/api/v1/user-settings/${key}`)
    return { success: true, value: data.value }
  } catch {
    return { success: false }
  }
}

// 更新用户设置
export const updateUserSetting = async (key: string, value: string, description?: string): Promise<ApiResponse> => {
  return put(`/api/v1/user-settings/${key}`, { value, description })
}

// 一键创建对接卡密秘钥（后端调用外部密钥服务创建并自动保存到当前用户）
export const createCardSecretKey = async (): Promise<ApiResponse<{ key_value: string }>> => {
  return post('/api/v1/user-settings/card-secret-key/create')
}

// 上传收款码
export const uploadPaymentQrcode = async (file: File, paymentType: 'alipay' | 'wechat'): Promise<{
  success: boolean
  message?: string
  data?: { image_url: string; payment_type: string }
}> => {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('payment_type', paymentType)
  return post('/api/v1/user-settings/payment-qrcode/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}


// ========== 对接码管理 ==========

// 获取对接码
export const getDockCode = async (): Promise<{ success: boolean; dock_code?: string }> => {
  return get(`${USERS_PREFIX}/dock-code`)
}

// 重置对接码
export const resetDockCode = async (): Promise<ApiResponse> => {
  return post(`${USERS_PREFIX}/dock-code/reset`)
}


// ========== 分销秘钥管理 ==========

// 获取分销秘钥（无则自动生成）
export const getSecretKey = async (): Promise<{ success: boolean; secret_key?: string }> => {
  return get(`${USERS_PREFIX}/secret-key`)
}

// 更换分销秘钥
export const resetSecretKey = async (): Promise<ApiResponse<{ secret_key: string }>> => {
  return post(`${USERS_PREFIX}/secret-key/reset`)
}


// ========== 群二维码管理 ==========

// 二维码类型
type QrcodeType = 'wechat' | 'qq' | 'wechat_official' | 'telegram' | 'reward'

// 上传群二维码（管理员）
export const uploadQrcode = async (type: QrcodeType, file: File): Promise<ApiResponse & { data?: { image_url: string } }> => {
  const formData = new FormData()
  formData.append('image', file)
  return post(`/api/v1/qrcode/${type}`, formData, {
    headers: { 'Content-Type': 'multipart/form-data' }
  })
}

// 获取群二维码路径
export const getQrcodeUrl = async (type: QrcodeType): Promise<{ success: boolean; data?: { image_url: string } }> => {
  return get(`/api/v1/qrcode/${type}`)
}
