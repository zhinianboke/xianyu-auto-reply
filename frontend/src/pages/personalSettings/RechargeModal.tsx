/**
 * 充值弹窗组件
 * 
 * 功能：
 * 1. 输入充值金额
 * 2. 调用后端生成支付宝当面付二维码
 * 3. 展示二维码供用户扫码支付
 * 4. 轮询支付状态，支付成功后自动关闭
 */
import { useState, useEffect, useRef, useCallback } from 'react'
import { X, Loader2, CheckCircle, AlertCircle } from 'lucide-react'
import { QRCodeSVG } from 'qrcode.react'
import { createRecharge, getPaymentOptions, getRechargeStatus, type PaymentOption, type PaymentOptions } from '@/api/payment'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

interface RechargeModalProps {
  visible: boolean
  onClose: () => void
  onSuccess: () => void
}

/** 充值步骤 */
type Step = 'input' | 'qrcode' | 'success' | 'error'

export function RechargeModal({ visible, onClose, onSuccess }: RechargeModalProps) {
  const { addToast } = useUIStore()
  const [step, setStep] = useState<Step>('input')
  const [amount, setAmount] = useState('')
  const [loading, setLoading] = useState(false)
  const [qrCode, setQrCode] = useState('')
  const [orderNo, setOrderNo] = useState('')
  const [errorMsg, setErrorMsg] = useState('')
  const [paymentOptions, setPaymentOptions] = useState<PaymentOptions | null>(null)
  const [selectedPayType, setSelectedPayType] = useState<PaymentOption['value'] | ''>('')
  const [payUrl, setPayUrl] = useState('')
  const [optionsLoading, setOptionsLoading] = useState(false)
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
    setStep('input')
    setAmount('')
    setLoading(false)
    setQrCode('')
    setOrderNo('')
    setErrorMsg('')
    setPaymentOptions(null)
    setSelectedPayType('')
    setPayUrl('')
    setOptionsLoading(false)
    clearPoll()
  }, [clearPoll])

  /** 关闭弹窗 */
  const handleClose = useCallback(() => {
    clearPoll()
    reset()
    onClose()
  }, [clearPoll, reset, onClose])

  const loadPaymentOptions = useCallback(async (session = sessionRef.current) => {
    setOptionsLoading(true)
    try {
      const result = await getPaymentOptions()
      if (session !== sessionRef.current) return
      if (!result.success || !result.data) {
        setErrorMsg(result.message || '加载支付方式失败')
        setStep('error')
        return
      }
      setPaymentOptions(result.data)
      if (result.data.pay_types.length === 1) setSelectedPayType(result.data.pay_types[0].value)
    } catch (error: unknown) {
      if (session !== sessionRef.current) return
      setErrorMsg(getApiErrorMessage(error, '加载支付方式失败，请稍后重试'))
      setStep('error')
    } finally {
      if (session === sessionRef.current) setOptionsLoading(false)
    }
  }, [])

  useEffect(() => {
    reset()
    if (visible) void loadPaymentOptions(sessionRef.current)
    return () => { sessionRef.current += 1; clearPoll() }
  }, [visible, reset, clearPoll, loadPaymentOptions])

  /** 提交充值 */
  const handleSubmit = async () => {
    if (!visible || !amount || loading) return

    const num = parseFloat(amount)
    if (isNaN(num) || num <= 0) {
      addToast({ message: '请输入有效的充值金额', type: 'error' })
      return
    }
    if (num > 10000) {
      addToast({ message: '单次充值金额不能超过10000元', type: 'error' })
      return
    }

    const session = sessionRef.current
    setLoading(true)
    try {
      const result = await createRecharge(amount, selectedPayType || undefined)
      if (session !== sessionRef.current) return
      if (result.success && result.data?.order_no) {
        setAmount(result.data.amount)
        setQrCode(result.data.qr_code || '')
        setPayUrl(result.data.pay_url || '')
        setOrderNo(result.data.order_no)
        if (result.data.status === 'paid') {
          setStep('success')
          addToast({ message: '充值成功', type: 'success' })
          closeTimerRef.current = setTimeout(() => {
            if (session !== sessionRef.current) return
            onSuccess()
            handleClose()
          }, 1500)
          return
        }
        if (result.data.status === 'failed' || result.data.status === 'expired') {
          const message = result.data.status === 'expired' ? '支付订单已过期，请重新充值' : '支付订单已失败，请重新充值'
          setErrorMsg(message)
          setStep('error')
          return
        }
        if (result.data.status !== 'pending') {
          setErrorMsg('充值订单状态异常，请重新充值或联系管理员')
          setStep('error')
          return
        }
        if (!result.data.qr_code && !result.data.pay_url) {
          setErrorMsg('支付服务未返回二维码或支付链接，请重新充值或联系管理员')
          setStep('error')
          return
        }
        setStep('qrcode')
        startPolling(result.data.order_no)
      } else {
        setErrorMsg(result.message || '创建充值订单失败')
        setStep('error')
      }
    } catch (error: unknown) {
      if (session !== sessionRef.current) return
      setErrorMsg(getApiErrorMessage(error, '创建充值订单失败，请稍后重试'))
      setStep('error')
    } finally {
      if (session === sessionRef.current) setLoading(false)
    }
  }

  /** 开始轮询支付状态 */
  const startPolling = (no: string) => {
    clearPoll()
    const session = sessionRef.current
    let inFlight = false
    pollRef.current = setInterval(async () => {
      if (inFlight || session !== sessionRef.current) return
      inFlight = true
      try {
        const res = await getRechargeStatus(no)
        if (session !== sessionRef.current) return
        if (res.success && res.data?.status === 'paid') {
          clearPoll()
          setAmount(res.data.amount)
          setStep('success')
          addToast({ message: '充值成功', type: 'success' })
          // 延迟关闭，让用户看到成功状态
          closeTimerRef.current = setTimeout(() => {
            if (session !== sessionRef.current) return
            onSuccess()
            handleClose()
          }, 1500)
        } else if (res.success && (res.data?.status === 'failed' || res.data?.status === 'expired')) {
          clearPoll()
          const message = res.data.status === 'expired' ? '支付订单已过期，请重新充值' : '支付订单已失败，请重新充值'
          setErrorMsg(message)
          setStep('error')
          addToast({ message, type: 'error' })
        } else if (res.success && res.data?.status === 'pending') {
          if (res.data.amount) setAmount(res.data.amount)
        } else if (res.success) {
          clearPoll()
          const message = res.data ? '支付订单状态异常，请重新充值或稍后查看余额' : '支付订单状态数据异常，请重新充值或稍后查看余额'
          setErrorMsg(message)
          setStep('error')
          addToast({ message, type: 'error' })
        } else if (!res.success) {
          clearPoll()
          const message = res.message || '查询支付结果失败，请重新充值或稍后查看余额'
          setErrorMsg(message)
          setStep('error')
          addToast({ message, type: 'error' })
        }
      } catch (error: unknown) {
        if (session !== sessionRef.current) return
        clearPoll()
        const message = getApiErrorMessage(error, '查询支付结果失败，请重新充值或稍后查看余额')
        setErrorMsg(message)
        setStep('error')
        addToast({ message, type: 'error' })
      } finally {
        inFlight = false
      }
    }, 3000)
  }

  if (!visible) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white dark:bg-slate-800 rounded-xl p-6 w-full max-w-md mx-4 shadow-xl">
        {/* 标题栏 */}
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
            余额充值
          </h3>
          <button
            onClick={handleClose}
            className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* 输入金额步骤 */}
        {step === 'input' && (
          <div className="space-y-4">
            <div className="input-group">
              <label className="input-label">充值金额（元）</label>
              <input
                type="text"
                value={amount}
                onChange={(e) => {
                  const val = e.target.value
                  if (val === '' || /^\d*\.?\d{0,2}$/.test(val)) {
                    setAmount(val)
                  }
                }}
                placeholder="请输入充值金额"
                className="input-ios text-lg"
                autoFocus
              />
            </div>
            {paymentOptions?.pay_types && paymentOptions.pay_types.length > 1 && (
              <div className="input-group">
                <label className="input-label">支付方式</label>
                <div className="flex flex-wrap gap-2">
                  {paymentOptions.pay_types.map((item) => <button key={item.value} type="button" onClick={() => setSelectedPayType(item.value)} className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${selectedPayType === item.value ? 'border-[rgb(var(--color-primary))] bg-[rgb(var(--color-primary-light))] text-[rgb(var(--color-primary))]' : 'border-slate-200 dark:border-slate-700'}`}>{item.label}</button>)}
                </div>
              </div>
            )}
            {/* 快捷金额 */}
            <div className="flex flex-wrap gap-2">
              {['10', '20', '50', '100', '200', '500'].map((v) => (
                <button
                  key={v}
                  onClick={() => setAmount(v)}
                  className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                    amount === v
                      ? 'bg-blue-500 text-white'
                      : 'bg-slate-100 dark:bg-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-600'
                  }`}
                >
                  ¥{v}
                </button>
              ))}
            </div>
            <button
              onClick={handleSubmit}
              disabled={!amount || loading || optionsLoading || !paymentOptions || (paymentOptions.pay_types.length > 1 && !selectedPayType)}
              className="btn-ios-primary w-full"
            >
              {loading || optionsLoading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  {optionsLoading ? '加载支付方式中...' : '创建支付订单中...'}
                </>
              ) : (
                '确认充值'
              )}
            </button>
          </div>
        )}

        {/* 二维码步骤 */}
        {step === 'qrcode' && (
          <div className="space-y-4 text-center">
            <p className="text-sm text-slate-500 dark:text-slate-400">
              {payUrl ? '请点击下方按钮打开支付页面并完成支付' : `请使用${paymentOptions?.channel_label || '对应应用'}扫描下方二维码完成支付`}
            </p>
            {qrCode && <div className="flex justify-center">
              <div className="p-4 bg-white rounded-xl inline-block">
                <QRCodeSVG value={qrCode} size={200} />
              </div>
            </div>}
            {payUrl && <button type="button" onClick={() => window.open(payUrl, '_blank', 'noopener,noreferrer')} className="btn-ios-primary mx-auto">打开支付页面</button>}
            <div className="text-2xl font-bold text-amber-600 dark:text-amber-400">
              ¥{amount}
            </div>
            {paymentOptions?.channel === 'zzcode' && qrCode && <p className="text-sm font-medium text-amber-600 dark:text-amber-400">请按以上金额完成支付</p>}
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
              充值成功
            </p>
            <p className="text-sm text-slate-500">
              ¥{amount} 已充入账户余额
            </p>
          </div>
        )}

        {/* 错误步骤 */}
        {step === 'error' && (
          <div className="space-y-4 text-center py-4">
            <AlertCircle className="w-16 h-16 text-red-500 mx-auto" />
            <p className="text-lg font-semibold text-red-600 dark:text-red-400">
              充值失败
            </p>
            <p className="text-sm text-slate-500">{errorMsg}</p>
            <button onClick={() => { reset(); void loadPaymentOptions() }} className="btn-ios-secondary">
              重新充值
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
