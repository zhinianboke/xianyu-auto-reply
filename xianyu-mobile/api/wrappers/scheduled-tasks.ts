import { getApiClient } from './client';

/** 定时任务数据结构（对齐 web ScheduledTask） */
export interface ScheduledTask {
  id: number;
  task_code: string;
  task_name: string;
  interval_seconds: number;
  enabled: boolean;
  description: string | null;
  task_running: boolean;
  created_at: string | null;
  updated_at: string | null;
}

/** 后端统一响应可能为 { success, data } 或裸数据，抽出内部 data；未包裹则原样返回 */
function unwrap<T>(body: unknown): T {
  if (
    body &&
    typeof body === 'object' &&
    'success' in body &&
    'data' in body
  ) {
    const inner = (body as { data: unknown }).data;
    if (inner != null) return inner as T;
  }
  return body as T;
}

/** 获取定时任务列表（管理员） */
export async function getScheduledTasks(): Promise<{
  tasks: ScheduledTask[];
  schedulerRunning: boolean;
}> {
  const client = await getApiClient();
  const { data } = (await (client.GET as any)(
    '/api/v1/admin/scheduled-tasks',
  )) as { data?: unknown; error?: unknown };
  const body = data as Record<string, unknown> | unknown[] | undefined;

  // 调度器运行状态：仅当外层为对象时才有意义
  const schedulerRunning =
    body && typeof body === 'object' && !Array.isArray(body)
      ? Boolean((body as Record<string, unknown>).scheduler_running)
      : false;

  const inner = unwrap<unknown>(body);
  const tasks = Array.isArray(inner) ? (inner as ScheduledTask[]) : [];
  return { tasks, schedulerRunning };
}

/**
 * 更新定时任务配置（间隔时间 / 是否启用）
 * 后端用 query 参数传 interval_seconds / enabled
 */
export async function updateScheduledTask(
  taskCode: string,
  params: { interval_seconds?: number; enabled?: boolean },
): Promise<{ message: string; task: ScheduledTask | null }> {
  const client = await getApiClient();
  const query: Record<string, string> = {};
  if (params.interval_seconds !== undefined) {
    query.interval_seconds = String(params.interval_seconds);
  }
  if (params.enabled !== undefined) {
    query.enabled = String(params.enabled);
  }
  const { data } = (await (client.PUT as any)(
    '/api/v1/admin/scheduled-tasks/{task_code}',
    {
      params: {
        path: { task_code: taskCode },
        query,
      },
    },
  )) as { data?: unknown; error?: unknown };
  const body = (data ?? {}) as Record<string, unknown>;
  const message =
    typeof body.message === 'string' ? body.message : '更新成功';
  const task = body.data
    ? (body.data as ScheduledTask)
    : unwrap<ScheduledTask | null>(data) ?? null;
  return { message, task };
}

/** 手动触发定时任务执行一次（管理员） */
export async function triggerScheduledTask(
  taskCode: string,
): Promise<string> {
  const client = await getApiClient();
  const { data } = (await (client.POST as any)(
    '/api/v1/admin/scheduled-tasks/{task_code}/trigger',
    {
      params: { path: { task_code: taskCode } },
    },
  )) as { data?: unknown; error?: unknown };
  const body = (data ?? {}) as Record<string, unknown>;
  return typeof body.message === 'string' ? body.message : '已触发执行';
}
