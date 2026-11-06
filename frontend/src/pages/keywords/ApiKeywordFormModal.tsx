/** API关键词新建和编辑表单，读取最新配置并保存指定字段。 */
import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { createApiKeyword, createApiKeywordRequestId, getApiKeywordDetail, getApiKeywordOptions, updateApiKeyword } from '@/api/apiKeywords'
import type { ApiKeywordOptions } from '@/api/apiKeywords'
import { Loading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

interface Props { accountId: string; ruleId?: string; onClose: () => void; onSaved: () => void }

/** 解析JSON对象，错误输入给出中文提示，保持填写内容。 */
function parseObject(value: string, label: string): Promise<Record<string, unknown>> {
  return Promise.resolve().then(() => JSON.parse(value.trim() || '{}') as unknown).then(
    parsed => {
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error(`${label}必须是JSON对象`)
      return parsed as Record<string, unknown>
    },
    () => { throw new Error(`${label}JSON格式不正确，请检查后保存`) },
  )
}

export function ApiKeywordFormModal({ accountId, ruleId, onClose, onSaved }: Props) {
  const { addToast } = useUIStore()
  const [keyword, setKeyword] = useState('')
  const [url, setUrl] = useState('')
  const [method, setMethod] = useState('GET')
  const [timeout, setTimeout] = useState('60')
  const [headers, setHeaders] = useState('')
  const [params, setParams] = useState('')
  const [responseField, setResponseField] = useState('')
  const [syncConfirmDelivery, setSyncConfirmDelivery] = useState(false)
  const [triggerAfterOrder, setTriggerAfterOrder] = useState(false)
  const [options, setOptions] = useState<ApiKeywordOptions | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [saving, setSaving] = useState(false)
  const [reload, setReload] = useState(0)
  const requestId = useRef('')
  const expectedRevision = useRef('')
  const submitting = useRef(false)

  useEffect(() => {
    let active = true
    setLoading(true)
    setLoadError('')
    setOptions(null)
    Promise.all([getApiKeywordOptions(), ruleId ? getApiKeywordDetail(accountId, ruleId) : Promise.resolve(null)]).then(([result, detail]) => {
      if (!active) return
      if (!result.success || !result.data || !result.data.methods.length) {
        setLoadError(result.message || '读取API关键词选项失败')
        return
      }
      if (ruleId) {
        if (!detail?.success || !detail.data) {
          setLoadError(detail?.message || '读取API关键词配置失败')
          return
        }
        const current = detail.data
        setKeyword(current.keyword)
        setUrl(current.url)
        setMethod(current.method)
        setTimeout(String(current.timeout))
        setHeaders(JSON.stringify(current.headers, null, 2))
        setParams(JSON.stringify(current.params, null, 2))
        setResponseField(current.response_field)
        setSyncConfirmDelivery(current.sync_confirm_delivery)
        setTriggerAfterOrder(current.trigger_after_order)
        expectedRevision.current = current.revision
      } else {
        setMethod(current => result.data!.methods.some(item => item.value === current)
          ? current : result.data!.methods[0].value)
      }
      setOptions(result.data)
    }, error => {
      if (active) setLoadError(getApiErrorMessage(error, '读取API关键词选项失败'))
    }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [accountId, ruleId, reload])

  const methodEnabled = options?.methods.some(item => item.value === method) ?? false

  /** GET和POST均允许插入字典参数；actId使用消息链接占位符，保留其他参数。 */
  const insertParameter = (name: string, placeholder: string) => {
    parseObject(params, '请求参数').then(
      current => setParams(JSON.stringify({ ...current, [name]: placeholder }, null, 2)),
      error => addToast({ type: 'error', message: getApiErrorMessage(error, '请求参数格式不正确') }),
    )
  }

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault()
    if (submitting.current || loading || !options) return
    if (!methodEnabled) {
      addToast({ type: 'error', message: '当前请求方法已禁用，请重新选择后保存' })
      return
    }
    submitting.current = true
    setSaving(true)
    Promise.all([parseObject(headers, '请求头'), parseObject(params, '请求参数')]).then(([parsedHeaders, parsedParams]) => {
      const values = {
        keyword, url, method, timeout: Number(timeout),
        headers: parsedHeaders, params: parsedParams, response_field: responseField,
        sync_confirm_delivery: syncConfirmDelivery, trigger_after_order: triggerAfterOrder,
      }
      if (ruleId) return updateApiKeyword(accountId, ruleId, { ...values, expected_revision: expectedRevision.current })
      if (!requestId.current) requestId.current = createApiKeywordRequestId()
      return createApiKeyword(accountId, { ...values, request_id: requestId.current })
    }).then(result => {
      if (!result.success) {
        // 已明确失败时允许用户修改后再次保存；网络断开仍保留原标识供幂等重试。
        requestId.current = ''
        addToast({ type: 'error', message: result.message || '保存API关键词失败' })
        return
      }
      addToast({ type: 'success', message: result.message || 'API关键词保存成功' })
      onSaved()
    }, error => {
      addToast({ type: 'error', message: getApiErrorMessage(error, '保存API关键词失败，请稍后重试') })
    }).finally(() => { submitting.current = false; setSaving(false) })
  }

  return <div className="modal-overlay">
    <div className="modal-content max-w-2xl relative" role="dialog" aria-modal="true" aria-labelledby="api-keyword-title">
      <div className="modal-header flex items-center justify-between">
        <h2 id="api-keyword-title" className="text-lg font-semibold">{ruleId ? '编辑 API关键词' : '新增 API关键词'}</h2>
        <button type="button" onClick={onClose} disabled={saving} className="btn-ios-secondary">关闭</button>
      </div>
      <form onSubmit={handleSubmit} className="flex flex-col flex-1 min-h-0">
        <div className="modal-body space-y-4">
          {loadError && <div className="text-sm text-red-600 dark:text-red-400 flex items-center gap-3" role="alert">
            <span>{loadError}</span><button type="button" className="btn-ios-secondary" onClick={() => setReload(value => value + 1)}>重试</button>
          </div>}
          <fieldset disabled={saving || loading || !options} className="space-y-4">
            <div>
              <label className="input-label" htmlFor="api-keyword-text">触发关键字 <span className="text-red-500">*</span></label>
              <textarea id="api-keyword-text" className="input-ios h-20" value={keyword} onChange={event => setKeyword(event.target.value)}
                required maxLength={12000} placeholder="例如：查询,进度,订单状态" />
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">支持中英文逗号分隔，多个关键字对应同一份API配置。</p>
            </div>
            <div className="border border-slate-200 dark:border-slate-700 rounded-lg p-4 space-y-4">
              <div>
                <label className="input-label" htmlFor="api-keyword-url">API地址 <span className="text-red-500">*</span></label>
                <input id="api-keyword-url" type="url" className="input-ios" value={url} onChange={event => setUrl(event.target.value)}
                  required maxLength={2048} placeholder="https://api.example.com/query" />
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div><label className="input-label">请求方法</label>
                  <Select value={method} onChange={setMethod} options={options?.methods || []} disabled={saving || loading || !options}
                    placeholder={options && !methodEnabled ? `${method}（已禁用）` : '请选择'} />
                  {options && !methodEnabled && <p className="text-xs text-red-600 dark:text-red-400 mt-1" role="alert">当前请求方法已禁用，请重新选择后保存</p>}
                </div>
                <div><label className="input-label" htmlFor="api-keyword-timeout">超时时间（秒）</label>
                  <input id="api-keyword-timeout" type="number" className="input-ios" value={timeout} onChange={event => setTimeout(event.target.value)}
                    min={1} max={300} step={1} required />
                </div>
              </div>
              <div><label className="input-label" htmlFor="api-keyword-headers">请求头（JSON格式）</label>
                <textarea id="api-keyword-headers" className="input-ios h-20 font-mono text-sm" value={headers} onChange={event => setHeaders(event.target.value)}
                  maxLength={65536} placeholder='{"Authorization": "Bearer token"}' />
              </div>
              <div><label className="input-label" htmlFor="api-keyword-params">请求参数（JSON格式）</label>
                <textarea id="api-keyword-params" className="input-ios h-24 font-mono text-sm" value={params} onChange={event => setParams(event.target.value)}
                  maxLength={65536} placeholder='{"item_id": "{item_id}", "message": "{message}"}' />
                <div className="mt-2 p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                  <p className="text-xs text-slate-600 dark:text-slate-300 mb-2">可用参数（GET、POST均支持，点击添加）：</p>
                  <div className="flex flex-wrap gap-2">{options?.parameters.map(item => <button key={item.value} type="button" className="btn-ios-secondary text-xs"
                    onClick={() => insertParameter(item.value, item.placeholder)}>{item.label} <code>{item.placeholder}</code></button>)}</div>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">actId 提取消息中的第一个HTTP/HTTPS链接，没有链接时传递完整消息；message 始终传递完整消息。</p>
                </div>
              </div>
              <div><label className="input-label" htmlFor="api-keyword-response">响应取值字段（选填）</label>
                <input id="api-keyword-response" className="input-ios" value={responseField} onChange={event => setResponseField(event.target.value)}
                  maxLength={255} placeholder="data.cards[0].key" />
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">用点号进入对象、中括号表示数组下标，例如 data.result 或 data.cards[0].key。</p>
              </div>
            </div>
            <div className="space-y-3">{[
              { label: '是否同步确认发货', value: syncConfirmDelivery, setter: setSyncConfirmDelivery },
              { label: '下单后触发', value: triggerAfterOrder, setter: setTriggerAfterOrder },
            ].map(item => <div key={item.label} className="flex items-center justify-between gap-4">
              <span className="input-label mb-0">{item.label}</span>
              <button type="button" role="switch" aria-checked={item.value} aria-label={item.label}
                onClick={() => item.setter(value => !value)} disabled={saving || loading || !options}
                className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors ${item.value ? 'bg-[rgb(var(--color-primary))]' : 'bg-slate-300 dark:bg-slate-600'}`}>
                <span className={`inline-block h-4 w-4 rounded-full bg-white transition-transform ${item.value ? 'translate-x-6' : 'translate-x-1'}`} />
              </button>
            </div>)}</div>
          </fieldset>
        </div>
        <div className="modal-footer">
          <button type="button" className="btn-ios-secondary" disabled={saving} onClick={onClose}>关闭</button>
          <button type="submit" className="btn-ios-primary" disabled={saving || loading || !options || !methodEnabled}>{saving ? '保存中...' : '保存'}</button>
        </div>
      </form>
      {(loading || saving) && <div className="absolute inset-0 bg-white/75 dark:bg-slate-900/75 flex items-center justify-center rounded-xl z-10">
        <div className="flex flex-col items-center gap-4">
          <Loading text={saving ? '保存中...' : '加载中...'} />
          {loading && <button type="button" className="btn-ios-secondary" onClick={onClose}>关闭</button>}
        </div>
      </div>}
    </div>
  </div>
}
