/**
 * 带超时的 Promise 竞速工具。
 *
 * 与裸 Promise.race 不同：超时后清理定时器，且超时错误信息可控。
 * 底层请求不会被 cancel（fetch 无通用 cancel），仅保证 UI 侧按时收到反馈。
 */
export class TimeoutError extends Error {
  constructor(message = '操作超时') {
    super(message);
    this.name = 'TimeoutError';
  }
}

export function withTimeout<T>(
  promise: Promise<T>,
  ms: number,
  message?: string,
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new TimeoutError(message));
    }, ms);
    promise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (err) => {
        clearTimeout(timer);
        reject(err);
      },
    );
  });
}

/** 是否为 withTimeout 抛出的超时错误（兼容旧字符串标记 'TIMEOUT_15S'） */
export function isTimeoutError(e: unknown): boolean {
  return e instanceof TimeoutError || (e as Error)?.message === 'TIMEOUT_15S';
}
