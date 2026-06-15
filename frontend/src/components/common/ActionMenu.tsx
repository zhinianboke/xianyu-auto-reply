import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/utils/cn'

export interface ActionMenuItem {
  key: string
  label: ReactNode
  icon?: ReactNode
  danger?: boolean
  disabled?: boolean
}

interface ActionMenuProps {
  trigger: ReactNode
  items: ActionMenuItem[]
  onSelect: (key: string) => void
  align?: 'left' | 'right'
  menuClassName?: string
}

export function ActionMenu({
  trigger,
  items,
  onSelect,
  align = 'right',
  menuClassName,
}: ActionMenuProps) {
  const [open, setOpen] = useState(false)
  const [menuStyle, setMenuStyle] = useState<CSSProperties>({
    position: 'fixed',
    top: -9999,
    left: -9999,
    visibility: 'hidden',
  })
  const rootRef = useRef<HTMLDivElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const anchorRef = useRef<HTMLElement | null>(null)
  const repositionTimerRef = useRef<number[]>([])

  const resetMenuStyle = () => {
    setMenuStyle({
      position: 'fixed',
      top: -9999,
      left: -9999,
      visibility: 'hidden',
    })
  }

  const clearRepositionTimers = () => {
    repositionTimerRef.current.forEach((timerId) => window.clearTimeout(timerId))
    repositionTimerRef.current = []
  }

  const updateMenuPosition = () => {
    const trigger = anchorRef.current || rootRef.current
    const menu = menuRef.current
    if (!trigger || !menu) return

    const rect = trigger.getBoundingClientRect()
    const menuRect = menu.getBoundingClientRect()
    const viewportPadding = 8
    const menuWidth = menuRect.width || menu.offsetWidth || 160
    const menuHeight = menuRect.height || menu.offsetHeight || 0
    const viewportWidth = window.innerWidth
    const viewportHeight = window.innerHeight

    let left = align === 'right'
      ? rect.right - menuWidth
      : rect.left

    left = Math.max(viewportPadding, Math.min(left, viewportWidth - menuWidth - viewportPadding))

    let top = rect.bottom + 4
    if (menuHeight && top + menuHeight > viewportHeight - viewportPadding) {
      top = Math.max(viewportPadding, rect.top - menuHeight - 4)
    }

    const nextStyle: CSSProperties = {
      position: 'fixed',
      top,
      left,
      visibility: 'visible',
    }

    setMenuStyle(nextStyle)
  }

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node
      if (
        rootRef.current
        && !rootRef.current.contains(target)
        && !menuRef.current?.contains(target)
      ) {
        setOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  useLayoutEffect(() => {
    if (!open) {
      clearRepositionTimers()
      resetMenuStyle()
      return
    }

    updateMenuPosition()

    let frameId1 = 0
    let frameId2 = 0
    frameId1 = window.requestAnimationFrame(() => {
      updateMenuPosition()
      frameId2 = window.requestAnimationFrame(() => {
        updateMenuPosition()
      })
    })

    repositionTimerRef.current = [
      window.setTimeout(updateMenuPosition, 0),
      window.setTimeout(updateMenuPosition, 80),
      window.setTimeout(updateMenuPosition, 180),
    ]

    return () => {
      window.cancelAnimationFrame(frameId1)
      window.cancelAnimationFrame(frameId2)
      clearRepositionTimers()
    }
  }, [open, align])

  useEffect(() => {
    if (!open) return

    const handleViewportChange = () => updateMenuPosition()

    window.addEventListener('resize', handleViewportChange)
    window.addEventListener('scroll', handleViewportChange, true)

    return () => {
      window.removeEventListener('resize', handleViewportChange)
      window.removeEventListener('scroll', handleViewportChange, true)
    }
  }, [open, align])

  return (
    <div ref={rootRef} className="relative inline-flex">
      <div
        onClick={(event) => {
          anchorRef.current = event.currentTarget as HTMLElement
          setOpen((value) => !value)
        }}
      >
        {trigger}
      </div>

      {open && createPortal(
        <div
          ref={menuRef}
          style={menuStyle}
          className={cn(
            'z-50 min-w-32 rounded-md border border-slate-200 bg-white p-1 shadow-lg',
            'dark:border-slate-700 dark:bg-slate-800',
            menuClassName,
          )}
        >
          {items.map((item) => (
            <button
              key={item.key}
              type="button"
              disabled={item.disabled}
              onClick={() => {
                if (item.disabled) return
                onSelect(item.key)
                setOpen(false)
              }}
              className={cn(
                'flex h-8 w-full items-center gap-2 rounded px-2 text-left text-sm transition-colors',
                'text-slate-700 hover:bg-blue-50 hover:text-blue-600',
                'dark:text-slate-200 dark:hover:bg-slate-700 dark:hover:text-blue-400',
                item.danger && 'text-red-500 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/20',
                item.disabled && 'cursor-not-allowed opacity-50',
              )}
            >
              {item.icon && <span className="flex h-4 w-4 shrink-0 items-center justify-center">{item.icon}</span>}
              <span className="truncate">{item.label}</span>
            </button>
          ))}
        </div>,
        document.body,
      )}
    </div>
  )
}
