/**
 * 基础设置中的 Token 获取方式切换项。
 *
 * 功能：
 * 1. 展示小程序接口、网页接口两种 Token 获取方式
 * 2. 切换后立即持久化并反馈结果
 */
import { useState } from 'react'
import { Loader2 } from 'lucide-react'

import { normalizeTokenApiMode, updateTokenApiMode } from '@/api/tokenApiModeSettings'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import type { TokenApiMode } from '@/types'

interface TokenApiModeSettingProps {
  value: unknown
  onSaved: (mode: TokenApiMode) => void
}

const MODE_LABELS: Record<TokenApiMode, string> = {
  miniapp: '小程序接口',
  web: '网页接口',
}

export function TokenApiModeSetting({ value, onSaved }: TokenApiModeSettingProps) {
  const { addToast } = useUIStore()
  const [saving, setSaving] = useState(false)
  const currentMode = normalizeTokenApiMode(value)

  const handleChange = async (mode: TokenApiMode) => {
    if (saving || mode === currentMode) {
      return
    }

    try {
      setSaving(true)
      const result = await updateTokenApiMode(mode)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || 'Token获取方式切换失败' })
        return
      }

      onSaved(mode)
      addToast({
        type: 'success',
        message: `已切换为${MODE_LABELS[mode]}，后续取Token实时生效`,
      })
    } catch (error) {
      addToast({
        type: 'error',
        message: getApiErrorMessage(error, 'Token获取方式切换失败'),
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex items-center justify-between gap-4 py-3 border-t border-slate-100 dark:border-slate-700">
      <div className="min-w-0">
        <p className="font-medium text-slate-900 dark:text-slate-100">Token获取方式</p>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          账号取Token时使用的接口，触发风控将自动切换到另一个接口重试
        </p>
      </div>
      <div className="relative shrink-0">
        <select
          aria-label="Token获取方式"
          value={currentMode}
          disabled={saving}
          onChange={(event) => void handleChange(event.target.value as TokenApiMode)}
          className="input-ios w-44 pr-9 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <option value="miniapp">小程序接口</option>
          <option value="web">网页接口</option>
        </select>
        {saving && (
          <Loader2 className="pointer-events-none absolute right-8 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-[rgb(var(--color-primary))]" />
        )}
      </div>
    </div>
  )
}
