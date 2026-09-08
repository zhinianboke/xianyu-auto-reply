import { useState, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, FlatList, Pressable, ScrollView } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Card, Button, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import {
  subscribeLogs,
  clearLogs,
  exportLogsAsString,
  getLogStats,
  type LogEntry,
  type LogLevel,
} from '@/lib/logger';

const LEVEL_COLORS: Record<LogLevel, string> = {
  debug: '#9CA3AF',
  info: '#3B82F6',
  warn: '#F59E0B',
  error: '#EF4444',
};

const LEVEL_LABELS: Record<LogLevel, string> = {
  debug: 'DEBUG',
  info: 'INFO',
  warn: 'WARN',
  error: 'ERROR',
};

export default function AppLogsScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [filter, setFilter] = useState<LogLevel | 'all'>('all');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const unsub = subscribeLogs((newLogs) => setLogs(newLogs));
    return unsub;
  }, []);

  const filtered = filter === 'all' ? logs : logs.filter((l) => l.level === filter);
  const stats = getLogStats();

  async function handleCopyAll() {
    const text = exportLogsAsString();
    try {
      await Clipboard.setStringAsync(text);
    } catch {
      // expo-clipboard native module not available in this build
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  function formatTime(ts: number): string {
    const d = new Date(ts);
    const h = d.getHours().toString().padStart(2, '0');
    const m = d.getMinutes().toString().padStart(2, '0');
    const s = d.getSeconds().toString().padStart(2, '0');
    const ms = d.getMilliseconds().toString().padStart(3, '0');
    return `${h}:${m}:${s}.${ms}`;
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      {/* 统计栏 */}
      <View style={[styles.statsBar, { backgroundColor: c.surface, borderBottomColor: c.borderLight }]}>
        <Pressable
          onPress={() => setFilter('all')}
          style={[styles.filterChip, { backgroundColor: filter === 'all' ? c.primary : c.background, borderColor: c.border }]}
        >
          <Text style={[styles.filterText, { color: filter === 'all' ? '#FFF' : c.text }]}>
            全部 {stats.total}
          </Text>
        </Pressable>
        <Pressable
          onPress={() => setFilter('error')}
          style={[styles.filterChip, { backgroundColor: filter === 'error' ? c.error : c.background, borderColor: c.border }]}
        >
          <Text style={[styles.filterText, { color: filter === 'error' ? '#FFF' : c.text }]}>
            错误 {stats.errors}
          </Text>
        </Pressable>
        <Pressable
          onPress={() => setFilter('warn')}
          style={[styles.filterChip, { backgroundColor: filter === 'warn' ? c.warning : c.background, borderColor: c.border }]}
        >
          <Text style={[styles.filterText, { color: filter === 'warn' ? '#FFF' : c.text }]}>
            警告 {stats.warns}
          </Text>
        </Pressable>
        <Pressable
          onPress={() => setFilter('info')}
          style={[styles.filterChip, { backgroundColor: filter === 'info' ? c.info : c.background, borderColor: c.border }]}
        >
          <Text style={[styles.filterText, { color: filter === 'info' ? '#FFF' : c.text }]}>
            信息
          </Text>
        </Pressable>
      </View>

      {/* 操作栏 */}
      <View style={[styles.actionBar, { backgroundColor: c.surface, borderBottomColor: c.borderLight }]}>
        <Button label={copied ? '✓ 已复制' : '复制全部日志'} onPress={handleCopyAll} variant="secondary" style={styles.actionBtn} />
        <Button label="清除日志" onPress={() => clearLogs()} variant="danger" style={styles.actionBtn} />
      </View>

      {/* 日志列表 */}
      <FlatList
        data={filtered}
        keyExtractor={(item) => String(item.id)}
        renderItem={({ item }) => (
          <View style={[styles.logItem, { borderBottomColor: c.borderLight }]}>
            <View style={styles.logHeader}>
              <Text style={[styles.logLevel, { color: LEVEL_COLORS[item.level] }]}>
                {LEVEL_LABELS[item.level]}
              </Text>
              <Text style={[styles.logTag, { color: c.textMuted }]}>[{item.tag}]</Text>
              <Text style={[styles.logTime, { color: c.textMuted }]}>{formatTime(item.timestamp)}</Text>
            </View>
            <Text style={[styles.logMessage, { color: c.text }]} selectable>
              {item.message}
            </Text>
            {item.data && (
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                <Text style={[styles.logData, { color: c.textSecondary }]} selectable>
                  {item.data}
                </Text>
              </ScrollView>
            )}
          </View>
        )}
        ListEmptyComponent={
          <View style={styles.empty}>
            <Text style={[styles.emptyText, { color: c.textMuted }]}>暂无日志</Text>
          </View>
        }
        contentContainerStyle={styles.list}
      />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  statsBar: {
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
  },
  filterChip: {
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.xs,
    borderRadius: radius.full,
    borderWidth: 1,
  },
  filterText: { fontSize: 12, fontWeight: '600' },
  actionBar: {
    flexDirection: 'row',
    gap: spacing.sm,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    borderBottomWidth: 1,
  },
  actionBtn: { flex: 1, minHeight: 40 },
  list: { padding: spacing.sm },
  logItem: {
    padding: spacing.sm,
    borderBottomWidth: 1,
    gap: spacing.xs,
  },
  logHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.xs,
  },
  logLevel: { fontSize: 11, fontWeight: '700', fontFamily: 'monospace' },
  logTag: { fontSize: 11, fontFamily: 'monospace' },
  logTime: { fontSize: 11, fontFamily: 'monospace', marginLeft: 'auto' },
  logMessage: { fontSize: 13, lineHeight: 18, fontFamily: 'monospace' },
  logData: { fontSize: 12, fontFamily: 'monospace', opacity: 0.7 },
  empty: { alignItems: 'center', paddingVertical: 60 },
  emptyText: { fontSize: 16 },
});
