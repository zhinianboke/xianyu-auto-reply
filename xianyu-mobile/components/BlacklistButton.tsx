import React, { useCallback, useEffect, useState } from 'react';
import {
  Pressable,
  Text,
  ActivityIndicator,
  StyleSheet,
  Alert,
} from 'react-native';
import { useColorScheme } from 'react-native';
import { colors, spacing, typography, radius } from '@/lib/theme';
import { getBlacklistStatus, changeBlacklist } from '@/api/wrappers/blacklist';

interface BlacklistButtonProps {
  accountId: string;
  cid: string;
}

/**
 * 黑名单按钮组件：显示当前会话的黑名单状态，点击切换。
 * 挂载时查询状态，点击时乐观更新；失败回滚并提示。
 */
export function BlacklistButton({ accountId, cid }: BlacklistButtonProps) {
  const scheme = useColorScheme();
  const c = colors[scheme === 'dark' ? 'dark' : 'light'];

  const [blacklisted, setBlacklisted] = useState<boolean | null>(null);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState(false);

  const load = useCallback(async () => {
    if (!accountId || !cid) return;
    setLoading(true);
    try {
      const { is_blacklisted } = await getBlacklistStatus(accountId, cid);
      setBlacklisted(is_blacklisted);
    } catch (e) {
      console.error('查询黑名单状态失败', e);
      setBlacklisted(null);
    } finally {
      setLoading(false);
    }
  }, [accountId, cid]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleToggle() {
    if (blacklisted == null || toggling) return;
    const prev = blacklisted;
    const next = !prev;
    const action = next ? 'add' : 'remove';

    // 乐观更新
    setBlacklisted(next);
    setToggling(true);
    try {
      await changeBlacklist(accountId, cid, action);
    } catch (e) {
      // 回滚
      setBlacklisted(prev);
      Alert.alert('操作失败', (e as Error).message);
    } finally {
      setToggling(false);
    }
  }

  const isBlacklisted = blacklisted === true;
  const bg = isBlacklisted ? c.error : c.surface;
  const fg = isBlacklisted ? '#FFFFFF' : c.text;
  const label = isBlacklisted ? '解除黑名单' : '加入黑名单';
  const busy = loading || toggling;

  return (
    <Pressable
      onPress={handleToggle}
      disabled={busy}
      style={({ pressed }) => [
        styles.base,
        { backgroundColor: bg, borderColor: c.border, opacity: pressed ? 0.8 : 1 },
        busy && styles.disabled,
      ]}
    >
      {busy ? (
        <ActivityIndicator size="small" color={fg} />
      ) : (
        <Text style={[styles.text, { color: fg }]}>{label}</Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    minHeight: 38,
    borderRadius: radius.md,
    paddingHorizontal: spacing.md,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    flexDirection: 'row',
  },
  text: {
    ...typography.caption,
    fontWeight: '600',
  },
  disabled: {
    opacity: 0.5,
  },
});
