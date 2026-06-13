import { useCallback, useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { Plus, RefreshCw, QrCode, Key, Edit2, Trash2, Power, PowerOff, X, Loader2, Clock, CheckCircle, MessageSquare, Bot, Globe, Timer, ScanFace, ChevronLeft, ChevronRight, ChevronDown, ImagePlus, Filter, Repeat, MoreHorizontal, PackageCheck, Star, ShieldCheck, Flower2, Eye, EyeOff, Ban, Download, Upload, Send } from 'lucide-react'
import { getAccountDetailsPaginated, deleteAccount, updateAccountCookie, updateAccountStatus, updateAccountsStatusBatch, closeAccountsNoticeBatch, clearTokenCacheBatch, updateAccountRemark, addAccount, generateQRLogin, checkQRLoginStatus, passwordLogin, checkPasswordLoginStatus, updateAccountAutoConfirm, updateAccountPauseDuration, updateAccountMessageExpireTime, updateAccountReplyDelay, updateAccountLoginInfo, updateAccountScheduledRedelivery, updateAccountScheduledRate, updateAccountAutoPolish, updateAccountConfirmBeforeSend, updateAccountSendBeforeConfirm, updateAccountAutoRedFlower, updateAccountAiReplyBlockOrderedUsers, getAIReplySettings, updateAIReplySettings, testAIConnection, fetchAIModels, AI_PROVIDER_OPTIONS, AI_PROVIDER_DEFAULT_BASE_URLS, getProxyConfig, updateProxyConfig, getFaceVerificationScreenshot, deleteFaceVerificationScreenshot, getConfirmReceiptMessage, updateConfirmReceiptMessage, uploadConfirmReceiptImage, exportAccountsExcel, importAccountsExcel, type AIProviderType, type AIModelOption, type ProxyConfig, type FaceVerificationScreenshot, type AccountFilterParams } from '@/api/accounts'
import { getDefaultReply, updateDefaultReply, uploadDefaultReplyImage } from '@/api/keywords'
import { getAutoRateConfig, updateAutoRateConfig } from '@/api/autoRate'
import { checkAdminDefaultPassword } from '@/api/auth'
import { getApiErrorMessage } from '@/utils/request'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { useMenuVisibilityStore } from '@/store/menuVisibilityStore'
import { PageLoading } from '@/components/common/Loading'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { DeliveryBlockRulesModal } from './DeliveryBlockRulesModal'
import type { AccountDetail } from '@/types'

type ModalType = 'qrcode' | 'password' | 'manual' | 'edit' | 'default-reply' | 'ai-settings' | 'proxy-settings' | 'message-expire-time' | 'reply-delay' | 'face-verification' | 'confirm-receipt' | 'auto-rate' | 'delivery-disabled' | null

interface AccountWithKeywordCount extends AccountDetail {
  keywordCount?: number
  aiEnabled?: boolean
}

interface AccountPagination {
  page: number
  pageSize: number
  total: number
  totalPages: number
}

// 筛选状态类型
interface AccountFilters {
  status: 'active' | 'inactive' | null
  ai_reply: boolean | null
  scheduled_redelivery: boolean | null
  scheduled_rate: boolean | null
  auto_polish: boolean | null
  auto_confirm: boolean | null
  has_password: boolean | null
  disable_reason: string | null
  account_id: string | null
}

interface AIConfigSnapshot {
  provider_type?: AIProviderType
  base_url?: string
  api_key?: string
  model_name?: string
}

const getAIConfigMissingItems = (config: AIConfigSnapshot): string[] => {
  const providerType = config.provider_type || 'openai_compatible'
  const baseUrl = (config.base_url || '').trim()
  const apiKey = (config.api_key || '').trim()
  const modelName = (config.model_name || '').trim()
  const missingItems: string[] = []
  if (!baseUrl) missingItems.push('API地址')
  if (!apiKey) missingItems.push('API Key')
  if (providerType !== 'dashscope_app' && !modelName) missingItems.push('模型名称')
  if (providerType === 'dashscope_app' && baseUrl && (baseUrl.includes('{app_id}') || !baseUrl.includes('/apps/'))) {
    missingItems.push('DashScope应用地址')
  }
  return missingItems
}

const getAIConfigIncompleteMessage = (missingItems: string[]): string => (
  `AI配置未填写完整，请先补全：${missingItems.join('、')}`
)

export function Accounts() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, user, _hasHydrated } = useAuthStore()
  const { isExeMode } = useMenuVisibilityStore()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [accounts, setAccounts] = useState<AccountWithKeywordCount[]>([])
  const [activeModal, setActiveModal] = useState<ModalType>(null)
  const [pagination, setPagination] = useState<AccountPagination>({
    page: 1,
    pageSize: 100,
    total: 0,
    totalPages: 0,
  })
  const [accountsLoading, setAccountsLoading] = useState(false)
  
  // 筛选状态
  const [filters, setFilters] = useState<AccountFilters>({
    status: null,
    ai_reply: null,
    scheduled_redelivery: null,
    scheduled_rate: null,
    auto_polish: null,
    auto_confirm: null,
    has_password: null,
    disable_reason: null,
    account_id: null,
  })
  const [showFilters, setShowFilters] = useState(false)
  // 「禁用原因」筛选输入框的本地草稿：输入过程不触发接口，回车/失焦/点击查询按钮时提交
  const [disableReasonInput, setDisableReasonInput] = useState('')
  // 「账号ID」筛选输入框的本地草稿：输入过程不触发接口，回车/失焦/点击查询按钮时提交
  const [accountIdInput, setAccountIdInput] = useState('')
  
  // 更多操作下拉菜单状态
  const [moreMenuAccountId, setMoreMenuAccountId] = useState<string | null>(null)
  const [moreMenuPosition, setMoreMenuPosition] = useState<{ top: number; right: number }>({ top: 0, right: 0 })

  // 默认回复管理状态
  const [defaultReplyAccount, setDefaultReplyAccount] = useState<AccountWithKeywordCount | null>(null)
  const [defaultReplyContent, setDefaultReplyContent] = useState('')
  const [defaultReplyImage, setDefaultReplyImage] = useState('')
  const [defaultReplyEnabled, setDefaultReplyEnabled] = useState(false)
  const [defaultReplyOnce, setDefaultReplyOnce] = useState(false)
  const [defaultReplyType, setDefaultReplyType] = useState<'text' | 'api'>('text')
  const [defaultReplyApiUrl, setDefaultReplyApiUrl] = useState('')
  const [defaultReplyApiTimeout, setDefaultReplyApiTimeout] = useState(80)
  const [defaultReplySaving, setDefaultReplySaving] = useState(false)
  const [defaultReplyImageUploading, setDefaultReplyImageUploading] = useState(false)
  const defaultReplyImageInputRef = useRef<HTMLInputElement>(null)

  // 扫码登录状态
  const [qrCodeUrl, setQrCodeUrl] = useState('')
  const [, setQrSessionId] = useState('')
  const [qrStatus, setQrStatus] = useState<'loading' | 'ready' | 'scanned' | 'success' | 'failed' | 'expired' | 'error'>('loading')
  const [qrErrorMessage, setQrErrorMessage] = useState('')
  const qrCheckIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 密码登录状态
  const [pwdAccount, setPwdAccount] = useState('')
  const [pwdPassword, setPwdPassword] = useState('')
  const [pwdPasswordVisible, setPwdPasswordVisible] = useState(false)
  const [pwdLoading, setPwdLoading] = useState(false)
  const [pwdShowBrowser, setPwdShowBrowser] = useState(false)
  const [, setPwdSessionId] = useState('')
  const [pwdStatus, setPwdStatus] = useState<'idle' | 'processing' | 'verification_required' | 'success' | 'failed'>('idle')
  const [pwdVerificationUrl, setPwdVerificationUrl] = useState('')
  const [pwdScreenshotPath, setPwdScreenshotPath] = useState('')
  const pwdCheckIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // 手动输入状态
  const [manualAccountId, setManualAccountId] = useState('')
  const [manualCookie, setManualCookie] = useState('')
  const [manualLoading, setManualLoading] = useState(false)

  // 编辑账号状态
  const [editingAccount, setEditingAccount] = useState<AccountDetail | null>(null)
  const [editNote, setEditNote] = useState('')
  const [editCookie, setEditCookie] = useState('')
  const [, setEditAutoConfirm] = useState(false)
  const [editPauseDuration, setEditPauseDuration] = useState(0)
  const [editUsername, setEditUsername] = useState('')
  const [editPassword, setEditPassword] = useState('')
  const [editPasswordVisible, setEditPasswordVisible] = useState(false)
  const [editShowBrowser, setEditShowBrowser] = useState(false)
  const [editSaving, setEditSaving] = useState(false)

  // AI设置状态
  const [aiSettingsAccount, setAiSettingsAccount] = useState<AccountWithKeywordCount | null>(null)
  const [aiEnabled, setAiEnabled] = useState(false)
  const [aiProviderType, setAiProviderType] = useState<AIProviderType>('openai_compatible')
  const [aiApiUrl, setAiApiUrl] = useState('')
  const [aiApiKey, setAiApiKey] = useState('')
  const [aiModelName, setAiModelName] = useState('')
  const [aiMaxDiscountPercent, setAiMaxDiscountPercent] = useState(10)
  const [aiMaxDiscountAmount, setAiMaxDiscountAmount] = useState(100)
  const [aiMaxBargainRounds, setAiMaxBargainRounds] = useState(3)
  const [aiCustomPrompts, setAiCustomPrompts] = useState('')
  const [aiTimeRangeStart, setAiTimeRangeStart] = useState('')
  const [aiTimeRangeEnd, setAiTimeRangeEnd] = useState('')
  const [aiSettingsSaving, setAiSettingsSaving] = useState(false)
  const [aiSettingsLoading, setAiSettingsLoading] = useState(false)
  const [aiTesting, setAiTesting] = useState(false)
  const [aiModelOptions, setAiModelOptions] = useState<AIModelOption[]>([])
  const [aiModelsLoading, setAiModelsLoading] = useState(false)
  const [showAiModelDropdown, setShowAiModelDropdown] = useState(false)
  // 是否按当前输入过滤模型列表：用户主动键入时为 true，点击展开按钮时为 false（显示全部）
  const [aiModelFilterByInput, setAiModelFilterByInput] = useState(false)
  // API Key 显示/隐藏切换
  const [showAiApiKey, setShowAiApiKey] = useState(false)

  // 代理设置状态
  const [proxySettingsAccount, setProxySettingsAccount] = useState<AccountWithKeywordCount | null>(null)
  const [proxyType, setProxyType] = useState<'none' | 'http' | 'https' | 'socks5'>('none')
  const [proxyHost, setProxyHost] = useState('')
  const [proxyPort, setProxyPort] = useState<number | ''>('')
  const [proxyUser, setProxyUser] = useState('')
  const [proxyPass, setProxyPass] = useState('')
  const [proxySettingsLoading, setProxySettingsLoading] = useState(false)
  const [proxySettingsSaving, setProxySettingsSaving] = useState(false)

  // 消息等待时间设置状态
  const [messageExpireTimeAccount, setMessageExpireTimeAccount] = useState<AccountWithKeywordCount | null>(null)
  const [messageExpireTime, setMessageExpireTime] = useState(3600)
  const [messageExpireTimeSaving, setMessageExpireTimeSaving] = useState(false)

  // 自动回复延迟设置状态
  const [replyDelayAccount, setReplyDelayAccount] = useState<AccountWithKeywordCount | null>(null)
  const [replyDelay, setReplyDelay] = useState(0)
  const [replyDelaySaving, setReplyDelaySaving] = useState(false)

  // 人脸验证状态
  const [faceVerificationAccount, setFaceVerificationAccount] = useState<AccountWithKeywordCount | null>(null)
  const [faceVerificationScreenshot, setFaceVerificationScreenshot] = useState<FaceVerificationScreenshot | null>(null)
  const [faceVerificationLoading, setFaceVerificationLoading] = useState(false)

  // 确认收货消息状态
  const [confirmReceiptAccount, setConfirmReceiptAccount] = useState<AccountWithKeywordCount | null>(null)
  const [confirmReceiptEnabled, setConfirmReceiptEnabled] = useState(false)
  const [confirmReceiptContent, setConfirmReceiptContent] = useState('')
  const [confirmReceiptImage, setConfirmReceiptImage] = useState('')
  const [confirmReceiptSaving, setConfirmReceiptSaving] = useState(false)
  const [confirmReceiptImageUploading, setConfirmReceiptImageUploading] = useState(false)
  const confirmReceiptImageInputRef = useRef<HTMLInputElement>(null)

  // 自动评价配置状态
  const [autoRateAccount, setAutoRateAccount] = useState<AccountWithKeywordCount | null>(null)
  const [autoRateEnabled, setAutoRateEnabled] = useState(false)
  const [autoRateType, setAutoRateType] = useState<'text' | 'api'>('text')
  const [autoRateTextContent, setAutoRateTextContent] = useState('')
  const [autoRateApiUrl, setAutoRateApiUrl] = useState('')
  const [autoRateSaving, setAutoRateSaving] = useState(false)

  // 禁止发货设置状态
  const [deliveryDisabledAccount, setDeliveryDisabledAccount] = useState<AccountWithKeywordCount | null>(null)

  // 确认弹窗状态
  const [deleteAccountConfirm, setDeleteAccountConfirm] = useState<{ open: boolean; id: string | null }>({ open: false, id: null })
  const [deleteFaceConfirm, setDeleteFaceConfirm] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([])
  const [batchAction, setBatchAction] = useState<'enable' | 'disable' | 'close-notice' | 'clear-token' | 'renew-login' | 'batch-rate' | null>(null)
  const [exporting, setExporting] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [importFile, setImportFile] = useState<File | null>(null)
  const [importing, setImporting] = useState(false)

  const selectedCount = selectedAccountIds.length
  const batchOperating = batchAction !== null
  const allVisibleSelected = accounts.length > 0 && accounts.every(account => selectedAccountIds.includes(account.id))
  // 是否管理员：管理员可查看全量账号，需展示账号所属用户列
  const isAdmin = Boolean(user?.is_admin)

  const loadAccounts = async (page: number = pagination.page, pageSize: number = pagination.pageSize, currentFilters: AccountFilters = filters) => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setAccountsLoading(true)
      
      // 构建筛选参数
      const filterParams: AccountFilterParams = {}
      if (currentFilters.status) filterParams.status = currentFilters.status
      if (currentFilters.ai_reply !== null) filterParams.ai_reply = currentFilters.ai_reply
      if (currentFilters.scheduled_redelivery !== null) filterParams.scheduled_redelivery = currentFilters.scheduled_redelivery
      if (currentFilters.scheduled_rate !== null) filterParams.scheduled_rate = currentFilters.scheduled_rate
      if (currentFilters.auto_polish !== null) filterParams.auto_polish = currentFilters.auto_polish
      if (currentFilters.auto_confirm !== null) filterParams.auto_confirm = currentFilters.auto_confirm
      if (currentFilters.has_password !== null) filterParams.has_password = currentFilters.has_password
      if (currentFilters.disable_reason && currentFilters.disable_reason.trim()) {
        filterParams.disable_reason = currentFilters.disable_reason.trim()
      }
      if (currentFilters.account_id && currentFilters.account_id.trim()) {
        filterParams.account_id = currentFilters.account_id.trim()
      }
      
      const result = await getAccountDetailsPaginated(page, pageSize, filterParams)

      setAccounts(result.data)
      setSelectedAccountIds(prev => prev.filter(accountId => result.data.some(account => account.id === accountId)))
      setPagination({
        page: result.page,
        pageSize: result.page_size,
        total: result.total,
        totalPages: result.total_pages,
      })
    } catch {
      addToast({ type: 'error', message: '加载账号列表失败' })
    } finally {
      setAccountsLoading(false)
      setLoading(false)
    }
  }

  // 分页切换
  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= pagination.totalPages) {
      loadAccounts(newPage, pagination.pageSize, filters)
    }
  }

  // 每页条数切换
  const handlePageSizeChange = (newPageSize: number) => {
    setPagination(prev => ({ ...prev, pageSize: newPageSize }))
    loadAccounts(1, newPageSize, filters)
  }
  
  // 筛选条件变更
  const handleFilterChange = (key: keyof AccountFilters, value: string | boolean | null) => {
    const newFilters = { ...filters, [key]: value }
    setFilters(newFilters)
    loadAccounts(1, pagination.pageSize, newFilters)
  }
  
  // 重置筛选条件
  const handleResetFilters = () => {
    const emptyFilters: AccountFilters = {
      status: null,
      ai_reply: null,
      scheduled_redelivery: null,
      scheduled_rate: null,
      auto_polish: null,
      auto_confirm: null,
      has_password: null,
      disable_reason: null,
      account_id: null,
    }
    setFilters(emptyFilters)
    setDisableReasonInput('')
    setAccountIdInput('')
    loadAccounts(1, pagination.pageSize, emptyFilters)
  }

  // 提交「禁用原因」筛选（回车或失焦时调用）
  const handleDisableReasonSubmit = () => {
    const keyword = disableReasonInput.trim()
    const currentValue = filters.disable_reason || ''
    // 关键词未变化则跳过，避免重复请求
    if (keyword === currentValue) return
    handleFilterChange('disable_reason', keyword || null)
  }

  // 提交「账号ID」筛选（回车或失焦时调用）
  const handleAccountIdSubmit = () => {
    const keyword = accountIdInput.trim()
    const currentValue = filters.account_id || ''
    // 关键词未变化则跳过，避免重复请求
    if (keyword === currentValue) return
    handleFilterChange('account_id', keyword || null)
  }

  // 统一「查询」按钮：合并所有文本草稿到 filters 后按筛选条件重新查询
  // - 文本类筛选（账号ID、禁用原因）只在草稿提交后才生效；点击查询会强制以当前草稿为准
  // - 下拉类筛选（状态、AI 回复等）已在变更时立即生效，这里直接按当前 filters 重新查询
  const handleSearch = () => {
    const accountIdKeyword = accountIdInput.trim()
    const disableReasonKeyword = disableReasonInput.trim()
    const mergedFilters: AccountFilters = {
      ...filters,
      account_id: accountIdKeyword || null,
      disable_reason: disableReasonKeyword || null,
    }
    setFilters(mergedFilters)
    loadAccounts(1, pagination.pageSize, mergedFilters)
  }
  
  // 检查是否有筛选条件（空字符串视为无效筛选）
  const hasActiveFilters = Object.values(filters).some(v => v !== null && v !== '')

  const handleToggleSelectAllAccounts = () => {
    if (accounts.length === 0) return
    if (allVisibleSelected) {
      setSelectedAccountIds([])
      return
    }
    setSelectedAccountIds(accounts.map(account => account.id))
  }

  const handleToggleSelectAccount = (accountId: string) => {
    setSelectedAccountIds(prev => (
      prev.includes(accountId)
        ? prev.filter(id => id !== accountId)
        : [...prev, accountId]
    ))
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadAccounts()
  }, [_hasHydrated, isAuthenticated, token])

  // 清理扫码检查定时器
  const clearQrCheck = useCallback(() => {
    if (qrCheckIntervalRef.current) {
      clearInterval(qrCheckIntervalRef.current)
      qrCheckIntervalRef.current = null
    }
  }, [])

  // 清理密码登录检查定时器
  const clearPwdCheck = useCallback(() => {
    if (pwdCheckIntervalRef.current) {
      clearInterval(pwdCheckIntervalRef.current)
      pwdCheckIntervalRef.current = null
    }
  }, [])

  // 关闭弹窗时清理
  const closeModal = useCallback(() => {
    clearQrCheck()
    clearPwdCheck()
    setActiveModal(null)
    setQrCodeUrl('')
    setQrSessionId('')
    setQrStatus('loading')
    setQrErrorMessage('')
    setPwdAccount('')
    setPwdPassword('')
    setPwdPasswordVisible(false)
    setPwdLoading(false)
    setPwdSessionId('')
    setPwdStatus('idle')
    setPwdVerificationUrl('')
    setPwdScreenshotPath('')
    setManualAccountId('')
    setManualCookie('')
    setManualLoading(false)
    setEditPasswordVisible(false)
    setAiTimeRangeStart('')
    setAiTimeRangeEnd('')
  }, [clearQrCheck, clearPwdCheck])

  // ==================== 管理员默认密码检查 ====================
  /**
   * 检查管理员是否使用默认密码，如果是则弹窗提示并阻止添加账号
   * 返回 true 表示通过检查（可以继续），false 表示被拦截
   */
  const checkAdminPassword = async (): Promise<boolean> => {
    // 仅管理员需要检查
    if (!user?.is_admin) {
      return true
    }
    try {
      const result = await checkAdminDefaultPassword()
      if (result.success && result.data?.is_default) {
        addToast({
          type: 'warning',
          message: '检测到您仍在使用默认密码，为保障系统安全，请先前往个人设置修改密码后再添加账号',
        })
        return false
      }
      return true
    } catch {
      // 接口异常时不阻止操作
      return true
    }
  }

  // ==================== 扫码登录 ====================
  const startQRCodeLogin = async () => {
    // 管理员默认密码检查
    const passed = await checkAdminPassword()
    if (!passed) return

    setActiveModal('qrcode')
    setQrStatus('loading')
    setQrErrorMessage('')
    try {
      const result = await generateQRLogin()
      if (result.success && result.qr_code_url && result.session_id) {
        setQrCodeUrl(result.qr_code_url)
        setQrSessionId(result.session_id)
        setQrStatus('ready')
        // 开始轮询
        startQrCheck(result.session_id)
      } else {
        setQrStatus('error')
        setQrErrorMessage(result.message || '生成二维码失败')
        addToast({ type: 'error', message: result.message || '生成二维码失败' })
      }
    } catch {
      setQrStatus('error')
      setQrErrorMessage('生成二维码失败')
      addToast({ type: 'error', message: '生成二维码失败' })
    }
  }

  const startQrCheck = (sessionId: string) => {
    clearQrCheck()
    qrCheckIntervalRef.current = setInterval(async () => {
      try {
        const result = await checkQRLoginStatus(sessionId)

        switch (result.status) {
          case 'scanned':
            setQrStatus('scanned')
            break
          case 'processing':
            // 正在处理中，显示已扫描状态
            setQrStatus('scanned')
            break
          case 'success':
          case 'already_processed':
            // 登录成功或已处理完成
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
              closeModal()
              loadAccounts()
            }, 1500)
            break
          case 'expired':
            setQrStatus('expired')
            clearQrCheck()
            break
          case 'failed':
            setQrStatus('failed')
            setQrErrorMessage(result.message || '扫码登录失败')
            clearQrCheck()
            addToast({ type: 'error', message: result.message || '扫码登录失败' })
            break
          case 'cancelled':
            clearQrCheck()
            addToast({ type: 'warning', message: '用户取消登录' })
            closeModal()
            break
          case 'verification_required':
            addToast({ type: 'warning', message: '触发人脸验证，系统无法处理，请使用账号密码或者cookies登录' })
            break
          case 'error':
            setQrStatus('error')
            setQrErrorMessage(result.message || '扫码状态查询失败')
            clearQrCheck()
            break
        }
      } catch {
        // 忽略网络错误，继续轮询
      }
    }, 2000)
  }

  const refreshQRCode = async () => {
    setQrStatus('loading')
    setQrErrorMessage('')
    clearQrCheck()
    try {
      const result = await generateQRLogin()
      if (result.success && result.qr_code_url && result.session_id) {
        setQrCodeUrl(result.qr_code_url)
        setQrSessionId(result.session_id)
        setQrStatus('ready')
        startQrCheck(result.session_id)
      } else {
        setQrStatus('error')
        setQrErrorMessage(result.message || '生成二维码失败')
      }
    } catch {
      setQrStatus('error')
      setQrErrorMessage('生成二维码失败')
    }
  }

  // ==================== 密码登录 ====================
  const startPwdCheck = (sessionId: string) => {
    clearPwdCheck()
    pwdCheckIntervalRef.current = setInterval(async () => {
      try {
        const result = await checkPasswordLoginStatus(sessionId)
        
        switch (result.status) {
          case 'processing':
            setPwdStatus('processing')
            break
          case 'verification_required':
            setPwdStatus('verification_required')
            if (result.verification_url) setPwdVerificationUrl(result.verification_url)
            if (result.screenshot_path) setPwdScreenshotPath(result.screenshot_path)
            break
          case 'success':
            setPwdStatus('success')
            clearPwdCheck()
            addToast({
              type: 'success',
              message: result.is_new_account
                ? `新账号 ${result.account_id} 添加成功`
                : `账号 ${result.account_id} 登录成功`,
            })
            setTimeout(() => {
              closeModal()
              loadAccounts()
            }, 1500)
            break
          case 'failed':
          case 'not_found':
            setPwdStatus('failed')
            clearPwdCheck()
            addToast({ type: 'error', message: result.error || result.message || '登录失败' })
            break
        }
      } catch {
        // 忽略网络错误，继续轮询
      }
    }, 2000)
  }

  const handlePasswordLogin = async (e: FormEvent) => {
    e.preventDefault()
    if (!pwdAccount.trim() || !pwdPassword.trim()) {
      addToast({ type: 'warning', message: '请输入账号和密码' })
      return
    }

    setPwdLoading(true)
    setPwdStatus('processing')
    try {
      const result = await passwordLogin({
        account_id: pwdAccount.trim(),
        account: pwdAccount.trim(),
        password: pwdPassword,
        show_browser: pwdShowBrowser,
      })
      if (result.success && result.session_id) {
        setPwdSessionId(result.session_id)
        addToast({ type: 'info', message: '登录任务已启动，请等待...' })
        // 开始轮询状态
        startPwdCheck(result.session_id)
      } else {
        setPwdStatus('failed')
        addToast({ type: 'error', message: result.message || '登录失败' })
      }
    } catch {
      setPwdStatus('failed')
      addToast({ type: 'error', message: '登录请求失败' })
    } finally {
      setPwdLoading(false)
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
    } catch (error: unknown) {
      // 获取后端返回的错误信息
      const axiosError = error as { response?: { data?: { detail?: string; message?: string } } }
      const errorMessage = axiosError.response?.data?.detail || axiosError.response?.data?.message || '添加账号失败'
      addToast({ type: 'error', message: errorMessage })
    } finally {
      setManualLoading(false)
    }
  }

  const handleToggleEnabled = async (account: AccountDetail) => {
    try {
      const result = await updateAccountStatus(account.id, !account.enabled)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '操作失败' })
        return
      }
      addToast({ type: 'success', message: account.enabled ? '账号已禁用' : '账号已启用' })
      await loadAccounts()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '操作失败') })
    }
  }

  const getBatchFailedMessage = (
    message: string | undefined,
    failedItems: Array<{ account_id: string; message: string }> | undefined,
    fallback: string,
  ) => {
    const failedMessage = failedItems
      ?.slice(0, 3)
      .map(item => `${item.account_id}：${item.message}`)
      .join('；')
    return failedMessage ? `${message || fallback}；${failedMessage}` : message || fallback
  }

  const handleBatchToggleEnabled = async (enabled: boolean) => {
    if (selectedCount === 0) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }

    const targetAccountIds = accounts
      .filter(account => selectedAccountIds.includes(account.id) && account.enabled !== enabled)
      .map(account => account.id)

    if (targetAccountIds.length === 0) {
      addToast({ type: 'warning', message: enabled ? '所选账号已全部启用' : '所选账号已全部禁用' })
      return
    }

    setBatchAction(enabled ? 'enable' : 'disable')
    try {
      const result = await updateAccountsStatusBatch(targetAccountIds, enabled)
      if (result.success) {
        addToast({ type: 'success', message: result.message || (enabled ? '批量启动成功' : '批量禁用成功') })
      } else {
        addToast({
          type: 'error',
          message: getBatchFailedMessage(result.message, result.data?.failed_items, enabled ? '批量启动失败' : '批量禁用失败'),
        })
      }
      setSelectedAccountIds([])
      await loadAccounts()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, enabled ? '批量启动失败' : '批量禁用失败') })
    } finally {
      setBatchAction(null)
    }
  }

  const handleBatchCloseNotice = async () => {
    if (selectedCount === 0) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }

    setBatchAction('close-notice')
    try {
      const result = await closeAccountsNoticeBatch(selectedAccountIds)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '批量关闭通知成功' })
      } else {
        addToast({
          type: 'error',
          message: getBatchFailedMessage(result.message, result.data?.failed_items, '批量关闭通知失败'),
        })
      }
      setSelectedAccountIds([])
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '批量关闭通知失败') })
    } finally {
      setBatchAction(null)
    }
  }

  const handleBatchClearTokenCache = async () => {
    if (selectedCount === 0) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }

    setBatchAction('clear-token')
    try {
      const result = await clearTokenCacheBatch(selectedAccountIds)
      if (result.success) {
        addToast({ type: 'success', message: result.message || '批量清除Token缓存并重启成功' })
      } else {
        addToast({
          type: 'error',
          message: getBatchFailedMessage(result.message, result.data?.failed_items, '批量清除Token缓存失败'),
        })
      }
      setSelectedAccountIds([])
      await loadAccounts()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '批量清除Token缓存失败') })
    } finally {
      setBatchAction(null)
    }
  }

  const handleBatchRenewLogin = async () => {
    if (selectedCount === 0) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }

    setBatchAction('renew-login')
    try {
      const { renewAccountLoginBatch } = await import('@/api/accounts')
      const result = await renewAccountLoginBatch(selectedAccountIds)
      if (result.success) {
        const data = result.data as { success_count?: number; failed_count?: number; results?: Array<{ account_name?: string; success: boolean; message: string }> } | undefined
        const failedCount = data?.failed_count || 0
        if (failedCount > 0) {
          const failedMessages = (data?.results || []).filter(r => !r.success).map(r => `${r.account_name || '未知'}: ${r.message}`).join('；')
          addToast({ type: 'warning', message: `${result.message}${failedMessages ? '。' + failedMessages : ''}` })
        } else {
          addToast({ type: 'success', message: result.message || '批量账号续期成功' })
        }
      } else {
        addToast({ type: 'error', message: result.message || '批量账号续期失败' })
      }
      setSelectedAccountIds([])
      await loadAccounts()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '批量账号续期失败') })
    } finally {
      setBatchAction(null)
    }
  }

  const handleBatchRate = async () => {
    if (selectedCount === 0) {
      addToast({ type: 'warning', message: '请先选择账号' })
      return
    }

    setBatchAction('batch-rate')
    try {
      const { batchRateOrders } = await import('@/api/autoRate')
      const result = await batchRateOrders(selectedAccountIds)
      if (result.success) {
        const data = result.data
        if (data) {
          const details = data.details || []
          const failedAccounts = details.filter(d => !d.success)
          if (failedAccounts.length > 0) {
            const failedMsg = failedAccounts.slice(0, 3).map(d => `${d.account_id}：${d.message}`).join('；')
            addToast({ type: 'warning', message: `${result.message}。${failedMsg}` })
          } else {
            addToast({ type: 'success', message: result.message || '批量补评价完成' })
          }
        } else {
          addToast({ type: 'success', message: result.message || '批量补评价完成' })
        }
      } else {
        addToast({ type: 'error', message: result.message || '批量补评价失败' })
      }
      setSelectedAccountIds([])
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '批量补评价失败') })
    } finally {
      setBatchAction(null)
    }
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const blob = await exportAccountsExcel({
        account_ids: selectedCount > 0 ? selectedAccountIds : undefined,
        status: selectedCount > 0 ? null : filters.status,
        account_id: selectedCount > 0 ? null : filters.account_id,
        has_password: selectedCount > 0 ? null : filters.has_password,
      })
      // 触发下载
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `账号导出_${new Date().toISOString().slice(0, 10)}.xlsx`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
      addToast({ type: 'success', message: selectedCount > 0 ? `已导出 ${selectedCount} 个账号` : '已导出全部账号' })
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '导出失败') })
    } finally {
      setExporting(false)
    }
  }

  const handleImport = async (enableAll: boolean) => {
    if (!importFile) {
      addToast({ type: 'warning', message: '请先选择文件' })
      return
    }
    setImporting(true)
    try {
      const result = await importAccountsExcel(importFile, enableAll)
      if (result.success) {
        addToast({ type: 'success', message: result.message })
        if (result.data?.errors && result.data.errors.length > 0) {
          addToast({ type: 'warning', message: `部分数据导入异常：${result.data.errors.slice(0, 3).join('；')}` })
        }
        setShowImportModal(false)
        setImportFile(null)
        await loadAccounts()
      } else {
        addToast({ type: 'error', message: result.message || '导入失败' })
      }
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '导入失败') })
    } finally {
      setImporting(false)
    }
  }

  const handleDelete = async (id: string) => {
    setDeleting(true)
    try {
      await deleteAccount(id)
      addToast({ type: 'success', message: '删除成功' })
      setDeleteAccountConfirm({ open: false, id: null })
      loadAccounts()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setDeleting(false)
    }
  }

  // ==================== 编辑账号 ====================
  const openEditModal = (account: AccountDetail) => {
    setEditingAccount(account)
    setEditNote(account.note || '')
    setEditCookie(account.cookie || '')
    setEditAutoConfirm(account.auto_confirm || false)
    setEditPauseDuration(account.pause_duration || 0)
    setEditUsername(account.username || '')
    setEditPassword(account.login_password || '')
    setEditShowBrowser(account.show_browser || false)
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

      // 更新暂停时间
      if (editPauseDuration !== (editingAccount.pause_duration || 0)) {
        promises.push(updateAccountPauseDuration(editingAccount.id, editPauseDuration))
      }

      // 更新登录信息（用户名、密码、显示浏览器）
      const loginInfoChanged = 
        editUsername !== (editingAccount.username || '') ||
        editPassword !== (editingAccount.login_password || '') ||
        editShowBrowser !== (editingAccount.show_browser || false)
      
      if (loginInfoChanged) {
        promises.push(updateAccountLoginInfo(editingAccount.id, {
          username: editUsername,
          login_password: editPassword,
          show_browser: editShowBrowser,
        }))
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
    setDefaultReplyImage('')
    setDefaultReplyEnabled(false)
    setDefaultReplyOnce(false)
    setDefaultReplyType('text')
    setDefaultReplyApiUrl('')
    setDefaultReplyApiTimeout(80)
    setActiveModal('default-reply')
    
    // 加载当前默认回复
    try {
      const result = await getDefaultReply(account.id)
      setDefaultReplyContent(result.default_reply || '')
      setDefaultReplyImage(result.reply_image || '')
      setDefaultReplyEnabled(result.enabled || false)
      setDefaultReplyOnce(result.reply_once || false)
      setDefaultReplyType((result.reply_type as 'text' | 'api') || 'text')
      setDefaultReplyApiUrl(result.api_url || '')
      setDefaultReplyApiTimeout(result.api_timeout || 80)
    } catch {
      // ignore
    }
  }

  const handleSaveDefaultReply = async () => {
    if (!defaultReplyAccount) return
    if (defaultReplyType === 'api' && !defaultReplyApiUrl.trim()) {
      addToast({ type: 'warning', message: '请输入 API 地址' })
      return
    }
    
    try {
      setDefaultReplySaving(true)
      const result = await updateDefaultReply(
        defaultReplyAccount.id,
        defaultReplyContent,
        defaultReplyEnabled,
        defaultReplyOnce,
        defaultReplyImage,
        defaultReplyType,
        defaultReplyApiUrl,
        defaultReplyApiTimeout
      )
      if (result.success) {
        addToast({ type: 'success', message: '默认回复已保存' })
        closeModal()
        loadAccounts() // 刷新账号列表
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch (error) {
      console.error('保存默认回复失败:', error)
      addToast({ type: 'error', message: '保存失败，请检查网络连接' })
    } finally {
      setDefaultReplySaving(false)
    }
  }

  // 上传默认回复图片
  const handleDefaultReplyImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !defaultReplyAccount) return
    
    // 验证文件类型
    if (!file.type.startsWith('image/')) {
      addToast({ type: 'error', message: '只支持上传图片文件' })
      return
    }
    
    // 验证文件大小（最大5MB）
    if (file.size > 5 * 1024 * 1024) {
      addToast({ type: 'error', message: '图片大小不能超过5MB' })
      return
    }
    
    try {
      setDefaultReplyImageUploading(true)
      const result = await uploadDefaultReplyImage(defaultReplyAccount.id, file)
      if (result.success && result.image_url) {
        setDefaultReplyImage(result.image_url)
        addToast({ type: 'success', message: '图片上传成功' })
      } else {
        addToast({ type: 'error', message: result.message || '图片上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '图片上传失败' })
    } finally {
      setDefaultReplyImageUploading(false)
      // 清空input，允许重复上传同一文件
      if (defaultReplyImageInputRef.current) {
        defaultReplyImageInputRef.current.value = ''
      }
    }
  }

  // ==================== AI回复开关 ====================
  const handleToggleAI = async (account: AccountWithKeywordCount) => {
    const newEnabled = !account.aiEnabled
    try {
      if (newEnabled) {
        const settings = await getAIReplySettings(account.id)
        const missingItems = getAIConfigMissingItems({
          provider_type: settings.provider_type,
          base_url: settings.base_url,
          api_key: settings.api_key,
          model_name: settings.model_name,
        })
        if (missingItems.length > 0) {
          addToast({ type: 'warning', message: getAIConfigIncompleteMessage(missingItems) })
          return
        }
      }
      const result = await updateAIReplySettings(account.id, { ai_enabled: newEnabled })
      if (!result.success) {
        addToast({ type: 'warning', message: result.message || 'AI配置未填写完整，无法开启AI回复' })
        return
      }
      setAccounts(prev => prev.map(a =>
        a.id === account.id ? { ...a, aiEnabled: newEnabled } : a,
      ))
      addToast({ type: 'success', message: `AI回复已${newEnabled ? '开启' : '关闭'}` })
      await loadAccounts()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '操作失败') })
    }
  }

  // ==================== 定时补发货开关 ====================
  const handleToggleScheduledRedelivery = async (account: AccountWithKeywordCount) => {
    const newEnabled = !account.scheduled_redelivery
    try {
      await updateAccountScheduledRedelivery(account.id, newEnabled)
      setAccounts(prev => prev.map(a =>
        a.id === account.id ? { ...a, scheduled_redelivery: newEnabled } : a,
      ))
      addToast({ type: 'success', message: `定时补发货已${newEnabled ? '开启' : '关闭'}` })
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  // ==================== 定时补评价开关 ====================
  const handleToggleScheduledRate = async (account: AccountWithKeywordCount) => {
    const newEnabled = !account.scheduled_rate
    try {
      await updateAccountScheduledRate(account.id, newEnabled)
      setAccounts(prev => prev.map(a =>
        a.id === account.id ? { ...a, scheduled_rate: newEnabled } : a,
      ))
      addToast({ type: 'success', message: `定时补评价已${newEnabled ? '开启' : '关闭'}` })
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  // ==================== 商品自动擦亮开关 ====================
  const handleToggleAutoPolish = async (account: AccountWithKeywordCount) => {
    const newEnabled = !account.auto_polish
    try {
      await updateAccountAutoPolish(account.id, newEnabled)
      setAccounts(prev => prev.map(a =>
        a.id === account.id ? { ...a, auto_polish: newEnabled } : a,
      ))
      addToast({ type: 'success', message: `商品自动擦亮已${newEnabled ? '开启' : '关闭'}` })
    } catch (error) {
      console.error('更新商品自动擦亮开关失败:', error)
      addToast({ type: 'error', message: '更新商品自动擦亮开关失败' })
    }
  }

  // ==================== 发货成功再发卡券开关 ====================
  const handleToggleConfirmBeforeSend = async (account: AccountWithKeywordCount) => {
    const newEnabled = !account.confirm_before_send
    try {
      await updateAccountConfirmBeforeSend(account.id, newEnabled)
      setAccounts(prev => prev.map(a =>
        a.id === account.id ? { ...a, confirm_before_send: newEnabled, ...(newEnabled ? { send_before_confirm: false } : {}) } : a,
      ))
      addToast({ type: 'success', message: `发货成功再发卡券已${newEnabled ? '开启' : '关闭'}` })
    } catch {
      addToast({ type: 'error', message: '更新发货成功再发卡券开关失败' })
    }
  }

  // ==================== 卡券发送成功再确认发货开关 ====================
  const handleToggleSendBeforeConfirm = async (account: AccountWithKeywordCount) => {
    const newEnabled = !account.send_before_confirm
    try {
      await updateAccountSendBeforeConfirm(account.id, newEnabled)
      setAccounts(prev => prev.map(a =>
        a.id === account.id ? { ...a, send_before_confirm: newEnabled, ...(newEnabled ? { confirm_before_send: false } : {}) } : a,
      ))
      addToast({ type: 'success', message: `卡券发送成功再确认发货已${newEnabled ? '开启' : '关闭'}` })
    } catch {
      addToast({ type: 'error', message: '更新卡券发送成功再确认发货开关失败' })
    }
  }

  // ==================== 自动求小红花开关 ====================
  const handleToggleAutoRedFlower = async (account: AccountWithKeywordCount) => {
    const newEnabled = !account.auto_red_flower
    try {
      const result = await updateAccountAutoRedFlower(account.id, newEnabled)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '更新自动求小红花开关失败' })
        return
      }
      setAccounts(prev => prev.map(a =>
        a.id === account.id ? { ...a, auto_red_flower: newEnabled } : a,
      ))
      addToast({ type: 'success', message: `自动求小红花已${newEnabled ? '开启' : '关闭'}` })
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '更新自动求小红花开关失败') })
    }
  }

  // ==================== 已下单用户禁止AI回复开关 ====================
  const handleToggleAiReplyBlockOrderedUsers = async (account: AccountWithKeywordCount) => {
    const newEnabled = !account.ai_reply_block_ordered_users
    try {
      const result = await updateAccountAiReplyBlockOrderedUsers(account.id, newEnabled)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || '更新已下单用户禁止AI回复开关失败' })
        return
      }
      setAccounts(prev => prev.map(a =>
        a.id === account.id ? { ...a, ai_reply_block_ordered_users: newEnabled } : a,
      ))
      addToast({ type: 'success', message: `已下单用户禁止AI回复已${newEnabled ? '开启' : '关闭'}` })
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '更新已下单用户禁止AI回复开关失败') })
    }
  }

  // ==================== 自动确认发货开关 ====================
  const handleToggleAutoConfirm = async (account: AccountWithKeywordCount) => {
    const newEnabled = !account.auto_confirm
    try {
      await updateAccountAutoConfirm(account.id, newEnabled)
      setAccounts(prev => prev.map(a =>
        a.id === account.id ? { ...a, auto_confirm: newEnabled } : a,
      ))
      addToast({ type: 'success', message: `自动确认发货已${newEnabled ? '开启' : '关闭'}` })
    } catch {
      addToast({ type: 'error', message: '操作失败' })
    }
  }

  // ==================== AI设置管理 ====================
  const openAISettings = async (account: AccountWithKeywordCount) => {
    setAiSettingsAccount(account)
    setActiveModal('ai-settings')
    setAiSettingsLoading(true)
    setAiModelOptions([])
    try {
      const settings = await getAIReplySettings(account.id)
      const providerType = (settings.provider_type as AIProviderType) || 'openai_compatible'
      setAiProviderType(providerType)
      setAiEnabled(settings.ai_enabled ?? settings.enabled ?? false)
      setAiApiUrl(settings.base_url ?? AI_PROVIDER_DEFAULT_BASE_URLS[providerType])
      setAiApiKey(settings.api_key ?? '')
      setAiModelName(settings.model_name ?? 'qwen-plus')
      setAiMaxDiscountPercent(settings.max_discount_percent ?? 10)
      setAiMaxDiscountAmount(settings.max_discount_amount ?? 100)
      setAiMaxBargainRounds(settings.max_bargain_rounds ?? 3)
      setAiCustomPrompts(settings.custom_prompts ?? '')
      const formatTime = (t: string | undefined | null) => {
        if (!t) return ''
        const parts = t.split(':')
        return parts.length >= 2 ? `${parts[0].padStart(2, '0')}:${parts[1].padStart(2, '0')}` : t
      }
      setAiTimeRangeStart(formatTime(settings.ai_time_range_start))
      setAiTimeRangeEnd(formatTime(settings.ai_time_range_end))
    } catch (error) {
      const detail = getApiErrorMessage(error, '加载AI设置失败')
      addToast({ type: 'error', message: detail })
    } finally {
      setAiSettingsLoading(false)
    }
  }

  // 切换AI服务商类型时，自动联动默认API地址（如果当前地址为空或仍是其他服务商默认地址）
  const handleAIProviderChange = (next: AIProviderType) => {
    setAiProviderType(next)
    setAiModelOptions([])
    const isPreviousDefault = !aiApiUrl
      || Object.values(AI_PROVIDER_DEFAULT_BASE_URLS).includes(aiApiUrl)
    if (isPreviousDefault) {
      setAiApiUrl(AI_PROVIDER_DEFAULT_BASE_URLS[next])
    }
  }

  const getCurrentAIConfigMissingItems = () => getAIConfigMissingItems({
    provider_type: aiProviderType,
    base_url: aiApiUrl,
    api_key: aiApiKey,
    model_name: aiModelName,
  })

  const handleToggleAIEnabledInModal = () => {
    if (aiEnabled) {
      setAiEnabled(false)
      return
    }
    const missingItems = getCurrentAIConfigMissingItems()
    if (missingItems.length > 0) {
      addToast({ type: 'warning', message: getAIConfigIncompleteMessage(missingItems) })
      return
    }
    setAiEnabled(true)
  }

  // 手动获取模型列表
  const handleFetchAIModels = async () => {
    if (!aiApiKey) {
      addToast({ type: 'warning', message: '请先填写API Key' })
      return
    }
    if (aiProviderType === 'dashscope_app') {
      addToast({ type: 'warning', message: 'DashScope应用API不支持自动获取模型列表，请手动填写模型名称' })
      return
    }
    try {
      setAiModelsLoading(true)
      const result = await fetchAIModels({
        provider_type: aiProviderType,
        base_url: aiApiUrl || AI_PROVIDER_DEFAULT_BASE_URLS[aiProviderType],
        api_key: aiApiKey,
      })
      const models = result.data?.models ?? []
      // 不论成功失败，都按返回结果设置（失败时为空数组，前端自动回退为普通文本框输入）
      setAiModelOptions(models)
      setShowAiModelDropdown(false)
      if (result.success && models.length > 0) {
        addToast({ type: 'success', message: result.message || `获取到 ${models.length} 个模型` })
        if (!models.some(m => m.id === aiModelName)) {
          setAiModelName(models[0].id)
        }
      } else {
        // 失败或空列表：提示用户改用手动输入
        addToast({
          type: 'warning',
          message: result.message || '未获取到模型列表，请直接在文本框输入模型名称',
        })
      }
    } catch (error) {
      // 异常时同样清空选项，让 UI 回到文本框输入模式
      setAiModelOptions([])
      setShowAiModelDropdown(false)
      const detail = getApiErrorMessage(error, '获取模型列表失败，请直接在文本框输入模型名称')
      addToast({ type: 'error', message: detail })
    } finally {
      setAiModelsLoading(false)
    }
  }

  const handleSaveAISettings = async () => {
    if (!aiSettingsAccount) return
    if (aiEnabled) {
      const missingItems = getCurrentAIConfigMissingItems()
      if (missingItems.length > 0) {
        addToast({ type: 'warning', message: getAIConfigIncompleteMessage(missingItems) })
        return
      }
    }
    try {
      setAiSettingsSaving(true)
      const result = await updateAIReplySettings(aiSettingsAccount.id, {
        ai_enabled: aiEnabled,
        provider_type: aiProviderType,
        base_url: aiApiUrl,
        api_key: aiApiKey,
        model_name: aiModelName,
        max_discount_percent: aiMaxDiscountPercent,
        max_discount_amount: aiMaxDiscountAmount,
        max_bargain_rounds: aiMaxBargainRounds,
        custom_prompts: aiCustomPrompts,
        ai_time_range_start: aiTimeRangeStart,
        ai_time_range_end: aiTimeRangeEnd,
      })
      if (!result.success) {
        addToast({ type: 'warning', message: result.message || 'AI配置未填写完整，无法开启AI回复' })
        return
      }
      // 更新本地状态
      setAccounts(prev => prev.map(a =>
        a.id === aiSettingsAccount.id ? { ...a, aiEnabled } : a,
      ))
      addToast({ type: 'success', message: 'AI设置已保存' })
      closeModal()
      await loadAccounts()
    } catch (error) {
      const detail = getApiErrorMessage(error, '保存失败')
      addToast({ type: 'error', message: detail })
    } finally {
      setAiSettingsSaving(false)
    }
  }

  // 测试AI连接
  const handleTestAI = async () => {
    if (!aiSettingsAccount) return
    const missingItems = getCurrentAIConfigMissingItems()
    if (missingItems.length > 0) {
      addToast({ type: 'warning', message: getAIConfigIncompleteMessage(missingItems) })
      return
    }
    // 先保存设置再测试
    try {
      setAiTesting(true)
      const saveResult = await updateAIReplySettings(aiSettingsAccount.id, {
        ai_enabled: aiEnabled,
        provider_type: aiProviderType,
        base_url: aiApiUrl,
        api_key: aiApiKey,
        model_name: aiModelName,
        max_discount_percent: aiMaxDiscountPercent,
        max_discount_amount: aiMaxDiscountAmount,
        max_bargain_rounds: aiMaxBargainRounds,
        custom_prompts: aiCustomPrompts,
        ai_time_range_start: aiTimeRangeStart,
        ai_time_range_end: aiTimeRangeEnd,
      })
      if (!saveResult.success) {
        addToast({ type: 'warning', message: saveResult.message || 'AI配置未填写完整，无法测试AI连接' })
        return
      }
      const result = await testAIConnection(aiSettingsAccount.id)
      if (result.success) {
        addToast({ type: 'success', message: result.message || 'AI连接测试成功' })
      } else {
        addToast({ type: 'error', message: result.message || 'AI连接测试失败' })
      }
    } catch (error) {
      const detail = getApiErrorMessage(error, 'AI连接测试失败')
      addToast({ type: 'error', message: detail })
    } finally {
      setAiTesting(false)
    }
  }

  // ==================== 代理设置管理 ====================
  const openProxySettings = async (account: AccountWithKeywordCount) => {
    setProxySettingsAccount(account)
    setActiveModal('proxy-settings')
    setProxySettingsLoading(true)
    // 重置状态
    setProxyType('none')
    setProxyHost('')
    setProxyPort('')
    setProxyUser('')
    setProxyPass('')
    
    try {
      const result = await getProxyConfig(account.id)
      if (result.success && result.data) {
        setProxyType(result.data.proxy_type || 'none')
        setProxyHost(result.data.proxy_host || '')
        setProxyPort(result.data.proxy_port || '')
        setProxyUser(result.data.proxy_user || '')
        setProxyPass(result.data.proxy_pass || '')
      }
    } catch {
      addToast({ type: 'error', message: '加载代理配置失败' })
    } finally {
      setProxySettingsLoading(false)
    }
  }

  const handleSaveProxySettings = async () => {
    if (!proxySettingsAccount) return
    
    // 验证
    if (proxyType !== 'none') {
      if (!proxyHost.trim()) {
        addToast({ type: 'warning', message: '请输入代理地址' })
        return
      }
      if (!proxyPort || proxyPort <= 0) {
        addToast({ type: 'warning', message: '请输入有效的代理端口' })
        return
      }
    }
    
    try {
      setProxySettingsSaving(true)
      const config: ProxyConfig = {
        proxy_type: proxyType,
        proxy_host: proxyType !== 'none' ? proxyHost.trim() : undefined,
        proxy_port: proxyType !== 'none' ? Number(proxyPort) : undefined,
        proxy_user: proxyType !== 'none' && proxyUser.trim() ? proxyUser.trim() : undefined,
        proxy_pass: proxyType !== 'none' && proxyPass ? proxyPass : undefined,
      }
      const result = await updateProxyConfig(proxySettingsAccount.id, config)
      if (result.success) {
        addToast({ type: 'success', message: '代理配置已保存' })
        closeModal()
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch {
      addToast({ type: 'error', message: '保存代理配置失败' })
    } finally {
      setProxySettingsSaving(false)
    }
  }

  // ==================== 消息等待时间设置 ====================
  const openMessageExpireTimeModal = (account: AccountWithKeywordCount) => {
    setMessageExpireTimeAccount(account)
    setMessageExpireTime(account.message_expire_time || 3600)
    setActiveModal('message-expire-time')
  }

  // ==================== 禁止发货设置 ====================
  const openDeliveryDisabledModal = (account: AccountWithKeywordCount) => {
    setDeliveryDisabledAccount(account)
    setActiveModal('delivery-disabled')
  }

  const handleSaveMessageExpireTime = async () => {
    if (!messageExpireTimeAccount) return
    
    try {
      setMessageExpireTimeSaving(true)
      const result = await updateAccountMessageExpireTime(messageExpireTimeAccount.id, messageExpireTime)
      if (result.success) {
        addToast({ type: 'success', message: '相同消息等待时间已保存' })
        closeModal()
        loadAccounts()
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setMessageExpireTimeSaving(false)
    }
  }

  // ==================== 自动回复延迟设置 ====================
  const openReplyDelayModal = (account: AccountWithKeywordCount) => {
    setReplyDelayAccount(account)
    setReplyDelay(account.reply_delay_seconds || 0)
    setActiveModal('reply-delay')
  }

  const handleSaveReplyDelay = async () => {
    if (!replyDelayAccount) return

    try {
      setReplyDelaySaving(true)
      const result = await updateAccountReplyDelay(replyDelayAccount.id, replyDelay)
      if (result.success) {
        addToast({ type: 'success', message: '自动回复延迟时间已保存' })
        closeModal()
        loadAccounts()
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setReplyDelaySaving(false)
    }
  }

  // ==================== 人脸验证 ====================
  const openFaceVerificationModal = async (account: AccountWithKeywordCount) => {
    setFaceVerificationAccount(account)
    setFaceVerificationScreenshot(null)
    setActiveModal('face-verification')
    setFaceVerificationLoading(true)
    
    try {
      const result = await getFaceVerificationScreenshot(account.id)
      if (result.success && result.screenshot) {
        setFaceVerificationScreenshot(result.screenshot)
      } else {
        addToast({ type: 'warning', message: result.message || '未找到验证截图' })
      }
    } catch {
      addToast({ type: 'error', message: '获取验证截图失败' })
    } finally {
      setFaceVerificationLoading(false)
    }
  }

  const handleDeleteFaceVerification = async () => {
    if (!faceVerificationAccount) return
    
    setDeleting(true)
    try {
      const result = await deleteFaceVerificationScreenshot(faceVerificationAccount.id)
      if (result.success) {
        addToast({ type: 'success', message: '验证截图已删除' })
        setDeleteFaceConfirm(false)
        setFaceVerificationScreenshot(null)
      } else {
        addToast({ type: 'error', message: result.message || '删除失败' })
      }
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    } finally {
      setDeleting(false)
    }
  }

  // ==================== 确认收货消息 ====================
  const openConfirmReceiptModal = async (account: AccountWithKeywordCount) => {
    setConfirmReceiptAccount(account)
    setConfirmReceiptEnabled(false)
    setConfirmReceiptContent('')
    setConfirmReceiptImage('')
    setActiveModal('confirm-receipt')
    
    try {
      const result = await getConfirmReceiptMessage(account.id)
      setConfirmReceiptEnabled(result.enabled || false)
      setConfirmReceiptContent(result.message_content || '')
      setConfirmReceiptImage(result.message_image || '')
    } catch {
      // 忽略错误，使用默认值
    }
  }

  const handleSaveConfirmReceipt = async () => {
    if (!confirmReceiptAccount) return
    
    try {
      setConfirmReceiptSaving(true)
      const result = await updateConfirmReceiptMessage(confirmReceiptAccount.id, {
        enabled: confirmReceiptEnabled,
        message_content: confirmReceiptContent,
        message_image: confirmReceiptImage,
      })
      if (result.success) {
        addToast({ type: 'success', message: '确认收货消息已保存' })
        closeModal()
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setConfirmReceiptSaving(false)
    }
  }

  const handleConfirmReceiptImageUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file || !confirmReceiptAccount) return
    
    if (!file.type.startsWith('image/')) {
      addToast({ type: 'error', message: '只支持上传图片文件' })
      return
    }
    
    if (file.size > 5 * 1024 * 1024) {
      addToast({ type: 'error', message: '图片大小不能超过5MB' })
      return
    }
    
    try {
      setConfirmReceiptImageUploading(true)
      const result = await uploadConfirmReceiptImage(confirmReceiptAccount.id, file)
      if (result.success && result.image_url) {
        setConfirmReceiptImage(result.image_url)
        addToast({ type: 'success', message: '图片上传成功' })
      } else {
        addToast({ type: 'error', message: result.message || '图片上传失败' })
      }
    } catch {
      addToast({ type: 'error', message: '图片上传失败' })
    } finally {
      setConfirmReceiptImageUploading(false)
      if (confirmReceiptImageInputRef.current) {
        confirmReceiptImageInputRef.current.value = ''
      }
    }
  }

  // ==================== 自动评价配置 ====================
  const openAutoRateModal = async (account: AccountWithKeywordCount) => {
    setAutoRateAccount(account)
    setAutoRateEnabled(false)
    setAutoRateType('text')
    setAutoRateTextContent('不错的买家')
    setAutoRateApiUrl('')
    setActiveModal('auto-rate')
    
    try {
      const result = await getAutoRateConfig(account.id)
      if (result.success && result.data) {
        setAutoRateEnabled(result.data.enabled || false)
        setAutoRateType(result.data.rate_type || 'text')
        setAutoRateTextContent(result.data.text_content || '不错的买家')
        setAutoRateApiUrl(result.data.api_url || '')
      }
    } catch {
      // 忽略错误，使用默认值
    }
  }

  const handleSaveAutoRate = async () => {
    if (!autoRateAccount) return
    
    // 验证
    if (autoRateEnabled) {
      if (autoRateType === 'text' && !autoRateTextContent.trim()) {
        addToast({ type: 'warning', message: '请填写评价内容' })
        return
      }
      if (autoRateType === 'api' && !autoRateApiUrl.trim()) {
        addToast({ type: 'warning', message: '请填写API地址' })
        return
      }
    }
    
    try {
      setAutoRateSaving(true)
      const result = await updateAutoRateConfig(autoRateAccount.id, {
        enabled: autoRateEnabled,
        rate_type: autoRateType,
        text_content: autoRateTextContent,
        api_url: autoRateApiUrl,
      })
      if (result.success) {
        addToast({ type: 'success', message: '自动评价配置已保存' })
        closeModal()
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch {
      addToast({ type: 'error', message: '保存失败' })
    } finally {
      setAutoRateSaving(false)
    }
  }

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      clearQrCheck()
      clearPwdCheck()
    }
  }, [clearQrCheck, clearPwdCheck])

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="page-header flex-between">
        <div>
          <h1 className="page-title">账号管理</h1>
          <p className="page-description">管理闲鱼账号Cookie信息</p>
        </div>
        <button onClick={() => loadAccounts()} className="btn-ios-secondary">
          <RefreshCw className="w-4 h-4" />
          刷新
        </button>
      </div>

      {/* Add Account Card */}
      <div className="vben-card">
        <div className="vben-card-header">
          <h2 className="vben-card-title ">
            <Plus className="w-4 h-4" />
            添加新账号
            <span className="ml-2 text-xs font-normal text-slate-500 dark:text-slate-400">
              获取Cookie工具地址：
              <a
                href="https://github.com/zhinianboke/packet-capture-tool"
                target="_blank"
                rel="noopener noreferrer"
                className="text-blue-600 dark:text-blue-400 hover:underline break-all"
              >
                https://github.com/zhinianboke/packet-capture-tool
              </a>
            </span>
          </h2>
        </div>
        <div className="vben-card-body">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
            {/* 扫码登录 */}
            <button
              onClick={startQRCodeLogin}
              className="flex items-center gap-3 p-4 rounded-md border border-blue-200 dark:border-blue-800 
                         bg-blue-50 dark:bg-blue-900/30 hover:bg-blue-100 dark:hover:bg-blue-900/50 transition-colors text-left"
            >
              <div className="w-10 h-10 rounded-lg bg-blue-600 flex items-center justify-center flex-shrink-0">
                <QrCode className="w-4 h-4 text-white" />
              </div>
              <div>
                <p className="font-medium text-slate-900 dark:text-slate-100 text-sm">扫码登录</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">推荐方式</p>
              </div>
            </button>

            {!isExeMode && (
              <button
                onClick={async () => {
                  const passed = await checkAdminPassword()
                  if (!passed) return
                  navigate('/accounts/shared-scan')
                }}
                className="flex items-center gap-3 p-4 rounded-md border border-emerald-200 dark:border-emerald-800 
                           bg-emerald-50 dark:bg-emerald-900/30 hover:bg-emerald-100 dark:hover:bg-emerald-900/50 transition-colors text-left"
              >
                <div className="w-10 h-10 rounded-lg bg-emerald-600 flex items-center justify-center flex-shrink-0">
                  <Globe className="w-4 h-4 text-white" />
                </div>
                <div>
                  <p className="font-medium text-slate-900 dark:text-slate-100 text-sm">兼职登录</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">在当前界面打开兼职登录页面</p>
                </div>
              </button>
            )}

            {/* 账号密码登录 */}
            <button
              onClick={async () => {
                const passed = await checkAdminPassword()
                if (!passed) return
                setActiveModal('password')
              }}
              className="flex items-center gap-3 p-4 rounded-md border border-slate-200 dark:border-slate-700 
                         hover:border-blue-300 dark:hover:border-blue-700 hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors text-left"
            >
              <div className="w-10 h-10 rounded-lg bg-slate-100 dark:bg-slate-700 flex items-center justify-center flex-shrink-0">
                <Key className="w-4 h-4 text-slate-600 dark:text-slate-300" />
              </div>
              <div>
                <p className="font-medium text-slate-900 dark:text-slate-100 text-sm">账号密码</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">使用账号和密码</p>
              </div>
            </button>

            {/* 手动输入 */}
            <button
              onClick={async () => {
                const passed = await checkAdminPassword()
                if (!passed) return
                setActiveModal('manual')
              }}
              className="flex items-center gap-3 p-4 rounded-md border border-slate-200 dark:border-slate-700 
                         hover:border-blue-300 dark:hover:border-blue-700 hover:bg-blue-50 dark:hover:bg-blue-900/30 transition-colors text-left"
            >
              <div className="w-10 h-10 rounded-lg bg-slate-100 dark:bg-slate-700 flex items-center justify-center flex-shrink-0">
                <Edit2 className="w-4 h-4 text-slate-600 dark:text-slate-300" />
              </div>
              <div>
                <p className="font-medium text-slate-900 dark:text-slate-100 text-sm">手动输入</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">手动输入Cookie</p>
              </div>
            </button>
          </div>
        </div>
      </div>

      {/* Accounts List */}
      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 280px)', minHeight: '400px' }}>
        <div className="vben-card-header flex-shrink-0">
          <div className="flex items-center gap-2">
            <h2 className="vben-card-title">账号列表</h2>
            <span className="badge-primary">{pagination.total} 个账号</span>
          </div>
          <div className="flex items-center gap-2 flex-wrap justify-end">
            {selectedCount > 0 && (
              <span className="text-sm text-slate-500 dark:text-slate-400">已选择 {selectedCount} 个账号</span>
            )}
            <button
              onClick={() => handleBatchToggleEnabled(true)}
              disabled={selectedCount === 0 || batchOperating}
              className="btn-ios-secondary btn-sm disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {batchAction === 'enable' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Power className="w-4 h-4" />}
              批量启动
            </button>
            <button
              onClick={() => handleBatchToggleEnabled(false)}
              disabled={selectedCount === 0 || batchOperating}
              className="btn-ios-secondary btn-sm text-amber-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {batchAction === 'disable' ? <Loader2 className="w-4 h-4 animate-spin" /> : <PowerOff className="w-4 h-4" />}
              批量禁用
            </button>
            <button
              onClick={handleBatchCloseNotice}
              disabled={selectedCount === 0 || batchOperating}
              className="btn-ios-secondary btn-sm text-sky-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {batchAction === 'close-notice' ? <Loader2 className="w-4 h-4 animate-spin" /> : <MessageSquare className="w-4 h-4" />}
              关闭通知
            </button>
            <button
              onClick={handleBatchClearTokenCache}
              disabled={selectedCount === 0 || batchOperating}
              className="btn-ios-secondary btn-sm text-orange-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {batchAction === 'clear-token' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Key className="w-4 h-4" />}
              清除Token缓存
            </button>
            <button
              onClick={handleBatchRenewLogin}
              disabled={selectedCount === 0 || batchOperating}
              className="btn-ios-secondary btn-sm text-green-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {batchAction === 'renew-login' ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
              账号续期
            </button>
            <button
              onClick={handleBatchRate}
              disabled={selectedCount === 0 || batchOperating}
              className="btn-ios-secondary btn-sm text-rose-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {batchAction === 'batch-rate' ? <Loader2 className="w-4 h-4 animate-spin" /> : <Star className="w-4 h-4" />}
              订单补评价
            </button>
            <button
              onClick={handleExport}
              disabled={exporting}
              className="btn-ios-secondary btn-sm text-purple-600 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Download className="w-4 h-4" />}
              导出
            </button>
            <button
              onClick={() => setShowImportModal(true)}
              className="btn-ios-secondary btn-sm text-teal-600"
            >
              <Upload className="w-4 h-4" />
              导入
            </button>
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`btn-ios-secondary btn-sm flex items-center gap-1 ${hasActiveFilters ? 'text-blue-600 border-blue-300' : ''}`}
            >
              <Filter className="w-4 h-4" />
              筛选
              {hasActiveFilters && <span className="ml-1 px-1.5 py-0.5 text-xs bg-blue-100 text-blue-600 rounded-full">已启用</span>}
            </button>
            {hasActiveFilters && (
              <button onClick={handleResetFilters} className="btn-ios-secondary btn-sm text-red-500">
                重置
              </button>
            )}
          </div>
        </div>
        
        {/* 筛选区域 */}
        {showFilters && (
          <div className="px-4 py-3 border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3">
              {/* 状态筛选 */}
              <div className="flex flex-col gap-1">
                <label className="text-xs text-gray-500 dark:text-gray-400">状态</label>
                <select
                  value={filters.status || ''}
                  onChange={(e) => handleFilterChange('status', e.target.value || null)}
                  className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">全部</option>
                  <option value="active">启用</option>
                  <option value="inactive">禁用</option>
                </select>
              </div>
              
              {/* AI回复筛选 */}
              <div className="flex flex-col gap-1">
                <label className="text-xs text-gray-500 dark:text-gray-400">AI回复</label>
                <select
                  value={filters.ai_reply === null ? '' : String(filters.ai_reply)}
                  onChange={(e) => handleFilterChange('ai_reply', e.target.value === '' ? null : e.target.value === 'true')}
                  className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">全部</option>
                  <option value="true">开启</option>
                  <option value="false">关闭</option>
                </select>
              </div>
              
              {/* 定时补发货筛选 */}
              <div className="flex flex-col gap-1">
                <label className="text-xs text-gray-500 dark:text-gray-400">定时补发货</label>
                <select
                  value={filters.scheduled_redelivery === null ? '' : String(filters.scheduled_redelivery)}
                  onChange={(e) => handleFilterChange('scheduled_redelivery', e.target.value === '' ? null : e.target.value === 'true')}
                  className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">全部</option>
                  <option value="true">开启</option>
                  <option value="false">关闭</option>
                </select>
              </div>
              
              {/* 定时补评价筛选 */}
              <div className="flex flex-col gap-1">
                <label className="text-xs text-gray-500 dark:text-gray-400">定时补评价</label>
                <select
                  value={filters.scheduled_rate === null ? '' : String(filters.scheduled_rate)}
                  onChange={(e) => handleFilterChange('scheduled_rate', e.target.value === '' ? null : e.target.value === 'true')}
                  className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">全部</option>
                  <option value="true">开启</option>
                  <option value="false">关闭</option>
                </select>
              </div>
              
              {/* 商品擦亮筛选 */}
              <div className="flex flex-col gap-1">
                <label className="text-xs text-gray-500 dark:text-gray-400">商品擦亮</label>
                <select
                  value={filters.auto_polish === null ? '' : String(filters.auto_polish)}
                  onChange={(e) => handleFilterChange('auto_polish', e.target.value === '' ? null : e.target.value === 'true')}
                  className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">全部</option>
                  <option value="true">开启</option>
                  <option value="false">关闭</option>
                </select>
              </div>
              
              {/* 自动确认收货筛选 */}
              <div className="flex flex-col gap-1">
                <label className="text-xs text-gray-500 dark:text-gray-400">自动确认收货</label>
                <select
                  value={filters.auto_confirm === null ? '' : String(filters.auto_confirm)}
                  onChange={(e) => handleFilterChange('auto_confirm', e.target.value === '' ? null : e.target.value === 'true')}
                  className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">全部</option>
                  <option value="true">开启</option>
                  <option value="false">关闭</option>
                </select>
              </div>
              
              {/* 配置密码筛选 */}
              <div className="flex flex-col gap-1">
                <label className="text-xs text-gray-500 dark:text-gray-400">配置密码</label>
                <select
                  value={filters.has_password === null ? '' : String(filters.has_password)}
                  onChange={(e) => handleFilterChange('has_password', e.target.value === '' ? null : e.target.value === 'true')}
                  className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  <option value="">全部</option>
                  <option value="true">已配置</option>
                  <option value="false">未配置</option>
                </select>
              </div>

              {/* 账号ID筛选（模糊搜索，回车/失焦/查询按钮均会提交） */}
              <div className="flex flex-col gap-1 col-span-2">
                <label className="text-xs text-gray-500 dark:text-gray-400">账号ID</label>
                <input
                  type="text"
                  value={accountIdInput}
                  maxLength={255}
                  onChange={(e) => setAccountIdInput(e.target.value)}
                  onBlur={handleAccountIdSubmit}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      handleAccountIdSubmit()
                    }
                  }}
                  placeholder="输入账号ID关键字模糊搜索"
                  className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>

              {/* 禁用原因筛选（模糊搜索，回车/失焦/查询按钮均会提交） */}
              <div className="flex flex-col gap-1 col-span-2">
                <label className="text-xs text-gray-500 dark:text-gray-400">禁用原因</label>
                <input
                  type="text"
                  value={disableReasonInput}
                  maxLength={255}
                  onChange={(e) => setDisableReasonInput(e.target.value)}
                  onBlur={handleDisableReasonSubmit}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault()
                      handleDisableReasonSubmit()
                    }
                  }}
                  placeholder="输入关键字模糊搜索"
                  className="px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            {/* 筛选操作按钮：统一查询 / 重置 */}
            <div className="mt-3 flex items-center justify-end gap-2">
              <button
                type="button"
                onClick={handleResetFilters}
                disabled={!hasActiveFilters && !accountIdInput && !disableReasonInput}
                className="btn-ios-secondary btn-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                重置
              </button>
              <button
                type="button"
                onClick={handleSearch}
                className="btn-ios-primary btn-sm flex items-center gap-1"
              >
                <Filter className="w-4 h-4" />
                查询
              </button>
            </div>
          </div>
        )}
        <div className="flex-1 overflow-x-auto overflow-y-auto scrollbar-visible">
          {accountsLoading ? (
            <div className="flex justify-center py-8">
              <RefreshCw className="w-6 h-6 animate-spin text-blue-500" />
            </div>
          ) : (
            <table className="table-ios min-w-[1400px]">
              <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
                <tr>
                  <th className="w-10">
                    <input
                      type="checkbox"
                      checked={allVisibleSelected}
                      onChange={handleToggleSelectAllAccounts}
                      disabled={accounts.length === 0}
                      className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500 disabled:cursor-not-allowed"
                    />
                  </th>
                  <th className="whitespace-nowrap min-w-[180px]">账号ID</th>
                  {isAdmin && <th className="whitespace-nowrap min-w-[120px]">所属用户</th>}
                  <th className="whitespace-nowrap min-w-[80px]">关键词</th>
                  <th className="whitespace-nowrap min-w-[80px]">过滤词</th>
                  <th className="whitespace-nowrap min-w-[80px]">今日回复</th>
                  <th className="whitespace-nowrap min-w-[120px]">状态</th>
                  <th className="whitespace-nowrap min-w-[90px]">配置密码</th>
                  <th className="whitespace-nowrap min-w-[280px]">功能开关</th>
                  <th className="whitespace-nowrap min-w-[90px]">暂停时间</th>
                  <th className="whitespace-nowrap min-w-[160px] sticky right-0 bg-slate-50 dark:bg-slate-800 z-20">操作</th>
                </tr>
              </thead>
              <tbody>
                {accounts.length === 0 ? (
                  <tr>
                    <td colSpan={isAdmin ? 11 : 10}>
                      <div className="empty-state py-8">
                        <p className="text-slate-500 dark:text-slate-400">暂无账号，请添加新账号</p>
                      </div>
                    </td>
                  </tr>
                ) : (
                  accounts.map((account) => (
                  <tr key={account.id}>
                    <td className="w-12">
                      <input
                        type="checkbox"
                        checked={selectedAccountIds.includes(account.id)}
                        onChange={() => handleToggleSelectAccount(account.id)}
                        className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                    </td>
                    <td className="font-medium text-blue-600 dark:text-blue-400">
                      {account.note ? `${account.id} (${account.note})` : account.id}
                    </td>
                    {isAdmin && (
                      <td className="text-sm text-slate-600 dark:text-slate-400 whitespace-nowrap">
                        {account.owner_username || '-'}
                      </td>
                    )}
                    <td>
                      <span className="inline-flex items-center gap-1.5 text-sm">
                        <MessageSquare className="w-3.5 h-3.5 text-blue-500" />
                        <span className="font-medium">{account.keywordCount || 0}</span>
                        <span className="text-slate-400">个</span>
                      </span>
                    </td>
                    <td>
                      <span className="inline-flex items-center gap-1.5 text-sm">
                        <Filter className="w-3.5 h-3.5 text-orange-500" />
                        <span className="font-medium">{account.filter_count || 0}</span>
                        <span className="text-slate-400">个</span>
                      </span>
                    </td>
                    <td>
                      <span className="inline-flex items-center gap-1.5 text-sm">
                        <MessageSquare className="w-3.5 h-3.5 text-emerald-500" />
                        <span className="font-medium">{account.today_reply_count || 0}</span>
                        <span className="text-slate-400">条</span>
                      </span>
                    </td>
                    <td>
                      <div className="flex flex-col gap-0.5">
                        <span className={`inline-flex items-center gap-1.5 ${account.enabled !== false ? 'text-green-600' : 'text-gray-400'}`}>
                          <span className={`status-dot ${account.enabled !== false ? 'status-dot-success' : 'status-dot-danger'}`} />
                          {account.enabled !== false ? '启用' : '禁用'}
                        </span>
                        {account.disable_reason && (
                          <span
                            className="text-[11px] text-red-500 dark:text-red-400 max-w-[140px] truncate"
                            title={account.disable_reason}
                          >
                            {account.disable_reason}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className={`inline-flex items-center gap-1.5 text-xs font-medium px-2 py-1 rounded ${
                        (account.username && account.login_password)
                          ? 'bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-300' 
                          : 'bg-slate-100 text-slate-500 dark:bg-slate-700 dark:text-slate-400'
                      }`}>
                        <Key className="w-3.5 h-3.5" />
                        {(account.username && account.login_password) ? '已配置' : '未配置'}
                      </span>
                    </td>
                    {/* 功能开关组：7 个开关合并为紧凑图标组，点击切换，hover 查看说明 */}
                    <td>
                      <div className="flex items-center gap-1">
                        {/* AI回复 */}
                        <button
                          onClick={() => handleToggleAI(account)}
                          className={`inline-flex items-center justify-center w-7 h-7 rounded transition-colors ${
                            account.aiEnabled
                              ? 'bg-purple-100 text-purple-700 hover:bg-purple-200 dark:bg-purple-900/30 dark:text-purple-300 dark:hover:bg-purple-900/50'
                              : 'bg-slate-100 text-slate-400 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-500 dark:hover:bg-slate-600'
                          }`}
                          title={`AI回复：${account.aiEnabled ? '已开启（点击关闭）' : '已关闭（点击开启）'}`}
                        >
                          <Bot className="w-3.5 h-3.5" />
                        </button>
                        {/* 定时补发货 */}
                        <button
                          onClick={() => handleToggleScheduledRedelivery(account)}
                          className={`inline-flex items-center justify-center w-7 h-7 rounded transition-colors ${
                            account.scheduled_redelivery
                              ? 'bg-teal-100 text-teal-700 hover:bg-teal-200 dark:bg-teal-900/30 dark:text-teal-300 dark:hover:bg-teal-900/50'
                              : 'bg-slate-100 text-slate-400 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-500 dark:hover:bg-slate-600'
                          }`}
                          title={`定时补发货：${account.scheduled_redelivery ? '已开启（点击关闭）' : '已关闭（点击开启）'}`}
                        >
                          <Repeat className="w-3.5 h-3.5" />
                        </button>
                        {/* 定时补评价 */}
                        <button
                          onClick={() => handleToggleScheduledRate(account)}
                          className={`inline-flex items-center justify-center w-7 h-7 rounded transition-colors ${
                            account.scheduled_rate
                              ? 'bg-amber-100 text-amber-700 hover:bg-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:hover:bg-amber-900/50'
                              : 'bg-slate-100 text-slate-400 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-500 dark:hover:bg-slate-600'
                          }`}
                          title={`定时补评价：${account.scheduled_rate ? '已开启（点击关闭）' : '已关闭（点击开启）'}`}
                        >
                          <Star className="w-3.5 h-3.5" />
                        </button>
                        {/* 商品擦亮 */}
                        <button
                          onClick={() => handleToggleAutoPolish(account)}
                          className={`inline-flex items-center justify-center w-7 h-7 rounded transition-colors ${
                            account.auto_polish
                              ? 'bg-fuchsia-100 text-fuchsia-700 hover:bg-fuchsia-200 dark:bg-fuchsia-900/30 dark:text-fuchsia-300 dark:hover:bg-fuchsia-900/50'
                              : 'bg-slate-100 text-slate-400 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-500 dark:hover:bg-slate-600'
                          }`}
                          title={`商品自动擦亮：${account.auto_polish ? '已开启（点击关闭）' : '已关闭（点击开启）'}`}
                        >
                          <RefreshCw className="w-3.5 h-3.5" />
                        </button>
                        {/* 自动确认发货 */}
                        <button
                          onClick={() => handleToggleAutoConfirm(account)}
                          className={`inline-flex items-center justify-center w-7 h-7 rounded transition-colors ${
                            account.auto_confirm
                              ? 'bg-green-100 text-green-700 hover:bg-green-200 dark:bg-green-900/30 dark:text-green-300 dark:hover:bg-green-900/50'
                              : 'bg-slate-100 text-slate-400 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-500 dark:hover:bg-slate-600'
                          }`}
                          title={`自动确认发货：${account.auto_confirm ? '已开启（点击关闭）' : '已关闭（点击开启）'}`}
                        >
                          <PackageCheck className="w-3.5 h-3.5" />
                        </button>
                        {/* 发货成功再发卡券 */}
                        <button
                          onClick={() => handleToggleConfirmBeforeSend(account)}
                          className={`inline-flex items-center justify-center w-7 h-7 rounded transition-colors ${
                            account.confirm_before_send
                              ? 'bg-cyan-100 text-cyan-700 hover:bg-cyan-200 dark:bg-cyan-900/30 dark:text-cyan-300 dark:hover:bg-cyan-900/50'
                              : 'bg-slate-100 text-slate-400 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-500 dark:hover:bg-slate-600'
                          }`}
                          title={`发货成功再发卡券：${account.confirm_before_send ? '已开启（点击关闭）' : '已关闭（点击开启，开启后确认发货失败将不发送卡券）'}`}
                        >
                          <ShieldCheck className="w-3.5 h-3.5" />
                        </button>
                        {/* 卡券发送成功再确认发货 */}
                        <button
                          onClick={() => handleToggleSendBeforeConfirm(account)}
                          className={`inline-flex items-center justify-center w-7 h-7 rounded transition-colors ${
                            account.send_before_confirm
                              ? 'bg-amber-100 text-amber-700 hover:bg-amber-200 dark:bg-amber-900/30 dark:text-amber-300 dark:hover:bg-amber-900/50'
                              : 'bg-slate-100 text-slate-400 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-500 dark:hover:bg-slate-600'
                          }`}
                          title={`卡券发送成功再确认发货：${account.send_before_confirm ? '已开启（点击关闭）' : '已关闭（点击开启，开启后先发卡券，发送成功后再确认发货）'}`}
                        >
                          <Send className="w-3.5 h-3.5" />
                        </button>
                        {/* 自动求小红花 */}
                        <button
                          onClick={() => handleToggleAutoRedFlower(account)}
                          className={`inline-flex items-center justify-center w-7 h-7 rounded transition-colors ${
                            account.auto_red_flower
                              ? 'bg-pink-100 text-pink-700 hover:bg-pink-200 dark:bg-pink-900/30 dark:text-pink-300 dark:hover:bg-pink-900/50'
                              : 'bg-slate-100 text-slate-400 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-500 dark:hover:bg-slate-600'
                          }`}
                          title={`自动求小红花：${account.auto_red_flower ? '已开启（点击关闭）' : '已关闭（点击开启）'}`}
                        >
                          <Flower2 className="w-3.5 h-3.5" />
                        </button>
                        {/* 已下单用户禁止AI回复 */}
                        <button
                          onClick={() => handleToggleAiReplyBlockOrderedUsers(account)}
                          className={`inline-flex items-center justify-center w-7 h-7 rounded transition-colors ${
                            account.ai_reply_block_ordered_users
                              ? 'bg-red-100 text-red-700 hover:bg-red-200 dark:bg-red-900/30 dark:text-red-300 dark:hover:bg-red-900/50'
                              : 'bg-slate-100 text-slate-400 hover:bg-slate-200 dark:bg-slate-700 dark:text-slate-500 dark:hover:bg-slate-600'
                          }`}
                          title={`已下单用户禁止AI回复：${account.ai_reply_block_ordered_users ? '已开启（点击关闭）对已下单用户不使用AI回复' : '已关闭（点击开启）'}`}
                        >
                          <Ban className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </td>
                    <td>
                      <span className="text-slate-600 dark:text-slate-300 text-sm">
                        <Clock className="w-3.5 h-3.5 inline mr-1" />
                        {account.pause_duration || 0} 分钟
                      </span>
                    </td>
                    <td className="sticky right-0 bg-white dark:bg-slate-800 z-[5] shadow-[-4px_0_8px_-4px_rgba(0,0,0,0.1)]">
                      <div className="flex items-center gap-1">
                        {/* 常用操作按钮 */}
                        <button
                          onClick={() => handleToggleEnabled(account)}
                          className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                          title={account.enabled !== false ? '禁用' : '启用'}
                        >
                          {account.enabled !== false ? (
                            <><PowerOff className="w-3.5 h-3.5 text-amber-500" /><span className="text-amber-600 dark:text-amber-400">禁用</span></>
                          ) : (
                            <><Power className="w-3.5 h-3.5 text-green-500" /><span className="text-green-600 dark:text-green-400">启用</span></>
                          )}
                        </button>
                        <button
                          onClick={() => openEditModal(account)}
                          className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                          title="编辑"
                        >
                          <Edit2 className="w-3.5 h-3.5 text-blue-500" />
                          <span className="text-blue-600 dark:text-blue-400">编辑</span>
                        </button>
                        <button
                          onClick={() => setDeleteAccountConfirm({ open: true, id: account.id })}
                          className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded hover:bg-red-50 dark:hover:bg-red-900/30 transition-colors"
                          title="删除"
                        >
                          <Trash2 className="w-3.5 h-3.5 text-red-500" />
                          <span className="text-red-600 dark:text-red-400">删除</span>
                        </button>
                        {/* 更多操作下拉菜单 */}
                        <div className="relative group">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              if (moreMenuAccountId === account.id) {
                                setMoreMenuAccountId(null)
                              } else {
                                const rect = e.currentTarget.getBoundingClientRect()
                                setMoreMenuPosition({ top: rect.bottom + 4, right: window.innerWidth - rect.right })
                                setMoreMenuAccountId(account.id)
                              }
                            }}
                            className="inline-flex items-center gap-1 px-2 py-1 text-xs rounded hover:bg-slate-100 dark:hover:bg-slate-700 transition-colors"
                            title="更多操作"
                          >
                            <MoreHorizontal className="w-4 h-4 text-slate-500" />
                            <span className="text-slate-600 dark:text-slate-400">更多</span>
                          </button>
                        </div>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
          )}

        {/* 更多操作下拉菜单 - 移到表格外部避免overflow裁剪 */}
        {moreMenuAccountId && (
          <>
            <div 
              className="fixed inset-0 z-40" 
              onClick={() => setMoreMenuAccountId(null)}
            />
            <div 
              className="fixed z-50 w-40 bg-white dark:bg-slate-800 rounded-lg shadow-lg ring-1 ring-black/5 dark:ring-white/10 py-1"
              style={{ top: moreMenuPosition.top, right: moreMenuPosition.right }}
            >
              {(() => {
                const account = accounts.find(a => a.id === moreMenuAccountId)
                if (!account) return null
                return (
                  <>
                    <button
                      onClick={() => { openAISettings(account); setMoreMenuAccountId(null) }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                    >
                      <Bot className="w-3.5 h-3.5 text-purple-500" />
                      <span className="text-slate-700 dark:text-slate-300">AI设置</span>
                    </button>
                    <button
                      onClick={() => { openDefaultReplyModal(account); setMoreMenuAccountId(null) }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                    >
                      <MessageSquare className="w-3.5 h-3.5 text-green-500" />
                      <span className="text-slate-700 dark:text-slate-300">默认回复</span>
                    </button>
                    <button
                      onClick={() => { openProxySettings(account); setMoreMenuAccountId(null) }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                    >
                      <Globe className="w-3.5 h-3.5 text-cyan-500" />
                      <span className="text-slate-700 dark:text-slate-300">代理设置</span>
                    </button>
                    <button
                      onClick={() => { openMessageExpireTimeModal(account); setMoreMenuAccountId(null) }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                    >
                      <Timer className="w-3.5 h-3.5 text-orange-500" />
                      <span className="text-slate-700 dark:text-slate-300">消息等待</span>
                    </button>
                    <button
                      onClick={() => { openReplyDelayModal(account); setMoreMenuAccountId(null) }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                    >
                      <Clock className="w-3.5 h-3.5 text-amber-500" />
                      <span className="text-slate-700 dark:text-slate-300">延迟回复</span>
                    </button>
                    <button
                      onClick={() => { openFaceVerificationModal(account); setMoreMenuAccountId(null) }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                    >
                      <ScanFace className="w-3.5 h-3.5 text-pink-500" />
                      <span className="text-slate-700 dark:text-slate-300">人脸验证</span>
                    </button>
                    <button
                      onClick={() => { openConfirmReceiptModal(account); setMoreMenuAccountId(null) }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                    >
                      <PackageCheck className="w-3.5 h-3.5 text-emerald-500" />
                      <span className="text-slate-700 dark:text-slate-300">确认收货消息</span>
                    </button>
                    <button
                      onClick={() => { openAutoRateModal(account); setMoreMenuAccountId(null) }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                    >
                      <Star className="w-3.5 h-3.5 text-yellow-500" />
                      <span className="text-slate-700 dark:text-slate-300">自动评价</span>
                    </button>
                    <button
                      onClick={() => { openDeliveryDisabledModal(account); setMoreMenuAccountId(null) }}
                      className="w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-slate-50 dark:hover:bg-slate-700 transition-colors"
                    >
                      <Ban className={`w-3.5 h-3.5 ${account.delivery_disabled ? 'text-red-500' : 'text-slate-400'}`} />
                      <span className="text-slate-700 dark:text-slate-300">禁止发货设置</span>
                    </button>
                  </>
                )
              })()}
            </div>
          </>
        )}
        </div>
        
        {/* 分页控件 */}
        {pagination.total > 0 && (
          <div className="flex-shrink-0 flex flex-col sm:flex-row items-center justify-between px-4 py-3 border-t border-gray-200 dark:border-gray-700 gap-3">
            <div className="flex items-center gap-2 text-sm text-gray-500">
              <span>每页</span>
              <select
                value={pagination.pageSize}
                onChange={(e) => handlePageSizeChange(Number(e.target.value))}
                disabled={accountsLoading}
                className="px-2 py-1 border border-gray-300 dark:border-gray-600 rounded-md bg-white dark:bg-gray-800 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>条，共 {pagination.total} 条</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-sm text-gray-500">
                第 {pagination.page} / {pagination.totalPages} 页
              </span>
              <button
                onClick={() => handlePageChange(pagination.page - 1)}
                disabled={pagination.page <= 1 || accountsLoading}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronLeft className="w-5 h-5" />
              </button>
              <button
                onClick={() => handlePageChange(pagination.page + 1)}
                disabled={pagination.page >= pagination.totalPages || accountsLoading}
                className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <ChevronRight className="w-5 h-5" />
              </button>
            </div>
          </div>
        )}
      </div>

      {/* 扫码登录弹窗 */}
      {activeModal === 'qrcode' && (
        <div className="modal-overlay">
          <div className="modal-content max-w-sm">
            <div className="modal-header">
              <h2 className="modal-title">扫码登录</h2>
              <button onClick={closeModal} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body flex flex-col items-center py-6">
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
                    <span>已扫描，等待确认...</span>
                  </div>
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
                  <button onClick={refreshQRCode} className="btn-ios-primary btn-sm">
                    刷新二维码
                  </button>
                </div>
              )}
              {qrStatus === 'error' && (
                <div className="flex flex-col items-center gap-3">
                  <p className="text-sm text-red-500">{qrErrorMessage || '生成二维码失败'}</p>
                  <button onClick={refreshQRCode} className="btn-ios-primary btn-sm">
                    重新生成
                  </button>
                </div>
              )}
              {qrStatus === 'failed' && (
                <div className="flex flex-col items-center gap-3">
                  <p className="text-sm text-red-500">{qrErrorMessage || '登录失败'}</p>
                  <button onClick={refreshQRCode} className="btn-ios-primary btn-sm">
                    重新登录
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* 密码登录弹窗 */}
      {activeModal === 'password' && (
        <div className="modal-overlay">
          <div className="modal-content max-w-sm">
            <div className="modal-header">
              <h2 className="modal-title">账号密码登录</h2>
              <button onClick={closeModal} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            {/* 登录状态显示 */}
            {pwdStatus === 'processing' && (
              <div className="modal-body flex flex-col items-center py-6">
                <Loader2 className="w-10 h-10 text-blue-600 dark:text-blue-400 animate-spin" />
                <p className="mt-3 text-sm text-slate-600 dark:text-slate-300">正在登录，请稍候...</p>
                <p className="mt-1 text-xs text-slate-400">可能需要进行滑块验证</p>
              </div>
            )}
            {pwdStatus === 'verification_required' && (
              <div className="modal-body flex flex-col items-center py-6">
                <div className="w-14 h-14 rounded-full bg-amber-100 dark:bg-amber-900/30 flex items-center justify-center mb-3">
                  <Key className="w-7 h-7 text-amber-600 dark:text-amber-400" />
                </div>
                <p className="text-sm font-medium text-slate-700 dark:text-slate-200">需要人脸验证</p>
                {pwdScreenshotPath && (
                  <img src={pwdScreenshotPath} alt="验证截图" className="mt-3 max-w-full rounded-lg border" />
                )}
                {pwdVerificationUrl && (
                  <a href={pwdVerificationUrl} target="_blank" rel="noopener noreferrer" className="mt-3 text-blue-600 hover:underline text-sm">
                    点击打开验证链接
                  </a>
                )}
                <p className="mt-2 text-xs text-slate-400">请在手机上完成验证后等待</p>
              </div>
            )}
            {pwdStatus === 'success' && (
              <div className="modal-body flex flex-col items-center py-6">
                <div className="w-14 h-14 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
                  <CheckCircle className="w-7 h-7 text-green-600 dark:text-green-400" />
                </div>
                <p className="mt-3 font-medium text-green-600 dark:text-green-400">登录成功！</p>
              </div>
            )}
            {pwdStatus === 'failed' && (
              <div className="modal-body flex flex-col items-center py-6">
                <div className="w-14 h-14 rounded-full bg-red-100 dark:bg-red-900/30 flex items-center justify-center">
                  <X className="w-7 h-7 text-red-600 dark:text-red-400" />
                </div>
                <p className="mt-3 font-medium text-red-600 dark:text-red-400">登录失败</p>
                <button onClick={() => setPwdStatus('idle')} className="mt-3 btn-ios-secondary btn-sm">
                  重试
                </button>
              </div>
            )}
            {/* 登录表单 */}
            {pwdStatus === 'idle' && (
              <form onSubmit={handlePasswordLogin}>
                <div className="modal-body space-y-4">
                  <div className="input-group">
                    <label className="input-label">账号(一般是手机号)</label>
                    <input
                      type="text"
                      value={pwdAccount}
                      onChange={(e) => setPwdAccount(e.target.value)}
                      className="input-ios"
                      placeholder="请输入闲鱼账号/手机号"
                      autoFocus
                    />
                  </div>
                  <div className="input-group">
                    <label className="input-label">密码</label>
                    <div className="relative">
                      <input
                        type={pwdPasswordVisible ? 'text' : 'password'}
                        value={pwdPassword}
                        onChange={(e) => setPwdPassword(e.target.value)}
                        className="input-ios pr-10"
                        placeholder="请输入密码"
                      />
                      <button
                        type="button"
                        onClick={() => setPwdPasswordVisible((current) => !current)}
                        className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                        title={pwdPasswordVisible ? '隐藏密码' : '查看密码'}
                      >
                        {pwdPasswordVisible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                  <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
                    <input
                      type="checkbox"
                      checked={pwdShowBrowser}
                      onChange={(e) => setPwdShowBrowser(e.target.checked)}
                      className="h-4 w-4 rounded border-slate-300 dark:border-slate-600 text-blue-600"
                    />
                    显示浏览器(只有Windows源码部署用)
                  </label>
                  <p className="input-hint">
                    登录过程可能需要进行人脸验证，请确保手机畅通
                  </p>
                </div>
                <div className="modal-footer">
                  <button type="button" onClick={closeModal} className="btn-ios-secondary" disabled={pwdLoading}>
                    取消
                  </button>
                  <button type="submit" className="btn-ios-primary" disabled={pwdLoading}>
                    {pwdLoading ? (
                      <span className="">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        登录中...
                      </span>
                    ) : (
                      '登录'
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* 手动输入弹窗 */}
      {activeModal === 'manual' && (
        <div className="modal-overlay">
          <div className="modal-content max-w-md">
            <div className="modal-header">
              <h2 className="modal-title">手动输入Cookie</h2>
              <button onClick={closeModal} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleManualAdd}>
              <div className="modal-body space-y-4">
                <div className="input-group">
                  <label className="input-label">账号ID(随便输入)</label>
                  <input
                    type="text"
                    value={manualAccountId}
                    onChange={(e) => setManualAccountId(e.target.value)}
                    className="input-ios"
                    placeholder="请输入账号ID（如手机号或用户名）"
                    autoFocus
                  />
                </div>
                <div className="input-group">
                  <label className="input-label">Cookie</label>
                  <textarea
                    value={manualCookie}
                    onChange={(e) => setManualCookie(e.target.value)}
                    className="input-ios h-28 resize-none font-mono text-xs"
                    placeholder="请粘贴完整的Cookie值"
                  />
                  <p className="input-hint">
                    可从浏览器开发者工具中获取Cookie
                  </p>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" onClick={closeModal} className="btn-ios-secondary" disabled={manualLoading}>
                  取消
                </button>
                <button type="submit" className="btn-ios-primary" disabled={manualLoading}>
                  {manualLoading ? (
                    <span className="">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      添加中...
                    </span>
                  ) : (
                    '添加账号'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 编辑账号弹窗 */}
      {activeModal === 'edit' && editingAccount && (
        <div className="modal-overlay">
          <div className="modal-content max-w-md">
            <div className="modal-header">
              <h2 className="modal-title">编辑账号</h2>
              <button onClick={closeModal} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <form onSubmit={handleEditSubmit}>
              <div className="modal-body space-y-4">
                <div className="input-group">
                  <label className="input-label">账号ID</label>
                  <input
                    type="text"
                    value={editingAccount.id}
                    disabled
                    className="input-ios bg-slate-100 dark:bg-slate-700"
                  />
                </div>
                <div className="input-group">
                  <label className="input-label">备注</label>
                  <input
                    type="text"
                    value={editNote}
                    onChange={(e) => setEditNote(e.target.value)}
                    className="input-ios"
                    placeholder="添加备注信息"
                  />
                </div>
                <div className="input-group">
                  <label className="input-label">Cookie</label>
                  <textarea
                    value={editCookie}
                    onChange={(e) => setEditCookie(e.target.value)}
                    className="input-ios h-20 resize-none font-mono text-xs"
                    placeholder="更新Cookie值"
                  />
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    当前Cookie长度: {editCookie.length} 字符
                  </p>
                </div>

                {/* 暂停时间 */}
                <div className="input-group">
                  <label className="input-label flex items-center gap-2">
                    <Clock className="w-4 h-4 text-amber-500" />
                    暂停时间（分钟）
                  </label>
                  <input
                    type="number"
                    min="0"
                    max="1440"
                    value={editPauseDuration}
                    onChange={(e) => setEditPauseDuration(parseInt(e.target.value) || 0)}
                    className="input-ios"
                    placeholder="0"
                  />
                  <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                    检测到手动发出消息后，自动回复暂停的时间。设置为0表示不暂停。
                  </p>
                </div>

                {/* 登录信息设置 */}
                <div className="border-t border-slate-100 dark:border-slate-700 pt-4 mt-2">
                  <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-3 flex items-center gap-2">
                    <Key className="w-4 h-4 text-blue-500" />
                    自动登录设置
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
                    配置后，当Cookie失效时系统会自动尝试使用账号密码重新登录
                  </p>
                  
                  <div className="space-y-3">
                    <div className="input-group">
                      <label className="input-label">登录用户名(手机号)</label>
                      <input
                        type="text"
                        value={editUsername}
                        onChange={(e) => setEditUsername(e.target.value)}
                        className="input-ios"
                        placeholder="闲鱼账号/手机号"
                      />
                    </div>
                    <div className="input-group">
                      <label className="input-label">登录密码</label>
                      <div className="relative">
                        <input
                          type={editPasswordVisible ? 'text' : 'password'}
                          value={editPassword}
                          onChange={(e) => setEditPassword(e.target.value)}
                          className="input-ios pr-10"
                          placeholder="登录密码"
                        />
                        <button
                          type="button"
                          onClick={() => setEditPasswordVisible((current) => !current)}
                          className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
                          title={editPasswordVisible ? '隐藏密码' : '查看密码'}
                        >
                          {editPasswordVisible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                        </button>
                      </div>
                    </div>
                    <label className="flex items-center gap-2 text-sm text-slate-600 dark:text-slate-300">
                      <input
                        type="checkbox"
                        checked={editShowBrowser}
                        onChange={(e) => setEditShowBrowser(e.target.checked)}
                        className="h-4 w-4 rounded border-slate-300 dark:border-slate-600 text-blue-600"
                      />
                      显示浏览器(只有Windows源码部署用)
                    </label>
                  </div>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" onClick={closeModal} className="btn-ios-secondary" disabled={editSaving}>
                  取消
                </button>
                <button type="submit" className="btn-ios-primary" disabled={editSaving}>
                  {editSaving ? (
                    <span className="">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      保存中...
                    </span>
                  ) : (
                    '保存'
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* 默认回复管理弹窗 */}
      {activeModal === 'default-reply' && defaultReplyAccount && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg">
            <div className="modal-header">
              <h2 className="modal-title">默认回复管理</h2>
              <button onClick={closeModal} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              <div className="input-group">
                <label className="input-label">账号</label>
                <input
                  type="text"
                  value={defaultReplyAccount.id}
                  disabled
                  className="input-ios bg-slate-100 dark:bg-slate-700"
                />
              </div>

              {/* 启用开关 */}
              <div className="flex items-center justify-between py-3 border-b border-slate-100 dark:border-slate-700">
                <div>
                  <p className="font-medium text-slate-900 dark:text-slate-100">启用默认回复</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">开启后，未匹配关键词时使用默认回复</p>
                </div>
                <button
                  type="button"
                  onClick={() => setDefaultReplyEnabled(!defaultReplyEnabled)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    defaultReplyEnabled ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-600'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      defaultReplyEnabled ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              {/* 只回复一次 */}
              <div className="flex items-center justify-between py-3 border-b border-slate-100 dark:border-slate-700">
                <div>
                  <p className="font-medium text-slate-900 dark:text-slate-100">只回复一次</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">开启后，每个用户只会收到一次默认回复</p>
                </div>
                <button
                  type="button"
                  onClick={() => setDefaultReplyOnce(!defaultReplyOnce)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    defaultReplyOnce ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-600'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      defaultReplyOnce ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>

              {/* 回复类型选择 */}
              <div className="input-group">
                <label className="input-label">回复类型</label>
                <div className="flex gap-2">
                  {([
                    { value: 'text', label: '默认回复' },
                    { value: 'api', label: 'API接口' },
                  ] as const).map((opt) => (
                    <button
                      key={opt.value}
                      type="button"
                      onClick={() => setDefaultReplyType(opt.value)}
                      className={`flex-1 px-3 py-2 rounded-lg text-sm font-medium transition-colors border ${
                        defaultReplyType === opt.value
                          ? 'bg-blue-600 text-white border-blue-600'
                          : 'bg-white dark:bg-slate-700 text-slate-600 dark:text-slate-300 border-slate-300 dark:border-slate-600 hover:border-blue-400'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* API 接口配置（仅 API 类型显示） */}
              {defaultReplyType === 'api' && (
                <>
                  <div className="input-group">
                    <label className="input-label">API 地址</label>
                    <input
                      type="text"
                      value={defaultReplyApiUrl}
                      onChange={(e) => setDefaultReplyApiUrl(e.target.value)}
                      className="input-ios"
                      placeholder="https://example.com/api/reply"
                    />
                  </div>
                  <div className="input-group">
                    <label className="input-label">超时时间（秒）</label>
                    <input
                      type="number"
                      min={1}
                      max={120}
                      value={defaultReplyApiTimeout}
                      onChange={(e) => setDefaultReplyApiTimeout(Number(e.target.value) || 80)}
                      className="input-ios"
                      placeholder="80"
                    />
                  </div>
                  <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg space-y-2">
                    <p className="text-xs text-blue-600 dark:text-blue-400">
                      <strong>调用说明：</strong>触发默认回复时，系统会向上述地址发起 <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">POST</code> 请求，
                      请求体为 JSON：
                    </p>
                    <pre className="text-xs bg-blue-100 dark:bg-blue-800 p-2 rounded overflow-x-auto whitespace-pre-wrap break-all">{`{
  "account_id": "闲鱼账号标识",
  "message": "买家发来的消息内容"
}`}</pre>
                    <p className="text-xs text-blue-600 dark:text-blue-400">
                      <strong>返回格式：</strong>兼容以下两种，任选其一：
                    </p>
                    <pre className="text-xs bg-blue-100 dark:bg-blue-800 p-2 rounded overflow-x-auto whitespace-pre-wrap break-all">{`// 方式一：JSON
{ "success": true, "reply": "要发送给买家的内容" }

// 方式二：纯文本
要发送给买家的内容`}</pre>
                    <p className="text-xs text-amber-600 dark:text-amber-400">
                      返回内容支持用 <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">######</code> 分隔为多条消息依次发送。
                      接口调用失败、超时或返回空内容时，将不发送任何回复。
                    </p>
                  </div>
                </>
              )}

              {/* 文本回复内容（API 类型时隐藏） */}
              {defaultReplyType !== 'api' && (
              <div className="input-group">
                <label className="input-label">默认回复内容</label>
                <textarea
                  value={defaultReplyContent}
                  onChange={(e) => setDefaultReplyContent(e.target.value)}
                  className="input-ios h-32 resize-none"
                  placeholder="输入默认回复内容"
                />
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  当没有匹配到任何关键词且AI回复未启用时，将使用此默认回复。
                </p>
              </div>
              )}

              {/* 图片上传（默认回复类型显示，与文本一起） */}
              {defaultReplyType !== 'api' && (
              <div className="input-group">
                <label className="input-label">回复图片（可选）</label>
                <input
                  ref={defaultReplyImageInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleDefaultReplyImageUpload}
                  className="hidden"
                />
                {defaultReplyImage ? (
                  <div className="relative inline-block">
                    <img
                      src={defaultReplyImage}
                      alt="回复图片"
                      className="max-w-[200px] max-h-[150px] rounded-lg border border-slate-200 dark:border-slate-700"
                    />
                    <button
                      type="button"
                      onClick={() => setDefaultReplyImage('')}
                      className="absolute -top-2 -right-2 w-6 h-6 bg-red-500 text-white rounded-full flex items-center justify-center hover:bg-red-600"
                    >
                      <X className="w-3 h-3" />
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => defaultReplyImageInputRef.current?.click()}
                    disabled={defaultReplyImageUploading}
                    className="flex items-center gap-2 px-4 py-2 border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-lg hover:border-blue-500 dark:hover:border-blue-400 transition-colors"
                  >
                    {defaultReplyImageUploading ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span className="text-sm text-slate-500">上传中...</span>
                      </>
                    ) : (
                      <>
                        <ImagePlus className="w-4 h-4 text-slate-400" />
                        <span className="text-sm text-slate-500">点击上传图片</span>
                      </>
                    )}
                  </button>
                )}
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  支持 JPG、PNG、GIF 格式，最大 5MB
                </p>
                <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                  发送顺序：如果同时配置了图片和文字，将先发送图片，再发送文字内容
                </p>
              </div>
              )}

              {/* 变量说明（API 类型时隐藏） */}
              {defaultReplyType !== 'api' && (
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                <p className="text-xs text-blue-600 dark:text-blue-400">
                  <strong>支持变量：</strong><br />
                  <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">{'{send_user_name}'}</code> - 用户昵称<br />
                  <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">{'{send_user_id}'}</code> - 用户ID<br />
                  <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">{'{send_message}'}</code> - 用户消息内容
                </p>
                <p className="text-xs text-blue-600 dark:text-blue-400 mt-2">
                  <strong>多条消息：</strong>使用 <code className="bg-blue-100 dark:bg-blue-800 px-1 rounded">######</code> 分隔，将拆分为多条消息依次发送<br />
                  例如：第一条消息######第二条消息
                </p>
              </div>
              )}
            </div>
            <div className="modal-footer">
              <button type="button" onClick={closeModal} className="btn-ios-secondary" disabled={defaultReplySaving}>
                取消
              </button>
              <button onClick={handleSaveDefaultReply} className="btn-ios-primary" disabled={defaultReplySaving}>
                {defaultReplySaving ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    保存中...
                  </span>
                ) : (
                  '保存'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* AI设置弹窗 */}
      {activeModal === 'ai-settings' && aiSettingsAccount && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg">
            <div className="modal-header">
              <h2 className="modal-title">AI回复设置</h2>
              <button onClick={closeModal} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              {aiSettingsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                </div>
              ) : (
                <>
                  <div className="input-group">
                    <label className="input-label">账号</label>
                    <input
                      type="text"
                      value={aiSettingsAccount.id}
                      disabled
                      className="input-ios bg-slate-100 dark:bg-slate-700"
                    />
                  </div>

                  {/* AI开关 */}
                  <div className="flex items-center justify-between py-3 border-b border-slate-100 dark:border-slate-700">
                    <div>
                      <p className="font-medium text-slate-900 dark:text-slate-100">启用AI回复</p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">开启后将使用AI自动回复消息</p>
                    </div>
                    <button
                      type="button"
                      onClick={handleToggleAIEnabledInModal}
                      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                        aiEnabled ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-600'
                      }`}
                    >
                      <span
                        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                          aiEnabled ? 'translate-x-6' : 'translate-x-1'
                        }`}
                      />
                    </button>
                  </div>

                  {/* 启用时间段选择 */}
                  {aiEnabled && (
                    <div className="bg-slate-50 dark:bg-slate-800/40 rounded-xl p-3.5 border border-slate-100 dark:border-slate-800 space-y-3 transition-all duration-300">
                      <div className="flex items-center justify-between">
                        <label className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">启用时间范围</label>
                        {(aiTimeRangeStart || aiTimeRangeEnd) && (
                          <button
                            type="button"
                            onClick={() => {
                              setAiTimeRangeStart('')
                              setAiTimeRangeEnd('')
                            }}
                            className="text-xs text-rose-500 hover:text-rose-600 dark:text-rose-400 dark:hover:text-rose-300 font-medium transition-colors"
                          >
                            重置为全天
                          </button>
                        )}
                      </div>
                      <div className="flex items-center gap-3">
                        <div className="flex-1 relative">
                          <input
                            type="time"
                            value={aiTimeRangeStart}
                            onChange={(e) => setAiTimeRangeStart(e.target.value)}
                            className="input-ios w-full pl-3 pr-10 text-sm font-medium"
                          />
                          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-bold text-slate-400 dark:text-slate-500 pointer-events-none uppercase">
                            开始
                          </span>
                        </div>
                        <span className="text-slate-400 dark:text-slate-600 text-xs font-medium">至</span>
                        <div className="flex-1 relative">
                          <input
                            type="time"
                            value={aiTimeRangeEnd}
                            onChange={(e) => setAiTimeRangeEnd(e.target.value)}
                            className="input-ios w-full pl-3 pr-10 text-sm font-medium"
                          />
                          <span className="absolute right-3 top-1/2 -translate-y-1/2 text-[10px] font-bold text-slate-400 dark:text-slate-500 pointer-events-none uppercase">
                            结束
                          </span>
                        </div>
                      </div>
                      <p className="text-xs text-slate-500 dark:text-slate-400 leading-relaxed">
                        {aiTimeRangeStart && aiTimeRangeEnd ? (
                          <span>
                            当前配置：每天 <strong className="text-blue-600 dark:text-blue-400">{aiTimeRangeStart}</strong> 到 <strong className="text-blue-600 dark:text-blue-400">{aiTimeRangeEnd}</strong>
                            {aiTimeRangeStart > aiTimeRangeEnd ? <span className="text-amber-500 dark:text-amber-400 font-medium">（跨天至次日）</span> : ''} 启用AI自动回复。其余时间将使用普通规则回复。
                          </span>
                        ) : (
                          <span className="text-slate-400 dark:text-slate-500">
                            未设置时间范围，默认全天 24 小时启用AI自动回复。
                          </span>
                        )}
                      </p>
                    </div>
                  )}

                  {/* API配置 */}
                  <div className="border-t border-slate-200 dark:border-slate-700 pt-4">
                    <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-3 flex items-center gap-2">
                      <Bot className="w-4 h-4" />
                      API配置
                    </h3>
                    <div className="space-y-3">
                      <div className="input-group">
                        <label className="input-label">服务商类型</label>
                        <select
                          value={aiProviderType}
                          onChange={(e) => handleAIProviderChange(e.target.value as AIProviderType)}
                          className="input-ios"
                        >
                          {AI_PROVIDER_OPTIONS.map(opt => (
                            <option key={opt.value} value={opt.value}>{opt.label}</option>
                          ))}
                        </select>
                        <p className="text-xs text-slate-400 mt-1">
                          {AI_PROVIDER_OPTIONS.find(opt => opt.value === aiProviderType)?.description}
                        </p>
                      </div>
                      <div className="input-group">
                        <label className="input-label">API地址</label>
                        <input
                          type="text"
                          value={aiApiUrl}
                          onChange={(e) => setAiApiUrl(e.target.value)}
                          className="input-ios"
                          placeholder={AI_PROVIDER_DEFAULT_BASE_URLS[aiProviderType]}
                        />
                        <p className="text-xs text-slate-400 mt-1">
                          {aiProviderType === 'openai_compatible' && '无需补全 /chat/completions'}
                          {aiProviderType === 'anthropic' && '无需补全 /v1/messages'}
                          {aiProviderType === 'gemini' && '无需补全 /v1beta/models'}
                          {aiProviderType === 'dashscope_app' && '请填入完整的 .../apps/{app_id}/completion 地址'}
                        </p>
                      </div>
                      <div className="input-group">
                        <label className="input-label">API Key</label>
                        <div className="relative">
                          <input
                            type={showAiApiKey ? 'text' : 'password'}
                            value={aiApiKey}
                            onChange={(e) => setAiApiKey(e.target.value)}
                            className="input-ios pr-9"
                            placeholder="sk-..."
                          />
                          <button
                            type="button"
                            onClick={() => setShowAiApiKey(v => !v)}
                            className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                            aria-label={showAiApiKey ? '隐藏API Key' : '显示API Key'}
                          >
                            {showAiApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                          </button>
                        </div>
                      </div>
                      <div className="input-group">
                        {/* 注意：label 不能包裹 button，否则点击 label 任意位置都会触发内部 button 的 click 事件。改用 div 容器隔离 */}
                        <div className="input-label flex items-center justify-between">
                          <span>模型名称</span>
                          <button
                            type="button"
                            onClick={handleFetchAIModels}
                            disabled={aiModelsLoading || aiProviderType === 'dashscope_app'}
                            className="text-xs text-blue-500 hover:text-blue-600 disabled:text-slate-400 disabled:cursor-not-allowed flex items-center gap-1"
                          >
                            {aiModelsLoading ? (
                              <>
                                <Loader2 className="w-3 h-3 animate-spin" />
                                获取中...
                              </>
                            ) : (
                              <>
                                <RefreshCw className="w-3 h-3" />
                                获取模型列表
                              </>
                            )}
                          </button>
                        </div>
                        <div className="relative">
                          <input
                            type="text"
                            value={aiModelName}
                            onChange={(e) => {
                              setAiModelName(e.target.value)
                              setAiModelFilterByInput(true)
                              if (aiModelOptions.length > 0) setShowAiModelDropdown(true)
                            }}
                            onFocus={() => {
                              if (aiModelOptions.length > 0) setShowAiModelDropdown(true)
                            }}
                            onBlur={() => { window.setTimeout(() => setShowAiModelDropdown(false), 150) }}
                            className="input-ios pr-9"
                            placeholder="qwen-plus"
                          />
                          {aiModelOptions.length > 0 && (
                            <button
                              type="button"
                              onMouseDown={(e) => {
                                e.preventDefault()
                                setAiModelFilterByInput(false)
                                setShowAiModelDropdown(v => !v)
                              }}
                              className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                              aria-label="展开模型列表"
                            >
                              <ChevronDown className={`w-4 h-4 transition-transform ${showAiModelDropdown ? 'rotate-180' : ''}`} />
                            </button>
                          )}
                          {showAiModelDropdown && aiModelOptions.length > 0 && (() => {
                            const q = aiModelName.trim().toLowerCase()
                            const filtered = aiModelFilterByInput && q
                              ? aiModelOptions.filter(m =>
                                  m.id.toLowerCase().includes(q) ||
                                  (m.name || '').toLowerCase().includes(q)
                                )
                              : aiModelOptions
                            return (
                              <div className="absolute z-20 mt-1 w-full bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg shadow-lg max-h-60 overflow-auto">
                                {filtered.length === 0 ? (
                                  <div className="px-3 py-2 text-xs text-slate-400">无匹配模型，将按当前输入保存</div>
                                ) : (
                                  filtered.map(model => (
                                    <div
                                      key={model.id}
                                      onMouseDown={(e) => {
                                        e.preventDefault()
                                        setAiModelName(model.id)
                                        setAiModelFilterByInput(false)
                                        setShowAiModelDropdown(false)
                                      }}
                                      className={`px-3 py-2 cursor-pointer text-sm hover:bg-slate-100 dark:hover:bg-slate-700 ${aiModelName === model.id ? 'bg-blue-50 dark:bg-blue-900/30' : ''}`}
                                    >
                                      <div className="font-mono text-slate-700 dark:text-slate-200">{model.id}</div>
                                      {model.name && model.name !== model.id && (
                                        <div className="text-xs text-slate-400 mt-0.5">{model.name}</div>
                                      )}
                                    </div>
                                  ))
                                )}
                              </div>
                            )
                          })()}
                        </div>
                        <p className="text-xs text-slate-400 mt-1">
                          {aiProviderType === 'dashscope_app'
                            ? '阿里云百炼应用编排无需填写模型名'
                            : aiModelOptions.length > 0
                              ? `已加载 ${aiModelOptions.length} 个模型，可直接选择或继续手动输入`
                              : '可手动输入或点击右侧按钮获取该服务商支持的模型列表'}
                        </p>
                      </div>
                      <button
                        type="button"
                        onClick={handleTestAI}
                        disabled={aiTesting}
                        className="btn-ios-primary w-full"
                      >
                        {aiTesting ? (
                          <span className="flex items-center justify-center gap-2">
                            <Loader2 className="w-4 h-4 animate-spin" />
                            测试中...
                          </span>
                        ) : (
                          '测试AI连接'
                        )}
                      </button>
                    </div>
                  </div>

                  {/* 议价设置 */}
                  <div className="border-t border-slate-200 dark:border-slate-700 pt-4">
                    <h3 className="text-sm font-medium text-slate-700 dark:text-slate-300 mb-3">议价设置</h3>
                    <div className="grid grid-cols-3 gap-3">
                      <div className="input-group">
                        <label className="input-label text-xs">最大折扣(%)</label>
                        <input
                          type="number"
                          value={aiMaxDiscountPercent}
                          onChange={(e) => setAiMaxDiscountPercent(Number(e.target.value))}
                          className="input-ios"
                          min="0"
                          max="100"
                        />
                      </div>
                      <div className="input-group">
                        <label className="input-label text-xs">最大减价(元)</label>
                        <input
                          type="number"
                          value={aiMaxDiscountAmount}
                          onChange={(e) => setAiMaxDiscountAmount(Number(e.target.value))}
                          className="input-ios"
                          min="0"
                        />
                      </div>
                      <div className="input-group">
                        <label className="input-label text-xs">最大议价轮数</label>
                        <input
                          type="number"
                          value={aiMaxBargainRounds}
                          onChange={(e) => setAiMaxBargainRounds(Number(e.target.value))}
                          className="input-ios"
                          min="1"
                          max="10"
                        />
                      </div>
                    </div>
                  </div>

                  {/* 自定义提示词 */}
                  <div className="input-group">
                    <label className="input-label">自定义提示词 (JSON格式)</label>
                    <textarea
                      value={aiCustomPrompts}
                      onChange={(e) => setAiCustomPrompts(e.target.value)}
                      className="input-ios h-24 resize-none font-mono text-xs"
                      placeholder='{"classify": "分类提示词", "price": "议价提示词", "tech": "技术提示词", "default": "默认提示词"}'
                    />
                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                      留空使用系统默认提示词
                    </p>
                  </div>

                  {/* 配置提示 */}
                  <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg p-3 text-xs text-slate-500 dark:text-slate-400">
                    {aiProviderType === 'openai_compatible' && (
                      <>
                        <p className="font-medium mb-1">OpenAI兼容服务示例:</p>
                        <ul className="space-y-0.5 list-disc list-inside">
                          <li><span className="text-blue-500">阿里云百炼(推荐)</span>: https://dashscope.aliyuncs.com/compatible-mode/v1</li>
                          <li>阿里云模型: qwen-plus、qwen-turbo、qwen-max、qwen-long</li>
                          <li>OpenAI: https://api.openai.com/v1</li>
                          <li>DeepSeek: https://api.deepseek.com / Moonshot: https://api.moonshot.cn/v1</li>
                          <li>国内中转: 使用服务商提供的API地址</li>
                        </ul>
                        <p className="mt-2 text-slate-400">
                          阿里云百炼平台: <a href="https://bailian.console.aliyun.com/" target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:underline">https://bailian.console.aliyun.com/</a>
                        </p>
                      </>
                    )}
                    {aiProviderType === 'anthropic' && (
                      <>
                        <p className="font-medium mb-1">Anthropic Claude 配置:</p>
                        <ul className="space-y-0.5 list-disc list-inside">
                          <li>API地址: https://api.anthropic.com</li>
                          <li>常用模型: claude-3-5-sonnet-latest、claude-3-5-haiku-latest、claude-3-opus-latest</li>
                          <li>API Key 从 console.anthropic.com 获取</li>
                        </ul>
                      </>
                    )}
                    {aiProviderType === 'gemini' && (
                      <>
                        <p className="font-medium mb-1">Google Gemini 配置:</p>
                        <ul className="space-y-0.5 list-disc list-inside">
                          <li>API地址: https://generativelanguage.googleapis.com</li>
                          <li>常用模型: gemini-1.5-pro、gemini-1.5-flash、gemini-2.0-flash</li>
                          <li>API Key 从 Google AI Studio 获取</li>
                        </ul>
                      </>
                    )}
                    {aiProviderType === 'dashscope_app' && (
                      <>
                        <p className="font-medium mb-1">阿里云百炼应用编排:</p>
                        <ul className="space-y-0.5 list-disc list-inside">
                          <li>API地址需包含 app_id，例如 https://dashscope.aliyuncs.com/api/v1/apps/&lt;app_id&gt;/completion</li>
                          <li>无需填写模型名，由应用编排内部决定</li>
                          <li>API Key 在 bailian.console.aliyun.com 中创建</li>
                        </ul>
                      </>
                    )}
                  </div>
                </>
              )}
            </div>
            <div className="modal-footer">
              <button type="button" onClick={closeModal} className="btn-ios-secondary" disabled={aiSettingsSaving}>
                取消
              </button>
              <button
                onClick={handleSaveAISettings}
                className="btn-ios-primary"
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
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 代理设置弹窗 */}
      {activeModal === 'proxy-settings' && proxySettingsAccount && (
        <div className="modal-overlay">
          <div className="modal-content max-w-md">
            <div className="modal-header">
              <h2 className="modal-title">代理设置</h2>
              <button onClick={closeModal} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              {proxySettingsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-6 h-6 animate-spin text-blue-500" />
                </div>
              ) : (
                <>
                  <div className="input-group">
                    <label className="input-label">账号</label>
                    <input
                      type="text"
                      value={proxySettingsAccount.id}
                      disabled
                      className="input-ios bg-slate-100 dark:bg-slate-700"
                    />
                  </div>

                  <div className="input-group">
                    <label className="input-label">代理类型</label>
                    <select
                      value={proxyType}
                      onChange={(e) => setProxyType(e.target.value as 'none' | 'http' | 'https' | 'socks5')}
                      className="input-ios"
                    >
                      <option value="none">不使用代理</option>
                      <option value="http">HTTP</option>
                      <option value="https">HTTPS</option>
                      <option value="socks5">SOCKS5</option>
                    </select>
                  </div>

                  {proxyType !== 'none' && (
                    <>
                      <div className="grid grid-cols-3 gap-3">
                        <div className="input-group col-span-2">
                          <label className="input-label">代理地址</label>
                          <input
                            type="text"
                            value={proxyHost}
                            onChange={(e) => setProxyHost(e.target.value)}
                            className="input-ios"
                            placeholder="127.0.0.1"
                          />
                        </div>
                        <div className="input-group">
                          <label className="input-label">端口</label>
                          <input
                            type="number"
                            value={proxyPort}
                            onChange={(e) => setProxyPort(e.target.value ? Number(e.target.value) : '')}
                            className="input-ios"
                            placeholder="7890"
                            min="1"
                            max="65535"
                          />
                        </div>
                      </div>

                      <div className="border-t border-slate-100 dark:border-slate-700 pt-4">
                        <p className="text-xs text-slate-500 dark:text-slate-400 mb-3">
                          代理认证（可选）
                        </p>
                        <div className="grid grid-cols-2 gap-3">
                          <div className="input-group">
                            <label className="input-label">用户名</label>
                            <input
                              type="text"
                              value={proxyUser}
                              onChange={(e) => setProxyUser(e.target.value)}
                              className="input-ios"
                              placeholder="可选"
                            />
                          </div>
                          <div className="input-group">
                            <label className="input-label">密码</label>
                            <input
                              type="password"
                              value={proxyPass}
                              onChange={(e) => setProxyPass(e.target.value)}
                              className="input-ios"
                              placeholder="可选"
                            />
                          </div>
                        </div>
                      </div>
                    </>
                  )}

                  <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg p-3 text-xs text-slate-500 dark:text-slate-400">
                    <p className="font-medium mb-1">说明：</p>
                    <ul className="space-y-0.5 list-disc list-inside">
                      <li>代理用于WebSocket连接和API请求</li>
                      <li>SOCKS5代理支持更好，推荐使用</li>
                      <li>修改代理后需要重启账号监听才能生效</li>
                    </ul>
                  </div>
                </>
              )}
            </div>
            <div className="modal-footer">
              <button type="button" onClick={closeModal} className="btn-ios-secondary" disabled={proxySettingsSaving}>
                取消
              </button>
              <button
                onClick={handleSaveProxySettings}
                className="btn-ios-primary"
                disabled={proxySettingsSaving || proxySettingsLoading}
              >
                {proxySettingsSaving ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    保存中...
                  </span>
                ) : (
                  '保存'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 消息等待时间设置弹窗 */}
      {activeModal === 'message-expire-time' && messageExpireTimeAccount && (
        <div className="modal-overlay">
          <div className="modal-content max-w-md">
            <div className="modal-header">
              <h2 className="modal-title">相同消息等待时间</h2>
              <button onClick={closeModal} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 text-sm text-blue-700 dark:text-blue-300">
                <p>账号: <span className="font-medium">{messageExpireTimeAccount.id}</span></p>
              </div>
              
              <div className="input-group">
                <label className="input-label">等待时间（秒）</label>
                <input
                  type="number"
                  value={messageExpireTime}
                  onChange={(e) => setMessageExpireTime(Math.max(0, Math.min(86400, parseInt(e.target.value) || 0)))}
                  className="input-ios"
                  min={0}
                  max={86400}
                  step={60}
                />
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  {messageExpireTime === 0 
                    ? '当前设置: 不限制（每条消息都会回复）' 
                    : `当前设置: ${Math.floor(messageExpireTime / 60)} 分钟 ${messageExpireTime % 60} 秒`}
                </p>
              </div>

              <div className="grid grid-cols-5 gap-2">
                <button
                  type="button"
                  onClick={() => setMessageExpireTime(0)}
                  className={`px-3 py-2 text-xs rounded-lg border transition-colors ${messageExpireTime === 0 ? 'bg-blue-500 text-white border-blue-500' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'}`}
                >
                  不限制
                </button>
                <button
                  type="button"
                  onClick={() => setMessageExpireTime(300)}
                  className={`px-3 py-2 text-xs rounded-lg border transition-colors ${messageExpireTime === 300 ? 'bg-blue-500 text-white border-blue-500' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'}`}
                >
                  5分钟
                </button>
                <button
                  type="button"
                  onClick={() => setMessageExpireTime(600)}
                  className={`px-3 py-2 text-xs rounded-lg border transition-colors ${messageExpireTime === 600 ? 'bg-blue-500 text-white border-blue-500' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'}`}
                >
                  10分钟
                </button>
                <button
                  type="button"
                  onClick={() => setMessageExpireTime(1800)}
                  className={`px-3 py-2 text-xs rounded-lg border transition-colors ${messageExpireTime === 1800 ? 'bg-blue-500 text-white border-blue-500' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'}`}
                >
                  30分钟
                </button>
                <button
                  type="button"
                  onClick={() => setMessageExpireTime(3600)}
                  className={`px-3 py-2 text-xs rounded-lg border transition-colors ${messageExpireTime === 3600 ? 'bg-blue-500 text-white border-blue-500' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'}`}
                >
                  1小时
                </button>
              </div>

              <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg p-3 text-xs text-slate-500 dark:text-slate-400">
                <p className="font-medium mb-1">说明：</p>
                <ul className="space-y-0.5 list-disc list-inside">
                  <li>防止用户一直重复发同样的消息内容</li>
                  <li>设为0表示不限制，每条消息都会触发回复</li>
                  <li>相同消息在等待时间内不会重复回复</li>
                  <li>超过等待时间后，相同消息可以再次触发回复</li>
                </ul>
              </div>
            </div>
            <div className="modal-footer">
              <button type="button" onClick={closeModal} className="btn-ios-secondary" disabled={messageExpireTimeSaving}>
                取消
              </button>
              <button
                onClick={handleSaveMessageExpireTime}
                className="btn-ios-primary"
                disabled={messageExpireTimeSaving}
              >
                {messageExpireTimeSaving ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    保存中...
                  </span>
                ) : (
                  '保存'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 自动回复延迟设置弹窗 */}
      {activeModal === 'reply-delay' && replyDelayAccount && (
        <div className="modal-overlay">
          <div className="modal-content max-w-md">
            <div className="modal-header">
              <h2 className="modal-title">自动回复延迟</h2>
              <button onClick={closeModal} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 text-sm text-blue-700 dark:text-blue-300">
                <p>账号: <span className="font-medium">{replyDelayAccount.id}</span></p>
              </div>

              <div className="input-group">
                <label className="input-label">延迟时间（秒）</label>
                <input
                  type="number"
                  value={replyDelay}
                  onChange={(e) => setReplyDelay(Math.max(0, Math.min(3600, parseInt(e.target.value) || 0)))}
                  className="input-ios"
                  min={0}
                  max={3600}
                  step={1}
                />
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  {replyDelay === 0
                    ? '当前设置: 立即回复（不延迟）'
                    : `当前设置: 延迟 ${replyDelay} 秒后回复`}
                </p>
              </div>

              <div className="grid grid-cols-5 gap-2">
                <button
                  type="button"
                  onClick={() => setReplyDelay(0)}
                  className={`px-3 py-2 text-xs rounded-lg border transition-colors ${replyDelay === 0 ? 'bg-blue-500 text-white border-blue-500' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'}`}
                >
                  立即
                </button>
                <button
                  type="button"
                  onClick={() => setReplyDelay(3)}
                  className={`px-3 py-2 text-xs rounded-lg border transition-colors ${replyDelay === 3 ? 'bg-blue-500 text-white border-blue-500' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'}`}
                >
                  3秒
                </button>
                <button
                  type="button"
                  onClick={() => setReplyDelay(5)}
                  className={`px-3 py-2 text-xs rounded-lg border transition-colors ${replyDelay === 5 ? 'bg-blue-500 text-white border-blue-500' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'}`}
                >
                  5秒
                </button>
                <button
                  type="button"
                  onClick={() => setReplyDelay(10)}
                  className={`px-3 py-2 text-xs rounded-lg border transition-colors ${replyDelay === 10 ? 'bg-blue-500 text-white border-blue-500' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'}`}
                >
                  10秒
                </button>
                <button
                  type="button"
                  onClick={() => setReplyDelay(30)}
                  className={`px-3 py-2 text-xs rounded-lg border transition-colors ${replyDelay === 30 ? 'bg-blue-500 text-white border-blue-500' : 'border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800'}`}
                >
                  30秒
                </button>
              </div>

              <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg p-3 text-xs text-slate-500 dark:text-slate-400">
                <p className="font-medium mb-1">说明：</p>
                <ul className="space-y-0.5 list-disc list-inside">
                  <li>自动回复在发送前会先等待设定的秒数</li>
                  <li>设为0表示立即回复，不做延迟</li>
                  <li>延迟可让回复显得更自然，降低风控风险</li>
                  <li>最大可设置 3600 秒（1小时）</li>
                </ul>
              </div>
            </div>
            <div className="modal-footer">
              <button type="button" onClick={closeModal} className="btn-ios-secondary" disabled={replyDelaySaving}>
                取消
              </button>
              <button
                onClick={handleSaveReplyDelay}
                className="btn-ios-primary"
                disabled={replyDelaySaving}
              >
                {replyDelaySaving ? (
                  <span className="flex items-center gap-2">
                    <Loader2 className="w-4 h-4 animate-spin" />
                    保存中...
                  </span>
                ) : (
                  '保存'
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 禁止发货规则设置弹窗 */}
      {activeModal === 'delivery-disabled' && deliveryDisabledAccount && (
        <DeliveryBlockRulesModal
          accountId={deliveryDisabledAccount.id}
          accountDisplayId={deliveryDisabledAccount.id}
          onClose={closeModal}
        />
      )}

      {/* 人脸验证弹窗 */}
      {activeModal === 'face-verification' && faceVerificationAccount && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg">
            <div className="modal-header">
              <h2 className="modal-title">人脸验证</h2>
              <button onClick={closeModal} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body">
              <div className="bg-blue-50 dark:bg-blue-900/20 rounded-lg p-3 text-sm text-blue-700 dark:text-blue-300 mb-4">
                <p>账号: <span className="font-medium">{faceVerificationAccount.id}</span></p>
              </div>
              
              {faceVerificationLoading ? (
                <div className="flex flex-col items-center justify-center py-12">
                  <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
                  <p className="mt-3 text-sm text-slate-500">加载中...</p>
                </div>
              ) : faceVerificationScreenshot ? (
                <div className="space-y-4">
                  <div className="flex justify-center">
                    <img 
                      src={`${faceVerificationScreenshot.path}?t=${Date.now()}`} 
                      alt="人脸验证二维码" 
                      className="max-w-full rounded-lg border-2 border-slate-200 dark:border-slate-700"
                      style={{ maxHeight: '400px' }}
                    />
                  </div>
                  <div className="text-center">
                    <p className="text-sm text-slate-600 dark:text-slate-300">
                      请使用手机闲鱼APP扫描上方二维码完成验证
                    </p>
                    <p className="text-xs text-slate-400 mt-1">
                      创建时间: {faceVerificationScreenshot.created_time_str}
                    </p>
                  </div>
                  <div className="flex justify-center">
                    <button
                      onClick={() => setDeleteFaceConfirm(true)}
                      className="btn-ios-secondary text-red-600 hover:bg-red-50 dark:hover:bg-red-900/30"
                    >
                      <Trash2 className="w-4 h-4" />
                      删除截图
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex flex-col items-center justify-center py-12">
                  <ScanFace className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                  <p className="mt-3 text-sm text-slate-500">暂无验证截图</p>
                  <p className="text-xs text-slate-400 mt-1">当需要人脸验证时，截图会自动保存在这里</p>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button type="button" onClick={closeModal} className="btn-ios-secondary">
                关闭
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 确认收货消息弹窗 */}
      {activeModal === 'confirm-receipt' && confirmReceiptAccount && (
        <div className="modal-overlay">
          <div className="modal-content max-w-lg">
            <div className="modal-header">
              <h2 className="modal-title">确认收货消息</h2>
              <button type="button" onClick={closeModal} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              <div className="bg-emerald-50 dark:bg-emerald-900/20 rounded-lg p-3 text-sm text-emerald-700 dark:text-emerald-300">
                <p>账号: <span className="font-medium">{confirmReceiptAccount.id}</span></p>
              </div>
              
              {/* 启用开关 */}
              <div className="flex items-center justify-between py-3 border-b border-slate-100 dark:border-slate-700">
                <div>
                  <p className="font-medium text-slate-900 dark:text-slate-100">启用确认收货消息</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">开启后，买家确认收货时自动发送消息</p>
                </div>
                <label className="switch-ios">
                  <input
                    type="checkbox"
                    checked={confirmReceiptEnabled}
                    onChange={(e) => setConfirmReceiptEnabled(e.target.checked)}
                  />
                  <span className="switch-slider" />
                </label>
              </div>
              
              {/* 消息内容 */}
              <div className="input-group">
                <label className="input-label">消息内容</label>
                <textarea
                  value={confirmReceiptContent}
                  onChange={(e) => setConfirmReceiptContent(e.target.value)}
                  placeholder="例如：感谢您的购买，欢迎下次光临！如有问题请随时联系~"
                  className="input-ios min-h-[100px] resize-none"
                  maxLength={500}
                />
                <p className="input-hint">{confirmReceiptContent.length}/500</p>
              </div>
              
              {/* 图片上传 */}
              <div className="input-group">
                <label className="input-label">消息图片（可选）</label>
                <div className="flex items-start gap-3">
                  {confirmReceiptImage ? (
                    <div className="relative w-24 h-24 rounded-lg overflow-hidden border border-slate-200 dark:border-slate-700">
                      <img
                        src={confirmReceiptImage}
                        alt="消息图片"
                        className="w-full h-full object-cover"
                      />
                      <button
                        type="button"
                        onClick={() => setConfirmReceiptImage('')}
                        className="absolute top-1 right-1 p-1 bg-red-500 text-white rounded-full hover:bg-red-600"
                      >
                        <X className="w-3 h-3" />
                      </button>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={() => confirmReceiptImageInputRef.current?.click()}
                      disabled={confirmReceiptImageUploading}
                      className="w-24 h-24 flex flex-col items-center justify-center border-2 border-dashed border-slate-300 dark:border-slate-600 rounded-lg hover:border-emerald-500 dark:hover:border-emerald-500 transition-colors"
                    >
                      {confirmReceiptImageUploading ? (
                        <Loader2 className="w-6 h-6 text-slate-400 animate-spin" />
                      ) : (
                        <>
                          <ImagePlus className="w-6 h-6 text-slate-400" />
                          <span className="text-xs text-slate-400 mt-1">上传图片</span>
                        </>
                      )}
                    </button>
                  )}
                  <input
                    ref={confirmReceiptImageInputRef}
                    type="file"
                    accept="image/*"
                    onChange={handleConfirmReceiptImageUpload}
                    className="hidden"
                  />
                </div>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
                  支持 JPG、PNG、GIF 格式，最大 5MB
                </p>
                <p className="text-xs text-amber-600 dark:text-amber-400 mt-1">
                  发送顺序：如果同时配置了图片和文字，将先发送图片，再发送文字内容
                </p>
              </div>

              {/* 使用说明 */}
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                <p className="text-xs text-blue-600 dark:text-blue-400">
                  <strong>使用说明：</strong><br />
                  • 当买家点击「确认收货」后，系统会自动向买家发送此消息<br />
                  • 可用于感谢购买、引导好评、推荐其他商品等<br />
                  • 每笔订单只会发送一次确认收货消息
                </p>
              </div>
            </div>
            <div className="modal-footer">
              <button type="button" onClick={closeModal} className="btn-ios-secondary">
                取消
              </button>
              <button
                type="button"
                onClick={handleSaveConfirmReceipt}
                disabled={confirmReceiptSaving}
                className="btn-ios-primary"
              >
                {confirmReceiptSaving && <Loader2 className="w-4 h-4 animate-spin" />}
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 自动评价配置弹窗 */}
      {activeModal === 'auto-rate' && autoRateAccount && (
        <div className="modal-overlay">
          <div className="modal-content max-w-md">
            <div className="modal-header">
              <h2 className="modal-title">自动评价配置</h2>
              <button onClick={closeModal} className="modal-close">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="modal-body space-y-4">
              <div className="input-group">
                <label className="input-label">账号</label>
                <input
                  type="text"
                  value={autoRateAccount.id}
                  disabled
                  className="input-ios bg-slate-100 dark:bg-slate-700"
                />
              </div>
              
              {/* 启用开关 */}
              <div className="flex items-center justify-between py-3 border-b border-slate-100 dark:border-slate-700">
                <div>
                  <p className="font-medium text-slate-900 dark:text-slate-100">启用自动评价</p>
                  <p className="text-xs text-slate-500 dark:text-slate-400">开启后，收到评价请求时自动评价买家</p>
                </div>
                <button
                  type="button"
                  onClick={() => setAutoRateEnabled(!autoRateEnabled)}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors ${
                    autoRateEnabled ? 'bg-blue-600' : 'bg-slate-300 dark:bg-slate-600'
                  }`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                      autoRateEnabled ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
              </div>
              
              {/* 评价类型选择 */}
              <div className="input-group">
                <label className="input-label">评价内容来源</label>
                <div className="flex gap-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="rateType"
                      value="text"
                      checked={autoRateType === 'text'}
                      onChange={() => setAutoRateType('text')}
                      className="w-4 h-4 text-blue-600"
                    />
                    <span className="text-sm text-slate-700 dark:text-slate-300">固定文字</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="rateType"
                      value="api"
                      checked={autoRateType === 'api'}
                      onChange={() => setAutoRateType('api')}
                      className="w-4 h-4 text-blue-600"
                    />
                    <span className="text-sm text-slate-700 dark:text-slate-300">API获取</span>
                  </label>
                </div>
              </div>
              
              {/* 固定文字输入 */}
              {autoRateType === 'text' && (
                <div className="input-group">
                  <label className="input-label">评价内容</label>
                  <textarea
                    value={autoRateTextContent}
                    onChange={(e) => setAutoRateTextContent(e.target.value)}
                    placeholder="例如：不错的买家，交易愉快！"
                    className="input-ios min-h-[80px] resize-none"
                    maxLength={200}
                  />
                  <p className="input-hint">{autoRateTextContent.length}/200</p>
                </div>
              )}
              
              {/* API地址输入 */}
              {autoRateType === 'api' && (
                <div className="input-group">
                  <label className="input-label">API地址</label>
                  <input
                    type="text"
                    value={autoRateApiUrl}
                    onChange={(e) => setAutoRateApiUrl(e.target.value)}
                    placeholder="https://example.com/api/rate"
                    className="input-ios"
                  />
                  <p className="input-hint">API返回的全部内容将作为评价内容，超时时间30秒</p>
                </div>
              )}

              {/* 使用说明 */}
              <div className="p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg">
                <p className="text-xs text-blue-600 dark:text-blue-400">
                  <strong>使用说明：</strong><br />
                  • 当收到「快给ta一个评价吧」消息时，系统会自动评价买家<br />
                  • 固定文字：使用您设置的固定评价内容<br />
                  • API获取：请求API地址，将返回内容作为评价内容<br />
                  • 评价成功后会自动更新订单的评价状态
                </p>
              </div>
            </div>
            <div className="modal-footer">
              <button type="button" onClick={closeModal} className="btn-ios-secondary">
                取消
              </button>
              <button
                type="button"
                onClick={handleSaveAutoRate}
                disabled={autoRateSaving}
                className="btn-ios-primary"
              >
                {autoRateSaving && <Loader2 className="w-4 h-4 animate-spin" />}
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 删除账号确认弹窗 */}
      <ConfirmModal
        isOpen={deleteAccountConfirm.open}
        title="删除确认"
        message="确定要删除这个账号吗？删除后无法恢复。"
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={() => deleteAccountConfirm.id && handleDelete(deleteAccountConfirm.id)}
        onCancel={() => setDeleteAccountConfirm({ open: false, id: null })}
      />

      {/* 删除人脸验证截图确认弹窗 */}
      <ConfirmModal
        isOpen={deleteFaceConfirm}
        title="删除确认"
        message="确定要删除该验证截图吗？"
        confirmText="删除"
        cancelText="取消"
        type="danger"
        loading={deleting}
        onConfirm={handleDeleteFaceVerification}
        onCancel={() => setDeleteFaceConfirm(false)}
      />

      {/* 导入弹窗 */}
      {showImportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50" onClick={() => !importing && setShowImportModal(false)}>
          <div className="bg-white dark:bg-slate-800 rounded-xl shadow-xl w-full max-w-md mx-4 p-6" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold text-slate-800 dark:text-slate-200">导入账号数据</h3>
              <button onClick={() => !importing && setShowImportModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 拖拽/选择文件区域 */}
            <div
              className={`border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors ${
                importFile
                  ? 'border-green-300 bg-green-50 dark:border-green-700 dark:bg-green-900/20'
                  : 'border-slate-300 dark:border-slate-600 hover:border-blue-400 dark:hover:border-blue-500'
              }`}
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation() }}
              onDrop={(e) => {
                e.preventDefault()
                e.stopPropagation()
                const file = e.dataTransfer.files[0]
                if (file && file.name.endsWith('.xlsx')) {
                  setImportFile(file)
                } else {
                  addToast({ type: 'warning', message: '请选择 .xlsx 格式的文件' })
                }
              }}
              onClick={() => {
                const input = document.createElement('input')
                input.type = 'file'
                input.accept = '.xlsx'
                input.onchange = (e) => {
                  const file = (e.target as HTMLInputElement).files?.[0]
                  if (file) setImportFile(file)
                }
                input.click()
              }}
            >
              {importFile ? (
                <div className="space-y-2">
                  <CheckCircle className="w-10 h-10 text-green-500 mx-auto" />
                  <p className="text-sm font-medium text-slate-700 dark:text-slate-300">{importFile.name}</p>
                  <p className="text-xs text-slate-500">{(importFile.size / 1024).toFixed(1)} KB</p>
                </div>
              ) : (
                <div className="space-y-2">
                  <Upload className="w-10 h-10 text-slate-400 mx-auto" />
                  <p className="text-sm text-slate-600 dark:text-slate-400">拖拽文件到此处，或点击选择文件</p>
                  <p className="text-xs text-slate-400">支持 .xlsx 格式</p>
                </div>
              )}
            </div>

            {/* 操作按钮 */}
            <div className="flex gap-3 mt-6">
              <button
                onClick={() => handleImport(false)}
                disabled={!importFile || importing}
                className="flex-1 btn-ios-secondary disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                保存
              </button>
              <button
                onClick={() => handleImport(true)}
                disabled={!importFile || importing}
                className="flex-1 btn-ios-primary disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {importing ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                保存并全部启用
              </button>
            </div>

            <p className="text-xs text-slate-400 dark:text-slate-500 mt-3 text-center">
              「保存」按Excel中状态导入 · 「保存并全部启用」强制启用所有账号
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
