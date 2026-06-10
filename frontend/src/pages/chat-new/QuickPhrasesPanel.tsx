/**
 * 在线聊天工作台 - 右侧快捷短语面板
 *
 * 展示与管理可复用的快捷短语：点击即发送，支持新增/编辑/删除。
 * 仅负责渲染与回调透传，数据与业务逻辑由父组件 ChatNew 维护。
 */
import { Loader2, Pencil, Plus, Save, Trash2 } from 'lucide-react'
import type { QuickPhrase } from '@/api/chatNew'

interface QuickPhrasesPanelProps {
  /** 快捷短语列表 */
  phrases: QuickPhrase[]
  /** 当前选中的会话ID，为空时禁止发送 */
  activeCid: string
  /** 消息发送中（禁止重复发送） */
  sending: boolean
  /** 正在编辑的短语ID，null 表示新增 */
  editingPhraseId: number | null
  /** 表单：标题 */
  phraseTitle: string
  /** 表单：内容 */
  phraseContent: string
  /** 保存中 */
  savingPhrase: boolean
  /** 点击短语发送内容 */
  onSend: (content: string) => void
  /** 进入编辑态 */
  onEdit: (phrase: QuickPhrase) => void
  /** 删除短语 */
  onDelete: (id: number) => void
  /** 重置表单（新增态） */
  onReset: () => void
  /** 标题输入变化 */
  onTitleChange: (value: string) => void
  /** 内容输入变化 */
  onContentChange: (value: string) => void
  /** 保存（新增或更新） */
  onSave: () => void
}

export function QuickPhrasesPanel({
  phrases,
  activeCid,
  sending,
  editingPhraseId,
  phraseTitle,
  phraseContent,
  savingPhrase,
  onSend,
  onEdit,
  onDelete,
  onReset,
  onTitleChange,
  onContentChange,
  onSave,
}: QuickPhrasesPanelProps) {
  return (
    <div className="basis-2/5 min-h-0 bg-white dark:bg-gray-800 rounded-lg shadow-sm border border-gray-200 dark:border-gray-700 flex flex-col">
      <div className="p-3 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <span className="font-medium text-sm text-gray-700 dark:text-gray-300">快捷短语</span>
        <button onClick={onReset} className="p-1 hover:bg-gray-100 dark:hover:bg-gray-700 rounded" title="新增短语"><Plus className="w-4 h-4 text-blue-500" /></button>
      </div>
      <div className="flex-1 min-h-0 overflow-y-auto p-2 space-y-1.5">
        {phrases.length === 0 ? (
          <p className="text-center text-sm text-gray-400 py-4">先在下方添加常用回复</p>
        ) : phrases.map((phrase) => (
          <div key={phrase.id} className="flex items-center gap-1 rounded-lg border border-gray-200 dark:border-gray-700 hover:border-blue-300">
            <button onClick={() => onSend(phrase.content)} disabled={!activeCid || sending} className="flex-1 min-w-0 text-left px-2.5 py-2 disabled:opacity-40" title={`点击发送：${phrase.content}`}>
              <span className="block text-xs font-medium text-gray-700 dark:text-gray-200 truncate">{phrase.title}</span>
              <span className="block text-xs text-gray-400 truncate">{phrase.content}</span>
            </button>
            <button onClick={() => onEdit(phrase)} className="p-1 text-gray-400 hover:text-blue-500" title="编辑"><Pencil className="w-3.5 h-3.5" /></button>
            <button onClick={() => onDelete(phrase.id)} className="p-1 mr-1 text-gray-400 hover:text-red-500" title="删除"><Trash2 className="w-3.5 h-3.5" /></button>
          </div>
        ))}
      </div>
      <div className="p-2 border-t border-gray-200 dark:border-gray-700 space-y-1.5">
        <input value={phraseTitle} onChange={(e) => onTitleChange(e.target.value)} placeholder="短语名称，例如：催付款" className="w-full px-2 py-1.5 text-xs border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700" />
        <div className="flex gap-1.5">
          <input value={phraseContent} onChange={(e) => onContentChange(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') onSave() }} placeholder="输入发送内容" className="flex-1 min-w-0 px-2 py-1.5 text-xs border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-700" />
          <button onClick={onSave} disabled={!phraseTitle.trim() || !phraseContent.trim() || savingPhrase} className="px-2.5 rounded bg-blue-500 text-white disabled:opacity-40" title={editingPhraseId ? '保存修改' : '添加短语'}>
            {savingPhrase ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          </button>
        </div>
      </div>
    </div>
  )
}
