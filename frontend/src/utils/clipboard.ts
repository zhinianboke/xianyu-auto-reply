/**
 * 剪贴板工具
 *
 * 功能：
 * 1. 优先使用 navigator.clipboard（仅 HTTPS / localhost / file:// 等 secure context 可用）
 * 2. 自动 fallback 到 document.execCommand('copy') + 临时 textarea
 *    （兼容云服务器 HTTP 部署、旧浏览器、iframe 内嵌等场景）
 * 3. 任一阶段失败时返回 false，由调用方决定提示文案
 *
 * 用法：
 *   const ok = await copyToClipboard(text)
 *   addToast({ type: ok ? 'success' : 'error', message: ok ? '已复制' : '复制失败' })
 */

/**
 * 复制文本到剪贴板
 * @param text 需要复制的文本
 * @returns true=复制成功，false=复制失败（应提示用户手动复制）
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  if (text === undefined || text === null) {
    return false
  }

  const value = String(text)

  // 优先走原生 Clipboard API（异步），仅 secure context 可用
  if (typeof navigator !== 'undefined' && navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(value)
      return true
    } catch {
      // 落到 execCommand fallback
    }
  }

  // 兼容方案：临时 textarea + execCommand('copy')
  // 适用于 HTTP 环境（非 secure context）以及 navigator.clipboard 被禁用的情况
  try {
    const textArea = document.createElement('textarea')
    textArea.value = value
    textArea.setAttribute('readonly', 'readonly')
    // 移到屏幕外避免视觉抖动
    textArea.style.position = 'fixed'
    textArea.style.left = '-9999px'
    textArea.style.top = '0'
    textArea.style.opacity = '0'
    document.body.appendChild(textArea)

    textArea.focus()
    textArea.select()
    // iOS Safari 上 select() 不一定生效，需要再调用 setSelectionRange
    textArea.setSelectionRange(0, value.length)

    const ok = document.execCommand('copy')
    document.body.removeChild(textArea)
    return ok
  } catch {
    return false
  }
}
