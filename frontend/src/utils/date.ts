/**
 * 日期/时间格式化工具
 *
 * 提供项目内统一的日期时间展示格式，避免在多个页面重复定义相同的格式化函数。
 */

/**
 * 将日期值格式化为「YYYY/MM/DD HH:mm:ss」中文 24 小时格式。
 *
 * 行为约定：
 * - 入参为空（`null` / `undefined` / 空字符串）时返回 `-`，便于表格直接展示。
 * - 入参非法（无法被 `Date` 解析）时同样返回 `-`，避免页面出现 `Invalid Date` 字样。
 *
 * @param value 字符串、Date 对象或空值
 * @returns 格式化后的中文日期时间字符串，或缺省占位符 `-`
 */
export function formatDateTime(value?: string | Date | null): string {
  if (!value) return '-'
  const date = typeof value === 'string' ? new Date(value) : value
  if (Number.isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

/**
 * 获取北京时间日期字符串，格式为 input[type="date"] 可直接使用的 YYYY-MM-DD。
 *
 * @param value 可选日期，默认当前时间
 * @returns 北京时间日期字符串
 */
export function getBeijingDateInputValue(value: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  }).formatToParts(value)

  const partMap = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${partMap.year}-${partMap.month}-${partMap.day}`
}
