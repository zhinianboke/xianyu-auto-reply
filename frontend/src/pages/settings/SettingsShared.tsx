import { createContext, useContext, useEffect, useRef, useState } from 'react'
import type { ChangeEvent, ReactNode } from 'react'
import { Button, Empty, Modal, Space, Switch, Table, TimePicker, type TableColumnProps } from '@arco-design/web-react'
import { Copy, Download, Eye, EyeOff, Key, RefreshCw, Save, Upload } from 'lucide-react'
import { getAccounts } from '@/api/accounts'
import { changePassword, downloadDatabaseBackup, getBackupList, getSystemSettings, reloadSystemCache, runDatabaseBackup, testAIConnection, testEmailSend, updateSystemSettings, uploadDatabaseBackup } from '@/api/settings'
import { ButtonLoading, PageLoading } from '@/components/common/Loading'
import { Select } from '@/components/common/Select'
import { useAuthStore } from '@/store/authStore'
import { useUIStore } from '@/store/uiStore'
import type { Account, SystemSettings } from '@/types'

export function SettingsPageShell({
  actions,
  children,
}: {
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="space-y-4">
      <div className="vben-card">
        <div className="vben-card-body">
          {children}
          {actions ? <div className="settings-page-actions">{actions}</div> : null}
        </div>
      </div>
    </div>
  )
}

export function SettingsSectionHeader({
  title,
  description,
}: {
  title: string
  description?: string
}) {
  return (
    <div className="settings-section-header">
      <h2 className="settings-section-title">{title}</h2>
      {description ? <p className="settings-section-description">{description}</p> : null}
    </div>
  )
}

export function SettingsSection({
  title,
  description,
  children,
}: {
  title: string
  description?: string
  children: ReactNode
}) {
  return (
    <section className="space-y-4">
      <SettingsSectionHeader title={title} description={description} />
      {children}
    </section>
  )
}

export function useSettingsResource() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated, user } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [settings, setSettings] = useState<SystemSettings | null>(null)

  const loadSettings = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getSystemSettings()
      if (result.success && result.data) {
        setSettings(result.data)
      }
    } catch {
      addToast({ type: 'error', message: '加载系统设置失败' })
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!settings) return
    try {
      setSaving(true)
      const result = await updateSystemSettings(settings)
      if (result.success) {
        addToast({ type: 'success', message: '设置保存成功' })
      } else {
        addToast({ type: 'error', message: result.message || '保存失败' })
      }
    } catch {
      addToast({ type: 'error', message: '保存设置失败' })
    } finally {
      setSaving(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadSettings()
  }, [_hasHydrated, isAuthenticated, token])

  return {
    addToast,
    user,
    loading,
    saving,
    settings,
    setSettings,
    loadSettings,
    handleSave,
  }
}

export function SystemSettingsSection() {
  const { settings, setSettings } = useSettingsResourceContext()

  return (
    <SettingsSection title="基础设置" description="注册、登录与默认提示相关设置。">
      <div className="flex items-center justify-between py-3 border-b border-slate-100 dark:border-slate-700">
        <div>
          <p className="font-medium text-slate-900 dark:text-slate-100">允许用户注册</p>
          <p className="text-sm text-slate-500 dark:text-slate-400">开启后允许新用户注册账号</p>
        </div>
        <label className="switch-ios">
          <input
            type="checkbox"
            checked={Boolean(settings?.registration_enabled ?? false)}
            onChange={(e) => setSettings((s) => s ? { ...s, registration_enabled: e.target.checked } : null)}
          />
          <span className="switch-slider"></span>
        </label>
      </div>

      <div className="flex items-center justify-between py-3">
        <div>
          <p className="font-medium text-slate-900 dark:text-slate-100">显示默认登录信息</p>
          <p className="text-sm text-slate-500 dark:text-slate-400">登录页面显示默认账号密码提示</p>
        </div>
        <label className="switch-ios">
          <input
            type="checkbox"
            checked={Boolean(settings?.show_default_login_info ?? false)}
            onChange={(e) => setSettings((s) => s ? { ...s, show_default_login_info: e.target.checked } : null)}
          />
          <span className="switch-slider"></span>
        </label>
      </div>

      <div className="flex items-center justify-between py-3 border-t border-slate-100 dark:border-slate-700">
        <div>
          <p className="font-medium text-slate-900 dark:text-slate-100">登录滑动验证码</p>
          <p className="text-sm text-slate-500 dark:text-slate-400">开启后账号密码登录需要完成滑动验证</p>
        </div>
        <label className="switch-ios">
          <input
            type="checkbox"
            checked={Boolean(settings?.login_captcha_enabled ?? true)}
            onChange={(e) => setSettings((s) => s ? { ...s, login_captcha_enabled: e.target.checked } : null)}
          />
          <span className="switch-slider"></span>
        </label>
      </div>
    </SettingsSection>
  )
}

export function SmtpSettingsSection() {
  const { addToast, settings, setSettings } = useSettingsResourceContext()
  const [showSmtpPassword, setShowSmtpPassword] = useState(false)

  const handleTestEmail = async () => {
    const email = prompt('请输入测试邮箱地址:')
    if (!email) return
    try {
      const result = await testEmailSend(email)
      if (result.success) {
        addToast({ type: 'success', message: '测试邮件发送成功' })
      } else {
        addToast({ type: 'error', message: result.message || '发送测试邮件失败' })
      }
    } catch {
      addToast({ type: 'error', message: '发送测试邮件失败' })
    }
  }

  return (
    <SettingsSection title="SMTP 邮件配置" description="用于验证码、注册通知等邮件发送。">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="input-group">
          <label className="input-label">SMTP服务器</label>
          <input
            type="text"
            value={settings?.smtp_server || ''}
            onChange={(e) => setSettings((s) => s ? { ...s, smtp_server: e.target.value } : null)}
            placeholder="smtp.qq.com"
            className="input-ios"
          />
          <p className="text-xs text-slate-400 mt-1">如：smtp.qq.com、smtp.gmail.com</p>
        </div>
        <div className="input-group">
          <label className="input-label">SMTP端口</label>
          <input
            type="number"
            value={settings?.smtp_port || 587}
            onChange={(e) => setSettings((s) => s ? { ...s, smtp_port: parseInt(e.target.value) } : null)}
            placeholder="587"
            className="input-ios"
          />
          <p className="text-xs text-slate-400 mt-1">通常为587(TLS)或465(SSL)</p>
        </div>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="input-group">
          <label className="input-label">发件邮箱</label>
          <input
            type="email"
            value={settings?.smtp_user || ''}
            onChange={(e) => setSettings((s) => s ? { ...s, smtp_user: e.target.value } : null)}
            placeholder="your-email@qq.com"
            className="input-ios"
          />
          <p className="text-xs text-slate-400 mt-1">用于发送邮件的邮箱地址</p>
        </div>
        <div className="input-group">
          <label className="input-label">邮箱密码/授权码</label>
          <div className="relative">
            <input
              type={showSmtpPassword ? 'text' : 'password'}
              value={settings?.smtp_password || ''}
              onChange={(e) => setSettings((s) => s ? { ...s, smtp_password: e.target.value } : null)}
              placeholder="输入密码或授权码"
              className="input-ios w-full pr-20"
            />
            <div className="absolute right-2 top-1/2 -translate-y-1/2 flex gap-1">
              <button
                onClick={() => setShowSmtpPassword(!showSmtpPassword)}
                className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                title={showSmtpPassword ? '隐藏' : '显示'}
              >
                {showSmtpPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
              <button
                type="button"
                onClick={() => {
                  if (settings?.smtp_password) {
                    navigator.clipboard.writeText(settings.smtp_password)
                    addToast({ type: 'success', message: '已复制到剪贴板' })
                  }
                }}
                className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
                title="复制"
              >
                <Copy className="w-4 h-4" />
              </button>
            </div>
          </div>
          <p className="text-xs text-slate-400 mt-1">邮箱密码或应用专用密码(QQ邮箱需要授权码)</p>
        </div>
      </div>
      <div className="input-group">
        <label className="input-label">发件人显示名（可选）</label>
        <input
          type="text"
          value={settings?.smtp_from || ''}
          onChange={(e) => setSettings((s) => s ? { ...s, smtp_from: e.target.value } : null)}
          placeholder="闲鱼自动回复系统"
          className="input-ios"
        />
        <p className="text-xs text-slate-400 mt-1">邮件发件人显示的名称，留空则使用邮箱地址</p>
      </div>
      <Button 
        type="primary"
        onClick={handleTestEmail} className="accounts-header-btn">
        发送测试邮件
      </Button>
    </SettingsSection>
  )
}

export function AiSettingsSection() {
  const { addToast, settings, setSettings } = useSettingsResourceContext()
  const { _hasHydrated, isAuthenticated, token } = useAuthStore()
  const [showApiKey, setShowApiKey] = useState(false)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [testAccountId, setTestAccountId] = useState('')
  const [testingAI, setTestingAI] = useState(false)

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    const loadAccounts = async () => {
      try {
        const data = await getAccounts()
        setAccounts(data)
        if (data.length > 0 && !testAccountId) {
          setTestAccountId(data[0].id)
        }
      } catch {
        // ignore
      }
    }
    loadAccounts()
  }, [_hasHydrated, isAuthenticated, token, testAccountId])

  const handleTestAI = async () => {
    if (!testAccountId) {
      addToast({ type: 'warning', message: '请先选择一个账号' })
      return
    }

    setTestingAI(true)
    try {
      if (settings) {
        await updateSystemSettings(settings)
      }
      const result = await testAIConnection(testAccountId)
      if (result.success) {
        addToast({ type: 'success', message: result.message || 'AI 连接测试成功' })
      } else {
        addToast({ type: 'error', message: result.message || 'AI 连接测试失败' })
      }
    } catch {
      addToast({ type: 'error', message: 'AI 连接测试失败' })
    } finally {
      setTestingAI(false)
    }
  }

  return (
    <SettingsSection title="AI 设置" description="配置模型接口、鉴权信息和连接测试。">
      <div className="input-group">
        <label className="input-label">API 地址</label>
        <input
          type="text"
          value={settings?.ai_api_url || 'https://dashscope.aliyuncs.com/compatible-mode/v1'}
          onChange={(e) => setSettings((s) => s ? { ...s, ai_api_url: e.target.value } : null)}
          className="input-ios"
        />
        <p className="text-xs text-slate-400 mt-1">无需补全 /chat/completions</p>
      </div>
      <div className="input-group">
        <label className="input-label">API Key</label>
        <div className="relative">
          <input
            type={showApiKey ? 'text' : 'password'}
            value={settings?.ai_api_key || ''}
            onChange={(e) => setSettings((s) => s ? { ...s, ai_api_key: e.target.value } : null)}
            placeholder="sk-..."
            className="input-ios w-full pr-20"
          />
          <div className="absolute right-2 top-1/2 -translate-y-1/2 flex gap-1">
            <button
              type="button"
              onClick={() => setShowApiKey(!showApiKey)}
              className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              title={showApiKey ? '隐藏' : '显示'}
            >
              {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
            <button
              type="button"
              onClick={() => {
                if (settings?.ai_api_key) {
                  navigator.clipboard.writeText(settings.ai_api_key)
                  addToast({ type: 'success', message: '已复制到剪贴板' })
                }
              }}
              className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              title="复制"
            >
              <Copy className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
      <div className="input-group">
        <label className="input-label">模型</label>
        <input
          type="text"
          value={settings?.ai_model || 'qwen-plus'}
          onChange={(e) => setSettings((s) => s ? { ...s, ai_model: e.target.value } : null)}
          className="input-ios"
        />
        <p className="text-xs text-slate-400 mt-1">如: qwen-plus、qwen-turbo、gpt-3.5-turbo、gpt-4</p>
      </div>
      <div className="flex items-end gap-2">
        <div className="flex-1">
          <label className="input-label">测试账号</label>
          <Select
            value={testAccountId}
            onChange={setTestAccountId}
            options={accounts.map((a) => ({ value: a.id, label: a.id }))}
            placeholder="选择账号"
          />
        </div>
        <button onClick={handleTestAI} className="btn-ios-secondary" disabled={testingAI || !testAccountId}>
          {testingAI ? '测试中...' : '测试 AI 连接'}
        </button>
      </div>
      <div className="bg-slate-50 dark:bg-slate-800/50 rounded-lg p-3 text-xs text-slate-500 dark:text-slate-400">
        <p className="font-medium mb-1">常见 AI 服务配置:</p>
        <ul className="space-y-0.5 list-disc list-inside">
          <li>阿里云通义千问: https://dashscope.aliyuncs.com/compatible-mode/v1</li>
          <li>OpenAI: https://api.openai.com/v1</li>
          <li>国内中转: 使用服务商提供的 API 地址</li>
        </ul>
      </div>
    </SettingsSection>
  )
}

export function ProfileSection() {
  const { addToast } = useUIStore()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [changingPassword, setChangingPassword] = useState(false)
  const [showCurrentPassword, setShowCurrentPassword] = useState(false)
  const [showNewPassword, setShowNewPassword] = useState(false)
  const [showConfirmPassword, setShowConfirmPassword] = useState(false)

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
        addToast({ type: 'success', message: '密码修改成功' })
        setCurrentPassword('')
        setNewPassword('')
        setConfirmPassword('')
      } else {
        addToast({ type: 'error', message: result.message || '密码修改失败' })
      }
    } catch {
      addToast({ type: 'error', message: '密码修改失败' })
    } finally {
      setChangingPassword(false)
    }
  }

  return (
    <SettingsSection title="" description="">
      <div className="input-group">
        <label className="input-label">当前密码</label>
        <PasswordField
          value={currentPassword}
          onChange={setCurrentPassword}
          placeholder="请输入当前密码"
          visible={showCurrentPassword}
          onToggleVisible={() => setShowCurrentPassword(!showCurrentPassword)}
        />
      </div>
      <div className="input-group">
        <label className="input-label">新密码</label>
        <PasswordField
          value={newPassword}
          onChange={setNewPassword}
          placeholder="请输入新密码"
          visible={showNewPassword}
          onToggleVisible={() => setShowNewPassword(!showNewPassword)}
        />
      </div>
      <div className="input-group">
        <label className="input-label">确认新密码</label>
        <PasswordField
          value={confirmPassword}
          onChange={setConfirmPassword}
          placeholder="请再次输入新密码"
          visible={showConfirmPassword}
          onToggleVisible={() => setShowConfirmPassword(!showConfirmPassword)}
        />
      </div>
      <Button 
        type="primary"
        onClick={handleChangePassword} disabled={changingPassword} className="accounts-header-btn">
        {changingPassword ? <ButtonLoading /> : <Key />}
        修改密码
      </Button>
    </SettingsSection>
  )
}

export function BackupSection() {
  const { addToast, user, settings, setSettings } = useSettingsResourceContext()
  const backupFileRef = useRef<HTMLInputElement>(null)
  const [uploadingBackup, setUploadingBackup] = useState(false)
  const [reloadingCache, setReloadingCache] = useState(false)
  const [runningBackup, setRunningBackup] = useState(false)
  const [backupListLoading, setBackupListLoading] = useState(false)
  const [backupList, setBackupList] = useState<Array<{ filename: string; size: number; size_mb: number; created_time?: string; modified_time: string }>>([])

  const handleDownloadBackup = () => {
    const url = downloadDatabaseBackup()
    const link = document.createElement('a')
    link.href = url
    link.download = ''
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  const handleUploadBackup = async (e: ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    if (!file.name.endsWith('.db')) {
      addToast({ type: 'error', message: '只支持 .db 格式的数据库文件' })
      return
    }
    Modal.confirm({
      title: '恢复数据库',
      content: '恢复数据库将覆盖所有当前数据，确定要继续吗？',
      okButtonProps: { status: 'danger' },
      onOk: async () => {
        try {
          setUploadingBackup(true)
          const result = await uploadDatabaseBackup(file)
          if (result.success) {
            addToast({ type: 'success', message: '数据库恢复成功' })
          } else {
            addToast({ type: 'error', message: result.message || '数据库恢复失败' })
          }
        } catch {
          addToast({ type: 'error', message: '数据库恢复失败' })
        } finally {
          setUploadingBackup(false)
          e.target.value = ''
        }
      },
      onCancel: () => {
        e.target.value = ''
      },
    })
  }

  const handleReloadCache = async () => {
    try {
      setReloadingCache(true)
      const result = await reloadSystemCache()
      if (result.success) {
        addToast({ type: 'success', message: '系统缓存已刷新' })
      } else {
        addToast({ type: 'error', message: result.message || '刷新缓存失败' })
      }
    } catch {
      addToast({ type: 'error', message: '刷新缓存失败' })
    } finally {
      setReloadingCache(false)
    }
  }

  const loadBackupList = async () => {
    try {
      setBackupListLoading(true)
      const result = await getBackupList()
      setBackupList(result.backups || [])
    } catch {
      addToast({ type: 'error', message: '加载备份记录失败' })
    } finally {
      setBackupListLoading(false)
    }
  }

  const handleRunBackup = async () => {
    try {
      setRunningBackup(true)
      const result = await runDatabaseBackup()
      if (result.success) {
        addToast({ type: 'success', message: '数据库备份成功' })
        loadBackupList()
      } else {
        addToast({ type: 'error', message: result.message || '数据库备份失败' })
      }
    } catch {
      addToast({ type: 'error', message: '数据库备份失败' })
    } finally {
      setRunningBackup(false)
    }
  }

  useEffect(() => {
    if (user?.is_admin) {
      loadBackupList()
    }
  }, [user?.is_admin])

  const backupColumns: TableColumnProps<{ filename: string; size: number; size_mb: number; created_time?: string; modified_time: string }>[] = [
    {
      title: '文件名',
      dataIndex: 'filename',
      render: (value) => <span className="whitespace-nowrap font-medium text-slate-700 dark:text-slate-200">{value}</span>,
    },
    {
      title: '大小',
      dataIndex: 'size_mb',
      render: (value) => <span>{value} MB</span>,
    },
    {
      title: '创建时间',
      dataIndex: 'created_time',
      render: (value) => <span className="whitespace-nowrap text-slate-500 dark:text-slate-400">{value || '-'}</span>,
    },
    {
      title: '更新时间',
      dataIndex: 'modified_time',
      render: (value) => <span className="whitespace-nowrap text-slate-500 dark:text-slate-400">{value}</span>,
    },
  ]

  return (
    <section className="space-y-4">
      <div className="accounts-page-intro">
        <h1>数据库备份</h1>
        <p>用于数据库下载、恢复和系统缓存刷新</p>
      </div>
      {user?.is_admin && (
        <div className="space-y-5">
          <div className="grid grid-cols-1 lg:grid-cols-[1.2fr_0.8fr] gap-6">
            <div className="space-y-3">
              <div className="settings-section-header">
                <h2 className="settings-section-title">备份操作</h2>
                <p className="settings-section-description">支持手动创建、下载、恢复数据库，并刷新系统缓存。</p>
              </div>
              <Space wrap>
                <Button type="primary" onClick={handleRunBackup} className="accounts-header-btn" loading={runningBackup}>
                  <Download />
                  立即备份
                </Button>
                <Button type="primary" onClick={handleDownloadBackup} className="accounts-header-btn">
                  <Download />
                  下载数据库
                </Button>
                <Button
                  onClick={() => backupFileRef.current?.click()}
                  disabled={uploadingBackup}
                  className="accounts-header-btn"
                >
                  {uploadingBackup ? <ButtonLoading /> : <Upload />}
                  恢复数据库
                </Button>
                <input
                  ref={backupFileRef}
                  type="file"
                  accept=".db"
                  className="hidden"
                  onChange={handleUploadBackup}
                  disabled={uploadingBackup}
                />
                <Button onClick={handleReloadCache} disabled={reloadingCache} className="accounts-header-btn">
                  {reloadingCache ? <ButtonLoading /> : <RefreshCw />}
                  刷新缓存
                </Button>
              </Space>
              <p className="text-xs text-slate-500 dark:text-slate-400">注意：恢复数据库将覆盖所有当前数据，请谨慎操作。</p>
            </div>

            <div className="space-y-3">
              <div className="settings-section-header">
                <h2 className="settings-section-title">自动备份</h2>
                <p className="settings-section-description">按每天固定时间自动生成数据库备份。</p>
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="input-group">
                  <label className="input-label">启用自动备份</label>
                  <div className="pt-2">
                    <Switch
                      checked={Boolean(settings?.auto_backup_enabled ?? false)}
                      onChange={(checked) => {
                        setSettings((s) => s ? { ...s, auto_backup_enabled: checked } : null)
                        addToast({
                          type: checked ? 'success' : 'info',
                          message: checked ? '已启用自动备份' : '已关闭自动备份',
                        })
                      }}
                    />
                  </div>
                </div>
                <div className="input-group">
                  <label className="input-label">每日备份时间</label>
                  <TimePicker
                    format="HH:mm"
                    value={typeof settings?.auto_backup_time === 'string' ? settings.auto_backup_time : '03:00'}
                    onChange={(value) => setSettings((s) => s ? { ...s, auto_backup_time: value || '03:00' } : null)}
                    className="w-full"
                    placeholder="选择时间"
                  />
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-3">
            <div className="settings-section-header">
              <h2 className="settings-section-title">备份记录</h2>
              <p className="settings-section-description">查看服务器上现有的数据库备份文件记录。</p>
            </div>
            <Table
              className="accounts-arco-table"
              columns={backupColumns}
              data={backupList}
              rowKey="filename"
              borderCell={false}
              pagination={false}
              loading={backupListLoading}
              scroll={{ x: 'max-content' }}
              noDataElement={<Empty description="暂无备份记录" />}
            />
          </div>
        </div>
      )}

      {!user?.is_admin && (
        <div className="rounded-lg border border-dashed border-slate-200 bg-slate-50 px-4 py-5 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-800/40 dark:text-slate-400">
          当前页面仅用于管理员数据库备份与恢复。
        </div>
      )}
    </section>
  )
}

function PasswordField({
  value,
  onChange,
  placeholder,
  visible,
  onToggleVisible,
}: {
  value: string
  onChange: (value: string) => void
  placeholder: string
  visible: boolean
  onToggleVisible: () => void
}) {
  const { addToast } = useUIStore()

  return (
    <div className="relative">
      <input
        type={visible ? 'text' : 'password'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="input-ios w-full pr-20"
      />
      <div className="absolute right-2 top-1/2 -translate-y-1/2 flex gap-1">
        <button
          type="button"
          onClick={onToggleVisible}
          className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
          title={visible ? '隐藏' : '显示'}
        >
          {visible ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
        </button>
        <button
          type="button"
          onClick={() => {
            if (value) {
              navigator.clipboard.writeText(value)
              addToast({ type: 'success', message: '已复制到剪贴板' })
            }
          }}
          className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
          title="复制"
        >
          <Copy className="w-4 h-4" />
        </button>
      </div>
    </div>
  )
}

type SettingsResource = ReturnType<typeof useSettingsResource>

const SettingsResourceContext = createContext<SettingsResource | null>(null)

function SettingsResourceProvider({ value, children }: { value: SettingsResource; children: ReactNode }) {
  return <SettingsResourceContext.Provider value={value}>{children}</SettingsResourceContext.Provider>
}

function useSettingsResourceContext() {
  const context = useContext(SettingsResourceContext)
  if (!context) {
    throw new Error('Settings resource context is not available')
  }
  return context
}

export function SettingsResourceBoundary({
  resource,
  children,
}: {
  resource: SettingsResource
  children: ReactNode
}) {
  if (resource.loading) {
    return <PageLoading />
  }

  return <SettingsResourceProvider value={resource}>{children}</SettingsResourceProvider>
}

export function SettingsActions({ onRefresh, onSave, saving }: { onRefresh: () => void; onSave: () => void; saving: boolean }) {
  return (
    <div className="flex gap-2">
      <Button onClick={onRefresh} className="accounts-header-btn">
        <RefreshCw />
        刷新
      </Button>
      <Button 
        type="primary"
        onClick={onSave} disabled={saving} className="accounts-header-btn">
        {saving ? <ButtonLoading /> : <Save />}
        保存设置
      </Button>
    </div>
  )
}
