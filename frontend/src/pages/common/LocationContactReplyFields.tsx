import { useState } from 'react'
import { MapPin } from 'lucide-react'
import AddressPickerModal from '../product-publish/AddressPickerModal'

export interface LocationContactReplyValue {
  location_name: string
  location_longitude: string
  location_latitude: string
  location_title: string
  location_subtitle: string
}

export const DEFAULT_LOCATION_TITLE = '微信:123456'

interface Props {
  value: LocationContactReplyValue
  onChange: (value: LocationContactReplyValue) => void
  disabled?: boolean
}

export function LocationContactReplyFields({ value, onChange, disabled = false }: Props) {
  const [open, setOpen] = useState(false)
  const update = (patch: Partial<LocationContactReplyValue>) => onChange({ ...value, ...patch })

  return (
    <div className="space-y-3 rounded-lg border border-blue-200 bg-blue-50/60 p-3 dark:border-blue-800 dark:bg-blue-900/20">
      <p className="text-sm font-medium text-red-600 dark:text-red-400">
        通过地图定位功能发送联系方式给买家
      </p>
      <div className="input-group">
        <label className="input-label">定位信息</label>
        <button type="button" disabled={disabled} className="input-ios flex items-center gap-2 text-left" onClick={() => setOpen(true)}>
          <MapPin className="h-4 w-4 flex-shrink-0 text-blue-500" />
          <span className={`min-w-0 flex-1 truncate ${value.location_name ? 'text-slate-700 dark:text-slate-200' : 'text-slate-400'}`}>
            {value.location_name || '请选择定位信息'}
          </span>
        </button>
        {value.location_longitude && value.location_latitude && (
          <p className="mt-1 text-xs text-slate-500">经度 {value.location_longitude}，纬度 {value.location_latitude}</p>
        )}
      </div>
      <div className="input-group">
        <label className="input-label">标题(买家能看到的信息)</label>
        <input type="text" maxLength={128} className="input-ios" value={value.location_title || DEFAULT_LOCATION_TITLE} disabled={disabled} onChange={(e) => update({ location_title: e.target.value })} placeholder={DEFAULT_LOCATION_TITLE} />
      </div>
      <div className="input-group">
        <label className="input-label">副标题（选填）</label>
        <input type="text" maxLength={255} className="input-ios" value={value.location_subtitle} disabled={disabled} onChange={(e) => update({ location_subtitle: e.target.value })} placeholder="请输入位置副标题" />
      </div>
      <AddressPickerModal
        open={open}
        currentValue={value.location_name}
        onClose={() => setOpen(false)}
        onSelect={(address, expectedText, location) => {
          const [longitude = '', latitude = ''] = (location || '').split(',').map((part) => part.trim())
          update({ location_name: expectedText || address, location_longitude: longitude, location_latitude: latitude })
          setOpen(false)
        }}
      />
    </div>
  )
}

export default LocationContactReplyFields
