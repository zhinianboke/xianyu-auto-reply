/**
 * 通用展示入口管理弹窗
 *
 * 用户级模板（/api/v1/display-link-templates），供所有商品复用：
 * 标记「默认展示」的入口由提货页在读取商品自身配置后合并（按名称去重，商品自身配置优先）。
 *
 * 列表内的「默认展示」开关走单字段 PUT（乐观更新，失败回滚）；
 * 表单为内联编辑，新增与编辑共用一份草稿，字段按类型收敛（与商品配置弹窗一致）。
 */
import { useEffect, useRef, useState } from 'react'
import { Image as ImageIcon, Loader2, Pencil, Plus, Trash2, X } from 'lucide-react'
import {
  createDisplayLinkTemplate,
  deleteDisplayLinkTemplate,
  getDisplayLinkTemplates,
  updateDisplayLinkTemplate,
  uploadDisplayLinkTemplateImage,
  type DisplayLinkTemplate,
  type DisplayLinkTemplatePayload,
} from '@/api/displayLinkTemplates'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { getApiErrorMessage } from '@/utils/request'
import { useUIStore } from '@/store/uiStore'

/** 表单草稿：三类字段平铺，保存时按 type 收敛为 payload */
interface TemplateDraft {
  name: string
  type: 'link' | 'text' | 'image'
  /** link / image 使用 */
  url: string
  /** link / image 使用，可选（如「提取码：xxxx」「扫码进群」） */
  note: string
  /** 仅 text 使用（弹窗标题） */
  title: string
  /** 仅 text 使用（多行文本，支持 {cookie} 占位符） */
  content: string
}

const emptyDraft = (): TemplateDraft => ({
  name: '',
  type: 'link',
  url: '',
  note: '',
  title: '',
  content: '',
})

/** 模板 → 编辑草稿 */
const toDraft = (tpl: DisplayLinkTemplate): TemplateDraft => ({
  name: tpl.name || '',
  type: tpl.type,
  url: tpl.type === 'text' ? '' : tpl.url || '',
  note: tpl.type === 'text' ? '' : tpl.note || '',
  title: tpl.type === 'text' ? tpl.title || '' : '',
  content: tpl.type === 'text' ? tpl.content || '' : '',
})

const TYPE_LABELS: Record<TemplateDraft['type'], string> = {
  link: '链接',
  text: '文本',
  image: '图片',
}

/** 草稿 → 接口 payload（不含 is_default，开关单独提交）；返回错误消息或 payload */
const toPayload = (draft: TemplateDraft): { payload?: DisplayLinkTemplatePayload; error?: string } => {
  const name = draft.name.trim()
  if (!name) return { error: '名称不能为空' }
  if (draft.type === 'link') {
    const url = draft.url.trim()
    if (!url) return { error: '链接地址不能为空' }
    if (!/^https?:\/\//i.test(url)) return { error: '链接地址必须以 http:// 或 https:// 开头' }
    // 空备注也要提交：PUT 为部分更新语义，缺省字段会保留服务端旧值，导致备注清不掉
    return { payload: { name, type: 'link', url, note: draft.note.trim() } }
  }
  if (draft.type === 'image') {
    const url = draft.url.trim()
    if (!url) return { error: '请上传图片或填写图片地址' }
    if (!(url.startsWith('/static/') || url.startsWith('http://') || url.startsWith('https://'))) {
      return { error: '图片地址必须是 /static 开头的站内路径或 http(s) 链接' }
    }
    return { payload: { name, type: 'image', url, note: draft.note.trim() } }
  }
  const title = draft.title.trim()
  if (!title) return { error: '弹窗标题不能为空' }
  const content = draft.content.trim()
  if (!content) return { error: '内容不能为空' }
  return { payload: { name, type: 'text', title, content } }
}

interface DisplayLinkTemplatesModalProps {
  visible: boolean
  onClose: () => void
}

export function DisplayLinkTemplatesModal({ visible, onClose }: DisplayLinkTemplatesModalProps) {
  const { addToast } = useUIStore()
  const [templates, setTemplates] = useState<DisplayLinkTemplate[]>([])
  const [loading, setLoading] = useState(false)
  // 加载失败时不展示空态（避免用户误以为没有模板而重复创建），改为内联错误 + 重试
  const [loadFailed, setLoadFailed] = useState(false)
  const [reloadKey, setReloadKey] = useState(0)

  // 表单：editingId 为 null 表示新增
  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<number | null>(null)
  const [draft, setDraft] = useState<TemplateDraft>(emptyDraft)
  const [saving, setSaving] = useState(false)
  const [uploading, setUploading] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  // 表单渲染在列表之后，打开时滚动到可见处，避免长列表下看不到表单
  const formRef = useRef<HTMLDivElement>(null)

  // 默认开关：请求中的行（同一行请求期间禁用，避免重复提交与回滚错乱）
  const [togglingDefault, setTogglingDefault] = useState<Record<number, boolean>>({})
  const [deleteConfirm, setDeleteConfirm] = useState<{ open: boolean; template: DisplayLinkTemplate | null }>({
    open: false,
    template: null,
  })
  const [deleting, setDeleting] = useState(false)

  useEffect(() => {
    if (!visible) return
    let cancelled = false
    const load = async () => {
      setLoading(true)
      setLoadFailed(false)
      try {
        const list = await getDisplayLinkTemplates()
        if (!cancelled) setTemplates(list)
      } catch (err) {
        if (cancelled) return
        setLoadFailed(true)
        addToast({ type: 'error', message: getApiErrorMessage(err, '获取通用展示入口失败，请稍后重试') })
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [visible, reloadKey, addToast])

  // 关闭后清空表单/确认框，避免下次打开残留上一次的编辑内容
  useEffect(() => {
    if (visible) return
    setFormOpen(false)
    setEditingId(null)
    setDraft(emptyDraft())
    setDeleteConfirm({ open: false, template: null })
  }, [visible])

  useEffect(() => {
    if (!formOpen) return
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [formOpen, editingId])

  const openCreateForm = () => {
    setEditingId(null)
    setDraft(emptyDraft())
    setFormOpen(true)
  }

  const openEditForm = (tpl: DisplayLinkTemplate) => {
    setEditingId(tpl.id)
    setDraft(toDraft(tpl))
    setFormOpen(true)
  }

  const closeForm = () => {
    setFormOpen(false)
    setEditingId(null)
    setDraft(emptyDraft())
  }

  /** 上传图片并回填草稿的图片地址 */
  const handleUploadImage = async (file: File) => {
    if (!file.type.startsWith('image/')) {
      addToast({ type: 'error', message: '请选择图片文件' })
      return
    }
    if (file.size > 5 * 1024 * 1024) {
      addToast({ type: 'error', message: '图片不能超过 5MB' })
      return
    }
    setUploading(true)
    try {
      const url = await uploadDisplayLinkTemplateImage(file)
      setDraft((prev) => ({ ...prev, url }))
      addToast({ type: 'success', message: '图片已上传' })
    } catch (err) {
      addToast({ type: 'error', message: getApiErrorMessage(err, '图片上传失败，请稍后重试') })
    } finally {
      setUploading(false)
    }
  }

  const handleSave = async () => {
    if (saving || uploading) return
    const { payload, error } = toPayload(draft)
    if (error || !payload) {
      addToast({ type: 'error', message: error || '配置校验失败' })
      return
    }
    const editId = editingId
    setSaving(true)
    try {
      const result =
        editId === null
          ? await createDisplayLinkTemplate(payload)
          : await updateDisplayLinkTemplate(editId, payload)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '保存失败，请稍后重试' })
        return
      }
      const saved = result.data
      if (saved) {
        setTemplates((prev) =>
          editId === null ? [...prev, saved] : prev.map((t) => (t.id === saved.id ? saved : t)),
        )
      } else {
        // 响应缺少数据时回源，保证列表与后端一致
        setReloadKey((k) => k + 1)
      }
      addToast({ type: 'success', message: editId === null ? '通用入口已创建' : '通用入口已更新' })
      closeForm()
    } catch (err) {
      addToast({ type: 'error', message: getApiErrorMessage(err, '保存失败，请稍后重试') })
    } finally {
      setSaving(false)
    }
  }

  /** 切换「默认展示」：先改本地再提交，失败回滚为原值 */
  const handleToggleDefault = async (tpl: DisplayLinkTemplate) => {
    if (togglingDefault[tpl.id]) return
    const next = !tpl.is_default
    setTemplates((prev) => prev.map((t) => (t.id === tpl.id ? { ...t, is_default: next } : t)))
    setTogglingDefault((prev) => ({ ...prev, [tpl.id]: true }))
    try {
      const result = await updateDisplayLinkTemplate(tpl.id, { is_default: next })
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '更新失败，请稍后重试' })
        setTemplates((prev) => prev.map((t) => (t.id === tpl.id ? { ...t, is_default: tpl.is_default } : t)))
      }
    } catch (err) {
      addToast({ type: 'error', message: getApiErrorMessage(err, '更新失败，请稍后重试') })
      setTemplates((prev) => prev.map((t) => (t.id === tpl.id ? { ...t, is_default: tpl.is_default } : t)))
    } finally {
      setTogglingDefault((prev) => {
        const nextState = { ...prev }
        delete nextState[tpl.id]
        return nextState
      })
    }
  }

  const handleDelete = async () => {
    const target = deleteConfirm.template
    if (!target || deleting) return
    setDeleting(true)
    try {
      const result = await deleteDisplayLinkTemplate(target.id)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '删除失败，请稍后重试' })
        return
      }
      setTemplates((prev) => prev.filter((t) => t.id !== target.id))
      if (editingId === target.id) closeForm()
      setDeleteConfirm({ open: false, template: null })
      addToast({ type: 'success', message: '通用入口已删除' })
    } catch (err) {
      addToast({ type: 'error', message: getApiErrorMessage(err, '删除失败，请稍后重试') })
    } finally {
      setDeleting(false)
    }
  }

  if (!visible) return null

  return (
    <>
      <div className="modal-overlay" style={{ zIndex: 60 }}>
        <div className="modal-content max-w-3xl max-h-[90vh] overflow-hidden flex flex-col">
          <div className="modal-header flex items-center justify-between flex-shrink-0">
            <div>
              <h2 className="modal-title flex items-center gap-2">
                <ImageIcon className="w-5 h-5 text-blue-500" />
                通用展示入口
              </h2>
              <p className="text-sm text-gray-500 mt-1">
                标记为『默认展示』的入口会自动出现在所有商品的提卡页底部（按名称去重，商品自身配置优先）
              </p>
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
                <p className="text-sm text-red-500">通用展示入口加载失败，请重试</p>
                <button type="button" onClick={() => setReloadKey((k) => k + 1)} className="btn-ios-secondary text-sm">
                  重新加载
                </button>
              </div>
            ) : (
              <>
                {templates.length === 0 && !formOpen && (
                  <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
                    暂无通用展示入口，点击下方「新增通用入口」创建
                  </p>
                )}

                {templates.map((tpl) => (
                  <div
                    key={tpl.id}
                    className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 flex items-center justify-between gap-3"
                  >
                    <div className="min-w-0 flex items-center gap-2">
                      <span className="flex-shrink-0 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] text-slate-500 dark:bg-slate-700 dark:text-slate-300">
                        {TYPE_LABELS[tpl.type]}
                      </span>
                      <span className="text-sm font-medium text-gray-700 dark:text-gray-300 truncate">{tpl.name}</span>
                    </div>
                    <div className="flex-shrink-0 flex items-center gap-3">
                      <div className="flex items-center gap-1.5">
                        <button
                          type="button"
                          role="switch"
                          aria-checked={tpl.is_default}
                          aria-label="默认展示"
                          title={tpl.is_default ? '点击取消默认展示' : '点击设为默认展示'}
                          disabled={togglingDefault[tpl.id]}
                          onClick={() => handleToggleDefault(tpl)}
                          className={`relative w-9 h-5 rounded-full transition-colors disabled:opacity-60 ${
                            tpl.is_default ? 'bg-blue-500' : 'bg-gray-300 dark:bg-gray-600'
                          }`}
                        >
                          <span
                            className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-all ${
                              tpl.is_default ? 'left-[18px]' : 'left-0.5'
                            }`}
                          />
                        </button>
                        <span className="text-xs text-gray-500 dark:text-gray-400">默认展示</span>
                      </div>
                      <button
                        type="button"
                        onClick={() => openEditForm(tpl)}
                        className="p-1.5 rounded hover:bg-slate-100 dark:hover:bg-slate-700 text-slate-500"
                        title="编辑该入口"
                      >
                        <Pencil className="w-4 h-4" />
                      </button>
                      <button
                        type="button"
                        onClick={() => setDeleteConfirm({ open: true, template: tpl })}
                        className="p-1.5 rounded hover:bg-red-50 dark:hover:bg-red-900/30 text-red-500"
                        title="删除该入口"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}

                {formOpen ? (
                  <div
                    ref={formRef}
                    className="border border-blue-200 dark:border-blue-900/50 rounded-lg p-4 space-y-3"
                  >
                    <div className="flex items-center justify-between">
                      <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                        {editingId === null ? '新增通用入口' : '编辑通用入口'}
                      </p>
                      <button type="button" onClick={closeForm} className="modal-close" title="取消编辑">
                        <X className="w-4 h-4" />
                      </button>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                      <div className="input-group sm:col-span-2">
                        <label className="input-label">名称</label>
                        <input
                          type="text"
                          value={draft.name}
                          onChange={(e) => setDraft((prev) => ({ ...prev, name: e.target.value }))}
                          className="input-ios"
                          placeholder="如：查询工具下载"
                        />
                      </div>
                      <div className="input-group">
                        <label className="input-label">类型</label>
                        <select
                          value={draft.type}
                          onChange={(e) =>
                            setDraft((prev) => ({ ...prev, type: e.target.value as TemplateDraft['type'] }))
                          }
                          className="input-ios"
                        >
                          <option value="link">链接</option>
                          <option value="text">文本</option>
                          <option value="image">图片</option>
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
                            onChange={(e) => setDraft((prev) => ({ ...prev, url: e.target.value }))}
                            className="input-ios"
                            placeholder="https://example.com/download"
                          />
                        </div>
                        <div className="input-group">
                          <label className="input-label">备注（可选，显示在按钮右侧）</label>
                          <input
                            type="text"
                            value={draft.note}
                            onChange={(e) => setDraft((prev) => ({ ...prev, note: e.target.value }))}
                            className="input-ios"
                            placeholder="如：提取码：abcd"
                          />
                        </div>
                      </>
                    )}

                    {draft.type === 'image' && (
                      <>
                        <div className="input-group">
                          <label className="input-label">图片地址</label>
                          <input
                            ref={fileInputRef}
                            type="file"
                            accept="image/*"
                            className="hidden"
                            onChange={(e) => {
                              const file = e.target.files?.[0]
                              // 清空 value，使同一文件再次选择时仍触发 change
                              e.target.value = ''
                              if (file) handleUploadImage(file)
                            }}
                          />
                          <div className="flex items-center gap-2">
                            <button
                              type="button"
                              className="btn-ios-secondary"
                              onClick={() => fileInputRef.current?.click()}
                              disabled={uploading}
                            >
                              {uploading ? '上传中...' : '上传图片'}
                            </button>
                            <span className="text-xs text-slate-400">
                              支持 jpg/png 等图片，不超过 5MB；或直接粘贴图片链接
                            </span>
                          </div>
                          <input
                            type="text"
                            value={draft.url}
                            onChange={(e) => setDraft((prev) => ({ ...prev, url: e.target.value }))}
                            className="input-ios"
                            placeholder="/static/uploads/display_links/xxx.png 或 https://..."
                          />
                          {draft.url && (
                            <img
                              src={draft.url}
                              alt="预览"
                              className="mt-2 max-h-32 rounded border border-slate-200 object-contain dark:border-slate-700"
                            />
                          )}
                        </div>
                        <div className="input-group">
                          <label className="input-label">备注（可选）</label>
                          <input
                            type="text"
                            value={draft.note}
                            onChange={(e) => setDraft((prev) => ({ ...prev, note: e.target.value }))}
                            className="input-ios"
                            placeholder="如：扫码进群"
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
                            onChange={(e) => setDraft((prev) => ({ ...prev, title: e.target.value }))}
                            className="input-ios"
                            placeholder="如：余额查询 API"
                          />
                        </div>
                        <div className="input-group">
                          <label className="input-label">内容（多行文本，可用 {'{cookie}'} 变量）</label>
                          <textarea
                            value={draft.content}
                            onChange={(e) => setDraft((prev) => ({ ...prev, content: e.target.value }))}
                            className="input-ios h-32 resize-none font-mono text-sm"
                            placeholder={'接口：GET https://example.com/api\n请求头：\nCookie: {cookie}'}
                          />
                          <p className="text-xs text-gray-500 mt-1">
                            {'{cookie}'} 会在买家打开时替换为发货内容中的 Cookie
                          </p>
                        </div>
                      </>
                    )}

                    <div className="flex justify-end gap-2">
                      <button type="button" onClick={closeForm} className="btn-ios-secondary" disabled={saving}>
                        取消
                      </button>
                      <button
                        type="button"
                        onClick={handleSave}
                        className="btn-ios-primary"
                        disabled={saving || uploading}
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
                ) : (
                  <button
                    type="button"
                    onClick={openCreateForm}
                    className="flex items-center justify-center gap-1.5 w-full px-4 py-2 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 text-sm text-gray-600 dark:text-gray-400 hover:border-blue-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                  >
                    <Plus className="w-4 h-4" />
                    新增通用入口
                  </button>
                )}
              </>
            )}
          </div>

          <div className="modal-footer flex-shrink-0 flex justify-end gap-2">
            <button onClick={onClose} className="btn-ios-secondary">
              关闭
            </button>
          </div>
        </div>
      </div>

      <ConfirmModal
        isOpen={deleteConfirm.open}
        title="删除确认"
        message={`确定要删除通用入口「${deleteConfirm.template?.name || ''}」吗？已引用该入口的商品配置不受影响。`}
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={handleDelete}
        onCancel={() => setDeleteConfirm({ open: false, template: null })}
      />
    </>
  )
}

export default DisplayLinkTemplatesModal
