"""
资源管理模块

功能:
1. 自动回复暂停管理
2. 浏览器资源关闭和清理
3. 后台任务管理

负责处理各种资源的关闭和清理
"""

import asyncio
import time
from loguru import logger

from common.utils.text_utils import safe_str


class AutoReplyPauseManager:
    """自动回复暂停管理器
    
    功能:
    - 管理每个chat_id的暂停状态
    - 支持账号特定的暂停时间
    - 自动清理过期的暂停记录
    """
    
    def __init__(self):
        # 存储每个账号下chat_id的暂停信息
        # key: (cookie_id, chat_id) 元组，value: pause_until_timestamp
        # 设计要点：暂停必须按账号隔离，避免账号A对某个chat手动回复后账号B在相同chat上也被误暂停
        self.paused_chats: dict[tuple[str, str], float] = {}

    def pause_chat(self, chat_id: str, cookie_id: str):
        """暂停指定chat_id的自动回复,使用账号特定的暂停时间
        
        Args:
            chat_id: 会话ID
            cookie_id: 账号标识
        """
        # 获取账号特定的暂停时间
        try:
            from common.db.compat import db_manager
            pause_minutes = db_manager.get_cookie_pause_duration(cookie_id)
            logger.debug(f"【{cookie_id}】从数据库获取暂停时间: {pause_minutes}分钟")
        except Exception as e:
            logger.error(f"获取账号 {cookie_id} 暂停时间失败: {e},使用默认10分钟")
            pause_minutes = 10

        # 如果暂停时间为0,表示不暂停
        if pause_minutes == 0:
            logger.info(f"【{cookie_id}】检测到手动发出消息,但暂停时间设置为0,不暂停自动回复")
            return

        pause_duration_seconds = pause_minutes * 60
        pause_until = time.time() + pause_duration_seconds
        # 按 (cookie_id, chat_id) 隔离存储，仅影响当前账号
        self.paused_chats[(cookie_id, chat_id)] = pause_until

        # 计算暂停结束时间
        end_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(pause_until))
        logger.info(f"【{cookie_id}】检测到手动发出消息,chat_id {chat_id} 自动回复暂停{pause_minutes}分钟,恢复时间: {end_time}")

    def is_chat_paused(self, chat_id: str, cookie_id: str) -> bool:
        """检查指定账号下的chat_id是否处于暂停状态
        
        Args:
            chat_id: 会话ID
            cookie_id: 账号标识（每个账号独立暂停）
            
        Returns:
            是否暂停
        """
        key = (cookie_id, chat_id)
        if key not in self.paused_chats:
            return False

        current_time = time.time()
        pause_until = self.paused_chats[key]

        if current_time >= pause_until:
            # 暂停时间已过,移除记录
            del self.paused_chats[key]
            return False

        return True

    def get_remaining_pause_time(self, chat_id: str, cookie_id: str) -> int:
        """获取指定账号下的chat_id剩余暂停时间(秒)
        
        Args:
            chat_id: 会话ID
            cookie_id: 账号标识
            
        Returns:
            剩余暂停时间(秒)
        """
        key = (cookie_id, chat_id)
        if key not in self.paused_chats:
            return 0

        current_time = time.time()
        pause_until = self.paused_chats[key]
        remaining = max(0, int(pause_until - current_time))

        return remaining

    def cleanup_expired_pauses(self):
        """清理已过期的暂停记录"""
        current_time = time.time()
        expired_keys = [key for key, pause_until in self.paused_chats.items()
                        if current_time >= pause_until]

        for key in expired_keys:
            del self.paused_chats[key]


# 全局暂停管理器实例
pause_manager = AutoReplyPauseManager()


class BrowserResourceManager:
    """浏览器资源管理器
    
    功能:
    - 处理浏览器和Playwright的关闭
    - 支持正常关闭和强制关闭
    - 超时控制和错误处理
    """
    
    def __init__(self, cookie_id: str):
        """
        初始化浏览器资源管理器
        
        Args:
            cookie_id: 账号标识
        """
        self.cookie_id = cookie_id
    
    def _safe_str(self, e):
        """安全地将异常转换为字符串（委托公共实现）"""
        return safe_str(e)
    
    async def normal_close_resources(self, browser, playwright):
        """正常关闭资源:浏览器+Playwright短超时关闭
        
        Args:
            browser: 浏览器实例
            playwright: Playwright实例
        """
        try:
            # 先关闭浏览器,再关闭Playwright
            if browser:
                try:
                    # 关闭浏览器,设置超时
                    await asyncio.wait_for(browser.close(), timeout=5.0)
                    logger.info(f"【{self.cookie_id}】浏览器关闭完成")
                except asyncio.TimeoutError:
                    logger.warning(f"【{self.cookie_id}】浏览器关闭超时,尝试强制关闭")
                    try:
                        # 尝试强制关闭
                        if hasattr(browser, '_connection'):
                            browser._connection.dispose()
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"【{self.cookie_id}】关闭浏览器时出错: {e}")
            
            # 关闭Playwright:使用短超时,如果超时就放弃
            if playwright:
                try:
                    logger.info(f"【{self.cookie_id}】正在关闭Playwright...")
                    # 增加超时时间,确保Playwright有足够时间清理资源
                    await asyncio.wait_for(playwright.stop(), timeout=5.0)
                    logger.info(f"【{self.cookie_id}】Playwright关闭完成")
                except asyncio.TimeoutError:
                    logger.warning(f"【{self.cookie_id}】Playwright关闭超时,将自动清理")
                    # 尝试强制清理Playwright的内部连接
                    try:
                        if hasattr(playwright, '_connection'):
                            playwright._connection.dispose()
                    except Exception:
                        pass
                except Exception as e:
                    logger.warning(f"【{self.cookie_id}】关闭Playwright时出错: {e}")
                
        except Exception as e:
            logger.error(f"【{self.cookie_id}】正常关闭时出现异常: {e}")
            raise

    async def force_close_resources(self, browser, playwright):
        """强制关闭资源:强制关闭浏览器+Playwright超时等待
        
        Args:
            browser: 浏览器实例
            playwright: Playwright实例
        """
        try:
            logger.warning(f"【{self.cookie_id}】开始强制关闭资源...")
            
            # 强制关闭浏览器+Playwright,设置短超时
            force_tasks = []
            if browser:
                force_tasks.append(asyncio.wait_for(browser.close(), timeout=3.0))
            if playwright:
                force_tasks.append(asyncio.wait_for(playwright.stop(), timeout=3.0))
            
            if force_tasks:
                # 使用gather执行,所有失败都会被忽略
                results = await asyncio.gather(*force_tasks, return_exceptions=True)
                
                # 检查是否有超时或异常,尝试强制清理
                for i, result in enumerate(results):
                    if isinstance(result, (asyncio.TimeoutError, Exception)):
                        resource_name = "浏览器" if i == 0 and browser else "Playwright"
                        logger.warning(f"【{self.cookie_id}】{resource_name}强制关闭失败,尝试直接清理连接")
                        try:
                            if i == 0 and browser and hasattr(browser, '_connection'):
                                browser._connection.dispose()
                            elif playwright and hasattr(playwright, '_connection'):
                                playwright._connection.dispose()
                        except Exception:
                            pass
                
                logger.info(f"【{self.cookie_id}】强制关闭完成")
            else:
                logger.info(f"【{self.cookie_id}】没有需要强制关闭的资源")
            
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】强制关闭时出现异常(已忽略): {e}")

    async def close_browser_resources(self, browser, playwright):
        """关闭浏览器资源的统一入口
        
        先尝试正常关闭,超时后强制关闭
        
        Args:
            browser: 浏览器实例
            playwright: Playwright实例
        """
        try:
            # 正常关闭,设置超时
            await asyncio.wait_for(
                self.normal_close_resources(browser, playwright),
                timeout=10.0
            )
        except asyncio.TimeoutError:
            logger.warning(f"【{self.cookie_id}】正常关闭超时,开始强制关闭...")
            await self.force_close_resources(browser, playwright)
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】异步关闭时出错,强制关闭: {self._safe_str(e)}")
            await self.force_close_resources(browser, playwright)


class TaskManager:
    """后台任务管理器
    
    功能:
    - 处理后台任务的取消和清理
    - 支持快速重置(用于重连)
    - 支持完整清理(用于退出)
    """
    
    def __init__(self, parent):
        """
        初始化任务管理器
        
        Args:
            parent: XianyuAsync实例,用于访问任务引用
        """
        self.parent = parent
    
    @property
    def cookie_id(self):
        return self.parent.cookie_id
    
    def reset_background_tasks(self):
        """直接重置后台任务引用,不等待取消(用于快速重连)
        
        注意:只重置心跳任务,因为只有心跳任务依赖WebSocket连接。
        其他任务(Token刷新、清理、Cookie刷新)不依赖WebSocket,可以继续运行。
        """
        logger.info(f"【{self.cookie_id}】准备重置后台任务引用(仅重置依赖WebSocket的任务)...")
        
        # 只处理心跳任务(依赖WebSocket,需要重启)
        if self.parent.heartbeat_task:
            status = "已完成" if self.parent.heartbeat_task.done() else "运行中"
            logger.info(f"【{self.cookie_id}】发现心跳任务(状态: {status}),需要重置(因为依赖WebSocket连接)")
            # 尝试取消心跳任务(但不等待)
            if not self.parent.heartbeat_task.done():
                try:
                    self.parent.heartbeat_task.cancel()
                    logger.debug(f"【{self.cookie_id}】已发送取消信号给心跳任务(不等待响应)")
                except Exception as e:
                    logger.warning(f"【{self.cookie_id}】取消心跳任务失败: {e}")
            # 重置心跳任务引用
            self.parent.heartbeat_task = None
            logger.info(f"【{self.cookie_id}】心跳任务引用已重置")
        else:
            logger.info(f"【{self.cookie_id}】没有心跳任务需要重置")
        
        # 检查其他任务的状态(这些任务不依赖WebSocket,不需要重启)
        other_tasks_status = []
        if self.parent.token_refresh_task:
            status = "已完成" if self.parent.token_refresh_task.done() else "运行中"
            other_tasks_status.append(f"Token刷新任务({status})")
        if self.parent.cleanup_task:
            status = "已完成" if self.parent.cleanup_task.done() else "运行中"
            other_tasks_status.append(f"清理任务({status})")
        if self.parent.cookie_refresh_task:
            status = "已完成" if self.parent.cookie_refresh_task.done() else "运行中"
            other_tasks_status.append(f"Cookie刷新任务({status})")
        
        if other_tasks_status:
            logger.info(f"【{self.cookie_id}】其他任务继续运行(不依赖WebSocket): {', '.join(other_tasks_status)}")
        else:
            logger.info(f"【{self.cookie_id}】没有其他任务在运行")
        
        logger.info(f"【{self.cookie_id}】任务重置完成,可以立即创建新的心跳任务")
    
    async def cancel_background_tasks(self):
        """取消并清理所有后台任务(用于程序退出时的完整清理)"""
        try:
            tasks_to_cancel = []
            
            # 收集所有需要取消的任务(只收集未完成的任务)
            if self.parent.heartbeat_task:
                if not self.parent.heartbeat_task.done():
                    tasks_to_cancel.append(("心跳任务", self.parent.heartbeat_task))
                else:
                    logger.debug(f"【{self.cookie_id}】心跳任务已完成,跳过")
                    
            if self.parent.token_refresh_task:
                if not self.parent.token_refresh_task.done():
                    tasks_to_cancel.append(("Token刷新任务", self.parent.token_refresh_task))
                else:
                    logger.debug(f"【{self.cookie_id}】Token刷新任务已完成,跳过")
                    
            if self.parent.cleanup_task:
                if not self.parent.cleanup_task.done():
                    tasks_to_cancel.append(("清理任务", self.parent.cleanup_task))
                else:
                    logger.debug(f"【{self.cookie_id}】清理任务已完成,跳过")
                    
            if self.parent.cookie_refresh_task:
                if not self.parent.cookie_refresh_task.done():
                    tasks_to_cancel.append(("Cookie刷新任务", self.parent.cookie_refresh_task))
                else:
                    logger.debug(f"【{self.cookie_id}】Cookie刷新任务已完成,跳过")
            
            if not tasks_to_cancel:
                logger.info(f"【{self.cookie_id}】没有后台任务需要取消(所有任务已完成或不存在)")
                # 立即重置任务引用
                self._reset_task_references()
                return
            
            logger.info(f"【{self.cookie_id}】开始取消 {len(tasks_to_cancel)} 个未完成的后台任务...")
            
            # 取消所有任务
            for task_name, task in tasks_to_cancel:
                try:
                    if task.done():
                        logger.info(f"【{self.cookie_id}】任务已完成,跳过取消: {task_name}")
                    else:
                        task.cancel()
                        logger.info(f"【{self.cookie_id}】已发送取消信号: {task_name}")
                except Exception as e:
                    logger.warning(f"【{self.cookie_id}】取消任务失败 {task_name}: {e}")
            
            # 等待所有任务完成取消
            tasks = [task for _, task in tasks_to_cancel]
            logger.info(f"【{self.cookie_id}】等待 {len(tasks)} 个任务响应取消信号...")
            
            wait_timeout = 5.0
            start_time = time.time()
            
            try:
                pending_tasks_list = [task for task in tasks if not task.done()]
                
                # 记录每个任务的状态
                for task_name, task in tasks_to_cancel:
                    status = "已完成" if task.done() else "运行中"
                    logger.info(f"【{self.cookie_id}】任务状态: {task_name} - {status}")
                
                if not pending_tasks_list:
                    logger.info(f"【{self.cookie_id}】所有任务已完成,无需等待")
                else:
                    await self._wait_for_tasks(tasks_to_cancel, pending_tasks_list, wait_timeout, start_time)
                        
            except Exception as e:
                elapsed = time.time() - start_time
                logger.error(f"【{self.cookie_id}】等待任务取消时出错 (耗时 {elapsed:.3f}秒): {e}")
                import traceback
                logger.error(f"【{self.cookie_id}】等待任务取消异常堆栈:\n{traceback.format_exc()}")
            
            logger.info(f"【{self.cookie_id}】任务取消流程完成,继续重连流程")
            
            # 最后检查一次所有任务的状态
            for task_name, task in tasks_to_cancel:
                if task and not task.done():
                    logger.warning(f"【{self.cookie_id}】⚠️ 任务取消流程完成后,任务仍未完成: {task_name} (done={task.done()})")
                elif task and task.done():
                    logger.debug(f"【{self.cookie_id}】✅ 任务已完成: {task_name}")
        
        finally:
            self._reset_task_references()
    
    def _reset_task_references(self):
        """重置所有任务引用"""
        self.parent.heartbeat_task = None
        self.parent.token_refresh_task = None
        self.parent.cleanup_task = None
        self.parent.cookie_refresh_task = None
        logger.info(f"【{self.cookie_id}】后台任务引用已全部重置")
    
    async def _wait_for_tasks(self, tasks_to_cancel, pending_tasks_list, wait_timeout, start_time):
        """等待任务完成取消
        
        Args:
            tasks_to_cancel: 需要取消的任务列表
            pending_tasks_list: 待处理的任务列表
            wait_timeout: 等待超时时间
            start_time: 开始时间
        """
        logger.info(f"【{self.cookie_id}】等待 {len(pending_tasks_list)} 个未完成任务响应(超时时间: {wait_timeout}秒)...")
        try:
            logger.debug(f"【{self.cookie_id}】开始调用 asyncio.wait()...")
            done, pending = await asyncio.wait(
                pending_tasks_list,
                timeout=wait_timeout,
                return_when=asyncio.ALL_COMPLETED
            )
            elapsed = time.time() - start_time
            logger.info(f"【{self.cookie_id}】asyncio.wait() 返回,耗时 {elapsed:.3f}秒,已完成: {len(done)},未完成: {len(pending)}")
            
            # 检查已完成的任务
            for task_name, task in tasks_to_cancel:
                if task in done:
                    try:
                        task.result()
                        logger.warning(f"【{self.cookie_id}】⚠️ 任务正常完成(非取消): {task_name}")
                    except asyncio.CancelledError:
                        logger.info(f"【{self.cookie_id}】✅ 任务已成功取消: {task_name}")
                    except Exception as e:
                        logger.warning(f"【{self.cookie_id}】⚠️ 任务取消时出现异常 {task_name}: {e}")
            
            if pending:
                await self._handle_pending_tasks(tasks_to_cancel, pending, elapsed)
            else:
                logger.info(f"【{self.cookie_id}】所有后台任务已取消 (耗时 {elapsed:.3f}秒)")
                
        except Exception as e:
            elapsed = time.time() - start_time
            logger.warning(f"【{self.cookie_id}】等待任务时出错 (耗时 {elapsed:.3f}秒): {e}")
            import traceback
            logger.warning(f"【{self.cookie_id}】等待任务异常堆栈:\n{traceback.format_exc()}")
    
    async def _handle_pending_tasks(self, tasks_to_cancel, pending, elapsed):
        """处理未完成的任务
        
        Args:
            tasks_to_cancel: 需要取消的任务列表
            pending: 未完成的任务集合
            elapsed: 已耗时
        """
        pending_names = []
        for task_name, task in tasks_to_cancel:
            if task in pending:
                pending_names.append(task_name)
                if task.done():
                    try:
                        task.result()
                        logger.warning(f"【{self.cookie_id}】任务在等待期间完成: {task_name}")
                    except asyncio.CancelledError:
                        logger.info(f"【{self.cookie_id}】任务在等待期间被取消: {task_name}")
                    except Exception as e:
                        logger.warning(f"【{self.cookie_id}】任务在等待期间异常 {task_name}: {e}")
                else:
                    logger.warning(f"【{self.cookie_id}】任务仍未完成: {task_name} (done={task.done()})")
        
        logger.warning(f"【{self.cookie_id}】等待超时 ({elapsed:.3f}秒),以下任务可能仍在运行: {', '.join(pending_names)}")
        
        # 强制取消所有未完成的任务
        for task_name, task in tasks_to_cancel:
            if task in pending and not task.done():
                try:
                    task.cancel()
                    logger.warning(f"【{self.cookie_id}】强制取消任务: {task_name}")
                except Exception as e:
                    logger.warning(f"【{self.cookie_id}】强制取消任务失败 {task_name}: {e}")
        
        # 再等待一小段时间
        if pending:
            try:
                done2, pending2 = await asyncio.wait(pending, timeout=1.0, return_when=asyncio.ALL_COMPLETED)
                for task_name, task in tasks_to_cancel:
                    if task in done2:
                        try:
                            task.result()
                        except asyncio.CancelledError:
                            logger.info(f"【{self.cookie_id}】任务在二次等待期间被取消: {task_name}")
                        except Exception as e:
                            logger.warning(f"【{self.cookie_id}】任务在二次等待期间异常 {task_name}: {e}")
            except Exception as e:
                logger.warning(f"【{self.cookie_id}】二次等待任务时出错: {e}")
        
        logger.warning(f"【{self.cookie_id}】强制继续重连流程,未完成的任务将在后台继续运行(但已标记为取消)")
