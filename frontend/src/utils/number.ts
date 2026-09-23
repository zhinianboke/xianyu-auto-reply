/**
 * 数字输入处理工具
 *
 * 解决受控数字输入框的常见问题：输入框被清空时 `Number('')` 会得到 0，
 * 直接提交会触发后端校验失败（返回 422 英文报错），因此统一在前端夹到合法区间。
 */

/**
 * 把输入框的原始字符串转成受限范围内的数字。
 *
 * @param raw 输入框原始值
 * @param min 允许的最小值
 * @param max 允许的最大值
 * @param fallback 输入为空或非法数字时的回退值
 * @returns 落在 [min, max] 内的数字
 */
export function clampNumberInput(raw: string, min: number, max: number, fallback: number): number {
  if (raw.trim() === '') return fallback
  const value = Number(raw)
  if (!Number.isFinite(value)) return fallback
  return Math.min(Math.max(value, min), max)
}
