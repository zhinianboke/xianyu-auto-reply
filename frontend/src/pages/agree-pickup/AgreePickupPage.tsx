/**
 * 同意后发货 - 买家提货页（无需登录的公开页面）
 *
 * 功能：
 * 1. 无需登录，通过 URL 参数 orderNo(订单号) + orderId(订单主键) 访问
 * 2. 加载时校验订单：不存在 / 订单号与订单id不匹配 均在界面明确提示
 * 3. 校验通过展示订单信息 + 「同意」按钮，点击后触发发货并展示卡券内容
 * 4. 并发由后端 Redis 发货锁保证，前端点击后禁用按钮防重复提交
 * 5. 提货内容支持一键复制（复用公共剪贴板工具，兼容买家在 HTTP 环境下打开）
 * 6. 展示商品标题与规格，商品标题可点击跳转闲鱼商品详情页
 */
import { useEffect, useState } from 'react'
import { AlertCircle, Check, CheckCircle, Copy, ExternalLink, Loader2, PackageCheck, ShieldCheck } from 'lucide-react'
import { agreePickup, queryPickupOrder, type PickupOrderView } from '@/api/agreePickup'
import { copyToClipboard } from '@/utils/clipboard'
import { useUIStore } from '@/store/uiStore'

type PageStatus = 'loading' | 'ready' | 'already_agreed' | 'success' | 'invalid'

export function AgreePickupPage() {
  const { addToast } = useUIStore()
  const [status, setStatus] = useState<PageStatus>('loading')
  const [errorMessage, setErrorMessage] = useState('')
  const [order, setOrder] = useState<PickupOrderView | null>(null)
  const [content, setContent] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [tip, setTip] = useState('')
  const [copied, setCopied] = useState(false)

  const [orderNo, setOrderNo] = useState('')
  const [orderId, setOrderId] = useState('')

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const no = params.get('orderNo') || ''
    const id = params.get('orderId') || ''
    if (!no || !id) {
      setStatus('invalid')
      setErrorMessage('链接无效，缺少订单参数')
      return
    }
    setOrderNo(no)
    setOrderId(id)
    loadOrder(no, id)
  }, [])

  // 加载并校验订单
  const loadOrder = async (no: string, id: string) => {
    setStatus('loading')
    const res = await queryPickupOrder(no, id)
    if (!res.success || !res.data) {
      setStatus('invalid')
      setErrorMessage(res.message || '订单校验失败')
      return
    }
    setOrder(res.data)
    if (res.data.already_agreed) {
      setContent(res.data.content)
      setStatus('already_agreed')
    } else {
      setStatus('ready')
    }
  }

  // 点击「同意」触发发货
  const handleAgree = async () => {
    if (submitting) return
    setSubmitting(true)
    setTip('')
    const res = await agreePickup(orderNo, orderId)
    if (res.success) {
      setContent(res.data?.content ?? null)
      setStatus('success')
    } else {
      // 失败保持在当前界面，展示后端返回的中文提示，允许重试
      setTip(res.message || '发货失败，请稍后重试或联系卖家')
      setSubmitting(false)
    }
  }

  // 复制提货内容（买家常在 HTTP 环境打开，走公共工具自动兼容 execCommand 方案）
  const handleCopyContent = async () => {
    if (!content) return
    const ok = await copyToClipboard(content)
    if (ok) {
      setCopied(true)
      addToast({ type: 'success', message: '提货内容已复制' })
      setTimeout(() => setCopied(false), 2000)
    } else {
      addToast({ type: 'error', message: '复制失败，请长按内容手动复制' })
    }
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-600 via-blue-500 to-indigo-600 flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-white dark:bg-slate-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* 顶部标题栏：底色比页面背景更深一档，避免与页面渐变糊在一起，同时保证白字对比度 */}
        <div className="bg-gradient-to-r from-blue-700 to-indigo-700 px-6 py-5 text-white text-center">
          <div className="flex items-center justify-center gap-2 mb-1">
            <PackageCheck className="w-5 h-5 flex-shrink-0" />
            <h1 className="text-xl font-bold tracking-wide drop-shadow-sm">订单提货确认</h1>
          </div>
          <p className="text-blue-50 text-sm font-medium">确认同意发货后即可查看提货内容</p>
        </div>

        <div className="p-6">
          {/* 加载中 */}
          {status === 'loading' && (
            <div className="flex flex-col items-center py-10 gap-4">
              <Loader2 className="w-12 h-12 text-blue-500 animate-spin" />
              <p className="text-slate-600 dark:text-slate-400">正在校验订单，请稍候...</p>
            </div>
          )}

          {/* 订单无效（不存在 / 不匹配 / 参数缺失） */}
          {status === 'invalid' && (
            <div className="flex flex-col items-center py-8 gap-4 text-center">
              <div className="w-20 h-20 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                <AlertCircle className="w-12 h-12 text-red-500" />
              </div>
              <div>
                <p className="text-xl font-bold text-red-600 dark:text-red-400 mb-1">无法提货</p>
                <p className="text-sm text-slate-500 dark:text-slate-400">{errorMessage}</p>
              </div>
            </div>
          )}

          {/* 待同意 */}
          {status === 'ready' && order && (
            <div className="flex flex-col gap-5">
              <OrderInfo order={order} />
              <div className="rounded-lg bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800 px-4 py-3">
                <p className="text-sm text-blue-700 dark:text-blue-300 leading-relaxed">
                  如果您同意发货，请点击下方同意按钮
                </p>
              </div>
              {tip && (
                <p className="text-sm text-red-500 text-center">{tip}</p>
              )}
              <button
                onClick={handleAgree}
                disabled={submitting}
                className="flex items-center justify-center gap-2 w-full px-6 py-3 bg-blue-500 hover:bg-blue-600 active:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed text-white rounded-lg text-base font-medium transition-colors"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-5 h-5 animate-spin" />
                    正在处理...
                  </>
                ) : (
                  <>
                    <ShieldCheck className="w-5 h-5" />
                    同意发货
                  </>
                )}
              </button>
            </div>
          )}

          {/* 已同意（此前已点过）/ 本次同意成功：均展示发货内容 */}
          {(status === 'success' || status === 'already_agreed') && (
            <div className="flex flex-col gap-5">
              <div className="flex flex-col items-center gap-3 text-center">
                <div className="w-16 h-16 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                  <CheckCircle className="w-10 h-10 text-green-500" />
                </div>
                <p className="text-lg font-bold text-green-600 dark:text-green-400">
                  {status === 'success' ? '发货成功' : '您已同意发货'}
                </p>
              </div>
              {order && <OrderInfo order={order} />}
              <div>
                <div className="flex items-center justify-between mb-2">
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300">提货内容</p>
                  {content && (
                    <button
                      type="button"
                      onClick={handleCopyContent}
                      title="复制提货内容"
                      className="inline-flex items-center gap-1 px-2 py-1 -mr-1 rounded text-sm text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30 active:bg-blue-100 dark:active:bg-blue-900/50 transition-colors"
                    >
                      {copied ? (
                        <>
                          <Check className="w-4 h-4 text-green-500" />
                          已复制
                        </>
                      ) : (
                        <>
                          <Copy className="w-4 h-4" />
                          复制
                        </>
                      )}
                    </button>
                  )}
                </div>
                {content ? (
                  <pre className="whitespace-pre-wrap break-words text-sm text-slate-800 dark:text-slate-200 bg-slate-50 dark:bg-slate-700/50 border border-slate-200 dark:border-slate-600 rounded-lg px-4 py-3 max-h-72 overflow-auto">
                    {content}
                  </pre>
                ) : (
                  <p className="text-sm text-slate-500 dark:text-slate-400">发货内容为空，请联系卖家</p>
                )}
              </div>
            </div>
          )}
        </div>

        {/* 底部提示 */}
        <div className="px-6 py-3 bg-slate-50 dark:bg-slate-700/50 border-t border-slate-100 dark:border-slate-700">
          <p className="text-xs text-slate-600 dark:text-slate-300 text-center">
            本页面用于订单提货确认，请确认信息无误后再点击同意
          </p>
        </div>
      </div>
    </div>
  )
}

/** 订单信息展示块（商品标题可点击跳转闲鱼商品详情页） */
function OrderInfo({ order }: { order: PickupOrderView }) {
  // 标题取不到时退化展示商品ID，避免出现空白行
  const itemLabel = order.item_title || order.item_id || ''
  // 规格名与规格值用「 / 」分隔（仅一侧有值时不出现多余分隔符）
  const specText = [order.spec_name, order.spec_value].filter(Boolean).join(' / ')

  const rows: Array<[string, string]> = [
    ['订单号', order.order_no || '-'],
  ]
  if (specText) rows.push(['规格', specText])
  if (order.quantity != null) rows.push(['数量', String(order.quantity)])
  if (order.amount != null) rows.push(['金额', `¥${order.amount}`])

  return (
    <div className="rounded-lg border border-slate-200 dark:border-slate-600 divide-y divide-slate-100 dark:divide-slate-700">
      {/* 商品信息：有商品链接时可点击跳转闲鱼查看 */}
      {itemLabel && (
        <div className="px-4 py-3">
          <div className="flex items-center justify-between gap-2 mb-1">
            <span className="text-sm text-slate-500 dark:text-slate-400">商品</span>
            {order.item_url && (
              <a
                href={order.item_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 flex-shrink-0 text-xs text-blue-600 dark:text-blue-400 hover:underline"
              >
                去闲鱼查看
                <ExternalLink className="w-3.5 h-3.5" />
              </a>
            )}
          </div>
          {order.item_url ? (
            <a
              href={order.item_url}
              target="_blank"
              rel="noopener noreferrer"
              className="block text-sm font-medium text-blue-600 dark:text-blue-400 hover:underline break-all"
            >
              {itemLabel}
            </a>
          ) : (
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 break-all">
              {itemLabel}
            </p>
          )}
        </div>
      )}
      {rows.map(([label, value]) => (
        <div key={label} className="flex items-center justify-between px-4 py-2.5">
          <span className="text-sm text-slate-500 dark:text-slate-400">{label}</span>
          <span className="text-sm font-medium text-slate-800 dark:text-slate-200 text-right break-all ml-4">
            {value}
          </span>
        </div>
      ))}
    </div>
  )
}
