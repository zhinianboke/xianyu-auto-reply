import { useState, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, Linking, Pressable, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import Constants from 'expo-constants';
import QRCode from 'react-native-qrcode-svg';
import { Card, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { getSystemSettings } from '@/api/wrappers/settings';
import { Info, Phone, Mail, Globe, MessageCircle } from 'lucide-react-native';

/** 从系统设置中按候选 key 顺序取第一个非空字符串 */
function pick(settings: Record<string, string>, keys: string[]): string {
  for (const k of keys) {
    const v = settings[k];
    if (v && v.trim()) return v.trim();
  }
  return '';
}

export default function AboutScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [settings, setSettings] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);

  const appName = Constants.expoConfig?.name ?? '闲鱼管家';
  const appVersion = Constants.expoConfig?.version ?? '1.0.0';

  const load = useCallback(async () => {
    try {
      const data = await getSystemSettings();
      setSettings(data);
    } catch (e) {
      // 关于页对设置加载失败应保持静默，仍展示基础信息
      console.warn('加载系统设置失败', e);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const description = pick(settings, [
    'app_description',
    'about',
    'app_about',
    'description',
  ]);
  const groupQr = pick(settings, [
    'qq_group_qrcode',
    'group_qrcode',
    'qq_group',
    'qrcode',
  ]);
  const contact = pick(settings, [
    'contact',
    'contact_info',
    'customer_service',
    'qq',
  ]);
  const email = pick(settings, ['email', 'support_email']);
  const website = pick(settings, ['website', 'site', 'official_url']);

  if (loading) {
    return (
      <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
        <Loading label="加载中..." />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        {/* 应用信息 */}
        <View style={styles.appHeader}>
          <View style={[styles.appIcon, { backgroundColor: c.primary }]}>
            <Text style={styles.appIconText}>{appName.charAt(0)}</Text>
          </View>
          <Text style={[styles.appName, { color: c.text }]}>{appName}</Text>
          <View style={[styles.versionBadge, { backgroundColor: c.primaryLight }]}>
            <Text style={[styles.versionText, { color: c.primary }]}>v{appVersion}</Text>
          </View>
        </View>

        {description ? (
          <Card style={styles.section}>
            <View style={styles.sectionTitleRow}>
              <Info size={16} stroke={c.textSecondary} />
              <Text style={[styles.sectionTitle, { color: c.textSecondary }]}>应用介绍</Text>
            </View>
            <Text style={[styles.description, { color: c.text }]}>{description}</Text>
          </Card>
        ) : null}

        {/* 群二维码 */}
        {groupQr ? (
          <Card style={styles.section}>
            <View style={styles.sectionTitleRow}>
              <MessageCircle size={16} stroke={c.textSecondary} />
              <Text style={[styles.sectionTitle, { color: c.textSecondary }]}>交流群</Text>
            </View>
            <View style={styles.qrWrap}>
              <View style={[styles.qrBox, { backgroundColor: '#FFFFFF' }]}>
                <QRCode
                  value={groupQr}
                  size={180}
                  color="#1A1A1A"
                  backgroundColor="#FFFFFF"
                  quietZone={10}
                />
              </View>
              <Text style={[styles.qrHint, { color: c.textMuted }]}>
                扫描二维码加入交流群
              </Text>
            </View>
          </Card>
        ) : null}

        {/* 联系方式 */}
        {(contact || email || website) ? (
          <Card style={styles.section}>
            <View style={styles.sectionTitleRow}>
              <Phone size={16} stroke={c.textSecondary} />
              <Text style={[styles.sectionTitle, { color: c.textSecondary }]}>联系方式</Text>
            </View>
            {contact ? (
              <Pressable
                style={styles.contactRow}
                onPress={() => Linking.openURL(`tel:${contact}`).catch(() => {})}
              >
                <Phone size={18} stroke={c.textSecondary} />
                <Text style={[styles.contactText, { color: c.text }]}>{contact}</Text>
              </Pressable>
            ) : null}
            {email ? (
              <Pressable
                style={styles.contactRow}
                onPress={() => Linking.openURL(`mailto:${email}`).catch(() => {})}
              >
                <Mail size={18} stroke={c.textSecondary} />
                <Text style={[styles.contactText, { color: c.text }]}>{email}</Text>
              </Pressable>
            ) : null}
            {website ? (
              <Pressable
                style={styles.contactRow}
                onPress={() => {
                  const url = website.startsWith('http') ? website : `https://${website}`;
                  Linking.openURL(url).catch(() => Alert.alert('提示', '无法打开链接'));
                }}
              >
                <Globe size={18} stroke={c.textSecondary} />
                <Text style={[styles.contactText, { color: c.primary }]} numberOfLines={1}>
                  {website}
                </Text>
              </Pressable>
            ) : null}
          </Card>
        ) : null}

        <Text style={[styles.copyright, { color: c.textMuted }]}>
          © {new Date().getFullYear()} {appName}
        </Text>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.lg, paddingBottom: spacing.xxl },
  appHeader: { alignItems: 'center', gap: spacing.sm, paddingVertical: spacing.lg },
  appIcon: {
    width: 72,
    height: 72,
    borderRadius: 18,
    alignItems: 'center',
    justifyContent: 'center',
  },
  appIconText: { color: '#FFF', fontSize: 36, fontWeight: '700' },
  appName: { ...typography.title },
  versionBadge: {
    paddingHorizontal: spacing.md,
    paddingVertical: 2,
    borderRadius: radius.sm,
  },
  versionText: { ...typography.caption, fontWeight: '600' },
  section: { gap: spacing.md },
  sectionTitleRow: { flexDirection: 'row', alignItems: 'center', gap: spacing.sm },
  sectionTitle: { ...typography.caption, fontWeight: '600' },
  description: { ...typography.body, lineHeight: 24 },
  qrWrap: { alignItems: 'center', gap: spacing.sm },
  qrBox: { padding: 4, borderRadius: radius.md },
  qrHint: { ...typography.small },
  contactRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingVertical: spacing.xs,
  },
  contactText: { ...typography.body, flex: 1 },
  copyright: { ...typography.small, textAlign: 'center', marginTop: spacing.md },
});
