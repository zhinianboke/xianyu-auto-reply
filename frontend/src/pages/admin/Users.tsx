import { useState, useEffect } from 'react'
import { Users as UsersIcon, RefreshCw, Plus, Trash2 } from 'lucide-react'
import { getUsers, deleteUser } from '@/api/admin'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import type { User } from '@/types'

export function Users() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [users, setUsers] = useState<User[]>([])

  const loadUsers = async () => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    try {
      setLoading(true)
      const result = await getUsers()
      if (result.success) {
        setUsers(result.data || [])
      }
    } catch {
      addToast({ type: 'error', message: '加载用户列表失败' })
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (!_hasHydrated || !isAuthenticated || !token) return
    loadUsers()
  }, [_hasHydrated, isAuthenticated, token])

  // TODO: 后端暂未实现 PUT /admin/users/{user_id} 接口
  const handleNotImplemented = (action: string) => {
    addToast({ type: 'warning', message: `${action}功能后端暂未实现` })
  }

  const handleDelete = async (userId: number) => {
    if (!confirm('确定要删除这个用户吗？此操作不可恢复！')) return
    try {
      await deleteUser(userId)
      addToast({ type: 'success', message: '删除成功' })
      loadUsers()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    }
  }

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="page-title">用户管理</h1>
          <p className="page-description">管理系统用户账号</p>
        </div>
        <div className="flex gap-3">
          {/* TODO: 后端暂未实现 POST /admin/users 接口 */}
          <button onClick={() => handleNotImplemented('添加用户')} className="btn-ios-primary">
            <Plus className="w-4 h-4" />
            添加用户
          </button>
          <button onClick={loadUsers} className="btn-ios-secondary">
            <RefreshCw className="w-4 h-4" />
            刷新
          </button>
        </div>
      </div>

      {/* Users List */}
      <div className="vben-card">
        <div className="vben-card-header flex items-center justify-between">
          <h2 className="vben-card-title">
            <UsersIcon className="w-4 h-4" />
            用户列表
          </h2>
          <span className="badge-primary">{users.length} 个用户</span>
        </div>
        <div className="overflow-x-auto">
          <table className="table-ios">
            <thead>
              <tr>
                <th>ID</th>
                <th>用户名</th>
                <th>邮箱</th>
                <th>角色</th>
                <th>操作</th>
              </tr>
            </thead>
            <tbody>
              {users.length === 0 ? (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-slate-500 dark:text-slate-400">
                    <div className="flex flex-col items-center gap-2">
                      <UsersIcon className="w-12 h-12 text-slate-300 dark:text-slate-600" />
                      <p>暂无用户数据</p>
                    </div>
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.user_id}>
                    <td className="font-medium">{user.user_id}</td>
                    <td className="font-medium text-blue-600 dark:text-blue-400">{user.username}</td>
                    <td className="text-slate-500 dark:text-slate-400">{user.email || '-'}</td>
                    <td>
                      {user.is_admin ? (
                        <span className="badge-warning">管理员</span>
                      ) : (
                        <span className="badge-gray">普通用户</span>
                      )}
                    </td>
                    <td>
                      <div className="flex gap-1">
                        <button
                          onClick={() => handleDelete(user.user_id)}
                          className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                          title="删除"
                        >
                          <Trash2 className="w-4 h-4 text-red-500" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* 提示信息 */}
      <div className="vben-card">
        <div className="vben-card-body">
          <p className="text-sm text-slate-500 dark:text-slate-400">
            提示：用户可通过注册页面自行注册账号。管理员可在此页面删除用户。
          </p>
        </div>
      </div>
    </div>
  )
}
