/** 在线安装交互：SSH 测试、幂等提交、增量日志轮询、耗时计时及当前会话恢复。 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { isAxiosError } from 'axios'
import { getOnlineInstallLogs, startOnlineInstall, testSSHConnection, type InstallConnection, type InstallLogs, type InstallTaskTiming } from '@/api/onlineInstall'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { createRequestId } from '@/utils/uuid'
import { forgetInstallTask, readInstallResult, readInstallTask, rememberInstallResult, rememberInstallTask } from '@/utils/onlineInstallSession'

/** 管理本次安装生命周期；SSH 密码、私钥及口令只保留在内存，不写入浏览器存储。 */
export function useOnlineInstall() {
  const addToast = useUIStore(state => state.addToast)
  const [taskId, setTaskId] = useState<string | null>(null)
  const [restoring, setRestoring] = useState(true)
  const [testing, setTesting] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [running, setRunning] = useState(false)
  const [polling, setPolling] = useState(false)
  const [logs, setLogs] = useState('')
  const [result, setResult] = useState<InstallLogs | null>(null)
  const [timing, setTiming] = useState<InstallTaskTiming | null>(null)
  const [elapsedSeconds, setElapsedSeconds] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [serverInfo, setServerInfo] = useState('')
  const cursor = useRef(0)
  const inFlight = useRef(false)
  const pendingRequest = useRef<{ id: string; signature: string } | null>(null)
  const lastResultMessage = useRef('')
  const mounted = useRef(true)
  const pollGeneration = useRef(0)
  const canReset = !!result?.finished && !running && !polling && !restoring && !testing && !submitting

  // 以服务器耗时为基准，使用单调时钟补齐轮询间隔；浏览器时区、改时和刷新不会重置计时。
  useEffect(() => {
    if (!timing) { setElapsedSeconds(null); return }
    const receivedAt = performance.now()
    const updateElapsed = () => setElapsedSeconds(Math.floor(timing.elapsed_seconds + (timing.finished ? 0 : (performance.now() - receivedAt) / 1000)))
    updateElapsed()
    if (timing.finished) return
    const timer = setInterval(updateElapsed, 1000)
    return () => clearInterval(timer)
  }, [timing])

  const elapsedText = elapsedSeconds === null ? null : [
    Math.floor(elapsedSeconds / 3600), Math.floor(elapsedSeconds / 60) % 60, elapsedSeconds % 60,
  ].map(part => String(part).padStart(2, '0')).join(':')

  useEffect(() => {
    mounted.current = true
    return () => { mounted.current = false }
  }, [])

  const showError = useCallback((message: string) => {
    if (!mounted.current) return
    setError(message)
    addToast({ type: 'error', message })
  }, [addToast])

  /** 网络错误复用公共错误提取，不包装或覆盖后端业务 message。 */
  const showNetworkError = useCallback((reason: unknown) => {
    const fallback = '无法连接安装服务，请检查网络后重试'
    if (isAxiosError(reason) && !reason.response) {
      showError(reason.code === 'ECONNABORTED' || reason.code === 'ETIMEDOUT'
        ? '安装服务请求超时，请重新读取日志确认任务状态'
        : fallback)
      return
    }
    showError(getApiErrorMessage(reason, fallback))
  }, [showError])

  useEffect(() => {
    let cancelled = false
    void readInstallTask().then(async id => {
      if (cancelled) return
      setTaskId(id)
      if (!id) return
      const completed = await readInstallResult(id).catch(reason => {
        if (!cancelled) showNetworkError(reason)
        return null
      })
      if (cancelled) return
      if (completed) {
        cursor.current = completed.cursor
        lastResultMessage.current = completed.message
        setResult(completed)
        setTiming(completed)
        setLogs(completed.logs.join(''))
        setRunning(false)
        setPolling(false)
        return
      }
      setRunning(true)
      setPolling(true)
    }).catch(reason => {
      if (!cancelled) showNetworkError(reason)
    }).finally(() => {
      if (!cancelled) setRestoring(false)
    })
    return () => { cancelled = true }
  }, [showNetworkError])

  /** 修改连接配置后清除旧测试结果，避免把其他凭据的成功状态用于当前连接。 */
  const clearConnectionTest = useCallback(() => { setServerInfo('') }, [])

  const testConnection = useCallback((connection: InstallConnection) => {
    if (inFlight.current || running || polling || restoring || (taskId && !canReset)) return
    inFlight.current = true
    setTesting(true)
    setError('')
    setServerInfo('')
    void testSSHConnection(connection).then(response => {
      if (!mounted.current) return
      if (!response.success || !response.data) { showError(response.message); return }
      setServerInfo(`${response.data.server_info} · ${response.data.response_time} 毫秒`)
      addToast({ type: 'success', message: response.message })
    }).catch(showNetworkError).finally(() => {
      inFlight.current = false
      if (mounted.current) setTesting(false)
    })
  }, [running, polling, restoring, taskId, canReset, addToast, showError, showNetworkError])

  const startInstall = useCallback((connection: InstallConnection) => {
    if (inFlight.current || running || polling || restoring || (taskId && !canReset)) return
    let id: string | null = null
    let submitted = false
    inFlight.current = true
    setSubmitting(true)
    setError('')
    setServerInfo('')
    setLogs('')
    setResult(null)
    setTiming(null)
    setTaskId(null)
    cursor.current = 0
    lastResultMessage.current = ''
    pollGeneration.current += 1
    // 存储与请求都放入 Promise，浏览器存储异常也会给用户明确反馈。
    // 提交结果未知时保留 UUID，刷新可读取原任务，避免重复安装。
    void Promise.resolve().then(async () => {
      const signature = JSON.stringify(connection)
      if (!pendingRequest.current || pendingRequest.current.signature !== signature) {
        pendingRequest.current = { id: createRequestId(), signature }
      }
      id = pendingRequest.current.id
      await rememberInstallTask(id)
      submitted = true
      return startOnlineInstall(id, connection)
    }).then(async response => {
      if (!mounted.current) return
      if (!response.success || !response.data) {
        submitted = false
        showError(response.message)
        await forgetInstallTask()
        return
      }
      cursor.current = 0
      setLogs('')
      setResult(null)
      lastResultMessage.current = ''
      setTaskId(response.data.task_id)
      setTiming(response.data)
      setRunning(true)
      setPolling(true)
      pendingRequest.current = null
      addToast({ type: 'info', message: response.message })
    }).catch(reason => {
      if (!mounted.current) return
      if (submitted && id) {
        cursor.current = 0
        setTaskId(id)
        setRunning(true)
        setPolling(false)
      }
      showNetworkError(reason)
    }).finally(() => {
      inFlight.current = false
      if (mounted.current) setSubmitting(false)
    })
  }, [running, polling, restoring, taskId, canReset, addToast, showError, showNetworkError])

  useEffect(() => {
    if (!taskId || !polling) return
    let cancelled = false
    const generation = ++pollGeneration.current
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = () => {
      void getOnlineInstallLogs(taskId, cursor.current).then(response => {
        if (cancelled || pollGeneration.current !== generation) return
        if (!response.success || !response.data) {
          setPolling(false)
          showError(response.message)
          return
        }
        const data = response.data
        cursor.current = data.cursor
        // 兼容旧后端的完成响应：不追加尚未读完的下载进度，只展示真实结果 message。
        const output = data.finished
          ? (data.has_more ? `\n${data.message}\n` : data.logs.slice(-1).join('') || `\n${data.message}\n`)
          : data.logs.join('')
        setLogs(current => current + output)
        setResult(data)
        setTiming(data)
        setError('')
        // 任务完成立即停止安装状态、计时和轮询，无需等待历史日志游标追平。
        setRunning(!data.finished)
        if (data.finished) {
          // 保存明确字段和最终日志，刷新已完成任务时无需请求或重播历史输出。
          void rememberInstallResult(data, output).catch(showNetworkError)
          if (lastResultMessage.current !== data.message) {
            lastResultMessage.current = data.message
            addToast({ type: data.success ? 'success' : 'error', message: data.message })
          }
          setPolling(false)
          return
        }
        timer = setTimeout(poll, data.has_more ? 50 : 2000)
      }).catch(reason => {
        if (cancelled || pollGeneration.current !== generation) return
        setPolling(false)
        showNetworkError(reason)
      })
    }
    poll()
    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [taskId, polling, addToast, showError, showNetworkError])

  const resumeLogs = () => {
    if (inFlight.current || restoring || polling || !taskId || result?.finished) return
    pollGeneration.current += 1
    cursor.current = 0
    setLogs('')
    setResult(null)
    setError('')
    setPolling(true)
  }
  const resetTask = () => {
    if (inFlight.current || !canReset) return
    inFlight.current = true
    void forgetInstallTask().then(() => {
      if (!mounted.current) return
      pollGeneration.current += 1
      setTaskId(null)
      setRunning(false)
      setPolling(false)
      setResult(null)
      setTiming(null)
      setLogs('')
      setError('')
      setServerInfo('')
      pendingRequest.current = null
      lastResultMessage.current = ''
      cursor.current = 0
    }).catch(showNetworkError).finally(() => { inFlight.current = false })
  }

  return { restoring, testing, submitting, running, polling, canReset, elapsedText, logs, result, error, serverInfo, taskId, testConnection, clearConnectionTest, startInstall, resumeLogs, resetTask }
}
