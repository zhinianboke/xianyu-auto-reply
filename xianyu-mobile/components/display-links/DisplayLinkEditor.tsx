// 展示入口编辑（商品级 / 素材级 / 通用模板共用）。
// 上传实现由调用方注入：商品级传 uploadItemDisplayLinkImage 的绑定闭包，素材级与模板级传 uploadDisplayLinkTemplateImage。
import { useCallback, useEffect, useRef, useState } from 'react';
import { Alert, Image, Pressable, StyleSheet, Text, View, useColorScheme } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { ChevronDown, Trash2 } from 'lucide-react-native';
import { Button, Card, Input } from '@/components/ui';
import { colors, radius, spacing, typography } from '@/lib/theme';
import { getServerUrl } from '@/lib/config';
import {
  getDisplayLinkTemplates,
  type DisplayLinkTemplate,
} from '@/api/wrappers/display-link-templates';
import type { DisplayLinkEntry } from '@/api/wrappers/item-query-config';

type EntryType = DisplayLinkEntry['type'];

/** 编辑态草稿：三种类型字段齐备且扁平，避免受控 value 出现 undefined */
export interface EntryDraft extends Record<string, string> {
  name: string;
  type: EntryType;
  url: string;
  note: string;
  title: string;
  content: string;
}

interface Props {
  entries: DisplayLinkEntry[];
  onChange: (next: DisplayLinkEntry[]) => void;
  /** 注入的上传实现：返回 image_url（/static/... 或 http(s)） */
  uploadImage: (fileUri: string) => Promise<string>;
  /** 顶部说明文案（可选） */
  hint?: string;
  /** 单条模式（通用入口模板）：隐藏新增按钮与「从通用入口添加」，一条模板只对应一条入口；
   *  同时隐藏唯一条目的删除按钮（删到 0 条后无新增入口，模板页将无法保存） */
  singleEntry?: boolean;
}

const TYPE_LABEL: Record<EntryType, string> = { link: '链接', text: '文本', image: '图片' };
const TYPE_ORDER: EntryType[] = ['link', 'text', 'image'];

/** 按类型构造空白条目（字段齐备，保存时按类型白名单收敛） */
function emptyEntry(type: EntryType): DisplayLinkEntry {
  if (type === 'link') return { name: '', type: 'link', url: '', note: '' };
  if (type === 'image') return { name: '', type: 'image', url: '', note: '' };
  return { name: '', type: 'text', title: '', content: '' };
}

function asString(v: unknown): string {
  return typeof v === 'string' ? v : '';
}

/** 条目/模板 → 可编辑草稿（字段齐备，避免 undefined 受控告警） */
export function toDraft(e: DisplayLinkEntry | DisplayLinkTemplate): EntryDraft {
  const raw = e as unknown as Record<string, unknown>;
  return {
    name: asString(e.name),
    type: e.type,
    url: asString(raw.url),
    note: asString(raw.note),
    title: asString(raw.title),
    content: asString(raw.content),
  };
}

// 与后端 display_link_service.py 的列宽/长度上限一致：超长写入会被数据库拒绝（500），故在入口处拦下
export const MAX_NAME_LEN = 255;
export const MAX_URL_LEN = 512;
export const MAX_NOTE_LEN = 255;
export const MAX_TITLE_LEN = 255;
export const MAX_TEXT_CONTENT_LEN = 2000;

/** url 是否含 ``..`` 路径段：按 ``/`` 切分整段比对，查询串里的 ``..``（如 ``?k=a..b``）不误伤 */
function hasDotDotSegment(url: string): boolean {
  return url.split('/').includes('..');
}

/** 校验单条（与后端契约一致），返回错误文案或 null */
export function validateEntry(draft: Record<string, string>): string | null {
  const name = (draft.name ?? '').trim();
  if (!name) return '请填写入口名称';
  if (name.length > MAX_NAME_LEN) return `入口名称不能超过 ${MAX_NAME_LEN} 字符`;
  if (draft.type === 'link') {
    const url = (draft.url ?? '').trim();
    if (!url) return '请填写链接地址';
    if (!/^https?:\/\//.test(url)) return '链接地址必须以 http:// 或 https:// 开头';
    if (url.length > MAX_URL_LEN) return `链接地址不能超过 ${MAX_URL_LEN} 字符`;
    if (hasDotDotSegment(url)) return '链接地址不能包含 .. 路径段';
    if ((draft.note ?? '').trim().length > MAX_NOTE_LEN) {
      return `备注不能超过 ${MAX_NOTE_LEN} 字符`;
    }
  } else if (draft.type === 'image') {
    const url = (draft.url ?? '').trim();
    if (!url) return '请上传图片或填写图片地址';
    if (!(url.startsWith('/static/') || /^https?:\/\//.test(url))) {
      return '图片地址必须是 /static/ 开头的站内路径或 http(s) 链接';
    }
    if (url.length > MAX_URL_LEN) return `图片地址不能超过 ${MAX_URL_LEN} 字符`;
    if (hasDotDotSegment(url)) return '图片地址不能包含 .. 路径段';
    if ((draft.note ?? '').trim().length > MAX_NOTE_LEN) {
      return `备注不能超过 ${MAX_NOTE_LEN} 字符`;
    }
  } else {
    const title = (draft.title ?? '').trim();
    if (!title) return '请填写弹窗标题';
    if (title.length > MAX_TITLE_LEN) return `弹窗标题不能超过 ${MAX_TITLE_LEN} 字符`;
    const content = draft.content ?? '';
    if (!content.trim()) return '请填写弹窗内容';
    if (content.length > MAX_TEXT_CONTENT_LEN) {
      return `弹窗内容不能超过 ${MAX_TEXT_CONTENT_LEN} 字符`;
    }
  }
  return null;
}

/** 草稿 → 条目（白名单字段，丢弃空的可选字段） */
export function draftToEntry(draft: Record<string, string>): DisplayLinkEntry {
  const name = draft.name.trim();
  if (draft.type === 'link' || draft.type === 'image') {
    const entry: Record<string, string> = { name, type: draft.type, url: draft.url.trim() };
    if (draft.note.trim()) entry.note = draft.note.trim();
    return entry as unknown as DisplayLinkEntry;
  }
  return { name, type: 'text', title: draft.title.trim(), content: draft.content };
}

/** RN <Image> 不认 /static/... 相对路径：先补当前服务器地址；取不到服务器地址时返回 null，由调用方提示不可用 */
async function absolutizeImageUrl(url: string): Promise<string | null> {
  if (/^https?:\/\//i.test(url)) return url;
  const base = await getServerUrl();
  if (!base) return null;
  return `${base.replace(/\/+$/, '')}${url.startsWith('/') ? '' : '/'}${url}`;
}

const PREVIEW_DEBOUNCE_MS = 300;

/** 图片预览：相对路径需先拼服务器地址；未配置服务器地址或图片加载失败时给出文字说明而非空灰框 */
function ImagePreview({ url }: { url: string }) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const [uri, setUri] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    // 先清掉上一张已解析的图，避免 url 变化时旧图闪一下
    setUri(null);
    setUnavailable(false);
    setFailed(false);
    // 输入过程中逐个字符解析会打出多次请求，静默 300ms 后再解析
    const timer = setTimeout(() => {
      absolutizeImageUrl(url)
        .then((abs) => {
          if (!alive) return;
          if (abs) setUri(abs);
          else setUnavailable(true);
        })
        .catch(() => {
          if (!alive) return;
          if (/^https?:\/\//i.test(url)) setUri(url);
          else setUnavailable(true);
        });
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [url]);

  if (unavailable) {
    return (
      <View
        style={[
          styles.preview,
          styles.previewPlaceholder,
          { backgroundColor: c.surfaceAlt, borderColor: c.border },
        ]}
      >
        <Text style={[styles.previewPlaceholderText, { color: c.textMuted }]}>
          图片预览不可用：未配置服务器地址
        </Text>
      </View>
    );
  }

  if (failed) {
    return (
      <View
        style={[
          styles.preview,
          styles.previewPlaceholder,
          { backgroundColor: c.surfaceAlt, borderColor: c.border },
        ]}
      >
        <Text style={[styles.previewPlaceholderText, { color: c.textMuted }]}>
          图片加载失败，请检查地址
        </Text>
      </View>
    );
  }

  return (
    <Image
      source={uri ? { uri } : undefined}
      style={[styles.preview, { backgroundColor: c.surfaceAlt }]}
      resizeMode="contain"
      onError={() => setFailed(true)}
    />
  );
}

export function DisplayLinkEditor({ entries, onChange, uploadImage, hint, singleEntry }: Props) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const [drafts, setDrafts] = useState<EntryDraft[]>(() => entries.map(toDraft));
  const draftsRef = useRef<EntryDraft[]>(drafts);
  // 记录最近一次自身 emit 出去的数组：外部 entries 与它同引用说明变化来自本组件，
  // 不再回写草稿，否则名称/备注两端空白会被立刻 trim 掉、光标跳到末尾
  const emittedRef = useRef<DisplayLinkEntry[] | null>(null);
  const [pickerOpen, setPickerOpen] = useState(false);
  const [pickerLoading, setPickerLoading] = useState(false);
  const [templates, setTemplates] = useState<DisplayLinkTemplate[]>([]);
  const [uploadingIndex, setUploadingIndex] = useState<number | null>(null);

  // 外部 entries 变化（如服务端加载完成）时重建草稿
  useEffect(() => {
    if (entries === emittedRef.current) return;
    const next = entries.map(toDraft);
    draftsRef.current = next;
    setDrafts(next);
  }, [entries]);

  const emit = useCallback(
    (next: EntryDraft[]) => {
      draftsRef.current = next;
      setDrafts(next);
      const nextEntries = next.map(draftToEntry);
      emittedRef.current = nextEntries;
      onChange(nextEntries);
    },
    [onChange],
  );

  const updateDraft = (index: number, patch: Record<string, string>) => {
    emit(draftsRef.current.map((d, i) => (i === index ? { ...d, ...patch } : d)));
  };

  const addEntry = (type: EntryType) => {
    emit([...draftsRef.current, toDraft(emptyEntry(type))]);
  };

  /** 单条模式切换类型：保留名称（免去重打），类型专属字段按新类型清空 —— 与网页端切换类型的行为一致 */
  const switchType = (index: number, type: EntryType) => {
    const current = draftsRef.current[index];
    if (!current || current.type === type) return;
    updateDraft(index, { ...toDraft(emptyEntry(type)), name: current.name, type });
  };

  const removeEntry = (index: number) => {
    Alert.alert('删除入口', '确认删除该展示入口？', [
      { text: '取消', style: 'cancel' },
      {
        text: '删除',
        style: 'destructive',
        onPress: () => emit(draftsRef.current.filter((_, i) => i !== index)),
      },
    ]);
  };

  const pickImage = async (index: number) => {
    let fileUri: string;
    try {
      const perm = await ImagePicker.requestMediaLibraryPermissionsAsync();
      if (!perm.granted) {
        Alert.alert('提示', '需要相册权限才能选择图片');
        return;
      }
      const res = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ['images'], quality: 0.9 });
      if (res.canceled || !res.assets?.[0]) return;
      fileUri = res.assets[0].uri;
    } catch (e) {
      Alert.alert('选择图片失败', (e as Error).message || '无法打开相册');
      return;
    }
    const targetName = draftsRef.current[index]?.name ?? '';
    try {
      setUploadingIndex(index);
      const url = await uploadImage(fileUri);
      // 上传期间条目可能被删除/改动：索引失效或名称已变时丢弃结果，避免写到错误条目
      const current = draftsRef.current[index];
      if (!current || current.name !== targetName) {
        Alert.alert('上传完成但未写入', '该入口已变更，请重新选择图片');
        return;
      }
      updateDraft(index, { url });
    } catch (e) {
      Alert.alert('上传失败', (e as Error).message);
    } finally {
      setUploadingIndex(null);
    }
  };

  const openTemplatePicker = async () => {
    if (pickerOpen) {
      setPickerOpen(false);
      return;
    }
    if (pickerLoading) return;
    setPickerLoading(true);
    try {
      setTemplates(await getDisplayLinkTemplates());
      setPickerOpen(true);
    } catch (e) {
      Alert.alert('加载失败', (e as Error).message);
    } finally {
      setPickerLoading(false);
    }
  };

  const insertTemplate = (tpl: DisplayLinkTemplate) => {
    const current = draftsRef.current;
    if (current.some((d) => d.name.trim().toLowerCase() === tpl.name.trim().toLowerCase())) {
      Alert.alert('提示', '同名入口已存在');
      return;
    }
    emit([...current, toDraft(tpl)]);
    setPickerOpen(false);
  };

  const available = templates.filter(
    (t) => !drafts.some((d) => d.name.trim().toLowerCase() === t.name.trim().toLowerCase()),
  );

  // Input 内部把 {...props} 展开在 style 之后，传入 style 会整体覆盖其基础样式（padding/边框/底色），
  // 这里补回视觉样式，与 accounts.tsx 的 textarea 写法一致
  const inputColors = { backgroundColor: c.background, color: c.text, borderColor: c.border };

  return (
    <View style={styles.wrap}>
      {hint ? <Text style={[styles.hint, { color: c.textMuted }]}>{hint}</Text> : null}

      {drafts.map((draft, index) => (
        <Card key={index} style={styles.entryCard}>
          <View style={styles.rowBetween}>
            {singleEntry ? (
              // 单条模式没有新增按钮，类型只能在此切换（否则永远锁死在初始草稿的类型上）
              <View style={styles.typeChips}>
                <Text style={[styles.label, { color: c.textSecondary }]}>类型</Text>
                {TYPE_ORDER.map((t) => {
                  const on = draft.type === t;
                  return (
                    <Pressable
                      key={t}
                      onPress={() => switchType(index, t)}
                      accessibilityRole="button"
                      accessibilityState={{ selected: on }}
                      style={[
                        styles.typeChip,
                        {
                          backgroundColor: on ? c.primary : c.background,
                          borderColor: on ? c.primary : c.border,
                        },
                      ]}
                    >
                      <Text style={[styles.typeChipText, { color: on ? '#FFF' : c.text }]}>
                        {TYPE_LABEL[t]}
                      </Text>
                    </Pressable>
                  );
                })}
              </View>
            ) : (
              <Text style={[styles.typeBadge, { color: c.primary }]}>
                {TYPE_LABEL[draft.type as EntryType] ?? draft.type}
              </Text>
            )}
            {/* 单条模式必须保留一条：删到 0 条后新增按钮已隐藏，模板页将无法保存 */}
            {singleEntry && drafts.length <= 1 ? null : (
              <Pressable
                onPress={() => removeEntry(index)}
                disabled={uploadingIndex === index}
                hitSlop={8}
                accessibilityLabel="删除该展示入口"
                style={uploadingIndex === index ? styles.disabledAction : undefined}
              >
                <Trash2 size={16} stroke={c.error} />
              </Pressable>
            )}
          </View>

          <View style={styles.field}>
            <Text style={[styles.label, { color: c.textSecondary }]}>名称</Text>
            <Input
              value={draft.name}
              onChangeText={(v) => updateDraft(index, { name: v })}
              placeholder="如：QQ群"
            />
          </View>

          {draft.type === 'link' || draft.type === 'image' ? (
            <>
              <View style={styles.field}>
                <Text style={[styles.label, { color: c.textSecondary }]}>
                  {draft.type === 'image' ? '图片地址' : '链接地址'}
                </Text>
                <Input
                  value={draft.url}
                  onChangeText={(v) => updateDraft(index, { url: v })}
                  placeholder={
                    draft.type === 'image'
                      ? '/static/uploads/display_links/xxx.png 或 https://...'
                      : 'https://...'
                  }
                  autoCapitalize="none"
                  autoCorrect={false}
                />
              </View>

              {draft.type === 'image' ? (
                <>
                  <Button
                    label="从相册选择图片"
                    variant="secondary"
                    loading={uploadingIndex === index}
                    disabled={uploadingIndex !== null}
                    onPress={() => pickImage(index)}
                  />
                  {draft.url.trim() ? <ImagePreview url={draft.url.trim()} /> : null}
                </>
              ) : null}

              <View style={styles.field}>
                <Text style={[styles.label, { color: c.textSecondary }]}>备注（可选）</Text>
                <Input
                  value={draft.note}
                  onChangeText={(v) => updateDraft(index, { note: v })}
                  placeholder="如：扫码进群"
                />
              </View>
            </>
          ) : null}

          {draft.type === 'text' ? (
            <>
              <View style={styles.field}>
                <Text style={[styles.label, { color: c.textSecondary }]}>弹窗标题</Text>
                <Input
                  value={draft.title}
                  onChangeText={(v) => updateDraft(index, { title: v })}
                  placeholder="如：扫码进群"
                />
              </View>
              <View style={styles.field}>
                <Text style={[styles.label, { color: c.textSecondary }]}>弹窗内容</Text>
                <Input
                  value={draft.content}
                  onChangeText={(v) => updateDraft(index, { content: v })}
                  placeholder="买家点击入口后弹窗展示的正文（最多 2000 字）"
                  multiline
                  textAlignVertical="top"
                  style={[styles.textarea, inputColors]}
                />
              </View>
            </>
          ) : null}
        </Card>
      ))}

      {singleEntry ? null : (
        <>
          <View style={styles.actions}>
            {TYPE_ORDER.map((t) => (
              <Button
                key={t}
                label={`+ ${TYPE_LABEL[t]}`}
                variant="secondary"
                onPress={() => addEntry(t)}
                style={styles.actionBtn}
              />
            ))}
          </View>

          <Pressable onPress={openTemplatePicker} style={styles.templateEntry}>
            <ChevronDown size={14} stroke={c.primary} />
            <Text style={[styles.templateEntryText, { color: c.primary }]}>
              {pickerLoading ? '通用入口加载中...' : '从通用入口添加'}
            </Text>
          </Pressable>

          {pickerOpen ? (
            <Card style={styles.pickerCard}>
              {available.length === 0 ? (
                <Text style={[styles.hint, { color: c.textMuted }]}>
                  通用入口为空或已全部添加（可在「我的 - 通用展示入口」中管理）
                </Text>
              ) : (
                available.map((tpl) => (
                  <Pressable key={tpl.id} onPress={() => insertTemplate(tpl)} style={styles.pickerRow}>
                    <Text style={[styles.typeBadge, { color: c.primary }]}>{TYPE_LABEL[tpl.type]}</Text>
                    <Text style={[styles.pickerName, { color: c.text }]} numberOfLines={1}>
                      {tpl.name}
                    </Text>
                    {tpl.is_default ? (
                      <Text style={[styles.defaultBadge, { color: c.success }]}>默认</Text>
                    ) : null}
                  </Pressable>
                ))
              )}
            </Card>
          ) : null}
        </>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  hint: { ...typography.small, lineHeight: 18 },
  entryCard: { gap: spacing.sm },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  typeBadge: { ...typography.small, fontWeight: '600' },
  // 类型选择器（单条模式），沿用 material-edit.tsx / notification-channels.tsx 的 chip 视觉
  typeChips: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs, flexShrink: 1 },
  typeChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.sm,
    borderWidth: 1,
  },
  typeChipText: { ...typography.caption },
  field: { gap: spacing.xs },
  label: { ...typography.caption },
  // 传入 style 会整体覆盖 Input 的基础样式，故此处补齐（对齐 accounts.tsx 的 editTextarea 写法）
  textarea: {
    ...typography.body,
    minHeight: 88,
    paddingVertical: 12,
    paddingHorizontal: spacing.md,
    borderRadius: radius.md,
    borderWidth: 1,
  },
  preview: { width: '100%', height: 140, borderRadius: radius.sm },
  previewPlaceholder: {
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderStyle: 'dashed',
    paddingHorizontal: spacing.md,
  },
  previewPlaceholderText: { ...typography.small, textAlign: 'center' },
  disabledAction: { opacity: 0.4 },
  actions: { flexDirection: 'row', gap: spacing.sm },
  actionBtn: { flex: 1 },
  templateEntry: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
    paddingVertical: spacing.xs,
  },
  templateEntryText: { ...typography.caption },
  pickerCard: { gap: spacing.xs },
  pickerRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingVertical: spacing.xs,
  },
  pickerName: { ...typography.body, flex: 1 },
  defaultBadge: { ...typography.small, fontWeight: '600' },
});
