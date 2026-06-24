/**
 * 批量修改监控任务私信内容弹窗
 *
 * 功能：
 * 1. 对勾选的多个监控任务，批量设置统一的「私信内容」（必填）
 * 2. 内容长度上限 1000 字
 * 说明：弹窗只能通过按钮关闭（不点击遮罩关闭）；批量仅支持设置，不支持清空（清空请逐条编辑）。
 */
import { useState } from 'react'
import { Loader2, X } from 'lucide-react'
import { batchUpdateListingMonitorDmContent } from '@/api/listingMonitor'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

interface BatchDmContentModalProps {
  taskIds: number[]
  onClose: () => void
  onSaved: () => void
}

const MAX_LENGTH = 1000

export function BatchDmContentModal({ taskIds, onClose, onSaved }: BatchDmContentModalProps) {
  const { addToast } = useUIStore()
  const [dmContent, setDmContent] = useState('')
  const [saving, setSaving] = useState(false)

  const handleSave = async () => {
    const content = dmContent.trim()
    if (!content) {
      addToast({ type: 'warning', message: '请输入私信内容' })
      return
    }
    if (content.length > MAX_LENGTH) {
      addToast({ type: 'warning', message: `私信内容长度不能超过${MAX_LENGTH}个字符` })
      return
    }
    setSaving(true)
    try {
      const result = await batchUpdateListingMonitorDmContent(taskIds, content)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '批量修改私信内容失败' })
        return
      }
      addToast({ type: 'success', message: result.message || '批量修改私信内容成功' })
      onSaved()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '批量修改私信内容失败') })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg bg-white dark:bg-slate-800 rounded-2xl shadow-xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 dark:border-slate-700">
          <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">
            批量修改私信内容（{taskIds.length} 条任务）
          </h3>
          <button className="modal-close" onClick={onClose} disabled={saving}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <div className="input-group">
            <label className="input-label">私信内容 <span className="text-red-500">*</span></label>
            <textarea
              className="input-ios min-h-[120px] resize-y"
              placeholder="请输入要批量设置的私信内容（最多 1000 字）"
              value={dmContent}
              maxLength={MAX_LENGTH}
              onChange={(e) => setDmContent(e.target.value)}
            />
            <p className="text-xs text-slate-400 mt-1 text-right">{dmContent.length}/{MAX_LENGTH}</p>
          </div>
          <p className="text-xs text-slate-400">将选中的监控任务统一设置为以上私信内容（仅设置，不支持批量清空）。</p>
        </div>

        <div className="flex justify-end gap-3 px-5 py-4 border-t border-slate-200 dark:border-slate-700">
          <button className="btn-ios-secondary" onClick={onClose} disabled={saving}>取消</button>
          <button className="btn-ios-primary" onClick={() => void handleSave()} disabled={saving}>
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            确认修改
          </button>
        </div>
      </div>
    </div>
  )
}

export default BatchDmContentModal
