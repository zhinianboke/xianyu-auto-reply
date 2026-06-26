import { useMemo, useState } from 'react'
import { Loader2, X } from 'lucide-react'
import { addUser, updateUser, type AdminUserApiItem, type CreateAdminUserPayload, type UpdateAdminUserPayload } from '@/api/admin'
import { useUIStore } from '@/store/uiStore'
import { getApiErrorMessage } from '@/utils/request'
import type { User, UserRole, UserStatus } from '@/types'

interface Props {
  initial: User | null
  onClose: () => void
  onSaved: (user: User, mode: 'create' | 'update') => void
}

interface UserFormState {
  username: string
  email: string
  phone: string
  password: string
  confirmPassword: string
  role: UserRole
  status: UserStatus
  account_limit: string
  expire_at: string
}

// 后端到期日为北京时间 naive 字符串（如 '2026-06-25T14:30:00'），
// datetime-local 输入框需要 'YYYY-MM-DDTHH:MM:SS' 格式，直接截取前 19 位即可。
const toDatetimeLocalValue = (value?: string | null): string => {
  if (!value) return ''
  return value.slice(0, 19)
}

const createInitialState = (initial: User | null): UserFormState => ({
  username: initial?.username ?? '',
  email: initial?.email ?? '',
  phone: initial?.phone ?? '',
  password: '',
  confirmPassword: '',
  role: initial?.role ?? (initial?.is_admin ? 'ADMIN' : 'MEMBER'),
  status: initial?.status ?? 'ACTIVE',
  account_limit: initial?.account_limit != null ? String(initial.account_limit) : '',
  expire_at: toDatetimeLocalValue(initial?.expire_at),
})

const roleOptions: Array<{ value: UserRole; label: string }> = [
  { value: 'ADMIN', label: '管理员' },
  { value: 'OPERATOR', label: '运营人员' },
  { value: 'MEMBER', label: '普通用户' },
]

const toUser = (item: AdminUserApiItem): User => ({
  user_id: item.id,
  username: item.username,
  email: item.email,
  phone: item.phone,
  role: item.role,
  status: item.status,
  is_admin: item.is_admin,
  account_limit: item.account_limit,
  expire_at: item.expire_at,
})

export function UserFormModal({ initial, onClose, onSaved }: Props) {
  const { addToast } = useUIStore()
  const [form, setForm] = useState<UserFormState>(() => createInitialState(initial))
  const [saving, setSaving] = useState(false)

  const isEditMode = !!initial
  const statusOptions = useMemo<Array<{ value: UserStatus; label: string }>>(() => {
    const options: Array<{ value: UserStatus; label: string }> = [
      { value: 'ACTIVE', label: '正常' },
      { value: 'INACTIVE', label: '停用' },
      { value: 'SUSPENDED', label: '封禁' },
    ]
    if (initial?.status === 'DELETED') {
      options.push({ value: 'DELETED', label: '已删除' })
    }
    return options
  }, [initial?.status])

  const updateField = <K extends keyof UserFormState>(field: K, value: UserFormState[K]) => {
    setForm((current) => ({ ...current, [field]: value }))
  }

  const handleSave = async () => {
    const username = form.username.trim()
    const email = form.email.trim()
    const phone = form.phone.trim()
    const password = form.password.trim()
    const confirmPassword = form.confirmPassword.trim()
    const accountLimitText = form.account_limit.trim()
    const accountLimit = accountLimitText === '' ? null : Number(accountLimitText)

    if (!username) {
      addToast({ type: 'warning', message: '请输入用户名' })
      return
    }

    if (!email) {
      addToast({ type: 'warning', message: '请输入邮箱' })
      return
    }

    if (!/^\S+@\S+\.\S+$/.test(email)) {
      addToast({ type: 'warning', message: '请输入正确的邮箱地址' })
      return
    }

    if (!isEditMode && !password) {
      addToast({ type: 'warning', message: '请输入登录密码' })
      return
    }

    if (password && password.length < 6) {
      addToast({ type: 'warning', message: '密码长度不能少于6位' })
      return
    }

    if (password !== confirmPassword) {
      addToast({ type: 'warning', message: '两次输入的密码不一致' })
      return
    }

    if (accountLimitText && (accountLimit === null || !Number.isInteger(accountLimit) || accountLimit <= 0)) {
      addToast({ type: 'warning', message: '可添加账号数量必须为正整数' })
      return
    }

    setSaving(true)
    try {
      // 到期日：留空表示永不过期（显式传 null 清空），非空则传 'YYYY-MM-DDTHH:MM:SS'
      const expireAtValue = form.expire_at.trim() ? form.expire_at.trim() : null

      const basePayload = {
        username,
        email,
        phone,
        role: form.role,
        status: form.status,
        account_limit: accountLimit,
        expire_at: expireAtValue,
      }

      let result
      if (isEditMode && initial) {
        const payload: UpdateAdminUserPayload = {
          ...basePayload,
          password: password || undefined,
        }
        result = await updateUser(initial.user_id, payload)
      } else {
        const payload: CreateAdminUserPayload = {
          ...basePayload,
          password,
        }
        result = await addUser(payload)
      }

      if (!result.success || !result.data?.user) {
        addToast({ type: 'error', message: result.message || (isEditMode ? '更新用户失败' : '创建用户失败') })
        return
      }

      addToast({ type: 'success', message: result.message || (isEditMode ? '用户更新成功' : '用户创建成功') })
      onSaved(toUser(result.data.user), isEditMode ? 'update' : 'create')
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, isEditMode ? '更新用户失败' : '创建用户失败') })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="modal-overlay">
      <div className="modal-content max-w-2xl">
        <div className="modal-header">
          <h2 className="modal-title">{isEditMode ? '编辑用户' : '新增用户'}</h2>
          <button className="modal-close" onClick={onClose} disabled={saving}>
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="modal-body">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="input-group">
              <label className="input-label">用户名 <span className="text-red-500">*</span></label>
              <input
                className="input-ios"
                value={form.username}
                onChange={(event) => updateField('username', event.target.value)}
                placeholder="请输入用户名"
                maxLength={64}
              />
            </div>
            <div className="input-group">
              <label className="input-label">邮箱 <span className="text-red-500">*</span></label>
              <input
                className="input-ios"
                type="email"
                value={form.email}
                onChange={(event) => updateField('email', event.target.value)}
                placeholder="请输入邮箱"
              />
            </div>
            <div className="input-group">
              <label className="input-label">手机号</label>
              <input
                className="input-ios"
                value={form.phone}
                onChange={(event) => updateField('phone', event.target.value)}
                placeholder="请输入手机号"
                maxLength={32}
              />
            </div>
            <div className="input-group">
              <label className="input-label">角色 <span className="text-red-500">*</span></label>
              <select
                className="input-ios"
                value={form.role}
                onChange={(event) => updateField('role', event.target.value as UserRole)}
              >
                {roleOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
            <div className="input-group">
              <label className="input-label">状态 <span className="text-red-500">*</span></label>
              <select
                className="input-ios"
                value={form.status}
                onChange={(event) => updateField('status', event.target.value as UserStatus)}
              >
                {statusOptions.map((option) => (
                  <option key={option.value} value={option.value}>{option.label}</option>
                ))}
              </select>
            </div>
            <div className="input-group">
              <label className="input-label">可添加账号数量</label>
              <input
                className="input-ios"
                type="number"
                min={1}
                step={1}
                value={form.account_limit}
                onChange={(event) => updateField('account_limit', event.target.value)}
                placeholder="留空表示不限制"
              />
            </div>
            <div className="input-group">
              <label className="input-label">到期日</label>
              <input
                className="input-ios"
                type="datetime-local"
                step={1}
                value={form.expire_at}
                onChange={(event) => updateField('expire_at', event.target.value)}
              />
              <p className="text-xs text-slate-400 mt-1">留空表示永不过期；精确到秒</p>
            </div>
            <div className="input-group">
              <label className="input-label">{isEditMode ? '新密码' : '登录密码'} {!isEditMode && <span className="text-red-500">*</span>}</label>
              <input
                className="input-ios"
                type="password"
                value={form.password}
                onChange={(event) => updateField('password', event.target.value)}
                placeholder={isEditMode ? '不填写则不修改' : '请输入登录密码'}
                maxLength={128}
              />
            </div>
            <div className="input-group sm:col-span-2">
              <label className="input-label">确认密码 {(form.password || !isEditMode) && <span className="text-red-500">*</span>}</label>
              <input
                className="input-ios"
                type="password"
                value={form.confirmPassword}
                onChange={(event) => updateField('confirmPassword', event.target.value)}
                placeholder={isEditMode ? '如填写了新密码，请再次输入' : '请再次输入登录密码'}
                maxLength={128}
              />
            </div>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn-ios-secondary" onClick={onClose} disabled={saving}>取消</button>
          <button className="btn-ios-primary" onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="w-4 h-4 animate-spin" />}
            {isEditMode ? '保存修改' : '创建用户'}
          </button>
        </div>
      </div>
    </div>
  )
}

export default UserFormModal
