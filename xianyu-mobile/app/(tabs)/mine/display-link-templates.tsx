// 通用展示入口（用户级模板）管理页：列表 + 默认展示开关 + 增删改。
// 标记「默认展示」的入口由提卡页读取商品配置后合并（按名称去重，商品自身配置优先）。
// 编辑表单内始终只有一条入口（保存时取 draftEntries[0]），校验复用 DisplayLinkEditor 的 validateEntry。
import { useCallback, useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Switch,
  Alert,
  RefreshControl,
  ScrollView,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Images, Plus, Trash2 } from 'lucide-react-native';
import { Card, Button, Loading, EmptyState, FormModal } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  DisplayLinkEditor,
  draftToEntry,
  toDraft,
  validateEntry,
} from '@/components/display-links/DisplayLinkEditor';
import {
  getDisplayLinkTemplates,
  createDisplayLinkTemplate,
  updateDisplayLinkTemplate,
  deleteDisplayLinkTemplate,
  uploadDisplayLinkTemplateImage,
  type DisplayLinkTemplate,
} from '@/api/wrappers/display-link-templates';
import type { DisplayLinkEntry } from '@/api/wrappers/item-query-config';

const TYPE_LABEL: Record<string, string> = { link: '链接', text: '文本', image: '图片' };

const HINT = '标记『默认展示』的入口会自动出现在所有商品的提卡页底部（按名称去重，商品自身配置优先）';

/** 新增时的空白草稿（与商品级入口一致，默认链接型） */
function emptyEntry(): DisplayLinkEntry {
  return { name: '', type: 'link', url: '', note: '' };
}

/**
 * 草稿 → 提交载荷。
 * link/image 显式带上 note：PUT 为部分更新语义，缺省字段会保留服务端旧值，导致备注清不掉。
 */
function toPayload(draft: Record<string, string>): DisplayLinkEntry {
  const entry = draftToEntry(draft);
  if (entry.type === 'text') return entry;
  const note = (draft.note ?? '').trim();
  return entry.type === 'link'
    ? { name: entry.name, type: 'link', url: entry.url, note }
    : { name: entry.name, type: 'image', url: entry.url, note };
}

/** 加载失败的内联提示 + 重试（失败时不渲染空态，避免误判为无数据后重复创建） */
function LoadErrorRow({ message, onRetry }: { message: string; onRetry: () => void }) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  return (
    <View style={styles.loadErrorWrap}>
      <Text style={[styles.loadErrorText, { color: c.error }]}>加载失败：{message}</Text>
      <Button label="重试" variant="secondary" onPress={onRetry} style={styles.loadErrorBtn} />
    </View>
  );
}

export default function DisplayLinkTemplatesScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [templates, setTemplates] = useState<DisplayLinkTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  // 同一行开关请求期间禁用，避免并发提交与回滚错乱
  const [togglingDefault, setTogglingDefault] = useState<Record<number, boolean>>({});

  // 新建/编辑共用表单
  const [formVisible, setFormVisible] = useState(false);
  const [editing, setEditing] = useState<DisplayLinkTemplate | null>(null);
  const [draftEntries, setDraftEntries] = useState<DisplayLinkEntry[]>([]);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    setLoadError(null);
    try {
      setTemplates(await getDisplayLinkTemplates());
    } catch (e) {
      setLoadError((e as Error).message || '获取通用展示入口失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // 首次加载失败且无数据：空态不可信，禁止新增（防止重复创建同名入口）
  const emptyAfterError = loadError != null && templates.length === 0;

  function openCreate() {
    if (emptyAfterError) return;
    setEditing(null);
    setDraftEntries([emptyEntry()]);
    setFormVisible(true);
  }

  function openEdit(item: DisplayLinkTemplate) {
    setEditing(item);
    // 模板带 id/is_default，先归一为条目（多余字段不进编辑器草稿）
    setDraftEntries([draftToEntry(toDraft(item))]);
    setFormVisible(true);
  }

  function closeForm() {
    setFormVisible(false);
    setEditing(null);
  }

  async function handleSave() {
    if (saving) return;
    if (draftEntries.length === 0) { Alert.alert('提示', '请先添加一个入口'); return; }
    if (draftEntries.length > 1) { Alert.alert('提示', '一条通用入口对应一条模板，请删除多余的入口'); return; }
    const draft = toDraft(draftEntries[0]);
    const invalid = validateEntry(draft);
    if (invalid) { Alert.alert('请检查入口配置', invalid); return; }
    const payload = toPayload(draft);
    setSaving(true);
    try {
      if (editing) await updateDisplayLinkTemplate(editing.id, payload);
      else await createDisplayLinkTemplate(payload);
      closeForm();
      await load();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message || '未知错误');
    } finally {
      setSaving(false);
    }
  }

  /** 切换「默认展示」：先改本地再提交，失败回滚为原值 */
  async function handleToggleDefault(item: DisplayLinkTemplate) {
    if (togglingDefault[item.id]) return;
    const next = !item.is_default;
    setTemplates((prev) => prev.map((t) => (t.id === item.id ? { ...t, is_default: next } : t)));
    setTogglingDefault((prev) => ({ ...prev, [item.id]: true }));
    try {
      await updateDisplayLinkTemplate(item.id, { is_default: next });
    } catch (e) {
      setTemplates((prev) => prev.map((t) => (t.id === item.id ? { ...t, is_default: item.is_default } : t)));
      Alert.alert('操作失败', (e as Error).message || '未知错误');
    } finally {
      setTogglingDefault((prev) => {
        const nextState = { ...prev };
        delete nextState[item.id];
        return nextState;
      });
    }
  }

  function confirmDelete(item: DisplayLinkTemplate) {
    Alert.alert('确认删除', `删除通用入口「${item.name}」？已引用该入口的商品配置不受影响。`, [
      { text: '取消', style: 'cancel' },
      { text: '删除', style: 'destructive', onPress: async () => {
        try { await deleteDisplayLinkTemplate(item.id); await load(); }
        catch (e) { Alert.alert('删除失败', (e as Error).message || '未知错误'); }
      } },
    ]);
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
        <Loading label="加载通用展示入口..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.header}>
        <Text style={[styles.hint, { color: c.textMuted }]}>{HINT}</Text>
        <Pressable
          onPress={openCreate}
          disabled={emptyAfterError}
          style={[styles.addBtn, { backgroundColor: c.primary, opacity: emptyAfterError ? 0.4 : 1 }]}
          accessibilityRole="button"
          accessibilityLabel="新增通用展示入口"
          hitSlop={8}
        >
          <Plus size={20} color="#FFF" />
        </Pressable>
      </View>

      <FlatList
        data={templates}
        keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
        ListHeaderComponent={
          loadError && templates.length > 0 ? <LoadErrorRow message={loadError} onRetry={load} /> : null
        }
        renderItem={({ item }) => (
          <Pressable onLongPress={() => confirmDelete(item)} delayLongPress={400}>
            <Card style={styles.card}>
              <View style={styles.cardRow}>
                <View style={styles.cardContent}>
                  <View style={styles.typeRow}>
                    <View style={[styles.typeBadge, { backgroundColor: c.primary }]}>
                      <Text style={styles.typeText}>{TYPE_LABEL[item.type] ?? item.type}</Text>
                    </View>
                    <Text style={[styles.name, { color: c.text }]} numberOfLines={1}>{item.name}</Text>
                  </View>
                  <Text style={[styles.summary, { color: c.textMuted }]} numberOfLines={1}>
                    {summarize(item)}
                  </Text>
                </View>
                <Pressable
                  onPress={() => confirmDelete(item)}
                  style={styles.deleteBtn}
                  accessibilityRole="button"
                  accessibilityLabel={`删除${item.name}`}
                  hitSlop={8}
                >
                  <Trash2 size={18} stroke={c.error} />
                </Pressable>
                <View style={styles.switchCol}>
                  <Switch
                    value={item.is_default}
                    onValueChange={() => handleToggleDefault(item)}
                    disabled={!!togglingDefault[item.id]}
                    trackColor={{ false: c.border, true: c.primary }}
                  />
                  <Text style={[styles.switchLabel, { color: c.textMuted }]}>默认展示</Text>
                </View>
              </View>
              <View style={styles.cardActions}>
                <Button label="编辑" variant="secondary" onPress={() => openEdit(item)} style={styles.actionBtn} />
              </View>
            </Card>
          </Pressable>
        )}
        ListEmptyComponent={
          loadError ? (
            <LoadErrorRow message={loadError} onRetry={load} />
          ) : (
            <EmptyState
              icon={Images}
              title="暂无通用展示入口"
              message="标记默认展示的入口会自动出现在所有商品的提卡页底部"
              actionLabel="新增入口"
              onAction={openCreate}
            />
          )
        }
        contentContainerStyle={styles.list}
      />

      <FormModal
        visible={formVisible}
        onClose={closeForm}
        title={editing ? '编辑通用入口' : '新增通用入口'}
        contentStyle={styles.formSheet}
      >
        <ScrollView
          style={styles.formScroll}
          contentContainerStyle={styles.formContent}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* entries 必须传 state 引用：内联数组会让编辑器每次渲染都重建草稿，输入中的空格被 trim */}
          <DisplayLinkEditor
            entries={draftEntries}
            onChange={setDraftEntries}
            uploadImage={uploadDisplayLinkTemplateImage}
            hint="每条通用入口单独保存；需要多条时保存后再次新增"
            singleEntry
          />
        </ScrollView>
        <View style={styles.sheetActions}>
          <Button label="取消" variant="secondary" onPress={closeForm} disabled={saving} style={styles.sheetBtn} />
          <Button label={editing ? '保存' : '创建'} onPress={handleSave} loading={saving} style={styles.sheetBtn} />
        </View>
      </FormModal>
    </SafeAreaView>
  );
}

/** 卡片上的一行摘要（链接/图片给地址，文本给弹窗标题） */
function summarize(item: DisplayLinkTemplate): string {
  if (item.type === 'text') return item.title || item.content || '未配置';
  return item.url || '未配置';
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: { flexDirection: 'row', alignItems: 'center', gap: spacing.md, paddingHorizontal: spacing.lg, paddingVertical: spacing.md },
  hint: { ...typography.small, flex: 1, lineHeight: 18 },
  addBtn: { width: 32, height: 32, borderRadius: radius.full, alignItems: 'center', justifyContent: 'center' },
  list: { padding: spacing.lg, paddingTop: 0, gap: spacing.md, paddingBottom: 80 },
  card: { gap: spacing.sm },
  cardRow: { flexDirection: 'row', alignItems: 'center' },
  cardContent: { flex: 1, marginRight: spacing.sm, gap: spacing.xs },
  typeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  typeBadge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: radius.sm },
  typeText: { color: '#FFF', fontSize: 11, fontWeight: '600' },
  name: { ...typography.body, flex: 1, fontWeight: '600' },
  summary: { ...typography.small },
  deleteBtn: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center', marginRight: spacing.xs },
  switchCol: { alignItems: 'center', gap: 2 },
  switchLabel: { ...typography.micro, fontWeight: '400' },
  cardActions: { flexDirection: 'row', gap: spacing.sm },
  actionBtn: { flex: 1, minHeight: 38 },
  loadErrorWrap: { alignItems: 'center', paddingVertical: spacing.md, gap: spacing.sm },
  loadErrorText: { ...typography.caption, textAlign: 'center' },
  loadErrorBtn: { minHeight: 40, paddingHorizontal: spacing.xl },
  formSheet: { height: '85%' },
  formScroll: { flex: 1 },
  formContent: { paddingBottom: spacing.sm },
  sheetActions: { flexDirection: 'row', gap: spacing.sm },
  sheetBtn: { flex: 1 },
});
