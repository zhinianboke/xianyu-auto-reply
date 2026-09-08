import { useState, useEffect, useRef, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  Modal,
  Pressable,
  FlatList,
  ActivityIndicator,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { CheckSquare, Square, X, Search, Ticket } from 'lucide-react-native';
import { Button, Input, Loading, EmptyState } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getSelectableCards,
  getItemCards,
  updateItemCards,
  type SelectableCard,
  type CardRelationItem,
} from '@/api/wrappers/card-relation';

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE = 300;

interface ItemCardRelationModalProps {
  itemId: string;
  itemName: string;
  visible: boolean;
  onClose: () => void;
  onSaved?: () => void;
}

const sourceLabel = (s: SelectableCard['source']) =>
  s === 'own' ? '自有' : s === 'dock_l1' ? '一级对接' : '二级对接';

export function ItemCardRelationModal({
  itemId,
  itemName,
  visible,
  onClose,
  onSaved,
}: ItemCardRelationModalProps) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  const [list, setList] = useState<SelectableCard[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loadingMore, setLoadingMore] = useState(false);
  const loadingMoreRef = useRef(false);

  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
  // 卡券缓存：累积「已关联 + 已加载各页」，供保存时还原 card_id/source/dock_record_id
  const [cardCache, setCardCache] = useState<Map<string, SelectableCard>>(
    new Map(),
  );
  const cardCacheRef = useRef(cardCache);
  cardCacheRef.current = cardCache;

  const [searchInput, setSearchInput] = useState('');
  const [appliedSearch, setAppliedSearch] = useState('');

  const mergeCache = useCallback((items: SelectableCard[]) => {
    if (items.length === 0) return;
    setCardCache((prev) => {
      const next = new Map(prev);
      for (const it of items) next.set(it.unique_key, it);
      return next;
    });
  }, []);

  // 已关联卡券 → 初始选中态 + 缓存
  const loadAssociated = useCallback(async () => {
    try {
      const existing = await getItemCards(itemId);
      mergeCache(existing);
      setSelectedKeys(new Set(existing.map((x) => x.unique_key)));
    } catch {
      // 已关联加载失败不阻塞可选列表
    }
  }, [itemId, mergeCache]);

  // 加载/重置到第一页
  const loadFirstPage = useCallback(
    async (search: string) => {
      setLoading(true);
      try {
        const res = await getSelectableCards(itemId, 1, PAGE_SIZE, search);
        setList(res.list);
        setPage(res.page);
        setTotal(res.total);
        mergeCache(res.list);
      } catch {
        setList([]);
        setTotal(0);
      } finally {
        setLoading(false);
      }
    },
    [itemId, mergeCache],
  );

  // 打开时初始化：重置搜索/选中/缓存并加载已关联卡券（可选列表由下方 appliedSearch
  // effect 在 visible 变化时统一触发，避免在此重复调用 loadFirstPage）
  useEffect(() => {
    if (!visible || !itemId) return;
    setSearchInput('');
    setAppliedSearch('');
    setCardCache(new Map());
    setSelectedKeys(new Set());
    loadAssociated();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visible, itemId]);

  // 搜索防抖 → 生效查询词 → 重新加载第一页
  useEffect(() => {
    if (!visible) return;
    const t = setTimeout(() => setAppliedSearch(searchInput.trim()), SEARCH_DEBOUNCE);
    return () => clearTimeout(t);
  }, [searchInput, visible]);

  useEffect(() => {
    if (!visible) return;
    loadFirstPage(appliedSearch);
  }, [appliedSearch, visible, loadFirstPage]);

  const loadMore = useCallback(async () => {
    if (loadingMoreRef.current || loading) return;
    if (list.length >= total) return;
    loadingMoreRef.current = true;
    setLoadingMore(true);
    try {
      const next = page + 1;
      const res = await getSelectableCards(itemId, next, PAGE_SIZE, appliedSearch);
      setList((prev) => [...prev, ...res.list]);
      setPage(res.page);
      setTotal(res.total);
      mergeCache(res.list);
    } catch {
      // 静默：加载更多失败不中断列表
    } finally {
      loadingMoreRef.current = false;
      setLoadingMore(false);
    }
  }, [loading, list.length, total, page, itemId, appliedSearch, mergeCache]);

  const toggle = useCallback((key: string) => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);

  const allLoadedSelected =
    list.length > 0 && list.every((x) => selectedKeys.has(x.unique_key));

  const handleSelectAll = useCallback(() => {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (allLoadedSelected) {
        list.forEach((x) => next.delete(x.unique_key));
      } else {
        list.forEach((x) => next.add(x.unique_key));
      }
      return next;
    });
  }, [allLoadedSelected, list]);

  const handleSave = useCallback(async () => {
    setSaving(true);
    try {
      const cardItems: CardRelationItem[] = [];
      for (const key of selectedKeys) {
        const card = cardCacheRef.current.get(key);
        // 对接卡券可能无 numeric id，跳过（与 web 行为一致，避免发送非法 card_id）
        if (card && card.id != null) {
          cardItems.push({
            card_id: card.id,
            source: card.source,
            dock_record_id: card.dock_record_id ?? null,
          });
        }
      }
      await updateItemCards(itemId, cardItems);
      onSaved?.();
      onClose();
    } catch {
      // 保存失败：保持弹窗打开以便重试
    } finally {
      setSaving(false);
    }
  }, [selectedKeys, itemId, onSaved, onClose]);

  const subtitle = (card: SelectableCard) => {
    const parts: string[] = [sourceLabel(card.source)];
    if (card.source === 'own') parts.push(card.type || '');
    else if (card.dock_name) parts.push(card.dock_name);
    if (card.is_multi_spec && card.spec_name && card.spec_value) {
      parts.push(`${card.spec_name}: ${card.spec_value}`);
    }
    if (card.price) parts.push(`¥${card.price}`);
    if (card.enabled === false) parts.push('已禁用');
    return parts.filter(Boolean).join(' | ');
  };

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <SafeAreaView
        style={[styles.overlay, { backgroundColor: c.overlay }]}
        edges={['top', 'left', 'right', 'bottom']}
      >
        <Pressable style={StyleSheet.absoluteFill} onPress={onClose} />
        <View style={[styles.sheet, { backgroundColor: c.surface }]}>
          {/* 头部 */}
          <View style={[styles.header, { borderBottomColor: c.borderLight }]}>
            <View style={styles.headerLeft}>
              <Ticket size={18} stroke={c.primary} />
              <View>
                <Text style={[styles.title, { color: c.text }]}>关联卡券</Text>
                <Text
                  style={[styles.subtitle, { color: c.textMuted }]}
                  numberOfLines={1}
                >
                  {itemName || itemId}
                </Text>
              </View>
            </View>
            <Pressable onPress={onClose} hitSlop={12}>
              <X size={20} stroke={c.textMuted} />
            </Pressable>
          </View>

          {/* 搜索 + 工具栏 */}
          <View style={[styles.toolbar, { borderBottomColor: c.borderLight }]}>
            <View style={styles.searchWrap}>
              <Search size={15} stroke={c.textMuted} style={styles.searchIcon} />
              <Input
                value={searchInput}
                onChangeText={setSearchInput}
                placeholder="搜索卡券名称/类型/对接名"
                style={styles.searchInput}
                returnKeyType="search"
              />
            </View>
            <View style={styles.toolbarRow}>
              <Pressable
                onPress={handleSelectAll}
                disabled={loading || list.length === 0}
                style={({ pressed }) => [
                  styles.selectAll,
                  {
                    backgroundColor: allLoadedSelected ? c.primaryLight : c.surfaceAlt,
                    opacity: pressed ? 0.7 : 1,
                  },
                ]}
              >
                {allLoadedSelected ? (
                  <CheckSquare size={13} stroke={c.primary} />
                ) : (
                  <Square size={13} stroke={c.textMuted} />
                )}
                <Text
                  style={[
                    styles.selectAllText,
                    { color: allLoadedSelected ? c.primary : c.textSecondary },
                  ]}
                >
                  {allLoadedSelected ? '取消全选' : '全选'}
                </Text>
              </Pressable>
              <Text style={[styles.count, { color: c.textMuted }]}>
                共 {total} 个 · 已选 {selectedKeys.size}
              </Text>
            </View>
          </View>

          {/* 列表 */}
          {loading ? (
            <View style={styles.centerBox}>
              <Loading label="加载卡券..." />
            </View>
          ) : (
            <FlatList
              data={list}
              keyExtractor={(item) => item.unique_key}
              contentContainerStyle={styles.list}
              onEndReached={loadMore}
              onEndReachedThreshold={0.2}
              ListEmptyComponent={
                <EmptyState
                  icon={Ticket}
                  title="暂无卡券"
                  message={appliedSearch ? '未匹配到卡券' : '可新建卡券后在此关联'}
                />
              }
              ListFooterComponent={
                loadingMore ? (
                  <View style={styles.footer}>
                    <ActivityIndicator size="small" color={c.primary} />
                  </View>
                ) : list.length > 0 && list.length >= total && total > 0 ? (
                  <Text style={[styles.footerText, { color: c.textMuted }]}>
                    没有更多了
                  </Text>
                ) : null
              }
              renderItem={({ item }) => {
                const checked = selectedKeys.has(item.unique_key);
                return (
                  <Pressable
                    onPress={() => toggle(item.unique_key)}
                    style={({ pressed }) => [
                      styles.row,
                      {
                        backgroundColor: checked ? c.primaryLight : 'transparent',
                        opacity: pressed ? 0.85 : 1,
                      },
                    ]}
                  >
                    {checked ? (
                      <CheckSquare size={18} stroke={c.primary} />
                    ) : (
                      <Square size={18} stroke={c.textMuted} />
                    )}
                    <View style={styles.rowBody}>
                      <Text
                        style={[styles.rowTitle, { color: c.text }]}
                        numberOfLines={1}
                      >
                        {item.name || '未命名卡券'}
                      </Text>
                      <Text
                        style={[styles.rowSub, { color: c.textMuted }]}
                        numberOfLines={1}
                      >
                        {subtitle(item)}
                      </Text>
                    </View>
                  </Pressable>
                );
              }}
            />
          )}

          {/* 底部操作 */}
          <View
            style={[styles.footerBar, { borderTopColor: c.borderLight, backgroundColor: c.surface }]}
          >
            <Button
              label="取消"
              variant="ghost"
              onPress={onClose}
              style={styles.footerBtn}
            />
            <Button
              label={`保存 (${selectedKeys.size} 个卡券)`}
              onPress={handleSave}
              loading={saving}
              disabled={saving || loading}
              style={styles.footerBtn}
            />
          </View>
        </View>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  overlay: { flex: 1, justifyContent: 'flex-end' },
  sheet: { flex: 1, maxHeight: '92%' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    borderBottomWidth: 1,
  },
  headerLeft: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm, flex: 1 },
  title: { ...typography.heading },
  subtitle: { ...typography.small, maxWidth: 220 },
  toolbar: { paddingHorizontal: spacing.lg, paddingVertical: spacing.sm, borderBottomWidth: 1, gap: spacing.sm },
  searchWrap: { flexDirection: 'row', alignItems: 'center' },
  searchIcon: { position: 'absolute', left: spacing.sm, zIndex: 1 },
  searchInput: { minHeight: 40, paddingLeft: spacing.xl + spacing.sm },
  toolbarRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  selectAll: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: spacing.sm,
    paddingVertical: 4,
    borderRadius: radius.sm,
  },
  selectAllText: { ...typography.small, fontWeight: '600' },
  count: { ...typography.small },
  list: { paddingVertical: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
  },
  rowBody: { flex: 1, gap: 2 },
  rowTitle: { ...typography.caption, fontWeight: '600' },
  rowSub: { ...typography.small },
  centerBox: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  footer: { paddingVertical: spacing.lg, alignItems: 'center' },
  footerText: { ...typography.small, textAlign: 'center', paddingVertical: spacing.md },
  footerBar: {
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderTopWidth: 1,
  },
  footerBtn: { flex: 1 },
});
