/**
 * 基础设置中的滑块滑动方式切换项。
 *
 * 功能：
 * 1. 展示浏览器自动滑动、真实鼠标滑动两种方式
 * 2. 切换后由本模块的保存按钮持久化并反馈结果
 */
import { useEffect, useState } from 'react'
import { Loader2, Save } from 'lucide-react'

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
  const [selectedMode, setSelectedMode] = useState(currentMode)

  useEffect(() => {
    setSelectedMode(currentMode)
  }, [currentMode])

  const handleSave = async () => {
    if (saving || selectedMode === currentMode) {
      return
    }

    try {
      setSaving(true)
      const result = await updateSliderMode(selectedMode)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '滑块滑动方式切换失败' })
        return
      }

      onSaved(selectedMode)
      addToast({
        type: 'success',
        message: `已切换为${MODE_LABELS[selectedMode]}，后续滑块实时生效`,
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
    <div className="flex flex-wrap items-center justify-between gap-3 py-3 border-t border-slate-100 dark:border-slate-700">
      <div className="min-w-0">
        <p className="font-medium text-slate-900 dark:text-slate-100">滑块滑动方式</p>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          后续滑块任务将使用所选方式执行
        </p>
      </div>
      <div className="relative min-w-0 flex-1 sm:flex-none">
        <select
          aria-label="滑块滑动方式"
          value={selectedMode}
          disabled={saving}
          onChange={(event) => setSelectedMode(event.target.value as SliderMode)}
          className="input-ios w-full pr-9 disabled:cursor-not-allowed disabled:opacity-60 sm:w-44"
        >
          <option value="browser">浏览器自动滑动</option>
          <option value="real_mouse">真实鼠标滑动</option>
        </select>
        {saving && (
          <Loader2 className="pointer-events-none absolute right-8 top-1/2 h-4 w-4 -translate-y-1/2 animate-spin text-blue-500" />
        )}
      </div>
      <button
        type="button"
        onClick={() => void handleSave()}
        disabled={saving || selectedMode === currentMode}
        className="btn-ios-secondary"
      >
        {saving && <Loader2 className="h-4 w-4 animate-spin" />}
        {!saving && <Save className="h-4 w-4" />}
        保存滑块方式
      </button>
    </div>
  )
}
