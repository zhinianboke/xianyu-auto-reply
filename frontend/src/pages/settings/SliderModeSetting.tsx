/**
 * 基础设置中的滑块滑动方式切换项。
 *
 * 功能：
 * 1. 展示浏览器自动滑动、真实鼠标滑动两种方式
 * 2. 切换后立即持久化并反馈结果
 */
import { useState } from 'react'
import { Loader2 } from 'lucide-react'

import { normalizeSliderMode, updateSliderMode } from '@/api/sliderModeSettings'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import type { SliderMode } from '@/types'

interface SliderModeSettingProps {
  value: unknown
  onSaved: (mode: SliderMode) => void
}

const MODE_LABELS: Record<SliderMode, string> = {
  browser: '浏览器自动滑动',
  real_mouse: '真实鼠标滑动',
}

export function SliderModeSetting({ value, onSaved }: SliderModeSettingProps) {
  const { addToast } = useUIStore()
  const [saving, setSaving] = useState(false)
  const currentMode = normalizeSliderMode(value)

  const handleChange = async (mode: SliderMode) => {
    if (saving || mode === currentMode) {
      return
    }

    try {
      setSaving(true)
      const result = await updateSliderMode(mode)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '滑块滑动方式切换失败' })
        return
      }

      onSaved(mode)
      addToast({
        type: 'success',
        message: `已切换为${MODE_LABELS[mode]}，后续滑块实时生效`,
      })
    } catch (error) {
      addToast({
        type: 'error',
        message: getApiErrorMessage(error, '滑块滑动方式切换失败'),
      })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="flex items-center justify-between gap-4 py-3 border-t border-slate-100 dark:border-slate-700">
      <div className="min-w-0">
        <p className="font-medium text-slate-900 dark:text-slate-100">滑块滑动方式</p>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          后续滑块任务将使用所选方式执行
        </p>
      </div>
      <div className="relative shrink-0">
        <select
          aria-label="滑块滑动方式"
          value={currentMode}
          disabled={saving}
          onChange={(event) => void handleChange(event.target.value as SliderMode)}
          className="input-ios w-44 pr-9 disabled:cursor-not-allowed disabled:opacity-60"
        >
          <option value="browser">浏览器自动滑动</option>
          <option value="real_mouse">真实鼠标滑动</option>
        </select>
        {saving && (
          <Loader2 className="pointer-events-none absolute right-8 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-blue-500" />
        )}
      </div>
    </div>
  )
}
