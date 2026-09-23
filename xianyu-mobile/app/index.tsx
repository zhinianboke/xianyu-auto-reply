import { Redirect } from 'expo-router';
import { useConfigStore } from '@/stores/config';
import { useAuthStore } from '@/stores/auth';

export default function Index() {
  const serverUrl = useConfigStore((s) => s.serverUrl);
  const token = useAuthStore((s) => s.token);

  if (!serverUrl) {
    return <Redirect href="/(onboarding)/server-config" />;
  }
  if (!token) {
    return <Redirect href="/(onboarding)/login" />;
  }
  return <Redirect href="/(tabs)/messages" />;
}
