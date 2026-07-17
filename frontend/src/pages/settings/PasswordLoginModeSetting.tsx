/**
 * 基础设置中的账号密码登录方式切换项。
 *
 * 功能：
 * 1. 展示自动选择、协议登录、浏览器登录三种方式
 * 2. 用户切换后立即持久化，并反馈实时生效结果
 */
import { useState } from 'react'
import { Loader2 } from 'lucide-react'

import {
  normalizePasswordLoginMode,
  updatePasswordLoginMode,
} from '@/api/passwordLoginSettings'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import type { PasswordLoginMode } from '@/types'

interface PasswordLoginModeSettingProps {
  value: unknown
  onSaved: (mode: PasswordLoginMode) => void
}

const MODE_LABELS: Record<PasswordLoginMode, string> = {
  auto: '自动选择',
  protocol: '协议登录',
  browser: '浏览器登录',
}

export function PasswordLoginModeSetting({
  value,
  onSaved,
}: PasswordLoginModeSettingProps) {
  const { addToast } = useUIStore()
  const [saving, setSaving] = useState(false)
  const currentMode = normalizePasswordLoginMode(value)

  const handleChange = async (mode: PasswordLoginMode) => {
    if (saving || mode === currentMode) {
      return
    }

    try {
      setSaving(true)
      const result = await updatePasswordLoginMode(mode)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '账号密码登录方式切换失败' })
        return
      }

      onSaved(mode)
      addToast({
        type: 'success',
        message: `已切换为${MODE_LABELS[mode]}，后续账号密码登录实时生效`,
      })
    } catch (error) {
      addToast({
        type: 'error',
        message: getApiErrorMessage(error, '账号密码登录方式切换失败'),
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex items-center justify-between gap-4 py-3 border-t border-slate-100 dark:border-slate-700">
      <div className="min-w-0">
        <p className="font-medium text-slate-900 dark:text-slate-100">账号密码登录方式</p>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          自动选择会优先使用可用的协议登录能力，否则使用浏览器登录
        </p>
      </div>
      <div className="relative shrink-0">
        <select
          aria-label="账号密码登录方式"
          value={currentMode}
          disabled={saving}
          onChange={(event) => void handleChange(event.target.value as PasswordLoginMode)}
          className="input-ios w-36 pr-9 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <option value="auto">自动选择</option>
          <option value="protocol">协议登录</option>
          <option value="browser">浏览器登录</option>
        </select>
        {saving && (
          <Loader2 className="pointer-events-none absolute right-8 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-blue-500" />
        )}
      </div>
    </div>
  )
}
