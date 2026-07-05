/**
 * 共享多人扫码登录 API
 *
 * 管理员端：创建会话、查询状态、删除会话
 * 兼职端：加入会话、轮询扫码状态
 */
import { get, post, del } from '@/utils/request'

const PREFIX = '/api/v1/shared-scan'

// ==================== 类型定义 ====================

export interface SharedScanSessionItem {
  session_id: string
  status: 'active' | 'closed'
  share_url: string
  expires_at: string
  created_at: string
  worker_count: number
  success_count: number
}

export interface SharedScanWorker {
  sub_session_id: string
  status: 'qrcode_ready' | 'scanning' | 'success' | 'failed'
  account_id?: string
  cookie_saved: boolean
  joined_at: number
}

export interface CreateSessionResponse {
  session_id: string
  share_url: string
  expires_at: string
}

export interface JoinSessionResponse {
  sub_session_id: string
  qrcode_data_url: string
}

export interface JoinSharedSessionParams {
  sessionId: string
  visitorToken?: string
  forceRefresh?: boolean
}

export interface WorkerStatusResponse {
  status: 'qrcode_ready' | 'scanning' | 'verification_required' | 'success' | 'failed'
  account_id?: string
  message?: string
  /** 触发人脸验证时的人脸二维码(base64 data-url) */
  face_qr_url?: string
}

// ==================== 管理员接口 ====================

/** 创建共享扫码登录会话 */
export const createSharedSession = async (): Promise<{ success: boolean; message: string; data?: CreateSessionResponse }> => {
  return post(`${PREFIX}/create`, {})
}

/** 获取当前用户的共享会话列表 */
export const listSharedSessions = async (): Promise<{ success: boolean; message?: string; data?: { sessions: SharedScanSessionItem[] } }> => {
  return get(`${PREFIX}/list`)
}

/** 查询共享会话下所有兼职的实时状态 */
export const getSharedSessionStatus = async (sessionId: string): Promise<{ success: boolean; data?: { session_id: string; session_status: string; part_time_workers: SharedScanWorker[] } }> => {
  return get(`${PREFIX}/status?session_id=${sessionId}`)
}

/** 删除共享会话 */
export const deleteSharedSession = async (sessionId: string): Promise<{ success: boolean; message: string }> => {
  return del(`${PREFIX}/${sessionId}`)
}

// ==================== 兼职端接口（无需登录） ====================

/** 兼职加入共享会话，获取独立二维码 */
export const joinSharedSession = async ({
  sessionId,
  visitorToken,
  forceRefresh = false,
}: JoinSharedSessionParams): Promise<{ success: boolean; message: string; data?: JoinSessionResponse }> => {
  const response = await fetch(`${PREFIX}/join`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      visitor_token: visitorToken,
      force_refresh: forceRefresh,
    }),
  })
  return response.json()
}

/** 兼职轮询自己的扫码状态 */
export const getWorkerStatus = async (subSessionId: string): Promise<{ success: boolean; message?: string; data?: WorkerStatusResponse }> => {
  const response = await fetch(`${PREFIX}/worker-status?sub_session_id=${subSessionId}`)
  return response.json()
}
