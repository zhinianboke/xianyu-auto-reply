/**
 * 商品通用查询页（无需登录的公开页面）
 *
 * 功能：
 * 1. 输入订单号拉取该商品配置的查询按钮列表，点击按钮由服务端代理执行查询
 * 2. URL 带 orderNo/button 参数时（从提货页跳转过来）自动填入并执行对应按钮
 * 3. 一单多件（多份卡密）时逐份展示结果列表，单份失败不影响其他份
 * 4. uses_cookie=true 时展示「手动 Cookie 查询」折叠区，直接粘贴 Cookie 执行
 * 5. Cookie 仅作为请求参数传给后端代理，前端不保存、不展示
 * 6. 旧路径 /balance-query 由 App.tsx 重定向到本页（保留 query string）
 */
import { useEffect, useRef, useState } from 'react'
import {
  AlertCircle,
  ChevronDown,
  ChevronUp,
  KeyRound,
  Loader2,
  Receipt,
  Search,
  User,
  Wallet,
} from 'lucide-react'
import {
  executeQueryButton,
  getQueryButtonsByOrder,
  type ExecResult,
  type PublicQueryButton,
} from '@/api/itemQuery'

export function QueryPage() {
  const [orderNo, setOrderNo] = useState('')
  const [loadingButtons, setLoadingButtons] = useState(false)
  const [buttonsLoaded, setButtonsLoaded] = useState(false)
  const [buttons, setButtons] = useState<PublicQueryButton[]>([])
  const [usesCookie, setUsesCookie] = useState(false)
  const [executingIndex, setExecutingIndex] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [results, setResults] = useState<ExecResult[]>([])

  // 手动 Cookie 查询折叠区
  const [cookieOpen, setCookieOpen] = useState(false)
  const [cookieText, setCookieText] = useState('')
  const [cookieButtonIndex, setCookieButtonIndex] = useState(0)
  const [cookieExecuting, setCookieExecuting] = useState(false)
  const [cookieError, setCookieError] = useState('')
  const [cookieResults, setCookieResults] = useState<ExecResult[]>([])

  // 防止 URL 参数自动执行与手动操作并发
  const autoExecuted = useRef(false)

  // 拉取按钮列表；返回按钮数组供自动执行使用
  const loadButtons = async (no: string): Promise<PublicQueryButton[] | null> => {
    setLoadingButtons(true)
    setError('')
    setResults([])
    setButtonsLoaded(false)
    // 换订单重新加载时清空旧订单的按钮与手动 Cookie 区状态，避免残留配置串单
    setButtons([])
    setUsesCookie(false)
    setCookieResults([])
    setCookieError('')
    setCookieButtonIndex(0)
    try {
      const res = await getQueryButtonsByOrder(no)
      if (res.success && res.data) {
        const list = res.data.buttons || []
        setButtons(list)
        setUsesCookie(Boolean(res.data.uses_cookie))
        // 手动 Cookie 查询默认选中第一个含 {cookie} 变量的按钮（后端逐按钮下发标记）
        const cookieIdx = list.findIndex((b) => b.uses_cookie)
        if (cookieIdx >= 0) setCookieButtonIndex(cookieIdx)
        setButtonsLoaded(true)
        return list
      }
      setError(res.message || '查询失败，请稍后重试')
      return null
    } catch {
      setError('网络异常，请稍后重试')
      return null
    } finally {
      setLoadingButtons(false)
    }
  }

  // 执行指定按钮
  const executeButton = async (no: string, index: number) => {
    if (executingIndex !== null) return
    setExecutingIndex(index)
    setError('')
    setResults([])
    try {
      const res = await executeQueryButton({ orderNo: no, buttonIndex: index })
      if (res.data?.results?.length) {
        setResults(res.data.results)
        // 全部失败时后端 success=false 且 data 仍带 results，错误信息一并展示
        if (!res.success) setError(res.message || '查询失败，请稍后重试')
      } else {
        setError(res.message || '查询失败，请稍后重试')
      }
    } catch {
      setError('网络异常，请稍后重试')
    } finally {
      setExecutingIndex(null)
    }
  }

  // URL 参数自动填入并执行：/query?orderNo=xxx&button=N
  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const no = params.get('orderNo') || ''
    const buttonParam = params.get('button')
    if (!no || autoExecuted.current) return
    autoExecuted.current = true
    setOrderNo(no)
    void (async () => {
      const list = await loadButtons(no)
      if (buttonParam !== null && list && list.length > 0) {
        const idx = Number.parseInt(buttonParam, 10)
        if (Number.isInteger(idx) && idx >= 0 && idx < list.length) {
          await executeButton(no, idx)
        }
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const handleLoadButtons = async () => {
    if (loadingButtons) return
    const no = orderNo.trim()
    if (!no) {
      setError('请输入订单号')
      return
    }
    await loadButtons(no)
  }

  const handleCookieExecute = async () => {
    if (cookieExecuting) return
    const ck = cookieText.trim()
    if (!ck) {
      setCookieError('请粘贴 Cookie')
      return
    }
    setCookieExecuting(true)
    setCookieError('')
    setCookieResults([])
    try {
      const res = await executeQueryButton({
        orderNo: orderNo.trim() || null,
        buttonIndex: cookieButtonIndex,
        cookieOverride: ck,
      })
      if (res.data?.results?.length) {
        setCookieResults(res.data.results)
        if (!res.success) setCookieError(res.message || '查询失败，请稍后重试')
      } else {
        setCookieError(res.message || '查询失败，请稍后重试')
      }
    } catch {
      setCookieError('网络异常，请稍后重试')
    } finally {
      setCookieExecuting(false)
    }
  }

  const formatTime = (iso?: string | null) => {
    if (!iso) return '-'
    const d = new Date(iso)
    if (Number.isNaN(d.getTime())) return iso
    return d.toLocaleString('zh-CN', { hour12: false })
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-blue-600 via-blue-500 to-indigo-600 flex items-center justify-center p-4">
      <div className="w-full max-w-sm bg-white dark:bg-slate-800 rounded-2xl shadow-2xl overflow-hidden">
        {/* 顶部标题栏 */}
        <div className="bg-gradient-to-r from-blue-700 to-indigo-700 px-6 py-5 text-white text-center">
          <div className="flex items-center justify-center gap-2 mb-1">
            <Wallet className="w-5 h-5 flex-shrink-0" />
            <h1 className="text-xl font-bold tracking-wide drop-shadow-sm">订单查询</h1>
          </div>
          <p className="text-blue-50 text-sm font-medium">输入订单号，点击按钮查询</p>
        </div>

        <div className="p-6 flex flex-col gap-5">
          {/* 订单号输入 */}
          <div>
            <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
              订单号
            </label>
            <input
              type="text"
              inputMode="numeric"
              value={orderNo}
              onChange={(e) => setOrderNo(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleLoadButtons() }}
              placeholder="请输入闲鱼订单号"
              className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-4 py-2.5 text-sm text-slate-800 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* 获取查询按钮 */}
          <button
            type="button"
            onClick={handleLoadButtons}
            disabled={loadingButtons}
            className="flex items-center justify-center gap-2 w-full px-6 py-3 bg-blue-500 hover:bg-blue-600 active:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed text-white rounded-lg text-base font-medium transition-colors"
          >
            {loadingButtons ? (
              <>
                <Loader2 className="w-5 h-5 animate-spin" />
                正在加载...
              </>
            ) : (
              <>
                <Receipt className="w-5 h-5" />
                查询
              </>
            )}
          </button>

          {/* 整体错误提示 */}
          {error && (
            <div className="flex items-start gap-2 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800 px-4 py-3">
              <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            </div>
          )}

          {/* 按钮组：点击执行 */}
          {buttonsLoaded && buttons.length > 0 && (
            <div className="flex flex-col gap-2">
              <p className="text-sm font-medium text-slate-700 dark:text-slate-300">选择查询功能</p>
              {buttons.map((btn, idx) => (
                <button
                  key={idx}
                  type="button"
                  onClick={() => executeButton(orderNo.trim(), idx)}
                  disabled={executingIndex !== null}
                  className="flex items-center justify-center gap-2 w-full px-4 py-2.5 rounded-lg border border-blue-200 dark:border-blue-700 bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-300 text-sm font-medium hover:bg-blue-100 dark:hover:bg-blue-900/40 active:bg-blue-200 disabled:opacity-60 disabled:cursor-not-allowed transition-colors"
                >
                  {executingIndex === idx ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Search className="w-4 h-4" />
                  )}
                  {btn.name}
                </button>
              ))}
            </div>
          )}

          {/* 商品未配置查询功能 */}
          {buttonsLoaded && buttons.length === 0 && (
            <div className="flex items-start gap-2 rounded-lg bg-amber-50 dark:bg-amber-900/20 border border-amber-100 dark:border-amber-800 px-4 py-3">
              <AlertCircle className="w-4 h-4 text-amber-500 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-amber-600 dark:text-amber-400">
                该商品未配置查询功能，请联系卖家
              </p>
            </div>
          )}

          {/* 查询结果列表：一单多件时逐份展示 */}
          {results.length > 0 && <ResultList results={results} formatTime={formatTime} />}

          {/* 手动 Cookie 查询折叠区 */}
          {usesCookie && (
            <div className="rounded-lg border border-slate-200 dark:border-slate-600 overflow-hidden">
              <button
                type="button"
                onClick={() => setCookieOpen((v) => !v)}
                className="flex items-center justify-between w-full px-4 py-2.5 bg-slate-50 dark:bg-slate-700/50 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
              >
                <span className="flex items-center gap-1.5">
                  <KeyRound className="w-4 h-4 text-slate-400" />
                  手动 Cookie 查询
                </span>
                {cookieOpen ? (
                  <ChevronUp className="w-4 h-4 text-slate-400" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-slate-400" />
                )}
              </button>
              {cookieOpen && (
                <div className="p-4 flex flex-col gap-3">
                  {buttons.length > 1 && (
                    <div>
                      <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                        查询功能
                      </label>
                      <select
                        value={cookieButtonIndex}
                        onChange={(e) => setCookieButtonIndex(Number(e.target.value))}
                        className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
                      >
                        {buttons.map((btn, idx) => (
                          <option key={idx} value={idx}>{btn.name}</option>
                        ))}
                      </select>
                    </div>
                  )}
                  <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                      Cookie
                    </label>
                    <textarea
                      value={cookieText}
                      onChange={(e) => setCookieText(e.target.value)}
                      placeholder="粘贴发货内容里 Cookie： 后面的完整字符串"
                      rows={4}
                      className="w-full rounded-lg border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-700 px-4 py-2.5 text-sm text-slate-800 dark:text-slate-200 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={handleCookieExecute}
                    disabled={cookieExecuting}
                    className="flex items-center justify-center gap-2 w-full px-4 py-2.5 bg-blue-500 hover:bg-blue-600 active:bg-blue-700 disabled:opacity-60 disabled:cursor-not-allowed text-white rounded-lg text-sm font-medium transition-colors"
                  >
                    {cookieExecuting ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        正在查询...
                      </>
                    ) : (
                      <>
                        <Search className="w-4 h-4" />
                        执行查询
                      </>
                    )}
                  </button>
                  {cookieError && (
                    <div className="flex items-start gap-2 rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-100 dark:border-red-800 px-4 py-3">
                      <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                      <p className="text-sm text-red-600 dark:text-red-400">{cookieError}</p>
                    </div>
                  )}
                  {cookieResults.length > 0 && <ResultList results={cookieResults} formatTime={formatTime} />}
                </div>
              )}
            </div>
          )}
        </div>

        {/* 底部提示 */}
        <div className="px-6 py-3 bg-slate-50 dark:bg-slate-700/50 border-t border-slate-100 dark:border-slate-700">
          <p className="text-xs text-slate-600 dark:text-slate-300 text-center">
            Cookie 仅在本次查询中使用，不会被保存
          </p>
        </div>
      </div>
    </div>
  )
}

/** 查询结果列表：字段由 ExecResult.fields 数组驱动 */
function ResultList({
  results,
  formatTime,
}: {
  results: ExecResult[]
  formatTime: (iso?: string | null) => string
}) {
  const firstSuccess = results.find((r) => r.success && r.as_of)
  return (
    <div className="flex flex-col gap-3">
      {results.map((item, idx) => {
        const highlightFields = (item.fields || []).filter((f) => f.highlight)
        const normalFields = (item.fields || []).filter((f) => !f.highlight)
        return (
          <div
            key={idx}
            className="rounded-lg border border-slate-200 dark:border-slate-600 overflow-hidden"
          >
            {/* 账号行：一单多件时用于区分每份卡密 */}
            {item.account && (
              <div className="flex items-center gap-1.5 px-4 py-2 bg-slate-50 dark:bg-slate-700/50 border-b border-slate-100 dark:border-slate-700">
                <User className="w-3.5 h-3.5 text-slate-400" />
                <span className="text-sm font-medium text-slate-700 dark:text-slate-300">{item.account}</span>
              </div>
            )}
            {item.success ? (
              <>
                {/* 高亮字段：主结果大字 */}
                {highlightFields.map((f, i) => (
                  <div key={i} className="bg-green-50 dark:bg-green-900/20 px-4 py-3 text-center">
                    <p className="text-xs text-green-600 dark:text-green-400 mb-0.5">{f.label}</p>
                    <p className="text-2xl font-bold text-green-600 dark:text-green-400">
                      {f.prefix || ''}{f.value ?? '-'}
                    </p>
                  </div>
                ))}
                {/* 其余字段行 */}
                {normalFields.length > 0 && (
                  <div className="divide-y divide-slate-100 dark:divide-slate-700">
                    {normalFields.map((f, i) => (
                      <div key={i} className="flex items-center justify-between px-4 py-2">
                        <span className="text-sm text-slate-500 dark:text-slate-400">{f.label}</span>
                        <span className="text-sm font-medium text-slate-800 dark:text-slate-200">
                          {f.prefix || ''}{f.value ?? '-'}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </>
            ) : (
              <div className="flex items-start gap-2 px-4 py-3 bg-red-50 dark:bg-red-900/20">
                <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                <p className="text-sm text-red-600 dark:text-red-400">{item.error || '查询失败'}</p>
              </div>
            )}
          </div>
        )
      })}
      {firstSuccess && (
        <p className="text-xs text-slate-400 dark:text-slate-500 text-center">
          查询时间 {formatTime(firstSuccess.as_of)}
        </p>
      )}
    </div>
  )
}
