/**
 * 平台分类属性编辑器。
 * 按闲鱼分类推荐接口返回的 cardData 顺序渲染属性，并保留品牌搜索和普通下拉两种交互。
 */
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { Check, ChevronDown, Search } from 'lucide-react'
import type {
  PlatformCategoryCandidate,
  PlatformCategoryProperty,
  PlatformCategoryPropertyOption,
  PlatformMaterialAttribute,
} from '@/api/productPublish'

interface PlatformAttributesEditorProps {
  properties: PlatformCategoryProperty[]
  attributes: PlatformMaterialAttribute[]
  candidate?: PlatformCategoryCandidate
  onChange: (attributes: PlatformMaterialAttribute[]) => void
}

export interface PlatformSelectOption {
  value: string
  label: string
  disabled?: boolean
}

interface PlatformOptionFieldProps {
  label: ReactNode
  placeholder: string
  value: string | string[]
  options: PlatformSelectOption[]
  searchable?: boolean
  multiple?: boolean
  disabled?: boolean
  onSelect: (value: string) => void
}

function optionMatchesCandidate(option: PlatformCategoryPropertyOption, candidate?: PlatformCategoryCandidate) {
  if (!candidate) return true
  const channelMatches = !option.channel_cat_id || !candidate.channel_cat_id || option.channel_cat_id === candidate.channel_cat_id
  const tbMatches = !option.tb_cat_id || !candidate.tb_cat_id || option.tb_cat_id === candidate.tb_cat_id
  return channelMatches && tbMatches
}

function optionValue(option: PlatformCategoryPropertyOption) {
  return option.value_id || option.value_name
}

function attributeKey(attribute: PlatformMaterialAttribute) {
  return attribute.property_id || attribute.property_name || ''
}

/** 平台分类和属性共用的下拉框，品牌卡启用本地筛选输入。 */
export function PlatformOptionField({
  label,
  placeholder,
  value,
  options,
  searchable = false,
  multiple = false,
  disabled = false,
  onSelect,
}: PlatformOptionFieldProps) {
  const rootRef = useRef<HTMLDivElement>(null)
  const [open, setOpen] = useState(false)
  const [keyword, setKeyword] = useState('')
  const selectedValues = Array.isArray(value) ? value : [value]
  const selectedOptions = options.filter((option) => selectedValues.includes(option.value))
  const selected = selectedOptions[0]
  const selectedLabel = multiple ? selectedOptions.map((option) => option.label).join('、') : selected?.label
  const visibleOptions = useMemo(() => {
    const normalized = keyword.trim().toLocaleLowerCase()
    if (!searchable || !normalized) return options
    return options.filter((option) => option.label.toLocaleLowerCase().includes(normalized))
  }, [keyword, options, searchable])

  useEffect(() => {
    const closeMenu = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', closeMenu)
    return () => document.removeEventListener('mousedown', closeMenu)
  }, [])

  const selectOption = (option: PlatformSelectOption) => {
    onSelect(option.value)
    setKeyword('')
    if (!multiple) setOpen(false)
  }

  return (
    <div ref={rootRef} className="input-group relative">
      <label className="input-label">{label}</label>
      {searchable ? (
        <div className="relative">
          <input
            className="input-ios pr-9"
            disabled={disabled}
            value={open ? keyword : selectedLabel || ''}
            placeholder={placeholder}
            onFocus={() => {
              setKeyword('')
              setOpen(true)
            }}
            onChange={(event) => {
              setKeyword(event.target.value)
              setOpen(true)
            }}
          />
          <Search className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        </div>
      ) : (
        <button
          type="button"
          disabled={disabled}
          className="input-ios flex w-full items-center justify-between gap-2 text-left disabled:cursor-not-allowed disabled:opacity-60"
          onClick={() => setOpen((current) => !current)}
        >
          <span className={selected ? 'truncate text-slate-700 dark:text-slate-200' : 'truncate text-slate-400'}>{selectedLabel || placeholder}</span>
          <ChevronDown className={`h-4 w-4 flex-shrink-0 text-slate-400 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>
      )}

      {open && !disabled && (
        <div className="absolute left-0 right-0 top-full z-30 mt-1 max-h-56 overflow-y-auto rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-slate-600 dark:bg-slate-800">
          {visibleOptions.length ? visibleOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              disabled={option.disabled}
              className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-45 dark:hover:bg-slate-700 ${selectedValues.includes(option.value) ? 'text-amber-600 dark:text-amber-400' : 'text-slate-700 dark:text-slate-200'}`}
              onClick={() => !option.disabled && selectOption(option)}
            >
              <span className="min-w-0 truncate">{option.label}</span>
              {selectedValues.includes(option.value) && <Check className="h-4 w-4 flex-shrink-0" />}
            </button>
          )) : <p className="px-3 py-2 text-sm text-slate-400">无匹配选项</p>}
        </div>
      )}
    </div>
  )
}

export function PlatformAttributesEditor({ properties, attributes, candidate, onChange }: PlatformAttributesEditorProps) {
  const visibleProperties = useMemo(
    () => properties.filter((property) => property.property_id && property.property_name),
    [properties],
  )

  if (!visibleProperties.length) return null

  const selectedByProperty = new Map<string, PlatformMaterialAttribute[]>()
  for (const attribute of attributes) {
    const key = attributeKey(attribute)
    const current = selectedByProperty.get(key) || []
    current.push(attribute)
    selectedByProperty.set(key, current)
  }

  const createAttribute = (property: PlatformCategoryProperty, option?: PlatformCategoryPropertyOption, textValue?: string) => {
    const valueName = option?.value_name || textValue?.trim() || ''
    if (!valueName) return null
    const valueId = option?.value_id || null
    return {
      property_id: property.property_id,
      property_name: property.property_name,
      value_id: valueId,
      value_name: valueName,
      text: valueName,
      properties: valueId ? `${property.property_id}##${property.property_name}:${valueId}##${valueName}` : null,
    } satisfies PlatformMaterialAttribute
  }

  const setPropertyValue = (property: PlatformCategoryProperty, option?: PlatformCategoryPropertyOption, textValue?: string) => {
    const propertyId = property.property_id
    const retained = attributes.filter((attribute) => attributeKey(attribute) !== propertyId)
    const current = selectedByProperty.get(propertyId) || []

    if (property.is_multiple && option) {
      const value = optionValue(option)
      const exists = current.some((attribute) => (attribute.value_id || attribute.value_name) === value)
      const nextAttribute = createAttribute(property, option)
      const updated = exists
        ? current.filter((attribute) => (attribute.value_id || attribute.value_name) !== value)
        : nextAttribute ? [...current, nextAttribute] : current
      onChange([...retained, ...updated])
      return
    }

    const nextAttribute = createAttribute(property, option, textValue)
    onChange(nextAttribute ? [...retained, nextAttribute] : retained)
  }

  return (
    <>
      {visibleProperties.map((property) => {
        const selectedValues = selectedByProperty.get(property.property_id) || []
        const selected = selectedValues[0]
        // 属性选项带有频道/淘宝分类 ID 时，只显示当前分类的选项，不能用旧分类选项兜底。
        const options = property.options.filter((option) => optionMatchesCandidate(option, candidate))
        const selectedOptions = options.filter((option) => selectedValues.some((attribute) =>
          (option.value_id && option.value_id === attribute.value_id)
          || option.value_name === attribute.value_name,
        ))
        const selectedOption = selectedOptions[0]
        const hasOptions = property.options.length > 0
        const placeholder = property.input_word ? `请输入宝贝的${property.property_name}` : `请选择${property.property_name}`

        if (hasOptions) {
          return (
            <PlatformOptionField
              key={property.property_id}
              label={property.property_name}
              placeholder={placeholder}
              value={property.is_multiple
                ? selectedOptions.map((option) => optionValue(option))
                : selectedOption ? optionValue(selectedOption) : selected?.value_id || selected?.value_name || ''}
              options={options.map((option) => ({ value: optionValue(option), label: option.value_name }))}
              searchable={Boolean(property.input_word)}
              multiple={Boolean(property.is_multiple)}
              onSelect={(value) => setPropertyValue(property, options.find((option) => optionValue(option) === value))}
            />
          )
        }

        return (
          <div className="input-group" key={property.property_id}>
            <label className="input-label">{property.property_name}</label>
            <input
              className="input-ios"
              value={selected?.value_name || ''}
              placeholder={placeholder}
              maxLength={200}
              onChange={(event) => setPropertyValue(property, undefined, event.target.value)}
              onBlur={(event) => setPropertyValue(property, undefined, event.target.value)}
            />
          </div>
        )
      })}
    </>
  )
}

export default PlatformAttributesEditor
