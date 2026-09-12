import { useState, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, Alert, RefreshControl, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Loading, FilterTabs } from '@/components/ui';
import { colors, spacing, typography } from '@/lib/theme';
import { getTableData } from '@/api/wrappers/admin';

// 后端 TABLE_MAP（admin.py:45-55）：orders 需用 xy_orders，cards 表未注册（后端未开放）
const TABLE_OPTIONS = [
  { key: 'default_replies', label: '默认回复' },
  { key: 'keywords', label: '关键词' },
  { key: 'cookies', label: '账号' },
  { key: 'xy_orders', label: '订单' },
  { key: 'item_info', label: '商品信息' },
  { key: 'notification_channels', label: '通知渠道' },
  { key: 'risk_control_logs', label: '风控日志' },
];

export default function DataManagementScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const [selectedTable, setSelectedTable] = useState('default_replies');
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [columns, setColumns] = useState<string[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const { rows, count, columns } = await getTableData(selectedTable);
      setRows(rows); setCount(count); setColumns(columns);
    } catch (e) { Alert.alert('加载失败', (e as Error).message); }
    finally { setLoading(false); }
  }, [selectedTable]);

  useEffect(() => { load(); }, [load]);

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left','right','bottom']}>
      <FilterTabs tabs={TABLE_OPTIONS} active={selectedTable} onChange={setSelectedTable} />
      <View style={styles.toolbar}>
        <Text style={[styles.count, { color: c.textMuted }]}>共 {count} 条</Text>
      </View>
      {loading ? (
        <Loading label="加载数据..." />
      ) : rows.length === 0 ? (
        <View style={styles.empty}><Text style={{ color: c.textMuted }}>暂无数据</Text></View>
      ) : (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.tableScroll}>
          <View style={styles.table}>
            <View style={[styles.tableHeader, { backgroundColor: c.surfaceAlt }]}>
              {columns.map(col => (
                <Text key={col} style={[styles.headerCell, { color: c.textSecondary }]}>{col}</Text>
              ))}
            </View>
            <FlatList
              data={rows.slice(0, 100)}
              keyExtractor={(_, i) => String(i)}
              scrollEnabled={false}
              renderItem={({ item }) => (
                <View style={[styles.tableRow, { borderBottomColor: c.borderLight }]}>
                  {columns.map(col => (
                    <Text key={col} style={[styles.cell, { color: c.text }]} numberOfLines={1}>
                      {String(item[col] ?? '')}
                    </Text>
                  ))}
                </View>
              )}
            />
          </View>
        </ScrollView>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  toolbar: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: spacing.lg, paddingVertical: spacing.sm },
  count: { ...typography.small },
  tableScroll: { flex: 1 },
  table: { minWidth: 600 },
  tableHeader: { flexDirection: 'row', borderBottomWidth: 1 },
  headerCell: { minWidth: 100, paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, fontSize: 12, fontWeight: '600' },
  tableRow: { flexDirection: 'row', borderBottomWidth: 1 },
  cell: { minWidth: 100, paddingHorizontal: spacing.sm, paddingVertical: spacing.xs, fontSize: 12 },
  empty: { alignItems: 'center', paddingVertical: 40 },
});
