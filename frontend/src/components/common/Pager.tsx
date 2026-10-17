/**
 * 公共分页组件
 *
 * 功能：
 * 1. 统一的「每页条数 + 首页/上一页/页码/下一页/尾页 + 指定页跳转」交互
 * 2. 支持指定页码翻页（输入页码后点击「跳转」或按回车直达）
 * 3. 亮色 / 暗色主题自适应，文案全中文，移动端自适应换行
 */
import { useEffect, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'

export interface PagerProps {
  /** 当前页码（从 1 开始） */
  page: number
  /** 每页条数 */
  pageSize: number
  /** 总条数 */
  total: number
  /** 总页数（可选，缺省按 total / pageSize 计算） */
  totalPages?: number
  /** 每页条数可选项 */
  pageSizeOptions?: number[]
  /** 数据加载中（禁用交互） */
  loading?: boolean
  /** 页码变化回调 */
  onPageChange: (page: number) => void
  /** 每页条数变化回调 */
  onPageSizeChange?: (pageSize: number) => void
}

export function Pager({
  page,
  pageSize,
  total,
  totalPages,
  pageSizeOptions = [10, 20, 50, 100],
  loading = false,
  onPageChange,
  onPageSizeChange,
}: PagerProps) {
  // 总页数至少为 1，避免出现「第 1 / 0 页」
  const maxPage = Math.max(1, totalPages ?? (Math.ceil(total / pageSize) || 1))
  const [jumpValue, setJumpValue] = useState(String(page))

  // 外部页码变化时同步跳页输入框，避免输入框停留在旧值
  useEffect(() => {
    setJumpValue(String(page))
  }, [page])

  const startIndex = total === 0 ? 0 : (page - 1) * pageSize + 1
  const endIndex = Math.min(page * pageSize, total)

  // 跳转到指定页码，越界自动收敛到 [1, maxPage]
  const goTo = (next: number) => {
    const target = Math.min(Math.max(next, 1), maxPage)
    setJumpValue(String(target))
    if (target !== page) onPageChange(target)
  }

  const handleJump = () => {
    const parsed = Number(jumpValue)
    if (!jumpValue || Number.isNaN(parsed)) {
      setJumpValue(String(page))
      return
    }
    goTo(Math.trunc(parsed))
  }

  // 页码展示：≤7 页全部显示；>7 页折叠为「1 2 3 ... 98 99 100」形式，
  // 始终保留首页、尾页、当前页及其左右各一页
  const buildPageItems = (current: number, max: number): Array<number | 'ellipsis'> => {
    if (max <= 7) {
      const items: Array<number | 'ellipsis'> = []
      for (let value = 1; value <= max; value += 1) items.push(value)
      return items
    }
    const kept = new Set<number>([1, max, current, current - 1, current + 1])
    const sortedPages = Array.from(kept)
      .filter((value) => value >= 1 && value <= max)
      .sort((left, right) => left - right)
    const items: Array<number | 'ellipsis'> = []
    let previous = 0
    for (const value of sortedPages) {
      if (previous !== 0 && value - previous > 1) items.push('ellipsis')
      items.push(value)
      previous = value
    }
    return items
  }
  const pageItems = buildPageItems(page, maxPage)

  const navButtonClass =
    'px-2.5 py-1 text-sm rounded border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 ' +
    'hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-50 disabled:cursor-not-allowed'

  const pageButtonClass = (active: boolean) =>
    active
      ? 'min-w-[32px] px-2 py-1 text-sm rounded bg-blue-600 text-white border border-blue-600'
      : 'min-w-[32px] px-2 py-1 text-sm rounded border border-slate-300 dark:border-slate-600 ' +
        'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'

  return (
    <div className="flex-shrink-0 vben-card-footer flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-3 border-t border-slate-200 dark:border-slate-700">
      <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400 flex-wrap">
        <span>每页</span>
        <select
          value={pageSize}
          onChange={(event) => onPageSizeChange?.(Number(event.target.value))}
          disabled={loading}
          className="px-2 py-1 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 disabled:opacity-50"
        >
          {pageSizeOptions.map((size) => (
            <option key={size} value={size}>
              {size}
            </option>
          ))}
        </select>
        <span>条</span>
        <span className="ml-2">
          显示 {startIndex}-{endIndex} 条，共 {total} 条
        </span>
      </div>

      <div className="flex items-center gap-1 flex-wrap">
        <button
          type="button"
          onClick={() => goTo(1)}
          disabled={loading || page <= 1}
          className={navButtonClass}
        >
          首页
        </button>
        <button
          type="button"
          onClick={() => goTo(page - 1)}
          disabled={loading || page <= 1}
          className={navButtonClass}
          aria-label="上一页"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>

        {pageItems.map((item, index) =>
          item === 'ellipsis' ? (
            <span
              key={`ellipsis-${index}`}
              className="px-2 text-sm text-slate-400 dark:text-slate-500 select-none"
            >
              ...
            </span>
          ) : (
            <button
              key={item}
              type="button"
              onClick={() => goTo(item)}
              disabled={loading}
              className={pageButtonClass(item === page)}
            >
              {item}
            </button>
          ),
        )}

        <button
          type="button"
          onClick={() => goTo(page + 1)}
          disabled={loading || page >= maxPage}
          className={navButtonClass}
          aria-label="下一页"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => goTo(maxPage)}
          disabled={loading || page >= maxPage}
          className={navButtonClass}
        >
          尾页
        </button>

        <span className="ml-2 flex items-center gap-1 text-sm text-slate-500 dark:text-slate-400">
          跳至
          <input
            type="number"
            min={1}
            max={maxPage}
            value={jumpValue}
            disabled={loading}
            onChange={(event) => setJumpValue(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                handleJump()
              }
            }}
            className="w-16 px-2 py-1 text-sm border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 disabled:opacity-50"
          />
          页
          <button
            type="button"
            onClick={handleJump}
            disabled={loading}
            className="btn-ios-secondary"
          >
            跳转
          </button>
        </span>
      </div>
    </div>
  )
}
