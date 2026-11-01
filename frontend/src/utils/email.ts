/**
 * 邮箱地址校验工具。
 *
 * 统一前端各入口的基础邮箱格式判断，提交前仍由后端再次校验。
 */
const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export function isValidEmail(value: string): boolean {
  return EMAIL_PATTERN.test(value.trim())
}
