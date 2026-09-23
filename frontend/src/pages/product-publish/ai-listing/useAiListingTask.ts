/**
 * AI 铺货任务轮询 Hook
 *
 * 功能：
 * 1. 轮询任务进度（3 秒一次，带 in-flight 保护，避免请求堆积）
 * 2. 任务结束或状态失效时立即停表，业务失败展示后端返回的 message
 * 3. 用 sessionStorage 记住进行中的任务，重新打开弹窗可恢复进度
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { getAiListingTask, type AiListingTaskDetail } from '@/api/aiListing'
import { useUIStore } from '@/store/uiStore'

/** 轮询间隔，与批量发布保持一致 */
const POLL_INTERVAL = 3000

/** 进行中任务的 sessionStorage 键名 */
const STORAGE_KEY = 'ai_listing_active_task_id'

interface UseAiListingTaskOptions {
  /** 任务结束时回调（成功/部分成功/失败/取消都会触发） */
  onFinished?: (task: AiListingTaskDetail) => void
}

export function useAiListingTask({ onFinished }: UseAiListingTaskOptions = {}) {
  const { addToast } = useUIStore()
  const [task, setTask] = useState<AiListingTaskDetail | null>(null)

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)
  // 单次请求未返回时不再发起下一次，避免慢响应下请求叠加
  const busyRef = useRef(false)
  // 世代号：用户点「清除」或切换任务后，在飞请求的结果要作废
  const runIdRef = useRef(0)
  const onFinishedRef = useRef(onFinished)
  onFinishedRef.current = onFinished

  const readStoredTaskId = (): string | null => {
    try {
      return sessionStorage.getItem(STORAGE_KEY)
    } catch {
      return null
    }
  }

  const storeTaskId = (taskId: string) => {
    try {
      sessionStorage.setItem(STORAGE_KEY, taskId)
    } catch {
      // 隐私模式下写入失败不影响主流程
    }
  }

  const clearStoredTaskId = () => {
    try {
      sessionStorage.removeItem(STORAGE_KEY)
    } catch {
      // 忽略
    }
  }

  const stopPolling = useCallback(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current)
      timerRef.current = null
    }
    busyRef.current = false
  }, [])

  /** 查询一次任务状态；返回任务是否仍在进行中 */
  const syncOnce = useCallback(async (taskId: string): Promise<boolean> => {
    if (busyRef.current) return true
    busyRef.current = true
    const runId = runIdRef.current
    try {
      const res = await getAiListingTask(taskId)
      // 请求返回时若已被清除或切换到别的任务，丢弃这次结果
      if (runId !== runIdRef.current) return false

      if (!res.success || !res.data) {
        stopPolling()
        clearStoredTaskId()
        addToast({ type: 'warning', message: res.message || '任务状态已失效' })
        return false
      }

      setTask(res.data)
      if (res.data.finished) {
        stopPolling()
        clearStoredTaskId()
        onFinishedRef.current?.(res.data)
        return false
      }
      return true
    } catch {
      // 网络抖动静默处理，下一轮继续（避免轮询失败刷屏）
      return true
    } finally {
      busyRef.current = false
    }
  }, [addToast, stopPolling])

  const startPolling = useCallback((taskId: string) => {
    stopPolling()
    storeTaskId(taskId)
    timerRef.current = setInterval(() => {
      void syncOnce(taskId)
    }, POLL_INTERVAL)
  }, [stopPolling, syncOnce])

  /** 启动跟踪：立刻查一次并开始轮询 */
  const startTracking = useCallback(async (taskId: string) => {
    runIdRef.current += 1
    storeTaskId(taskId)
    const running = await syncOnce(taskId)
    if (running) startPolling(taskId)
  }, [startPolling, syncOnce])

  /** 恢复跟踪：重新打开弹窗时读取上次进行中的任务 */
  const restoreTracking = useCallback(async () => {
    const taskId = readStoredTaskId()
    if (!taskId) return
    const runId = runIdRef.current
    try {
      const res = await getAiListingTask(taskId)
      if (runId !== runIdRef.current) return
      if (!res.success || !res.data) {
        clearStoredTaskId()
        return
      }
      setTask(res.data)
      if (!res.data.finished) startPolling(taskId)
      else clearStoredTaskId()
    } catch {
      // 查询失败时保留缓存，下次打开再试
    }
  }, [startPolling])

  /** 放弃跟踪当前任务（不影响后端执行） */
  const resetTask = useCallback(() => {
    runIdRef.current += 1
    stopPolling()
    clearStoredTaskId()
    setTask(null)
  }, [stopPolling])

  useEffect(() => stopPolling, [stopPolling])

  return { task, startTracking, restoreTracking, resetTask, refresh: syncOnce }
}

