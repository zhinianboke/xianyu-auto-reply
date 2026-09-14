/**
 * 商品查询配置弹窗
 *
 * 顶部 Tab：
 * - 查询按钮：按商品配置通用查询按钮（存 metadata_json.query_buttons），买家在
 *   公开查询页 /query 点击按钮后由服务端代理执行并返回结构化结果。
 * - 展示入口：配置提货页底部工具区的入口（存 metadata_json.display_links），
 *   链接入口新窗口打开，文本入口弹窗展示（{cookie} 由提货页替换为发货 Cookie）。
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
  getItemDisplayLinks,
  getItemQueryButtons,
  saveItemDisplayLinks,
  saveItemQueryButtons,
  type DisplayLink,
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
  /** 是否启用（停用后买家端隐藏且不可执行） */
  enabled: boolean
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
  enabled: true,
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
  enabled: btn.enabled !== false,
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
      enabled: draft.enabled,
    },
  }
}

// ==================== 展示入口编辑态 ⇄ DisplayLink 序列化 ====================

/** 展示入口编辑草稿：两种类型字段平铺编辑，保存时按 type 收敛为 DisplayLink */
interface LinkDraft {
  name: string
  type: 'link' | 'text'
  /** 仅 type=link 使用 */
  url: string
  /** 仅 type=link 使用，可选（如「提取码：xxxx」，显示在按钮右侧） */
  note: string
  /** 仅 type=text 使用（弹窗标题） */
  title: string
  /** 仅 type=text 使用（多行文本，支持 {cookie} 占位符） */
  content: string
}

const emptyLinkDraft = (): LinkDraft => ({
  name: '',
  type: 'link',
  url: '',
  note: '',
  title: '',
  content: '',
})

/** DisplayLink → 编辑草稿 */
const linkToDraft = (link: DisplayLink): LinkDraft => ({
  name: link.name || '',
  type: link.type === 'text' ? 'text' : 'link',
  url: link.type === 'link' ? link.url || '' : '',
  note: link.type === 'link' ? link.note || '' : '',
  title: link.type === 'text' ? link.title || '' : '',
  content: link.type === 'text' ? link.content || '' : '',
})

/** 编辑草稿 → DisplayLink；返回错误消息或解析结果 */
const toDisplayLink = (draft: LinkDraft, index: number): { link?: DisplayLink; error?: string } => {
  const name = draft.name.trim()
  if (!name) return { error: `第 ${index + 1} 个入口：名称不能为空` }
  if (draft.type === 'link') {
    const url = draft.url.trim()
    if (!url) return { error: `入口「${name}」：链接地址不能为空` }
    if (!/^https?:\/\//i.test(url)) return { error: `入口「${name}」：链接地址必须以 http:// 或 https:// 开头` }
    const note = draft.note.trim()
    return { link: { name, type: 'link', url, ...(note ? { note } : {}) } }
  }
  const title = draft.title.trim()
  if (!title) return { error: `入口「${name}」：弹窗标题不能为空` }
  const content = draft.content.trim()
  if (!content) return { error: `入口「${name}」：内容不能为空` }
  return { link: { name, type: 'text', title, content } }
}

// ==================== 组件 ====================

interface ItemQueryConfigModalProps {
  /** 账号 cookie_id（草稿模式下可空） */
  cookieId?: string
  /** 商品ID（草稿模式下可空） */
  itemId?: string
  /** 商品名称（用于弹窗标题） */
  itemName: string
  /** 关闭回调 */
  onClose: () => void
  /** 保存成功回调（后端模式） */
  onSaved?: () => void
  /**
   * 草稿模式：不读写后端，用于素材 item_config.query_buttons 编辑。
   * 打开时以 initialButtons 初始化，保存时回调 onSavedButtons 返回解析后的按钮。
   */
  draftMode?: boolean
  /** 草稿模式初始按钮（仅打开时读取一次） */
  initialButtons?: QueryButton[]
  /** 草稿模式保存回调，回传解析后的按钮数组 */
  onSavedButtons?: (buttons: QueryButton[]) => void
}

export function ItemQueryConfigModal({
  cookieId,
  itemId,
  itemName,
  onClose,
  onSaved,
  draftMode,
  initialButtons,
  onSavedButtons,
}: ItemQueryConfigModalProps) {
  const { addToast } = useUIStore()
  const [loading, setLoading] = useState(() => !draftMode)
  const [saving, setSaving] = useState(false)
  const [drafts, setDrafts] = useState<ButtonDraft[]>(() =>
    draftMode ? (initialButtons || []).map(toDraft) : [],
  )
  // 加载失败时禁止保存：覆盖式保存会把服务端已有配置清空，必须阻止"加载失败→保存空配置"的数据丢失路径
  const [loadFailed, setLoadFailed] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)
  // 查询页顶部提示文案（metadata_json.page_hint），空串不显示；仅后端模式读写
  const [pageHint, setPageHint] = useState('')

  // 顶部 Tab：查询按钮 | 展示入口（草稿模式无后端数据源，不展示 Tab）
  const [activeTab, setActiveTab] = useState<'buttons' | 'links'>('buttons')

  // 展示入口 Tab 的独立状态：切到该 Tab 时才加载（懒加载），独立保存
  const [linksLoading, setLinksLoading] = useState(false)
  const [linksLoadFailed, setLinksLoadFailed] = useState(false)
  const [linkDrafts, setLinkDrafts] = useState<LinkDraft[]>([])
  const [linksSaving, setLinksSaving] = useState(false)
  // 已加载过一次标记 + 重载计数：「重新加载」时递增 linksReloadKey 触发重新拉取
  const [linksLoadedOnce, setLinksLoadedOnce] = useState(false)
  const [linksReloadKey, setLinksReloadKey] = useState(0)

  useEffect(() => {
    // 草稿模式不读后端，初始按钮在 useState 初始化时已注入
    if (draftMode) return
    const load = async () => {
      setLoading(true)
      setLoadFailed(false)
      try {
        const result = await getItemQueryButtons(cookieId!, itemId!)
        if (result.success) {
          setDrafts((result.data?.buttons || []).map(toDraft))
          setPageHint(result.data?.page_hint || '')
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
  }, [cookieId, itemId, addToast, reloadKey, draftMode])

  // 展示入口懒加载：仅在后端模式且切到该 Tab 时拉取一次；加载失败置 linksLoadFailed 禁止保存
  useEffect(() => {
    if (draftMode || activeTab !== 'links' || linksLoadedOnce) return
    let cancelled = false
    const load = async () => {
      setLinksLoading(true)
      setLinksLoadFailed(false)
      try {
        const result = await getItemDisplayLinks(cookieId!, itemId!)
        if (cancelled) return
        if (result.success) {
          setLinkDrafts((result.data?.links || []).map(linkToDraft))
          setLinksLoadedOnce(true)
        } else {
          setLinksLoadFailed(true)
          addToast({ type: 'error', message: result.message || '加载展示入口失败' })
        }
      } catch {
        if (cancelled) return
        setLinksLoadFailed(true)
        addToast({ type: 'error', message: '加载展示入口失败，请稍后重试' })
      } finally {
        if (!cancelled) setLinksLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [activeTab, draftMode, linksLoadedOnce, linksReloadKey, cookieId, itemId, addToast])

  const updateDraft = (index: number, patch: Partial<ButtonDraft>) => {
    setDrafts((prev) => prev.map((d, i) => (i === index ? { ...d, ...patch } : d)))
  }

  const addDraft = () => setDrafts((prev) => [...prev, emptyDraft()])

  const removeDraft = (index: number) => setDrafts((prev) => prev.filter((_, i) => i !== index))

  const updateLinkDraft = (index: number, patch: Partial<LinkDraft>) => {
    setLinkDrafts((prev) => prev.map((d, i) => (i === index ? { ...d, ...patch } : d)))
  }

  const addLinkDraft = () => setLinkDrafts((prev) => [...prev, emptyLinkDraft()])

  const removeLinkDraft = (index: number) => setLinkDrafts((prev) => prev.filter((_, i) => i !== index))

  // 保存「查询按钮」Tab
  const handleSaveButtons = async () => {
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
    // 草稿模式不落库，回传解析结果交由调用方写入 item_config
    if (draftMode) {
      onSavedButtons?.(buttons)
      return
    }
    setSaving(true)
    try {
      const result = await saveItemQueryButtons(cookieId!, itemId!, buttons, pageHint)
      if (result.success) {
        addToast({ type: 'success', message: '查询配置已保存' })
        onSaved?.()
      } else {
        addToast({ type: 'error', message: result.message || '保存失败，请稍后重试' })
      }
    } catch {
      addToast({ type: 'error', message: '保存失败，请稍后重试' })
    } finally {
      setSaving(false)
    }
  }

  // 保存「展示入口」Tab（整体覆盖）
  const handleSaveLinks = async () => {
    if (linksSaving) return
    const links: DisplayLink[] = []
    for (let i = 0; i < linkDrafts.length; i++) {
      const { link, error } = toDisplayLink(linkDrafts[i], i)
      if (error || !link) {
        addToast({ type: 'error', message: error || '配置校验失败' })
        return
      }
      links.push(link)
    }
    setLinksSaving(true)
    try {
      const result = await saveItemDisplayLinks(cookieId!, itemId!, links)
      if (result.success) {
        addToast({ type: 'success', message: '展示入口已保存' })
        onSaved?.()
      } else {
        addToast({ type: 'error', message: result.message || '保存失败，请稍后重试' })
      }
    } catch {
      addToast({ type: 'error', message: '保存失败，请稍后重试' })
    } finally {
      setLinksSaving(false)
    }
  }

  // 底部保存按钮按当前 Tab 分发（草稿模式只有查询按钮）
  const isLinksTab = !draftMode && activeTab === 'links'
  const handleSave = isLinksTab ? handleSaveLinks : handleSaveButtons
  const currentSaving = isLinksTab ? linksSaving : saving
  // 各 Tab 独立的保存门襟：加载中或加载失败（避免覆盖式保存清空服务端配置）时禁止保存
  const saveDisabled = isLinksTab
    ? linksSaving || linksLoading || linksLoadFailed
    : saving || loading || loadFailed

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

        {/* 顶部 Tab：查询按钮 | 展示入口（草稿模式无展示入口数据源，不展示 Tab） */}
        {!draftMode && (
          <div className="flex gap-2 px-5 pt-3 flex-shrink-0">
            {([
              { value: 'buttons', label: '查询按钮' },
              { value: 'links', label: '展示入口' },
            ] as const).map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setActiveTab(opt.value)}
                className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors border ${
                  activeTab === opt.value
                    ? 'bg-blue-600 text-white border-blue-600'
                    : 'bg-white dark:bg-slate-700 text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-600 hover:border-blue-400'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        )}

        <div className="modal-body flex-1 overflow-y-auto space-y-4">
          {activeTab === 'buttons' ? (
          loading ? (
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

              {!draftMode && (
                <div className="input-group">
                  <label className="input-label">查询页提示文案（可空，空则不显示）</label>
                  <textarea
                    value={pageHint}
                    onChange={(e) => setPageHint(e.target.value)}
                    className="input-ios h-20 resize-none text-sm"
                    placeholder="显示在查询页顶部的提示，如：会查 API 的朋友请尽量使用 API 查询"
                  />
                </div>
              )}

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
                      {!draft.enabled && <span className="ml-2 text-xs text-gray-400">(已停用)</span>}
                    </p>
                    <div className="flex items-center gap-2">
                      {/* 启用开关：停用后买家端隐藏该按钮且不可执行，配置保留 */}
                      <button
                        type="button"
                        role="switch"
                        aria-checked={draft.enabled}
                        title={draft.enabled ? '点击停用' : '点击启用'}
                        onClick={() => updateDraft(index, { enabled: !draft.enabled })}
                        className={`relative w-9 h-5 rounded-full transition-colors ${draft.enabled ? 'bg-blue-500' : 'bg-gray-300 dark:bg-gray-600'}`}
                      >
                        <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${draft.enabled ? 'left-[18px]' : 'left-0.5'}`} />
                      </button>
                      <button
                        type="button"
                        onClick={() => removeDraft(index)}
                        className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/30 text-red-500"
                        title="删除该按钮"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
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
          )
          ) : linksLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : linksLoadFailed ? (
            <div className="flex flex-col items-center gap-3 py-8">
              <p className="text-sm text-red-500">展示入口加载失败，为避免误清空已有配置，已禁止保存</p>
              <button
                type="button"
                onClick={() => setLinksReloadKey((k) => k + 1)}
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
                  <li>展示入口显示在买家提货页底部工具区，随商品独立配置</li>
                  <li>「链接」类型：点击新窗口打开链接地址，备注（如提取码）显示在按钮右侧</li>
                  <li>「文本」类型：点击弹窗展示内容，内容中的 {'{cookie}'} 会替换为发货内容里的 Cookie</li>
                </ul>
              </div>

              {linkDrafts.length === 0 && (
                <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
                  暂无展示入口，点击下方「添加入口」创建
                </p>
              )}

              {linkDrafts.map((draft, index) => (
                <div
                  key={index}
                  className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 space-y-3"
                >
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                      入口 {index + 1}{draft.name ? `：${draft.name}` : ''}
                      <span className="ml-2 text-xs text-gray-400">
                        {draft.type === 'link' ? '链接' : '文本'}
                      </span>
                    </p>
                    <button
                      type="button"
                      onClick={() => removeLinkDraft(index)}
                      className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/30 text-red-500"
                      title="删除该入口"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="input-group sm:col-span-2">
                      <label className="input-label">名称</label>
                      <input
                        type="text"
                        value={draft.name}
                        onChange={(e) => updateLinkDraft(index, { name: e.target.value })}
                        className="input-ios"
                        placeholder="如：查询工具下载"
                      />
                    </div>
                    <div className="input-group">
                      <label className="input-label">类型</label>
                      <select
                        value={draft.type}
                        onChange={(e) => updateLinkDraft(index, { type: e.target.value as 'link' | 'text' })}
                        className="input-ios"
                      >
                        <option value="link">链接</option>
                        <option value="text">文本</option>
                      </select>
                    </div>
                  </div>

                  {draft.type === 'link' && (
                    <>
                      <div className="input-group">
                        <label className="input-label">链接地址</label>
                        <input
                          type="text"
                          value={draft.url}
                          onChange={(e) => updateLinkDraft(index, { url: e.target.value })}
                          className="input-ios"
                          placeholder="https://example.com/download"
                        />
                      </div>
                      <div className="input-group">
                        <label className="input-label">备注（可选，显示在按钮右侧）</label>
                        <input
                          type="text"
                          value={draft.note}
                          onChange={(e) => updateLinkDraft(index, { note: e.target.value })}
                          className="input-ios"
                          placeholder="如：提取码：abcd"
                        />
                      </div>
                    </>
                  )}

                  {draft.type === 'text' && (
                    <>
                      <div className="input-group">
                        <label className="input-label">弹窗标题</label>
                        <input
                          type="text"
                          value={draft.title}
                          onChange={(e) => updateLinkDraft(index, { title: e.target.value })}
                          className="input-ios"
                          placeholder="如：余额查询 API"
                        />
                      </div>
                      <div className="input-group">
                        <label className="input-label">内容（多行文本，可用 {'{cookie}'} 变量）</label>
                        <textarea
                          value={draft.content}
                          onChange={(e) => updateLinkDraft(index, { content: e.target.value })}
                          className="input-ios h-32 resize-none font-mono text-sm"
                          placeholder={'接口：GET https://example.com/api\n请求头：\nCookie: {cookie}'}
                        />
                        <p className="text-xs text-gray-500 mt-1">
                          {'{cookie}'} 会在买家打开时替换为发货内容中的 Cookie
                        </p>
                      </div>
                    </>
                  )}
                </div>
              ))}

              <button
                type="button"
                onClick={addLinkDraft}
                className="flex items-center justify-center gap-1.5 w-full px-4 py-2 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 text-sm text-gray-600 dark:text-gray-400 hover:border-blue-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
              >
                <Plus className="w-4 h-4" />
                添加入口
              </button>
            </>
          )}
        </div>

        <div className="modal-footer flex-shrink-0 flex justify-end gap-2">
          <button onClick={onClose} className="btn-ios-secondary" disabled={currentSaving}>
            取消
          </button>
          <button
            onClick={handleSave}
            className="btn-ios-primary"
            disabled={saveDisabled}
          >
            {currentSaving ? (
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
