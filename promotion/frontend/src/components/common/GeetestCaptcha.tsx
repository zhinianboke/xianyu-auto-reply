/**
 * 极验滑动验证码组件
 *
 * 功能：
 * 1. 初始化极验验证码
 * 2. 用户完成滑动后进行二次验证
 * 3. 验证成功后回调父组件
 *
 * 注意：极验的 challenge 是一次性的，每次初始化都需要重新获取
 */
import { useEffect, useRef, useState, useCallback } from 'react'
import request from '@/utils/request'

/** 极验验证结果类型 */
export interface GeetestResult {
  challenge: string
  validate: string
  seccode: string
}

interface GeetestCaptchaProps {
  onSuccess: (result: GeetestResult) => void
  onError?: (error: string) => void
  disabled?: boolean
  buttonText?: string
  className?: string
}

declare global {
  interface Window {
    initGeetest?: (config: any, callback: (captchaObj: any) => void) => void
  }
}

type GeetestInitializer = NonNullable<Window['initGeetest']>
const DEFAULT_GEETEST_SDK_URL = 'https://static.geetest.com/static/tools/gt.js'
const GEETEST_SDK_TIMEOUT_MS = 10000
const geetestScriptLoaders = new Map<string, Promise<GeetestInitializer>>()
let pendingScript: Promise<GeetestInitializer> | undefined
let loadedSdkUrl: string | undefined

/** 加载指定地址的极验脚本，同一地址共用加载结果。 */
async function loadGeetestScript(sdkUrl = DEFAULT_GEETEST_SDK_URL): Promise<GeetestInitializer> {
  let url: URL
  try {
    url = new URL(sdkUrl)
  } catch {
    throw new Error('极验脚本地址无效')
  }
  if (url.protocol !== 'https:' && url.protocol !== 'http:') {
    throw new Error('极验脚本地址无效')
  }
  if (window.location.protocol === 'https:' && url.protocol === 'http:') {
    throw new Error('当前页面需要使用 HTTPS 极验脚本')
  }

  const cached = geetestScriptLoaders.get(url.href)
  if (cached) return cached

  // SDK 通过全局变量暴露初始化函数，不同地址的加载按顺序执行。
  const loader = (pendingScript ?? Promise.resolve()).catch(() => undefined).then(() => {
    const existing = Array.from(document.scripts).find((script) => script.src === url.href)
    const script = existing ?? document.createElement('script')
    const previousInitializer = window.initGeetest
    const canReuseInitializer = existing && (!loadedSdkUrl || loadedSdkUrl === url.href)

    return new Promise<GeetestInitializer>((resolve, reject) => {
      let loaded = Boolean(existing)
      const check = () => {
        const initializer = window.initGeetest
        if (loaded && typeof initializer === 'function' && (canReuseInitializer || initializer !== previousInitializer)) {
          cleanup()
          loadedSdkUrl = url.href
          resolve(initializer)
        }
      }
      const fail = (message: string) => {
        cleanup()
        if (!existing) script.remove()
        reject(new Error(message))
      }
      const onLoad = () => {
        loaded = true
        check()
      }
      const onError = () => fail('极验脚本加载失败')
      const poll = setInterval(check, 50)
      const timeout = setTimeout(() => fail('极验脚本加载或初始化超时'), GEETEST_SDK_TIMEOUT_MS)
      const cleanup = () => {
        clearInterval(poll)
        clearTimeout(timeout)
        script.removeEventListener('load', onLoad)
        script.removeEventListener('error', onError)
      }

      script.addEventListener('load', onLoad)
      script.addEventListener('error', onError)
      if (existing) {
        check()
      } else {
        script.src = url.href
        script.async = true
        document.head.appendChild(script)
      }
    })
  }).catch((error: unknown) => {
    geetestScriptLoaders.delete(url.href)
    throw error
  }).finally(() => {
    if (pendingScript === loader) pendingScript = undefined
  })

  geetestScriptLoaders.set(url.href, loader)
  pendingScript = loader
  return loader
}

/** 获取极验验证码初始化参数 */
const getGeetestRegister = async () => {
  const response = await request.get('/api/v1/geetest/register')
  return response.data
}

/** 极验二次验证 */
const geetestValidate = async (data: { challenge: string; validate: string; seccode: string }) => {
  const response = await request.post('/api/v1/geetest/validate', data)
  return response.data
}

export function GeetestCaptcha({
  onSuccess,
  onError,
  disabled = false,
  buttonText = '点击进行验证',
  className = ''
}: GeetestCaptchaProps) {
  const [status, setStatus] = useState<'loading' | 'ready' | 'verified' | 'error'>('loading')
  const [errorMsg, setErrorMsg] = useState('')
  const captchaObjRef = useRef<any>(null)
  const initedRef = useRef(false)
  const initializationRef = useRef(0)
  const onSuccessRef = useRef(onSuccess)
  const onErrorRef = useRef(onError)

  useEffect(() => {
    onSuccessRef.current = onSuccess
    onErrorRef.current = onError
  }, [onSuccess, onError])

  /** 初始化极验验证码 */
  const init = useCallback(async () => {
    if (initedRef.current) return
    initedRef.current = true
    const initialization = ++initializationRef.current
    const isCurrent = () => initialization === initializationRef.current

    try {
      setStatus('loading')
      setErrorMsg('')

      // 每次初始化都需要获取新的 challenge（challenge 是一次性的）
      const res = await getGeetestRegister()
      if (!isCurrent()) return

      if (!res.success || !res.data) {
        throw new Error(res.message || '获取参数失败')
      }

      const { gt, challenge, success, new_captcha, sdk_url } = res.data
      if (!gt || !challenge) {
        throw new Error('参数不完整')
      }

      const initialize = await loadGeetestScript(sdk_url)
      if (!isCurrent()) return
      initialize.call(
        window,
        {
          gt,
          challenge,
          offline: success === 0,
          new_captcha,
          product: 'bind',
          width: '100%',
          lang: 'zh-cn'
        },
        (obj: any) => {
          if (!isCurrent()) return
          captchaObjRef.current = obj

          obj.onReady(() => {
            if (isCurrent()) setStatus('ready')
          })

          obj.onSuccess(async () => {
            if (!isCurrent()) return
            const result = obj.getValidate()
            if (!result) return

            // 显示验证中状态
            setStatus('loading')

            try {
              const validateRes = await geetestValidate({
                challenge: result.geetest_challenge,
                validate: result.geetest_validate,
                seccode: result.geetest_seccode
              })

              if (!isCurrent()) return

              if (validateRes.success) {
                setStatus('verified')
                onSuccessRef.current({
                  challenge: result.geetest_challenge,
                  validate: result.geetest_validate,
                  seccode: result.geetest_seccode
                })
              } else {
                setErrorMsg(validateRes.message || '验证失败')
                setStatus('error')
                onErrorRef.current?.(validateRes.message || '验证失败')
                obj.reset()
              }
            } catch (err: any) {
              if (!isCurrent()) return
              const errMsg = err.message?.includes('timeout') ? '验证超时，请重试' : '验证异常，请重试'
              setErrorMsg(errMsg)
              setStatus('error')
              onErrorRef.current?.(errMsg)
              obj.reset()
            }
          })

          obj.onError(() => {
            if (isCurrent()) {
              setErrorMsg('加载失败')
              setStatus('error')
              onErrorRef.current?.('加载失败')
            }
          })

          obj.onClose(() => {
            // 用户关闭，不处理
          })
        }
      )
    } catch (err: any) {
      if (isCurrent()) {
        initedRef.current = false
        const msg = err.message || '初始化失败'
        setErrorMsg(msg)
        setStatus('error')
        onErrorRef.current?.(msg)
      }
    }
  }, [])

  useEffect(() => {
    init()
    return () => {
      initializationRef.current++
      captchaObjRef.current = null
      initedRef.current = false
    }
  }, [init])

  /** 点击按钮处理 */
  const handleClick = () => {
    if (disabled) return

    if (status === 'error') {
      initedRef.current = false
      init()
      return
    }

    if (status === 'ready' && captchaObjRef.current) {
      captchaObjRef.current.verify()
    }
  }

  const btnClass = `w-full h-10 px-4 rounded-lg border transition-all duration-200 text-sm font-medium
    ${
      status === 'verified'
        ? 'bg-green-50 border-green-300 text-green-700 dark:bg-green-900/20 dark:border-green-700 dark:text-green-400'
        : status === 'error'
          ? 'bg-red-50 border-red-300 text-red-700 dark:bg-red-900/20 dark:border-red-700 dark:text-red-400 cursor-pointer'
          : 'bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100 dark:bg-slate-800 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-700'
    }
    ${disabled || status === 'loading' ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`

  return (
    <div className={className}>
      <button
        type="button"
        onClick={handleClick}
        disabled={disabled || status === 'loading'}
        className={btnClass}
      >
        {status === 'loading' && (
          <span className="flex items-center justify-center gap-2">
            <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
              <circle
                className="opacity-25"
                cx="12"
                cy="12"
                r="10"
                stroke="currentColor"
                strokeWidth="4"
                fill="none"
              />
              <path
                className="opacity-75"
                fill="currentColor"
                d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
              />
            </svg>
            加载中...
          </span>
        )}
        {status === 'ready' && buttonText}
        {status === 'verified' && (
          <span className="flex items-center justify-center gap-2">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            验证成功
          </span>
        )}
        {status === 'error' && `${errorMsg}，点击重试`}
      </button>
    </div>
  )
}

export default GeetestCaptcha
