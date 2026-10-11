import { useState, useCallback, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  Pressable,
  Image,
  Alert,
  RefreshControl,
  ActivityIndicator,
  useColorScheme,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Card, Button, Badge, EmptyState, FAB } from '@/components/ui';
import { Package, SlidersHorizontal } from 'lucide-react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  listMaterials,
  deleteMaterial,
  type ProductMaterial,
} from '@/api/wrappers/product-publish';

const PAGE_SIZE = 50;

/** 素材是否已携带商品列表配置（任一配置字段非空即标记） */
function hasConfig(m: ProductMaterial): boolean {
  const cfg = m.item_config;
  if (!cfg) return false;
  return (
    cfg.multi_quantity_delivery ||
    cfg.card_ids.length > 0 ||
    Boolean(cfg.default_reply) ||
    Boolean(cfg.ai_prompt) ||
    cfg.query_buttons.length > 0
  );
}

export default function MaterialsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();

  const [materials, setMaterials] = useState<ProductMaterial[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const res = await listMaterials(1, PAGE_SIZE);
      setMaterials(res.list);
      setTotal(res.total);
    } catch (e) {
      Alert.alert('加载素材失败', (e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleDelete = useCallback(
    (material: ProductMaterial) => {
      Alert.alert('删除素材', `确定删除「${material.title}」吗？此操作不可恢复。`, [
        { text: '取消', style: 'cancel' },
        {
          text: '删除',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteMaterial(material.id);
              setMaterials((prev) => prev.filter((x) => x.id !== material.id));
              setTotal((prev) => Math.max(0, prev - 1));
            } catch (e) {
              Alert.alert('删除失败', (e as Error).message);
            }
          },
        },
      ]);
    },
    [],
  );

  const openEdit = useCallback(
    (id?: number) => {
      router.push({
        pathname: '/(tabs)/mine/material-edit',
        params: id != null ? { id: String(id) } : {},
      });
    },
    [router],
  );

  if (loading) {
    return (
      <SafeAreaView
        style={[styles.container, { backgroundColor: c.background }]}
        edges={['left', 'right', 'bottom']}
      >
        <View style={styles.center}>
          <ActivityIndicator size="small" color={c.primary} />
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView
      style={[styles.container, { backgroundColor: c.background }]}
      edges={['left', 'right', 'bottom']}
    >
      <View style={styles.header}>
        <View>
          <Text style={[styles.title, { color: c.text }]}>素材管理</Text>
          <Text style={[styles.subtitle, { color: c.textMuted }]}>共 {total} 个素材</Text>
        </View>
        <Button
          label="新建素材"
          variant="secondary"
          onPress={() => openEdit()}
        />
      </View>

      <FlatList
        data={materials}
        keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <EmptyState
            icon={Package}
            title="暂无素材"
            message="新建素材以供单品/批量发布使用，可携带商品列表配置"
            actionLabel="新建素材"
            onAction={() => openEdit()}
          />
        }
        renderItem={({ item }) => {
          const configured = hasConfig(item);
          return (
            <Pressable
              onPress={() => openEdit(item.id)}
              onLongPress={() => handleDelete(item)}
            >
              <Card style={styles.rowCard}>
                <View style={styles.row}>
                  {item.images && item.images.length > 0 ? (
                    <Image
                      source={{ uri: item.images[0] }}
                      style={[styles.thumb, { backgroundColor: c.surfaceAlt }]}
                    />
                  ) : (
                    <View style={[styles.thumb, { backgroundColor: c.surfaceAlt }]}>
                      <Package size={20} stroke={c.textMuted} />
                    </View>
                  )}
                  <View style={styles.body}>
                    <Text style={[styles.name, { color: c.text }]} numberOfLines={2}>
                      {item.title || '未命名素材'}
                    </Text>
                    <View style={styles.meta}>
                      <Text style={[styles.price, { color: c.warning }]}>¥{item.price}</Text>
                      <Text style={[styles.metaText, { color: c.textMuted }]}>
                        {item.condition} · 数量 {item.quantity} · {item.images?.length ?? 0} 图
                      </Text>
                    </View>
                    {configured ? (
                      <View style={styles.badgeRow}>
                        <Badge label="已配列表" variant="info" />
                        <SlidersHorizontal size={12} stroke={c.textMuted} />
                      </View>
                    ) : null}
                  </View>
                </View>
              </Card>
            </Pressable>
          );
        }}
      />

      <FAB onPress={() => openEdit()} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    paddingBottom: spacing.xs,
  },
  title: { ...typography.heading },
  subtitle: { ...typography.small, marginTop: 2 },
  list: { padding: spacing.lg, paddingTop: spacing.xs, gap: spacing.md, paddingBottom: 96 },
  rowCard: { padding: spacing.md },
  row: { flexDirection: 'row', gap: spacing.md, alignItems: 'center' },
  thumb: {
    width: 52,
    height: 52,
    borderRadius: radius.sm,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: { flex: 1, gap: spacing.xs },
  name: { ...typography.caption, fontWeight: '600', lineHeight: 18 },
  meta: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  price: { ...typography.small, fontWeight: '700' },
  metaText: { ...typography.small },
  badgeRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.xs },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
});
