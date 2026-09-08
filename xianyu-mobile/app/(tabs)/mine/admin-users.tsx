import { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Alert,
  Modal,
  Switch,
  RefreshControl,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button, Input, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { useAuthStore } from '@/stores/auth';
import {
  getAdminUsers,
  createAdminUser,
  updateAdminUser,
  deleteAdminUser,
  rechargeUser,
  type AdminUser,
} from '@/api/wrappers/admin';

/** 角色 → 文案 */
function roleLabel(role?: string): string {
  switch (role) {
    case 'ADMIN':
      return '管理员';
    case 'OPERATOR':
      return '运营';
    case 'MEMBER':
      return '普通成员';
    default:
      return role || '普通成员';
  }
}

/** 状态 → 文案 */
function statusLabel(status?: string): string {
  switch (status) {
    case 'active':
      return '正常';
    case 'disabled':
    case 'inactive':
      return '禁用';
    default:
      return status || '正常';
  }
}

/** ISO 时间 → 可读字符串，无法解析时原样返回 */
function formatDate(iso?: string): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  const p = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(
    d.getHours(),
  )}:${p(d.getMinutes())}`;
}

/** 创建用户的角色选项 */
const ROLE_OPTIONS = ['MEMBER', 'OPERATOR', 'ADMIN'];

export default function AdminUsersScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const user = useAuthStore((s) => s.user);

  const [users, setUsers] = useState<AdminUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // 新增用户
  const [createVisible, setCreateVisible] = useState(false);
  const [createForm, setCreateForm] = useState({
    username: '',
    email: '',
    password: '',
    role: 'MEMBER',
  });
  const [creating, setCreating] = useState(false);

  // 编辑用户
  const [editVisible, setEditVisible] = useState(false);
  const [editTarget, setEditTarget] = useState<AdminUser | null>(null);
  const [editForm, setEditForm] = useState({
    username: '',
    email: '',
    role: '',
    status: '',
    account_limit: '',
    balance: '',
    expire_at: '',
    is_admin: false,
  });
  const [editSaving, setEditSaving] = useState(false);

  // 充值
  const [rechargeVisible, setRechargeVisible] = useState(false);
  const [rechargeTarget, setRechargeTarget] = useState<AdminUser | null>(null);
  const [amount, setAmount] = useState('');
  const [recharging, setRecharging] = useState(false);

  const loadUsers = useCallback(async () => {
    setRefreshing(true);
    try {
      const list = await getAdminUsers();
      setUsers(list);
    } catch (e) {
      Alert.alert('加载失败', (e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  function resetCreateForm() {
    setCreateForm({ username: '', email: '', password: '', role: 'MEMBER' });
  }

  async function handleCreate() {
    const { username, email, password, role } = createForm;
    if (!username.trim() || !password.trim()) {
      Alert.alert('提示', '请填写用户名和密码');
      return;
    }
    setCreating(true);
    try {
      await createAdminUser(username.trim(), email.trim(), password, role);
      setCreateVisible(false);
      resetCreateForm();
      await loadUsers();
    } catch (e) {
      Alert.alert('创建失败', (e as Error).message);
    } finally {
      setCreating(false);
    }
  }

  function openEdit(u: AdminUser) {
    setEditTarget(u);
    setEditForm({
      username: u.username ?? '',
      email: u.email ?? '',
      role: u.role ?? '',
      status: u.status ?? '',
      account_limit: u.account_limit != null ? String(u.account_limit) : '',
      balance: u.balance ?? '',
      expire_at: u.expire_at ?? '',
      is_admin: !!u.is_admin,
    });
    setEditVisible(true);
  }

  async function handleEditSave() {
    if (!editTarget) return;
    const payload: Partial<AdminUser> = {
      username: editForm.username.trim(),
      email: editForm.email.trim(),
      role: editForm.role.trim(),
      status: editForm.status.trim(),
      balance: editForm.balance.trim(),
      expire_at: editForm.expire_at.trim(),
      is_admin: editForm.is_admin,
    };
    if (editForm.account_limit.trim() !== '') {
      const n = Number(editForm.account_limit);
      if (!isNaN(n)) payload.account_limit = n;
    }
    setEditSaving(true);
    try {
      await updateAdminUser(editTarget.id, payload);
      setUsers((prev) =>
        prev.map((u) => (u.id === editTarget.id ? { ...u, ...payload } : u)),
      );
      setEditVisible(false);
      setEditTarget(null);
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setEditSaving(false);
    }
  }

  function handleDelete(u: AdminUser) {
    Alert.alert(
      '删除用户',
      `确定删除用户「${u.username}」吗？此操作不可恢复。`,
      [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteAdminUser(u.id);
              setUsers((prev) => prev.filter((x) => x.id !== u.id));
            } catch (e) {
              Alert.alert('删除失败', (e as Error).message);
            }
          },
        },
      ],
      { cancelable: true },
    );
  }

  function openRecharge(u: AdminUser) {
    setRechargeTarget(u);
    setAmount('');
    setRechargeVisible(true);
  }

  async function handleRecharge() {
    if (!rechargeTarget) return;
    const val = amount.trim();
    if (val === '' || isNaN(Number(val))) {
      Alert.alert('提示', '请输入有效的充值金额');
      return;
    }
    setRecharging(true);
    try {
      await rechargeUser(rechargeTarget.id, val);
      setRechargeVisible(false);
      setRechargeTarget(null);
      await loadUsers();
    } catch (e) {
      Alert.alert('充值失败', (e as Error).message);
    } finally {
      setRecharging(false);
    }
  }

  // 非管理员：无权限提示
  if (!user?.is_admin) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <View style={styles.empty}>
          <Text style={[styles.emptyText, { color: c.textMuted }]}>
            无权限访问，仅管理员可查看
          </Text>
        </View>
      </SafeAreaView>
    );
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载用户..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <Button label="新增用户" onPress={() => setCreateVisible(true)} variant="secondary" />
      </View>

      <FlatList
        data={users}
        keyExtractor={(item) => String(item.id)}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={loadUsers} />
        }
        renderItem={({ item }) => {
          const isActive = statusLabel(item.status) === '正常';
          return (
            <Card style={styles.card}>
              <View style={styles.cardHeader}>
                <View style={styles.cardInfo}>
                  <View style={styles.nameRow}>
                    <Text style={[styles.username, { color: c.text }]} numberOfLines={1}>
                      {item.username}
                    </Text>
                    <View
                      style={[
                        styles.tag,
                        {
                          backgroundColor: item.is_admin ? c.primary : c.border,
                        },
                      ]}
                    >
                      <Text
                        style={[
                          styles.tagText,
                          { color: item.is_admin ? '#FFF' : c.textSecondary },
                        ]}
                      >
                        {roleLabel(item.role)}
                      </Text>
                    </View>
                    <View
                      style={[
                        styles.tag,
                        { backgroundColor: isActive ? c.success : c.textMuted },
                      ]}
                    >
                      <Text style={[styles.tagText, { color: '#FFF' }]}>
                        {statusLabel(item.status)}
                      </Text>
                    </View>
                  </View>
                  {item.email ? (
                    <Text style={[styles.email, { color: c.textMuted }]} numberOfLines={1}>
                      {item.email}
                    </Text>
                  ) : null}
                </View>
              </View>

              <View style={[styles.statsRow, { borderTopColor: c.border }]}>
                <View style={styles.stat}>
                  <Text style={[styles.statValue, { color: c.text }]}>
                    {item.cookie_count ?? 0}
                    {item.account_limit != null ? `/${item.account_limit}` : ''}
                  </Text>
                  <Text style={[styles.statLabel, { color: c.textMuted }]}>账号数</Text>
                </View>
                <View style={styles.stat}>
                  <Text style={[styles.statValue, { color: c.text }]} numberOfLines={1}>
                    {item.balance ? `¥${item.balance}` : '-'}
                  </Text>
                  <Text style={[styles.statLabel, { color: c.textMuted }]}>余额</Text>
                </View>
                <View style={styles.stat}>
                  <Text style={[styles.statValue, { color: c.text }]}>
                    {formatDate(item.expire_at)}
                  </Text>
                  <Text style={[styles.statLabel, { color: c.textMuted }]}>到期日</Text>
                </View>
              </View>

              <View style={styles.cardActions}>
                <Button
                  label="编辑"
                  variant="secondary"
                  onPress={() => openEdit(item)}
                  style={styles.cardBtn}
                />
                <Button
                  label="充值"
                  variant="secondary"
                  onPress={() => openRecharge(item)}
                  style={styles.cardBtn}
                />
                <Button
                  label="删除"
                  variant="danger"
                  onPress={() => handleDelete(item)}
                  style={styles.cardBtn}
                />
              </View>
            </Card>
          );
        }}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: c.textMuted }]}>暂无用户</Text>
          </View>
        }
        contentContainerStyle={styles.listContent}
      />

      {/* 新增用户 Modal */}
      <Modal
        visible={createVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setCreateVisible(false)}
      >
        <Pressable style={styles.modalOverlay} onPress={() => setCreateVisible(false)}>
          <Pressable
            style={[styles.modalCard, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>新增用户</Text>
              <Pressable onPress={() => setCreateVisible(false)} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>

            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>用户名</Text>
              <Input
                value={createForm.username}
                onChangeText={(v) => setCreateForm((f) => ({ ...f, username: v }))}
                placeholder="请输入用户名"
                autoCapitalize="none"
              />
            </View>
            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>邮箱</Text>
              <Input
                value={createForm.email}
                onChangeText={(v) => setCreateForm((f) => ({ ...f, email: v }))}
                placeholder="请输入邮箱（可选）"
                keyboardType="email-address"
                autoCapitalize="none"
              />
            </View>
            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>密码</Text>
              <Input
                value={createForm.password}
                onChangeText={(v) => setCreateForm((f) => ({ ...f, password: v }))}
                placeholder="请输入密码"
                secureTextEntry
              />
            </View>
            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>角色</Text>
              <View style={styles.roleChips}>
                {ROLE_OPTIONS.map((r) => (
                  <Pressable
                    key={r}
                    onPress={() => setCreateForm((f) => ({ ...f, role: r }))}
                    style={[
                      styles.chip,
                      {
                        backgroundColor:
                          createForm.role === r ? c.primary : c.surface,
                        borderColor: c.border,
                      },
                    ]}
                  >
                    <Text
                      style={[
                        styles.chipText,
                        { color: createForm.role === r ? '#FFF' : c.text },
                      ]}
                    >
                      {roleLabel(r)}
                    </Text>
                  </Pressable>
                ))}
              </View>
            </View>

            <View style={styles.modalActions}>
              <Button
                label="取消"
                variant="ghost"
                onPress={() => setCreateVisible(false)}
                style={styles.modalBtn}
              />
              <Button
                label="创建"
                onPress={handleCreate}
                loading={creating}
                disabled={creating}
                style={styles.modalBtn}
              />
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      {/* 编辑用户 Modal */}
      <Modal
        visible={editVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setEditVisible(false)}
      >
        <Pressable style={styles.modalOverlay} onPress={() => setEditVisible(false)}>
          <Pressable
            style={[styles.modalCard, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>编辑用户</Text>
              <Pressable onPress={() => setEditVisible(false)} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>

            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>用户名</Text>
              <Input
                value={editForm.username}
                onChangeText={(v) => setEditForm((f) => ({ ...f, username: v }))}
                autoCapitalize="none"
              />
            </View>
            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>邮箱</Text>
              <Input
                value={editForm.email}
                onChangeText={(v) => setEditForm((f) => ({ ...f, email: v }))}
                keyboardType="email-address"
                autoCapitalize="none"
              />
            </View>
            <View style={styles.fieldRow}>
              <View style={[styles.fieldGroup, { flex: 1 }]}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>角色</Text>
                <Input
                  value={editForm.role}
                  onChangeText={(v) => setEditForm((f) => ({ ...f, role: v }))}
                  placeholder="user / admin"
                  autoCapitalize="none"
                />
              </View>
              <View style={[styles.fieldGroup, { flex: 1 }]}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>状态</Text>
                <Input
                  value={editForm.status}
                  onChangeText={(v) => setEditForm((f) => ({ ...f, status: v }))}
                  placeholder="active / disabled"
                  autoCapitalize="none"
                />
              </View>
            </View>
            <View style={styles.fieldRow}>
              <View style={[styles.fieldGroup, { flex: 1 }]}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>账号限额</Text>
                <Input
                  value={editForm.account_limit}
                  onChangeText={(v) =>
                    setEditForm((f) => ({ ...f, account_limit: v }))
                  }
                  placeholder="数量"
                  keyboardType="numeric"
                />
              </View>
              <View style={[styles.fieldGroup, { flex: 1 }]}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>余额</Text>
                <Input
                  value={editForm.balance}
                  onChangeText={(v) => setEditForm((f) => ({ ...f, balance: v }))}
                  placeholder="0.00"
                  keyboardType="numeric"
                />
              </View>
            </View>
            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>到期时间</Text>
              <Input
                value={editForm.expire_at}
                onChangeText={(v) => setEditForm((f) => ({ ...f, expire_at: v }))}
                placeholder="YYYY-MM-DD HH:mm"
              />
            </View>
            <View style={styles.toggleRow}>
              <Text style={[styles.fieldLabel, { color: c.text }]}>管理员权限</Text>
              <Switch
                value={editForm.is_admin}
                onValueChange={(v) => setEditForm((f) => ({ ...f, is_admin: v }))}
                trackColor={{ false: c.border, true: c.primary }}
              />
            </View>

            <View style={styles.modalActions}>
              <Button
                label="取消"
                variant="ghost"
                onPress={() => setEditVisible(false)}
                style={styles.modalBtn}
              />
              <Button
                label="保存"
                onPress={handleEditSave}
                loading={editSaving}
                disabled={editSaving}
                style={styles.modalBtn}
              />
            </View>
          </Pressable>
        </Pressable>
      </Modal>

      {/* 充值 Modal */}
      <Modal
        visible={rechargeVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setRechargeVisible(false)}
      >
        <Pressable style={styles.modalOverlay} onPress={() => setRechargeVisible(false)}>
          <Pressable
            style={[styles.modalCard, { backgroundColor: c.surface }]}
            onPress={() => {}}
          >
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: c.text }]}>
                充值 - {rechargeTarget?.username}
              </Text>
              <Pressable onPress={() => setRechargeVisible(false)} hitSlop={8}>
                <Text style={[styles.closeBtn, { color: c.textMuted }]}>✕</Text>
              </Pressable>
            </View>

            <View style={styles.fieldGroup}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>充值金额</Text>
              <Input
                value={amount}
                onChangeText={setAmount}
                placeholder="请输入金额"
                keyboardType="numeric"
                autoFocus
              />
            </View>

            <View style={styles.modalActions}>
              <Button
                label="取消"
                variant="ghost"
                onPress={() => setRechargeVisible(false)}
                style={styles.modalBtn}
              />
              <Button
                label="确认充值"
                onPress={handleRecharge}
                loading={recharging}
                disabled={recharging}
                style={styles.modalBtn}
              />
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  listContent: { padding: spacing.lg, gap: spacing.md },
  card: { gap: spacing.md },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
  },
  cardInfo: { flex: 1 },
  nameRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    flexWrap: 'wrap',
  },
  username: { ...typography.body, fontWeight: '600' },
  email: { ...typography.small, marginTop: spacing.xs },
  tag: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: 4 },
  tagText: { ...typography.small, color: '#FFF' },
  statsRow: {
    flexDirection: 'row',
    borderTopWidth: 1,
    paddingTop: spacing.md,
  },
  stat: { flex: 1, alignItems: 'center' },
  statValue: { ...typography.body, fontWeight: '600', textAlign: 'center' },
  statLabel: { ...typography.small, marginTop: spacing.xs },
  cardActions: { flexDirection: 'row', gap: spacing.sm },
  cardBtn: { flex: 1 },
  empty: { alignItems: 'center', justifyContent: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  // Modal
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: spacing.lg,
  },
  modalCard: {
    width: '100%',
    maxWidth: 360,
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.md,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  modalTitle: { ...typography.heading },
  closeBtn: { fontSize: 22, paddingHorizontal: spacing.xs },
  fieldGroup: { gap: spacing.xs },
  fieldRow: { flexDirection: 'row', gap: spacing.md },
  fieldLabel: { ...typography.caption },
  roleChips: { flexDirection: 'row', gap: spacing.sm },
  chip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
    borderRadius: radius.xl,
    borderWidth: 1,
  },
  chipText: { ...typography.caption },
  toggleRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  modalActions: { flexDirection: 'row', gap: spacing.sm },
  modalBtn: { flex: 1 },
});
