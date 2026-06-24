/**
 * 个人地址表单弹窗
 *
 * 功能：
 * 1. 新增个人地址
 * 2. 编辑个人地址
 */
import { useState } from 'react'
import { Loader2, X } from 'lucide-react'
import { createPersonalAddress, updatePersonalAddress, type PersonalAddress } from '@/api/personalAddresses'
import { Loading } from '@/components/common/Loading'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'

interface PersonalAddressFormModalProps {
  initial?: PersonalAddress | null
  onClose: () => void
  onSaved: (address: PersonalAddress, mode: 'create' | 'update') => void
}

export function PersonalAddressFormModal({ initial, onClose, onSaved }: PersonalAddressFormModalProps) {
  const { addToast } = useUIStore()
  const isEditMode = Boolean(initial)
  const [saving, setSaving] = useState(false)
  const [address, setAddress] = useState<string>(initial?.address ?? '')

  const handleSubmit = async () => {
    const trimmed = address.trim()
    if (!trimmed) {
      addToast({ type: 'warning', message: '请填写地址' })
      return
    }

    setSaving(true)
    try {
      const result = isEditMode && initial
        ? await updatePersonalAddress(initial.id, trimmed)
        : await createPersonalAddress(trimmed)

      if (!result.success || !result.data?.address) {
        addToast({ type: 'error', message: result.message || (isEditMode ? '保存个人地址失败' : '创建个人地址失败') })
        return
      }

      addToast({
        type: 'success',
        message: result.message || (isEditMode ? '个人地址保存成功' : '个人地址创建成功'),
      })
      onSaved(result.data.address, isEditMode ? 'update' : 'create')
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, isEditMode ? '保存个人地址失败' : '创建个人地址失败') })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay">
      {saving && <Loading fullScreen text={isEditMode ? '正在保存个人地址...' : '正在创建个人地址...'} />}
      <div className="modal-content max-w-2xl">
        <div className="modal-header">
          <h2 className="modal-title">{isEditMode ? '编辑个人地址' : '新增个人地址'}</h2>
          <button className="modal-close" onClick={onClose} disabled={saving}>
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="modal-body">
          <div className="space-y-4">
            <div className="input-group">
              <label className="input-label">地址 <span className="text-red-500">*</span></label>
              <input
                className="input-ios"
                placeholder="如：北京市朝阳区"
                value={address}
                onChange={(e) => setAddress(e.target.value)}
              />
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                发布你名下账号的商品时，会优先随机使用个人地址库中的地址作为“宝贝所在地”。
              </p>
            </div>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn-ios-secondary" onClick={onClose} disabled={saving}>取消</button>
          <button className="btn-ios-primary" onClick={handleSubmit} disabled={saving}>
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            {isEditMode ? '保存修改' : '确认新增'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default PersonalAddressFormModal
