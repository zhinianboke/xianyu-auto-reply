/**
 * 广告付款弹窗组件
 * 
 * 功能：
 * 1. 调用后端生成支付宝当面付二维码
 * 2. 展示二维码供用户扫码支付
 * 3. 轮询支付状态，支付成功后自动关闭
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { X, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { createAdPayment, checkAdPaymentStatus } from '@/api/advertisements'
import type { Advertisement } from '@/api/advertisements'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

interface AdPaymentModalProps {
  visible: boolean
  ad: Advertisement | null
  onClose: () => void
  onSuccess: () => void
}

/** 付款步骤 */
type Step = 'confirm' | 'qrcode' | 'success' | 'error'

export function AdPaymentModal({ visible, ad, onClose, onSuccess }: AdPaymentModalProps) {
  const { addToast } = useUIStore()
  const [step, setStep] = useState<Step>('confirm')
  const [loading, setLoading] = useState(false)
  const [qrCode, setQrCode] = useState('')
  const [orderNo, setOrderNo] = useState('')
  const [paymentAmount, setPaymentAmount] = useState('')
  const [advertisementApproved, setAdvertisementApproved] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const closeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const sessionRef = useRef(0)

  /** 清理轮询定时器 */
  const clearPoll = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    if (closeTimerRef.current) {
      clearTimeout(closeTimerRef.current)
      closeTimerRef.current = null
    }
  }, [])

  /** 重置状态 */
  const reset = useCallback(() => {
    sessionRef.current += 1
    setStep('confirm')
    setLoading(false)
    setQrCode('')
    setOrderNo('')
    setPaymentAmount('')
    setAdvertisementApproved(false)
    setErrorMsg('')
    clearPoll()
  }, [clearPoll])

  /** 关闭弹窗 */
  const handleClose = useCallback(() => {
    clearPoll()
    reset()
    onClose()
  }, [clearPoll, reset, onClose])

  /** 切换广告、关闭或卸载后忽略迟到的订单及轮询结果。 */
  useEffect(() => {
    reset()
    return () => { sessionRef.current += 1; clearPoll() }
  }, [visible, ad?.id, reset, clearPoll])

  /** 提交付款 */
  const handleSubmit = async () => {
    if (!visible || !ad || loading) return

    const session = sessionRef.current
    setLoading(true)
    try {
      const result = await createAdPayment(ad.id)
      if (session !== sessionRef.current) return
      if (result.success && result.data?.qr_code && result.data.order_no) {
        setQrCode(result.data.qr_code)
        setOrderNo(result.data.order_no)
        setPaymentAmount(result.data.amount)
        setStep('qrcode')
        startPolling(ad.id, result.data.order_no)
      } else {
        setErrorMsg(result.message || '创建付款订单失败')
        setStep('error')
      }
    } catch (error: unknown) {
      if (session !== sessionRef.current) return
      setErrorMsg(getApiErrorMessage(error, '创建付款订单失败'))
      setStep('error')
    } finally {
      if (session === sessionRef.current) setLoading(false)
    }
  }

  /** 开始轮询支付状态 */
  const startPolling = (adId: number, no: string) => {
    clearPoll()
    const session = sessionRef.current
    let inFlight = false
    pollRef.current = setInterval(async () => {
      if (inFlight || session !== sessionRef.current) return
      inFlight = true
      try {
        const res = await checkAdPaymentStatus(adId, no)
        if (session !== sessionRef.current) return
        if (res.success && res.data?.paid === true) {
          clearPoll()
          setAdvertisementApproved(res.data.status === 'approved')
          setStep('success')
          addToast({ message: '付款成功', type: 'success' })
          // 延迟关闭，让用户看到成功状态
          closeTimerRef.current = setTimeout(() => {
            if (session !== sessionRef.current) return
            onSuccess()
            handleClose()
          }, 1500)
        } else if (!res.success) {
          clearPoll()
          setErrorMsg(res.message || '广告付款状态查询失败')
          setStep('error')
        }
      } catch (error: unknown) {
        if (session !== sessionRef.current) return
        clearPoll()
        setErrorMsg(getApiErrorMessage(error, '广告付款状态查询失败'))
        setStep('error')
      } finally {
        inFlight = false
      }
    }, 3000)
  }

  if (!visible || !ad) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-slate-800 rounded-xl p-6 w-full max-w-md mx-4 shadow-xl">
        {/* 标题栏 */}
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            广告付款
          </h3>
          <button
            onClick={handleClose}
            className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 确认付款步骤 */}
        {step === 'confirm' && (
          <div className="space-y-4">
            <div className="p-4 bg-slate-50 dark:bg-slate-700/50 rounded-lg space-y-2">
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">广告标题</span>
                <span className="font-medium text-slate-900 dark:text-slate-100 max-w-[200px] truncate">{ad.title}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">广告类型</span>
                <span className="font-medium text-slate-900 dark:text-slate-100">{ad.ad_type_label || ad.ad_type}</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">购买月数</span>
                <span className="font-medium text-slate-900 dark:text-slate-100">{ad.months} 个月</span>
              </div>
              <div className="flex justify-between text-sm">
                <span className="text-slate-500">到期日期</span>
                <span className="font-medium text-slate-900 dark:text-slate-100">{ad.expire_date || '-'}</span>
              </div>
              <div className="flex justify-between text-sm pt-2 border-t border-slate-200 dark:border-slate-600">
                <span className="text-slate-500 font-medium">应付金额</span>
                <span className="text-xl font-bold text-amber-600 dark:text-amber-400">¥{ad.total_amount || '0'}</span>
              </div>
            </div>
            <button
              onClick={handleSubmit}
              disabled={loading}
              className="btn-ios-primary w-full"
            >
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  生成支付二维码中...
                </>
              ) : (
                '确认付款'
              )}
            </button>
          </div>
        )}

        {/* 二维码步骤 */}
        {step === 'qrcode' && (
          <div className="space-y-4 text-center">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              请使用支付宝扫描下方二维码完成支付
            </p>
            <div className="flex justify-center">
              <div className="p-4 bg-white rounded-xl inline-block">
                <QRCodeSVG value={qrCode} size={200} />
              </div>
            </div>
            <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">
              ¥{paymentAmount}
            </div>
            <p className="text-xs text-slate-400">
              订单号: {orderNo}
            </p>
            <div className="flex items-center justify-center gap-2 text-sm text-blue-500">
              <Loader2 className="w-4 h-4 animate-spin" />
              等待支付中...
            </div>
          </div>
        )}

        {/* 成功步骤 */}
        {step === 'success' && (
          <div className="space-y-4 text-center py-4">
            <CheckCircle className="w-16 h-16 text-green-500 mx-auto" />
            <p className="text-lg font-semibold text-green-600 dark:text-green-400">
              付款成功
            </p>
            <p className="text-sm text-slate-500">
              {advertisementApproved ? '广告已自动复核通过' : '付款已确认，请在列表查看广告复核状态'}
            </p>
          </div>
        )}

        {/* 错误步骤 */}
        {step === 'error' && (
          <div className="space-y-4 text-center py-4">
            <AlertCircle className="w-16 h-16 text-red-500 mx-auto" />
            <p className="text-lg font-semibold text-red-600 dark:text-red-400">
              付款失败
            </p>
            <p className="text-sm text-slate-500">{errorMsg}</p>
            <button onClick={reset} className="btn-ios-secondary">
              重试
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
