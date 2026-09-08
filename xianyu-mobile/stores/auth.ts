import { create } from 'zustand';
import { getToken, setToken, setRefreshToken, clearTokens } from '@/lib/config';

export interface AuthUser {
  user_id: number;
  username: string;
  is_admin: boolean;
  account_limit: number | null;
}

interface AuthState {
  token: string | null;
  user: AuthUser | null;
  loading: boolean;
  init: () => Promise<void>;
  setAuth: (token: string, refreshToken: string, user: AuthUser) => Promise<void>;
  verifyAndSetUser: (user: AuthUser) => void;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  token: null,
  user: null,
  loading: true,

  init: async () => {
    const token = await getToken();
    set({ token, loading: false });
  },

  setAuth: async (token, refreshToken, user) => {
    await setToken(token);
    await setRefreshToken(refreshToken);
    set({ token, user });
  },

  verifyAndSetUser: (user) => {
    set({ user });
  },

  logout: async () => {
    await clearTokens();
    set({ token: null, user: null });
  },
}));
