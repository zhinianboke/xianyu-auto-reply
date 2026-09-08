import { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, Pressable } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { useColorScheme } from 'react-native';
import * as Clipboard from 'expo-clipboard';
import { Button, Input } from '@/components/ui';
import { useAlert } from '@/components/ui/Alert';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { isTimeoutError, withTimeout } from '@/lib/timeout';
import { useConfigStore } from '@/stores/config';
import { logger, subscribeLogs, exportLogsAsString, type LogEntry } from '@/lib/logger';

export default function ServerConfigScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();
  const showAlert = useAlert();
  const addProfile = useConfigStore((s) => s.addProfile);
  const [name, setName] = useState('');
  const [url, setUrl] = useState('');
  const [testing, setTesting] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [showLogs, setShowLogs] = useState(false);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    const unsub = subscribeLogs((newLogs) => setLogs(newLogs.slice(0, 30)));
    return unsub;
  }, []);

  function formatTime(ts: number): string {
    const d = new Date(ts);
    return `${d.getHours().toString().padStart(2, '0')}:${d.getMinutes().toString().padStart(2, '0')}:${d.getSeconds().toString().padStart(2, '0')}`;
  }

  async function handleCopyLogs() {
    try {
      await Clipboard.setStringAsync(exportLogsAsString());
    } catch {
      // expo-clipboard native module not available in this build
    }
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  async function handleSave() {
    if (!url.trim()) {
      showAlert({ title: '提示', message: '请输入服务器地址' });
      return;
    }
    let normalizedUrl = url.trim();
    if (!normalizedUrl.startsWith('http')) {
      normalizedUrl = `http://${normalizedUrl}`;
    }
    normalizedUrl = normalizedUrl.replace(/\/+$/, '');

    setTesting(true);
    logger.info('CONFIG', `测试连接: ${normalizedUrl}/api/v1/health/ping`);
    try {
      const testUrl = `${normalizedUrl}/api/v1/health/ping`;

      // 超时保护：15 秒内未响应则 UI 报错（不 cancel 请求，避免 canceled 报错）
      // 注意：域名可能解析到不可达的 IPv6 地址导致连接黑洞，超时提示用 IP 直连
      const fetchPromise = fetch(testUrl, { headers: { Accept: 'application/json' } });
      const resp = await withTimeout(fetchPromise, 15000, 'TIMEOUT_15S');

      logger.info('CONFIG', `响应状态: ${resp.status}`);
      if (!resp.ok) throw new Error(`服务器返回 HTTP ${resp.status}`);
      const data = await resp.json();
      if (data?.success !== true && data?.data?.status !== 'ok') {
        throw new Error('服务器响应格式不正确');
      }
      logger.info('CONFIG', `连接成功，保存服务器: ${normalizedUrl}`);
      await addProfile({ name: name.trim() || '默认服务器', url: normalizedUrl });
      router.replace('/(onboarding)/login');
    } catch (e) {
      const err = e as Error;
      let msg = err.message || '未知错误';
      if (isTimeoutError(e)) {
        msg = '连接超时（15秒）。\n\n常见原因：域名解析到了不可达的 IPv6 地址。\n建议：改用 IP 地址连接，如 http://113.205.186.225:18095\n（IP 可在电脑上 ping 域名获得）';
      } else if (msg === 'Network request failed') {
        msg = '网络请求失败，请检查：\n1. 服务器地址是否正确\n2. 手机网络是否正常\n3. 服务器是否正在运行\n\n若用域名失败，建议改用 IP 地址直连';
      }
      logger.error('CONFIG', `连接失败: ${msg}`, { rawError: err.message, url: normalizedUrl });
      showAlert({ title: '连接失败', message: msg, copyable: true });
    } finally {
      setTesting(false);
    }
  }

  async function handleSkip() {
    if (!url.trim()) {
      showAlert({ title: '提示', message: '请输入服务器地址' });
      return;
    }
    let normalizedUrl = url.trim();
    if (!normalizedUrl.startsWith('http')) normalizedUrl = `http://${normalizedUrl}`;
    normalizedUrl = normalizedUrl.replace(/\/+$/, '');
    logger.info('CONFIG', `跳过测试，直接保存: ${normalizedUrl}`);
    await addProfile({ name: name.trim() || '默认服务器', url: normalizedUrl });
    router.replace('/(onboarding)/login');
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        {/* Hero */}
        <View style={styles.hero}>
          <View style={[styles.logo, { backgroundColor: c.primary }]}>
            <Text style={styles.logoText}>闲</Text>
          </View>
          <Text style={[styles.appName, { color: c.text }]}>闲鱼管家</Text>
          <Text style={[styles.subtitle, { color: c.textSecondary }]}>
            连接你的管理后台，开始使用
          </Text>
        </View>

        {/* 表单 */}
        <View style={[styles.form, { backgroundColor: c.surface, borderColor: c.borderLight }]}>
          <Text style={[styles.label, { color: c.textSecondary }]}>服务器地址</Text>
          <Input
            value={url}
            onChangeText={setUrl}
            placeholder="http://your-server-ip:8095"
            autoCapitalize="none"
            autoCorrect={false}
            keyboardType="url"
            style={styles.input}
          />
          <Text style={[styles.label, { color: c.textSecondary, marginTop: spacing.md }]}>
            名称（可选）
          </Text>
          <Input
            value={name}
            onChangeText={setName}
            placeholder="如：我的服务器"
            style={styles.input}
          />
        </View>

        {/* 按钮 */}
        <View style={styles.actions}>
          <Button
            label={testing ? '测试连接中...' : '测试并保存'}
            onPress={handleSave}
            loading={testing}
          />
          <Button label="跳过测试直接保存" onPress={handleSkip} variant="ghost" />
        </View>

        {/* 日志区域 */}
        {logs.length > 0 && (
          <View style={[styles.logSection, { backgroundColor: c.surface, borderColor: c.borderLight }]}>
            <View style={styles.logHeader}>
              <Text style={[styles.logTitle, { color: c.text }]}>调试日志</Text>
              <View style={{ flexDirection: 'row', gap: spacing.sm }}>
                <Pressable onPress={handleCopyLogs} style={({ pressed }) => [styles.logBtn, { backgroundColor: copied ? c.success : c.borderLight, borderColor: c.border }, pressed && { opacity: 0.7 }]}>
                  <Text style={{ fontSize: 11, fontWeight: '600', color: copied ? '#FFF' : c.textSecondary }}>{copied ? '✓ 已复制' : '复制日志'}</Text>
                </Pressable>
                <Pressable onPress={() => setShowLogs(!showLogs)} style={({ pressed }) => [styles.logBtn, { backgroundColor: c.borderLight, borderColor: c.border }, pressed && { opacity: 0.7 }]}>
                  <Text style={{ fontSize: 11, fontWeight: '600', color: c.textSecondary }}>{showLogs ? '收起' : '展开'}</Text>
                </Pressable>
              </View>
            </View>
            {showLogs && (
              <ScrollView style={styles.logList} nestedScrollEnabled>
                {logs.map((log) => (
                  <View key={log.id} style={[styles.logItem, { borderBottomColor: c.borderLight }]}>
                    <Text style={[styles.logMeta, { color: c.textMuted }]}>
                      {formatTime(log.timestamp)} [{log.tag}] {log.level.toUpperCase()}
                    </Text>
                    <Text style={[styles.logMsg, { color: c.textSecondary }]} selectable>{log.message}</Text>
                    {log.data && <Text style={[styles.logData, { color: c.textMuted }]} selectable>{log.data}</Text>}
                  </View>
                ))}
              </ScrollView>
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: spacing.xl, gap: spacing.xl },
  hero: { alignItems: 'center', gap: spacing.sm, marginTop: spacing.xxxl, marginBottom: spacing.xl },
  logo: { width: 72, height: 72, borderRadius: 20, alignItems: 'center', justifyContent: 'center' },
  logoText: { color: '#FFF', fontSize: 36, fontWeight: '800' },
  appName: { ...typography.largeTitle },
  subtitle: { ...typography.caption },
  form: {
    borderRadius: radius.lg,
    padding: spacing.lg,
    gap: spacing.sm,
    borderWidth: 1,
  },
  label: { ...typography.small, fontWeight: '500' as const },
  input: { marginTop: spacing.xs },
  actions: { gap: spacing.sm },
  logSection: { borderRadius: radius.md, borderWidth: 1, padding: spacing.md, gap: spacing.sm },
  logHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  logTitle: { ...typography.caption, fontWeight: '600' },
  logBtn: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 6, borderWidth: 1 },
  logList: { maxHeight: 200, gap: 4 },
  logItem: { paddingVertical: 6, borderBottomWidth: 1, gap: 2 },
  logMeta: { fontSize: 10, fontFamily: 'monospace' },
  logMsg: { fontSize: 12, fontFamily: 'monospace', lineHeight: 16 },
  logData: { fontSize: 11, fontFamily: 'monospace', opacity: 0.7, lineHeight: 14 },
});
