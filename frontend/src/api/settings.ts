import { get, put, post } from '@/utils/request'
import type { ApiResponse, SystemSettings } from '@/types'

// 获取系统设置
export const getSystemSettings = async (): Promise<{ success: boolean; data?: SystemSettings }> => {
  const data = await get<Record<string, unknown>>('/system-settings')
  // 将字符串 'true'/'false' 转换为布尔值
  const booleanFields = ['registration_enabled', 'show_default_login_info', 'login_captcha_enabled', 'smtp_use_tls', 'smtp_use_ssl']
  const converted: SystemSettings = {}
  for (const [key, value] of Object.entries(data)) {
    if (booleanFields.includes(key)) {
      converted[key] = value === true || value === 'true'
    } else {
      converted[key] = value
    }
  }
  return { success: true, data: converted }
}

// 更新系统设置
export const updateSystemSettings = async (data: Partial<SystemSettings>): Promise<ApiResponse> => {
  // 逐个更新设置项，确保 value 是字符串
  const promises = Object.entries(data).map(([key, value]) => {
    // 将布尔值和数字转换为字符串
    const stringValue = typeof value === 'boolean' ? (value ? 'true' : 'false') 
                      : typeof value === 'number' ? String(value)
                      : value
    return put(`/system-settings/${key}`, { value: stringValue })
  })
  await Promise.all(promises)
  return { success: true, message: '设置已保存' }
}

// 获取 AI 设置
export const getAISettings = (): Promise<{ success: boolean; data?: Record<string, unknown> }> => {
  return get('/ai-reply-settings')
}

// 更新 AI 设置
export const updateAISettings = (data: Record<string, unknown>): Promise<ApiResponse> => {
  return put('/ai-reply-settings', data)
}

// 测试 AI 连接 - 需要指定 cookie_id
export const testAIConnection = async (cookieId?: string): Promise<ApiResponse> => {
  if (!cookieId) {
    return { success: false, message: '请先选择一个账号进行测试' }
  }
  try {
    const result = await post<{ success?: boolean; message?: string; reply?: string }>(`/ai-reply-test/${cookieId}`, {
      message: '你好，这是一条测试消息'
    })
    if (result.reply) {
      return { success: true, message: `AI 回复: ${result.reply}` }
    }
    return { success: result.success ?? true, message: result.message || 'AI 连接测试成功' }
  } catch (error) {
    return { success: false, message: 'AI 连接测试失败' }
  }
}

// 获取邮件设置
export const getEmailSettings = (): Promise<{ success: boolean; data?: Record<string, unknown> }> => {
  return get('/system-settings')
}

// 更新邮件设置
export const updateEmailSettings = (data: Record<string, unknown>): Promise<ApiResponse> => {
  const promises = Object.entries(data).map(([key, value]) => 
    put(`/system-settings/${key}`, { value })
  )
  return Promise.all(promises).then(() => ({ success: true, message: '设置已保存' }))
}

// TODO: 测试邮件发送功能需要后端支持 type: 'test' 参数
// 当前后端的 /send-verification-code 接口只支持 'register' 和 'login' 类型
export const testEmailSend = async (_email: string): Promise<ApiResponse> => {
  return { success: false, message: '邮件测试功能暂未实现，请检查 SMTP 配置后直接保存' }
}

// 修改密码
export const changePassword = async (data: { current_password: string; new_password: string }): Promise<ApiResponse> => {
  return post('/change-password', data)
}

// 获取备份文件列表（管理员）
export const getBackupList = async (): Promise<{ backups: Array<{ filename: string; size: number; size_mb: number; modified_time: string }>; total: number }> => {
  return get('/admin/backup/list')
}

// 下载数据库备份（管理员）
export const downloadDatabaseBackup = (): string => {
  const token = localStorage.getItem('auth_token')
  return `/admin/backup/download?token=${token}`
}

// 上传数据库备份（管理员）
export const uploadDatabaseBackup = async (file: File): Promise<ApiResponse> => {
  const formData = new FormData()
  formData.append('backup_file', file)
  return post('/admin/backup/upload', formData)
}

// 刷新系统缓存
export const reloadSystemCache = async (): Promise<ApiResponse> => {
  return post('/admin/reload-cache')
}

// 导出用户备份
export const exportUserBackup = (): string => {
  const token = localStorage.getItem('auth_token')
  return `/backup/export?token=${token}`
}

// 导入用户备份
export const importUserBackup = async (file: File): Promise<ApiResponse> => {
  const formData = new FormData()
  formData.append('file', file)
  return post('/backup/import', formData)
}
