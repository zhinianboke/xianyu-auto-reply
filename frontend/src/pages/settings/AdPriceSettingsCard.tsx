/** 广告费用管理卡片，费用类别与中文名称从广告类型数据字典读取。 */
import { Loader2, Megaphone, RefreshCw } from 'lucide-react'
import { useAdvertisementTypes } from '@/pages/advertisements/useAdvertisementTypes'
import type { SystemSettings } from '@/types'

interface AdPriceSettingsCardProps {
  settings: SystemSettings | null
  onChange: (key: string, value: string) => void
}
export function AdPriceSettingsCard({ settings, onChange }: AdPriceSettingsCardProps) {
  const { adTypeOptions, typesLoading, typesError, reloadTypes } = useAdvertisementTypes()
  return (
    <div className="vben-card relative" aria-busy={typesLoading}>
      <div className="vben-card-header"><h2 className="vben-card-title"><Megaphone className="h-4 w-4" />广告费用管理</h2></div>
      <div className="vben-card-body space-y-4">
        <p className="text-sm text-slate-500 dark:text-slate-400">按广告类型设置每月费用，用户申请广告时会根据此价格计算总费用</p>
        {typesError && <div className="flex flex-wrap items-center gap-3 text-sm text-red-600 dark:text-red-400" role="alert">
          {typesError}<button type="button" onClick={() => void reloadTypes()} className="btn-ios-secondary"><RefreshCw className="h-4 w-4" />重新加载</button>
        </div>}
        {adTypeOptions.map((option) => {
          const title = option.label.endsWith('广告') ? option.label : `${option.label}广告`
          return <div key={option.value} className="input-group">
            <label className="input-label" htmlFor={`ad-price-${option.value}`}>{title}（元/月）</label>
            <input id={`ad-price-${option.value}`} type="text" inputMode="decimal" value={String(settings?.[option.price_key] || '')}
              disabled={typesLoading || Boolean(typesError)} onChange={(event) => {
                const value = event.target.value
                if (value === '' || /^\d*\.?\d{0,2}$/.test(value)) onChange(option.price_key, value)
              }} placeholder={`请输入${title}每月价格`} className="input-ios" />
          </div>
        })}
      </div>
      {typesLoading && <div className="absolute inset-0 flex items-center justify-center gap-2 rounded-lg bg-white/80 text-sm text-slate-600 backdrop-blur-sm dark:bg-slate-900/80 dark:text-slate-300" role="status">
        <Loader2 className="h-5 w-5 animate-spin text-[rgb(var(--color-primary))]" />加载中...
      </div>}
    </div>
  )
}
