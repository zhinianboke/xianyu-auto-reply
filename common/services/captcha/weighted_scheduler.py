"""
real_mouse 加权公平调度器

用途：
    real_mouse（真实鼠标）过滑块引擎的物理光标全局唯一，同一时刻只能解一个滑块。
    本文件提供线程内兜底锁及数据库权重读取；线程池前置双队列实现在
    weighted_runner.py，本地与远程请求会先按实时权重选出唯一任务再执行。

设计：
    - 前置排队：权重选择发生在公共浏览器线程池之前，避免线程池 FIFO 掩盖权重。
    - 平滑加权：仅在本地、远程同时积压时累计当轮权重，不产生历史服务欠账。
    - 实时权重：前置队列每次选择下一个任务前重新读取数据库中的权重。
    - 滑块隔离：本模块只决定任务执行顺序，不修改任何滑块识别、轨迹或重试逻辑。
"""
from __future__ import annotations

import math
import threading
import time
from typing import Dict, Optional

from loguru import logger
from sqlalchemy import create_engine, text

# 权重配置在 system_settings 中的键（与 backend-web captcha 路由保持一致）
WEIGHT_KEY_LOCAL = "captcha.real_mouse_weight_local"
WEIGHT_KEY_REMOTE = "captcha.real_mouse_weight_remote"

# 默认权重（首次读取或某个配置缺失时使用，1:1 等价于公平轮转）
_DEFAULT_WEIGHTS: Dict[str, float] = {"local": 1.0, "remote": 1.0}

# 线程内兜底锁的缓存有效期；前置双队列每次派发都会通过 force_refresh 绕过此缓存。
_WEIGHTS_TTL = 5.0

# served 虚拟时间超过该阈值时重归一化，防止长时间满负载下浮点无限增长
_RENORM_THRESHOLD = 1e6

# 来源类别 → 权重桶：加权公平只在「本地 vs 远程」两个桶之间按权重分配，
# 远程的两个子类（无cookie / 有cookie）共用同一个 remote 桶（共享权重与 served 计数），
# 从而保证无论远程内部怎么分，本地:远程 的总比例始终等于配置的权重比。
_BUCKET = {"local": "local", "remote": "remote", "remote_cookie": "remote"}

# 桶的 tie-break 顺序：桶虚拟时间相等时本地优先
_BUCKET_ORDER = {"local": 0, "remote": 1}

# 远程桶内部的子优先级（严格优先）：无cookie("remote") 恒先于有cookie("remote_cookie")
_SUBORDER = {"remote": 0, "remote_cookie": 1}


class WeightedSerialScheduler:
    """单槽位加权公平调度器（线程安全）。

    典型用法：
        if scheduler.acquire("remote"):
            try:
                ... 独占执行 ...
            finally:
                scheduler.release()
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        # 当前是否有持有者（单槽位）
        self._busy = False
        # 每个来源类别当前的等待者数量：{class: count}（class 含远程子类，用于桶内子优先级判定）
        self._waiting: Dict[str, int] = {}
        # 每个「权重桶」累计放行次数（WFQ 虚拟服务量）：{bucket: served}（远程两子类共享 remote 桶）
        self._served: Dict[str, float] = {}

        # 权重缓存
        self._weights_cache: Optional[Dict[str, float]] = None
        self._weights_loaded_at: float = 0.0
        self._weights_lock = threading.Lock()

        # 数据库 engine 惰性创建（读 system_settings 权重用）
        self._engine = None
        self._engine_lock = threading.Lock()

    # ---------- 对外接口 ----------

    def acquire(self, weight_class: str = "local", timeout: Optional[float] = None) -> bool:
        """获取执行权（阻塞排队）。

        Args:
            weight_class: 来源类别（"local"=本地 / "remote"=远程无cookie / "remote_cookie"=远程有cookie）。
                本地与远程按权重公平分配；远程内部无cookie 严格优先于有cookie。
            timeout: 超时秒；None 表示无限等待（与旧 with lock 语义一致）

        Returns:
            True 成功获取；False 超时未获取
        """
        wc = weight_class or "local"

        # 进锁前预热权重缓存，避免持 condition 锁时才去查库（那会阻塞 release）
        self.get_effective_weights()

        with self._condition:
            self._waiting[wc] = self._waiting.get(wc, 0) + 1
            acquired = False
            start = time.time()
            try:
                while True:
                    # 槽位空闲且轮到本来源 → 放行
                    if not self._busy and self._pick_class() == wc:
                        acquired = True
                        break
                    if timeout is not None:
                        remaining = timeout - (time.time() - start)
                        if remaining <= 0:
                            break
                        self._condition.wait(timeout=min(remaining, 1.0))
                    else:
                        # 无限等待也定期醒来重判（防止极端情况下丢通知）
                        self._condition.wait(timeout=1.0)
            finally:
                # 无论成功/超时，都从等待队列中移除自己
                self._waiting[wc] = self._waiting.get(wc, 1) - 1
                if self._waiting.get(wc, 0) <= 0:
                    self._waiting.pop(wc, None)

            if acquired:
                # 持锁期间连续完成「置 busy + 记账」，惊群下也不会重复放行
                self._busy = True
                # 记账落到权重桶上（远程两子类共享 remote 桶），保证 本地:远程 总比例不受 cookie 拆分影响
                bucket = _BUCKET.get(wc, wc)
                self._served[bucket] = self._served.get(bucket, 0.0) + 1.0
                self._maybe_renormalize()
            return acquired

    def release(self) -> None:
        """释放执行权，唤醒排队者。"""
        with self._condition:
            self._busy = False
            # 无人等待时重置计数：既防长期空闲后的陈旧偏置，也顺带防溢出
            if not self._waiting:
                self._served.clear()
            self._condition.notify_all()

    def get_stats(self) -> Dict[str, object]:
        """调试/观测用：当前占用、等待与累计放行情况。"""
        with self._condition:
            return {
                "busy": self._busy,
                "waiting": dict(self._waiting),
                "served": dict(self._served),
                "weights": self.get_effective_weights(),
            }

    # ---------- 内部：调度 ----------

    def _pick_class(self) -> Optional[str]:
        """选出下一个放行的来源类别。

        两级决策：
        1. 桶级加权公平：在有等待者的桶（local / remote）里，选虚拟时间
           served[bucket]/weight[bucket] 最小者，保证 本地:远程 的总放行比例=权重比。
        2. 桶内子优先级：远程桶里，无cookie("remote") 严格优先于有cookie("remote_cookie")。

        - 唯一候选桶恒胜（即使权重为 0，也能在对方空闲时被放行，保证 work-conserving）。
        - 桶虚拟时间相等时按 _BUCKET_ORDER 确定性 tie-break（本地优先）。
        必须在持有 self._condition 时调用。
        """
        candidates = [c for c, n in self._waiting.items() if n > 0]
        if not candidates:
            return None
        weights = self.get_effective_weights()

        # 按桶归组
        buckets: Dict[str, list] = {}
        for c in candidates:
            buckets.setdefault(_BUCKET.get(c, c), []).append(c)

        # 1. 选桶：虚拟时间最小
        def bucket_key(bucket: str):
            vtime = self._served.get(bucket, 0.0) / max(weights.get(bucket, 1.0), 1e-9)
            return (vtime, _BUCKET_ORDER.get(bucket, 99), bucket)

        best_bucket = min(buckets, key=bucket_key)

        # 2. 桶内子优先级：无cookie 先于有cookie（本地桶只有一个类，min 自然返回它）
        return min(buckets[best_bucket], key=lambda c: (_SUBORDER.get(c, 0), c))

    def _maybe_renormalize(self) -> None:
        """持续满负载下对 served 做虚拟时间重归一化，防浮点无限增长。

        关键：对每个来源减去 vmin*weight[c]（而非统一减常数），才能保持
        各来源 served/weight 的相对差不变——否则会破坏加权比例（易踩的坑）。
        必须在持有 self._condition 时调用。
        """
        if not self._served:
            return
        weights = self.get_effective_weights()
        vmin = min(
            self._served.get(c, 0.0) / max(weights.get(c, 1.0), 1e-9)
            for c in self._served
        )
        if vmin > _RENORM_THRESHOLD:
            for c in list(self._served):
                self._served[c] -= vmin * max(weights.get(c, 1.0), 1e-9)

    # ---------- 内部：权重读取 ----------

    def get_effective_weights(self, force_refresh: bool = False) -> Dict[str, float]:
        """读取当前有效权重。

        Args:
            force_refresh: 是否忽略 5 秒缓存并立即查询数据库。

        Returns:
            本地、远程两个权重；读取失败时保留上一次成功值，首次失败才使用 1:1。
        """
        now = time.monotonic()
        with self._weights_lock:
            if (
                not force_refresh
                and self._weights_cache is not None
                and (now - self._weights_loaded_at) < _WEIGHTS_TTL
            ):
                return dict(self._weights_cache)

            weights = self._load_weights_from_db()
            if weights is not None:
                self._weights_cache = weights
            elif self._weights_cache is None:
                self._weights_cache = dict(_DEFAULT_WEIGHTS)
            # 以查询完成时间作为缓存起点，避免慢查询导致刚加载完就立即过期并重复查询。
            self._weights_loaded_at = time.monotonic()
            return dict(self._weights_cache)

    def _load_weights_from_db(self) -> Optional[Dict[str, float]]:
        """从 xy_system_settings 读取两个权重键，失败时返回 None。"""
        weights = dict(_DEFAULT_WEIGHTS)
        try:
            engine = self._get_engine()
            if engine is None:
                return None

            with engine.connect() as conn:
                # key 是 MySQL 保留字，必须加反引号
                rows = conn.execute(
                    text(
                        "SELECT `key`, value FROM xy_system_settings "
                        "WHERE `key` IN (:k_local, :k_remote)"
                    ),
                    {"k_local": WEIGHT_KEY_LOCAL, "k_remote": WEIGHT_KEY_REMOTE},
                ).fetchall()
            raw_map = {row[0]: row[1] for row in rows}
            for key, cls in ((WEIGHT_KEY_LOCAL, "local"), (WEIGHT_KEY_REMOTE, "remote")):
                raw = raw_map.get(key)
                if raw is None or str(raw).strip() == "":
                    continue
                try:
                    val = float(raw)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(val) and val >= 0:
                    weights[cls] = val
        except Exception as e:  # noqa: BLE001
            logger.warning(f"读取 real_mouse 权重失败，继续使用上次有效权重: {e}")
            return None
        return weights

    def _get_engine(self):
        """惰性创建并复用数据库 engine（读权重用）。"""
        if self._engine is not None:
            return self._engine
        with self._engine_lock:
            if self._engine is not None:
                return self._engine
            db_url, connect_timeout = self._resolve_db_config()
            if not db_url:
                logger.warning("real_mouse 权重调度器无法获取数据库配置")
                return None

            engine_kwargs = {
                "echo": False,
                "pool_pre_ping": True,
            }
            if db_url.startswith("mysql+pymysql"):
                engine_kwargs["connect_args"] = {
                    "connect_timeout": connect_timeout,
                    "read_timeout": connect_timeout,
                    "write_timeout": connect_timeout,
                }
            self._engine = create_engine(db_url, **engine_kwargs)
            return self._engine

    @staticmethod
    def _resolve_db_config() -> tuple[Optional[str], int]:
        """获取数据库 URL 与连接超时（兼容 common/core 和各服务配置）。"""
        for module_path in ("common.core.config", "app.core.config"):
            try:
                module = __import__(module_path, fromlist=["get_settings"])
                settings = module.get_settings()
                db_url = getattr(settings, "database_url", None)
                if db_url:
                    timeout = max(int(getattr(settings, "db_connect_timeout", 10)), 1)
                    return db_url, timeout
            except Exception:
                continue
        return None, 10


# 全局单例：real_mouse 引擎专用（本地/远程两来源共用这一把加权锁）
real_mouse_scheduler = WeightedSerialScheduler()
