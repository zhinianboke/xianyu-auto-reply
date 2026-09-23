import { Stack, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { SafeAreaProvider } from 'react-native-safe-area-context';
import { useEffect } from 'react';
import { useConfigStore } from '@/stores/config';
import { useAuthStore } from '@/stores/auth';
import { Loading } from '@/components/ui';
import { AlertProvider } from '@/components/ui/Alert';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { verifyToken } from '@/api/wrappers/auth';
import { logger } from '@/lib/logger';

export default function RootLayout() {
  const initConfig = useConfigStore((s) => s.init);
  const initAuth = useAuthStore((s) => s.init);
  const configLoading = useConfigStore((s) => s.loading);
  const authLoading = useAuthStore((s) => s.loading);
  const token = useAuthStore((s) => s.token);
  const serverUrl = useConfigStore((s) => s.serverUrl);
  const verifyAndSetUser = useAuthStore((s) => s.verifyAndSetUser);
  const logout = useAuthStore((s) => s.logout);
  const router = useRouter();

  useEffect(() => {
    logger.info('APP', '应用启动，初始化配置和认证状态...');
    initConfig();
    initAuth();
  }, []);

  // 有 token 时验证有效性
  useEffect(() => {
    if (!token || configLoading) return;
    logger.info('AUTH', '验证 token 有效性...');
    verifyToken()
      .then((resp) => {
        if (resp.authenticated && resp.user_id != null && resp.username != null) {
          logger.info('AUTH', `token 有效: user=${resp.username}`);
          verifyAndSetUser({
            user_id: resp.user_id,
            username: resp.username,
            is_admin: resp.is_admin ?? false,
            account_limit: resp.account_limit ?? null,
          });
        } else {
          logger.warn('AUTH', 'token 无效，清除登录状态');
          logout();
        }
      })
      .catch((e) => {
        logger.warn('AUTH', `验证失败(服务器不可达?): ${(e as Error).message}`);
      });
  }, [token, configLoading]);

  // token 被清除时（如 401）自动跳转登录页
  useEffect(() => {
    if (authLoading || configLoading) return;
    if (!token && serverUrl) {
      // token 从有到无，说明登出或 401，需跳转登录
      logger.info('AUTH', 'token 已清除，跳转登录页');
      router.replace('/(onboarding)/login');
    } else if (!serverUrl) {
      logger.info('AUTH', '未配置服务器，跳转配置页');
      router.replace('/(onboarding)/server-config');
    }
  }, [token, serverUrl, authLoading, configLoading]);

  if (configLoading || authLoading) {
    return <Loading />;
  }

  return (
    <ErrorBoundary>
      <AlertProvider>
        <SafeAreaProvider>
          <StatusBar style="auto" />
          <Stack screenOptions={{ headerShown: false }}>
            <Stack.Screen name="index" />
            <Stack.Screen name="(onboarding)" />
            <Stack.Screen name="(tabs)" />
          </Stack>
        </SafeAreaProvider>
      </AlertProvider>
    </ErrorBoundary>
  );
}
