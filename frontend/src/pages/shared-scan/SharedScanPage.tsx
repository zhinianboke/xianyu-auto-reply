/**
 * 共享多人扫码登录 - 兼职端公开页面
 *
 * 功能：
 * 1. 无需登录，通过 URL 参数 session_id 访问
 * 2. 自动加入共享会话，生成独立的闲鱼二维码
 * 3. 轮询扫码状态，成功后显示完成提示
 */
import { useEffect, useRef, useState } from 'react'
import { AlertCircle, CheckCircle, Loader2, QrCode, RefreshCw, Smartphone } from 'lucide-react'
import { joinSharedSession, getWorkerStatus } from '@/api/sharedScan'

type PageStatus = 'loading' | 'qrcode_ready' | 'scanning' | 'verification_required' | 'success' | 'failed' | 'error'

function createVisitorToken() {
  if (typeof window.crypto?.randomUUID === 'function') {
    return window.crypto.randomUUID()
  }

  if (typeof window.crypto?.getRandomValues === 'function') {
    const bytes = window.crypto.getRandomValues(new Uint8Array(16))
    bytes[6] = (bytes[6] & 0x0f) | 0x40
    bytes[8] = (bytes[8] & 0x3f) | 0x80
    const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, '0'))
    return [
      `${hex[0]}${hex[1]}${hex[2]}${hex[3]}`,
      `${hex[4]}${hex[5]}`,
      `${hex[6]}${hex[7]}`,
      `${hex[8]}${hex[9]}`,
      `${hex[10]}${hex[11]}${hex[12]}${hex[13]}${hex[14]}${hex[15]}`,
    ].join('-')
  }

  return `shared-scan-${Date.now()}-${Math.random().toString(16).slice(2)}${Math.random().toString(16).slice(2)}`
}

export function SharedScanPage() {
  const [sessionId, setSessionId] = useState('')
  const [subSessionId, setSubSessionId] = useState('')
  const [qrcodeUrl, setQrcodeUrl] = useState('')
  const [faceQrUrl, setFaceQrUrl] = useState('')
  const [status, setStatus] = useState<PageStatus>('loading')
  const [errorMessage, setErrorMessage] = useState('')
  const pollTimer = useRef<ReturnType<typeof setInterval> | null>(null)
  const visitorTokenRef = useRef('')

  if (!visitorTokenRef.current) {
    const existingToken = window.sessionStorage.getItem('shared_scan_visitor_token') || ''
    if (existingToken) {
      visitorTokenRef.current = existingToken
    } else {
      const newToken = createVisitorToken()
      window.sessionStorage.setItem('shared_scan_visitor_token', newToken)
      visitorTokenRef.current = newToken
    }
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const sid = params.get('session_id') || ''
    if (!sid) {
      setStatus('error')
      setErrorMessage('链接无效，缺少 session_id 参数')
      return
    }
    setSessionId(sid)
    joinSession(sid)
    return () => stopPoll()
  }, [])

  // 扫码状态轮询：subSessionId 建立后持续轮询，直到终止状态
  useEffect(() => {
    if (!subSessionId) return
    if (status === 'success' || status === 'failed' || status === 'error') return
    pollTimer.current = setInterval(() => pollStatus(), 2000)
    return () => stopPoll()
  }, [subSessionId])

  const stopPoll = () => {
    if (pollTimer.current) {
      clearInterval(pollTimer.current)
      pollTimer.current = null
    }
  }

  const joinSession = async (sid: string, forceRefresh = false) => {
    setStatus('loading')
    try {
      const res = await joinSharedSession({
        sessionId: sid,
        visitorToken: visitorTokenRef.current,
        forceRefresh,
      })
      if (res.success && res.data) {
        setSubSessionId(res.data.sub_session_id)
        setQrcodeUrl(res.data.qrcode_data_url)
        setStatus('qrcode_ready')
      } else {
        setStatus('error')
        setErrorMessage(res.message || '加入会话失败，请检查链接是否有效')
      }
    } catch {
      setStatus('error')
      setErrorMessage('网络错误，请稍后重试')
    }
  }

  const pollStatus = async () => {
    if (!subSessionId) return
    try {
      const res = await getWorkerStatus(subSessionId)
      if (!res.success) {
        stopPoll()
        setStatus('error')
        setErrorMessage(res.message || '查询扫码状态失败，请稍后重试')
        return
      }
      const s = res.data?.status
      if (s === 'scanning') {
        setStatus('scanning')
      } else if (s === 'verification_required') {
        // 触发人脸验证：展示人脸二维码，保持轮询直到用户手机完成后过渡到 success
        setStatus('verification_required')
        if (res.data?.face_qr_url) setFaceQrUrl(res.data.face_qr_url)
      } else if (s === 'success') {
        stopPoll()
        setStatus('success')
      } else if (s === 'failed') {
        stopPoll()
        setErrorMessage(res.data?.message || res.message || '二维码已失效，请点击重试重新获取')
        setStatus('failed')
      }
    } catch {
      // 静默失败，继续轮询
    }
  }

  const handleRetry = () => {
    stopPoll()
    setSubSessionId('')
    setQrcodeUrl('')
    setFaceQrUrl('')
    if (sessionId) {
      joinSession(sessionId, true)
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-600 via-blue-500 to-indigo-600 flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-white dark:bg-slate-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* 顶部标题栏 */}
        <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-5 text-white text-center">
          <div className="flex items-center justify-center gap-2 mb-1">
            <Smartphone className="w-5 h-5" />
            <h1 className="text-lg font-bold">闲鱼账号扫码登录</h1>
          </div>
          <p className="text-blue-100 text-sm">使用闲鱼 APP 扫描下方二维码</p>
        </div>

        {/* 内容区域 */}
        <div className="p-6">
          {/* 加载中 */}
          {status === 'loading' && (
            <div className="flex flex-col items-center py-10 gap-4">
              <Loader2 className="w-12 h-12 text-blue-500 animate-spin" />
              <p className="text-slate-600 dark:text-slate-400">正在生成二维码，请稍候...</p>
            </div>
          )}

          {/* 显示二维码 */}
          {(status === 'qrcode_ready' || status === 'scanning') && (
            <div className="flex flex-col items-center gap-4">
              <div className="relative w-56 h-56 border-2 border-dashed border-blue-300 dark:border-blue-700 rounded-xl overflow-hidden bg-white flex items-center justify-center">
                {qrcodeUrl ? (
                  <img src={qrcodeUrl} alt="扫码登录" className="w-full h-full object-contain p-2" />
                ) : (
                  <QrCode className="w-16 h-16 text-blue-300" />
                )}
                {/* 扫描中遮罩 */}
                {status === 'scanning' && (
                  <div className="absolute inset-0 bg-white/80 dark:bg-slate-800/80 flex flex-col items-center justify-center gap-2">
                    <Smartphone className="w-10 h-10 text-green-500 animate-pulse" />
                    <p className="text-sm font-medium text-green-600">已扫码，请在手机上确认</p>
                  </div>
                )}
              </div>

              {status === 'qrcode_ready' && (
                <>
                  <p className="text-sm text-slate-600 dark:text-slate-400 text-center">
                    打开闲鱼 APP → 点击右上角 <strong>+</strong> → 选择<strong>扫一扫</strong>
                  </p>
                  <button
                    onClick={handleRetry}
                    className="flex items-center gap-1.5 text-sm text-blue-500 hover:text-blue-600 transition-colors"
                  >
                    <RefreshCw className="w-4 h-4" />
                    刷新二维码
                  </button>
                </>
              )}
            </div>
          )}

          {/* 人脸验证 */}
          {status === 'verification_required' && (
            <div className="flex flex-col items-center gap-4">
              <p className="text-base font-semibold text-amber-600 dark:text-amber-400">需要人脸验证</p>
              <div className="relative w-56 h-56 border-2 border-dashed border-amber-300 dark:border-amber-700 rounded-xl overflow-hidden bg-white flex items-center justify-center">
                {faceQrUrl ? (
                  <img src={faceQrUrl} alt="人脸验证二维码" className="w-full h-full object-contain p-2" />
                ) : (
                  <div className="flex flex-col items-center gap-2">
                    <Loader2 className="w-10 h-10 text-amber-500 animate-spin" />
                    <p className="text-xs text-slate-400">正在获取人脸验证二维码…</p>
                  </div>
                )}
              </div>
              <p className="text-sm text-slate-600 dark:text-slate-400 text-center">
                请使用闲鱼 APP 扫描二维码，按提示完成人脸验证
              </p>
              <div className="flex items-center gap-1.5 text-blue-500 text-xs">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                <span>验证完成后将自动登录，请勿关闭页面</span>
              </div>
            </div>
          )}

          {/* 登录成功 */}
          {status === 'success' && (
            <div className="flex flex-col items-center py-8 gap-4 text-center">
              <div className="w-20 h-20 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                <CheckCircle className="w-12 h-12 text-green-500" />
              </div>
              <div>
                <p className="text-xl font-bold text-green-600 dark:text-green-400 mb-1">登录成功！</p>
                <p className="text-sm text-slate-500 dark:text-slate-400">您的闲鱼账号已成功添加到系统中</p>
              </div>
              <button
                onClick={() => window.close()}
                className="px-6 py-2 bg-green-500 hover:bg-green-600 text-white rounded-lg text-sm font-medium transition-colors"
              >
                关闭页面
              </button>
            </div>
          )}

          {/* 登录失败 */}
          {status === 'failed' && (
            <div className="flex flex-col items-center py-8 gap-4 text-center">
              <div className="w-20 h-20 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                <AlertCircle className="w-12 h-12 text-red-500" />
              </div>
              <div>
                <p className="text-xl font-bold text-red-600 dark:text-red-400 mb-1">登录失败</p>
                <p className="text-sm text-slate-500 dark:text-slate-400">{errorMessage || '二维码已失效，请点击重试重新获取'}</p>
              </div>
              <button
                onClick={handleRetry}
                className="flex items-center gap-1.5 px-6 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg text-sm font-medium transition-colors"
              >
                <RefreshCw className="w-4 h-4" />
                重新获取二维码
              </button>
            </div>
          )}

          {/* 错误状态 */}
          {status === 'error' && (
            <div className="flex flex-col items-center py-8 gap-4 text-center">
              <div className="w-20 h-20 rounded-full bg-orange-100 dark:bg-orange-900/30 flex items-center justify-center">
                <AlertCircle className="w-12 h-12 text-orange-500" />
              </div>
              <div>
                <p className="text-xl font-bold text-slate-700 dark:text-slate-300 mb-1">出错了</p>
                <p className="text-sm text-slate-500 dark:text-slate-400">{errorMessage}</p>
              </div>
              {sessionId && (
                <button
                  onClick={handleRetry}
                  className="flex items-center gap-1.5 px-6 py-2 bg-blue-500 hover:bg-blue-600 text-white rounded-lg text-sm font-medium transition-colors"
                >
                  <RefreshCw className="w-4 h-4" />
                  重试
                </button>
              )}
            </div>
          )}
        </div>

        {/* 底部提示 */}
        <div className="px-6 py-3 bg-slate-50 dark:bg-slate-700/50 border-t border-slate-100 dark:border-slate-700">
          <p className="text-xs text-slate-400 dark:text-slate-500 text-center">
            本页面仅用于扫码登录闲鱼账号，不会收集您的隐私信息
          </p>
        </div>
      </div>
    </div>
  )
}
