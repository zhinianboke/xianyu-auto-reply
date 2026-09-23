import { useState, useEffect, useCallback } from 'react';
import { View, Text, StyleSheet, ScrollView, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { useRouter } from 'expo-router';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { Card, Button, Loading } from '@/components/ui';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { getSystemSettings } from '@/api/wrappers/settings';

const DISCLAIMER_AGREED_KEY = 'disclaimer_agreed_v1';

/** 免责声明标题的候选 key */
const TITLE_KEYS = ['disclaimer_title', 'app_disclaimer_title'];
/** 免责声明正文的候选 key */
const CONTENT_KEYS = ['disclaimer', 'disclaimer_content', 'app_disclaimer'];

/** 从系统设置中按候选 key 顺序取第一个非空字符串 */
function pick(settings: Record<string, string>, keys: string[]): string {
  for (const k of keys) {
    const v = settings[k];
    if (v && v.trim()) return v.trim();
  }
  return '';
}

export default function DisclaimerScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];
  const router = useRouter();

  const [title, setTitle] = useState('免责声明');
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(true);
  const [agreeing, setAgreeing] = useState(false);

  const load = useCallback(async () => {
    try {
      const settings = await getSystemSettings();
      const t = pick(settings, TITLE_KEYS);
      const body = pick(settings, CONTENT_KEYS);
      if (t) setTitle(t);
      setContent(
        body ||
          '本应用仅供学习和个人使用，使用者需自行承担使用风险。' +
            '本应用不对任何因使用本应用而产生的直接或间接损失负责。' +
            '请遵守相关法律法规及平台规则，规范使用。',
      );
    } catch (e) {
      // 设置加载失败时使用默认文案，保证页面可用
      console.warn('加载免责声明失败', e);
      setContent(
        '本应用仅供学习和个人使用，使用者需自行承担使用风险。' +
          '本应用不对任何因使用本应用而产生的直接或间接损失负责。' +
          '请遵守相关法律法规及平台规则，规范使用。',
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleAgree() {
    setAgreeing(true);
    try {
      await AsyncStorage.setItem(DISCLAIMER_AGREED_KEY, String(Date.now()));
      Alert.alert('提示', '感谢您的理解与支持', [
        { text: '好的', onPress: () => router.back() },
      ]);
    } catch (e) {
      Alert.alert('操作失败', (e as Error).message);
    } finally {
      setAgreeing(false);
    }
  }

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
        <Card style={styles.bodyCard}>
          <Text style={[styles.body, { color: c.textSecondary }]}>{content}</Text>
        </Card>
      </ScrollView>

      <View style={[styles.footer, { backgroundColor: c.background }]}>
        <Button
          label="我已阅读并同意"
          onPress={handleAgree}
          loading={agreeing}
          style={styles.agreeBtn}
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.md, paddingBottom: spacing.xxl },
  bodyCard: { gap: spacing.xs },
  body: { ...typography.body, lineHeight: 26 },
  footer: {
    padding: spacing.lg,
    paddingBottom: spacing.xl,
    borderTopColor: 'transparent',
  },
  agreeBtn: { minHeight: 50, borderRadius: radius.md },
});
