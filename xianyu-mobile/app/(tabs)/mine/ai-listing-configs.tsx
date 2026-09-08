import { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, Switch, ScrollView, Alert, RefreshControl } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button, Input, EmptyState, Badge, FAB, Loading, FormModal } from '@/components/ui';
import { Search, Bot } from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getAiListingConfigs,
  createAiListingConfig,
  updateAiListingConfig,
  deleteAiListingConfig,
  getAiListingModels,
  testAiListingConfig,
  type AiListingConfig,
  type AiListingConfigParams,
} from '@/api/wrappers/ai-listing';
import { usePagedList } from '@/hooks/usePagedList';

const PAGE_SIZE = 20;

type ModelOption = { id: string; name?: string };

interface FormState {
  name: string;
  text_base_url: string;
  text_api_key: string;
  text_model: string;
  text_temperature: string;
  text_max_tokens: string;
  prompt_template: string;
  image_enabled: boolean;
  image_base_url: string;
  image_api_key: string;
  image_model: string;
  image_size: string;
  image_count: string;
}

const EMPTY_FORM: FormState = {
  name: '',
  text_base_url: '',
  text_api_key: '',
  text_model: '',
  text_temperature: '0.7',
  text_max_tokens: '2048',
  prompt_template: '',
  image_enabled: false,
  image_base_url: '',
  image_api_key: '',
  image_model: '',
  image_size: '1024x1024',
  image_count: '1',
};

function formFromConfig(cfg: AiListingConfig): FormState {
  return {
    name: cfg.name,
    text_base_url: cfg.text_base_url,
    text_api_key: '',
    text_model: cfg.text_model,
    text_temperature: String(cfg.text_temperature),
    text_max_tokens: String(cfg.text_max_tokens),
    prompt_template: cfg.prompt_template,
    image_enabled: cfg.image_enabled,
    image_base_url: cfg.image_base_url,
    image_api_key: '',
    image_model: cfg.image_model,
    image_size: cfg.image_size,
    image_count: String(cfg.image_count),
  };
}

function clampTemp(v: string): number {
  const n = parseFloat(v);
  if (isNaN(n)) return 0.7;
  return Math.min(2, Math.max(0, n));
}

function clampTokens(v: string): number {
  let n = parseInt(v, 10);
  if (isNaN(n)) n = 2048;
  return Math.min(32768, Math.max(256, n));
}

function clampCount(v: string): number {
  let n = parseInt(v, 10);
  if (isNaN(n)) n = 1;
  return Math.min(9, Math.max(1, n));
}

export default function AiListingConfigsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [formVisible, setFormVisible] = useState(false);
  const [editing, setEditing] = useState<AiListingConfig | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [textModels, setTextModels] = useState<ModelOption[]>([]);
  const [imageModels, setImageModels] = useState<ModelOption[]>([]);
  const [fetchingTextModels, setFetchingTextModels] = useState(false);
  const [fetchingImageModels, setFetchingImageModels] = useState(false);

  // 搜索防抖：输入停顿 400ms 后回第一页拉取
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 400);
    return () => clearTimeout(t);
  }, [search]);

  const {
    items,
    loading,
    refreshing,
    loadingMore,
    refresh,
    loadMore,
  } = usePagedList<AiListingConfig>({
    mode: 'page',
    pageSize: PAGE_SIZE,
    fetchPage: ({ page = 1, limit = PAGE_SIZE }) =>
      getAiListingConfigs(page, limit, debouncedSearch || undefined).then((r) => ({
        items: r.list,
        total: r.total,
      })),
    onError: (e) => Alert.alert('加载失败', e.message),
  });

  // 防抖词变化触发刷新；首次挂载跳过（usePagedList 已 auto 拉第一页）
  const firstSearch = useRef(true);
  useEffect(() => {
    if (firstSearch.current) { firstSearch.current = false; return; }
    refresh();
  }, [debouncedSearch, refresh]);

  const update = (patch: Partial<FormState>) => setForm((f) => ({ ...f, ...patch }));

  function openCreate() {
    setEditing(null);
    setForm(EMPTY_FORM);
    setTextModels([]);
    setImageModels([]);
    setFormVisible(true);
  }

  function openEdit(cfg: AiListingConfig) {
    setEditing(cfg);
    setForm(formFromConfig(cfg));
    setTextModels([]);
    setImageModels([]);
    setFormVisible(true);
  }

  function closeForm() {
    setFormVisible(false);
  }

  async function fetchTextModels() {
    if (!form.text_base_url.trim()) { Alert.alert('提示', '请先填写文案接口地址'); return; }
    setFetchingTextModels(true);
    try {
      const apiKey = form.text_api_key.trim() || undefined;
      const models = await getAiListingModels({
        base_url: form.text_base_url.trim(),
        api_key: apiKey,
        config_id: editing && !apiKey ? editing.id : undefined,
      });
      setTextModels(models);
      if (models.length === 0) Alert.alert('提示', '未拉取到模型');
    } catch (e) {
      Alert.alert('拉取模型失败', (e as Error).message);
    } finally {
      setFetchingTextModels(false);
    }
  }

  async function fetchImageModels() {
    if (!form.image_base_url.trim()) { Alert.alert('提示', '请先填写图片接口地址'); return; }
    setFetchingImageModels(true);
    try {
      const apiKey = form.image_api_key.trim() || undefined;
      const models = await getAiListingModels({
        base_url: form.image_base_url.trim(),
        api_key: apiKey,
        config_id: editing && !apiKey ? editing.id : undefined,
      });
      setImageModels(models);
      if (models.length === 0) Alert.alert('提示', '未拉取到模型');
    } catch (e) {
      Alert.alert('拉取模型失败', (e as Error).message);
    } finally {
      setFetchingImageModels(false);
    }
  }

  async function handleSave() {
    const creating = !editing;
    if (!form.name.trim()) { Alert.alert('提示', '请输入配置名'); return; }
    if (!form.text_base_url.trim()) { Alert.alert('提示', '请输入文案接口地址'); return; }
    if (!form.text_model.trim()) { Alert.alert('提示', '请输入文案模型'); return; }
    if (creating && !form.text_api_key.trim()) { Alert.alert('提示', '请输入文案密钥'); return; }
    if (form.image_enabled) {
      if (!form.image_base_url.trim()) { Alert.alert('提示', '请输入图片接口地址'); return; }
      if (!form.image_model.trim()) { Alert.alert('提示', '请输入图片模型'); return; }
      if (creating && !form.image_api_key.trim()) { Alert.alert('提示', '请输入图片密钥'); return; }
    }
    const params: AiListingConfigParams = {
      name: form.name.trim(),
      text_base_url: form.text_base_url.trim(),
      text_api_key: form.text_api_key,
      text_model: form.text_model.trim(),
      text_temperature: clampTemp(form.text_temperature),
      text_max_tokens: clampTokens(form.text_max_tokens),
      prompt_template: form.prompt_template,
      image_enabled: form.image_enabled,
      image_base_url: form.image_enabled ? form.image_base_url.trim() : undefined,
      image_api_key: form.image_enabled ? form.image_api_key : '',
      image_model: form.image_enabled ? form.image_model.trim() : undefined,
      image_size: form.image_enabled ? form.image_size.trim() : undefined,
      image_count: form.image_enabled ? clampCount(form.image_count) : undefined,
    };
    setSaving(true);
    try {
      if (editing) {
        await updateAiListingConfig(editing.id, params);
      } else {
        await createAiListingConfig(params);
      }
      setFormVisible(false);
      await refresh();
    } catch (e) {
      Alert.alert('保存失败', (e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function handleTest(item: AiListingConfig) {
    setTestingId(item.id);
    try {
      const reply = await testAiListingConfig(item.id);
      Alert.alert('测试结果', reply || '(无回复)');
    } catch (e) {
      Alert.alert('测试失败', (e as Error).message);
    } finally {
      setTestingId(null);
    }
  }

  function handleDelete(item: AiListingConfig) {
    Alert.alert('确认删除', `删除配置"${item.name}"？`, [
      { text: '取消' },
      {
        text: '删除',
        style: 'destructive',
        onPress: async () => {
          try {
            await deleteAiListingConfig(item.id);
            await refresh();
          } catch (e) {
            Alert.alert('删除失败', (e as Error).message);
          }
        },
      },
    ]);
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
        <Loading label="加载配置..." />
      </SafeAreaView>
    );
  }

  const renderModelChips = (
    models: ModelOption[],
    current: string,
    onSelect: (id: string) => void,
  ) => (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.modelChips}>
      {models.map((m) => {
        const active = current === m.id;
        return (
          <Pressable
            key={m.id}
            onPress={() => onSelect(m.id)}
            style={[
              styles.modelChip,
              { backgroundColor: active ? c.primary : c.surface, borderColor: active ? c.primary : c.border },
            ]}
          >
            <Text style={[styles.modelChipText, { color: active ? '#FFFFFF' : c.text }]} numberOfLines={1}>
              {m.name || m.id}
            </Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.searchBar}>
        <Search size={16} stroke={c.textMuted} />
        <View style={styles.searchInputWrap}>
          <Input
            value={search}
            onChangeText={setSearch}
            placeholder="搜索配置名"
            returnKeyType="search"
            clearButtonMode="while-editing"
          />
        </View>
      </View>

      <FlatList<AiListingConfig>
        data={items}
        keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={refresh} />}
        onEndReached={loadMore}
        onEndReachedThreshold={0.3}
        ListFooterComponent={
          loadingMore ? <Text style={[styles.loadingMore, { color: c.textMuted }]}>加载中...</Text> : null
        }
        renderItem={({ item }) => (
          <Card style={styles.card}>
            <View style={styles.cardHead}>
              <Text style={[styles.cfgName, { color: c.text }]} numberOfLines={1}>{item.name}</Text>
              <Badge label={item.image_enabled ? '图片' : '仅文案'} variant={item.image_enabled ? 'primary' : 'gray'} />
            </View>
            <Text style={[styles.cfgModel, { color: c.textSecondary }]} numberOfLines={1}>
              文案模型：{item.text_model || '—'}
            </Text>
            <Text style={[styles.cfgUrl, { color: c.textMuted }]} numberOfLines={1}>{item.text_base_url}</Text>
            <View style={styles.cardActions}>
              <Button label="测试" variant="secondary" onPress={() => handleTest(item)} loading={testingId === item.id} style={styles.cardBtn} />
              <Button label="编辑" variant="secondary" onPress={() => openEdit(item)} style={styles.cardBtn} />
              <Button label="删除" variant="danger" onPress={() => handleDelete(item)} style={styles.cardBtn} />
            </View>
          </Card>
        )}
        ListEmptyComponent={
          <EmptyState
            icon={Bot}
            title="暂无 AI 上架配置"
            message="新增配置后即可用 AI 生成商品文案与图片"
            actionLabel="添加配置"
            onAction={openCreate}
          />
        }
        contentContainerStyle={styles.list}
      />

      <FAB onPress={openCreate} label="添加配置" />

      <FormModal
        visible={formVisible}
        onClose={closeForm}
        title={editing ? '编辑配置' : '新增配置'}
        contentStyle={styles.formSheet}
      >
        <ScrollView
          style={styles.formScroll}
          contentContainerStyle={styles.formBody}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          <View style={styles.fieldGroup}>
            <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>配置名</Text>
            <Input value={form.name} onChangeText={(v) => update({ name: v })} placeholder="如 默认配置" />
          </View>

          <View style={styles.fieldGroup}>
            <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>文案接口地址</Text>
            <Input
              value={form.text_base_url}
              onChangeText={(v) => update({ text_base_url: v })}
              placeholder="https://..."
              autoCapitalize="none"
              autoCorrect={false}
              keyboardType="url"
            />
          </View>

          <View style={styles.fieldGroup}>
            <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
              文案密钥{editing ? '（留空=不修改）' : ''}
            </Text>
            <Input
              value={form.text_api_key}
              onChangeText={(v) => update({ text_api_key: v })}
              placeholder="sk-..."
              secureTextEntry
              autoCapitalize="none"
              autoCorrect={false}
            />
          </View>

          <View style={styles.fieldGroup}>
            <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>文案模型</Text>
            <View style={styles.modelRow}>
              <View style={styles.modelInputWrap}>
                <Input
                  value={form.text_model}
                  onChangeText={(v) => update({ text_model: v })}
                  placeholder="模型 id，如 gpt-4o"
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>
              <Button label="拉取" variant="secondary" onPress={fetchTextModels} loading={fetchingTextModels} style={styles.fetchBtn} />
            </View>
            {textModels.length > 0 && renderModelChips(textModels, form.text_model, (id) => update({ text_model: id }))}
          </View>

          <View style={styles.numRow}>
            <View style={styles.numField}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>温度 (0~2)</Text>
              <Input
                value={form.text_temperature}
                onChangeText={(v) => update({ text_temperature: v })}
                keyboardType="decimal-pad"
              />
            </View>
            <View style={styles.numField}>
              <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>最大 token (256~32768)</Text>
              <Input
                value={form.text_max_tokens}
                onChangeText={(v) => update({ text_max_tokens: v })}
                keyboardType="number-pad"
              />
            </View>
          </View>

          <View style={styles.fieldGroup}>
            <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>提示词模板</Text>
            <Input
              value={form.prompt_template}
              onChangeText={(v) => update({ prompt_template: v })}
              placeholder="商品描述生成提示词..."
              multiline
            />
          </View>

          <View style={[styles.switchRow, { borderTopColor: c.borderLight }]}>
            <Text style={[styles.switchLabel, { color: c.text }]}>启用 AI 图片</Text>
            <Switch
              value={form.image_enabled}
              onValueChange={(v) => update({ image_enabled: v })}
              trackColor={{ false: c.border, true: c.primary }}
            />
          </View>

          {form.image_enabled && (
            <View style={styles.imageGroup}>
              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>图片接口地址</Text>
                <Input
                  value={form.image_base_url}
                  onChangeText={(v) => update({ image_base_url: v })}
                  placeholder="https://..."
                  autoCapitalize="none"
                  autoCorrect={false}
                  keyboardType="url"
                />
              </View>

              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>
                  图片密钥{editing ? '（留空=不修改）' : ''}
                </Text>
                <Input
                  value={form.image_api_key}
                  onChangeText={(v) => update({ image_api_key: v })}
                  placeholder="sk-..."
                  secureTextEntry
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>

              <View style={styles.fieldGroup}>
                <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>图片模型</Text>
                <View style={styles.modelRow}>
                  <View style={styles.modelInputWrap}>
                    <Input
                      value={form.image_model}
                      onChangeText={(v) => update({ image_model: v })}
                      placeholder="模型 id"
                      autoCapitalize="none"
                      autoCorrect={false}
                    />
                  </View>
                  <Button label="拉取" variant="secondary" onPress={fetchImageModels} loading={fetchingImageModels} style={styles.fetchBtn} />
                </View>
                {imageModels.length > 0 && renderModelChips(imageModels, form.image_model, (id) => update({ image_model: id }))}
              </View>

              <View style={styles.numRow}>
                <View style={styles.numField}>
                  <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>图片尺寸</Text>
                  <Input
                    value={form.image_size}
                    onChangeText={(v) => update({ image_size: v })}
                    placeholder="1024x1024"
                    autoCapitalize="none"
                  />
                </View>
                <View style={styles.numField}>
                  <Text style={[styles.fieldLabel, { color: c.textSecondary }]}>每条张数 (1~9)</Text>
                  <Input
                    value={form.image_count}
                    onChangeText={(v) => update({ image_count: v })}
                    keyboardType="number-pad"
                  />
                </View>
              </View>
            </View>
          )}
        </ScrollView>

        <View style={styles.formActions}>
          <Button label="取消" variant="secondary" onPress={closeForm} style={styles.formBtn} />
          <Button label="保存" onPress={handleSave} loading={saving} style={styles.formBtn} />
        </View>
      </FormModal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  searchBar: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
  },
  searchInputWrap: { flex: 1 },
  list: { padding: spacing.lg, gap: spacing.md, paddingBottom: 88 },
  loadingMore: { textAlign: 'center', padding: spacing.md },
  card: { gap: spacing.xs },
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: spacing.sm },
  cfgName: { ...typography.body, fontWeight: '600', flex: 1 },
  cfgModel: { ...typography.caption },
  cfgUrl: { ...typography.small },
  cardActions: { flexDirection: 'row', gap: spacing.xs, marginTop: spacing.xs },
  cardBtn: { flex: 1, minHeight: 38 },
  formSheet: { height: '88%' },
  formScroll: { flex: 1 },
  formBody: { gap: spacing.md, paddingBottom: spacing.sm },
  fieldGroup: { gap: spacing.xs },
  fieldLabel: { ...typography.caption },
  modelRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  modelInputWrap: { flex: 1 },
  fetchBtn: { minHeight: 40, paddingHorizontal: spacing.md },
  modelChips: { gap: spacing.xs, paddingVertical: spacing.xs },
  modelChip: { paddingHorizontal: spacing.md, paddingVertical: spacing.xs, borderRadius: radius.full, borderWidth: 1, maxWidth: 200 },
  modelChipText: { ...typography.small },
  numRow: { flexDirection: 'row', gap: spacing.md },
  numField: { flex: 1, gap: spacing.xs },
  switchRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingVertical: spacing.sm, borderTopWidth: 1 },
  switchLabel: { ...typography.body },
  imageGroup: { gap: 0 },
  formActions: { flexDirection: 'row', gap: spacing.sm },
  formBtn: { flex: 1 },
});
