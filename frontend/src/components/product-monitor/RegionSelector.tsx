import { useEffect, useMemo, useRef, useState } from 'react'
import regionTreeData from '@/data/goofishRegions.json'
import { Select } from '@/components/common/Select'

type RegionTree = Record<string, Record<string, string[]>>

interface RegionSelectorProps {
  province: string
  city: string
  district: string
  onChange: (value: { province: string; city: string; district: string }) => void
}

const regionTree = regionTreeData as RegionTree
const directMunicipalities = new Set(['北京', '天津', '上海', '重庆'])

const toOptions = (values: string[]) => values.map((value) => ({ value, label: value }))

/**
 * 闲鱼地区三级联动。
 *
 * 数据来自闲鱼网页“区域”选择器快照，值保持与闲鱼筛选请求一致，
 * 包括“全广东 / 全深圳”等官方全区域选项。
 */
export function RegionSelector({ province, city, district, onChange }: RegionSelectorProps) {
  const [blockedHint, setBlockedHint] = useState('')
  const hintTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const isNationwideGroup = province === '全国'
  const isDirectMunicipality = directMunicipalities.has(province)
  const provinceOptions = useMemo(() => toOptions(Object.keys(regionTree)), [])
  const cityOptions = useMemo(
    () => toOptions(province ? Object.keys(regionTree[province] || {}) : []),
    [province]
  )
  const districtOptions = useMemo(
    () => toOptions(province && city ? regionTree[province]?.[city] || [] : []),
    [province, city]
  )

  const handleProvinceChange = (nextProvince: string) => {
    setBlockedHint('')
    onChange({ province: nextProvince, city: '', district: '' })
  }

  const handleCityChange = (nextCity: string) => {
    setBlockedHint('')
    onChange({ province, city: nextCity, district: '' })
  }

  const handleDistrictChange = (nextDistrict: string) => {
    setBlockedHint('')
    onChange({ province, city, district: nextDistrict })
  }

  const resetRegion = () => {
    setBlockedHint('')
    onChange({ province: '', city: '', district: '' })
  }

  const showBlockedHint = (message: string) => {
    setBlockedHint(message)
    if (hintTimerRef.current) clearTimeout(hintTimerRef.current)
    hintTimerRef.current = setTimeout(() => setBlockedHint(''), 3000)
  }

  useEffect(() => () => {
    if (hintTimerRef.current) clearTimeout(hintTimerRef.current)
  }, [])

  const districtDisabled = !city || isNationwideGroup || isDirectMunicipality || districtOptions.length === 0
  const districtBlockedHint = !province
    ? '请先选择省份/全国'
    : !city
      ? '请先选择城市'
      : '当前地区无需选择区/县'

  return (
    <div className="input-group">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-baseline gap-1">
          <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">地区</span>
          <span className="text-xs font-normal text-slate-400">（不选择默认为全国）</span>
        </div>
        <button
          type="button"
          onClick={resetRegion}
          disabled={!province && !city && !district}
          className="text-xs text-blue-600 dark:text-blue-400 hover:underline disabled:text-slate-300 dark:disabled:text-slate-600 disabled:no-underline disabled:cursor-not-allowed"
        >
          重置
        </button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <Select
          value={province}
          onChange={handleProvinceChange}
          options={provinceOptions}
          placeholder="选择省份/全国"
        />
        <div className="relative">
          <Select
            value={city}
            onChange={handleCityChange}
            options={cityOptions}
            placeholder="选择城市"
            disabled={!province}
          />
          {!province && (
            <button
              type="button"
              aria-label="选择城市：请先选择省份/全国"
              title="请先选择省份/全国"
              className="absolute inset-0 z-10 rounded-md cursor-not-allowed"
              onClick={() => showBlockedHint('请先选择省份/全国')}
            />
          )}
        </div>
        <div className="relative">
          <Select
            value={district}
            onChange={handleDistrictChange}
            options={districtOptions}
            placeholder="选择区/县"
            disabled={districtDisabled}
          />
          {districtDisabled && (
            <button
              type="button"
              aria-label={`选择区/县：${districtBlockedHint}`}
              title={districtBlockedHint}
              className="absolute inset-0 z-10 rounded-md cursor-not-allowed"
              onClick={() => showBlockedHint(districtBlockedHint)}
            />
          )}
        </div>
      </div>
      {blockedHint && (
        <p
          role="alert"
          aria-live="assertive"
          className="mt-2 text-xs font-medium text-amber-600 dark:text-amber-400"
        >
          {blockedHint}
        </p>
      )}
    </div>
  )
}
