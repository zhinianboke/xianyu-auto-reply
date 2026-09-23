import { create } from 'zustand';
import { getAccountOptions, type AccountOption } from '@/api/wrappers/accounts';

/** 缓存有效期：距上次成功加载超过该时长后 load() 才会重新请求 */
const TTL_MS = 60_000;

interface AccountsState {
  options: AccountOption[];
  loading: boolean;
  loadedAt: number | null;
  /** TTL 内直接复用缓存；force=true（如下拉刷新）时绕过 TTL 强制请求 */
  load: (force?: boolean) => Promise<void>;
  /** 数据变更后手动失效（如账号增删后），下次 load() 将重新请求 */
  invalidate: () => void;
}

// 模块级在途请求：多页面同时挂载或短时间内重复 load 时合并为一次请求
let inflight: Promise<void> | null = null;

export const useAccountsStore = create<AccountsState>((set, get) => ({
  options: [],
  loading: false,
  loadedAt: null,

  load: async (force = false) => {
    if (inflight) return inflight;
    const { loadedAt } = get();
    if (!force && loadedAt !== null && Date.now() - loadedAt < TTL_MS) {
      return;
    }
    const task = (async () => {
      set({ loading: true });
      try {
        const options = await getAccountOptions();
        // 请求失败不更新 loadedAt，保留旧缓存可供后续页面降级使用
        set({ options, loadedAt: Date.now() });
      } finally {
        set({ loading: false });
        inflight = null;
      }
    })();
    inflight = task;
    return task;
  },

  invalidate: () => set({ loadedAt: null }),
}));
