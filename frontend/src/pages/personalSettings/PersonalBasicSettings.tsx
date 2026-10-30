/** 个人设置基础内容，复用原页面的账户、余额及分销界面。 */
import { User, Wallet, Plus, Key, Link2, Copy, RotateCcw, Save, Package, ScrollText, ArrowUpFromLine, QrCode, CalendarClock } from 'lucide-react'
import { getSystemSettings } from '@/api/settings'
import { ButtonLoading } from '@/components/common/Loading'
import { PasswordInput } from '@/components/common/PasswordInput'
import { useUIStore } from '@/store/uiStore'
import type { usePersonalSettingsData } from './usePersonalSettingsData'
import type { usePersonalFinance } from './usePersonalFinance'

interface PersonalBasicSettingsProps {
  settings: ReturnType<typeof usePersonalSettingsData>
  finance: ReturnType<typeof usePersonalFinance>
}

// 格式化到期日展示（后端为北京时间 naive 字符串，无需做时区转换）
// 形如 '2026-06-25T14:30:00' -> '2026-06-25 14:30:00'；空值显示「永不过期」
const formatExpireAt = (value?: string | null): string => {
  if (!value) return '永不过期'
  return value.replace('T', ' ').slice(0, 19)
}

// 判断到期日是否已过期（到期日存在且早于当前时间）
const isExpiredTime = (value?: string | null): boolean => {
  if (!value) return false
  const time = new Date(value).getTime()
  return Number.isFinite(time) && time < Date.now()
}

export function PersonalBasicSettings({ settings, finance }: PersonalBasicSettingsProps) {
  const { addToast } = useUIStore()
  const {
    user,
    balance,
    expireAt,
    setShowRenew,
    setShowFundFlowModal,
    setShowRecharge,
    paymentQrcode,
    paymentType,
    dockCode,
    dockCodeLoading,
    resettingDockCode,
    setResetConfirmOpen,
    secretKey,
    secretKeyLoading,
    resettingSecretKey,
    setSecretKeyResetConfirmOpen,
    cardSecretKey,
    setCardSecretKey,
    savingCardSecretKey,
    creatingCardSecretKey,
    contactWechat,
    setContactWechat,
    contactQQ,
    setContactQQ,
    savingContact,
    redeliveryKeyword,
    setRedeliveryKeyword,
    savingRedeliveryKeyword,
    currentPassword,
    setCurrentPassword,
    newPassword,
    setNewPassword,
    confirmPassword,
    setConfirmPassword,
    changingPassword,
    handleCopyDockCode,
    handleCopySecretKey,
    handleSaveCardSecretKey,
    handleCreateCardSecretKey,
    handleSaveRedeliveryKeyword,
    handleSaveContact,
    handleChangePassword
  } = settings
  const { setShowQrcodeModal, withdrawing, setWithdrawMinAmount, setWithdrawAmount, setShowWithdrawModal, openSettlementModal } = finance
  return (
    <>
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">
            <User className="w-4 h-4" />
            账户信息
          </h2>
        </div>
        <div className="vben-card-body space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="input-label">用户名</label>
              <input
                type="text"
                value={user?.username || ''}
                disabled
                className="input-ios bg-gray-50 dark:bg-gray-800 cursor-not-allowed"
              />
            </div>
            <div>
              <label className="input-label">角色</label>
              <input
                type="text"
                value={user?.is_admin ? '管理员' : '普通用户'}
                disabled
                className="input-ios bg-gray-50 dark:bg-gray-800 cursor-not-allowed"
              />
            </div>
            <div className="md:col-span-2">
              <label className="input-label">账户到期日</label>
              <div className="flex items-center gap-2">
                <input
                  type="text"
                  value={formatExpireAt(expireAt)}
                  disabled
                  className={`input-ios flex-1 bg-gray-50 dark:bg-gray-800 cursor-not-allowed ${isExpiredTime(expireAt) ? 'text-red-500 dark:text-red-400' : ''}`}
                />
                <button
                  onClick={() => setShowRenew(true)}
                  className="btn-ios-primary whitespace-nowrap"
                >
                  <CalendarClock className="w-4 h-4" />
                  续期
                </button>
              </div>
              {isExpiredTime(expireAt) && (
                <p className="mt-1 text-xs text-red-500">账户已到期，请尽快续期以恢复服务。</p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 余额管理 */}
      <div className="vben-card">
        <div className="vben-card-header flex items-center justify-between">
          <h2 className="vben-card-title">
            <Wallet className="w-4 h-4" />
            余额管理
          </h2>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowFundFlowModal(true)}
              className="btn-ios-secondary text-sm"
            >
              <Wallet className="w-4 h-4" />
              资金流水
            </button>
            <button
              onClick={() => setShowQrcodeModal(true)}
              className="btn-ios-secondary text-sm"
            >
              <QrCode className="w-4 h-4" />
              收款码管理
            </button>
            <button
              onClick={async () => {
                if (!paymentQrcode) {
                  addToast({ type: 'warning', message: '请先上传收款码' })
                  return
                }
                // 获取最低提现金额
                try {
                  const sysResult = await getSystemSettings()
                  if (sysResult.success && sysResult.data) {
                    setWithdrawMinAmount(sysResult.data['withdraw.min_amount'] || '')
                  }
                } catch { /* 获取失败不阻断流程 */ }
                setWithdrawAmount('')
                setShowWithdrawModal(true)
              }}
              disabled={withdrawing}
              className="btn-ios-secondary text-sm"
            >
              {withdrawing ? <ButtonLoading /> : <ArrowUpFromLine className="w-4 h-4" />}
              提现
            </button>
            <button
              onClick={openSettlementModal}
              className="btn-ios-secondary text-sm"
            >
              <ScrollText className="w-4 h-4" />
              结算记录
            </button>
            <button
              onClick={() => setShowRecharge(true)}
              className="btn-ios-primary text-sm"
            >
              <Plus className="w-4 h-4" />
              余额充值
            </button>
          </div>
        </div>
        <div className="vben-card-body space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="input-label">当前余额（元）</label>
              <div className="text-2xl font-semibold text-amber-600 dark:text-amber-400">
                ¥{balance || '0.00'}
              </div>
              <p className="text-xs text-gray-500 mt-1">点击"余额充值"按钮可通过支付宝扫码充值</p>
            </div>
            <div>
              <label className="input-label">收款码</label>
              {paymentQrcode ? (
                <div className="flex items-center gap-2">
                  <img
                    src={paymentQrcode.startsWith('http') ? paymentQrcode : paymentQrcode}
                    alt="收款码"
                    className="w-16 h-16 rounded-lg border border-slate-200 dark:border-slate-700 object-contain"
                  />
                  <span className="text-xs text-slate-500">{paymentType === 'wechat' ? '微信' : '支付宝'}收款码</span>
                </div>
              ) : (
                <div className="text-sm text-slate-500 dark:text-slate-400">未上传，点击「收款码管理」上传</div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* 分销管理 */}
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">
            <Link2 className="w-4 h-4" />
            分销管理
          </h2>
        </div>
        <div className="vben-card-body space-y-4">
          <div>
            <label className="input-label">对接码</label>
            <p className="text-xs text-gray-500 mb-2">对接码用于分销商识别您的身份，分享给下级分销商即可对接您的卡券</p>
            <div className="flex items-center gap-3">
              {dockCodeLoading ? (
                <div className="text-sm text-gray-400">加载中...</div>
              ) : (
                <div className="flex items-center gap-2 px-4 py-2.5 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 font-mono text-lg tracking-widest font-semibold text-gray-900 dark:text-white select-all">
                  {dockCode || '-'}
                </div>
              )}
              <button
                onClick={handleCopyDockCode}
                disabled={!dockCode}
                className="btn-ios-secondary text-sm"
                title="复制对接码"
              >
                <Copy className="w-4 h-4" />
                复制
              </button>
              <button
                onClick={() => setResetConfirmOpen(true)}
                disabled={resettingDockCode}
                className="btn-ios-secondary text-sm text-amber-600 dark:text-amber-400"
                title="重置对接码"
              >
                <RotateCcw className={`w-4 h-4 ${resettingDockCode ? 'animate-spin' : ''}`} />
                重置
              </button>
            </div>
          </div>

          {/* 秘钥设置 */}
          <div>
            <label className="input-label">秘钥</label>
            <p className="text-xs text-gray-500 mb-2">分销秘钥为32位随机字符，全局唯一，用于分销接口的身份校验。请妥善保管，可随时更换。</p>
            <div className="flex items-center gap-3 flex-wrap">
              {secretKeyLoading ? (
                <div className="text-sm text-gray-400">加载中...</div>
              ) : (
                <div className="flex items-center px-4 py-2.5 bg-gray-50 dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700 font-mono text-sm tracking-wider font-semibold text-gray-900 dark:text-white break-all select-all">
                  {secretKey || '-'}
                </div>
              )}
              <button
                onClick={handleCopySecretKey}
                disabled={!secretKey}
                className="btn-ios-secondary text-sm"
                title="复制秘钥"
              >
                <Copy className="w-4 h-4" />
                复制
              </button>
              <button
                onClick={() => setSecretKeyResetConfirmOpen(true)}
                disabled={resettingSecretKey}
                className="btn-ios-secondary text-sm text-amber-600 dark:text-amber-400"
                title="更换秘钥"
              >
                <RotateCcw className={`w-4 h-4 ${resettingSecretKey ? 'animate-spin' : ''}`} />
                更换
              </button>
            </div>
          </div>

          {/* 对接卡密秘钥设置 */}
          <div>
            <label className="input-label">对接卡密秘钥</label>
            <p className="text-xs text-gray-500 mb-2">用于「分销卡券」页面对接上游卡券系统的鉴权秘钥，请妥善保管。修改后点击「保存」生效。</p>
            <p className="text-xs text-gray-500 mb-2">秘钥资金流水和余额充值，请进入 <a className="text-xs text-blue-600 dark:text-blue-400 mb-2" href="http://agent.zhinianboke.com" target='_BLANK'>agent.zhinianboke.com</a> 中进行操作。</p>
            <p className="text-xs text-blue-600 dark:text-blue-400 mb-2">如有其他疑问可联系 QQ：531779708 微信：zhinian_znbk</p>
            <div className="flex items-center gap-3 flex-wrap">
              <div className="relative min-w-0 flex-1">
                <PasswordInput
                  value={cardSecretKey}
                  onChange={setCardSecretKey}
                  placeholder="请输入对接卡密秘钥"
                  showLabel="显示秘钥"
                  hideLabel="隐藏秘钥"
                />
              </div>
              <button
                onClick={handleCreateCardSecretKey}
                disabled={creatingCardSecretKey || !!cardSecretKey.trim()}
                className="btn-ios-secondary text-sm"
                title={cardSecretKey.trim() ? '秘钥已存在，如需重新创建请联系管理员重置' : '一键创建对接卡密秘钥'}
              >
                {creatingCardSecretKey ? <ButtonLoading /> : <Plus className="w-4 h-4" />}
                创建
              </button>
              <button
                onClick={handleSaveCardSecretKey}
                disabled={savingCardSecretKey}
                className="btn-ios-primary text-sm"
                title="保存对接卡密秘钥"
              >
                {savingCardSecretKey ? <ButtonLoading /> : <Save className="w-4 h-4" />}
                保存
              </button>
            </div>
          </div>

          {/* 联系方式 */}
          <div>
            <label className="input-label">联系方式</label>
            <p className="text-xs text-gray-500 mb-2">设置您的微信和QQ，方便分销商联系您</p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="input-label">微信</label>
                <input
                  type="text"
                  value={contactWechat}
                  onChange={(e) => setContactWechat(e.target.value)}
                  placeholder="请输入微信号"
                  className="input-ios"
                />
              </div>
              <div>
                <label className="input-label">QQ</label>
                <input
                  type="text"
                  value={contactQQ}
                  onChange={(e) => setContactQQ(e.target.value)}
                  placeholder="请输入QQ号"
                  className="input-ios"
                />
              </div>
            </div>
            <button
              onClick={handleSaveContact}
              disabled={savingContact}
              className="btn-ios-primary mt-3"
            >
              {savingContact ? <ButtonLoading /> : <Save className="w-4 h-4" />}
              保存联系方式
            </button>
          </div>
        </div>
      </div>

      {/* 重发货触发关键字 */}
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">
            <Package className="w-4 h-4" />
            重发货触发关键字
          </h2>
        </div>
        <div className="vben-card-body space-y-4">
          <p className="text-xs text-slate-500 dark:text-slate-400">
            设置后，在闲鱼聊天中自己发送「关键字+订单号」即可触发自动重新发货。例如关键字为「重新触发」，发送「4502144774044041438重新触发」将提取订单号并自动发货。
            <br />
            <span className="text-amber-500 dark:text-amber-400">注意：关键字不包含前后空格；如果订单不在数据库中，系统会自动根据订单号获取订单信息后再发货。</span>
          </p>
          <div className="input-group">
            <label className="input-label">触发关键字</label>
            <input
              type="text"
              value={redeliveryKeyword}
              onChange={(e) => setRedeliveryKeyword(e.target.value)}
              placeholder="例如：重新触发"
              className="input-ios"
            />
            <p className="text-xs text-gray-400 mt-1">保存时会自动去除前后空格；留空则关闭此功能</p>
          </div>
          <button
            onClick={handleSaveRedeliveryKeyword}
            disabled={savingRedeliveryKeyword}
            className="btn-ios-primary"
          >
            {savingRedeliveryKeyword ? <ButtonLoading /> : <Save className="w-4 h-4" />}
            保存
          </button>
        </div>
      </div>

      {/* 修改密码 */}
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title">
            <Key className="w-4 h-4" />
            修改密码
          </h2>
        </div>
        <div className="vben-card-body space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="input-group">
              <label className="input-label">当前密码</label>
              <PasswordInput
                value={currentPassword}
                onChange={setCurrentPassword}
                placeholder="请输入当前密码"
              />
            </div>
            <div />
            <div className="input-group">
              <label className="input-label">新密码</label>
              <PasswordInput
                value={newPassword}
                onChange={setNewPassword}
                placeholder="请输入新密码（至少6位）"
              />
            </div>
            <div className="input-group">
              <label className="input-label">确认新密码</label>
              <PasswordInput
                value={confirmPassword}
                onChange={setConfirmPassword}
                placeholder="请再次输入新密码"
              />
            </div>
          </div>
          <button
            onClick={handleChangePassword}
            disabled={changingPassword}
            className="btn-ios-primary"
          >
            {changingPassword ? <ButtonLoading /> : <Key className="w-4 h-4" />}
            修改密码
          </button>
        </div>
      </div>

    </>
  )
}
