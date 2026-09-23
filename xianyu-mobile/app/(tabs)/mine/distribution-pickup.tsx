import { useState, useCallback, useEffect, useMemo } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, Modal, Alert, RefreshControl, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Card, Button, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  getDockRecordsFull,
  getDockRecordPickupUrl,
  fetchPickupContent,
  type DockRecordFull,
} from '@/api/wrappers/distribution';

/** 按卡券商（对接记录归属的上级用户名）分组 */
interface SupplierGroup {
  supplier: string;
  records: DockRecordFull[];
}

interface PickupResult {
  dockName: string;
  pickedAt: string;
  content: string;
}

export default function DistributionPickupScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [groups, setGroups] = useState<SupplierGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [pickingId, setPickingId] = useState<number | null>(null);
  const [result, setResult] = useState<PickupResult | null>(null);

  const loadRecords = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const records = await getDockRecordsFull(1);
      const map = new Map<string, DockRecordFull[]>();
      for (const r of records) {
        const key = r.owner_username || '未知卡券商';
        const list = map.get(key);
        if (list) list.push(r);
        else map.set(key, [r]);
      }
      setGroups(
        Array.from(map.entries()).map(([supplier, recs]) => ({ supplier, records: recs })),
      );
    } catch (e) {
      setError((e as Error).message || '加载失败');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    loadRecords();
  }, [loadRecords]);

  const totalRecords = useMemo(
    () => groups.reduce((sum, g) => sum + g.records.length, 0),
    [groups],
  );

  async function copyText(text: string, label: string) {
    try {
      await Clipboard.setStringAsync(text);
      Alert.alert('已复制', `${label}已复制到剪贴板`);
    } catch {
      Alert.alert('复制失败', '剪贴板不可用');
    }
  }

  /** 提货：取免认证提货链接后直接 GET，返回纯文本卡密内容 */
  function handlePickup(record: DockRecordFull) {
    Alert.alert('确认提货', `提货「${record.dock_name}」？将按对接价格扣费。`, [
      { text: '取消' },
      {
        text: '提货',
        onPress: async () => {
          setPickingId(record.id);
          try {
            const url = await getDockRecordPickupUrl(record.id);
            const content = await fetchPickupContent(url);
            setResult({
              dockName: record.dock_name,
              pickedAt: new Date().toLocaleString(),
              content,
            });
          } catch (e) {
            Alert.alert('提货失败', (e as Error).message);
          } finally {
            setPickingId(null);
          }
        },
      },
    ]);
  }

  function statusNode(status: boolean) {
    return (
      <Text style={[styles.status, { color: status ? c.success : c.error }]}>
        {status ? '已启用' : '已停用'}
      </Text>
    );
  }

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载分销卡券..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={[styles.notice, { borderColor: c.warning }]}>
        <Text style={[styles.noticeText, { color: c.text }]}>
          提示：该功能需要后端新版支持，当前通过已对接卡券简化提货（共 {totalRecords} 条）。
        </Text>
      </View>

      <FlatList
        data={groups}
        keyExtractor={(item) => item.supplier}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={loadRecords} />}
        contentContainerStyle={styles.list}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: c.textMuted }]}>{error ?? '暂无已对接的卡券'}</Text>
          </View>
        }
        renderItem={({ item: group }) => (
          <Card style={styles.card}>
            <View style={styles.cardRow}>
              <Text style={[styles.supplier, { color: c.text }]} numberOfLines={1}>
                {group.supplier}
              </Text>
              <View style={[styles.badge, { backgroundColor: c.primaryLight }]}>
                <Text style={[styles.badgeText, { color: c.primary }]}>{group.records.length} 项</Text>
              </View>
            </View>

            {group.records.map((record) => {
              const expanded = expandedId === record.id;
              return (
                <View key={record.id} style={[styles.recordBox, { borderColor: c.borderLight }]}>
                  <Pressable
                    style={styles.recordHeader}
                    onPress={() => setExpandedId(expanded ? null : record.id)}
                  >
                    <View style={styles.recordTitleCol}>
                      <Text style={[styles.name, { color: c.text }]} numberOfLines={1}>
                        {record.dock_name}
                      </Text>
                      {statusNode(record.status)}
                    </View>
                    <Text style={[styles.expandArrow, { color: c.textMuted }]}>
                      {expanded ? '收起' : '展开'}
                    </Text>
                  </Pressable>

                  {expanded && (
                    <View style={styles.recordDetail}>
                      {record.card_name ? (
                        <Text style={[styles.meta, { color: c.textSecondary }]} numberOfLines={1}>
                          卡券: {record.card_name}
                        </Text>
                      ) : null}
                      {record.is_multi_spec && record.spec_value ? (
                        <Text style={[styles.meta, { color: c.textSecondary }]} numberOfLines={2}>
                          {record.spec_name || '规格'}: {record.spec_value}
                        </Text>
                      ) : null}
                      <View style={styles.cardRow}>
                        <Text style={[styles.meta, { color: c.textSecondary }]}>
                          发货 {record.delivery_count} 次
                        </Text>
                        <Text style={[styles.price, { color: c.primary }]}>¥{record.card_price}</Text>
                      </View>
                      <Text style={[styles.meta, { color: c.textMuted }]}>{record.created_at}</Text>
                      <Button
                        label={record.status ? '提货' : '已停用'}
                        variant={record.status ? 'primary' : 'secondary'}
                        disabled={!record.status}
                        loading={pickingId === record.id}
                        onPress={() => handlePickup(record)}
                        style={styles.pickupBtn}
                      />
                    </View>
                  )}
                </View>
              );
            })}
          </Card>
        )}
      />

      <Modal visible={result != null} transparent animationType="fade" onRequestClose={() => setResult(null)}>
        <Pressable style={styles.overlay} onPress={() => setResult(null)}>
          <Pressable style={[styles.modal, { backgroundColor: c.surface }]} onPress={() => {}}>
            <Text style={[styles.modalTitle, { color: c.text }]}>提货结果</Text>
            {result && (
              <>
                <Text style={[styles.meta, { color: c.textSecondary }]} numberOfLines={1}>
                  {result.dockName} · {result.pickedAt}
                </Text>
                <ScrollView style={[styles.contentBox, { borderColor: c.border }]} bounces={false}>
                  <Text selectable style={[styles.contentText, { color: c.text }]}>
                    {result.content}
                  </Text>
                </ScrollView>
                <View style={styles.modalActions}>
                  <Button
                    label="复制卡密"
                    variant="secondary"
                    onPress={() => copyText(result.content, '卡密内容')}
                    style={styles.modalBtn}
                  />
                  <Button label="关闭" onPress={() => setResult(null)} style={styles.modalBtn} />
                </View>
              </>
            )}
          </Pressable>
        </Pressable>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  notice: {
    marginHorizontal: spacing.lg,
    marginBottom: spacing.sm,
    padding: spacing.md,
    borderWidth: 1,
    borderRadius: 8,
  },
  noticeText: { ...typography.caption },
  list: { padding: spacing.lg, gap: spacing.md },
  card: { gap: spacing.sm },
  cardRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  supplier: { ...typography.body, fontWeight: '600', flex: 1, marginRight: spacing.sm },
  badge: { paddingHorizontal: spacing.sm, paddingVertical: 2, borderRadius: 4 },
  badgeText: { ...typography.small, fontWeight: '600' },
  recordBox: { borderWidth: 1, borderRadius: 8, padding: spacing.md, gap: spacing.xs },
  recordHeader: { flexDirection: 'row', alignItems: 'center' },
  recordTitleCol: { flex: 1, gap: 2 },
  recordDetail: { gap: spacing.xs, marginTop: spacing.xs },
  name: { ...typography.body, fontWeight: '600' },
  status: { ...typography.small, fontWeight: '600' },
  expandArrow: { ...typography.caption, marginLeft: spacing.sm },
  meta: { ...typography.caption },
  price: { ...typography.body, fontWeight: '600' },
  pickupBtn: { minHeight: 40, marginTop: spacing.xs },
  empty: { alignItems: 'center', paddingVertical: 28 },
  emptyText: { ...typography.body },
  overlay: { flex: 1, justifyContent: 'center', padding: spacing.lg, backgroundColor: 'rgba(0,0,0,0.5)' },
  modal: { borderRadius: radius.lg, padding: spacing.lg, gap: spacing.sm },
  modalTitle: { ...typography.heading, textAlign: 'center' },
  contentBox: { maxHeight: 280, borderWidth: 1, borderRadius: 8, padding: spacing.md },
  contentText: { ...typography.body },
  modalActions: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm },
  modalBtn: { flex: 1 },
});
