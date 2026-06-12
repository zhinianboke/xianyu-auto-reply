"""
Cookie任务管理器

负责多账号任务调度、启停控制
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from .utils import safe_str


class CookieManager:
    """Cookie任务管理器
    
    负责：
    - 多账号任务调度
    - 账号启停控制
    - 任务状态监控
    - 账号关键词管理
    - 自动确认发货设置
    """
    
    _instance: Optional["CookieManager"] = None
    
    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None):
        """初始化Cookie管理器
        
        Args:
            loop: 事件循环（可选，不传则在需要时获取）
        """
        self.loop = loop
        
        # 账号Cookie存储 {cookie_id: cookie_value}
        self.cookies: Dict[str, str] = {}
        
        # 账号状态 {cookie_id: enabled}
        self.cookie_status: Dict[str, bool] = {}
        
        # 账号关键词 {cookie_id: [(keyword, reply), ...]}
        self.keywords: Dict[str, List[Tuple[str, str]]] = {}
        
        # 自动确认发货设置 {cookie_id: auto_confirm}
        self.auto_confirm_settings: Dict[str, bool] = {}

        # 账号所属用户ID {cookie_id: owner_id}
        self.user_ids: Dict[str, Optional[int]] = {}
        
        # 运行中的任务 {cookie_id: asyncio.Task}
        self.tasks: Dict[str, asyncio.Task] = {}
        
        # XianyuLive实例 {cookie_id: XianyuLive}
        self.instances: Dict[str, Any] = {}
        
        # 每个cookie_id的任务锁，防止重复创建
        self._task_locks: Dict[str, asyncio.Lock] = {}
        
        # 管理器锁
        self._lock = asyncio.Lock()
        
        logger.info("CookieManager初始化完成")
    
    @classmethod
    def get_instance(cls, loop: Optional[asyncio.AbstractEventLoop] = None) -> "CookieManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = CookieManager(loop)
        elif loop and cls._instance.loop is None:
            cls._instance.loop = loop
        return cls._instance
    
    def set_loop(self, loop: asyncio.AbstractEventLoop):
        """设置事件循环"""
        self.loop = loop
    
    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """获取事件循环"""
        if self.loop:
            return self.loop
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            # 在新线程中无法获取事件循环时，直接抛出异常
            # 调用方应确保 self.loop 已设置
            raise RuntimeError("事件循环未设置，请确保 CookieManager.loop 已初始化")

    async def _get_task_lock(self, cookie_id: str) -> asyncio.Lock:
        """获取指定cookie_id的任务锁"""
        if cookie_id not in self._task_locks:
            self._task_locks[cookie_id] = asyncio.Lock()
        return self._task_locks[cookie_id]

    async def load_from_db(self, db_session: AsyncSession):
        """从数据库加载所有Cookie、关键字和状态
        
        Args:
            db_session: 数据库会话
        """
        try:
            logger.info("从数据库加载Cookie配置...")
            
            from common.models import XYAccount, XYKeywordRule
            from sqlalchemy import select
            
            # 加载所有账号
            result = await db_session.execute(select(XYAccount))
            accounts = result.scalars().all()
            
            for account in accounts:
                cookie_id = account.account_id
                if cookie_id in self.cookies:
                    logger.warning(f"检测到重复账号ID: {cookie_id}，将使用最新加载的记录覆盖内存状态")
                self.cookies[cookie_id] = account.cookie or ""
                self.cookie_status[cookie_id] = account.status == "active"
                self.user_ids[cookie_id] = account.owner_id
                
                # 加载自动确认设置
                self.auto_confirm_settings[cookie_id] = account.auto_confirm if hasattr(account, 'auto_confirm') else True
                
                # 加载关键词
                kw_result = await db_session.execute(
                    select(XYKeywordRule).where(XYKeywordRule.account_pk == account.id)
                )
                keywords = kw_result.scalars().all()
                self.keywords[cookie_id] = [
                    (kw.keyword, kw.reply_content) for kw in keywords if kw.keyword and kw.reply_content
                ]
            
            logger.info(
                f"从数据库加载了 {len(self.cookies)} 个Cookie、"
                f"{sum(len(kws) for kws in self.keywords.values())} 个关键字、"
                f"{len(self.cookie_status)} 个状态记录"
            )
        except Exception as e:
            logger.error(f"从数据库加载数据失败: {safe_str(e)}")

    async def _run_xianyu(
        self,
        cookie_id: str,
        cookie_value: str,
        user_id: Optional[int] = None,
    ):
        """在事件循环中启动 XianyuAsync.main
        
        Args:
            cookie_id: 账号ID
            cookie_value: Cookie值
            user_id: 用户ID
        """
        logger.info(f"【{cookie_id}】_run_xianyu方法开始执行...")
        
        try:
            logger.info(f"【{cookie_id}】正在导入XianyuAsync...")
            from .xianyu_async import XianyuAsync
            
            logger.info(f"【{cookie_id}】正在创建XianyuAsync实例...")
            xianyu = XianyuAsync(
                cookies_str=cookie_value,
                cookie_id=cookie_id,
                user_id=user_id
            )
            
            # 保存实例引用
            self.instances[cookie_id] = xianyu
            
            logger.info(f"【{cookie_id}】正在启动XianyuAsync主程序...")
            await xianyu.main()
            
        except asyncio.CancelledError:
            logger.info(f"【{cookie_id}】XianyuAsync 任务已取消")
            raise
        except Exception as e:
            logger.error(f"【{cookie_id}】XianyuAsync 任务异常: {safe_str(e)}")
            raise
        finally:
            logger.info(f"【{cookie_id}】_run_xianyu方法执行结束")
            # 清理实例
            self.instances.pop(cookie_id, None)

    async def _add_cookie_async(
        self,
        cookie_id: str,
        cookie_value: str,
        user_id: Optional[int] = None,
    ):
        """异步添加Cookie并启动任务"""
        lock = await self._get_task_lock(cookie_id)
        
        async with lock:
            # 检查是否已存在任务
            if cookie_id in self.tasks:
                existing_task = self.tasks[cookie_id]
                if not existing_task.done():
                    logger.warning(f"【{cookie_id}】任务已存在且正在运行，先停止旧任务...")
                    existing_task.cancel()
                    try:
                        await existing_task
                    except asyncio.CancelledError:
                        pass
                    except Exception as e:
                        logger.error(f"等待旧任务停止时出错: {cookie_id}, {safe_str(e)}")
                    self.tasks.pop(cookie_id, None)
                    logger.info(f"【{cookie_id}】旧任务已停止")
                else:
                    self.tasks.pop(cookie_id, None)
                    logger.info(f"【{cookie_id}】旧任务已完成，已移除")
            
            # 更新内存
            self.cookies[cookie_id] = cookie_value
            if user_id is not None:
                self.user_ids[cookie_id] = user_id
            else:
                self.user_ids.setdefault(cookie_id, None)
            
            # 创建并启动任务
            loop = self._get_loop()
            task = loop.create_task(self._run_xianyu(cookie_id, cookie_value, user_id))
            self.tasks[cookie_id] = task
            
            logger.info(f"已启动账号任务: {cookie_id} (用户ID: {user_id})")

    async def _remove_cookie_async(self, cookie_id: str):
        """异步移除Cookie"""
        lock = await self._get_task_lock(cookie_id)
        
        async with lock:
            task = self.tasks.pop(cookie_id, None)
            if task:
                task.cancel()
                try:
                    await asyncio.wait_for(task, timeout=10.0)
                except asyncio.TimeoutError:
                    logger.warning(f"【{cookie_id}】等待任务停止超时（10秒），强制继续")
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"等待任务清理时出错: {cookie_id}, {safe_str(e)}")
            
            # 清理内存
            self.cookies.pop(cookie_id, None)
            self.keywords.pop(cookie_id, None)
            self.cookie_status.pop(cookie_id, None)
            self.auto_confirm_settings.pop(cookie_id, None)
            self.user_ids.pop(cookie_id, None)
            self.instances.pop(cookie_id, None)
            self._task_locks.pop(cookie_id, None)
            
            logger.info(f"已移除账号: {cookie_id}")

    async def _stop_task_async(self, cookie_id: str):
        """异步停止任务"""
        try:
            task = self.tasks.get(cookie_id)
            if task and not task.done():
                task.cancel()
                try:
                    await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
                except asyncio.TimeoutError:
                    logger.warning(f"等待任务取消超时: {cookie_id}")
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.debug(f"等待任务清理时出错: {cookie_id}, {safe_str(e)}")
                logger.info(f"已取消Cookie任务: {cookie_id}")
            
            self.tasks.pop(cookie_id, None)
            self.instances.pop(cookie_id, None)
            logger.info(f"成功停止Cookie任务: {cookie_id}")
        except Exception as e:
            logger.error(f"停止Cookie任务失败: {cookie_id}, {safe_str(e)}")

    def _run_in_loop(self, coro):
        """在事件循环中运行协程"""
        loop = self._get_loop()
        
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            # 当前线程没有事件循环，使用run_coroutine_threadsafe
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=30)
        
        if current_loop == loop:
            # 同一事件循环中，直接创建任务
            return loop.create_task(coro)
        else:
            # 不同事件循环，使用run_coroutine_threadsafe
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result(timeout=30)

    # ==================== 对外线程安全接口 ====================
    
    def add_cookie(
        self,
        cookie_id: str,
        cookie_value: str,
        kw_list: Optional[List[Tuple[str, str]]] = None,
        user_id: Optional[int] = None,
    ):
        """线程安全新增Cookie并启动任务"""
        if kw_list is not None:
            self.keywords[cookie_id] = kw_list
        else:
            self.keywords.setdefault(cookie_id, [])
        
        self.cookie_status[cookie_id] = True
        self.auto_confirm_settings.setdefault(cookie_id, True)
        
        return self._run_in_loop(self._add_cookie_async(cookie_id, cookie_value, user_id))

    def remove_cookie(self, cookie_id: str):
        """线程安全移除Cookie"""
        return self._run_in_loop(self._remove_cookie_async(cookie_id))

    def update_cookie(self, cookie_id: str, cookie_value: str, user_id: Optional[int] = None):
        """更新Cookie并重启任务
        
        Args:
            cookie_id: Cookie ID
            cookie_value: 新的Cookie值
            user_id: 用户ID（可选）
        """
        # 更新内存中的Cookie值
        self.cookies[cookie_id] = cookie_value
        
        # 先停止旧任务，再启动新任务
        async def _update_and_restart():
            await self._stop_task_async(cookie_id)
            await self._add_cookie_async(cookie_id, cookie_value, user_id)
        
        return self._run_in_loop(_update_and_restart())

    def update_cookie_status(self, cookie_id: str, enabled: bool):
        """更新Cookie的启用/禁用状态"""
        if cookie_id not in self.cookies:
            raise ValueError(f"Cookie ID {cookie_id} 不存在")
        
        old_status = self.cookie_status.get(cookie_id, True)
        self.cookie_status[cookie_id] = enabled
        logger.info(f"更新Cookie状态: {cookie_id} -> {'启用' if enabled else '禁用'}")

    def list_cookies(self) -> List[str]:
        """获取所有Cookie ID列表"""
        return list(self.cookies.keys())

    def get_cookie_status(self, cookie_id: str) -> bool:
        """获取Cookie的启用状态"""
        return self.cookie_status.get(cookie_id, True)

    def get_task_status(self, cookie_id: str) -> Dict[str, Any]:
        """获取任务状态"""
        if cookie_id not in self.tasks:
            return {"status": "not_started", "running": False, "is_connected": False}
        
        task = self.tasks[cookie_id]
        instance = self.instances.get(cookie_id)
        
        connection_state = "unknown"
        is_connected = False
        
        if instance:
            # 优先从 connection_manager 获取连接状态
            if hasattr(instance, 'connection_manager') and instance.connection_manager:
                connection_state = instance.connection_manager.connection_state.value
                is_connected = connection_state == "connected"
            # 兼容旧的 connection_state 属性
            elif hasattr(instance, 'connection_state'):
                connection_state = instance.connection_state.value
                is_connected = connection_state == "connected"
        
        return {
            "status": "running" if not task.done() else "stopped",
            "running": not task.done(),
            "connection_state": connection_state,
            "is_connected": is_connected,
        }

    def get_connection_stats(self) -> dict:
        """统计真实 WebSocket 连接状态

        遍历所有运行中的账号实例，按 connection_manager 的连接状态分类计数。
        其中 connected 表示真正建立了 WebSocket 连接的账号数量。

        Returns:
            包含总实例数、各状态计数、已连接账号ID列表的字典
        """
        by_state: dict = {}
        connected_ids = []
        total = 0
        for cookie_id, instance in list(self.instances.items()):
            total += 1
            conn_mgr = getattr(instance, 'connection_manager', None)
            if conn_mgr and getattr(conn_mgr, 'connection_state', None):
                state = conn_mgr.connection_state.value
            else:
                state = "unknown"
            by_state[state] = by_state.get(state, 0) + 1
            if state == "connected":
                connected_ids.append(cookie_id)

        return {
            "total_instances": total,           # 运行中的账号实例总数
            "connected": by_state.get("connected", 0),  # 真实 WebSocket 已连接数
            "by_state": by_state,               # 各连接状态明细
            "connected_account_ids": connected_ids,
        }

    async def start_all_tasks(self):
        """启动所有启用的账号任务"""
        for cookie_id, enabled in self.cookie_status.items():
            if enabled and cookie_id in self.cookies:
                cookie_value = self.cookies[cookie_id]
                user_id = self.user_ids.get(cookie_id)
                await self._add_cookie_async(cookie_id, cookie_value, user_id)
                await asyncio.sleep(0.05)

    async def stop_all_tasks(self):
        """停止所有任务"""
        for cookie_id in list(self.tasks.keys()):
            await self._stop_task_async(cookie_id)
    
    async def start(self):
        """启动CookieManager,从数据库加载并启动所有启用的账号"""
        try:
            logger.info("CookieManager启动中...")
            
            # 捕获当前事件循环，用于后续的跨线程调用
            if self.loop is None:
                self.loop = asyncio.get_running_loop()
                logger.info(f"CookieManager已捕获事件循环: {self.loop}")
            
            # 从数据库加载账号配置
            from common.db.session import async_session_maker
            async with async_session_maker() as db_session:
                await self.load_from_db(db_session)
            
            # 启动所有启用的账号任务
            await self.start_all_tasks()
            
            logger.info(f"CookieManager启动完成,已启动 {len(self.tasks)} 个账号任务")
        except Exception as e:
            logger.error(f"CookieManager启动失败: {safe_str(e)}")
            raise
    
    async def stop(self):
        """停止CookieManager,停止所有账号任务"""
        try:
            logger.info("CookieManager停止中...")
            
            # 停止所有任务
            await self.stop_all_tasks()
            
            logger.info("CookieManager已停止")
        except Exception as e:
            logger.error(f"CookieManager停止失败: {safe_str(e)}")
            raise


# 全局管理器实例
_manager: Optional[CookieManager] = None


def get_manager(loop: Optional[asyncio.AbstractEventLoop] = None) -> CookieManager:
    """获取全局Cookie管理器"""
    global _manager
    if _manager is None:
        _manager = CookieManager.get_instance(loop)
    elif loop and _manager.loop is None:
        _manager.set_loop(loop)
    return _manager
