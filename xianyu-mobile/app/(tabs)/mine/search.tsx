import { useState, useCallback, useRef, useEffect } from 'react';
import { View, Text, StyleSheet, FlatList, TextInput, Pressable, Image, RefreshControl, ActivityIndicator, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Loading } from '@/components/ui';
import { Search } from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { compassSearch, type SearchResult } from '@/api/wrappers/search';
import { getAccountOptions, type AccountOption } from '@/api/wrappers/accounts';

const EXAMPLE_KEYWORDS = ['iphone', '手机壳', '耳机'];

export default function SearchScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const [keyword, setKeyword] = useState('');
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  // 请求序号：reset 与翻页并发时，丢弃过期响应，防止旧结果覆盖新结果
  const searchSeq = useRef(0);
  // load-more 同步锁：onEndReached 在 setLoading 生效前可能连发，用 ref 拦截
  const loadingMoreRef = useRef(false);

  const [accounts, setAccounts] = useState<AccountOption[]>([]);
  const [selectedPk, setSelectedPk] = useState<number | null>(null);
  // 页面级搜索历史（不持久化），最近 5 条
  const [history, setHistory] = useState<string[]>([]);

  useEffect(() => {
    (async () => {
      try {
        const list = await getAccountOptions();
        setAccounts(list);
        // 默认选第一个启用的账号
        const first = list.find((a) => a.enabled) ?? list[0];
        if (first) setSelectedPk(first.pk);
      } catch (e) {
        Alert.alert('加载账号失败', (e as Error).message);
      }
    })();
  }, []);

  const handleSearch = useCallback(async (resetPage: boolean, kwOverride?: string) => {
    const kw = (kwOverride ?? keyword).trim();
    if (!kw) return;
    if (selectedPk == null) {
      Alert.alert('提示', '请先选择一个闲鱼账号');
      return;
    }
    // 同步锁：onEndReached 在 setLoading(true) 生效前可能连发，用 ref 拦截重复 load-more
    if (!resetPage && loadingMoreRef.current) return;
    if (!resetPage) loadingMoreRef.current = true;
    const seq = ++searchSeq.current;
    const p = resetPage ? 1 : page + 1;
    setLoading(true);
    try {
      const resp = await compassSearch(kw, p, selectedPk);
      if (searchSeq.current !== seq) return; // 已有更新的请求，丢弃本次响应
      if (resetPage) {
        setResults(resp.data);
        // 记录搜索历史：去重、保留最近 5 条
        setHistory((prev) => {
          const next = [kw, ...prev.filter((h) => h !== kw)];
          return next.slice(0, 5);
        });
      } else {
        setResults((prev) => [...prev, ...resp.data]);
      }
      setTotal(resp.total);
      setPage(p);
    } catch (e) {
      if (searchSeq.current === seq) {
        Alert.alert('搜索失败', (e as Error).message || '网络请求出错');
      }
    } finally {
      if (searchSeq.current === seq) setLoading(false);
      if (!resetPage) loadingMoreRef.current = false;
    }
  }, [keyword, page, selectedPk]);

  const pickKeyword = useCallback((k: string) => {
    setKeyword(k);
    handleSearch(true, k);
  }, [handleSearch]);

  if (loading && results.length === 0) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="搜索中..." />
      </SafeAreaView>
    );
  }

  const selectedAccount = accounts.find((a) => a.pk === selectedPk);
  const placeholder = '搜索闲鱼商品...';
  const showGuide = !keyword.trim() && results.length === 0;

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={[styles.searchBar, { backgroundColor: c.surface, borderBottomColor: c.border }]}>
        <TextInput
          value={keyword}
          onChangeText={setKeyword}
          placeholder={placeholder}
          placeholderTextColor={c.textMuted}
          style={[styles.input, { color: c.text, backgroundColor: c.background }]}
          onSubmitEditing={() => handleSearch(true)}
          returnKeyType="search"
        />
        {keyword.length > 0 ? (
          <Pressable onPress={() => setKeyword('')} style={styles.clearBtn} hitSlop={8}>
            <Text style={[styles.clearText, { color: c.textMuted }]}>✕</Text>
          </Pressable>
        ) : null}
        <Pressable onPress={() => handleSearch(true)} style={[styles.searchBtn, { backgroundColor: c.primary }]}>
          {loading ? <ActivityIndicator color="#FFF" size="small" /> : <Text style={styles.searchBtnText}>搜索</Text>}
        </Pressable>
      </View>

      {accounts.length > 0 && (
        <FlatList
          horizontal
          style={styles.accountScroll}
          data={accounts}
          keyExtractor={(item) => String(item.pk)}
          contentContainerStyle={styles.accountList}
          showsHorizontalScrollIndicator={false}
          renderItem={({ item }) => {
            const active = selectedPk === item.pk;
            return (
              <Pressable
                onPress={() => setSelectedPk(item.pk)}
                style={[
                  styles.chip,
                  { backgroundColor: active ? c.primary : c.surface, borderColor: active ? c.primary : c.border },
                ]}
              >
                <Text style={[styles.chipText, { color: active ? '#FFF' : c.text }]} numberOfLines={1}>
                  {item.remark || item.id}
                </Text>
              </Pressable>
            );
          }}
        />
      )}

      {total > 0 && (
        <Text style={[styles.count, { color: c.textMuted }]}>共 {total} 个结果</Text>
      )}

      {showGuide ? (
        <View style={styles.guideBlock}>
          <Search size={48} stroke={c.border} />
          <Text style={[styles.guideTitle, { color: c.textSecondary }]}>搜索闲鱼商品</Text>
          <Text style={[styles.guideHint, { color: c.textMuted }]}>
            输入关键词或选择下方示例{'\n'}结果来自所选账号的闲鱼
          </Text>
          <View style={styles.chipRow}>
            {EXAMPLE_KEYWORDS.map((k) => (
              <Pressable
                key={k}
                onPress={() => pickKeyword(k)}
                style={[styles.exampleChip, { backgroundColor: c.surface, borderColor: c.border }]}
              >
                <Text style={[styles.exampleChipText, { color: c.text }]}>{k}</Text>
              </Pressable>
            ))}
          </View>
          {history.length > 0 ? (
            <View style={styles.historyBlock}>
              <Text style={[styles.historyTitle, { color: c.textMuted }]}>最近搜索</Text>
              <View style={styles.chipRow}>
                {history.map((h) => (
                  <Pressable
                    key={h}
                    onPress={() => pickKeyword(h)}
                    style={[styles.exampleChip, { backgroundColor: c.surface, borderColor: c.border }]}
                  >
                    <Text style={[styles.exampleChipText, { color: c.text }]} numberOfLines={1}>{h}</Text>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : null}
        </View>
      ) : (
        <FlatList
          data={results}
          keyExtractor={(item, i) => `${item.item_id}-${i}`}
          onEndReached={() => results.length < total && !loading && handleSearch(false)}
          onEndReachedThreshold={0.3}
          renderItem={({ item }) => (
            <Card style={styles.card}>
              <View style={styles.itemRow}>
                {item.image_url ? (
                  <Image source={{ uri: item.image_url }} style={styles.thumb} resizeMode="cover" />
                ) : (
                  <View style={[styles.thumb, { backgroundColor: c.border }]} />
                )}
                <View style={styles.itemInfo}>
                  <Text style={[styles.title, { color: c.text }]} numberOfLines={2}>{item.title}</Text>
                  <Text style={[styles.price, { color: c.primary }]}>¥{item.price}</Text>
                  {item.seller_name && (
                    <Text style={[styles.seller, { color: c.textMuted }]} numberOfLines={1}>卖家: {item.seller_name}</Text>
                  )}
                </View>
              </View>
            </Card>
          )}
          ListEmptyComponent={
            loading ? null : (
              <View style={styles.empty}><Text style={[styles.emptyText, { color: c.textMuted }]}>暂无结果</Text></View>
            )
          }
          ListFooterComponent={loading ? <ActivityIndicator color={c.primary} style={{ padding: 16 }} /> : null}
          contentContainerStyle={styles.list}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  searchBar: { flexDirection: 'row', gap: 8, paddingHorizontal: 16, paddingVertical: 8, borderBottomWidth: 1, alignItems: 'center' },
  input: { flex: 1, height: 40, borderRadius: 8, paddingHorizontal: 12, fontSize: 15 },
  searchBtn: { paddingHorizontal: 16, height: 40, borderRadius: 8, alignItems: 'center', justifyContent: 'center' },
  searchBtnText: { color: '#FFF', fontWeight: '600' },
  // 横向列表必须给显式高度：默认 flexGrow:1 会撑满整屏；仅 flexGrow:0 时安卓初始测量会把文字压扁
  accountScroll: { flexGrow: 0, height: 54 },
  accountList: { paddingHorizontal: 16, paddingVertical: 8, gap: 8, alignItems: 'center' },
  chip: { paddingHorizontal: 16, paddingVertical: 8, borderRadius: 999, borderWidth: 1 },
  chipText: { fontSize: 14, maxWidth: 120 },
  count: { fontSize: 13, paddingHorizontal: 16, paddingVertical: 4 },
  list: { padding: 16, gap: 12 },
  card: { gap: 8 },
  itemRow: { flexDirection: 'row', gap: 12 },
  thumb: { width: 64, height: 64, borderRadius: 8 },
  itemInfo: { flex: 1, gap: 4 },
  title: { fontSize: 14, lineHeight: 20 },
  price: { fontSize: 16, fontWeight: '700' },
  seller: { fontSize: 12 },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { fontSize: 16 },
  clearBtn: { width: 28, height: 40, alignItems: 'center', justifyContent: 'center' },
  clearText: { fontSize: 16 },
  // 空态引导：紧随搜索区下方
  guideBlock: { alignItems: 'center', gap: 12, paddingVertical: 24, paddingHorizontal: 16 },
  guideTitle: { ...typography.title },
  guideHint: { ...typography.small, textAlign: 'center', lineHeight: 20 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, justifyContent: 'center' },
  exampleChip: { paddingHorizontal: 14, paddingVertical: 8, borderRadius: 999, borderWidth: 1 },
  exampleChipText: { fontSize: 14 },
  historyBlock: { width: '100%', marginTop: 8, gap: 8 },
  historyTitle: { ...typography.small, textAlign: 'left' },
});
