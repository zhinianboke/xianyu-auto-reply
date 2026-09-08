import { View, Text, StyleSheet, Alert } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useColorScheme } from 'react-native';
import { Card, Button } from '@/components/ui';
import { colors, spacing, typography } from '@/lib/theme';

export default function TutorialScreen() {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: c.background }]} edges={['left', 'right', 'bottom']}>
      <View style={styles.content}>
        <Text style={[styles.title, { color: c.text }]}>使用教程</Text>
        <Card style={styles.section}>
          <Text style={[styles.heading, { color: c.text }]}>1. 服务器配置</Text>
          <Text style={[styles.body, { color: c.textSecondary }]}>
            首次使用需要输入你的闲鱼管家后端地址，点击测试并保存。
          </Text>
        </Card>
        <Card style={styles.section}>
          <Text style={[styles.heading, { color: c.text }]}>2. 登录</Text>
          <Text style={[styles.body, { color: c.textSecondary }]}>
            使用管理员分配的用户名和密码登录。支持账号密码、邮箱密码和验证码三种方式。
          </Text>
        </Card>
        <Card style={styles.section}>
          <Text style={[styles.heading, { color: c.text }]}>3. 账号管理</Text>
          <Text style={[styles.body, { color: c.textSecondary }]}>
            在"我的"→"账号管理"中添加闲鱼账号，支持扫码登录和密码登录。添加后可配置自动回复、自动评价等功能开关。
          </Text>
        </Card>
        <Card style={styles.section}>
          <Text style={[styles.heading, { color: c.text }]}>4. 消息聊天</Text>
          <Text style={[styles.body, { color: c.textSecondary }]}>
            在"消息"Tab 中选择账号，查看会话列表。支持发送文本和图片、快捷短语、消息撤回、查看客户订单等。
          </Text>
        </Card>
        <Card style={styles.section}>
          <Text style={[styles.heading, { color: c.text }]}>5. 订单管理</Text>
          <Text style={[styles.body, { color: c.textSecondary }]}>
            在"订单"Tab 中查看订单列表、同步闲鱼订单、配置自动评价和自动确认收货。
          </Text>
        </Card>
        <Card style={styles.section}>
          <Text style={[styles.heading, { color: c.text }]}>6. 商品管理</Text>
          <Text style={[styles.body, { color: c.textSecondary }]}>
            在"商品"Tab 中查看商品监控、管理卡券和配置发货规则。
          </Text>
        </Card>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  content: { padding: spacing.lg, gap: spacing.md },
  title: { ...typography.title, marginTop: spacing.xl },
  section: { gap: spacing.sm },
  heading: { ...typography.heading },
  body: { ...typography.body, lineHeight: 22 },
});
