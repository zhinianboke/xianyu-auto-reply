import { useEffect, useState } from 'react'
import { Users as UsersIcon, RefreshCw, Plus, ChevronLeft, ChevronRight, Loader2, Pencil, Power, PowerOff, Wallet, Search, X } from 'lucide-react'
import { getUsers, deleteUser, updateUser } from '@/api/admin'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import { ConfirmModal } from '@/components/common/ConfirmModal'
import { UserFormModal } from './UserFormModal'
import { UserRechargeModal } from './UserRechargeModal'
import { getApiErrorMessage } from '@/utils/request'
import type { User } from '@/types'

const roleLabelMap: Record<string, string> = {
  ADMIN: '管理员',
  OPERATOR: '运营人员',
  MEMBER: '普通用户',
}

const statusLabelMap: Record<string, string> = {
  ACTIVE: '正常',
  INACTIVE: '停用',
  SUSPENDED: '封禁',
  DELETED: '已删除',
}

const statusClassMap: Record<string, string> = {
  ACTIVE: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
  INACTIVE: 'bg-slate-100 text-slate-700 dark:bg-slate-700/50 dark:text-slate-300',
  SUSPENDED: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
  DELETED: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
}

// 格式化到期日展示（后端为北京时间 naive 字符串，无需做时区转换）
const formatExpireAt = (value?: string | null): string => {
  if (!value) return '永不过期'
  // 形如 '2026-06-25T14:30:00' -> '2026-06-25 14:30:00'
  return value.replace('T', ' ').slice(0, 19)
}

// 判断是否已到期（到期日存在且早于当前时间）
const isExpired = (value?: string | null): boolean => {
  if (!value) return false
  const time = new Date(value).getTime()
  return Number.isFinite(time) && time < Date.now()
}

export function Users() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated, user: currentUser, updateUser: updateAuthUser } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [users, setUsers] = useState<User[]>([])

  const [currentPage, setCurrentPage] = useState(1)
  const [pageSize, setPageSize] = useState(20)
  const [total, setTotal] = useState(0)

  // 用户名搜索：输入框值与已应用的查询值分离，避免输入过程中频繁请求
  const [searchUsername, setSearchUsername] = useState('')
  const [appliedUsername, setAppliedUsername] = useState('')

  const [statusConfirm, setStatusConfirm] = useState<{ open: boolean; user: User | null; action: 'enable' | 'disable' }>({ open: false, user: null, action: 'disable' })
  const [statusSubmitting, setStatusSubmitting] = useState(false)
  const [showFormModal, setShowFormModal] = useState(false)
  const [editingUser, setEditingUser] = useState<User | null>(null)
  const [rechargingUser, setRechargingUser] = useState<User | null>(null)

  const loadUsers = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getUsers({ page: currentPage, pageSize, username: appliedUsername })
      if (!result.success) {
        setUsers([])
        setTotal(0)
        addToast({ type: 'error', message: result.message || '加载用户列表失败' })
        return
      }
      setUsers(result.data || [])
      setTotal(result.total || 0)
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, '加载用户列表失败') })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadUsers()
  }, [_hasHydrated, isAuthenticated, token, currentPage, pageSize, appliedUsername])

  // 执行用户名搜索：应用输入值并回到第一页
  const handleSearch = () => {
    const keyword = searchUsername.trim()
    setAppliedUsername(keyword)
    setCurrentPage(1)
  }

  // 重置用户名搜索条件
  const handleResetSearch = () => {
    setSearchUsername('')
    setAppliedUsername('')
    setCurrentPage(1)
  }

  const handleOpenCreate = () => {
    setEditingUser(null)
    setShowFormModal(true)
  }

  const handleOpenEdit = (user: User) => {
    setEditingUser(user)
    setShowFormModal(true)
  }

  const handleSaved = async (user: User, mode: 'create' | 'update') => {
    setShowFormModal(false)
    setEditingUser(null)
    if (currentUser?.user_id === user.user_id) {
      updateAuthUser(user)
    }
    if (mode === 'create' && currentPage !== 1) {
      setCurrentPage(1)
      return
    }
    await loadUsers()
  }

  const closeStatusConfirm = () => {
    setStatusConfirm({ open: false, user: null, action: 'disable' })
  }

  const handleStatusChange = async (user: User, action: 'enable' | 'disable') => {
    setStatusSubmitting(true)
    try {
      const result = action === 'enable'
        ? await updateUser(user.user_id, { status: 'ACTIVE' })
        : await deleteUser(user.user_id)
      if (!result.success) {
        addToast({ type: 'error', message: result.message || (action === 'enable' ? '启用失败' : '停用失败') })
        return
      }
      addToast({ type: 'success', message: result.message || (action === 'enable' ? '用户已启用' : '用户已停用') })
      closeStatusConfirm()
      await loadUsers()
    } catch (error) {
      addToast({ type: 'error', message: getApiErrorMessage(error, action === 'enable' ? '启用失败' : '停用失败') })
    } finally {
      setStatusSubmitting(false)
    }
  }

  const totalPages = Math.ceil(total / pageSize)
  const startIndex = (currentPage - 1) * pageSize + 1
  const endIndex = Math.min(currentPage * pageSize, total)
  const isEnableAction = statusConfirm.action === 'enable'

  // 仅首屏（未应用搜索条件）整屏展示加载态；应用搜索后保留搜索框，避免输入框中途消失
  if (loading && users.length === 0 && !appliedUsername) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">用户管理</h1>
          <p className="page-description">管理系统用户账号</p>
        </div>
        <div className="flex gap-3">
          <button onClick={handleOpenCreate} className="btn-ios-primary">
            <Plus className="w-4 h-4" />
            添加用户
          </button>
          <button onClick={loadUsers} disabled={loading} className="btn-ios-secondary">
            {loading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <RefreshCw className="w-4 h-4" />
            )}
            刷新
          </button>
        </div>
      </div>

      <div className="vben-card flex flex-col" style={{ height: 'calc(100vh - 280px)', minHeight: '400px' }}>
        <div className="vben-card-header flex-shrink-0 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <h2 className="vben-card-title">
            <UsersIcon className="w-4 h-4" />
            用户列表
          </h2>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400 pointer-events-none" />
              <input
                type="text"
                value={searchUsername}
                onChange={(e) => setSearchUsername(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                placeholder="搜索用户名"
                className="w-44 sm:w-52 pl-8 pr-8 py-1.5 text-sm border border-slate-300 dark:border-slate-600 rounded-md bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-blue-500/40"
              />
              {searchUsername && (
                <button
                  type="button"
                  onClick={handleResetSearch}
                  className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
                  title="清空"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
            <button onClick={handleSearch} className="btn-ios-secondary">
              <Search className="w-4 h-4" />
              搜索
            </button>
            <span className="badge-primary whitespace-nowrap">{total} 个用户</span>
          </div>
        </div>
        <div className="flex-1 overflow-auto">
          <table className="table-ios">
            <thead className="sticky top-0 bg-white dark:bg-slate-800 z-10">
              <tr>
                <th>ID</th>
                <th>用户名</th>
                <th>邮箱</th>
                <th>手机号</th>
                <th>角色</th>
                <th>可添加账号数</th>
                <th>余额</th>
                <th>到期日</th>
                <th>状态</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 ? (
                <tr>
                  <td colSpan={10} className="text-center py-8 text-slate-500 dark:text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <UsersIcon className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>{appliedUsername ? `未找到用户名包含「${appliedUsername}」的用户` : '暂无用户数据'}</p>
                    </div>
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.user_id}>
                    <td className="font-medium">{user.user_id}</td>
                    <td className="font-medium text-blue-600 dark:text-blue-400">{user.username}</td>
                    <td className="text-slate-500 dark:text-slate-400">{user.email || '-'}</td>
                    <td className="text-slate-500 dark:text-slate-400">{user.phone || '-'}</td>
                    <td>
                      <span className={user.role === 'ADMIN' ? 'badge-warning' : 'badge-gray'}>
                        {roleLabelMap[user.role || (user.is_admin ? 'ADMIN' : 'MEMBER')] || '普通用户'}
                      </span>
                    </td>
                    <td className="text-slate-500 dark:text-slate-400">{user.account_limit ?? '-'}</td>
                    <td className="font-medium text-slate-700 dark:text-slate-300 tabular-nums">¥{user.balance ?? '0.00'}</td>
                    <td className={`whitespace-nowrap text-sm ${isExpired(user.expire_at) ? 'text-red-500 font-medium' : 'text-slate-500 dark:text-slate-400'}`}>
                      {formatExpireAt(user.expire_at)}
                      {isExpired(user.expire_at) && <span className="ml-1">(已到期)</span>}
                    </td>
                    <td>
                      <span className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ${statusClassMap[user.status || 'ACTIVE'] || statusClassMap.ACTIVE}`}>
                        {statusLabelMap[user.status || 'ACTIVE'] || '正常'}
                      </span>
                    </td>
                    <td>
                      <div className="flex flex-wrap gap-2">
                        <button
                          onClick={() => handleOpenEdit(user)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg hover:bg-blue-50 dark:hover:bg-blue-900/20 text-blue-600 dark:text-blue-400 transition-colors"
                          title="编辑"
                        >
                          <Pencil className="w-4 h-4" />
                          编辑
                        </button>
                        <button
                          onClick={() => setRechargingUser(user)}
                          className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg hover:bg-amber-50 dark:hover:bg-amber-900/20 text-amber-600 dark:text-amber-400 transition-colors"
                          title="余额调整"
                        >
                          <Wallet className="w-4 h-4" />
                          余额调整
                        </button>
                        {user.status === 'INACTIVE' ? (
                          <button
                            onClick={() => setStatusConfirm({ open: true, user, action: 'enable' })}
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg hover:bg-emerald-50 dark:hover:bg-emerald-900/20 text-emerald-600 dark:text-emerald-400 transition-colors"
                            title="启用"
                          >
                            <Power className="w-4 h-4" />
                            启用
                          </button>
                        ) : (
                          <button
                            onClick={() => setStatusConfirm({ open: true, user, action: 'disable' })}
                            disabled={user.status === 'DELETED'}
                            className="inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 text-red-500 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                            title="停用"
                          >
                            <PowerOff className="w-4 h-4" />
                            停用
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {total > 0 && (
          <div className="flex-shrink-0 vben-card-footer flex flex-col sm:flex-row items-center justify-between gap-4 px-4 py-3 border-t border-slate-200 dark:border-slate-700">
            <div className="flex items-center gap-2 text-sm text-slate-500 dark:text-slate-400">
              <span>每页</span>
              <select
                value={pageSize}
                onChange={(e) => {
                  setPageSize(Number(e.target.value))
                  setCurrentPage(1)
                }}
                className="px-2 py-1 border border-slate-300 dark:border-slate-600 rounded bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300"
              >
                <option value={10}>10</option>
                <option value={20}>20</option>
                <option value={50}>50</option>
                <option value={100}>100</option>
              </select>
              <span>条</span>
              <span className="ml-2">
                显示 {startIndex}-{endIndex} 条，共 {total} 条
              </span>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                disabled={currentPage === 1}
                className="p-2 rounded border border-slate-300 dark:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-700"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="px-3 py-1 text-sm text-slate-600 dark:text-slate-400">
                第 {currentPage} / {totalPages || 1} 页
              </span>
              <button
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                disabled={currentPage >= totalPages}
                className="p-2 rounded border border-slate-300 dark:border-slate-600 disabled:opacity-50 disabled:cursor-not-allowed hover:bg-slate-100 dark:hover:bg-slate-700"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>

      <div className="vben-card">
        <div className="vben-card-body">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            提示：管理员可在此页面新增、编辑、停用和启用用户账号，停用后用户将无法登录，但历史数据会保留。
          </p>
        </div>
      </div>

      {showFormModal && (
        <UserFormModal
          initial={editingUser}
          onClose={() => {
            setShowFormModal(false)
            setEditingUser(null)
          }}
          onSaved={handleSaved}
        />
      )}

      <ConfirmModal
        isOpen={statusConfirm.open}
        title={isEnableAction ? '启用确认' : '停用确认'}
        message={isEnableAction
          ? `确定要启用用户「${statusConfirm.user?.username || ''}」吗？启用后该用户可恢复登录。`
          : `确定要停用用户「${statusConfirm.user?.username || ''}」吗？停用后该用户将无法登录，但历史数据会保留。`}
        confirmText={isEnableAction ? '启用' : '停用'}
        cancelText="取消"
        type={isEnableAction ? 'info' : 'danger'}
        loading={statusSubmitting}
        onConfirm={() => statusConfirm.user && handleStatusChange(statusConfirm.user, statusConfirm.action)}
        onCancel={closeStatusConfirm}
      />

      {rechargingUser && (
        <UserRechargeModal
          user={rechargingUser}
          onClose={() => setRechargingUser(null)}
          onSuccess={() => {
            setRechargingUser(null)
            loadUsers()
          }}
        />
      )}
    </div>
  )
}
