/**
 * 通用确认弹窗组件
 * 
 * 用于替代系统自带的 confirm 弹窗，提供更好的视觉效果
 */
import { motion, AnimatePresence } from 'framer-motion'
import { AlertTriangle, Info, Loader2, X } from 'lucide-react'
import { cn } from '@/utils/cn'

export interface ConfirmModalProps {
  isOpen: boolean
  title?: string
  message: string
  confirmText?: string
  cancelText?: string
  type?: 'warning' | 'danger' | 'info'
  loading?: boolean
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmModal({
  isOpen,
  title = '确认操作',
  message,
  confirmText = '确定',
  cancelText = '取消',
  type = 'warning',
  loading = false,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  const iconMap = {
    warning: <AlertTriangle className="w-6 h-6 text-amber-500" />,
    danger: <AlertTriangle className="w-6 h-6 text-red-500" />,
    info: <Info className="w-6 h-6 text-blue-500" />,
  }

  const confirmBtnClass = {
    warning: 'bg-amber-500 hover:bg-amber-600 text-white',
    danger: 'bg-red-500 hover:bg-red-600 text-white',
    info: 'bg-blue-500 hover:bg-blue-600 text-white',
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center">
          {/* 遮罩层（按规范禁止点击遮罩关闭，仅可通过按钮关闭） */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
          />

          {/* 弹窗内容 */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className={cn(
              'relative w-full max-w-sm mx-4',
              'bg-white dark:bg-slate-800 rounded-2xl shadow-2xl',
              'border border-slate-200 dark:border-slate-700'
            )}
          >
            {/* 关闭按钮 */}
            <button
              onClick={onCancel}
              className="absolute top-3 right-3 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
            >
              <X className="w-4 h-4" />
            </button>

            {/* 内容 */}
            <div className="p-6 text-center">
              <div className="flex justify-center mb-4">
                {iconMap[type]}
              </div>
              <h3 className="text-lg font-semibold text-slate-900 dark:text-white mb-2">
                {title}
              </h3>
              <p className="text-slate-600 dark:text-slate-400">
                {message}
              </p>
            </div>

            {/* 按钮 */}
            <div className="flex gap-3 px-6 pb-6">
              <button
                onClick={onCancel}
                disabled={loading}
                className={cn(
                  'flex-1 px-4 py-2.5 rounded-lg font-medium transition-colors',
                  'bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-300',
                  'hover:bg-slate-200 dark:hover:bg-slate-600',
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                )}
              >
                {cancelText}
              </button>
              <button
                onClick={onConfirm}
                disabled={loading}
                className={cn(
                  'flex-1 px-4 py-2.5 rounded-lg font-medium transition-colors flex items-center justify-center gap-2',
                  confirmBtnClass[type],
                  'disabled:opacity-50 disabled:cursor-not-allowed'
                )}
              >
                {loading && <Loader2 className="w-4 h-4 animate-spin" />}
                {confirmText}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}
