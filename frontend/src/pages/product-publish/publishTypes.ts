/**
 * 单品发布页面共享数据结构。
 * 规格数据只用于本次发布，不写入素材库。
 */
import type { MaterialVideo, PlatformCategoryPathItem, PlatformMaterialAttribute } from '@/api/productPublish'

export type ShippingMethod = 'free' | 'distance' | 'fixed' | 'template' | 'none'

export interface SpecificationValue {
  id: string
  name: string
  image?: string | null
}

export interface ProductSpecification {
  id: string
  name: string
  values: SpecificationValue[]
  supportImage: boolean
}

export interface SkuRow {
  key: string
  specs: Record<string, string>
  price: string
  stock: string
}

export interface DuplicateSpecificationValue {
  specificationName: string
  valueName: string
}

/** 查找同一规格类型下重复的规格值，供素材保存和单品发布共同校验。 */
export function findDuplicateSpecificationValue(
  specifications: ProductSpecification[],
): DuplicateSpecificationValue | null {
  for (const specification of specifications) {
    const values = new Set<string>()
    for (const value of specification.values) {
      const valueName = value.name.trim()
      if (!valueName) continue
      if (values.has(valueName)) {
        return {
          specificationName: specification.name.trim() || '未命名规格',
          valueName,
        }
      }
      values.add(valueName)
    }
  }
  return null
}

/** 按规格定义顺序生成稳定的 SKU key，确保素材库导入后能匹配原价格和库存。 */
export function buildSkuKey(specifications: ProductSpecification[], specs: Record<string, string>): string {
  return specifications
    .filter((specification) => specification.name.trim() && specification.values.some((value) => value.name.trim()))
    .map((specification) => `${specification.name}:${specs[specification.name] || ''}`)
    .join('|')
}

export interface PublishForm {
  account_id: string
  title: string
  description: string
  price: string
  original_price: string
  category: string
  platform_category_id: string
  platform_category_name: string
  platform_channel_category_id: string
  platform_channel_category_name: string
  platform_leaf_id: string
  platform_tb_category_id: string
  platform_category_path: PlatformCategoryPathItem[]
  platform_attributes: PlatformMaterialAttribute[]
  category_source: 'manual' | 'recommendation'
  category_confidence?: number
  videos: MaterialVideo[]
  quantity: number
  address: string
  address_expected_text?: string
  delivery_method: 'express' | 'pickup'
  shipping_method: ShippingMethod
  support_pickup: boolean
  postage: string
  brand: string
  condition: string
  specifications: ProductSpecification[]
  sku_rows: SkuRow[]
}
