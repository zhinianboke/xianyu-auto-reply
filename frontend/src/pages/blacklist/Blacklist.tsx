/**
 * 黑名单管理页面
 * 
 * 功能：
 * - 两个Tab页：个人黑名单、闲鱼黑名单
 * - 每个Tab有独立刷新按钮
 */
import { useState, useRef } from 'react'
import { motion } from 'framer-motion'
import { RefreshCw } from 'lucide-react'
import { PersonalBlacklist } from './PersonalBlacklist'
import { PlatformBlacklist } from './PlatformBlacklist'

type TabKey = 'personal' | 'platform'

export function Blacklist() {
  const [activeTab, setActiveTab] = useState<TabKey>('personal')
  const personalRefreshRef = useRef<() => void>(() => {})
  const platformRefreshRef = useRef<() => void>(() => {})

  const tabs: { key: TabKey; label: string }[] = [
    { key: 'personal', label: '个人黑名单' },
    { key: 'platform', label: '闲鱼黑名单' },
  ]

  const handleRefresh = () => {
    if (activeTab === 'personal') {
      personalRefreshRef.current?.()
    } else {
      platformRefreshRef.current?.()
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      className="space-y-4"
    >
      {/* 标题和Tab栏 */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-bold text-slate-800 dark:text-slate-100">黑名单管理</h1>
          <div className="flex border-b border-slate-200 dark:border-slate-700">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.key
                    ? 'border-blue-500 text-blue-600 dark:text-blue-400'
                    : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
        <button
          onClick={handleRefresh}
          className="flex items-center gap-1.5 px-3 py-1.5 text-sm text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-md transition-colors"
          title="刷新"
        >
          <RefreshCw className="w-4 h-4" />
          刷新
        </button>
      </div>

      {/* Tab内容 */}
      <div>
        {activeTab === 'personal' && (
          <PersonalBlacklist onRefreshRef={personalRefreshRef} />
        )}
        {activeTab === 'platform' && (
          <PlatformBlacklist onRefreshRef={platformRefreshRef} />
        )}
      </div>
    </motion.div>
  )
}

export default Blacklist
