"""
滑块验证全局并发控制

使用线程安全的方式控制滑块验证的并发数量
所有滑块验证（token刷新、密码登录等）共享同一个并发限制
"""
from __future__ import annotations

import asyncio
import functools
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Optional, Set

from loguru import logger


# ==================== 禁用账号管理 ====================

class DisabledAccountManager:
    """
    禁用账号管理器（线程安全单例）
    
    管理因人脸验证超时等原因被禁用的账号列表
    """
    _instance: Optional["DisabledAccountManager"] = None
    _instance_lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._lock = threading.Lock()
        self._disabled_accounts: Set[str] = set()  # 禁用账号集合
        self._initialized = True
        logger.info("禁用账号管理器初始化完成")
    
    def add(self, account_id: str):
        """添加禁用账号"""
        with self._lock:
            self._disabled_accounts.add(str(account_id))
            logger.info(f"账号 {account_id} 已添加到禁用列表")
    
    def remove(self, account_id: str):
        """移除禁用账号（账号重新启用时调用）"""
        with self._lock:
            self._disabled_accounts.discard(str(account_id))
            logger.info(f"账号 {account_id} 已从禁用列表移除")
    
    def contains(self, account_id: str) -> bool:
        """检查账号是否在禁用列表中"""
        with self._lock:
            return str(account_id) in self._disabled_accounts
    
    def get_all(self) -> Set[str]:
        """获取所有禁用账号"""
        with self._lock:
            return self._disabled_accounts.copy()
    
    def clear(self):
        """清空禁用列表"""
        with self._lock:
            self._disabled_accounts.clear()
            logger.info("禁用账号列表已清空")


# 全局禁用账号管理器实例
disabled_account_manager = DisabledAccountManager()


# ==================== 账号级浏览器互斥锁 ====================

class AccountBrowserLockManager:
    """账号级浏览器互斥锁管理器（线程安全单例）

    同一账号的 Playwright 持久化 user_data_dir 同一时间只能被一个 Chrome 进程持有，
    否则 Chrome 启动时检测到 SingletonLock 会立即以 exit code 21 退出（PROFILE_IN_USE）。

    本管理器为每个 account_id 维护一把进程内可重入的互斥锁，保证：
    - 同账号的多个 XianyuSliderStealth 实例排队执行（不会真正并发占用同一 user_data_dir）
    - 不同账号的实例之间互不干扰
    - 持有账号锁的代码可以安全地清理 user_data_dir 内的 Singleton 锁文件
      （不会误删正在运行的 Chrome 锁）
    """

    _instance: Optional["AccountBrowserLockManager"] = None
    _instance_lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        # 保护 _account_locks 字典自身的并发访问
        self._guard_lock = threading.Lock()
        # 每个 account_id 一把可重入锁（同一线程多次 acquire 不会死锁）
        self._account_locks: Dict[str, threading.RLock] = {}
        self._initialized = True
        logger.info("账号级浏览器互斥锁管理器初始化完成")

    def _get_lock(self, account_id: str) -> threading.RLock:
        """获取（或惰性创建）指定账号的互斥锁"""
        key = str(account_id)
        with self._guard_lock:
            lock = self._account_locks.get(key)
            if lock is None:
                lock = threading.RLock()
                self._account_locks[key] = lock
            return lock

    def acquire(self, account_id: str, timeout: Optional[float] = None) -> bool:
        """获取账号锁（阻塞等待）

        Args:
            account_id: 账号ID
            timeout: 超时时间（秒），None 表示无限等待；负数等价于不等待

        Returns:
            True 成功获取；False 超时未获取
        """
        lock = self._get_lock(account_id)
        try:
            if timeout is None:
                # threading.RLock.acquire(timeout=-1) 表示阻塞直到拿到
                acquired = lock.acquire(blocking=True)
            else:
                acquired = lock.acquire(timeout=max(0.0, float(timeout)))
            return bool(acquired)
        except Exception as exc:
            logger.warning(f"获取账号锁失败 ({account_id}): {exc}")
            return False

    def release(self, account_id: str):
        """释放账号锁

        仅在当前线程已持有锁时才会真正释放，否则忽略错误。
        """
        key = str(account_id)
        with self._guard_lock:
            lock = self._account_locks.get(key)
        if lock is None:
            return
        try:
            lock.release()
        except RuntimeError:
            # 当前线程未持有此锁，忽略
            pass


# 全局单例
account_browser_lock_manager = AccountBrowserLockManager()


def is_account_disabled_in_db(account_id: str) -> bool:
    """
    检查账号在数据库中是否为禁用状态
    
    Args:
        account_id: 账号ID
        
    Returns:
        True: 账号已禁用
        False: 账号未禁用或查询失败
    """
    try:
        from sqlalchemy import create_engine, text
        
        # 尝试从不同服务获取配置
        db_url = None
        try:
            from common.core.config import get_settings
            settings = get_settings()
            db_url = settings.database_url
        except ImportError:
            pass
        
        if not db_url:
            try:
                from app.core.config import get_settings
                settings = get_settings()
                db_url = settings.database_url
            except ImportError:
                pass
        
        if not db_url:
            logger.warning(f"无法获取数据库配置")
            return False
        
        engine = create_engine(db_url, echo=False)
        
        try:
            with engine.connect() as conn:
                sql = text("SELECT status FROM xy_accounts WHERE account_id = :account_id")
                result = conn.execute(sql, {"account_id": account_id})
                row = result.fetchone()
                
                if row and row[0] == 'disabled':
                    return True
                return False
        finally:
            engine.dispose()
            
    except Exception as e:
        logger.warning(f"检查账号禁用状态失败: {account_id}, 错误: {e}")
        return False


def should_skip_account(account_id: str) -> bool:
    """
    检查是否应该跳过该账号的处理
    
    条件：账号在禁用列表中 且 数据库中状态为禁用
    
    Args:
        account_id: 账号ID
        
    Returns:
        True: 应该跳过
        False: 可以处理
    """
    # 先检查内存列表（快速判断）
    if not disabled_account_manager.contains(account_id):
        return False
    
    # 再检查数据库状态（确认是否真的禁用）
    if is_account_disabled_in_db(account_id):
        logger.info(f"账号 {account_id} 已禁用，跳过处理")
        return True
    
    # 数据库中未禁用，从列表中移除（可能已被手动启用）
    disabled_account_manager.remove(account_id)
    return False


class BrowserSlotManager:
    """
    浏览器槽位管理器（线程安全单例）
    
    使用 Condition 实现等待/通知机制，确保多线程安全
    """
    _instance: Optional["BrowserSlotManager"] = None
    _instance_lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 配置
        self._max_slots = 1  # 默认最大并发数
        self._wait_timeout = 120  # 默认等待超时（秒）
        self._config_loaded = False
        
        # 线程安全控制
        self._lock = threading.Lock()  # 保护内部状态
        self._condition = threading.Condition(self._lock)  # 等待/通知机制
        
        # 状态
        self._active_count = 0  # 当前活跃的浏览器数量
        self._active_users: Dict[str, float] = {}  # 活跃用户及其开始时间
        
        self._initialized = True
        logger.info("浏览器槽位管理器初始化完成")
    
    def _load_config(self):
        """延迟加载配置"""
        if self._config_loaded:
            return
        
        try:
            # 尝试从不同服务获取配置
            settings = None
            try:
                from common.core.config import get_settings
                settings = get_settings()
            except ImportError:
                pass
            
            if not settings:
                try:
                    from app.core.config import get_settings
                    settings = get_settings()
                except ImportError:
                    pass
            
            if settings:
                # 使用getattr安全获取配置，避免属性不存在的错误
                self._max_slots = getattr(settings, 'max_captcha_concurrent', 1)
                self._wait_timeout = getattr(settings, 'captcha_wait_timeout', 120)
                logger.info(f"浏览器槽位配置: 最大并发={self._max_slots}, 超时={self._wait_timeout}秒")
            else:
                logger.warning("无法获取配置，使用默认值")
                self._max_slots = 1
                self._wait_timeout = 120
        except Exception as e:
            logger.warning(f"加载配置失败，使用默认值: {e}")
            self._max_slots = 1
            self._wait_timeout = 120
        
        self._config_loaded = True
    
    def acquire(self, user_id: str, timeout: Optional[float] = None) -> bool:
        """
        获取浏览器槽位（阻塞等待）
        
        Args:
            user_id: 用户ID
            timeout: 超时时间（秒），None使用默认值
            
        Returns:
            True: 成功获取
            False: 超时失败
        """
        self._load_config()
        
        if timeout is None:
            timeout = self._wait_timeout
        
        pure_id = self._extract_pure_user_id(user_id)
        start_time = time.time()
        logged = False
        
        with self._condition:
            while self._active_count >= self._max_slots:
                # 计算剩余等待时间
                elapsed = time.time() - start_time
                remaining = timeout - elapsed
                
                if remaining <= 0:
                    logger.warning(
                        f"【{pure_id}】获取槽位超时({timeout}秒)，"
                        f"当前: {self._active_count}/{self._max_slots}"
                    )
                    return False
                
                # 首次等待时记录日志
                if not logged:
                    logger.info(
                        f"【{pure_id}】等待浏览器槽位，"
                        f"当前: {self._active_count}/{self._max_slots}，"
                        f"排队中..."
                    )
                    logged = True
                
                # 等待通知或超时
                self._condition.wait(timeout=min(remaining, 2.0))
            
            # 获取槽位
            self._active_count += 1
            self._active_users[user_id] = time.time()
            
            logger.info(
                f"【{pure_id}】获取槽位成功，"
                f"当前: {self._active_count}/{self._max_slots}"
            )
            return True
    
    def release(self, user_id: str):
        """
        释放浏览器槽位
        
        Args:
            user_id: 用户ID
        """
        pure_id = self._extract_pure_user_id(user_id)
        
        with self._condition:
            # 减少计数
            if self._active_count > 0:
                self._active_count -= 1
            
            # 移除用户记录
            self._active_users.pop(user_id, None)
            
            logger.info(
                f"【{pure_id}】释放槽位，"
                f"当前: {self._active_count}/{self._max_slots}"
            )
            
            # 通知等待的线程
            self._condition.notify_all()
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        self._load_config()
        with self._lock:
            return {
                'active_count': self._active_count,
                'max_concurrent': self._max_slots,
                'available_slots': self._max_slots - self._active_count,
                'active_users': list(self._active_users.keys()),
            }
    
    @property
    def max_concurrent(self) -> int:
        """最大并发数"""
        self._load_config()
        return self._max_slots
    
    @property
    def wait_timeout(self) -> int:
        """等待超时时间"""
        self._load_config()
        return self._wait_timeout
    
    def _extract_pure_user_id(self, user_id: str) -> str:
        """提取纯用户ID"""
        user_id = str(user_id)
        if '_' in user_id:
            parts = user_id.split('_')
            if len(parts) >= 2 and parts[-1].isdigit() and len(parts[-1]) >= 10:
                return '_'.join(parts[:-1])
        return user_id


# 全局单例
_slot_manager = BrowserSlotManager()


# ==================== 对外接口 ====================

def acquire_browser_slot(user_id: str, timeout: Optional[float] = None) -> bool:
    """获取浏览器槽位"""
    return _slot_manager.acquire(user_id, timeout)


def release_browser_slot(user_id: str):
    """释放浏览器槽位"""
    _slot_manager.release(user_id)


def get_browser_stats() -> Dict[str, Any]:
    """获取统计信息"""
    return _slot_manager.get_stats()


# ==================== 兼容旧接口 ====================

class SliderConcurrencyManager:
    """兼容旧接口的包装类"""
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    @property
    def max_concurrent(self) -> int:
        return _slot_manager.max_concurrent
    
    @property
    def wait_timeout(self) -> int:
        return _slot_manager.wait_timeout
    
    def can_start_instance(self, user_id: str) -> bool:
        stats = _slot_manager.get_stats()
        return stats['active_count'] < stats['max_concurrent']
    
    def wait_for_slot(self, user_id: str, timeout: Optional[int] = None) -> bool:
        return _slot_manager.acquire(user_id, timeout)
    
    def register_instance(self, user_id: str, instance: Any = None):
        # 槽位已在 wait_for_slot 中获取，这里只是兼容接口
        pass
    
    def unregister_instance(self, user_id: str):
        _slot_manager.release(user_id)
    
    def _extract_pure_user_id(self, user_id: str) -> str:
        return _slot_manager._extract_pure_user_id(user_id)
    
    def get_stats(self) -> Dict[str, Any]:
        return _slot_manager.get_stats()


# 全局实例
concurrency_manager = SliderConcurrencyManager()


# ==================== 浏览器任务专用线程池 ====================
#
# 所有"会长时间阻塞"的浏览器/Playwright 任务（滑块验证、密码登录、Cookie 续期等）
# 都必须通过本线程池调度，而不是 asyncio 默认线程池。
#
# 原因：这些任务内部会等待并发槽位/账号锁（可能 park 长达 120 秒）并驱动浏览器，
# 若占用 asyncio 默认线程池，会与 aiohttp 的 DNS 解析（ThreadedResolver 默认用同一线程池）
# 争抢线程。一旦默认线程池被这些长任务占满，aiohttp 的 getaddrinfo 排不到线程，
# 所有 token 刷新等网络请求会集体在超时时间后失败（即使网络本身完全正常）。

_browser_task_executor: Optional[ThreadPoolExecutor] = None
_browser_task_executor_lock = threading.Lock()


def get_browser_task_executor() -> ThreadPoolExecutor:
    """返回浏览器任务专用线程池（与 asyncio 默认线程池隔离的单例）。

    线程池大小 = 浏览器并发槽位上限 + 少量余量。余量用于容纳"已进入任务但正在等待
    槽位/账号锁"的线程，避免它们排队时阻塞新任务进入；整体仍有上限，绝不会无限增长。
    """
    global _browser_task_executor
    if _browser_task_executor is None:
        with _browser_task_executor_lock:
            if _browser_task_executor is None:
                try:
                    slots = int(_slot_manager.max_concurrent or 1)
                except Exception:
                    slots = 1
                max_workers = max(2, slots + 2)
                _browser_task_executor = ThreadPoolExecutor(
                    max_workers=max_workers,
                    thread_name_prefix="browser-task",
                )
                logger.info(f"浏览器任务专用线程池初始化完成，max_workers={max_workers}")
    return _browser_task_executor


async def run_browser_task(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """在浏览器任务专用线程池中运行同步阻塞函数（替代 asyncio.to_thread）。

    用于所有长阻塞的浏览器/验证码任务，避免占用 asyncio 默认线程池导致
    aiohttp DNS 解析被饿死、网络请求集体超时。
    """
    loop = asyncio.get_running_loop()
    call = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(get_browser_task_executor(), call)

