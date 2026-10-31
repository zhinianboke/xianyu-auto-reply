/** 广告管理与申请共享编辑弹窗，类型名称使用数据字典，扩展区由调用页面提供。 */
import type { ReactNode } from 'react'
import { Loader2, Upload, X } from 'lucide-react'
import { Select } from '@/components/common/Select'
import type { AdvertisementTypeOption } from '@/api/advertisements'
import { useAdvertisementImage } from './useAdvertisementImage'

interface FormField { value: string; onChange: (value: string) => void }
interface AdvertisementFormModalProps {
  title: string
  token: string | null
  fields: { title: FormField; content: FormField; link: FormField; image: FormField; type: FormField }
  typeOptions: AdvertisementTypeOption[]
  typesLoading: boolean
  typesError: string
  saving: boolean
  submitText?: string
  onClose: () => void
  onSave: () => void
  children?: ReactNode
}

export function AdvertisementFormModal({ title, token, fields, typeOptions, typesLoading, typesError,
  saving, submitText = '保存', onClose, onSave, children }: AdvertisementFormModalProps) {
  const { uploading, fileInputRef, handleUploadImage } = useAdvertisementImage(token, fields.image.onChange)
  return <div className="modal-overlay">
    <div className="modal-content max-w-lg">
      <div className="modal-header">
        <h2 className="text-lg font-semibold">{title}</h2>
        <button type="button" onClick={onClose} disabled={saving || uploading} aria-label="关闭" className="p-1 hover:bg-gray-100 dark:hover:bg-slate-700 rounded-lg"><X className="h-4 w-4 text-gray-500" /></button>
      </div>
      <div className="modal-body space-y-4 relative" aria-busy={typesLoading || uploading}>
        <div className="input-group"><label className="input-label">标题 *</label>
          <input value={fields.title.value} onChange={(e) => fields.title.onChange(e.target.value)} className="input-ios" maxLength={200} placeholder="广告标题" /></div>
        <div className="input-group"><label className="input-label">正文</label>
          <textarea value={fields.content.value} onChange={(e) => fields.content.onChange(e.target.value)} className="input-ios min-h-[80px] resize-none" placeholder="广告正文内容" /></div>
        <div className="input-group"><label className="input-label">广告类型</label>
          <Select value={fields.type.value} onChange={fields.type.onChange} options={typeOptions} disabled={typesLoading || Boolean(typesError)} /></div>
        {typesError && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{typesError}</p>}
        <div className="input-group"><label className="input-label">链接</label>
          <input value={fields.link.value} onChange={(e) => fields.link.onChange(e.target.value)} className="input-ios" placeholder="https://" /></div>
        {children}
        <div className="input-group"><label className="input-label">图片</label>
          {fields.image.value ? <div className="relative w-20">
            <img src={fields.image.value} alt="广告图片" className="w-20 h-20 object-cover rounded-lg border" />
            <button type="button" onClick={() => fields.image.onChange('')} aria-label="移除图片" className="absolute -top-2 -right-2 p-0.5 bg-red-500 text-white rounded-full"><X className="w-3 h-3" /></button>
          </div> : <button type="button" onClick={() => fileInputRef.current?.click()} disabled={uploading || saving} aria-label="上传图片"
            className="w-20 h-20 rounded-lg border-2 border-dashed border-slate-300 dark:border-slate-600 flex items-center justify-center text-slate-400 hover:border-[rgb(var(--color-primary))] hover:text-[rgb(var(--color-primary))]">
            {uploading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Upload className="w-5 h-5" />}
          </button>}
          <input ref={fileInputRef} type="file" accept="image/*" onChange={handleUploadImage} className="hidden" />
        </div>
        {(typesLoading || uploading) && <div role="status" className="absolute inset-0 flex items-center justify-center gap-2 bg-white/80 dark:bg-slate-900/80 backdrop-blur-sm"><Loader2 className="w-5 h-5 animate-spin" />{uploading ? '上传中...' : '加载中...'}</div>}
      </div>
      <div className="modal-footer">
        <button type="button" onClick={onClose} className="btn-ios-secondary" disabled={saving || uploading}>取消</button>
        <button type="button" onClick={onSave} className="btn-ios-primary" disabled={saving || uploading || typesLoading || Boolean(typesError)}>
          {saving && <Loader2 className="w-4 h-4 animate-spin" />}{submitText}
        </button>
      </div>
    </div>
  </div>
}
