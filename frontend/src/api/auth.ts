import { post, get } from '@/utils/request'
import type { LoginRequest, LoginResponse, ApiResponse } from '@/types'

// 用户登录
export const login = (data: LoginRequest): Promise<LoginResponse> => {
  return post('/login', data)
}

// 验证 Token
export const verifyToken = (): Promise<{ authenticated: boolean; user_id?: number; username?: string; is_admin?: boolean }> => {
  return get('/verify')
}

// 用户登出
export const logout = (): Promise<ApiResponse> => {
  return post('/logout')
}

// 获取注册状态
export const getRegistrationStatus = (): Promise<{ enabled: boolean }> => {
  return get('/registration-status')
}

// 获取登录信息显示状态
export const getLoginInfoStatus = (): Promise<{ enabled: boolean }> => {
  return get('/login-info-status')
}

// 生成图形验证码
export const generateCaptcha = (sessionId: string): Promise<{ success: boolean; captcha_image?: string }> => {
  return post('/generate-captcha', { session_id: sessionId })
}

// 验证图形验证码
export const verifyCaptcha = (sessionId: string, captchaCode: string): Promise<{ success: boolean }> => {
  return post('/verify-captcha', { session_id: sessionId, captcha_code: captchaCode })
}

// 发送邮箱验证码
export const sendVerificationCode = (email: string, type: string, sessionId: string): Promise<ApiResponse> => {
  return post('/send-verification-code', { email, type, session_id: sessionId })
}

// 用户注册
export const register = (data: { 
  username: string
  password: string
  email: string
  verification_code: string
  session_id: string
}): Promise<ApiResponse> => {
  return post('/register', data)
}
