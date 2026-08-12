/**
 * 商品规格编辑器。
 * 支持最多两组规格、规格值图片和自动生成 SKU 价格/库存矩阵。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { ImagePlus, Plus, Trash2, Upload, X } from 'lucide-react'
import { buildSkuKey, type ProductSpecification, type SkuRow, type SpecificationValue } from './publishTypes'

const PRESET_TYPES = ['颜色', '尺码', '容量', '份数', '大小', '高度', '总量']

interface ProductSpecificationsEditorProps {
  specifications: ProductSpecification[]
  skuRows: SkuRow[]
  onChange: (specifications: ProductSpecification[], skuRows: SkuRow[]) => void
  onUploadImage: (file: File) => Promise<string | null>
}

const createId = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`

function cartesian<T>(groups: T[][]): T[][] {
  if (!groups.length) return []
  return groups.reduce<T[][]>((result, group) => result.flatMap((row) => group.map((item) => [...row, item])), [[]])
}

export function ProductSpecificationsEditor({
  specifications,
  skuRows,
  onChange,
  onUploadImage,
}: ProductSpecificationsEditorProps) {
  const [customTypeIndex, setCustomTypeIndex] = useState<number | null>(null)
  const [customType, setCustomType] = useState('')
  const [customTypes, setCustomTypes] = useState<string[]>(() => specifications
    .map((spec) => spec.name.trim())
    .filter((name) => name && !PRESET_TYPES.includes(name)))
  const imageInputs = useRef<Record<string, HTMLInputElement | null>>({})

  useEffect(() => {
    const savedCustomTypes = specifications
      .map((spec) => spec.name.trim())
      .filter((name) => name && !PRESET_TYPES.includes(name))
    setCustomTypes((current) => {
      const next = Array.from(new Set([...current, ...savedCustomTypes]))
      return next.length === current.length && next.every((name, index) => name === current[index])
        ? current
        : next
    })
  }, [specifications])

  const generatedRows = useMemo(() => {
    const validSpecs = specifications.filter((spec) => spec.name.trim() && spec.values.some((value) => value.name.trim()))
    if (!validSpecs.length) return []
    const combinations = cartesian(validSpecs.map((spec) => spec.values.filter((value) => value.name.trim())))
    return combinations.map((values) => {
      const specs = validSpecs.reduce<Record<string, string>>((result, spec, index) => {
        result[spec.name] = values[index].name
        return result
      }, {})
      const key = buildSkuKey(validSpecs, specs)
      return { key, specs }
    })
  }, [specifications])

  useEffect(() => {
    if (!generatedRows.length) {
      if (skuRows.length) onChange(specifications, [])
      return
    }
    const previous = new Map(skuRows.map((row) => [row.key, row]))
    const nextRows: SkuRow[] = generatedRows.map(({ key, specs }) => ({
      key,
      specs,
      price: previous.get(key)?.price || '',
      stock: previous.get(key)?.stock ?? '',
    }))
    if (JSON.stringify(nextRows) !== JSON.stringify(skuRows)) onChange(specifications, nextRows)
  }, [generatedRows, onChange, skuRows, specifications])

  const updateSpecifications = (next: ProductSpecification[]) => onChange(next, skuRows)

  const startAddSpecification = () => {
    if (specifications.length >= 2) return
    const next = [...specifications, { id: createId('spec'), name: '', values: [], supportImage: false }]
    updateSpecifications(next)
    setCustomTypeIndex(next.length - 1)
  }

  const updateSpec = (specId: string, patch: Partial<ProductSpecification>) => {
    updateSpecifications(specifications.map((spec) => {
      if (spec.id !== specId) return spec
      // 关闭规格图片时同步清理图片，避免界面隐藏后仍把旧图发布出去。
      if (patch.supportImage === false) {
        return { ...spec, ...patch, values: spec.values.map((value) => ({ ...value, image: null })) }
      }
      return { ...spec, ...patch }
    }))
  }

  const addValue = (spec: ProductSpecification, rawName: string) => {
    const name = rawName.trim()
    if (!name || spec.values.some((value) => value.name === name)) return
    updateSpec(spec.id, { values: [...spec.values, { id: createId('value'), name, image: null }] })
  }

  const finishCustomType = (spec: ProductSpecification) => {
    const name = customType.trim()
    const duplicated = specifications.some((item) => item.id !== spec.id && item.name === name)
    if (name && !duplicated) {
      setCustomTypes((current) => current.includes(name) ? current : [...current, name])
      updateSpec(spec.id, { name })
    }
    setCustomTypeIndex(null)
    setCustomType('')
  }

  const finishValueInput = (spec: ProductSpecification, input: HTMLInputElement) => {
    addValue(spec, input.value)
    input.value = ''
  }

  const updateValue = (spec: ProductSpecification, valueId: string, patch: Partial<SpecificationValue>) => {
    updateSpec(spec.id, {
      values: spec.values.map((value) => (value.id === valueId ? { ...value, ...patch } : value)),
    })
  }

  const updateSku = (key: string, field: 'price' | 'stock', value: string) => {
    onChange(specifications, skuRows.map((row) => (row.key === key ? { ...row, [field]: value } : row)))
  }

  const handleValueImage = async (spec: ProductSpecification, value: SpecificationValue, file?: File) => {
    if (!file) return
    const url = await onUploadImage(file)
    if (url) updateValue(spec, value.id, { image: url })
  }

  return (
    <div className="space-y-3">
      {specifications.map((spec) => (
        <div key={spec.id} className="rounded-lg bg-slate-50 dark:bg-slate-800/70 p-3 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-slate-400 select-none">⋮⋮</span>
            <select
              className="input-ios w-44"
              value={spec.name}
              onChange={(event) => {
                if (event.target.value === '__custom__') {
                  setCustomTypeIndex(specifications.findIndex((item) => item.id === spec.id))
                  setCustomType(PRESET_TYPES.includes(spec.name) ? '' : spec.name)
                } else {
                  updateSpec(spec.id, { name: event.target.value })
                  setCustomTypeIndex(null)
                  setCustomType('')
                }
              }}
            >
              <option value="">请选择规格类型</option>
              {PRESET_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
              {customTypes
                .filter((type) => type === spec.name || !specifications.some((item) => item.id !== spec.id && item.name === type))
                .map((type) => <option key={type} value={type}>{type}</option>)}
              <option value="__custom__">自定义规格类型</option>
            </select>
            {customTypeIndex === specifications.findIndex((item) => item.id === spec.id) && (
              <div className="flex items-center gap-1">
                <input
                  autoFocus
                  className="input-ios w-36"
                  placeholder="输入规格名称"
                  value={customType}
                  onChange={(event) => setCustomType(event.target.value)}
                  onBlur={() => finishCustomType(spec)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault()
                      event.currentTarget.blur()
                    }
                  }}
                />
                <button
                  type="button"
                  className="btn-ios-secondary px-2"
                  onMouseDown={(event) => event.preventDefault()}
                  onClick={() => finishCustomType(spec)}
                >
                  确定
                </button>
              </div>
            )}
            <label className="inline-flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-300">
              <input
                type="checkbox"
                checked={spec.supportImage}
                onChange={(event) => updateSpec(spec.id, { supportImage: event.target.checked })}
              />
              支持添加图片
            </label>
            <button
              type="button"
              className="ml-auto p-1.5 text-slate-400 hover:text-red-500"
              title="删除规格类型"
              onClick={() => updateSpecifications(specifications.filter((item) => item.id !== spec.id))}
            >
              <Trash2 className="w-4 h-4" />
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-2 pl-6">
            {spec.values.map((value) => (
              <div key={value.id} className="flex items-center gap-1">
                <div className="relative">
                  <input
                    className="input-ios w-36 pr-8"
                    value={value.name}
                    placeholder="输入规格值"
                    onChange={(event) => updateValue(spec, value.id, { name: event.target.value })}
                  />
                  {(spec.supportImage || Boolean(value.image)) && (
                    <>
                      <button
                        type="button"
                        className="absolute right-1 top-1/2 -translate-y-1/2 text-slate-400 hover:text-blue-500"
                        title="上传规格图片"
                        onClick={() => imageInputs.current[value.id]?.click()}
                      >
                        {value.image ? <ImagePlus className="w-4 h-4 text-blue-500" /> : <Upload className="w-4 h-4" />}
                      </button>
                      <input
                        ref={(element) => { imageInputs.current[value.id] = element }}
                        type="file"
                        accept="image/*"
                        className="hidden"
                        onChange={(event) => {
                          void handleValueImage(spec, value, event.target.files?.[0])
                          event.target.value = ''
                        }}
                      />
                    </>
                  )}
                </div>
                <button type="button" className="p-1 text-slate-400 hover:text-red-500" title="删除规格值" onClick={() => updateSpec(spec.id, { values: spec.values.filter((item) => item.id !== value.id) })}>
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
            <input
              className="input-ios w-36"
              placeholder="输入规格值"
              onBlur={(event) => finishValueInput(spec, event.currentTarget)}
              onKeyDown={(event) => {
                if (event.key === 'Enter') {
                  event.preventDefault()
                  event.currentTarget.blur()
                }
              }}
            />
          </div>
        </div>
      ))}

      {specifications.length < 2 && (
        <button
          type="button"
          className="w-full sm:w-52 h-9 rounded-lg bg-slate-50 dark:bg-slate-800 text-sm text-slate-600 dark:text-slate-300 hover:bg-blue-50 dark:hover:bg-blue-900/20 transition-colors"
          onClick={startAddSpecification}
        >
          <Plus className="w-4 h-4 inline-block mr-1" />添加规格类型 ({specifications.length}/2)
        </button>
      )}

      {generatedRows.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-700">
          <table className="table-ios min-w-[620px]">
            <thead>
              <tr>
                {specifications.filter((spec) => spec.name && spec.values.length).map((spec) => <th key={spec.id}>{spec.name}</th>)}
                <th>价格（元）</th>
                <th>库存</th>
              </tr>
            </thead>
            <tbody>
              {skuRows.map((row) => (
                <tr key={row.key}>
                  {specifications.filter((spec) => spec.name && spec.values.length).map((spec) => <td key={spec.id}>{row.specs[spec.name] || '-'}</td>)}
                  <td><input type="number" min="0" step="0.01" className="input-ios min-w-28" placeholder="0.00" value={row.price} onChange={(event) => updateSku(row.key, 'price', event.target.value)} /></td>
                  <td><input type="number" min="0" step="1" className="input-ios min-w-24" placeholder="0" value={row.stock} onChange={(event) => updateSku(row.key, 'stock', event.target.value)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default ProductSpecificationsEditor
