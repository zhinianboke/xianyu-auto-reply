/**
 * 滑块滑动方式设置接口。
 *
 * 功能：
 * 1. 规范化滑块滑动方式
 * 2. 独立保存设置，避免提交页面其他未保存内容
 */
import { put } from '@/utils/request'
import type { ApiResponse, SliderMode } from '@/types'

const SLIDER_MODE_URL = '/api/v1/system-settings/captcha.slider_mode'
const SLIDER_MODES: SliderMode[] = ['browser', 'real_mouse']

export const normalizeSliderMode = (value: unknown): SliderMode => {
  return SLIDER_MODES.includes(value as SliderMode)
    ? value as SliderMode
    : 'browser'
}

export const updateSliderMode = (mode: SliderMode): Promise<ApiResponse> => {
  return put<ApiResponse>(SLIDER_MODE_URL, { value: mode })
}
