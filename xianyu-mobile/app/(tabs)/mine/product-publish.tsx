import { useState, useCallback, useEffect } from 'react';
import { View, Text, StyleSheet, FlatList, RefreshControl, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { getPersonalAddresses, type PersonalAddress } from '@/api/wrappers/distribution';

export default function ProductPublishScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [addresses, setAddresses] = useState<PersonalAddress[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      setAddresses(await getPersonalAddresses());
    } catch (e) {
      Alert.alert('加载失败', (e as Error).message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载地址..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>

      <View style={styles.bannerWrap}>
        <View style={[styles.banner, { backgroundColor: c.primaryLight }]}>
          <Text style={[styles.bannerText, { color: c.primary }]}>
            当前为 Phase 1：仅展示发布地址。发布操作将在 Phase 2 上线。
          </Text>
        </View>
      </View>

      <FlatList
        data={addresses}
        keyExtractor={(item) => String(item.id)}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={load} />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: c.textMuted }]}>
              暂无收货地址
            </Text>
          </View>
        }
        renderItem={({ item }) => (
          <Card style={styles.card}>
            <View style={styles.cardRow}>
              <Text style={[styles.name, { color: c.text }]}>{item.name}</Text>
              <Text style={[styles.phone, { color: c.textSecondary }]}>
                {item.phone}
              </Text>
            </View>
            <Text style={[styles.address, { color: c.textSecondary }]}>
              {item.address}
            </Text>
          </Card>
        )}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  bannerWrap: { paddingHorizontal: spacing.lg, paddingBottom: spacing.sm },
  banner: { borderRadius: radius.md, padding: spacing.md },
  bannerText: { ...typography.caption },
  list: { padding: spacing.lg, gap: spacing.md },
  card: { gap: spacing.xs },
  cardRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  name: { ...typography.body, fontWeight: '600' },
  phone: { ...typography.caption },
  address: { ...typography.caption },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
});
