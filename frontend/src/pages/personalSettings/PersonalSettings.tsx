/**
 * 个人设置页面
 * 
 * 功能：
 * 1. 显示和编辑个人余额
 * 2. 修改登录密码
 * 3. 后续可扩展更多个人设置项
 */
import { useState, useEffect, useRef } from 'react'
import { User, RefreshCw, Wallet, Plus, Key, Link2, Copy, RotateCcw, Save, Package, X, ScrollText, ArrowUpFromLine, Upload, QrCode, Eye, EyeOff } from 'lucide-react'
import { getUserSetting, updateUserSetting, changePassword, getDockCode, resetDockCode, getSecretKey, resetSecretKey, uploadPaymentQrcode, getSystemSettings } from '@/api/settings'
import { createWithdraw, getSettlementRecords, type SettlementRecord } from '@/api/payment'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading, ButtonLoading } from '@/components/common/Loading'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { RechargeModal } from './RechargeModal'
import { FundFlowModal } from './FundFlowModal'

// 余额设置的 key
const BALANCE_KEY = 'balance'
const CONTACT_WECHAT_KEY = 'contact_wechat'
const CONTACT_QQ_KEY = 'contact_qq'
const REDELIVERY_TRIGGER_KEYWORD_KEY = 'redelivery_trigger_keyword'
const PAYMENT_QRCODE_KEY = 'payment_qrcode'
const PAYMENT_TYPE_KEY = 'payment_type'
// 对接卡密秘钥的 key（按用户存储，用于「分销卡券」页面对接上游卡券系统）
const CARD_SECRET_KEY = 'distribution.card_secret_key'

export function PersonalSettings() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated, user, clearAuth } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [balance, setBalance] = useState('')
  const [showRecharge, setShowRecharge] = useState(false)
  const [showFundFlowModal, setShowFundFlowModal] = useState(false)
  const [showSettlementModal, setShowSettlementModal] = useState(false)
  const [settlementRecords, setSettlementRecords] = useState<SettlementRecord[]>([])
  const [settlementLoading, setSettlementLoading] = useState(false)
  const [settlementPage, setSettlementPage] = useState(1)
  const [settlementPageSize, setSettlementPageSize] = useState(20)
  const [settlementTotal, setSettlementTotal] = useState(0)
  const [settlementTotalPages, setSettlementTotalPages] = useState(0)
  const [withdrawing, setWithdrawing] = useState(false)
  const [showWithdrawModal, setShowWithdrawModal] = useState(false)
  const [withdrawAmount, setWithdrawAmount] = useState('')
  const [withdrawMinAmount, setWithdrawMinAmount] = useState('')  // 最低提现金额
  // 收款码状态
  const [showQrcodeModal, setShowQrcodeModal] = useState(false)
  const [paymentQrcode, setPaymentQrcode] = useState('')
  const [paymentType, setPaymentType] = useState<'alipay' | 'wechat'>('alipay')
  const [uploadingQrcode, setUploadingQrcode] = useState(false)
  const qrcodeFileRef = useRef<HTMLInputElement>(null)

  // 对接码状态
  const [dockCode, setDockCode] = useState('')
  const [dockCodeLoading, setDockCodeLoading] = useState(false)
  const [resettingDockCode, setResettingDockCode] = useState(false)
  const [resetConfirmOpen, setResetConfirmOpen] = useState(false)

  // 分销秘钥状态
  const [secretKey, setSecretKey] = useState('')
  const [secretKeyLoading, setSecretKeyLoading] = useState(false)
  const [resettingSecretKey, setResettingSecretKey] = useState(false)
  const [secretKeyResetConfirmOpen, setSecretKeyResetConfirmOpen] = useState(false)

  // 对接卡密秘钥状态（用于分销卡券对接上游系统）
  const [cardSecretKey, setCardSecretKey] = useState('')
  const [savingCardSecretKey, setSavingCardSecretKey] = useState(false)
  const [showCardSecretKey, setShowCardSecretKey] = useState(false)

  // 联系方式状态
  const [contactWechat, setContactWechat] = useState('')
  const [contactQQ, setContactQQ] = useState('')
  const [savingContact, setSavingContact] = useState(false)

  // 重发货触发关键字状态
  const [redeliveryKeyword, setRedeliveryKeyword] = useState('')
  const [savingRedeliveryKeyword, setSavingRedeliveryKeyword] = useState(false)

  // 密码修改状态
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [changingPassword, setChangingPassword] = useState(false)

  // 加载个人设置
  const loadSettings = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getUserSetting(BALANCE_KEY)
      if (result.success && result.value !== undefined) {
        setBalance(result.value)
      } else {
        setBalance('0.00')
      }
      const qrcodeResult = await getUserSetting(PAYMENT_QRCODE_KEY)
      if (qrcodeResult.success && qrcodeResult.value) {
        setPaymentQrcode(qrcodeResult.value)
      }
      const typeResult = await getUserSetting(PAYMENT_TYPE_KEY)
      if (typeResult.success && typeResult.value) {
        setPaymentType(typeResult.value as 'alipay' | 'wechat')
      }
      // 加载重发货触发关键字
      const redeliveryResult = await getUserSetting(REDELIVERY_TRIGGER_KEYWORD_KEY)
      if (redeliveryResult.success && redeliveryResult.value !== undefined) {
        setRedeliveryKeyword(redeliveryResult.value)
      }
      // 加载联系方式
      const wechatResult = await getUserSetting(CONTACT_WECHAT_KEY)
      if (wechatResult.success && wechatResult.value !== undefined) {
        setContactWechat(wechatResult.value)
      }
      const qqResult = await getUserSetting(CONTACT_QQ_KEY)
      if (qqResult.success && qqResult.value !== undefined) {
        setContactQQ(qqResult.value)
      }
      // 加载对接卡密秘钥
      const cardKeyResult = await getUserSetting(CARD_SECRET_KEY)
      if (cardKeyResult.success && cardKeyResult.value !== undefined) {
        setCardSecretKey(cardKeyResult.value)
      }
    } catch {
      setBalance('0.00')
    } finally {
      setLoading(false)
    }
  }

  // 加载对接码
  const loadDockCode = async () => {
    try {
      setDockCodeLoading(true)
      const result = await getDockCode()
      if (result.success && result.dock_code) {
        setDockCode(result.dock_code)
      }
    } catch {
      // 静默失败
    } finally {
      setDockCodeLoading(false)
    }
  }

  // 重置对接码
  const handleResetDockCode = async () => {
    try {
      setResettingDockCode(true)
      const result = await resetDockCode()
      if (result.success) {
        addToast({ type: 'success', message: '对接码已重置' })
        await loadDockCode()
      } else {
        addToast({ type: 'error', message: result.message || '重置失败' })
      }
    } catch {
      addToast({ type: 'error', message: '重置对接码失败' })
    } finally {
      setResettingDockCode(false)
      setResetConfirmOpen(false)
    }
  }

  // 复制对接码
  const handleCopyDockCode = () => {
    if (!dockCode) return
    navigator.clipboard.writeText(dockCode).then(() => {
      addToast({ type: 'success', message: '对接码已复制到剪贴板' })
    }).catch(() => {
      addToast({ type: 'error', message: '复制失败，请手动复制' })
    })
  }

  // 加载分销秘钥
  const loadSecretKey = async () => {
    try {
      setSecretKeyLoading(true)
      const result = await getSecretKey()
      if (result.success && result.secret_key) {
        setSecretKey(result.secret_key)
      }
    } catch {
      // 静默失败
    } finally {
      setSecretKeyLoading(false)
    }
  }

  // 更换分销秘钥
  const handleResetSecretKey = async () => {
    try {
      setResettingSecretKey(true)
      const result = await resetSecretKey()
      if (result.success) {
        addToast({ type: 'success', message: '分销秘钥已更换' })
        if (result.data?.secret_key) {
          setSecretKey(result.data.secret_key)
        } else {
          await loadSecretKey()
        }
      } else {
        addToast({ type: 'error', message: result.message || '更换失败' })
      }
    } catch {
      addToast({ type: 'error', message: '更换分销秘钥失败' })
    } finally {
      setResettingSecretKey(false)
      setSecretKeyResetConfirmOpen(false)
    }
  }

  // 复制分销秘钥
  const handleCopySecretKey = () => {
    if (!secretKey) return
    navigator.clipboard.writeText(secretKey).then(() => {
      addToast({ type: 'success', message: '分销秘钥已复制到剪贴板' })
    }).catch(() => {
      addToast({ type: 'error', message: '复制失败，请手动复制' })
    })
  }

  // 保存对接卡密秘钥
  const handleSaveCardSecretKey = async () => {
    try {
      setSavingCardSecretKey(true)
      const result = await updateUserSetting(CARD_SECRET_KEY, cardSecretKey.trim(), '对接卡密秘钥')
      if (result.success) {
        addToast({ type: 'success', message: '对接卡密秘钥已保存' })
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch {
      addToast({ type: 'error', message: '保存对接卡密秘钥失败' })
    } finally {
      setSavingCardSecretKey(false)
    }
  }

  const loadSettlementRecords = async (page: number = 1, pageSize: number = settlementPageSize) => {
    try {
      setSettlementLoading(true)
      const result = await getSettlementRecords(page, pageSize)
      if (result.success && result.data) {
        setSettlementRecords(result.data.list)
        setSettlementPage(result.data.page)
        setSettlementPageSize(result.data.page_size)
        setSettlementTotal(result.data.total)
        setSettlementTotalPages(result.data.total_pages)
      } else {
        setSettlementRecords([])
        addToast({ type: 'error', message: result.message || '加载结算记录失败' })
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
      const errorMsg = err?.response?.data?.detail || err?.response?.data?.message || err?.message || '加载结算记录失败'
      addToast({ type: 'error', message: errorMsg })
      setSettlementRecords([])
    } finally {
      setSettlementLoading(false)
    }
  }

  useEffect(() => {
    loadSettings()
    loadDockCode()
    loadSecretKey()
  }, [_hasHydrated, isAuthenticated, token])

  // 保存重发货触发关键字
  const handleSaveRedeliveryKeyword = async () => {
    try {
      setSavingRedeliveryKeyword(true)
      const trimmed = redeliveryKeyword.trim()
      await updateUserSetting(REDELIVERY_TRIGGER_KEYWORD_KEY, trimmed, '重发货触发关键字')
      setRedeliveryKeyword(trimmed)
      addToast({ type: 'success', message: '重发货触发关键字保存成功' })
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setSavingRedeliveryKeyword(false)
    }
  }

  // 上传收款码
  const handleUploadQrcode = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    try {
      setUploadingQrcode(true)
      const result = await uploadPaymentQrcode(file, paymentType)
      if (result.success && result.data?.image_url) {
        setPaymentQrcode(result.data.image_url)
        setShowQrcodeModal(false)
        addToast({ type: 'success', message: '收款码上传成功' })
      } else {
        addToast({ type: 'error', message: result.message || '上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '上传失败' })
    } finally {
      setUploadingQrcode(false)
      e.target.value = ''
    }
  }

  const handleWithdraw = async () => {
    if (!paymentQrcode) {
      addToast({ type: 'warning', message: '请先上传收款码' })
      return
    }

    if (!withdrawAmount.trim()) {
      addToast({ type: 'warning', message: '请输入提现金额' })
      return
    }

    const currentBalance = Number(balance || '0')
    const amountValue = Number(withdrawAmount.trim())

    // 校验最低提现金额
    if (withdrawMinAmount) {
      const minAmt = Number(withdrawMinAmount)
      if (minAmt > 0 && amountValue < minAmt) {
        addToast({ type: 'warning', message: `提现金额不能低于最低提现金额 ¥${minAmt}` })
        return
      }
    }

    if (!Number.isFinite(amountValue) || amountValue <= 0) {
      addToast({ type: 'warning', message: '提现金额必须大于0' })
      return
    }

    if (amountValue > currentBalance) {
      addToast({ type: 'warning', message: '提现金额不能大于当前余额' })
      return
    }

    try {
      setWithdrawing(true)
      const result = await createWithdraw(withdrawAmount.trim())
      if (result.success) {
        const nextBalance = result.data?.balance
        if (nextBalance !== undefined) {
          setBalance(nextBalance)
        } else {
          await loadSettings()
        }
        setWithdrawAmount('')
        setShowWithdrawModal(false)
        addToast({ type: 'success', message: result.message || '提现申请已提交，等待审核' })
        await loadSettlementRecords(1, settlementPageSize)
        setShowSettlementModal(true)
      } else {
        addToast({ type: 'error', message: result.message || '提现申请失败' })
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
      const errorMsg = err?.response?.data?.detail || err?.response?.data?.message || err?.message || '提现申请失败'
      addToast({ type: 'error', message: errorMsg })
    } finally {
      setWithdrawing(false)
    }
  }

  const openSettlementModal = async () => {
    setShowSettlementModal(true)
    await loadSettlementRecords(1, settlementPageSize)
  }

  // 保存联系方式
  const handleSaveContact = async () => {
    try {
      setSavingContact(true)
      await updateUserSetting(CONTACT_WECHAT_KEY, contactWechat, '微信联系方式')
      await updateUserSetting(CONTACT_QQ_KEY, contactQQ, 'QQ联系方式')
      addToast({ type: 'success', message: '联系方式保存成功' })
    } catch {
      addToast({ type: 'error', message: '保存联系方式失败' })
    } finally {
      setSavingContact(false)
    }
  }

  // 修改密码
  const handleChangePassword = async () => {
    if (!currentPassword) {
      addToast({ type: 'warning', message: '请输入当前密码' })
      return
    }
    if (!newPassword) {
      addToast({ type: 'warning', message: '请输入新密码' })
      return
    }
    if (newPassword !== confirmPassword) {
      addToast({ type: 'warning', message: '两次输入的密码不一致' })
      return
    }
    if (newPassword.length < 6) {
      addToast({ type: 'warning', message: '新密码长度不能少于6位' })
      return
    }
    try {
      setChangingPassword(true)
      const result = await changePassword({ current_password: currentPassword, new_password: newPassword })
      if (result.success) {
        addToast({ type: 'success', message: '密码修改成功，即将退出登录' })
        setCurrentPassword('')
        setNewPassword('')
        setConfirmPassword('')
        // 延迟1秒后退出登录
        setTimeout(() => {
          clearAuth()
          window.location.href = '/login'
        }, 1000)
      } else {
        addToast({ type: 'error', message: result.message || '密码修改失败' })
      }
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string; message?: string } }; message?: string }
      const errorMsg = err?.response?.data?.detail || err?.response?.data?.message || err?.message || '密码修改失败'
      addToast({ type: 'error', message: errorMsg })
    } finally {
      setChangingPassword(false)
    }
  }

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
            <p className="text-xs text-blue-600 dark:text-blue-400 mb-2">如需获取对接卡密秘钥，请联系 QQ：531779707 微信：zhinian_znbk</p>
            <div className="flex items-center gap-3 flex-wrap">
              <div className="relative flex-1 min-w-[260px]">
                <input
                  type="text"
                  value={cardSecretKey}
                  onChange={(e) => setCardSecretKey(e.target.value)}
                  placeholder="请输入对接卡密秘钥"
                  className="input-ios pr-10"
                  style={{ WebkitTextSecurity: showCardSecretKey ? 'none' : 'disc' } as React.CSSProperties}
                />
                <button
                  type="button"
                  onClick={() => setShowCardSecretKey(!showCardSecretKey)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                  title={showCardSecretKey ? '隐藏' : '显示'}
                >
                  {showCardSecretKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
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
              <input
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                placeholder="请输入当前密码"
                className="input-ios"
              />
            </div>
            <div />
            <div className="input-group">
              <label className="input-label">新密码</label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                placeholder="请输入新密码（至少6位）"
                className="input-ios"
              />
            </div>
            <div className="input-group">
              <label className="input-label">确认新密码</label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="请再次输入新密码"
                className="input-ios"
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

      {/* 重置对接码确认弹窗 */}
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

      {/* 结算记录弹窗 */}
      {showSettlementModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="flex h-[80vh] w-full max-w-5xl flex-col rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">结算记录</h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">按实际创建时间倒序显示，最新申请排在最前面</p>
              </div>
              <div className="flex items-center gap-2">
                <button onClick={() => loadSettlementRecords(settlementPage, settlementPageSize)} className="btn-ios-secondary text-sm" disabled={settlementLoading}>
                  <RefreshCw className={`w-4 h-4 ${settlementLoading ? 'animate-spin' : ''}`} />
                  刷新
                </button>
                <button
                  onClick={() => setShowSettlementModal(false)}
                  className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-hidden rounded-xl border border-slate-200 dark:border-slate-700">
              <div className="h-full overflow-auto">
                <table className="table-ios">
                  <thead>
                    <tr>
                      <th>记录ID</th>
                      <th>提现金额</th>
                      <th>收款方式</th>
                      <th>状态</th>
                      <th>拒绝原因</th>
                      <th>创建时间</th>
                    </tr>
                  </thead>
                  <tbody>
                    {settlementLoading ? (
                      <tr>
                        <td colSpan={6}>
                          <div className="py-10 text-center text-sm text-slate-500">加载中...</div>
                        </td>
                      </tr>
                    ) : settlementRecords.length === 0 ? (
                      <tr>
                        <td colSpan={6}>
                          <div className="py-10 text-center text-sm text-slate-500">暂无结算记录</div>
                        </td>
                      </tr>
                    ) : (
                      settlementRecords.map((record) => (
                        <tr key={record.id}>
                          <td>{record.id}</td>
                          <td>¥{record.amount}</td>
                          <td>{record.payment_type === 'wechat' ? '微信' : record.payment_type === 'alipay' ? '支付宝' : (record.alipay_id ? '支付宝' : '-')}</td>
                          <td>
                            <span className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${
                              record.status === 'pending_review' ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400' :
                              record.status === 'approved' ? 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400' :
                              record.status === 'paid' ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400' :
                              'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400'
                            }`}>
                              {record.status === 'pending_review' ? '待审核' : record.status === 'approved' ? '已通过' : record.status === 'paid' ? '已打款' : '已拒绝'}
                            </span>
                          </td>
                          <td className="max-w-[200px] truncate text-red-600 dark:text-red-400" title={record.reject_reason || ''}>
                            {record.reject_reason || '-'}
                          </td>
                          <td className="whitespace-nowrap">{record.created_at ? new Date(record.created_at).toLocaleString('zh-CN') : '-'}</td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <div className="mt-4 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200 pt-4 dark:border-slate-700">
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <span>每页</span>
                <select
                  value={settlementPageSize}
                  onChange={async (e) => {
                    const nextSize = Number(e.target.value)
                    setSettlementPageSize(nextSize)
                    await loadSettlementRecords(1, nextSize)
                  }}
                  className="input-ios w-auto py-1 px-2 text-sm"
                >
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                  <option value={100}>100</option>
                </select>
                <span>条，共 {settlementTotal} 条</span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => loadSettlementRecords(settlementPage - 1, settlementPageSize)}
                  disabled={settlementPage <= 1 || settlementLoading}
                  className="btn-ios-secondary btn-sm"
                >
                  上一页
                </button>
                <span className="px-3 text-sm text-gray-600 dark:text-gray-400">
                  {settlementPage} / {settlementTotalPages || 1}
                </span>
                <button
                  onClick={() => loadSettlementRecords(settlementPage + 1, settlementPageSize)}
                  disabled={settlementPage >= settlementTotalPages || settlementLoading || settlementTotalPages === 0}
                  className="btn-ios-secondary btn-sm"
                >
                  下一页
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 提现弹窗 */}
      {showWithdrawModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">申请提现</h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">提现后将立即扣减余额，并生成待审核结算记录</p>
              </div>
              <button
                onClick={() => {
                  if (withdrawing) return
                  setShowWithdrawModal(false)
                }}
                className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                <div>当前余额：¥{balance || '0.00'}</div>
                <div className="mt-1">
                  收款方式：{paymentQrcode ? (paymentType === 'wechat' ? '微信' : '支付宝') + '收款码' : '未上传收款码'}
                </div>
                {withdrawMinAmount && Number(withdrawMinAmount) > 0 && (
                  <div className="mt-1 text-amber-600 dark:text-amber-400">
                    最低提现金额：¥{withdrawMinAmount}
                  </div>
                )}
              </div>
              <div>
                <label className="input-label">提现金额（元）</label>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={withdrawAmount}
                  onChange={(e) => setWithdrawAmount(e.target.value)}
                  placeholder="请输入提现金额"
                  className="input-ios"
                  autoFocus
                />
              </div>
              <p className="text-xs text-slate-500 dark:text-slate-400">
                提现提交后会同步扣减余额、写入资金流水，并生成状态为“待审核”的结算记录。
              </p>
              <div className="flex justify-end gap-3">
                <button
                  onClick={() => setShowWithdrawModal(false)}
                  className="btn-ios-secondary"
                  disabled={withdrawing}
                >
                  取消
                </button>
                <button
                  onClick={handleWithdraw}
                  className="btn-ios-primary"
                  disabled={withdrawing}
                >
                  {withdrawing ? <ButtonLoading /> : <ArrowUpFromLine className="w-4 h-4" />}
                  确认提现
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* 收款码管理弹窗 */}
      {showQrcodeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-lg rounded-2xl bg-white p-6 shadow-2xl dark:bg-slate-900">
            <div className="mb-4 flex items-center justify-between">
              <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">收款码管理</h3>
              <button
                onClick={() => setShowQrcodeModal(false)}
                className="rounded-lg p-2 text-slate-500 transition hover:bg-slate-100 hover:text-slate-700 dark:hover:bg-slate-800 dark:hover:text-slate-200"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="space-y-4">
              {/* 收款类型选择 */}
              <div>
                <label className="input-label">收款方式</label>
                <div className="flex gap-3">
                  <button
                    onClick={() => setPaymentType('alipay')}
                    className={`flex-1 rounded-xl border-2 py-3 text-sm font-medium transition ${
                      paymentType === 'alipay'
                        ? 'border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400'
                        : 'border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-400'
                    }`}
                  >
                    支付宝
                  </button>
                  <button
                    onClick={() => setPaymentType('wechat')}
                    className={`flex-1 rounded-xl border-2 py-3 text-sm font-medium transition ${
                      paymentType === 'wechat'
                        ? 'border-green-500 bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400'
                        : 'border-slate-200 text-slate-600 dark:border-slate-700 dark:text-slate-400'
                    }`}
                  >
                    微信
                  </button>
                </div>
              </div>
              {/* 当前收款码预览 */}
              {paymentQrcode && (
                <div className="text-center">
                  <label className="input-label">当前收款码</label>
                  <img
                    src={paymentQrcode}
                    alt="当前收款码"
                    className="mx-auto mt-2 h-40 w-40 rounded-xl border border-slate-200 object-contain dark:border-slate-700"
                  />
                </div>
              )}
              {/* 上传区域 */}
              <div>
                <label className="input-label">{paymentQrcode ? '更换收款码' : '上传收款码'}</label>
                <div
                  onClick={() => qrcodeFileRef.current?.click()}
                  className="flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed border-slate-300 py-8 transition hover:border-blue-400 hover:bg-slate-50 dark:border-slate-600 dark:hover:bg-slate-800"
                >
                  {uploadingQrcode ? (
                    <ButtonLoading />
                  ) : (
                    <>
                      <Upload className="mb-2 h-8 w-8 text-slate-400" />
                      <span className="text-sm text-slate-500">点击选择图片（JPG/PNG/WEBP）</span>
                    </>
                  )}
                </div>
                <input
                  ref={qrcodeFileRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  onChange={handleUploadQrcode}
                />
              </div>
              <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                请上传{paymentType === 'wechat' ? '微信' : '支付宝'}收款码图片，管理员打款时将看到此收款码。已上传的收款码可重新上传替换。
              </div>
              <div className="flex justify-end">
                <button onClick={() => setShowQrcodeModal(false)} className="btn-ios-secondary">
                  关闭
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

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
    </div>
  )
}
