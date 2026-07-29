import { useState } from 'react'
import { Eye, EyeOff } from 'lucide-react'

interface PasswordInputProps {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  className?: string
  inputClassName?: string
  disabled?: boolean
  required?: boolean
  autoComplete?: string
  showLabel?: string
  hideLabel?: string
}

export function PasswordInput({
  value,
  onChange,
  placeholder,
  className = '',
  inputClassName = '',
  disabled = false,
  required = false,
  autoComplete = 'off',
  showLabel = '显示密码',
  hideLabel = '隐藏密码',
}: PasswordInputProps) {
  const [visible, setVisible] = useState(false)

  return (
    <div className={`relative ${className}`}>
      <input
        type={visible ? 'text' : 'password'}
        value={value}
        disabled={disabled}
        required={required}
        autoComplete={autoComplete}
        placeholder={placeholder}
        onChange={(event) => onChange(event.target.value)}
        className={`input-ios pr-10 ${inputClassName}`}
      />
      <button
        type="button"
        tabIndex={-1}
        disabled={disabled}
        onClick={() => setVisible((current) => !current)}
        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 transition-colors hover:text-slate-600 disabled:cursor-not-allowed disabled:opacity-50 dark:text-slate-500 dark:hover:text-slate-300"
        aria-label={visible ? hideLabel : showLabel}
      >
        {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>
    </div>
  )
}
