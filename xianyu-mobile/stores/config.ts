import { create } from 'zustand';
import {
  getServerUrl,
  getServerProfiles,
  getActiveProfileIndex,
  setActiveProfileIndex,
  addServerProfile,
  type ServerProfile,
} from '@/lib/config';

interface ConfigState {
  serverUrl: string | null;
  profiles: ServerProfile[];
  activeIndex: number;
  loading: boolean;
  init: () => Promise<void>;
  addProfile: (profile: ServerProfile) => Promise<void>;
  switchProfile: (index: number) => Promise<void>;
}

export const useConfigStore = create<ConfigState>((set, get) => ({
  serverUrl: null,
  profiles: [],
  activeIndex: -1,
  loading: true,

  init: async () => {
    const [url, profiles, index] = await Promise.all([
      getServerUrl(),
      getServerProfiles(),
      getActiveProfileIndex(),
    ]);
    set({ serverUrl: url, profiles, activeIndex: index, loading: false });
  },

  addProfile: async (profile) => {
    await addServerProfile(profile);
    await get().init();
  },

  switchProfile: async (index) => {
    await setActiveProfileIndex(index);
    await get().init();
  },
}));
