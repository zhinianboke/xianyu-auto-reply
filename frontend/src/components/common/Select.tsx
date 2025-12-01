import { useState, useRef, useEffect } from 'react'
import { ChevronDown, Check } from 'lucide-react'
import { cn } from '@/utils/cn'

export interface SelectOption {
  value: string
  label: string
  disabled?: boolean
}

interface SelectProps {
  value: string
  onChange: (value: string) => void
  options: SelectOption[]
  placeholder?: string
  disabled?: boolean
  className?: string
}

export function Select({
  value,
  onChange,
  options,
  placeholder = '请选择',
  disabled = false,
  className,
}: SelectProps) {
  const [isOpen, setIsOpen] = useState(false)
  const selectRef = useRef<HTMLDivElement>(null)

  const selectedOption = options.find((opt) => opt.value === value)

  // 点击外部关闭
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (selectRef.current && !selectRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  // 键盘导航
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (disabled) return

    switch (e.key) {
      case 'Enter':
      case ' ':
        e.preventDefault()
        setIsOpen(!isOpen)
        break
      case 'Escape':
        setIsOpen(false)
        break
      case 'ArrowDown':
        e.preventDefault()
        if (!isOpen) {
          setIsOpen(true)
        } else {
          const currentIndex = options.findIndex((opt) => opt.value === value)
          const nextIndex = Math.min(currentIndex + 1, options.length - 1)
          onChange(options[nextIndex].value)
        }
        break
      case 'ArrowUp':
        e.preventDefault()
        if (isOpen) {
          const currentIndex = options.findIndex((opt) => opt.value === value)
          const prevIndex = Math.max(currentIndex - 1, 0)
          onChange(options[prevIndex].value)
        }
        break
    }
  }

  return (
    <div ref={selectRef} className={cn('relative', className)}>
      {/* 触发器 */}
      <button
        type="button"
        onClick={() => !disabled && setIsOpen(!isOpen)}
        onKeyDown={handleKeyDown}
        disabled={disabled}
        className={cn(
          'w-full flex items-center justify-between gap-2',
          'px-3 py-2 rounded-md text-sm text-left',
          'bg-white dark:bg-slate-700',
          'border border-slate-300 dark:border-slate-600',
          'hover:border-blue-400 dark:hover:border-blue-500',
          'focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent',
          'transition-colors duration-150',
          disabled && 'opacity-60 cursor-not-allowed bg-slate-100 dark:bg-slate-800',
          isOpen && 'ring-2 ring-blue-500 border-transparent'
        )}
      >
        <span className={cn(
          'truncate',
          selectedOption ? 'text-slate-900 dark:text-slate-100' : 'text-slate-400'
        )}>
          {selectedOption?.label || placeholder}
        </span>
        <ChevronDown
          className={cn(
            'w-4 h-4 text-slate-400 flex-shrink-0 transition-transform duration-200',
            isOpen && 'rotate-180'
          )}
        />
      </button>

      {/* 下拉菜单 */}
      {isOpen && (
        <div className={cn(
          'absolute z-50 w-full mt-1',
          'bg-white dark:bg-slate-800',
          'border border-slate-200 dark:border-slate-700',
          'rounded-md shadow-lg',
          'max-h-60 overflow-auto',
          'animate-in fade-in-0 zoom-in-95 duration-100'
        )}>
          {options.length === 0 ? (
            <div className="px-3 py-2 text-sm text-slate-400 text-center">
              暂无选项
            </div>
          ) : (
            options.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => {
                  if (!option.disabled) {
                    onChange(option.value)
                    setIsOpen(false)
                  }
                }}
                disabled={option.disabled}
                className={cn(
                  'w-full flex items-center justify-between gap-2',
                  'px-3 py-2 text-sm text-left',
                  'transition-colors duration-100',
                  option.disabled
                    ? 'text-slate-400 cursor-not-allowed'
                    : 'text-slate-700 dark:text-slate-200 hover:bg-blue-50 dark:hover:bg-slate-700',
                  option.value === value && 'bg-blue-50 dark:bg-slate-700 text-blue-600 dark:text-blue-400'
                )}
              >
                <span className="truncate">{option.label}</span>
                {option.value === value && (
                  <Check className="w-4 h-4 text-blue-500 flex-shrink-0" />
                )}
              </button>
            ))
          )}
        </div>
      )}
    </div>
  )
}
