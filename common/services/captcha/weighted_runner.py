"""
real_mouse 线程池前置加权任务执行器

功能：
1. 在公共浏览器线程池之前维护本地、远程两个等待队列
2. 每次派发前读取最新权重并执行平滑加权轮询
3. 只决定任务顺序，不修改滑块识别、轨迹、浏览器或重试逻辑
"""
from __future__ import annotations

import asyncio
import functools
import math
from collections import deque
from concurrent.futures import Executor, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Deque, Dict, Optional

from loguru import logger

from common.services.captcha.concurrency import get_browser_task_executor
from common.services.captcha.weighted_scheduler import (
    _BUCKET,
    _BUCKET_ORDER,
    _DEFAULT_WEIGHTS,
    _SUBORDER,
    real_mouse_scheduler,
)


@dataclass
class _QueuedTask:
    """前置加权队列中的一个同步任务。"""

    weight_class: str
    call: Callable[[], Any]
    future: asyncio.Future


class WeightedTaskRunner:
    """线程池前置的 real_mouse 平滑加权任务执行器。

    调度器维护本地、远程两个桶，只把已经选中的任务提交给公共浏览器线程池。因此线程池
    自身的 FIFO 队列不会遮挡滑块权重。任务开始后仍进入原 real_mouse 求解函数，本类不
    参与滑块处理过程。
    """

    def __init__(
        self,
        weight_loader: Callable[[], Dict[str, float]],
        executor_factory: Optional[Callable[[], Executor]] = None,
    ) -> None:
        self._weight_loader = weight_loader
        self._queues: Dict[str, Deque[_QueuedTask]] = {
            "local": deque(),
            "remote": deque(),
            "remote_cookie": deque(),
        }
        self._lock = asyncio.Lock()
        self._dispatcher_task: Optional[asyncio.Task] = None
        self._owned_executor: Optional[ThreadPoolExecutor] = None
        if executor_factory is None:
            self._owned_executor = ThreadPoolExecutor(
                max_workers=1,
                thread_name_prefix="weighted-real-mouse-test",
            )
            self._executor_factory = lambda: self._owned_executor
        else:
            self._executor_factory = executor_factory
        self._current = {"local": 0.0, "remote": 0.0}
        self._weight_signature: Optional[tuple[float, float]] = None
        self._was_contended = False

    async def submit(
        self,
        weight_class: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """按来源权重排队并执行一个同步任务。

        Args:
            weight_class: local、remote 或 remote_cookie。
            func: 原滑块编排函数。
            args: 传给原函数的位置参数。
            kwargs: 传给原函数的关键字参数。

        Returns:
            原函数返回值。
        """
        # 未知来源按远程处理，避免异常参数意外获得本地权重。
        wc = weight_class if weight_class in self._queues else "remote"
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        queued = _QueuedTask(
            weight_class=wc,
            call=functools.partial(func, *args, **kwargs),
            future=future,
        )

        async with self._lock:
            self._queues[wc].append(queued)
            self._ensure_dispatcher_locked()

        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            # 未执行的任务由调度循环跳过；已开始的真实鼠标任务不能安全中断，仍等待其自然结束。
            if not future.done():
                future.cancel()
            raise

    async def _dispatch_loop(self) -> None:
        """串行选择并执行排队任务，每次选择前强制刷新数据库权重。"""
        restart_pending = True
        try:
            while True:
                async with self._lock:
                    self._purge_cancelled_locked()
                    if not self._has_pending_locked():
                        self._reset_smooth_state()
                        return

                try:
                    loaded_weights = await asyncio.to_thread(self._weight_loader)
                    if not isinstance(loaded_weights, dict):
                        raise TypeError("权重读取结果不是字典")
                    weights = {
                        "local": self._sanitize_weight(loaded_weights.get("local", 1.0)),
                        "remote": self._sanitize_weight(loaded_weights.get("remote", 1.0)),
                    }
                except Exception as exc:  # noqa: BLE001
                    logger.error(f"刷新 real_mouse 实时权重失败，使用 1:1 调度: {exc}")
                    weights = dict(_DEFAULT_WEIGHTS)

                async with self._lock:
                    self._purge_cancelled_locked()
                    queued = self._pick_task_locked(weights)
                    pending_local = len(self._queues["local"])
                    pending_remote = len(self._queues["remote"]) + len(
                        self._queues["remote_cookie"]
                    )
                if queued is None:
                    continue

                logger.info(
                    "real_mouse 实时权重放行: "
                    f"来源={queued.weight_class}, "
                    f"权重={weights.get('local', 1)}:{weights.get('remote', 1)}, "
                    f"剩余排队=本地{pending_local}/远程{pending_remote}"
                )

                try:
                    result = await asyncio.get_running_loop().run_in_executor(
                        self._executor_factory(),
                        queued.call,
                    )
                except Exception as exc:  # noqa: BLE001
                    if not queued.future.done():
                        queued.future.set_exception(exc)
                else:
                    if not queued.future.done():
                        queued.future.set_result(result)
        except asyncio.CancelledError:
            restart_pending = False
            raise
        finally:
            async with self._lock:
                self._dispatcher_task = None
                self._purge_cancelled_locked()
                if not self._has_pending_locked():
                    self._reset_smooth_state()
                elif restart_pending:
                    self._ensure_dispatcher_locked()

    def _pick_task_locked(self, weights: Dict[str, float]) -> Optional[_QueuedTask]:
        """使用平滑加权轮询选择下一任务；必须持有异步锁。"""
        classes = [name for name, queue in self._queues.items() if queue]
        if not classes:
            return None

        buckets: Dict[str, list[str]] = {}
        for name in classes:
            buckets.setdefault(_BUCKET[name], []).append(name)

        if len(buckets) == 1:
            # 单方独占期间不累计权重，另一方重新加入时从新一轮开始计算。
            self._reset_smooth_state()
            best_bucket = next(iter(buckets))
        else:
            effective = {
                bucket: self._sanitize_weight(weights.get(bucket, 1.0))
                for bucket in buckets
            }
            max_weight = max(effective.values(), default=0.0)
            if max_weight <= 0:
                effective = {bucket: 1.0 for bucket in buckets}
            else:
                # 权重只表达比例；缩放到 0~1，避免超大有限数求和后溢出为 Infinity。
                effective = {
                    bucket: weight / max_weight
                    for bucket, weight in effective.items()
                }
            signature = (
                effective.get("local", 0.0),
                effective.get("remote", 0.0),
            )
            if not self._was_contended or signature != self._weight_signature:
                self._current = {"local": 0.0, "remote": 0.0}
            self._was_contended = True
            self._weight_signature = signature

            for bucket, weight in effective.items():
                self._current[bucket] = self._current.get(bucket, 0.0) + weight
            best_bucket = max(
                buckets,
                key=lambda bucket: (
                    self._current.get(bucket, 0.0),
                    -_BUCKET_ORDER.get(bucket, 99),
                ),
            )
            self._current[best_bucket] -= sum(effective.values())

        best_class = min(
            buckets[best_bucket],
            key=lambda name: (_SUBORDER.get(name, 0), name),
        )
        return self._queues[best_class].popleft()

    def _ensure_dispatcher_locked(self) -> None:
        """确保存在一个调度协程；必须持有异步锁。"""
        if self._dispatcher_task is None or self._dispatcher_task.done():
            self._dispatcher_task = asyncio.create_task(self._dispatch_loop())

    def _purge_cancelled_locked(self) -> None:
        """移除尚未执行就被调用方取消的任务；必须持有异步锁。"""
        for name, queue in self._queues.items():
            self._queues[name] = deque(item for item in queue if not item.future.cancelled())

    def _has_pending_locked(self) -> bool:
        """判断是否仍有等待任务；必须持有异步锁。"""
        return any(self._queues.values())

    def _reset_smooth_state(self) -> None:
        """结束竞争轮次，清除历史权重状态。"""
        self._current = {"local": 0.0, "remote": 0.0}
        self._weight_signature = None
        self._was_contended = False

    @staticmethod
    def _sanitize_weight(value: Any) -> float:
        """把运行期权重规整为有限非负数，非法值按默认权重 1 处理。"""
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return 1.0
        return parsed if math.isfinite(parsed) and parsed >= 0 else 1.0

    def shutdown(self) -> None:
        """关闭独立测试执行器；正式运行复用公共浏览器执行器。"""
        if self._owned_executor is not None:
            self._owned_executor.shutdown(wait=False, cancel_futures=True)


def _load_realtime_weights() -> Dict[str, float]:
    """每次派发前强制读取数据库中的最新权重。"""
    return real_mouse_scheduler.get_effective_weights(force_refresh=True)


# 被调用方 real_mouse 专用前置队列：只把选中的任务提交给原公共浏览器执行器。
real_mouse_weighted_runner = WeightedTaskRunner(
    _load_realtime_weights,
    executor_factory=get_browser_task_executor,
)
