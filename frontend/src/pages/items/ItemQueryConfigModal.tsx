/**
 * 商品查询配置弹窗
 *
 * 功能：按商品配置通用查询按钮（存 metadata_json.query_buttons），买家在
 * 公开查询页 /query 点击按钮后由服务端代理执行并返回结构化结果。
 *
 * 编辑格式（与 QueryButton 结构的序列化/反序列化在本组件内完成）：
 * - 请求头：textarea 每行 `Key: Value`，值支持变量
 * - 结果字段：textarea 每行 `标签=路径`，行尾加 `*` 表高亮（主结果大字），
 *   前缀用 `标签=路径|前缀` 表达（如 `可用余额=data.balance|¥*`）
 *
 * 可用变量（服务端执行时替换）：{cookie} {account} {api_key} {line}
 */
import { useEffect, useState } from 'react'
import { Loader2, Plus, Search, Trash2, X } from 'lucide-react'
import {
  getItemQueryButtons,
  saveItemQueryButtons,
  type QueryButton,
  type QueryResultField,
} from '@/api/itemQuery'
import { useUIStore } from '@/store/uiStore'

// ==================== 编辑态 ⇄ QueryButton 序列化 ====================

/** 按钮编辑草稿：headers / result_fields 以文本行形式编辑，保存时再解析 */
interface ButtonDraft {
  name: string
  method: 'GET' | 'POST'
  url: string
  /** 每行 `Key: Value` */
  headersText: string
  /** 仅 POST 使用 */
  body: string
  successPath: string
  successValue: string
  errorPath: string
  /** 每行 `标签=路径[|前缀][*]`，行尾 * 表高亮 */
  fieldsText: string
}

const emptyDraft = (): ButtonDraft => ({
  name: '',
  method: 'GET',
  url: '',
  headersText: '',
  body: '',
  successPath: '',
  successValue: '',
  errorPath: '',
  fieldsText: '',
})

/** QueryButton → 编辑草稿 */
const toDraft = (btn: QueryButton): ButtonDraft => ({
  name: btn.name || '',
  method: btn.method === 'POST' ? 'POST' : 'GET',
  url: btn.url || '',
  headersText: Object.entries(btn.headers || {})
    .map(([k, v]) => `${k}: ${v}`)
    .join('\n'),
  body: btn.body || '',
  successPath: btn.success_path || '',
  successValue: btn.success_value || '',
  errorPath: btn.error_path || '',
  fieldsText: (btn.result_fields || [])
    .map((f) => `${f.label}=${f.path}${f.prefix ? `|${f.prefix}` : ''}${f.highlight ? '*' : ''}`)
    .join('\n'),
})

/** 解析请求头文本（每行 `Key: Value`），返回 null 表示某行格式错误 */
const parseHeaders = (text: string): Record<string, string> | null => {
  const headers: Record<string, string> = {}
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean)
  for (const line of lines) {
    const idx = line.indexOf(':')
    if (idx <= 0) return null
    const key = line.slice(0, idx).trim()
    const value = line.slice(idx + 1).trim()
    if (!key) return null
    headers[key] = value
  }
  return headers
}

/** 解析结果字段文本（每行 `标签=路径[|前缀][*]`），返回 null 表示某行格式错误 */
const parseFields = (text: string): QueryResultField[] | null => {
  const fields: QueryResultField[] = []
  const lines = text.split('\n').map((l) => l.trim()).filter(Boolean)
  for (let line of lines) {
    // 行尾 * 表高亮
    let highlight = false
    if (line.endsWith('*')) {
      highlight = true
      line = line.slice(0, -1).trim()
    }
    // |前缀
    let prefix: string | undefined
    const pipeIdx = line.indexOf('|')
    if (pipeIdx >= 0) {
      prefix = line.slice(pipeIdx + 1).trim() || undefined
      line = line.slice(0, pipeIdx).trim()
    }
    const eqIdx = line.indexOf('=')
    if (eqIdx <= 0) return null
    const label = line.slice(0, eqIdx).trim()
    const path = line.slice(eqIdx + 1).trim()
    if (!label || !path) return null
    fields.push({ label, path, highlight, prefix })
  }
  return fields
}

/** 编辑草稿 → QueryButton；返回错误消息或解析结果 */
const toQueryButton = (draft: ButtonDraft, index: number): { button?: QueryButton; error?: string } => {
  const name = draft.name.trim()
  if (!name) return { error: `第 ${index + 1} 个按钮：名称不能为空` }
  const url = draft.url.trim()
  if (!url) return { error: `按钮「${name}」：URL 不能为空` }
  if (!/^https?:\/\//i.test(url)) return { error: `按钮「${name}」：URL 必须以 http:// 或 https:// 开头` }
  const headers = parseHeaders(draft.headersText)
  if (!headers) return { error: `按钮「${name}」：请求头格式错误，应为每行「Key: Value」` }
  const fields = parseFields(draft.fieldsText)
  if (!fields) return { error: `按钮「${name}」：结果字段格式错误，应为每行「标签=路径」，行尾加 * 表高亮，| 后缀表前缀` }
  if (fields.length === 0) return { error: `按钮「${name}」：至少配置一个结果字段` }
  return {
    button: {
      name,
      method: draft.method,
      url,
      headers,
      body: draft.method === 'POST' ? draft.body : null,
      success_path: draft.successPath.trim() || null,
      success_value: draft.successValue.trim() || null,
      error_path: draft.errorPath.trim() || null,
      result_fields: fields,
    },
  }
}

// ==================== 组件 ====================

interface ItemQueryConfigModalProps {
  /** 账号 cookie_id */
  cookieId: string
  /** 商品ID */
  itemId: string
  /** 商品名称（用于弹窗标题） */
  itemName: string
  /** 关闭回调 */
  onClose: () => void
  /** 保存成功回调 */
  onSaved: () => void
}

export function ItemQueryConfigModal({ cookieId, itemId, itemName, onClose, onSaved }: ItemQueryConfigModalProps) {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [drafts, setDrafts] = useState<ButtonDraft[]>([])
  // 加载失败时禁止保存：覆盖式保存会把服务端已有配置清空，必须阻止"加载失败→保存空配置"的数据丢失路径
  const [loadFailed, setLoadFailed] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      setLoadFailed(false)
      try {
        const result = await getItemQueryButtons(cookieId, itemId)
        if (result.success) {
          setDrafts((result.data?.buttons || []).map(toDraft))
        } else {
          setLoadFailed(true)
          addToast({ type: 'error', message: result.message || '加载查询配置失败' })
        }
      } catch {
        setLoadFailed(true)
        addToast({ type: 'error', message: '加载查询配置失败，请稍后重试' })
      } finally {
        setLoading(false)
      }
    }
    load()
  }, [cookieId, itemId, addToast, reloadKey])

  const updateDraft = (index: number, patch: Partial<ButtonDraft>) => {
    setDrafts((prev) => prev.map((d, i) => (i === index ? { ...d, ...patch } : d)))
  }

  const addDraft = () => setDrafts((prev) => [...prev, emptyDraft()])

  const removeDraft = (index: number) => setDrafts((prev) => prev.filter((_, i) => i !== index))

  const handleSave = async () => {
    if (saving) return
    const buttons: QueryButton[] = []
    for (let i = 0; i < drafts.length; i++) {
      const { button, error } = toQueryButton(drafts[i], i)
      if (error || !button) {
        addToast({ type: 'error', message: error || '配置校验失败' })
        return
      }
      buttons.push(button)
    }
    setSaving(true)
    try {
      const result = await saveItemQueryButtons(cookieId, itemId, buttons)
      if (result.success) {
        addToast({ type: 'success', message: '查询配置已保存' })
        onSaved()
      } else {
        addToast({ type: 'error', message: result.message || '保存失败，请稍后重试' })
      }
    } catch {
      addToast({ type: 'error', message: '保存失败，请稍后重试' })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay" style={{ zIndex: 60 }}>
      <div className="modal-content max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        <div className="modal-header flex items-center justify-between flex-shrink-0">
          <div>
            <h2 className="modal-title flex items-center gap-2">
              <Search className="w-5 h-5 text-blue-500" />
              商品查询配置
            </h2>
            <p className="text-sm text-gray-500 mt-1 truncate max-w-[300px]">{itemName}</p>
          </div>
          <button onClick={onClose} className="modal-close">
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="modal-body flex-1 overflow-y-auto space-y-4">
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : loadFailed ? (
            <div className="flex flex-col items-center gap-3 py-8">
              <p className="text-sm text-red-500">配置加载失败，为避免误清空已有配置，已禁止保存</p>
              <button
                type="button"
                onClick={() => setReloadKey((k) => k + 1)}
                className="btn-ios-secondary text-sm"
              >
                重新加载
              </button>
            </div>
          ) : (
            <>
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg text-sm text-blue-600 dark:text-blue-400">
                <strong>说明：</strong>
                <ul className="list-disc list-inside mt-1 space-y-1">
                  <li>买家在提货页/查询页点击按钮，由服务端代理发起请求并展示结果</li>
                  <li>可用变量 {'{cookie}'} {'{account}'} {'{api_key}'} {'{line}'}（按卡密行逐行替换）</li>
                  <li>成功条件的「路径=值」都留空时，HTTP 2xx 即视为成功</li>
                </ul>
              </div>

              {drafts.length === 0 && (
                <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
                  暂无查询按钮，点击下方「添加按钮」创建
                </p>
              )}

              {drafts.map((draft, index) => (
                <div
                  key={index}
                  className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      按钮 {index + 1}{draft.name ? `：${draft.name}` : ''}
                    </p>
                    <button
                      type="button"
                      onClick={() => removeDraft(index)}
                      className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/30 text-red-500"
                      title="删除该按钮"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="input-group sm:col-span-2">
                      <label className="input-label">按钮名称</label>
                      <input
                        type="text"
                        value={draft.name}
                        onChange={(e) => updateDraft(index, { name: e.target.value })}
                        className="input-ios"
                        placeholder="如：查余额"
                      />
                    </div>
                    <div className="input-group">
                      <label className="input-label">请求方法</label>
                      <select
                        value={draft.method}
                        onChange={(e) => updateDraft(index, { method: e.target.value as 'GET' | 'POST' })}
                        className="input-ios"
                      >
                        <option value="GET">GET</option>
                        <option value="POST">POST</option>
                      </select>
                    </div>
                  </div>

                  <div className="input-group">
                    <label className="input-label">请求地址 URL</label>
                    <input
                      type="text"
                      value={draft.url}
                      onChange={(e) => updateDraft(index, { url: e.target.value })}
                      className="input-ios"
                      placeholder="https://example.com/api/query"
                    />
                  </div>

                  <div className="input-group">
                    <label className="input-label">请求头（每行 Key: Value，支持变量）</label>
                    <textarea
                      value={draft.headersText}
                      onChange={(e) => updateDraft(index, { headersText: e.target.value })}
                      className="input-ios h-20 resize-none font-mono text-sm"
                      placeholder={'Cookie: {cookie}\nAuthorization: Bearer {api_key}'}
                    />
                  </div>

                  {draft.method === 'POST' && (
                    <div className="input-group">
                      <label className="input-label">POST Body（支持变量）</label>
                      <textarea
                        value={draft.body}
                        onChange={(e) => updateDraft(index, { body: e.target.value })}
                        className="input-ios h-20 resize-none font-mono text-sm"
                        placeholder={'{"account": "{account}"}'}
                      />
                    </div>
                  )}

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="input-group">
                      <label className="input-label">成功路径（可空）</label>
                      <input
                        type="text"
                        value={draft.successPath}
                        onChange={(e) => updateDraft(index, { successPath: e.target.value })}
                        className="input-ios"
                        placeholder="code"
                      />
                    </div>
                    <div className="input-group">
                      <label className="input-label">成功值（可空）</label>
                      <input
                        type="text"
                        value={draft.successValue}
                        onChange={(e) => updateDraft(index, { successValue: e.target.value })}
                        className="input-ios"
                        placeholder="0"
                      />
                    </div>
                    <div className="input-group">
                      <label className="input-label">错误消息路径（可空）</label>
                      <input
                        type="text"
                        value={draft.errorPath}
                        onChange={(e) => updateDraft(index, { errorPath: e.target.value })}
                        className="input-ios"
                        placeholder="message"
                      />
                    </div>
                  </div>

                  <div className="input-group">
                    <label className="input-label">
                      结果字段（每行 标签=路径，行尾 * 表高亮，| 后缀表前缀）
                    </label>
                    <textarea
                      value={draft.fieldsText}
                      onChange={(e) => updateDraft(index, { fieldsText: e.target.value })}
                      className="input-ios h-24 resize-none font-mono text-sm"
                      placeholder={'可用余额=data.availableBalanceCny|¥*\n账户状态=data.status'}
                    />
                  </div>
                </div>
              ))}

              <button
                type="button"
                onClick={addDraft}
                className="flex items-center justify-center gap-1.5 w-full px-4 py-2 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 text-sm text-gray-600 dark:text-gray-400 hover:border-blue-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                <Plus className="w-4 h-4" />
                添加按钮
              </button>
            </>
          )}
        </div>

        <div className="modal-footer flex-shrink-0 flex justify-end gap-2">
          <button onClick={onClose} className="btn-ios-secondary" disabled={saving}>
            取消
          </button>
          <button
            onClick={handleSave}
            className="btn-ios-primary"
            disabled={saving || loading || loadFailed}
          >
            {saving ? (
              <span className="flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" />
                保存中...
              </span>
            ) : (
              '保存'
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
