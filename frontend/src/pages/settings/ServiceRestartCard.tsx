/**
 * 系统管理 - 服务重启卡片
 *
 * 功能：
 * 1. 展示后端服务 / 消息服务 / 定时任务服务 三个服务的在线状态
 * 2. 提供三个重启按钮：先杀掉对应端口进程再重新启动（后端自动适配运行环境）
 * 3. 重启后端服务时，界面短暂不可用，自动轮询健康检查直到恢复
 *
 * 仅管理员可见（由父组件控制渲染）。
 */
import { useCallback, useEffect, useState } from 'react'
import { RotateCcw, Server, MessageSquare, Timer } from 'lucide-react'
import { ButtonLoading } from '@/components/common/Loading'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import {
  getServicesStatus,
  restartService,
  type ServiceKey,
  type ServiceStatusItem,
} from '@/api/systemControl'

// 三个服务的展示配置（顺序：消息服务、后端服务、定时任务服务）
const SERVICE_CARDS: Array<{ key: ServiceKey; label: string; icon: typeof Server }> = [
  { key: 'websocket', label: '消息服务', icon: MessageSquare },
  { key: 'backend-web', label: '后端服务', icon: Server },
  { key: 'scheduler', label: '定时任务服务', icon: Timer },
]

// 各服务重启二次确认文案
const CONFIRM_MESSAGE: Record<ServiceKey, string> = {
  'websocket': '确定要重启【消息服务】吗？重启期间账号消息收发会短暂中断，约数秒后自动恢复。',
  'backend-web': '确定要重启【后端服务】吗？重启期间当前管理界面会短暂不可用，恢复后会自动提示。',
  'scheduler': '确定要重启【定时任务服务】吗？重启期间定时任务会短暂暂停，约数秒后自动恢复。',
}

export function ServiceRestartCard() {
  const { addToast } = useUIStore()
  // 三服务在线状态：key -> online
  const [statusMap, setStatusMap] = useState<Record<string, boolean>>({})
  const [statusLoading, setStatusLoading] = useState(false)
  // 正在重启的服务 key（用于按钮 loading）
  const [restartingKey, setRestartingKey] = useState<ServiceKey | null>(null)
  // 二次确认弹窗目标服务
  const [confirmKey, setConfirmKey] = useState<ServiceKey | null>(null)

  // 拉取三服务在线状态
  const loadStatus = useCallback(async () => {
    setStatusLoading(true)
    try {
      const res = await getServicesStatus()
      if (res.success && res.data) {
        const map: Record<string, boolean> = {}
        res.data.services.forEach((s: ServiceStatusItem) => {
          map[s.key] = s.online
        })
        setStatusMap(map)
      }
    } catch {
      // 状态查询失败不打扰用户，仅置为未知（不显示在线）
      setStatusMap({})
    } finally {
      setStatusLoading(false)
    }
  }, [])

  useEffect(() => {
    loadStatus()
  }, [loadStatus])

  // 后端服务重启后：轮询健康检查直到恢复
  const waitBackendRecover = useCallback(async () => {
    const maxAttempts = 30 // 最多等约 30 次
    for (let i = 0; i < maxAttempts; i++) {
      await new Promise((resolve) => setTimeout(resolve, 2000))
      try {
        const res = await fetch('/api/v1/health/ping', { method: 'GET' })
        if (res.ok) {
          addToast({ type: 'success', message: '后端服务已重启完成' })
          loadStatus()
          return
        }
      } catch {
        // 后端尚未恢复，继续轮询
      }
    }
    addToast({ type: 'warning', message: '后端服务重启超时未恢复，请稍后手动刷新页面确认' })
    loadStatus()
  }, [addToast, loadStatus])

  // 执行重启
  const doRestart = useCallback(
    async (key: ServiceKey) => {
      setRestartingKey(key)
      try {
        const res = await restartService(key)
        if (res.success) {
          addToast({ type: 'success', message: res.message || '已触发重启' })
          if (key === 'backend-web') {
            // 后端自身重启：轮询等待恢复
            addToast({ type: 'info', message: '后端服务正在重启，请稍候…' })
            waitBackendRecover()
          } else {
            // 消息/定时任务服务：延迟刷新一次状态
            setTimeout(loadStatus, 4000)
          }
        } else {
          addToast({ type: 'error', message: res.message || '重启失败' })
        }
      } catch (error) {
        addToast({ type: 'error', message: getApiErrorMessage(error, '重启请求失败') })
      } finally {
        setRestartingKey(null)
      }
    },
    [addToast, loadStatus, waitBackendRecover],
  )

  const handleConfirm = useCallback(() => {
    if (confirmKey) {
      const key = confirmKey
      setConfirmKey(null)
      doRestart(key)
    }
  }, [confirmKey, doRestart])

  return (
    <div className="vben-card">
      <div className="vben-card-header flex items-center justify-between gap-3">
        <h2 className="vben-card-title">
          <RotateCcw className="w-4 h-4 text-blue-500" />
          服务管理
        </h2>
        <button onClick={loadStatus} disabled={statusLoading} className="btn-ios-secondary">
          {statusLoading ? <ButtonLoading /> : <RotateCcw className="w-4 h-4" />}
          刷新状态
        </button>
      </div>
      <div className="vben-card-body">
        <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">
          重启服务会先停止对应进程再重新启动，请在必要时操作。重启期间对应功能会短暂不可用。
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {SERVICE_CARDS.map(({ key, label, icon: Icon }) => {
            const online = statusMap[key]
            const isRestarting = restartingKey === key
            return (
              <div
                key={key}
                className="flex flex-col gap-3 rounded-xl border border-slate-200 dark:border-slate-700 p-4"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Icon className="w-5 h-5 text-slate-500 dark:text-slate-300" />
                    <span className="font-medium text-slate-800 dark:text-slate-100">{label}</span>
                  </div>
                  <span
                    className={`inline-flex items-center gap-1 text-xs px-2 py-0.5 rounded-full ${
                      online
                        ? 'bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300'
                        : 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-300'
                    }`}
                  >
                    <span
                      className={`w-1.5 h-1.5 rounded-full ${online ? 'bg-green-500' : 'bg-slate-400'}`}
                    />
                    {online ? '在线' : '离线'}
                  </span>
                </div>
                <button
                  onClick={() => setConfirmKey(key)}
                  disabled={isRestarting}
                  className="btn-ios-secondary w-full justify-center"
                >
                  {isRestarting ? <ButtonLoading /> : <RotateCcw className="w-4 h-4" />}
                  重启{label}
                </button>
              </div>
            )
          })}
        </div>
      </div>

      <ConfirmModal
        isOpen={confirmKey !== null}
        title="重启服务确认"
        message={confirmKey ? CONFIRM_MESSAGE[confirmKey] : ''}
        type="warning"
        confirmText="确定重启"
        cancelText="取消"
        loading={restartingKey !== null}
        onConfirm={handleConfirm}
        onCancel={() => setConfirmKey(null)}
      />
    </div>
  )
}
