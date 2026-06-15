import { useState, useEffect } from 'react'
import { Users as UsersIcon, RefreshCw, Plus, Trash2 } from 'lucide-react'
import { addUser, getUsers, deleteUser } from '@/api/admin'
import { Button, Form, Input, Modal, Popconfirm, Space } from '@arco-design/web-react'
import { useUIStore } from '@/store/uiStore'
import { useAuthStore } from '@/store/authStore'
import { PageLoading } from '@/components/common/Loading'
import type { User } from '@/types'

export function Users() {
  const { addToast } = useUIStore()
  const { isAuthenticated, token, _hasHydrated } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [users, setUsers] = useState<User[]>([])
  const [showAddModal, setShowAddModal] = useState(false)
  const [creating, setCreating] = useState(false)
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

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

  const handleDelete = async (userId: number) => {
    try {
      await deleteUser(userId)
      addToast({ type: 'success', message: '删除成功' })
      loadUsers()
    } catch {
      addToast({ type: 'error', message: '删除失败' })
    }
  }

  const handleCreateUser = async () => {
    if (!username.trim()) {
      addToast({ type: 'warning', message: '请输入用户名' })
      return
    }
    if (!email.trim()) {
      addToast({ type: 'warning', message: '请输入邮箱' })
      return
    }
    if (!password) {
      addToast({ type: 'warning', message: '请输入密码' })
      return
    }
    if (password.length < 6) {
      addToast({ type: 'warning', message: '密码长度不能少于6位' })
      return
    }

    try {
      setCreating(true)
      const result = await addUser({
        username: username.trim(),
        email: email.trim(),
        password,
      })
      if (result.success) {
        addToast({ type: 'success', message: '用户创建成功' })
        setShowAddModal(false)
        setUsername('')
        setEmail('')
        setPassword('')
        loadUsers()
      } else {
        addToast({ type: 'error', message: result.message || '创建用户失败' })
      }
    } catch (error: unknown) {
      const axiosError = error as { response?: { data?: { detail?: string; message?: string } } }
      const detail = axiosError.response?.data?.detail || axiosError.response?.data?.message
      addToast({ type: 'error', message: detail || '创建用户失败' })
    } finally {
      setCreating(false)
    }
  }

  if (loading) {
    return <PageLoading />
  }

  return (
    <div className="space-y-4">
      {/* Users List */}
      <div className="vben-card">
        <div className="accounts-page-intro">
          <h1>用户管理</h1>
          <p>管理系统用户账号</p>
        </div>
        <div className="flex gap-3">
          <div className="accounts-toolbar">
            <div className="accounts-filter-row accounts-filter-row--lined">
              <div className="accounts-action-row">
                <Space className="accounts-toolbar-right">
                  <Button 
                    type="primary"
                    onClick={() => setShowAddModal(true)} className="accounts-header-btn">
                    <Plus />
                    添加用户
                  </Button>
                  <Button onClick={loadUsers} className="accounts-header-btn">
                    <RefreshCw />
                    刷新
                  </Button>
                </Space>
              </div>
            </div>
          </div>
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
                        <Popconfirm
                          title="确定要删除这个用户吗？"
                          content="此操作不可恢复。"
                          okText="删除"
                          cancelText="取消"
                          okButtonProps={{ status: 'danger' }}
                          onOk={() => handleDelete(user.user_id)}
                        >
                          <button
                            className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                            title="删除"
                          >
                            <Trash2 className="w-4 h-4 text-red-500" />
                          </button>
                        </Popconfirm>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
      <Modal
        title="添加用户"
        visible={showAddModal}
        onCancel={() => {
          if (creating) return
          setShowAddModal(false)
        }}
        onOk={handleCreateUser}
        confirmLoading={creating}
        autoFocus={false}
        focusLock
      >
        <Form layout="vertical">
          <Form.Item label="用户名" required>
            <Input
              value={username}
              onChange={setUsername}
              placeholder="请输入用户名"
            />
          </Form.Item>
          <Form.Item label="邮箱" required>
            <Input
              value={email}
              onChange={setEmail}
              placeholder="请输入邮箱"
            />
          </Form.Item>
          <Form.Item label="密码" required>
            <Input.Password
              value={password}
              onChange={setPassword}
              placeholder="请输入密码，至少6位"
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  )
}
