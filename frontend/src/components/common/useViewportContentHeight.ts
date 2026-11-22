/** 测量内容区剩余可视高度，避免固定表格页面被顶部布局和外层内边距撑出窗口。 */
import { useLayoutEffect, useRef, useState } from 'react'

/** 返回内容容器 ref 和可用高度；监听窗口、祖先布局及移动端可视视口变化。 */
export function useViewportContentHeight<T extends HTMLElement>() {
  const containerRef = useRef<T>(null)
  const [height, setHeight] = useState(0)

  useLayoutEffect(() => {
    const container = containerRef.current
    if (!container) return

    const measure = () => {
      const main = container.closest('main')
      const bottomPadding = main ? Number.parseFloat(window.getComputedStyle(main).paddingBottom) || 0 : 0
      // 使用文档内位置，不能因上一个页面留下的窗口滚动而把当前页高度越算越大。
      const top = container.getBoundingClientRect().top + window.scrollY
      const viewportHeight = window.visualViewport?.height ?? window.innerHeight
      setHeight(Math.max(0, Math.floor(viewportHeight - top - bottomPadding)))
    }

    measure()
    const observer = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure)
    // 顶栏、侧栏宽度和字体变化都可能改变内容位置；不只监听窗口大小。
    for (let element: HTMLElement | null = container; element; element = element.parentElement) {
      observer?.observe(element)
    }
    const viewport = window.visualViewport
    window.addEventListener('resize', measure)
    viewport?.addEventListener('resize', measure)
    return () => {
      observer?.disconnect()
      window.removeEventListener('resize', measure)
      viewport?.removeEventListener('resize', measure)
    }
  }, [])

  return { containerRef, height }
}
