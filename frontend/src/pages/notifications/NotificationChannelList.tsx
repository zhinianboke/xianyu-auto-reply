/**
 * 通知渠道类型选择与已配置渠道列表。
 */
import { motion } from 'framer-motion'
import { Bell, Plus, Settings } from 'lucide-react'
import type { NotificationChannel } from '@/types'
import { channelTypeLabels, channelTypes } from './notificationChannelConfig'
import type { ChannelType } from './notificationChannelConfig'

interface NotificationChannelListProps {
  channels: NotificationChannel[]
  typeCounts: Record<string, number>
  notifyTypesUnavailable: boolean
  operatingChannelId: string | null
  onCreate: (type: ChannelType) => void
  onToggle: (channel: NotificationChannel) => void
  onTest: (id: string) => void
  onEdit: (channel: NotificationChannel) => void
  onDelete: (id: string) => void
}

export function NotificationChannelList({
  channels,
  typeCounts,
  notifyTypesUnavailable,
  operatingChannelId,
  onCreate,
  onToggle,
  onTest,
  onEdit,
  onDelete,
}: NotificationChannelListProps) {
  const countByType = (type: string) => typeCounts[type] || 0

  return (
    <>
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title"><Settings className="w-4 h-4" />选择通知方式</h2>
        </div>
        <div className="vben-card-body">
          <p className="text-sm text-slate-500 dark:text-slate-400 mb-4">点击下方按钮选择通知渠道类型新建，同一类型可创建多个</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-4">
            {channelTypes.map((channelType, index) => {
              const configuredCount = countByType(channelType.type)
              const Icon = channelType.icon
              return (
                <motion.div
                  key={channelType.type}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: index * 0.03 }}
                  className={`relative p-4 rounded-xl border-2 transition-all ${configuredCount > 0
                    ? 'border-blue-200 dark:border-blue-800 bg-blue-50/50 dark:bg-blue-900/20'
                    : 'border-slate-200 dark:border-slate-700 hover:border-blue-300 dark:hover:border-blue-600'}`}
                >
                  {configuredCount > 0 && (
                    <span className="absolute top-2 right-2 min-w-[1.25rem] h-5 px-1.5 inline-flex items-center justify-center text-xs font-medium rounded-full bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400">
                      {configuredCount}
                    </span>
                  )}
                  <div className="text-center">
                    <div className={`w-10 h-10 mx-auto mb-2 rounded-lg flex items-center justify-center ${configuredCount > 0
                      ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600 dark:text-blue-400'
                      : 'bg-slate-100 dark:bg-slate-700 text-slate-500'}`}
                    >
                      <Icon className="w-5 h-5" />
                    </div>
                    <h3 className="font-medium text-slate-900 dark:text-slate-100 text-sm">{channelType.label}</h3>
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">{channelType.desc}</p>
                    <button
                      onClick={() => onCreate(channelType.type)}
                      disabled={notifyTypesUnavailable}
                      className="mt-3 text-xs px-3 py-1 rounded border border-blue-300 dark:border-blue-600 text-blue-600 dark:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/30"
                    >
                      <Plus className="w-3 h-3 inline mr-1" />{configuredCount > 0 ? '新建' : '配置'}
                    </button>
                  </div>
                </motion.div>
              )
            })}
          </div>
        </div>
      </div>

      {channels.length > 0 && (
        <div className="vben-card">
          <div className="vben-card-header">
            <h2 className="vben-card-title"><Bell className="w-4 h-4" />已配置渠道</h2>
          </div>
          <div className="vben-card-body">
            <div className="table-scroll divide-y divide-slate-100 dark:divide-slate-700">
              {channels.map((channel) => (
                <div key={channel.id} className="flex flex-wrap gap-3 items-center justify-between py-3">
                  <div className="flex items-center gap-3">
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${channel.enabled
                      ? 'bg-blue-100 dark:bg-blue-900/50 text-blue-600'
                      : 'bg-slate-100 dark:bg-slate-700 text-slate-500'}`}
                    >
                      <Bell className="w-4 h-4" />
                    </div>
                    <div>
                      <p className="font-medium text-slate-900 dark:text-slate-100">{channel.name}</p>
                      <p className="text-xs text-slate-500">{channelTypeLabels[channel.type] || channel.type}</p>
                      {channel.config_error && <p className="text-xs text-red-600 dark:text-red-400">{channel.config_error}</p>}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => onToggle(channel)}
                      disabled={operatingChannelId === channel.id}
                      title={channel.enabled ? '点击禁用' : '点击启用'}
                      className={`text-xs px-2 py-0.5 rounded transition-colors ${channel.enabled
                        ? 'bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-400 hover:bg-green-200 dark:hover:bg-green-800'
                        : 'bg-slate-100 text-slate-500 dark:bg-slate-700 hover:bg-slate-200 dark:hover:bg-slate-600'}`}
                    >
                      {operatingChannelId === channel.id ? '处理中...' : channel.enabled ? '启用' : '禁用'}
                    </button>
                    <button disabled={operatingChannelId === channel.id} onClick={() => onTest(channel.id)} className="text-xs text-blue-600 dark:text-blue-400 hover:underline disabled:opacity-50">测试</button>
                    <button disabled={operatingChannelId === channel.id} onClick={() => onEdit(channel)} className="text-xs text-blue-600 dark:text-blue-400 hover:underline disabled:opacity-50">编辑</button>
                    <button disabled={operatingChannelId === channel.id} onClick={() => onDelete(channel.id)} className="text-xs text-red-600 dark:text-red-400 hover:underline disabled:opacity-50">删除</button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      {channels.length === 0 && (
        <div className="vben-card p-8 text-center text-slate-500 dark:text-slate-400">
          <Bell className="mx-auto mb-2 h-8 w-8 text-slate-300" />暂无已配置渠道
        </div>
      )}
    </>
  )
}
