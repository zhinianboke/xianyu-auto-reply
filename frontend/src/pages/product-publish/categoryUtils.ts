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

/** 判断推荐候选是否包含发布接口要求的三个分类 ID。 */
export function isCompleteCategoryCandidate(candidate?: PlatformCategoryCandidate | null) {
  return Boolean(candidate?.cat_id && candidate.channel_cat_id && candidate.tb_cat_id)
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
