/**
 * 素材随机价格公共工具。
 * 按“分”在闭区间内取值，确保单品发布导入的价格固定保留两位小数。
 */
import type { ProductMaterial, PublishSkuRow } from '@/api/productPublish'

function formatRange(minimum: number, maximum: number): string {
  return `¥${minimum.toFixed(2)} ~ ¥${maximum.toFixed(2)}`
}

function randomPrice(minimum: number | null | undefined, maximum: number | null | undefined, label: string): string {
  if (minimum == null || maximum == null) {
    throw new Error(`${label}随机价格区间不完整，请先编辑素材`)
  }
  const minCents = Math.round(minimum * 100)
  const maxCents = Math.round(maximum * 100)
  if (
    !Number.isSafeInteger(minCents)
    || !Number.isSafeInteger(maxCents)
    || minCents <= 0
    || maxCents < minCents
  ) {
    throw new Error(`${label}随机价格区间无效，请先编辑素材`)
  }
  return ((minCents + Math.floor(Math.random() * (maxCents - minCents + 1))) / 100).toFixed(2)
}

function assignUniqueRandomPrices(ranges: Array<[number, number]>): string[] {
  const priceOwners = new Map<number, number>()
  const rowPrices = new Map<number, number>()
  const assign = (rowIndex: number, seenPrices: Set<number>): boolean => {
    const [minimum, maximum] = ranges[rowIndex]
    const rangeSize = maximum - minimum + 1
    const start = Math.floor(Math.random() * rangeSize)
    const probeCount = Math.min(rangeSize, priceOwners.size + 1)
    for (let offset = 0; offset < probeCount; offset += 1) {
      const candidate = minimum + ((start + offset) % rangeSize)
      if (!priceOwners.has(candidate)) {
        const oldPrice = rowPrices.get(rowIndex)
        if (oldPrice != null) priceOwners.delete(oldPrice)
        priceOwners.set(candidate, rowIndex)
        rowPrices.set(rowIndex, candidate)
        return true
      }
    }
    for (let offset = 0; offset < rangeSize; offset += 1) {
      const candidate = minimum + ((start + offset) % rangeSize)
      if (seenPrices.has(candidate)) continue
      seenPrices.add(candidate)
      const owner = priceOwners.get(candidate)
      if (owner == null || (owner !== rowIndex && assign(owner, seenPrices))) {
        const oldPrice = rowPrices.get(rowIndex)
        if (oldPrice != null) priceOwners.delete(oldPrice)
        priceOwners.set(candidate, rowIndex)
        rowPrices.set(rowIndex, candidate)
        return true
      }
    }
    return false
  }
  const startRow = ranges.length > 0 ? Math.floor(Math.random() * ranges.length) : 0
  for (let offset = 0; offset < ranges.length; offset += 1) {
    const rowIndex = (startRow + offset) % ranges.length
    if (!assign(rowIndex, new Set())) {
      throw new Error('规格随机价格区间无法生成互不相同的价格，请调整重叠区间')
    }
  }
  return ranges.map((_, index) => ((rowPrices.get(index) || 0) / 100).toFixed(2))
}

export function ensureUniqueRandomPricesAvailable(
  ranges: Array<{ minimum: number; maximum: number }>,
): void {
  const centRanges = ranges.map((range, index) => priceRange(
    range.minimum,
    range.maximum,
    `第 ${index + 1} 个规格`,
  ))
  assignUniqueRandomPrices(centRanges)
}

function priceRange(
  minimum: number | null | undefined,
  maximum: number | null | undefined,
  label: string,
): [number, number] {
  if (minimum == null || maximum == null) {
    throw new Error(`${label}随机价格区间不完整，请先编辑素材`)
  }
  const minCents = Math.round(minimum * 100)
  const maxCents = Math.round(maximum * 100)
  if (!Number.isSafeInteger(minCents) || !Number.isSafeInteger(maxCents) || minCents <= 0 || maxCents < minCents) {
    throw new Error(`${label}随机价格区间无效，请先编辑素材`)
  }
  return [minCents, maxCents]
}

export function formatMaterialPrice(material: ProductMaterial): string {
  if (material.price_mode === 'random') {
    const skuRanges = (material.sku_rows || []).map((row) => ({
      minimum: row.price_min ?? material.price_min,
      maximum: row.price_max ?? material.price_max,
    }))
    const validSkuRanges = skuRanges.filter(
      (row): row is { minimum: number; maximum: number } => (
        row.minimum != null
        && row.maximum != null
        && Number.isFinite(Number(row.minimum))
        && Number.isFinite(Number(row.maximum))
      ),
    )
    if (validSkuRanges.length > 0 && validSkuRanges.length === skuRanges.length) {
      return formatRange(
        Math.min(...validSkuRanges.map((row) => Number(row.minimum))),
        Math.max(...validSkuRanges.map((row) => Number(row.maximum))),
      )
    }
    if (material.price_min != null && material.price_max != null) {
      return formatRange(material.price_min, material.price_max)
    }
  }
  return `¥${Number(material.price || 0).toFixed(2)}`
}

export function formatSkuRandomPrice(row: PublishSkuRow, material: ProductMaterial): string {
  const minimum = row.price_min ?? material.price_min
  const maximum = row.price_max ?? material.price_max
  return minimum != null && maximum != null ? formatRange(minimum, maximum) : '价格区间未设置'
}

export function resolveMaterialSelectionPrices(material: ProductMaterial): {
  price: string
  skuPrices: string[]
} {
  if (material.price_mode !== 'random') {
    const fixedPrice = Number(material.price)
    if (!Number.isFinite(fixedPrice) || fixedPrice <= 0) {
      throw new Error('素材固定价格无效，请先编辑素材')
    }
    return { price: fixedPrice.toFixed(2), skuPrices: [] }
  }
  if ((material.sku_rows || []).length > 0) {
    const ranges = material.sku_rows.map((row, index) => priceRange(
      row.price_min ?? material.price_min,
      row.price_max ?? material.price_max,
      `第 ${index + 1} 个规格`,
    ))
    const skuPrices = assignUniqueRandomPrices(ranges)
    return {
      price: Math.min(...skuPrices.map(Number)).toFixed(2),
      skuPrices,
    }
  }
  return {
    price: randomPrice(material.price_min, material.price_max, '素材'),
    skuPrices: [],
  }
}
