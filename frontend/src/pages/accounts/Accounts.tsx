import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { Button, Card, Checkbox, Empty, Input, InputNumber, Modal, Space, Spin, Table, Tag } from '@arco-design/web-react'
import type { TableColumnProps } from '@arco-design/web-react'
import { Plus, RefreshCw, QrCode, Key, Edit2, Trash2, Power, PowerOff, X, Loader2, Clock, CheckCircle, Eye, EyeOff, AlertTriangle, ChevronDown } from 'lucide-react'
import { getAccountDetails, deleteAccount, updateAccountCookie, updateAccountStatus, updateAccountRemark, addAccount, generateQRLogin, cancelQRLogin, checkQRLoginStatus, checkQRLoginStatusNow, getQRVerificationScreenshot, openQRVerificationBrowser, passwordLogin, checkPasswordLoginStatus, cancelPasswordLogin, updateAccountAutoConfirm, updateAccountPauseDuration, getAllAIReplySettings, getAIReplySettings, updateAIReplySettings, updateAccountLoginInfo, checkAccountStatus, type AIReplySettings } from '@/api/accounts'
import { getKeywords, getDefaultReply, updateDefaultReply } from '@/api/keywords'
import { checkDefaultPassword } from '@/api/settings'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { ActionMenu } from '@/components/common/ActionMenu'
import type { AccountDetail } from '@/types'

type ModalType = 'qrcode' | 'password' | 'manual' | 'edit' | 'default-reply' | 'ai-settings' | null

interface AccountWithKeywordCount extends AccountDetail {
  keywordCount?: number
  aiEnabled?: boolean
}

interface AccountTableRow extends AccountWithKeywordCount {
  key: string
}

const TAG_STYLE = { borderRadius: 4 }
const { TextArea } = Input

export function Accounts() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated, user } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [accounts, setAccounts] = useState<AccountWithKeywordCount[]>([])
  const [activeModal, setActiveModal] = useState<ModalType>(null)
  const [statusChecking, setStatusChecking] = useState<Record<string, boolean>>({})

  // 默认密码检查状态
  const [usingDefaultPassword, setUsingDefaultPassword] = useState(false)
  const [showPasswordWarning, setShowPasswordWarning] = useState(false)

  // 默认回复管理状态
  const [defaultReplyAccount, setDefaultReplyAccount] = useState<AccountWithKeywordCount | null>(null)
  const [defaultReplyContent, setDefaultReplyContent] = useState('')
  const [defaultReplyImageUrl, setDefaultReplyImageUrl] = useState('')
  const [defaultReplyOnce, setDefaultReplyOnce] = useState(false)
  const [defaultReplySaving, setDefaultReplySaving] = useState(false)
  const [uploadingDefaultReplyImage, setUploadingDefaultReplyImage] = useState(false)

  // 扫码登录状态
  const [qrCodeUrl, setQrCodeUrl] = useState('')
  const [qrVerificationUrl, setQrVerificationUrl] = useState('')
  const [qrVerificationScreenshotUrl, setQrVerificationScreenshotUrl] = useState('')
  const [qrVerificationScreenshotLoading, setQrVerificationScreenshotLoading] = useState(false)
  const [qrManualChecking, setQrManualChecking] = useState(false)
  const [qrSessionId, setQrSessionId] = useState('')
  const [qrStatus, setQrStatus] = useState<'loading' | 'ready' | 'scanned' | 'success' | 'expired' | 'error'>('loading')
  const qrCheckIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const qrVerificationWindowRef = useRef<Window | null>(null)
  const qrVerificationWatcherRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const qrLastAutoCheckAtRef = useRef(0)
  const qrSessionRef = useRef('')
  const qrStatusRef = useRef(qrStatus)

  // 密码登录状态
  const [pwdAccount, setPwdAccount] = useState('')
  const [pwdPassword, setPwdPassword] = useState('')
  const [pwdLoading, setPwdLoading] = useState(false)
  const [pwdShowBrowser, setPwdShowBrowser] = useState(false)
  const [pwdSessionId, setPwdSessionId] = useState('')
  const [pwdStatus, setPwdStatus] = useState<'idle' | 'processing' | 'verification_required' | 'success' | 'failed'>('idle')
  const [pwdStatusMessage, setPwdStatusMessage] = useState('')
  const [pwdVerificationUrl, setPwdVerificationUrl] = useState('')
  const [pwdScreenshotPath, setPwdScreenshotPath] = useState('')
  const pwdCheckIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const pwdSessionRef = useRef('')
  const pwdStatusRef = useRef(pwdStatus)

  // 手动输入状态
  const [manualAccountId, setManualAccountId] = useState('')
  const [manualCookie, setManualCookie] = useState('')
  const [manualLoading, setManualLoading] = useState(false)

  // 编辑账号状态
  const [editingAccount, setEditingAccount] = useState<AccountDetail | null>(null)
  const [editNote, setEditNote] = useState('')
  const [editCookie, setEditCookie] = useState('')
  const [editAutoConfirm, setEditAutoConfirm] = useState(false)
  const [editPauseDuration, setEditPauseDuration] = useState(0)
  const [editSaving, setEditSaving] = useState(false)
  // 登录信息
  const [editUsername, setEditUsername] = useState('')
  const [editLoginPassword, setEditLoginPassword] = useState('')
  const [editShowBrowser, setEditShowBrowser] = useState(false)
  const [showLoginPassword, setShowLoginPassword] = useState(false)

  // AI设置状态
  const [aiSettingsAccount, setAiSettingsAccount] = useState<AccountWithKeywordCount | null>(null)
  const [aiEnabled, setAiEnabled] = useState(false)
  const [aiMaxDiscountPercent, setAiMaxDiscountPercent] = useState(10)
  const [aiMaxDiscountAmount, setAiMaxDiscountAmount] = useState(100)
  const [aiMaxBargainRounds, setAiMaxBargainRounds] = useState(3)
  const [aiCustomPrompts, setAiCustomPrompts] = useState('')
  const [aiSettingsSaving, setAiSettingsSaving] = useState(false)
  const [aiSettingsLoading, setAiSettingsLoading] = useState(false)

  const loadAccounts = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const data = await getAccountDetails()

      // 获取所有账号的AI回复设置
      let aiSettings: Record<string, AIReplySettings> = {}
      try {
        aiSettings = await getAllAIReplySettings()
      } catch {
        // ignore
      }

      // 为每个账号获取关键词数量
      const accountsWithKeywords = await Promise.all(
        data.map(async (account) => {
          try {
            const keywords = await getKeywords(account.id)
            return {
              ...account,
              keywordCount: keywords.length,
              aiEnabled: aiSettings[account.id]?.ai_enabled ?? aiSettings[account.id]?.enabled ?? false,
            }
          } catch {
            return {
              ...account,
              keywordCount: 0,
              aiEnabled: aiSettings[account.id]?.ai_enabled ?? aiSettings[account.id]?.enabled ?? false,
            }
          }
        }),
      )

      setAccounts(accountsWithKeywords)
    } catch {
      addToast({ type: 'error', message: '加载账号列表失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    qrSessionRef.current = qrSessionId
  }, [qrSessionId])

  useEffect(() => {
    qrStatusRef.current = qrStatus
  }, [qrStatus])

  useEffect(() => {
    pwdSessionRef.current = pwdSessionId
  }, [pwdSessionId])

  useEffect(() => {
    pwdStatusRef.current = pwdStatus
  }, [pwdStatus])

  useEffect(() => {
    return () => {
      if (qrCheckIntervalRef.current) {
        clearInterval(qrCheckIntervalRef.current)
        qrCheckIntervalRef.current = null
      }
      if (qrVerificationWatcherRef.current) {
        clearInterval(qrVerificationWatcherRef.current)
        qrVerificationWatcherRef.current = null
      }
      if (pwdCheckIntervalRef.current) {
        clearInterval(pwdCheckIntervalRef.current)
        pwdCheckIntervalRef.current = null
      }
      qrVerificationWindowRef.current = null
      if (qrSessionRef.current && qrStatusRef.current !== 'success') {
        cancelQRLogin(qrSessionRef.current).catch(() => undefined)
      }
      if (pwdSessionRef.current && !['success', 'failed', 'idle'].includes(pwdStatusRef.current)) {
        cancelPasswordLogin(pwdSessionRef.current).catch(() => undefined)
      }
    }
  }, [])

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadAccounts()
  }, [_hasHydrated, isAuthenticated, token])

  // 单独的 useEffect 检查默认密码
  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token || !user) return

    // 检查是否使用默认密码
    const checkPassword = async () => {
      if (user.is_admin) {
        const result = await checkDefaultPassword()
        setUsingDefaultPassword(result.using_default)
      }
    }
    checkPassword()
  }, [_hasHydrated, isAuthenticated, token, user])

  // 清理扫码检查定时器
  const clearQrCheck = useCallback(() => {
    if (qrCheckIntervalRef.current) {
      clearInterval(qrCheckIntervalRef.current)
      qrCheckIntervalRef.current = null
    }
  }, [])

  const clearQrVerificationWatcher = useCallback(() => {
    if (qrVerificationWatcherRef.current) {
      clearInterval(qrVerificationWatcherRef.current)
      qrVerificationWatcherRef.current = null
    }
    qrVerificationWindowRef.current = null
  }, [])

  const clearPasswordCheck = useCallback(() => {
    if (pwdCheckIntervalRef.current) {
      clearInterval(pwdCheckIntervalRef.current)
      pwdCheckIntervalRef.current = null
    }
  }, [])

  // 关闭弹窗时清理
  const closeModal = useCallback((options?: { cancelQrSession?: boolean }) => {
    const shouldCancelQrSession = options?.cancelQrSession !== false
    const sessionIdToCancel = activeModal === 'qrcode' && qrSessionId && qrStatus !== 'success'
      ? qrSessionId
      : ''
    const passwordSessionIdToCancel = activeModal === 'password' && pwdSessionId && !['success', 'failed', 'idle'].includes(pwdStatus)
      ? pwdSessionId
      : ''
    clearQrCheck()
    clearQrVerificationWatcher()
    clearPasswordCheck()
    if (shouldCancelQrSession && sessionIdToCancel) {
      cancelQRLogin(sessionIdToCancel).catch(() => undefined)
    }
    if (passwordSessionIdToCancel) {
      cancelPasswordLogin(passwordSessionIdToCancel).catch(() => undefined)
    }
    setActiveModal(null)
    setQrCodeUrl('')
    setQrVerificationUrl('')
    setQrVerificationScreenshotUrl('')
    setQrVerificationScreenshotLoading(false)
    setQrManualChecking(false)
    setQrSessionId('')
    setQrStatus('loading')
    setPwdAccount('')
    setPwdPassword('')
    setPwdLoading(false)
    setPwdSessionId('')
    setPwdStatus('idle')
    setPwdStatusMessage('')
    setPwdVerificationUrl('')
    setPwdScreenshotPath('')
    setManualAccountId('')
    setManualCookie('')
    setManualLoading(false)
  }, [activeModal, clearPasswordCheck, clearQrCheck, clearQrVerificationWatcher, pwdSessionId, pwdStatus, qrSessionId, qrStatus])

  // ==================== 扫码登录 ====================
  const startQRCodeLogin = async () => {
    // 检查是否使用默认密码
    if (usingDefaultPassword) {
      setShowPasswordWarning(true)
      return
    }

    setActiveModal('qrcode')
    setQrStatus('loading')
    try {
      const result = await generateQRLogin()
        if (result.success && result.qr_code_url && result.session_id) {
          setQrCodeUrl(result.qr_code_url)
          setQrVerificationUrl('')
          setQrManualChecking(false)
          setQrSessionId(result.session_id)
          setQrStatus('ready')
        // 开始轮询
        startQrCheck(result.session_id)
      } else {
        setQrStatus('error')
        addToast({ type: 'error', message: result.message || '生成二维码失败' })
      }
    } catch {
      setQrStatus('error')
      addToast({ type: 'error', message: '生成二维码失败' })
    }
  }

  // 检查默认密码后打开弹窗
  const handleOpenModal = (modal: ModalType) => {
    if (usingDefaultPassword && (modal === 'password' || modal === 'manual')) {
      setShowPasswordWarning(true)
      return
    }
    setActiveModal(modal)
  }

  const handleAddAccountMethod = (method: 'qrcode' | 'password' | 'manual') => {
    if (method === 'qrcode') {
      startQRCodeLogin()
      return
    }
    handleOpenModal(method)
  }

  const startQrCheck = (sessionId: string) => {
    clearQrCheck()
    qrCheckIntervalRef.current = setInterval(async () => {
      try {
        const result = await checkQRLoginStatus(sessionId)
        if (!result.success) return
        handleQrStatusResult(result)
      } catch {
        // 忽略网络错误，继续轮询
      }
    }, 2000)
  }

  const loadQrVerificationScreenshot = useCallback(async (sessionId: string) => {
    if (!sessionId) return

    setQrVerificationScreenshotLoading(true)
    try {
      const result = await getQRVerificationScreenshot(sessionId)
      if (result.success && result.screenshot?.path) {
        setQrVerificationScreenshotUrl(`${result.screenshot.path}?t=${Date.now()}`)
      }
    } catch {
      // ignore
    } finally {
      setQrVerificationScreenshotLoading(false)
    }
  }, [])

  const handleQrStatusResult = (result: Awaited<ReturnType<typeof checkQRLoginStatus>>) => {
    switch (result.status) {
      case 'scanned':
      case 'processing':
        setQrStatus('scanned')
        break
      case 'success':
      case 'already_processed':
        setQrStatus('success')
        clearQrCheck()
        addToast({
          type: 'success',
          message: result.account_info?.is_new_account
            ? `新账号 ${result.account_info.account_id} 添加成功`
            : result.account_info?.account_id
              ? `账号 ${result.account_info.account_id} 登录成功`
              : '账号登录成功',
        })
        setTimeout(() => {
          closeModal({ cancelQrSession: false })
          loadAccounts()
        }, 1500)
        break
      case 'expired':
        setQrStatus(qrVerificationUrl ? 'scanned' : 'expired')
        if (!qrVerificationUrl) {
          clearQrCheck()
        }
        break
      case 'cancelled':
        clearQrCheck()
        addToast({ type: 'warning', message: '用户取消登录' })
        closeModal()
        break
      case 'verification_required':
        setQrStatus('scanned')
        setQrVerificationUrl(result.verification_url || '')
        if (qrSessionRef.current) {
          void loadQrVerificationScreenshot(qrSessionRef.current)
        }
        break
    }
  }

  const handlePasswordStatusResult = useCallback((result: Awaited<ReturnType<typeof checkPasswordLoginStatus>>) => {
    switch (result.status) {
      case 'processing':
      case 'pending':
        setPwdStatus('processing')
        setPwdStatusMessage(result.message || '登录处理中，请稍候...')
        break
      case 'verification_required':
        setPwdStatus('verification_required')
        setPwdStatusMessage(result.message || '需要人工辅助验证，请按页面提示完成验证')
        setPwdVerificationUrl(result.verification_url || '')
        setPwdScreenshotPath(result.screenshot_path || result.qr_code_url || '')
        break
      case 'success':
        setPwdStatus('success')
        setPwdStatusMessage(result.message || '登录成功')
        setPwdLoading(false)
        clearPasswordCheck()
        addToast({ type: 'success', message: result.message || '账号登录成功' })
        setTimeout(() => {
          closeModal()
          loadAccounts()
        }, 1200)
        break
      case 'failed':
      case 'not_found':
      case 'forbidden':
      case 'error':
        setPwdStatus('failed')
        setPwdStatusMessage(result.error || result.message || '登录失败')
        setPwdLoading(false)
        clearPasswordCheck()
        break
    }
  }, [addToast, clearPasswordCheck, closeModal])

  const pollPasswordLoginStatus = useCallback(async (sessionId: string) => {
    try {
      const result = await checkPasswordLoginStatus(sessionId)
      handlePasswordStatusResult(result)
    } catch {
      setPwdStatus('failed')
      setPwdStatusMessage('检查登录状态失败')
      setPwdLoading(false)
      clearPasswordCheck()
    }
  }, [clearPasswordCheck, handlePasswordStatusResult])

  const startPasswordStatusPolling = useCallback((sessionId: string) => {
    clearPasswordCheck()
    void pollPasswordLoginStatus(sessionId)
    pwdCheckIntervalRef.current = setInterval(() => {
      void pollPasswordLoginStatus(sessionId)
    }, 2500)
  }, [clearPasswordCheck, pollPasswordLoginStatus])

  const manualCheckQRLogin = async () => {
    if (!qrSessionId) return
    setQrManualChecking(true)
    try {
      const result = await checkQRLoginStatusNow(qrSessionId)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '检查登录状态失败' })
        return
      }
      handleQrStatusResult(result)
      if (result.status === 'verification_required' || result.status === 'scanned' || result.status === 'processing') {
        addToast({ type: 'info', message: '暂未检测到登录成功，请确认手机验证是否已完成' })
      }
    } catch {
      addToast({ type: 'error', message: '检查登录状态失败' })
    } finally {
      setQrManualChecking(false)
    }
  }

  const triggerAutoQrStatusCheck = useCallback(async () => {
    const now = Date.now()
    if (
      !qrSessionRef.current ||
      qrStatusRef.current === 'success' ||
      qrManualChecking ||
      now - qrLastAutoCheckAtRef.current < 1500
    ) {
      return
    }

    qrLastAutoCheckAtRef.current = now
    setQrManualChecking(true)
    try {
      const result = await checkQRLoginStatusNow(qrSessionRef.current)
      if (result.success) {
        handleQrStatusResult(result)
      }
    } catch {
      // 忽略自动检查失败，保留手动重试入口
    } finally {
      setQrManualChecking(false)
    }
  }, [qrManualChecking])

  const openQrVerificationPage = useCallback(() => {
    if (!qrSessionRef.current) return

    openQRVerificationBrowser(qrSessionRef.current)
      .then((result) => {
        if (result.success) {
          addToast({ type: 'info', message: result.message || '验证浏览器已打开，请根据截图预览完成验证' })
          void loadQrVerificationScreenshot(qrSessionRef.current)
          clearQrVerificationWatcher()
          triggerAutoQrStatusCheck()
        } else {
          addToast({ type: 'error', message: result.message || '打开验证浏览器失败' })
        }
      })
      .catch(() => {
        addToast({ type: 'error', message: '打开验证浏览器失败' })
      })
  }, [addToast, clearQrVerificationWatcher, loadQrVerificationScreenshot, triggerAutoQrStatusCheck])

  useEffect(() => {
    if (activeModal !== 'qrcode' || !qrVerificationUrl) return

    const handleWindowFocus = () => {
      triggerAutoQrStatusCheck()
    }

    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        triggerAutoQrStatusCheck()
      }
    }

    window.addEventListener('focus', handleWindowFocus)
    document.addEventListener('visibilitychange', handleVisibilityChange)
    return () => {
      window.removeEventListener('focus', handleWindowFocus)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [activeModal, qrVerificationUrl, triggerAutoQrStatusCheck])

  useEffect(() => {
    if (activeModal !== 'qrcode' || !qrVerificationUrl || !qrSessionId) return

    void loadQrVerificationScreenshot(qrSessionId)
    const intervalId = window.setInterval(() => {
      void loadQrVerificationScreenshot(qrSessionId)
    }, 3000)

    return () => window.clearInterval(intervalId)
  }, [activeModal, qrSessionId, qrVerificationUrl, loadQrVerificationScreenshot])

  const refreshQRCode = async () => {
    const previousSessionId = qrSessionId
    setQrStatus('loading')
    clearQrCheck()
    if (previousSessionId) {
      cancelQRLogin(previousSessionId).catch(() => undefined)
    }
    try {
      const result = await generateQRLogin()
      if (result.success && result.qr_code_url && result.session_id) {
        setQrCodeUrl(result.qr_code_url)
        setQrVerificationUrl('')
        setQrVerificationScreenshotUrl('')
        setQrManualChecking(false)
        setQrSessionId(result.session_id)
        setQrStatus('ready')
        startQrCheck(result.session_id)
      } else {
        setQrStatus('error')
      }
    } catch {
      setQrStatus('error')
    }
  }

  // ==================== 密码登录 ====================
  const handlePasswordLogin = async (e: FormEvent) => {
    e.preventDefault()
    if (!pwdAccount.trim() || !pwdPassword.trim()) {
      addToast({ type: 'warning', message: '请输入账号和密码' })
      return
    }

    setPwdLoading(true)
    try {
      const result = await passwordLogin({
        account_id: pwdAccount.trim(),
        account: pwdAccount.trim(),
        password: pwdPassword,
        show_browser: pwdShowBrowser,
      })
      if (result.success && result.session_id) {
        setPwdSessionId(result.session_id)
        setPwdStatus('processing')
        setPwdStatusMessage(result.message || '登录任务已启动，请等待页面响应...')
        setPwdVerificationUrl('')
        setPwdScreenshotPath('')
        addToast({ type: 'success', message: '登录请求已提交，请等待页面响应' })
        startPasswordStatusPolling(result.session_id)
      } else {
        setPwdStatus('failed')
        setPwdStatusMessage(result.message || '登录失败')
        setPwdLoading(false)
        addToast({ type: 'error', message: result.message || '登录失败' })
      }
    } catch {
      setPwdStatus('failed')
      setPwdStatusMessage('登录请求失败')
      setPwdLoading(false)
      addToast({ type: 'error', message: '登录请求失败' })
    }
  }

  // ==================== 手动输入 ====================
  const handleManualAdd = async (e: FormEvent) => {
    e.preventDefault()
    if (!manualAccountId.trim()) {
      addToast({ type: 'warning', message: '请输入账号ID' })
      return
    }
    if (!manualCookie.trim()) {
      addToast({ type: 'warning', message: '请输入Cookie' })
      return
    }

    setManualLoading(true)
    try {
      const result = await addAccount({
        id: manualAccountId.trim(),
        cookie: manualCookie.trim(),
      })
      // 后端返回 {msg: 'success'} 或 {success: true}
      if (result.success || result.msg === 'success') {
        addToast({ type: 'success', message: '账号添加成功' })
        closeModal()
        loadAccounts()
      } else {
        addToast({ type: 'error', message: result.message || result.detail || '添加失败' })
      }
    } catch {
      addToast({ type: 'error', message: '添加账号失败' })
    } finally {
      setManualLoading(false)
    }
  }

  const handleToggleEnabled = async (account: AccountDetail) => {
    try {
      await updateAccountStatus(account.id, !account.enabled)
      addToast({ type: 'success', message: account.enabled ? '账号已禁用' : '账号已启用' })
      loadAccounts()
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  const handleDelete = async (id: string) => {
    Modal.confirm({
      title: '删除账号',
      content: '确定要删除这个账号吗？',
      okButtonProps: { status: 'danger' },
      onOk: async () => {
        try {
          await deleteAccount(id)
          addToast({ type: 'success', message: '删除成功' })
          loadAccounts()
        } catch (error) {
          const message = error instanceof Error ? error.message : '删除失败'
          addToast({ type: 'error', message })
        }
      },
    })
  }

  // ==================== 编辑账号 ====================
  const openEditModal = (account: AccountDetail) => {
    setEditingAccount(account)
    setEditNote(account.note || '')
    setEditCookie(account.cookie || '')
    setEditAutoConfirm(account.auto_confirm || false)
    setEditPauseDuration(account.pause_duration || 0)
    setEditUsername(account.username || '')
    setEditLoginPassword(account.login_password || '')
    setEditShowBrowser(account.show_browser || false)
    setShowLoginPassword(false)
    setActiveModal('edit')
  }

  const handleEditSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!editingAccount) return

    setEditSaving(true)
    try {
      // 分别调用不同的 API 更新不同字段
      const promises: Promise<unknown>[] = []

      // 更新备注
      if (editNote.trim() !== (editingAccount.note || '')) {
        promises.push(updateAccountRemark(editingAccount.id, editNote.trim()))
      }

      // 更新 Cookie 值
      if (editCookie.trim() && editCookie.trim() !== editingAccount.cookie) {
        promises.push(updateAccountCookie(editingAccount.id, editCookie.trim()))
      }

      // 更新自动确认发货
      if (editAutoConfirm !== (editingAccount.auto_confirm || false)) {
        promises.push(updateAccountAutoConfirm(editingAccount.id, editAutoConfirm))
      }

      // 更新暂停时间
      if (editPauseDuration !== (editingAccount.pause_duration || 0)) {
        promises.push(updateAccountPauseDuration(editingAccount.id, editPauseDuration))
      }

      // 更新登录信息
      const loginInfoChanged =
        editUsername !== (editingAccount.username || '') ||
        editLoginPassword !== (editingAccount.login_password || '') ||
        editShowBrowser !== (editingAccount.show_browser || false)

      if (loginInfoChanged) {
        const loginInfoPayload: {
          username?: string
          login_password?: string
          show_browser?: boolean
        } = {
          username: editUsername,
          show_browser: editShowBrowser,
        }

        if (editLoginPassword || !editingAccount.login_password) {
          loginInfoPayload.login_password = editLoginPassword
        }

        promises.push(updateAccountLoginInfo(editingAccount.id, loginInfoPayload))
      }

      await Promise.all(promises)
      addToast({ type: 'success', message: '账号信息已更新' })
      closeModal()
      loadAccounts()
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setEditSaving(false)
    }
  }

  // ==================== 默认回复管理 ====================
  const openDefaultReplyModal = async (account: AccountWithKeywordCount) => {
    setDefaultReplyAccount(account)
    setDefaultReplyContent('')
    setDefaultReplyImageUrl('')
    setDefaultReplyOnce(false)
    setActiveModal('default-reply')

    // 加载当前默认回复
    try {
      const result = await getDefaultReply(account.id)
      setDefaultReplyContent(result.reply_content || '')
      setDefaultReplyImageUrl(result.reply_image_url || '')
      setDefaultReplyOnce(result.reply_once || false)
    } catch {
      // ignore
    }
  }

  const handleSaveDefaultReply = async () => {
    if (!defaultReplyAccount) return

    try {
      setDefaultReplySaving(true)
      await updateDefaultReply(defaultReplyAccount.id, defaultReplyContent, true, defaultReplyOnce, defaultReplyImageUrl)
      addToast({ type: 'success', message: '默认回复已保存' })
      closeModal()
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setDefaultReplySaving(false)
    }
  }

  // 上传默认回复图片
  const handleUploadDefaultReplyImage = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return

    try {
      setUploadingDefaultReplyImage(true)
      const formData = new FormData()
      formData.append('image', file)

      const response = await fetch('/upload-image', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('auth_token')}`
        },
        body: formData
      })

      const result = await response.json()
      if (result.image_url) {
        setDefaultReplyImageUrl(result.image_url)
        addToast({ type: 'success', message: '图片上传成功' })
      } else {
        addToast({ type: 'error', message: result.detail || '图片上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '图片上传失败' })
    } finally {
      setUploadingDefaultReplyImage(false)
      e.target.value = ''
    }
  }

  // ==================== AI回复开关 ====================
  const handleToggleAI = async (account: AccountWithKeywordCount) => {
    const newEnabled = !account.aiEnabled
    try {
      // 只更新 ai_enabled 字段
      await updateAIReplySettings(account.id, {
        ai_enabled: newEnabled,
      })
      setAccounts(prev => prev.map(a =>
        a.id === account.id ? { ...a, aiEnabled: newEnabled } : a,
      ))
      addToast({ type: 'success', message: `AI回复已${newEnabled ? '开启' : '关闭'}` })
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  // ==================== AI设置管理 ====================
  const openAISettings = async (account: AccountWithKeywordCount) => {
    setAiSettingsAccount(account)
    setActiveModal('ai-settings')
    setAiSettingsLoading(true)
    try {
      const settings = await getAIReplySettings(account.id)
      setAiEnabled(settings.ai_enabled ?? settings.enabled ?? false)
      setAiMaxDiscountPercent(settings.max_discount_percent ?? 10)
      setAiMaxDiscountAmount(settings.max_discount_amount ?? 100)
      setAiMaxBargainRounds(settings.max_bargain_rounds ?? 3)
      setAiCustomPrompts(settings.custom_prompts ?? '')
    } catch {
      addToast({ type: 'error', message: '加载AI设置失败' })
    } finally {
      setAiSettingsLoading(false)
    }
  }

  const handleSaveAISettings = async () => {
    if (!aiSettingsAccount) return
    try {
      setAiSettingsSaving(true)
      await updateAIReplySettings(aiSettingsAccount.id, {
        enabled: aiEnabled,
        max_discount_percent: aiMaxDiscountPercent,
        max_discount_amount: aiMaxDiscountAmount,
        max_bargain_rounds: aiMaxBargainRounds,
        custom_prompts: aiCustomPrompts,
      })
      // 更新本地状态
      setAccounts(prev => prev.map(a =>
        a.id === aiSettingsAccount.id ? { ...a, aiEnabled } : a,
      ))
      addToast({ type: 'success', message: 'AI设置已保存' })
      closeModal()
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setAiSettingsSaving(false)
    }
  }

  const handleCheckStatus = async (account: AccountWithKeywordCount) => {
    setStatusChecking((prev) => ({ ...prev, [account.id]: true }))
    try {
      const result = await checkAccountStatus(account.id)
      const failedChecks = result.checks.filter((check) => !check.ok)
      if (result.ok) {
        addToast({
          type: 'success',
          message: `账号 ${account.id} 状态正常：Cookie字段 ${result.cookie_field_count} 个，后台任务${result.task_running ? '运行中' : '未运行'}`,
        })
      } else {
        addToast({
          type: 'warning',
          message: failedChecks.length > 0
            ? `账号 ${account.id} 状态异常：${failedChecks.map((check) => `${check.name}-${check.message}`).join('；')}`
            : result.message || '账号状态异常',
        })
      }
    } catch (error) {
      const detail = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      addToast({ type: 'error', message: detail || '检查账号状态失败' })
    } finally {
      setStatusChecking((prev) => ({ ...prev, [account.id]: false }))
    }
  }

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      clearQrCheck()
      clearQrVerificationWatcher()
    }
  }, [clearQrCheck, clearQrVerificationWatcher])

  if (loading) {
    return <PageLoading />
  }

  const columns: TableColumnProps<AccountTableRow>[] = [
    {
      title: '账号ID',
      dataIndex: 'id',
      width: 150,
      render: (id: string) => <span className="text-slate-700 dark:text-slate-200">{id}</span>,
    },
    {
      title: '关键词',
      dataIndex: 'keywordCount',
      width: 100,
      render: (_value, account) => (
        <Space size={6} className="accounts-keyword-cell">
          <span>{account.keywordCount || 0}</span>
        </Space>
      ),
    },
    {
      title: '状态',
      dataIndex: 'enabled',
      width: 100,
      render: (_value, account) => (
        <Tag
          color={account.enabled !== false ? 'green' : 'red'}
          onClick={() => handleToggleEnabled(account)}
          style={{ ...TAG_STYLE, cursor: 'pointer' }}
        >
          {account.enabled !== false ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: 'AI回复',
      dataIndex: 'aiEnabled',
      width: 100,
      render: (_value, account) => (
        <Tag
          color={account.aiEnabled ? 'cyan' : 'gray'}
          onClick={() => handleToggleAI(account)}
          style={{ ...TAG_STYLE, cursor: 'pointer' }}
        >
          {account.aiEnabled ? '开启' : '关闭'}
        </Tag>
      ),
    },
    {
      title: '自动确认',
      dataIndex: 'auto_confirm',
      width: 100,
      render: (autoConfirm: boolean) => (
        <Tag color={autoConfirm ? 'arcoblue' : 'gray'} style={TAG_STYLE}>
          {autoConfirm ? '开启' : '关闭'}
        </Tag>
      ),
    },
    {
      title: '暂停时间',
      dataIndex: 'pause_duration',
      width: 140,
      render: (_value, account) => (
        <Space size={5} className="accounts-muted-text">
          <Clock className="accounts-table-icon" />
          <span>{account.pause_duration || 0} 分钟</span>
        </Space>
      ),
    },
    {
      title: '操作',
      dataIndex: 'operation',
      render: (_value, account) => (
        <Space size={8} wrap>
          <Button
            type="text"
            className="accounts-table-action-btn"
            loading={statusChecking[account.id]}
            onClick={() => handleCheckStatus(account)}
          >
            检查状态
          </Button>
          <Button type="text" className="accounts-table-action-btn" onClick={() => openAISettings(account)}>
            AI设置
          </Button>
          <Button type="text" className="accounts-table-action-btn" onClick={() => openDefaultReplyModal(account)}>
            默认回复
          </Button>
          <ActionMenu
            trigger={(
              <Button type="text" className="accounts-table-action-btn">
                <span>更多</span>
                <ChevronDown className="w-4 h-4" />
              </Button>
            )}
            items={[
              {
                key: 'toggle',
                label: account.enabled !== false ? '禁用' : '启用',
                icon: account.enabled !== false ? <PowerOff className="w-4 h-4" /> : <Power className="w-4 h-4" />,
              },
              { key: 'edit', label: '编辑', icon: <Edit2 className="w-4 h-4" /> },
              { key: 'delete', label: '删除', icon: <Trash2 className="w-4 h-4" />, danger: true },
            ]}
            onSelect={(key) => {
              if (key === 'toggle') handleToggleEnabled(account)
              if (key === 'edit') openEditModal(account)
              if (key === 'delete') handleDelete(account.id)
            }}
          />
        </Space>
      ),
    },
  ]

  const data: AccountTableRow[] = accounts.map((account) => ({
    ...account,
    key: account.id,
  }))

  return (
    <div className="space-y-4">
      {/* Accounts List */}
      <Card
        bordered={false}
        className="xianyu-arco-page-card accounts-arco-card"
      >
        <div className="accounts-page-intro">
          <h1>账号管理</h1>
          <p>集中维护闲鱼账号、自动回复和发货确认状态。</p>
        </div>

        <div className="accounts-toolbar">
          <div className="accounts-filter-row accounts-filter-row--lined">
            <div className="accounts-action-row">
              <Space className="accounts-toolbar-right">
                <ActionMenu
                  trigger={(
                    <Button type="primary" className="accounts-header-btn">
                      <Plus />
                      <span>添加账号</span>
                      <ChevronDown />
                    </Button>
                  )}
                  items={[
                    {
                      key: 'qrcode',
                      label: (
                        <span className="flex items-center gap-2">
                          <span>扫码登录</span>
                          <span className="badge-info">推荐</span>
                        </span>
                      ),
                      icon: <QrCode className="w-4 h-4" />,
                    },
                    { key: 'password', label: '账号密码', icon: <Key className="w-4 h-4" /> },
                    { key: 'manual', label: '手动输入', icon: <Edit2 className="w-4 h-4" /> },
                  ]}
                  onSelect={(key) => handleAddAccountMethod(key as 'qrcode' | 'password' | 'manual')}
                  menuClassName="min-w-40"
                />
                <Button className="accounts-header-btn" onClick={loadAccounts}>
                  <RefreshCw />
                  <span>刷新</span>
                </Button>
              </Space>
            </div>
          </div>
        </div>

        <Table
          rowKey="key"
          columns={columns}
          data={data}
          pagination={false}
          border={false}
          scroll={{ x: 920 }}
          rowSelection={{
            type: 'checkbox',
            columnWidth: 44,
            checkAll: true,
          }}
          className="accounts-arco-table table-main"
          noDataElement={<Empty description="暂无账号，请添加新账号" />}
        />
      </Card>

      {/* 扫码登录弹窗 */}
      <Modal
        visible={activeModal === 'qrcode'}
        title="扫码登录"
        footer={null}
        onCancel={() => closeModal()}
        unmountOnExit
        className="accounts-arco-modal"
      >
        <div className="flex flex-col items-center py-6">
              {qrStatus === 'loading' && (
                <div className="flex flex-col items-center gap-3">
                  <Loader2 className="w-10 h-10 text-blue-600 dark:text-blue-400 animate-spin" />
                  <p className="text-sm text-slate-500 dark:text-slate-400">正在生成二维码...</p>
                </div>
              )}
              {qrStatus === 'ready' && (
                <div className="flex flex-col items-center gap-3">
                  <img src={qrCodeUrl} alt="登录二维码" className="w-44 h-44 rounded-lg border" />
                  <p className="text-sm text-slate-600 dark:text-slate-300">请使用闲鱼APP扫描二维码</p>
                  <p className="text-xs text-slate-400 dark:text-slate-500">二维码有效期约5分钟</p>
                </div>
              )}
              {qrStatus === 'scanned' && (
                <div className="flex flex-col items-center gap-3">
                  <img src={qrCodeUrl} alt="登录二维码" className="w-44 h-44 rounded-lg border opacity-50" />
                  <div className=" text-blue-600 dark:text-blue-400 text-sm">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>{qrVerificationUrl ? '需要手机验证' : '已扫描，等待确认...'}</span>
                  </div>
                  {qrVerificationUrl && (
                    <>
                      <p className="max-w-xs text-center text-sm text-slate-500 dark:text-slate-400">
                        账号触发风控，请打开验证页完成手机验证。
                      </p>
                      <div className="w-full max-w-md rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
                        <div className="mb-2 flex items-center justify-between gap-2">
                          <span className="text-xs text-slate-500 dark:text-slate-400">服务器端验证页预览</span>
                          <Button
                            onClick={() => void loadQrVerificationScreenshot(qrSessionRef.current)}
                            loading={qrVerificationScreenshotLoading}
                            size="mini"
                          >
                            刷新预览
                          </Button>
                        </div>
                        <div className="overflow-hidden rounded border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
                          {qrVerificationScreenshotUrl ? (
                            <img
                              src={qrVerificationScreenshotUrl}
                              alt="验证页预览"
                              className="max-h-72 w-full object-contain"
                            />
                          ) : (
                            <div className="flex h-48 items-center justify-center text-sm text-slate-400">
                              {qrVerificationScreenshotLoading ? '正在生成预览...' : '验证页预览暂未生成'}
                            </div>
                          )}
                        </div>
                      </div>
                      <Space>
                        <Button
                          onClick={openQrVerificationPage}
                          size="small"
                          type="primary"
                        >
                          打开验证页
                        </Button>
                        <Button
                          onClick={manualCheckQRLogin}
                          loading={qrManualChecking}
                          size="small"
                        >
                          我已完成验证
                        </Button>
                      </Space>
                    </>
                  )}
                </div>
              )}
              {qrStatus === 'success' && (
                <div className="flex flex-col items-center gap-3 text-green-600">
                  <div className="w-14 h-14 rounded-full bg-green-100 flex items-center justify-center">
                    <Power className="w-7 h-7" />
                  </div>
                  <p className="font-medium">登录成功！</p>
                </div>
              )}
              {qrStatus === 'expired' && (
                <div className="flex flex-col items-center gap-3">
                  <p className="text-sm text-slate-500 dark:text-slate-400">二维码已过期</p>
                  <Button onClick={refreshQRCode} size="small" type="primary">
                    刷新二维码
                  </Button>
                </div>
              )}
              {qrStatus === 'error' && (
                <div className="flex flex-col items-center gap-3">
                  <p className="text-sm text-red-500">生成二维码失败</p>
                  <Button onClick={refreshQRCode} size="small" type="primary">
                    重试
                  </Button>
                </div>
              )}
        </div>
      </Modal>

      {/* 密码登录弹窗 */}
      <Modal
        visible={activeModal === 'password'}
        title="账号密码登录"
        footer={null}
        onCancel={() => closeModal()}
        unmountOnExit
        className="accounts-arco-modal"
      >
        <form onSubmit={handlePasswordLogin}>
          <div className="space-y-4">
                <div className="input-group">
                  <label className="input-label">账号</label>
                  <Input
                    value={pwdAccount}
                    onChange={setPwdAccount}
                    placeholder="请输入闲鱼账号/手机号"
                    autoFocus
                  />
                </div>
                <div className="input-group">
                  <label className="input-label">密码</label>
                  <Input.Password
                    value={pwdPassword}
                    onChange={setPwdPassword}
                    placeholder="请输入密码"
                  />
                </div>
                <p className="input-hint">
                  登录过程可能需要进行人脸验证，请确保手机畅通
                </p>
                <Checkbox checked={pwdShowBrowser} onChange={setPwdShowBrowser}>
                  显示浏览器（调试用）
                </Checkbox>
                {pwdStatus !== 'idle' && (
                  <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-800">
                    <div className="mb-2 flex items-center gap-2">
                      {pwdStatus === 'processing' && <Loader2 className="h-4 w-4 animate-spin text-blue-500" />}
                      {pwdStatus === 'verification_required' && <AlertTriangle className="h-4 w-4 text-orange-500" />}
                      {pwdStatus === 'success' && <CheckCircle className="h-4 w-4 text-green-500" />}
                      {pwdStatus === 'failed' && <X className="h-4 w-4 text-red-500" />}
                      <span className="text-sm font-medium text-slate-700 dark:text-slate-200">
                        {pwdStatus === 'processing' && '等待页面响应'}
                        {pwdStatus === 'verification_required' && '需要人工辅助验证'}
                        {pwdStatus === 'success' && '登录成功'}
                        {pwdStatus === 'failed' && '登录失败'}
                      </span>
                    </div>
                    <p className="text-sm text-slate-500 dark:text-slate-400">
                      {pwdStatusMessage || '正在检查登录状态...'}
                    </p>
                    {pwdStatus === 'verification_required' && (
                      <div className="mt-3 space-y-3">
                        {pwdScreenshotPath && (
                          <div className="overflow-hidden rounded border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900">
                            <img
                              src={pwdScreenshotPath.startsWith('/') ? pwdScreenshotPath : `/${pwdScreenshotPath}`}
                              alt="验证页面截图"
                              className="max-h-72 w-full object-contain"
                            />
                          </div>
                        )}
                        <Space>
                          {pwdVerificationUrl && (
                            <Button
                              size="small"
                              type="primary"
                              onClick={() => window.open(pwdVerificationUrl, '_blank', 'noopener,noreferrer')}
                            >
                              打开验证页
                            </Button>
                          )}
                          <Button
                            size="small"
                            onClick={() => pwdSessionId && void pollPasswordLoginStatus(pwdSessionId)}
                          >
                            我已完成验证
                          </Button>
                        </Space>
                      </div>
                    )}
                  </div>
                )}
          </div>
          <div className="modal-footer px-0 pb-0">
            <Button type="secondary" onClick={() => closeModal()}>
              取消
            </Button>
            <Button htmlType="submit" type="primary" disabled={pwdLoading || pwdStatus === 'verification_required'}>
                  {pwdLoading ? (
                    <span className="inline-flex items-center gap-1.5">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      登录中...
                    </span>
                  ) : (
                    '登录'
                  )}
            </Button>
          </div>
        </form>
      </Modal>

      {/* 手动输入弹窗 */}
      <Modal
        visible={activeModal === 'manual'}
        title="手动输入Cookie"
        footer={null}
        onCancel={() => closeModal()}
        unmountOnExit
        className="accounts-arco-modal"
      >
        <form onSubmit={handleManualAdd}>
          <div className="space-y-4">
                <div className="input-group">
                  <label className="input-label">账号ID</label>
                  <Input
                    value={manualAccountId}
                    onChange={setManualAccountId}
                    placeholder="请输入账号ID（如手机号或用户名）"
                    autoFocus
                  />
                </div>
                <div className="input-group">
                  <label className="input-label">Cookie</label>
                  <TextArea
                    value={manualCookie}
                    onChange={setManualCookie}
                    autoSize={{ minRows: 6, maxRows: 10 }}
                    className="font-mono text-xs"
                    placeholder="请粘贴完整的Cookie值"
                  />
                  <p className="input-hint">
                    可从浏览器开发者工具中获取Cookie
                  </p>
                </div>
          </div>
          <div className="modal-footer px-0 pb-0">
            <Button type="secondary" onClick={() => closeModal()} disabled={manualLoading}>
              取消
            </Button>
            <Button htmlType="submit" type="primary" disabled={manualLoading}>
              {manualLoading ? (
                <span className="">
                  <Loader2 className="w-4 h-4 animate-spin" />
                  添加中...
                </span>
              ) : (
                '添加账号'
              )}
            </Button>
          </div>
        </form>
      </Modal>

      {/* 编辑账号弹窗 */}
      <Modal
        visible={activeModal === 'edit' && !!editingAccount}
        title="编辑账号"
        footer={null}
        onCancel={() => closeModal()}
        unmountOnExit
        className="accounts-arco-modal"
        style={{ width: 860 }}
      >
        <form onSubmit={handleEditSubmit}>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="space-y-4">
                <div className="input-group">
                  <label className="input-label">账号ID</label>
                  <Input value={editingAccount?.id || ''} disabled />
                </div>
                <div className="input-group">
                  <label className="input-label">备注</label>
                  <Input value={editNote} onChange={setEditNote} placeholder="添加备注信息" />
                </div>
                <div className="input-group">
                  <label className="input-label">Cookie</label>
                  <TextArea
                    value={editCookie}
                    onChange={setEditCookie}
                    autoSize={{ minRows: 4, maxRows: 8 }}
                    className="font-mono text-xs"
                    placeholder="更新Cookie值"
                  />
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    当前Cookie长度: {editCookie.length} 字符
                  </p>
                </div>

                {/* 自动确认发货 */}
                <div className="flex items-center justify-between py-3 border-t border-slate-100 dark:border-slate-700">
                  <div>
                    <p className="font-medium text-slate-900 dark:text-slate-100 flex items-center gap-2">
                      <CheckCircle className="w-4 h-4 text-green-500" />
                      自动确认发货
                    </p>
                    <p className="text-xs text-slate-500 dark:text-slate-400">开启后系统会自动确认发货</p>
                  </div>
                  <Button
                    onClick={() => setEditAutoConfirm(!editAutoConfirm)}
                    size="mini"
                    type={editAutoConfirm ? 'primary' : 'secondary'}
                  >
                    {editAutoConfirm ? '开启' : '关闭'}
                  </Button>
                </div>
            </div>

            <div className="space-y-4">
                {/* 登录信息管理 */}
                <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-4">
                  <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-3 flex items-center gap-2">
                    <Key className="w-4 h-4 text-blue-500" />
                    登录信息（用于自动登录）
                  </h3>
                  <div className="space-y-3">
                    <div className="input-group">
                      <label className="input-label text-xs">登录账号</label>
                      <Input
                        value={editUsername}
                        onChange={setEditUsername}
                        placeholder="手机号或用户名"
                      />
                    </div>
                    <div className="input-group">
                      <label className="input-label text-xs">登录密码</label>
                      <div className="relative">
                        <Input
                          type={showLoginPassword ? 'text' : 'password'}
                          value={editLoginPassword}
                          onChange={setEditLoginPassword}
                          className="pr-10"
                          placeholder="登录密码"
                        />
                        <Button
                          onClick={() => setShowLoginPassword(!showLoginPassword)}
                          className="absolute right-1 top-1/2 -translate-y-1/2"
                          size="mini"
                          type="text"
                          icon={showLoginPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        >
                        </Button>
                      </div>
                    </div>
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="text-sm text-slate-700 dark:text-slate-300">显示浏览器</p>
                        <p className="text-xs text-slate-500 dark:text-slate-400">调试时可开启查看登录过程</p>
                      </div>
                      <Button
                        onClick={() => setEditShowBrowser(!editShowBrowser)}
                        size="mini"
                        type={editShowBrowser ? 'primary' : 'secondary'}
                      >
                        {editShowBrowser ? '开启' : '关闭'}
                      </Button>
                    </div>
                  </div>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
                    保存登录信息后，Cookie过期时系统可自动重新登录
                  </p>
                </div>

                {/* 暂停时间 */}
                <div className="rounded-lg border border-slate-200 dark:border-slate-700 p-4">
                  <label className="input-label flex items-center gap-2">
                    <Clock className="w-4 h-4 text-amber-500" />
                    暂停时间（分钟）
                  </label>
                  <InputNumber
                    min={0}
                    max={1440}
                    value={editPauseDuration}
                    onChange={(value) => setEditPauseDuration(Number(value) || 0)}
                    placeholder="0"
                    style={{ width: '100%' }}
                  />
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-2">
                    检测到手动发出消息后，自动回复暂停的时间。设置为0表示不暂停。
                  </p>
                </div>

                <p className="text-xs text-slate-500 dark:text-slate-400 pt-2">
                  提示：AI回复和默认回复设置请在"自动回复"页面配置
                </p>
            </div>
          </div>
          <div className="modal-footer px-0 pb-0">
            <Button type="secondary" onClick={() => closeModal()} disabled={editSaving}>
              取消
            </Button>
            <Button htmlType="submit" type="primary" disabled={editSaving}>
                  {editSaving ? (
                    <span className="">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      保存中...
                    </span>
                  ) : (
                    '保存'
                  )}
            </Button>
          </div>
        </form>
      </Modal>

      {/* 默认回复管理弹窗 */}
      <Modal
        visible={activeModal === 'default-reply' && !!defaultReplyAccount}
        title="默认回复管理"
        footer={null}
        onCancel={() => closeModal()}
        unmountOnExit
        className="accounts-arco-modal"
      >
        <div className="space-y-4">
              <div className="input-group">
                <label className="input-label">账号</label>
                <Input value={defaultReplyAccount?.id || ''} disabled />
              </div>
              <div className="input-group">
                <label className="input-label">默认回复内容</label>
                <TextArea
                  value={defaultReplyContent}
                  onChange={setDefaultReplyContent}
                  autoSize={{ minRows: 6, maxRows: 10 }}
                  placeholder="输入默认回复内容，留空表示不使用默认回复"
                />
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  当没有匹配到任何关键词时，将使用此默认回复。留空表示不自动回复。
                </p>
              </div>
              <div className="input-group">
                <label className="input-label">回复图片（可选）</label>
                <div className="flex items-center gap-2">
                  <Input
                    value={defaultReplyImageUrl}
                    onChange={setDefaultReplyImageUrl}
                    placeholder="图片URL或上传图片"
                  />
                  <Button
                    type="secondary"
                    loading={uploadingDefaultReplyImage}
                    onClick={() => document.getElementById('account-default-reply-image')?.click()}
                  >
                    {uploadingDefaultReplyImage ? (
                      <Loader2 className="w-4 h-4 animate-spin" />
                    ) : (
                      '上传'
                    )}
                    <input
                      id="account-default-reply-image"
                      type="file"
                      accept="image/*"
                      className="hidden"
                      onChange={handleUploadDefaultReplyImage}
                      disabled={uploadingDefaultReplyImage}
                    />
                  </Button>
                </div>
                {defaultReplyImageUrl && (
                  <div className="mt-2 relative inline-block">
                    <img
                      src={defaultReplyImageUrl}
                      alt="回复图片预览"
                      className="max-w-32 max-h-32 rounded border border-slate-200 dark:border-slate-700"
                    />
                    <Button
                      onClick={() => setDefaultReplyImageUrl('')}
                      className="absolute -top-2 -right-2"
                      size="mini"
                      status="danger"
                      shape="circle"
                      icon={<X className="w-3 h-3" />}
                    >
                    </Button>
                  </div>
                )}
              </div>
              <div className="input-group">
                <label className="flex items-center gap-2 cursor-pointer">
                  <Checkbox checked={defaultReplyOnce} onChange={setDefaultReplyOnce}>
                    只能回复一次
                  </Checkbox>
                </label>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  开启后，每个对话只会使用默认回复一次，避免重复回复同一用户
                </p>
              </div>
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                <p className="text-xs text-blue-600 dark:text-blue-400">
                  <strong>支持变量：</strong><br />
                  <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">{'{send_user_name}'}</code> - 用户昵称<br />
                  <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">{'{send_user_id}'}</code> - 用户ID<br />
                  <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">{'{send_message}'}</code> - 用户消息内容
                </p>
              </div>
        </div>
        <div className="modal-footer px-0 pb-0">
          <Button type="secondary" onClick={() => closeModal()} disabled={defaultReplySaving}>
            取消
          </Button>
          <Button onClick={handleSaveDefaultReply} type="primary" disabled={defaultReplySaving}>
                {defaultReplySaving ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    保存中...
                  </span>
                ) : (
                  '保存'
                )}
          </Button>
        </div>
      </Modal>

      {/* AI设置弹窗 */}
      <Modal
        visible={activeModal === 'ai-settings' && !!aiSettingsAccount}
        title="AI回复设置"
        footer={null}
        onCancel={() => closeModal()}
        unmountOnExit
        className="accounts-arco-modal"
      >
        <div className="space-y-4">
              {aiSettingsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Spin tip="加载中..." />
                </div>
              ) : (
                <>
                  <div className="input-group">
                    <label className="input-label">账号</label>
                    <Input value={aiSettingsAccount?.id || ''} disabled />
                  </div>

                  <div className="border-t border-slate-200 dark:border-slate-700 pt-4 mt-2">
                    <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-3">议价设置</h3>
                    <div className="grid grid-cols-3 gap-3">
                      <div className="input-group">
                        <label className="input-label text-xs">最大折扣(%)</label>
                        <InputNumber
                          value={aiMaxDiscountPercent}
                          onChange={(value) => setAiMaxDiscountPercent(Number(value) || 0)}
                          min={0}
                          max={100}
                          style={{ width: '100%' }}
                        />
                      </div>
                      <div className="input-group">
                        <label className="input-label text-xs">最大减价(元)</label>
                        <InputNumber
                          value={aiMaxDiscountAmount}
                          onChange={(value) => setAiMaxDiscountAmount(Number(value) || 0)}
                          min={0}
                          style={{ width: '100%' }}
                        />
                      </div>
                      <div className="input-group">
                        <label className="input-label text-xs">最大议价轮数</label>
                        <InputNumber
                          value={aiMaxBargainRounds}
                          onChange={(value) => setAiMaxBargainRounds(Number(value) || 1)}
                          min={1}
                          max={10}
                          style={{ width: '100%' }}
                        />
                      </div>
                    </div>
                  </div>

                  <div className="input-group">
                    <label className="input-label">自定义提示词 (JSON格式)</label>
                    <TextArea
                      value={aiCustomPrompts}
                      onChange={setAiCustomPrompts}
                      autoSize={{ minRows: 6, maxRows: 10 }}
                      className="font-mono text-xs"
                      placeholder='{"classify": "分类提示词", "price": "议价提示词", "tech": "技术提示词", "default": "默认提示词"}'
                    />
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                      留空使用系统默认提示词。格式：{`{"classify": "...", "price": "...", "tech": "...", "default": "..."}`}
                    </p>
                  </div>
                </>
              )}
        </div>
        <div className="modal-footer px-0 pb-0">
          <Button type="secondary" onClick={() => closeModal()} disabled={aiSettingsSaving}>
            取消
          </Button>
          <Button
            onClick={handleSaveAISettings}
            type="primary"
            disabled={aiSettingsSaving || aiSettingsLoading}
          >
                {aiSettingsSaving ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    保存中...
                  </span>
                ) : (
                  '保存'
                )}
          </Button>
        </div>
      </Modal>

      {/* 默认密码警告弹窗 */}
      <Modal
        visible={showPasswordWarning}
        title={<span className="flex items-center gap-2 text-amber-600"><AlertTriangle className="w-5 h-5" />安全提醒</span>}
        footer={null}
        onCancel={() => setShowPasswordWarning(false)}
        unmountOnExit
        className="accounts-arco-modal"
      >
        <div>
              <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-4 mb-4">
                <p className="text-amber-800 dark:text-amber-200 text-sm">
                  检测到您正在使用默认密码 <code className="bg-amber-100 dark:bg-amber-800 px-1 rounded">admin123</code>，
                  为了账号安全，请先修改密码后再添加闲鱼账号。
                </p>
              </div>
              <p className="text-slate-600 dark:text-slate-400 text-sm">
                请前往 <strong>系统设置</strong> 页面修改您的登录密码。
              </p>
        </div>
        <div className="modal-footer px-0 pb-0">
          <Button type="secondary" onClick={() => setShowPasswordWarning(false)}>
            稍后修改
          </Button>
          <Button
            type="primary"
            onClick={() => {
              setShowPasswordWarning(false)
              window.location.href = '/settings'
            }}
          >
                立即修改密码
          </Button>
        </div>
      </Modal>
    </div>
  )
}
