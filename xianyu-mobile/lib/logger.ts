/**
 * APP 日志系统
 *
 * 功能：
 * 1. 分级日志：debug/info/warn/error
 * 2. 内存环形缓冲（最近 500 条）
 * 3. AsyncStorage 持久化（最近 200 条 error/warn）
 * 4. 全局事件通知（日志页实时更新）
 * 5. 导出为文本（可复制）
 */

import AsyncStorage from '@react-native-async-storage/async-storage';
import { Platform } from 'react-native';

export type LogLevel = 'debug' | 'info' | 'warn' | 'error';

export interface LogEntry {
  id: number;
  timestamp: number;
  level: LogLevel;
  tag: string;
  message: string;
  data?: string;
}

const MAX_MEMORY = 500;
const MAX_STORAGE = 200;
const STORAGE_KEY = 'app_logs';
let logIdCounter = 0;

// 内存缓冲
const memoryLogs: LogEntry[] = [];

// 持久化防抖缓冲：积累日志后批量写入，避免频繁 IO
let persistBuffer: LogEntry[] = [];
let persistTimer: ReturnType<typeof setTimeout> | null = null;
const PERSIST_DEBOUNCE_MS = 2000;

// 监听器（日志页订阅）
type LogListener = (logs: LogEntry[]) => void;
const listeners = new Set<LogListener>();

// 推送合并节流：高频日志（如 HTTP debug）时避免每条都全量快照广播，窗口结束推一次最新快照
const NOTIFY_THROTTLE_MS = 300;
let notifyTimer: ReturnType<typeof setTimeout> | null = null;

function pushSnapshot() {
  const snapshot = [...memoryLogs].reverse();
  listeners.forEach((fn) => fn(snapshot));
}

function notify() {
  if (notifyTimer) return;
  notifyTimer = setTimeout(() => {
    notifyTimer = null;
    pushSnapshot();
  }, NOTIFY_THROTTLE_MS);
}

export function subscribeLogs(listener: LogListener): () => void {
  listeners.add(listener);
  // 立即推送当前日志
  pushSnapshot();
  return () => listeners.delete(listener);
}

function addLog(level: LogLevel, tag: string, message: string, data?: unknown) {
  const entry: LogEntry = {
    id: ++logIdCounter,
    timestamp: Date.now(),
    level,
    tag,
    message,
    data: data != null ? (typeof data === 'string' ? data : JSON.stringify(data, null, 2)) : undefined,
  };

  // 写入内存缓冲
  memoryLogs.push(entry);
  if (memoryLogs.length > MAX_MEMORY) {
    memoryLogs.splice(0, memoryLogs.length - MAX_MEMORY);
  }

  // 控制台输出
  const prefix = `[${tag}]`;
  if (level === 'error') {
    console.error(prefix, message, data ?? '');
  } else if (level === 'warn') {
    console.warn(prefix, message, data ?? '');
  } else {
    console.log(prefix, message, data ?? '');
  }

  // warn/error 持久化到 AsyncStorage（防抖批量写入）
  if (level === 'warn' || level === 'error') {
    schedulePersist(entry);
  }

  notify();
}

/** 防抖写入：积累 warn/error 日志，2 秒后批量持久化 */
function schedulePersist(entry: LogEntry) {
  persistBuffer.push(entry);
  if (persistTimer) return;
  persistTimer = setTimeout(() => {
    persistTimer = null;
    const batch = persistBuffer;
    persistBuffer = [];
    persistBatch(batch);
  }, PERSIST_DEBOUNCE_MS);
}

async function persistBatch(entries: LogEntry[]) {
  if (entries.length === 0) return;
  try {
    const raw = await AsyncStorage.getItem(STORAGE_KEY);
    const logs: LogEntry[] = raw ? JSON.parse(raw) : [];
    logs.push(...entries);
    if (logs.length > MAX_STORAGE) {
      logs.splice(0, logs.length - MAX_STORAGE);
    }
    await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(logs));
  } catch {
    // 持久化失败不影响运行
  }
}

// 日志 API
export const logger = {
  debug: (tag: string, message: string, data?: unknown) => addLog('debug', tag, message, data),
  info: (tag: string, message: string, data?: unknown) => addLog('info', tag, message, data),
  warn: (tag: string, message: string, data?: unknown) => addLog('warn', tag, message, data),
  error: (tag: string, message: string, data?: unknown) => addLog('error', tag, message, data),
};

/** 获取内存中的日志（最新在前） */
export function getLogs(): LogEntry[] {
  return [...memoryLogs].reverse();
}

/** 清除所有日志 */
export async function clearLogs() {
  memoryLogs.length = 0;
  await AsyncStorage.removeItem(STORAGE_KEY);
  notify();
}

/** 导出日志为纯文本（可复制） */
export function exportLogsAsString(): string {
  const lines = memoryLogs.map((e) => {
    const time = new Date(e.timestamp).toISOString();
    const dataStr = e.data ? `\n  ${e.data}` : '';
    return `[${time}] ${e.level.toUpperCase()} [${e.tag}] ${e.message}${dataStr}`;
  });
  return lines.join('\n\n');
}

/** 获取日志统计 */
export function getLogStats(): { total: number; errors: number; warns: number } {
  return {
    total: memoryLogs.length,
    errors: memoryLogs.filter((e) => e.level === 'error').length,
    warns: memoryLogs.filter((e) => e.level === 'warn').length,
  };
}
