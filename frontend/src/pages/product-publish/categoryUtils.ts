/**
 * 商品发布分类数据工具。
 * 统一判断平台分类是否可发布，并在分类刷新时保留已有的有效标识。
 */
import type { PlatformCategoryCandidate } from '@/api/productPublish'

interface PlatformCategoryIds {
  platform_category_id?: string | null
  platform_channel_category_id?: string | null
  platform_tb_category_id?: string | null
}

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

/** 判断推荐候选是否包含发布接口要求的三个分类 ID。 */
export function isCompleteCategoryCandidate(candidate?: PlatformCategoryCandidate | null) {
  return Boolean(
    candidate?.cat_id
      && candidate.channel_cat_id
      && candidate.tb_cat_id
      && (candidate.channel_cat_name || candidate.cat_name || candidate.path?.at(-1)?.name),
  )
}

/** 判断发布表单是否包含发布接口要求的三个分类 ID。 */
export function hasCompletePlatformCategory(category: PlatformCategoryIds) {
  return Boolean(
    category.platform_category_id?.trim()
      && category.platform_channel_category_id?.trim()
      && category.platform_tb_category_id?.trim(),
  )
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
