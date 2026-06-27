/**
 * 批量修改监控任务分类弹窗
 *
 * 功能：
 * 1. 对勾选的多个监控任务，批量设置「所属分类」（必选）
 * 2. 分类来自分类列表（普通用户仅见自己的分类，管理员可见全部）
 * 说明：弹窗只能通过按钮关闭（不点击遮罩关闭）。
 */
import { useEffect, useState } from 'react'
import { Loader2, X } from 'lucide-react'
import { batchUpdateListingMonitorCategory } from '@/api/listingMonitor'
import { getListingMonitorCategories } from '@/api/listingMonitorCategory'
import { Select } from '@/components/common/Select'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

interface BatchCategoryModalProps {
  taskIds: number[]
  onClose: () => void
  onSaved: () => void
}

export function BatchCategoryModal({ taskIds, onClose, onSaved }: BatchCategoryModalProps) {
  const { addToast } = useUIStore()
  const [categoryOptions, setCategoryOptions] = useState<{ value: string; label: string }[]>([])
  const [categoryId, setCategoryId] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    const loadCategories = async () => {
      try {
        const result = await getListingMonitorCategories()
        if (result.success && result.data) {
          setCategoryOptions(result.data.map((c) => ({ value: String(c.id), label: c.name })))
        } else {
          addToast({ type: 'error', message: result.message || '加载分类列表失败' })
        }
      } catch (error) {
        addToast({ type: 'error', message: getApiErrorMessage(error, '加载分类列表失败') })
      }
    }
    void loadCategories()
  }, [addToast])

  const handleSave = async () => {
    if (!categoryId) {
      addToast({ type: 'warning', message: '请选择分类' })
      return
    }
    setSaving(true)
    try {
      const result = await batchUpdateListingMonitorCategory(taskIds, Number(categoryId))
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '批量修改分类失败' })
        return
      }
      addToast({ type: 'success', message: result.message || '批量修改分类成功' })
      onSaved()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '批量修改分类失败') })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-lg bg-white dark:bg-slate-800 rounded-2xl shadow-xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-200 dark:border-slate-700">
          <h3 className="text-base font-semibold text-slate-800 dark:text-slate-100">
            批量修改分类（{taskIds.length} 条任务）
          </h3>
          <button className="modal-close" onClick={onClose} disabled={saving}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-5 py-4 space-y-3">
          <div className="input-group">
            <label className="input-label">目标分类 <span className="text-red-500">*</span></label>
            <Select
              value={categoryId}
              onChange={setCategoryId}
              options={categoryOptions}
              placeholder={categoryOptions.length === 0 ? '暂无分类，请先到「监控分类」新建' : '请选择分类'}
            />
          </div>
          <p className="text-xs text-slate-400">将选中的监控任务统一归入所选分类。</p>
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

export default BatchCategoryModal
