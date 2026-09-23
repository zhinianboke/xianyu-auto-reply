/**
 * 商品发布分类数据工具。
 * 统一判断平台分类是否可发布，并在分类刷新时保留已有的有效标识。
 */
import type {
  PlatformCategoryCandidate,
  PlatformCategoryProperty,
  PlatformCategoryPropertyOption,
  PlatformMaterialAttribute,
} from '@/api/productPublish'

const candidateIdFields = [
  ['channel_cat_id', 8],
  ['tb_cat_id', 4],
  ['cat_id', 2],
] as const

function samePath(left: PlatformCategoryCandidate['path'], right: PlatformCategoryCandidate['path']) {
  return Boolean(
    left?.length
      && right?.length
      && left.length === right.length
      && left.every((item, index) => item.id === right[index]?.id && item.name === right[index]?.name),
  )
}

/**
 * 计算两个分类候选的匹配分数。
 * 双方已有的任一 ID 冲突即不匹配；无 ID 可比较时才使用路径或名称兜底。
 */
export function categoryCandidateMatchScore(
  reference: PlatformCategoryCandidate,
  candidate: PlatformCategoryCandidate,
) {
  let score = 0
  for (const [field, weight] of candidateIdFields) {
    const referenceValue = reference[field]
    const candidateValue = candidate[field]
    if (!referenceValue || !candidateValue) continue
    if (referenceValue !== candidateValue) return -1
    score += weight
  }
  const referenceName = reference.cat_name || reference.channel_cat_name || reference.path?.at(-1)?.name
  const candidateName = candidate.cat_name || candidate.channel_cat_name || candidate.path?.at(-1)?.name
  if (referenceName && candidateName && referenceName === candidateName) score += 1
  if (score > 0) return score
  if (samePath(reference.path, candidate.path)) return 1
  return 0
}

/** 从整组候选中选择标识匹配最完整的一项，避免返回顺序影响选择结果。 */
export function bestMatchingCategoryCandidate(
  reference: PlatformCategoryCandidate | undefined,
  candidates: PlatformCategoryCandidate[],
) {
  if (!reference) return undefined
  let bestCandidate: PlatformCategoryCandidate | undefined
  let bestScore = 0
  for (const candidate of candidates) {
    const score = categoryCandidateMatchScore(reference, candidate)
    if (score <= bestScore) continue
    bestCandidate = candidate
    bestScore = score
  }
  return bestCandidate
}

/** 判断动态属性选项是否属于当前分类。 */
export function optionMatchesCategoryCandidate(
  option: PlatformCategoryPropertyOption,
  candidate?: PlatformCategoryCandidate,
) {
  if (!candidate) return true
  const channelMatches = !option.channel_cat_id
    || !candidate.channel_cat_id
    || option.channel_cat_id === candidate.channel_cat_id
  const tbMatches = !option.tb_cat_id || !candidate.tb_cat_id || option.tb_cat_id === candidate.tb_cat_id
  return channelMatches && tbMatches
}

/** 将接口属性选项转换为素材和发布接口共用的平台属性。 */
export function platformAttributeFromOption(
  property: PlatformCategoryProperty,
  option?: PlatformCategoryPropertyOption,
  textValue?: string,
): PlatformMaterialAttribute | null {
  const valueName = option?.value_name || textValue?.trim() || ''
  if (!valueName) return null
  const valueId = option?.value_id || null
  return {
    property_id: property.property_id,
    property_name: property.property_name,
    value_id: valueId,
    value_name: valueName,
    text: valueName,
    properties: option?.properties
      || (valueId ? `${property.property_id}##${property.property_name}:${valueId}##${valueName}` : null),
  }
}

/** 提取平台明确标记的默认属性；单选属性只采用第一个默认值。 */
export function defaultPlatformAttributes(
  properties: PlatformCategoryProperty[],
  candidate?: PlatformCategoryCandidate,
) {
  const attributes: PlatformMaterialAttribute[] = []
  for (const property of properties) {
    const selectedOptions = property.options.filter((option) =>
      option.is_selected && optionMatchesCategoryCandidate(option, candidate),
    )
    const acceptedOptions = property.is_multiple || selectedOptions.length > 1
      ? selectedOptions
      : selectedOptions.slice(0, 1)
    for (const option of acceptedOptions) {
      const attribute = platformAttributeFromOption(property, option)
      if (attribute) attributes.push(attribute)
    }
  }
  return attributes
}

/** 同步平台属性及素材库单独保存的品牌、成色字段。 */
export function platformAttributesPatch(platformAttributes: PlatformMaterialAttribute[]) {
  const valueOf = (propertyId: string) =>
    platformAttributes.find((attribute) => attribute.property_id === propertyId)?.value_name || ''
  return {
    platform_attributes: platformAttributes,
    brand: valueOf('20000'),
    condition: valueOf('20879') || '全新',
  }
}

/** 合并同一候选的刷新结果，避免平台返回空字段时清掉上一轮已取得的 ID。 */
export function mergeCategoryCandidate(
  current: PlatformCategoryCandidate,
  refreshed: PlatformCategoryCandidate,
): PlatformCategoryCandidate {
  return {
    ...current,
    ...refreshed,
    cat_id: refreshed.cat_id || current.cat_id || null,
    cat_name: refreshed.cat_name || current.cat_name || null,
    channel_cat_id: refreshed.channel_cat_id || current.channel_cat_id || null,
    channel_cat_name: refreshed.channel_cat_name || current.channel_cat_name || null,
    leaf_id: refreshed.leaf_id || current.leaf_id || null,
    tb_cat_id: refreshed.tb_cat_id || current.tb_cat_id || null,
    path: refreshed.path?.length ? refreshed.path : current.path || [],
  }
}
