/**
 * 系统版本号全局状态
 *
 * 功能：
 * 1. 统一缓存后端返回的系统版本号（唯一来源：GET /api/v1/version/current）
 * 2. 请求去重：多个组件（侧边栏、关于页）同时挂载时只发一次请求
 * 3. 提供 setCurrentVersion，供「检查更新」接口返回的 current_version 回写，保证各处显示一致
 *
 * 说明：版本号属于被动展示信息，获取失败时不弹 toast（避免离线环境反复打扰用户），
 * 界面上不显示版本号即可；用户主动点击「检查更新」时的失败提示由关于页负责。
 */
import { create } from 'zustand'
import { getCurrentVersion } from '@/api/version'

interface VersionState {
  /** 当前系统版本号（不含 v 前缀），未取到时为空字符串 */
  currentVersion: string
  /** 直接写入版本号（供检查更新结果回写） */
  setCurrentVersion: (version: string) => void
  /** 拉取版本号；已有缓存时默认不重复请求，force=true 强制刷新 */
  fetchCurrentVersion: (force?: boolean) => Promise<void>
}

/** 进行中的请求，用于并发去重 */
let inflightRequest: Promise<void> | null = null

export const useVersionStore = create<VersionState>((set, get) => ({
  currentVersion: '',

  setCurrentVersion: (version) => {
    const value = (version || '').trim()
    if (value && value !== get().currentVersion) {
      set({ currentVersion: value })
    }
  },

  fetchCurrentVersion: async (force = false) => {
    if (!force && get().currentVersion) return
    if (inflightRequest) return inflightRequest

    inflightRequest = (async () => {
      try {
        const result = await getCurrentVersion()
        if (result.success && result.data?.version) {
          set({ currentVersion: result.data.version.trim() })
        }
      } catch {
        // 网络异常等失败场景：保持版本号为空，界面隐藏版本标签，不打断用户操作
      } finally {
        inflightRequest = null
      }
    })()

    return inflightRequest
  },
}))
