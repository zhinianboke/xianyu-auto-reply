/** 个人设置页面：基础设置、远程 URL 配置及个人资金弹窗。 */
import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { PageLoading } from '@/components/common/Loading'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { RechargeModal } from './RechargeModal'
import { FundFlowModal } from './FundFlowModal'
import { RenewModal } from './RenewModal'
import { PersonalBasicSettings } from './PersonalBasicSettings'
import { PersonalFinanceModals } from './PersonalFinanceModals'
import { LocationRemoteSettingsCard } from './LocationRemoteSettingsCard'
import { TokenRemoteSettingsCard } from './TokenRemoteSettingsCard'
import { usePersonalSettingsData } from './usePersonalSettingsData'
import { usePersonalFinance } from './usePersonalFinance'

export function PersonalSettings() {
  const settings = usePersonalSettingsData()
  const finance = usePersonalFinance(settings)
  const [activeTab, setActiveTab] = useState<'basic' | 'remote'>('basic')
  const [remoteOpened, setRemoteOpened] = useState(false)
  const {
    loading, loadSettings, balance, renewPrice, showRenew, setShowRenew,
    showFundFlowModal, setShowFundFlowModal, showRecharge, setShowRecharge, setExpireAt,
    resetConfirmOpen, resettingDockCode, handleResetDockCode, setResetConfirmOpen,
    secretKeyResetConfirmOpen, resettingSecretKey, handleResetSecretKey, setSecretKeyResetConfirmOpen,
  } = settings

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* 页头 */}
      <div className="page-header flex-between flex-wrap gap-4">
        <div>
          <h1 className="page-title">个人设置</h1>
          <p className="page-description">管理个人账户信息和偏好设置</p>
        </div>
        <button onClick={loadSettings} className="btn-ios-secondary">
          <RefreshCw className="w-4 h-4" />
          刷新
        </button>
      </div>

      {/* 账户信息 */}
      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-700">
        <button type="button" onClick={() => setActiveTab('basic')} className={`border-b-2 px-4 py-2 text-sm font-medium transition ${activeTab === 'basic' ? 'border-[rgb(var(--color-primary))] text-[rgb(var(--color-primary))]' : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'}`}>
          基础设置
        </button>
        <button type="button" onClick={() => { setActiveTab('remote'); setRemoteOpened(true) }} className={`border-b-2 px-4 py-2 text-sm font-medium transition ${activeTab === 'remote' ? 'border-[rgb(var(--color-primary))] text-[rgb(var(--color-primary))]' : 'border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200'}`}>
          远程URL配置
        </button>
      </div>

      <div className={activeTab === 'basic' ? 'space-y-4' : 'hidden'}>
        <PersonalBasicSettings settings={settings} finance={finance} />
      </div>
      {remoteOpened && (
        <div className={activeTab === 'remote' ? 'space-y-4' : 'hidden'}>
          <LocationRemoteSettingsCard />
          <TokenRemoteSettingsCard />
        </div>
      )}

      <ConfirmModal
        isOpen={resetConfirmOpen}
        title="重置对接码"
        message="确定要重置对接码吗？重置后旧对接码将失效，请确保已通知相关分销商。"
        confirmText="确定重置"
        cancelText="取消"
        type="warning"
        loading={resettingDockCode}
        onConfirm={handleResetDockCode}
        onCancel={() => setResetConfirmOpen(false)}
      />

      {/* 更换分销秘钥确认弹窗 */}
      <ConfirmModal
        isOpen={secretKeyResetConfirmOpen}
        title="更换秘钥"
        message="确定要更换分销秘钥吗？更换后将生成新的32位秘钥，旧秘钥立即失效。"
        confirmText="确定更换"
        cancelText="取消"
        type="warning"
        loading={resettingSecretKey}
        onConfirm={handleResetSecretKey}
        onCancel={() => setSecretKeyResetConfirmOpen(false)}
      />

      <PersonalFinanceModals settings={settings} finance={finance} />

      {/* 资金流水弹窗 */}
      <FundFlowModal
        visible={showFundFlowModal}
        onClose={() => setShowFundFlowModal(false)}
      />

      {/* 充值弹窗 */}
      <RechargeModal
        visible={showRecharge}
        onClose={() => setShowRecharge(false)}
        onSuccess={loadSettings}
      />

      {/* 续期弹窗 */}
      <RenewModal
        visible={showRenew}
        unitPrice={renewPrice}
        balance={balance || '0'}
        onClose={() => setShowRenew(false)}
        onSuccess={(newExpireAt) => {
          setExpireAt(newExpireAt)
          setShowRenew(false)
          // 续期会扣减余额，刷新余额与到期日
          loadSettings()
        }}
      />
    </div>
  )
}
