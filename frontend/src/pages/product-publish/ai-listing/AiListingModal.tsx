/**
 * AI 铺货弹窗
 *
 * 功能：
 * 1. 「生成任务」与「配置管理」两个页内选项卡
 * 2. 统一加载配置列表供任务面板的下拉使用
 * 3. 只能通过按钮关闭（点击遮罩不关闭）
 */
import { useCallback, useEffect, useState } from 'react'
import { Loader2, Sparkles, X } from 'lucide-react'
import { getAiListingConfigs, type AiListingConfig, type AiListingTaskDetail } from '@/api/aiListing'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/apiError'
import { AiListingConfigPanel } from './AiListingConfigPanel'
import { AiListingTaskHistory } from './AiListingTaskHistory'
import { AiListingTaskPanel } from './AiListingTaskPanel'

interface AiListingModalProps {
  /** 当前跟踪的任务（由素材库页面持有轮询状态） */
  task: AiListingTaskDetail | null
  /** 启动任务后开始跟踪进度 */
  onStartTracking: (taskId: string) => Promise<void>
  /** 清除当前任务展示 */
  onResetTask: () => void
  /** 关闭弹窗 */
  onClose: () => void
}

export function AiListingModal({ task, onStartTracking, onResetTask, onClose }: AiListingModalProps) {
  const { addToast } = useUIStore()
  const [activeTab, setActiveTab] = useState<'task' | 'history' | 'config'>('task')
  const [configs, setConfigs] = useState<AiListingConfig[]>([])
  const [loading, setLoading] = useState(true)

  const loadConfigs = useCallback(async () => {
    try {
      const res = await getAiListingConfigs(1, 100)
      if (!res.success) {
        addToast({ type: 'error', message: res.message || '加载配置失败' })
        return
      }
      setConfigs(res.data.list)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载配置失败') })
    } finally {
      setLoading(false)
    }
  }, [addToast])

  useEffect(() => {
    void loadConfigs()
  }, [loadConfigs])

  return (
    <div className="modal-overlay">
      <div className="modal-content max-w-4xl h-[min(82vh,760px)] flex flex-col">
        <div className="modal-header">
          <h2 className="modal-title flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-blue-500" />
            AI 铺货
          </h2>
          <button className="modal-close" onClick={onClose}>
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="px-4 pt-3 flex-shrink-0">
          <div className="tabs">
            <button
              className={activeTab === 'task' ? 'tab-active' : 'tab'}
              onClick={() => setActiveTab('task')}
            >
              生成任务
            </button>
            <button
              className={activeTab === 'history' ? 'tab-active' : 'tab'}
              onClick={() => setActiveTab('history')}
            >
              历史任务
            </button>
            <button
              className={activeTab === 'config' ? 'tab-active' : 'tab'}
              onClick={() => setActiveTab('config')}
            >
              配置管理
            </button>
          </div>
        </div>

        <div className="modal-body flex-1 min-h-0 overflow-y-auto">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
              <span className="ml-2 text-sm text-slate-500">加载配置中...</span>
            </div>
          ) : activeTab === 'task' ? (
            <AiListingTaskPanel
              configs={configs}
              task={task}
              onStartTracking={onStartTracking}
              onResetTask={onResetTask}
            />
          ) : activeTab === 'history' ? (
            <AiListingTaskHistory />
          ) : (
            <AiListingConfigPanel onConfigsChanged={loadConfigs} />
          )}
        </div>

        <div className="modal-footer">
          <button className="btn-ios-secondary" onClick={onClose}>关闭</button>
        </div>
      </div>
    </div>
  )
}

export default AiListingModal

