/**
 * 黑名单管理页面
 * 
 * 功能：
 * - 两个Tab页：个人黑名单、闲鱼黑名单
 * - 每个Tab有独立刷新按钮
 */
import { useState, useRef } from 'react'
import { Button } from '@arco-design/web-react'
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
    <div className="space-y-4">
      <div className="vben-card">
        <div className="accounts-page-intro blacklist-page-intro">
          <div>
            <h1>黑名单管理</h1>
            <p>管理买家拦截名单和闲鱼平台黑名单记录</p>
          </div>
          <Button onClick={handleRefresh} className="accounts-header-btn">
            <RefreshCw />
            刷新
          </Button>
        </div>

        <div className="blacklist-tabs">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`blacklist-tab ${activeTab === tab.key ? 'blacklist-tab--active' : ''}`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {activeTab === 'personal' && (
          <PersonalBlacklist onRefreshRef={personalRefreshRef} />
        )}
        {activeTab === 'platform' && (
          <PlatformBlacklist onRefreshRef={platformRefreshRef} />
        )}
      </div>
    </div>
  )
}

export default Blacklist
