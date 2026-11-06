/** API关键词后端分页列表，支持查看配置及编辑后刷新当前页。 */
import { useEffect, useState } from 'react'
import { getApiKeywords, getApiKeywordOptions } from '@/api/apiKeywords'
import type { ApiKeyword, ApiKeywordPage } from '@/api/apiKeywords'
import { Loading } from '@/components/common/Loading'
import { Pager } from '@/components/common/Pager'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { ApiKeywordFormModal } from './ApiKeywordFormModal'

interface Props { accountId: string; revision: number }

export function ApiKeywordList({ accountId, revision }: Props) {
  const { addToast } = useUIStore()
  const [pagination, setPagination] = useState({ page: 1, pageSize: 20 })
  const [data, setData] = useState<ApiKeywordPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [errorMessage, setErrorMessage] = useState('')
  const [reload, setReload] = useState(0)
  const [methodLabels, setMethodLabels] = useState<Record<string, string>>({})
  const [detail, setDetail] = useState<ApiKeyword | null>(null)
  const [editing, setEditing] = useState<ApiKeyword | null>(null)

  useEffect(() => {
    let active = true
    getApiKeywordOptions().then(result => {
      if (!active) return
      if (!result.success || !result.data) {
        addToast({ type: 'error', message: result.message || '读取请求方法字典失败' })
        return
      }
      setMethodLabels(Object.fromEntries(result.data.methods.map(item => [item.value, item.label])))
    }, error => { if (active) addToast({ type: 'error', message: getApiErrorMessage(error, '读取请求方法字典失败') }) })
    return () => { active = false }
  }, [addToast])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    setErrorMessage('')
    getApiKeywords(accountId, pagination.page, pagination.pageSize, controller.signal).then(result => {
      if (controller.signal.aborted) return
      if (!result.success || !result.data) {
        setErrorMessage(result.message || '查询API关键词失败')
        return
      }
      setData(result.data)
      const lastPage = Math.max(1, Math.ceil(result.data.total / pagination.pageSize))
      if (pagination.page > lastPage) setPagination(current => ({ ...current, page: lastPage }))
    }, error => {
      if (!controller.signal.aborted) setErrorMessage(getApiErrorMessage(error, '查询API关键词失败'))
    }).finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [accountId, pagination, revision, reload])

  return <>
    <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 340px)', minHeight: 320 }}>
      <div className="vben-card-header flex items-center justify-between gap-2">
        <h2 className="vben-card-title">API关键词列表</h2>
        <button type="button" className="btn-ios-secondary" onClick={() => setReload(value => value + 1)} disabled={loading}>刷新</button>
      </div>
      <div className="table-scroll flex-1 min-h-0 relative" aria-busy={loading}>
        {errorMessage ? <div className="p-6 text-center text-red-600 dark:text-red-400" role="alert">{errorMessage}</div> : <table className="table-ios">
          <thead><tr><th>所属账号</th><th>触发关键字</th><th>API地址</th><th>请求方法</th><th>超时（秒）</th><th>创建时间</th><th>操作</th></tr></thead>
          <tbody>{data?.list.map(item => <tr key={item.id}>
            <td>{item.account_id}</td>
            <td className="max-w-xs"><div className="truncate" title={item.keyword}>{item.keyword}</div></td>
            <td className="max-w-xs"><div className="truncate" title={item.url}>{item.url}</div></td>
            <td>{methodLabels[item.method] || item.method}</td><td>{item.timeout}</td>
            <td className="whitespace-nowrap">{item.created_at.replace('T', ' ')}</td>
            <td><div className="flex items-center gap-2 whitespace-nowrap">
              <button type="button" className="btn-ios-secondary" onClick={() => setDetail(item)}>查看配置</button>
              <button type="button" className="btn-ios-secondary" onClick={() => setEditing(item)}>编辑</button>
            </div></td>
          </tr>)}{!loading && data?.total === 0 && <tr><td colSpan={7} className="text-center py-12 text-slate-500">暂无API关键词</td></tr>}</tbody>
        </table>}
        {loading && <div className="absolute inset-0 bg-white/75 dark:bg-slate-900/75 flex items-center justify-center"><Loading text="加载中..." /></div>}
      </div>
      <Pager page={pagination.page} pageSize={pagination.pageSize} total={errorMessage ? 0 : data?.total || 0} loading={loading}
        onPageChange={page => setPagination(current => ({ ...current, page }))}
        onPageSizeChange={pageSize => setPagination({ page: 1, pageSize })} />
    </div>
    {editing && <ApiKeywordFormModal key={editing.id} accountId={editing.account_id} ruleId={editing.id}
      onClose={() => setEditing(null)} onSaved={() => {
        setEditing(null)
        setDetail(null)
        setReload(value => value + 1)
      }} />}
    {detail && <div className="modal-overlay">
      <div className="modal-content max-w-2xl" role="dialog" aria-modal="true" aria-labelledby="api-keyword-detail">
        <div className="modal-header"><h2 id="api-keyword-detail" className="text-lg font-semibold">API关键词配置</h2></div>
        <dl className="modal-body space-y-4">
          {[
            ['触发关键字', detail.keyword], ['API地址', detail.url],
            ['请求方法', methodLabels[detail.method] || detail.method], ['超时时间（秒）', String(detail.timeout)],
            ['请求头', JSON.stringify(detail.headers, null, 2)], ['请求参数', JSON.stringify(detail.params, null, 2)],
            ['响应取值字段', detail.response_field || '未填写'],
            ['是否同步确认发货', detail.sync_confirm_delivery ? '开启' : '关闭'], ['下单后触发', detail.trigger_after_order ? '开启' : '关闭'],
          ].map(([label, value]) => <div key={label}><dt className="input-label">{label}</dt>
            <dd className="whitespace-pre-wrap break-all text-sm text-slate-700 dark:text-slate-200">{value}</dd></div>)}
        </dl>
        <div className="modal-footer"><button type="button" className="btn-ios-secondary" onClick={() => setDetail(null)}>关闭</button></div>
      </div>
    </div>}
  </>
}
