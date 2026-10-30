/** 个人设置原有账户、分销及偏好数据，保持既有读取和保存流程。 */
import { useState, useEffect } from 'react'
import { getUserSetting, updateUserSetting, createCardSecretKey, changePassword, getDockCode, resetDockCode, getSecretKey, resetSecretKey, getSystemSettings, getCurrentUserProfile } from '@/api/settings'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'

// 余额设置的 key
const BALANCE_KEY = 'balance'
// 续期单价的系统设置 key（普通用户可读，用于计算续期总价）
const RENEW_MONTH_PRICE_KEY = 'user.renew_month_price'

const CONTACT_WECHAT_KEY = 'contact_wechat'
const CONTACT_QQ_KEY = 'contact_qq'
const REDELIVERY_TRIGGER_KEYWORD_KEY = 'redelivery_trigger_keyword'
const PAYMENT_QRCODE_KEY = 'payment_qrcode'
const PAYMENT_TYPE_KEY = 'payment_type'
// 对接卡密秘钥的 key（按用户存储，用于「分销卡券」页面对接上游卡券系统）
const CARD_SECRET_KEY = 'distribution.card_secret_key'

export function usePersonalSettingsData() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated, user, clearAuth } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [balance, setBalance] = useState('')
  const [showRecharge, setShowRecharge] = useState(false)
  const [expireAt, setExpireAt] = useState<string | null>(null)
  const [renewPrice, setRenewPrice] = useState('')
  const [showRenew, setShowRenew] = useState(false)
  const [showFundFlowModal, setShowFundFlowModal] = useState(false)
  const [paymentQrcode, setPaymentQrcode] = useState('')
  const [paymentType, setPaymentType] = useState<'alipay' | 'wechat'>('alipay')

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
  const [creatingCardSecretKey, setCreatingCardSecretKey] = useState(false)

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
      // 加载当前用户到期日
      try {
        const profile = await getCurrentUserProfile()
        setExpireAt(profile.expire_at ?? null)
      } catch {
        // 到期日加载失败不阻断其他设置展示
      }
      // 加载续期单价（普通用户可读）
      try {
        const sysResult = await getSystemSettings()
        if (sysResult.success && sysResult.data) {
          setRenewPrice(String(sysResult.data[RENEW_MONTH_PRICE_KEY] ?? ''))
        }
      } catch {
        // 续期单价加载失败不阻断其他设置展示
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

  // 一键创建对接卡密秘钥：调用外部密钥服务创建并自动保存到当前用户
  const handleCreateCardSecretKey = async () => {
    // 已存在则禁止创建，提示联系管理员重置
    if (cardSecretKey.trim()) {
      addToast({ type: 'warning', message: '对接卡密秘钥已存在，如需重新创建请联系管理员重置' })
      return
    }
    try {
      setCreatingCardSecretKey(true)
      const result = await createCardSecretKey()
      if (result.success && result.data?.key_value) {
        setCardSecretKey(result.data.key_value)
        addToast({ type: 'success', message: result.message || '对接卡密秘钥创建成功' })
      } else {
        addToast({ type: 'error', message: result.message || '创建失败' })
      }
    } finally {
      setCreatingCardSecretKey(false)
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

  return {
    loading,
    loadSettings,
    user,
    balance,
    setBalance,
    expireAt,
    renewPrice,
    showRenew,
    setShowRenew,
    showFundFlowModal,
    setShowFundFlowModal,
    showRecharge,
    setShowRecharge,
    setExpireAt,
    paymentQrcode,
    setPaymentQrcode,
    paymentType,
    setPaymentType,
    dockCode,
    dockCodeLoading,
    resettingDockCode,
    resetConfirmOpen,
    setResetConfirmOpen,
    secretKey,
    secretKeyLoading,
    resettingSecretKey,
    secretKeyResetConfirmOpen,
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
    handleResetDockCode,
    handleCopyDockCode,
    handleResetSecretKey,
    handleCopySecretKey,
    handleSaveCardSecretKey,
    handleCreateCardSecretKey,
    handleSaveRedeliveryKeyword,
    handleSaveContact,
    handleChangePassword
  }
}
