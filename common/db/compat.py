"""
数据库兼容层

将旧框架的同步db_manager接口适配到新框架的异步数据库
使用独立线程和事件循环来避免异步上下文冲突
"""
from __future__ import annotations

import asyncio
import time
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple
from loguru import logger

from sqlalchemy import select, update, delete, and_, text, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from common.db.session import async_session_maker
from common.core.config import get_settings
from common.models.xy_account import XYAccount
from common.models.risk_control_log import XYRiskControlLog
from common.models.account_login_log import XYAccountLoginLog
from common.models.xy_catalog_item import XYCatalogItem
from common.models.xy_order import XYOrder
from common.models.xy_keyword_rule import XYKeywordRule
from common.models.card import Card
from common.models.default_reply import DefaultReply
from common.models.confirm_receipt_message import ConfirmReceiptMessage
from common.models.user_setting import UserSetting
from common.models.system_setting import SystemSetting
from common.utils.time_utils import get_beijing_now, get_beijing_now_naive


# 线程本地存储，用于缓存每个线程的数据库引擎和会话工厂
_thread_local = threading.local()

# 缓存未命中哨兵对象
_SENTINEL = object()


def _get_thread_local_session_maker():
    """获取当前线程的数据库会话工厂（懒加载）"""
    if not hasattr(_thread_local, 'session_maker'):
        settings = get_settings()
        engine = create_async_engine(
            settings.async_database_url,
            echo=False,
            pool_pre_ping=settings.db_pool_pre_ping,  # 取连接前 ping，剔除失效连接（asyncmy ping 已在 session 层做兼容修补）
            pool_size=1,   # 兼容层线程为一次性，单协程只需 1 条连接（原 3，避免连接累积）
            max_overflow=2,  # 仅留少量溢出余量（原 5），降低单引擎最大连接数 8 -> 3
            pool_timeout=settings.db_pool_timeout,  # 获取连接超时时间
            pool_recycle=settings.db_pool_recycle,  # 连接回收时间，防止MySQL断开陈旧连接
            connect_args={"connect_timeout": settings.db_connect_timeout},  # TCP 建连超时，远程库不可达时快速失败
        )
        _thread_local.engine = engine
        _thread_local.session_maker = async_sessionmaker(engine, expire_on_commit=False)
    return _thread_local.session_maker


class DBManagerCompat:
    """数据库管理器兼容层
    
    提供与旧框架db_manager相同的同步接口，内部使用异步数据库操作
    """
    
    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        # 实例级TTL缓存（5分钟）
        self._cache: Dict[str, tuple] = {}  # key -> (value, timestamp)
        self._cache_ttl: float = 300.0  # 5分钟
    
    def _get_cached(self, key: str):
        """从缓存获取值，过期返回None"""
        if key in self._cache:
            value, ts = self._cache[key]
            if time.time() - ts < self._cache_ttl:
                return value
            del self._cache[key]
        return _SENTINEL
    
    def _set_cached(self, key: str, value) -> None:
        """写入缓存"""
        self._cache[key] = (value, time.time())
    
    def _invalidate_cache(self, key: str) -> None:
        """使缓存失效"""
        self._cache.pop(key, None)
    
    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """获取事件循环"""
        try:
            return asyncio.get_running_loop()
        except RuntimeError:
            if self._loop is None or self._loop.is_closed():
                self._loop = asyncio.new_event_loop()
            return self._loop
    
    async def _run_async_coro(self, coro):
        """直接运行异步协程（在异步上下文中使用）"""
        return await coro
    
    def _run_async(self, async_func: Callable):
        """在同步代码中运行异步操作
        
        使用独立线程和新事件循环来避免死锁
        async_func: 一个接受session_maker参数的异步函数
        """
        max_attempts = 3

        for attempt in range(1, max_attempts + 1):
            result = [None]
            exception = [None]

            def run_in_thread():
                try:
                    # 创建新的事件循环
                    new_loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(new_loop)
                    try:
                        # 获取线程本地的会话工厂
                        session_maker = _get_thread_local_session_maker()
                        # 执行异步函数
                        result[0] = new_loop.run_until_complete(async_func(session_maker))
                    finally:
                        # 主动释放本线程引擎的连接池：本兼容层使用一次性线程，
                        # threading.local 缓存对新线程必然 miss（每次新建引擎），
                        # 若不主动 dispose，连接需等 GC 才回收，高并发下易累积、打满 MySQL。
                        try:
                            engine = getattr(_thread_local, 'engine', None)
                            if engine is not None:
                                new_loop.run_until_complete(engine.dispose())
                                # 清掉缓存，避免后续误用已释放的引擎
                                _thread_local.engine = None
                                if hasattr(_thread_local, 'session_maker'):
                                    del _thread_local.session_maker
                        except Exception:
                            pass
                        # 清理事件循环
                        try:
                            new_loop.run_until_complete(new_loop.shutdown_asyncgens())
                        except Exception:
                            pass
                        new_loop.close()
                except Exception as e:
                    exception[0] = e

            thread = threading.Thread(target=run_in_thread, daemon=True)
            thread.start()
            thread.join(timeout=30)

            if thread.is_alive():
                logger.error("异步操作超时")
                return None

            if exception[0]:
                if attempt < max_attempts:
                    logger.warning(f"执行异步操作失败，第{attempt}次重试前等待 {attempt} 秒: {exception[0]}")
                    time.sleep(attempt)
                    continue
                logger.error(f"执行异步操作失败: {exception[0]}")
                return None

            return result[0]

        return None
    
    # ==================== 账号相关 ====================
    
    async def get_account_pk_by_cookie_id(self, cookie_id: str) -> Optional[int]:
        """异步获取账号主键ID"""
        async with async_session_maker() as session:
            stmt = select(XYAccount.id).where(XYAccount.account_id == cookie_id)
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    
    def get_cookie_details(self, cookie_id: str) -> Optional[Dict[str, Any]]:
        """获取账号详情（带5分钟TTL缓存）"""
        cache_key = f"cookie_details:{cookie_id}"
        cached = self._get_cached(cache_key)
        if cached is not _SENTINEL:
            return cached
        
        async def _query(session_maker):
            async with session_maker() as session:
                stmt = select(XYAccount).where(XYAccount.account_id == cookie_id)
                result = await session.execute(stmt)
                account = result.scalars().first()
                if not account:
                    return None
                
                # 尝试获取账号昵称，若为空则从 cookie 中解析 tracknick，若仍为空则回退使用备注
                display_name = account.display_name
                if not display_name:
                    try:
                        from common.utils.xianyu_utils import trans_cookies
                        from urllib.parse import unquote
                        cookie_dict = trans_cookies(account.cookie)
                        tracknick = cookie_dict.get("tracknick")
                        if tracknick:
                            display_name = unquote(tracknick)
                    except Exception:
                        pass

                return {
                    'id': account.id,
                    'cookie_id': account.account_id,
                    'cookie_value': account.cookie,
                    'user_id': account.owner_id,
                    'auto_confirm': account.auto_confirm,
                    'remark': account.remark,
                    'display_name': display_name or account.remark,
                    'pause_duration': account.pause_duration,
                    'username': account.username,
                    'password': account.login_password,
                    'show_browser': account.show_browser,
                    'proxy_type': account.proxy_type,
                    'proxy_host': account.proxy_host,
                    'proxy_port': account.proxy_port,
                    'proxy_user': account.proxy_user,
                    'proxy_pass': account.proxy_pass,
                }
        result = self._run_async(_query)
        self._set_cached(cache_key, result)
        return result
    
    def get_cookie_proxy_config(self, cookie_id: str) -> Dict[str, Any]:
        """获取代理配置"""
        async def _query(session_maker):
            async with session_maker() as session:
                stmt = select(
                    XYAccount.proxy_type,
                    XYAccount.proxy_host,
                    XYAccount.proxy_port,
                    XYAccount.proxy_user,
                    XYAccount.proxy_pass
                ).where(XYAccount.account_id == cookie_id)
                result = await session.execute(stmt)
                row = result.first()
                if not row:
                    return {'proxy_type': 'none', 'proxy_host': '', 'proxy_port': 0, 'proxy_user': '', 'proxy_pass': ''}
                return {
                    'proxy_type': row.proxy_type or 'none',
                    'proxy_host': row.proxy_host or '',
                    'proxy_port': row.proxy_port or 0,
                    'proxy_user': row.proxy_user or '',
                    'proxy_pass': row.proxy_pass or ''
                }
        result = self._run_async(_query)
        if result is None:
            logger.warning(f"【{cookie_id}】获取代理配置失败，使用无代理默认配置")
            return {'proxy_type': 'none', 'proxy_host': '', 'proxy_port': 0, 'proxy_user': '', 'proxy_pass': ''}
        return result
    
    def get_cookie_message_expire_time(self, cookie_id: str) -> int:
        """获取相同消息等待时间配置"""
        async def _query(session_maker):
            async with session_maker() as session:
                stmt = select(XYAccount.message_expire_time).where(XYAccount.account_id == cookie_id)
                result = await session.execute(stmt)
                expire_time = result.scalar_one_or_none()
                logger.debug(f"【{cookie_id}】从数据库获取message_expire_time: {expire_time}")
                return expire_time if expire_time is not None else 3600
        result = self._run_async(_query)
        # _run_async失败时返回None，需要返回默认值
        if result is None:
            logger.warning(f"【{cookie_id}】获取message_expire_time失败，使用默认值3600")
            return 3600
        return result
    
    def get_cookie_pause_duration(self, cookie_id: str) -> int:
        """获取暂停时间"""
        async def _query(session_maker):
            async with session_maker() as session:
                stmt = select(XYAccount.pause_duration).where(XYAccount.account_id == cookie_id)
                result = await session.execute(stmt)
                duration = result.scalar_one_or_none()
                return duration if duration is not None else 10
        return self._run_async(_query)
    
    def get_auto_confirm(self, cookie_id: str) -> bool:
        """获取自动确认设置"""
        async def _query(session_maker):
            async with session_maker() as session:
                stmt = select(XYAccount.auto_confirm).where(XYAccount.account_id == cookie_id)
                result = await session.execute(stmt)
                auto_confirm = result.scalar_one_or_none()
                return bool(auto_confirm) if auto_confirm is not None else False
        return self._run_async(_query)
    
    def get_confirm_before_send(self, cookie_id: str) -> bool:
        """获取发货成功再发卡券开关设置"""
        async def _query(session_maker):
            async with session_maker() as session:
                stmt = select(XYAccount.confirm_before_send).where(XYAccount.account_id == cookie_id)
                result = await session.execute(stmt)
                confirm_before_send = result.scalar_one_or_none()
                return bool(confirm_before_send) if confirm_before_send is not None else False
        return self._run_async(_query)

    def get_send_before_confirm(self, cookie_id: str) -> bool:
        """获取卡券发送成功再确认发货开关设置"""
        async def _query(session_maker):
            async with session_maker() as session:
                stmt = select(XYAccount.send_before_confirm).where(XYAccount.account_id == cookie_id)
                result = await session.execute(stmt)
                send_before_confirm = result.scalar_one_or_none()
                return bool(send_before_confirm) if send_before_confirm is not None else False
        return self._run_async(_query)

    def get_cookie_status(self, cookie_id: str) -> bool:
        """获取账号是否启用"""
        async def _query(session_maker):
            async with session_maker() as session:
                stmt = select(XYAccount.status).where(XYAccount.account_id == cookie_id)
                result = await session.execute(stmt)
                status = result.scalars().first()
                return status == 'active'
        result = self._run_async(_query)
        if result is None:
            logger.warning(f"【{cookie_id}】获取账号状态失败，默认保持启用状态")
            return True
        return result

    
    def get_user_setting_by_cookie_id(self, cookie_id: str, key: str) -> Optional[str]:
        """通过cookie_id获取对应用户的个人设置值
        
        Args:
            cookie_id: 账号标识
            key: 设置键名
            
        Returns:
            设置值，不存在返回None
        """
        async def _query(session_maker):
            async with session_maker() as session:
                # 先获取 owner_id
                account_stmt = select(XYAccount.owner_id).where(XYAccount.account_id == cookie_id)
                account_result = await session.execute(account_stmt)
                owner_id = account_result.scalar_one_or_none()
                if not owner_id:
                    return None
                # 查询用户设置
                setting_stmt = select(UserSetting.value).where(
                    UserSetting.user_id == owner_id,
                    UserSetting.key == key
                )
                setting_result = await session.execute(setting_stmt)
                return setting_result.scalar_one_or_none()
        return self._run_async(_query)

    def update_cookie_account_info(self, cookie_id: str, **kwargs) -> bool:
        """更新账号信息"""
        async def _update(session_maker):
            async with session_maker() as session:
                values = {}
                # 支持 cookie_value 和 value 两种参数名
                if 'cookie_value' in kwargs:
                    values['cookie'] = kwargs['cookie_value']
                elif 'value' in kwargs:
                    values['cookie'] = kwargs['value']
                
                if not values:
                    logger.warning(f"update_cookie_account_info: 没有要更新的字段，kwargs={kwargs}")
                    return False
                    
                stmt = update(XYAccount).where(XYAccount.account_id == cookie_id).values(**values)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
        success = self._run_async(_update)
        if success:
            self._invalidate_cache(f"cookie_details:{cookie_id}")
        return success
    
    def disable_account(self, cookie_id: str, reason: str = "") -> bool:
        """禁用账号
        
        Args:
            cookie_id: 账号ID
            reason: 禁用原因
            
        Returns:
            是否成功
        """
        async def _update(session_maker):
            async with session_maker() as session:
                # 更新账号状态为禁用，同时保存禁用原因
                values = {'status': 'disabled'}
                if reason:
                    values['disable_reason'] = reason
                stmt = update(XYAccount).where(
                    XYAccount.account_id == cookie_id
                ).values(**values)
                result = await session.execute(stmt)
                await session.commit()
                
                if result.rowcount > 0:
                    logger.warning(f"【{cookie_id}】账号已被禁用，原因: {reason}")
                    return True
                return False
        return self._run_async(_update)
    
    def get_system_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """获取系统设置值（带5分钟TTL缓存）
        
        Args:
            key: 设置键名
            default: 默认值
            
        Returns:
            设置值，不存在时返回默认值
        """
        cache_key = f"system_setting:{key}"
        cached = self._get_cached(cache_key)
        if cached is not _SENTINEL:
            return cached
        
        async def _query(session_maker):
            async with session_maker() as session:
                stmt = select(SystemSetting.value).where(SystemSetting.key == key)
                result = await session.execute(stmt)
                value = result.scalar_one_or_none()
                return value if value is not None else default
        result = self._run_async(_query)
        self._set_cached(cache_key, result)
        return result
    
    # ==================== 商品相关 ====================
    
    def get_item_info(self, cookie_id: str, item_id: str) -> Optional[Dict[str, Any]]:
        """获取商品信息"""
        async def _query(session_maker):
            async with session_maker() as session:
                # 获取账号主键
                account_stmt = select(XYAccount.id).where(XYAccount.account_id == cookie_id)
                account_result = await session.execute(account_stmt)
                account_pk = account_result.scalar_one_or_none()
                if not account_pk:
                    return None
                
                stmt = select(XYCatalogItem).where(
                    XYCatalogItem.account_pk == account_pk,
                    XYCatalogItem.item_id == item_id
                )
                result = await session.execute(stmt)
                item = result.scalars().first()
                if not item:
                    return None
                
                # 从metadata_json中获取额外信息
                metadata = item.metadata_json or {}
                return {
                    'id': item.id,
                    'item_id': item.item_id,
                    'item_title': item.title,
                    'title': item.title,
                    'item_price': str(item.price) if item.price else '0',
                    'price': str(item.price) if item.price else '0',
                    'item_detail': metadata.get('detail', ''),
                    'detail': metadata.get('detail', ''),
                    'desc': metadata.get('description', ''),
                    'ai_prompt': item.ai_prompt or '',
                    'multi_quantity_delivery': metadata.get('multi_quantity_delivery', False),
                    'multi_spec': metadata.get('is_multi_spec', False),
                }
        return self._run_async(_query)
    
    def get_item_multi_quantity_delivery_status(self, cookie_id: str, item_id: str) -> bool:
        """获取多数量发货状态"""
        info = self.get_item_info(cookie_id, item_id)
        return info.get('multi_quantity_delivery', False) if info else False
    
    # ==================== 风控日志 ====================
    
    def add_risk_control_log(self, cookie_id: str, event_type: str, event_description: str, 
                            processing_status: str = 'processing', **kwargs) -> Optional[int]:
        """添加风控日志"""
        async def _insert(session_maker):
            async with session_maker() as session:
                # 获取账号信息
                account_stmt = select(XYAccount.id, XYAccount.owner_id).where(XYAccount.account_id == cookie_id)
                account_result = await session.execute(account_stmt)
                account_row = account_result.first()
                
                log = XYRiskControlLog(
                    owner_id=account_row.owner_id if account_row else None,
                    account_pk=account_row.id if account_row else None,
                    account_identifier=cookie_id,
                    event_type=event_type,
                    event_description=event_description,
                    processing_status=processing_status
                )
                session.add(log)
                await session.commit()
                await session.refresh(log)
                return log.id
        try:
            return self._run_async(_insert)
        except Exception as e:
            logger.error(f"添加风控日志失败: {e}")
            return None
    
    def update_risk_control_log(self, log_id: int, **kwargs) -> bool:
        """更新风控日志"""
        async def _update(session_maker):
            async with session_maker() as session:
                values = {}
                if 'processing_result' in kwargs:
                    values['processing_result'] = kwargs['processing_result']
                if 'processing_status' in kwargs:
                    values['processing_status'] = kwargs['processing_status']
                if 'captcha_engine' in kwargs:
                    values['captcha_engine'] = kwargs['captcha_engine']
                if 'error_message' in kwargs:
                    values['error_message'] = kwargs['error_message']
                if not values:
                    return True
                stmt = update(XYRiskControlLog).where(XYRiskControlLog.id == log_id).values(**values)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
        try:
            return self._run_async(_update)
        except Exception as e:
            logger.error(f"更新风控日志失败: {e}")
            return False

    # ==================== 账号登录日志 ====================

    def add_account_login_log(
        self,
        cookie_id: str,
        login_status: str,
        *,
        username: Optional[str] = None,
        trigger_reason: Optional[str] = None,
        failure_reason: Optional[str] = None,
        error_message: Optional[str] = None,
        updated_cookie_names: Optional[str] = None,
        duration_ms: Optional[int] = None,
    ) -> Optional[int]:
        """添加账号登录日志（每次密码登录尝试写一条）

        Args:
            cookie_id: 账号业务ID（XYAccount.account_id）
            login_status: 登录状态 success/failed/skipped_cooldown/no_credentials
            username: 闲鱼登录用户名（快照），便于排查
            trigger_reason: 触发本次登录的原因（如「Session过期」/「令牌过期」）
            failure_reason: 失败大类标签（聚合统计用）
            error_message: 详细错误消息（完整异常信息或风控提示）
            updated_cookie_names: 接口续期更新的Cookie字段名（逗号分隔）
            duration_ms: 整个登录流程耗时（毫秒）

        Returns:
            新增日志主键ID，失败返回 None
        """
        async def _insert(session_maker):
            async with session_maker() as session:
                # 获取账号信息（无外键约束，靠代码控制 owner_id 与 account_pk）
                account_stmt = select(XYAccount.id, XYAccount.owner_id).where(XYAccount.account_id == cookie_id)
                account_result = await session.execute(account_stmt)
                account_row = account_result.first()

                # 判断当天是否已存在相同状态和失败原因的记录，存在则只更新不重复插入
                today_start = get_beijing_now().replace(hour=0, minute=0, second=0, microsecond=0)
                today_end = get_beijing_now().replace(hour=23, minute=59, second=59, microsecond=999999)

                # 构建去重查询条件
                dedup_filters = [
                    XYAccountLoginLog.account_identifier == cookie_id,
                    XYAccountLoginLog.login_status == login_status,
                    XYAccountLoginLog.created_at >= today_start,
                    XYAccountLoginLog.created_at <= today_end,
                ]
                if failure_reason is not None:
                    dedup_filters.append(XYAccountLoginLog.failure_reason == failure_reason)
                else:
                    dedup_filters.append(XYAccountLoginLog.failure_reason.is_(None))

                existing_stmt = select(XYAccountLoginLog).where(*dedup_filters)
                existing_result = await session.execute(existing_stmt)
                existing_log = existing_result.scalars().first()

                if existing_log:
                    # 当天已存在相同状态和失败原因的记录，只更新相关字段
                    existing_log.username = username
                    existing_log.trigger_reason = trigger_reason
                    existing_log.error_message = error_message
                    existing_log.updated_cookie_names = updated_cookie_names
                    existing_log.duration_ms = duration_ms
                    existing_log.created_at = get_beijing_now()
                    await session.commit()
                    return existing_log.id

                # 当天不存在相同记录，新增一条
                log = XYAccountLoginLog(
                    owner_id=account_row.owner_id if account_row else None,
                    account_pk=account_row.id if account_row else None,
                    account_identifier=cookie_id,
                    username=username,
                    trigger_reason=trigger_reason,
                    login_status=login_status,
                    failure_reason=failure_reason,
                    error_message=error_message,
                    updated_cookie_names=updated_cookie_names,
                    duration_ms=duration_ms,
                )
                session.add(log)
                await session.commit()
                await session.refresh(log)
                return log.id

        try:
            return self._run_async(_insert)
        except Exception as e:
            # 写日志失败不能阻断登录主流程，仅记录 warning
            logger.warning(f"添加账号登录日志失败: {e}")
            return None

    def get_risk_control_logs(self, cookie_id: str = None, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """获取风控日志列表
        
        Args:
            cookie_id: Cookie ID，为None时获取所有日志
            limit: 限制返回数量
            offset: 偏移量
            
        Returns:
            List[Dict]: 风控日志列表
        """
        async def _query(session_maker):
            async with session_maker() as session:
                stmt = select(XYRiskControlLog)
                if cookie_id:
                    stmt = stmt.where(XYRiskControlLog.account_identifier == cookie_id)
                stmt = stmt.order_by(XYRiskControlLog.created_at.desc()).limit(limit).offset(offset)
                result = await session.execute(stmt)
                logs = result.scalars().all()
                return [
                    {
                        'id': log.id,
                        'cookie_id': log.account_identifier,
                        'event_type': log.event_type,
                        'event_description': log.event_description,
                        'processing_status': log.processing_status,
                        'processing_result': log.processing_result,
                        'captcha_engine': log.captcha_engine,
                        'error_message': log.error_message,
                        'created_at': log.created_at.strftime('%Y-%m-%d %H:%M:%S') if log.created_at else None
                    }
                    for log in logs
                ]
        try:
            return self._run_async(_query)
        except Exception as e:
            logger.error(f"获取风控日志失败: {e}")
            return []

    def get_risk_control_logs_count(self, cookie_id: str = None) -> int:
        """获取风控日志总数
        
        Args:
            cookie_id: Cookie ID，为None时获取所有日志数量
            
        Returns:
            int: 日志总数
        """
        async def _count(session_maker):
            async with session_maker() as session:
                stmt = select(func.count(XYRiskControlLog.id))
                if cookie_id:
                    stmt = stmt.where(XYRiskControlLog.account_identifier == cookie_id)
                result = await session.execute(stmt)
                return result.scalar() or 0
        try:
            return self._run_async(_count)
        except Exception as e:
            logger.error(f"获取风控日志数量失败: {e}")
            return 0
    
    # ==================== 订单相关 ====================
    
    def get_order_by_id(self, order_id: str) -> Optional[Dict[str, Any]]:
        """获取订单信息"""
        async def _query(session_maker):
            async with session_maker() as session:
                stmt = select(XYOrder).where(XYOrder.order_no == order_id)
                result = await session.execute(stmt)
                order = result.scalars().first()
                if not order:
                    return None
                return {
                    'id': order.id,
                    'order_id': order.order_no,
                    'account_id': order.account_id,
                    'item_id': order.item_id,
                    'buyer_id': order.buyer_id,
                    'chat_id': order.chat_id,
                    'status': order.status,
                    'amount': str(order.amount) if order.amount else '0',
                    'quantity': order.quantity,
                    'is_bargain': order.is_bargain,
                }
        return self._run_async(_query)
    
    def update_order_yifan_status(self, order_id: str, **kwargs) -> bool:
        """更新订单亦凡状态"""
        async def _update(session_maker):
            async with session_maker() as session:
                values = {}
                if 'yifan_order_no' in kwargs:
                    values['yifan_order_no'] = kwargs['yifan_order_no']
                if 'chat_id' in kwargs:
                    values['chat_id'] = kwargs['chat_id']
                if not values:
                    return True
                stmt = update(XYOrder).where(XYOrder.order_no == order_id).values(**values)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
        try:
            return self._run_async(_update)
        except Exception as e:
            logger.error(f"更新订单状态失败: {e}")
            return False
    
    def update_order_bargain_status(self, order_id: str, is_bargain: bool = True) -> bool:
        """更新订单小刀状态
        
        Args:
            order_id: 订单号
            is_bargain: 是否小刀
            
        Returns:
            bool: 是否更新成功
        """
        async def _update(session_maker):
            async with session_maker() as session:
                stmt = update(XYOrder).where(XYOrder.order_no == order_id).values(is_bargain=is_bargain)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
        try:
            result = self._run_async(_update)
            if result:
                logger.info(f"订单 {order_id} 小刀状态已更新为: {is_bargain}")
            return result or False
        except Exception as e:
            logger.error(f"更新订单小刀状态失败: {e}")
            return False
    
    # ==================== 关键词相关 ====================
    
    def get_keywords(self, cookie_id: str) -> List[Dict[str, Any]]:
        """获取关键词列表"""
        async def _query(session_maker):
            async with session_maker() as session:
                account_stmt = select(XYAccount.id).where(XYAccount.account_id == cookie_id)
                account_result = await session.execute(account_stmt)
                account_pk = account_result.scalar_one_or_none()
                if not account_pk:
                    return []
                
                stmt = select(XYKeywordRule).where(
                    XYKeywordRule.account_pk == account_pk,
                    XYKeywordRule.is_active == True
                )
                result = await session.execute(stmt)
                keywords = result.scalars().all()
                return [{
                    'id': k.id,
                    'keyword': k.keyword,
                    'reply': k.reply_content,
                    'reply_type': k.reply_type or 'text',
                    'item_id': k.item_id,
                    'image_url': k.image_url,
                } for k in keywords]
        return self._run_async(_query)
    
    def get_keywords_with_type(self, cookie_id: str) -> List[Dict[str, Any]]:
        """获取关键词列表（包含类型信息）"""
        async def _query(session_maker):
            async with session_maker() as session:
                account_stmt = select(XYAccount.id).where(XYAccount.account_id == cookie_id)
                account_result = await session.execute(account_stmt)
                account_pk = account_result.scalar_one_or_none()
                if not account_pk:
                    return []
                
                stmt = select(XYKeywordRule).where(
                    XYKeywordRule.account_pk == account_pk,
                    XYKeywordRule.is_active == True
                )
                result = await session.execute(stmt)
                keywords = result.scalars().all()
                return [{
                    'id': k.id,
                    'keyword': k.keyword,
                    'reply': k.reply_content,
                    'type': k.reply_type or 'text',
                    'item_id': k.item_id,
                    'image_url': k.image_url,
                } for k in keywords]
        return self._run_async(_query)
    
    def update_keyword_image_url(self, cookie_id: str, keyword: str, image_url: str) -> bool:
        """更新关键词图片URL"""
        async def _update(session_maker):
            async with session_maker() as session:
                account_stmt = select(XYAccount.id).where(XYAccount.account_id == cookie_id)
                account_result = await session.execute(account_stmt)
                account_pk = account_result.scalar_one_or_none()
                if not account_pk:
                    return False
                
                stmt = update(XYKeywordRule).where(
                    XYKeywordRule.account_pk == account_pk,
                    XYKeywordRule.keyword == keyword
                ).values(image_url=image_url)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
        try:
            return self._run_async(_update)
        except Exception as e:
            logger.error(f"更新关键词图片URL失败: {e}")
            return False
    
    # ==================== 卡券相关 ====================
    
    def update_card_image_url(self, card_id: int, image_url: str) -> bool:
        """更新卡券图片URL"""
        async def _update():
            async with async_session_maker() as session:
                stmt = update(Card).where(Card.id == card_id).values(image_url=image_url)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
        try:
            return self._run_async(_update())
        except Exception as e:
            logger.error(f"更新卡券图片URL失败: {e}")
            return False
    
    def update_card_image_urls(self, card_id: int, index: int, cdn_url: str) -> bool:
        """更新卡券多图片列表中指定索引的图片URL
        
        Args:
            card_id: 卡券ID
            index: 图片索引（0-2）
            cdn_url: CDN图片URL
            
        Returns:
            是否更新成功
        """
        import json
        
        async def _update(session_maker):
            async with session_maker() as session:
                # 先获取当前的image_urls
                stmt = select(Card.image_urls).where(Card.id == card_id)
                result = await session.execute(stmt)
                current_urls = result.scalar_one_or_none()
                
                # 解析JSON
                if current_urls:
                    try:
                        urls_list = json.loads(current_urls)
                    except Exception:
                        urls_list = []
                else:
                    urls_list = []
                
                # 确保列表长度足够
                while len(urls_list) <= index:
                    urls_list.append("")
                
                # 更新指定索引的URL
                urls_list[index] = cdn_url
                
                # 保存回数据库
                new_urls_json = json.dumps(urls_list, ensure_ascii=False)
                update_stmt = update(Card).where(Card.id == card_id).values(image_urls=new_urls_json)
                result = await session.execute(update_stmt)
                await session.commit()
                return result.rowcount > 0
        try:
            return self._run_async(_update)
        except Exception as e:
            logger.error(f"更新卡券多图片URL失败: {e}")
            return False
    
    def update_confirm_receipt_image_url(self, cookie_id: str, image_url: str) -> bool:
        """更新确认收货消息的图片URL
        
        Args:
            cookie_id: 账号ID
            image_url: CDN图片URL
            
        Returns:
            是否更新成功
        """
        async def _update(session_maker):
            async with session_maker() as session:
                stmt = update(ConfirmReceiptMessage).where(
                    ConfirmReceiptMessage.account_id == cookie_id
                ).values(message_image=image_url)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
        try:
            return self._run_async(_update)
        except Exception as e:
            logger.error(f"更新确认收货图片URL失败: {e}")
            return False
    
    def update_default_reply_image_url(self, cookie_id: str, image_url: str, item_id: str = None) -> bool:
        """更新默认回复的图片URL
        
        Args:
            cookie_id: 账号ID
            image_url: CDN图片URL
            item_id: 商品ID（可选，None表示账号级别）
            
        Returns:
            是否更新成功
        """
        async def _update(session_maker):
            async with session_maker() as session:
                if item_id:
                    stmt = update(DefaultReply).where(
                        DefaultReply.account_id == cookie_id,
                        DefaultReply.item_id == item_id
                    ).values(reply_image=image_url)
                else:
                    stmt = update(DefaultReply).where(
                        DefaultReply.account_id == cookie_id,
                        DefaultReply.item_id.is_(None)
                    ).values(reply_image=image_url)
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
        try:
            return self._run_async(_update)
        except Exception as e:
            logger.error(f"更新默认回复图片URL失败: {e}")
            return False
    
    # ==================== 默认回复 ====================
    # 说明：默认回复的读写已统一由 backend-web 的 DefaultReplyService 处理，
    # websocket 端 auto_reply_service 直接用 ORM 查询，故此处不再保留兼容方法。
    
    # ==================== 通知相关 ====================
    
    def get_notification_config(self, cookie_id: str) -> Optional[Dict[str, Any]]:
        """获取通知配置
        
        Args:
            cookie_id: Cookie ID
            
        Returns:
            通知配置字典或None
        """
        from common.models.notification_channel import NotificationChannel
        from common.models.message_notification import MessageNotification
        
        async def _query(session_maker):
            async with session_maker() as session:
                # 获取账号的第一个启用的通知配置
                stmt = select(
                    MessageNotification, NotificationChannel
                ).join(
                    NotificationChannel,
                    MessageNotification.channel_id == NotificationChannel.id
                ).where(
                    MessageNotification.account_identifier == cookie_id,
                    MessageNotification.enabled == True,
                    NotificationChannel.enabled == True
                ).limit(1)
                
                result = await session.execute(stmt)
                row = result.first()
                
                if not row:
                    return None
                
                notification, channel = row
                return {
                    'id': notification.id,
                    'channel_id': channel.id,
                    'enabled': notification.enabled,
                    'channel_name': channel.name,
                    'channel_type': channel.channel_type,
                    'channel_config': channel.config_payload
                }
        
        try:
            return self._run_async(_query)
        except Exception as e:
            logger.error(f"获取通知配置失败: {e}")
            return None
    
    # ==================== 清理相关 ====================
    
    def cleanup_old_data(self, days: int = 90) -> Dict[str, int]:
        """清理过期的历史数据
        
        Args:
            days: 保留最近N天的数据，默认90天
            
        Returns:
            清理统计信息
        """
        async def _cleanup(session_maker):
            stats = {
                'risk_control_logs': 0,
                'total_cleaned': 0
            }
            try:
                async with session_maker() as session:
                    from datetime import timedelta
                    cutoff_date = get_beijing_now_naive() - timedelta(days=days)
                    
                    # 清理风控日志
                    try:
                        from sqlalchemy import delete
                        stmt = delete(XYRiskControlLog).where(XYRiskControlLog.created_at < cutoff_date)
                        result = await session.execute(stmt)
                        stats['risk_control_logs'] = result.rowcount
                        if result.rowcount > 0:
                            logger.info(f"清理了 {result.rowcount} 条过期的风控日志（{days}天前）")
                    except Exception as e:
                        logger.warning(f"清理风控日志失败: {e}")
                    
                    await session.commit()
                    stats['total_cleaned'] = stats['risk_control_logs']
                    
            except Exception as e:
                logger.error(f"清理旧数据失败: {e}")
            
            return stats
        
        try:
            return self._run_async(_cleanup) or {
                'risk_control_logs': 0,
                'total_cleaned': 0
            }
        except Exception as e:
            logger.error(f"清理旧数据异常: {e}")
            return {
                'risk_control_logs': 0,
                'total_cleaned': 0
            }
    
    def get_account_notifications(self, cookie_id: str) -> List[Dict[str, Any]]:
        """获取账号的通知配置
        
        Args:
            cookie_id: Cookie ID
            
        Returns:
            通知配置列表
        """
        from common.models.notification_channel import NotificationChannel
        from common.models.message_notification import MessageNotification
        
        async def _query(session_maker):
            async with session_maker() as session:
                stmt = select(
                    MessageNotification, NotificationChannel
                ).join(
                    NotificationChannel,
                    MessageNotification.channel_id == NotificationChannel.id
                ).where(
                    MessageNotification.account_identifier == cookie_id,
                    NotificationChannel.enabled == True
                ).order_by(MessageNotification.id)
                
                result = await session.execute(stmt)
                rows = result.all()
                
                notifications = []
                for notification, channel in rows:
                    notifications.append({
                        'id': notification.id,
                        'channel_id': channel.id,
                        'enabled': notification.enabled,
                        'channel_name': channel.name,
                        'channel_type': channel.channel_type,
                        'channel_config': channel.config_payload
                    })
                
                return notifications
        
        try:
            return self._run_async(_query) or []
        except Exception as e:
            logger.error(f"获取账号通知配置失败: {e}")
            return []
    
    def get_notification_channels(self, user_id: int = None) -> List[Dict[str, Any]]:
        """获取所有通知渠道
        
        Args:
            user_id: 用户ID，为None时获取所有渠道
            
        Returns:
            通知渠道列表
        """
        from common.models.notification_channel import NotificationChannel
        
        async def _query(session_maker):
            async with session_maker() as session:
                stmt = select(NotificationChannel)
                if user_id:
                    stmt = stmt.where(NotificationChannel.owner_id == user_id)
                stmt = stmt.where(NotificationChannel.enabled == True)
                
                result = await session.execute(stmt)
                channels = result.scalars().all()
                
                return [{
                    'id': ch.id,
                    'name': ch.name,
                    'type': ch.channel_type,
                    'config': ch.config_payload,
                    'enabled': ch.enabled
                } for ch in channels]
        
        try:
            return self._run_async(_query) or []
        except Exception as e:
            logger.error(f"获取通知渠道失败: {e}")
            return []
    
    def get_all_message_notifications(self) -> Dict[str, List[Dict[str, Any]]]:
        """获取所有账号的通知配置
        
        Returns:
            按cookie_id分组的通知配置字典
        """
        from common.models.notification_channel import NotificationChannel
        from common.models.message_notification import MessageNotification
        
        async def _query(session_maker):
            async with session_maker() as session:
                stmt = select(
                    MessageNotification, NotificationChannel
                ).join(
                    NotificationChannel,
                    MessageNotification.channel_id == NotificationChannel.id
                ).where(
                    NotificationChannel.enabled == True
                ).order_by(
                    MessageNotification.account_identifier,
                    MessageNotification.id
                )
                
                result = await session.execute(stmt)
                rows = result.all()
                
                notifications_dict = {}
                for notification, channel in rows:
                    cookie_id = notification.account_identifier
                    if cookie_id not in notifications_dict:
                        notifications_dict[cookie_id] = []
                    
                    notifications_dict[cookie_id].append({
                        'id': notification.id,
                        'channel_id': channel.id,
                        'enabled': notification.enabled,
                        'channel_name': channel.name,
                        'channel_type': channel.channel_type,
                        'channel_config': channel.config_payload
                    })
                
                return notifications_dict
        
        try:
            return self._run_async(_query) or {}
        except Exception as e:
            logger.error(f"获取所有消息通知配置失败: {e}")
            return {}
    
    def save_item_info(self, cookie_id: str, item_id: str, item_data=None, **kwargs) -> bool:
        """保存或更新商品信息
        
        Args:
            cookie_id: Cookie ID
            item_id: 商品ID
            item_data: 商品详情数据，可以是字符串或字典
            
        Returns:
            bool: 操作是否成功
        """
        # 验证：如果没有商品详情数据，则不保存
        if not item_data:
            logger.debug(f"跳过保存商品信息：缺少商品详情数据 - {item_id}")
            return False
        
        async def _save(session_maker):
            async with session_maker() as session:
                # 获取账号主键
                account_stmt = select(XYAccount.id, XYAccount.owner_id).where(XYAccount.account_id == cookie_id)
                account_result = await session.execute(account_stmt)
                account_row = account_result.first()
                if not account_row:
                    logger.warning(f"保存商品信息失败：账号不存在 - {cookie_id}")
                    return False
                
                account_pk, owner_id = account_row
                
                # 检查商品是否已存在
                stmt = select(XYCatalogItem).where(
                    XYCatalogItem.account_pk == account_pk,
                    XYCatalogItem.item_id == item_id
                )
                result = await session.execute(stmt)
                existing = result.scalars().first()
                
                if existing:
                    # 更新商品信息
                    metadata = existing.metadata_json or {}
                    if isinstance(item_data, dict):
                        import json
                        metadata['detail'] = json.dumps(item_data, ensure_ascii=False)
                        if item_data.get('title'):
                            existing.title = item_data['title']
                    else:
                        metadata['detail'] = item_data
                    existing.metadata_json = metadata
                    await session.commit()
                    logger.info(f"更新商品信息: {item_id}")
                else:
                    # 新增商品信息
                    import json
                    title = ''
                    detail_str = ''
                    if isinstance(item_data, dict):
                        title = item_data.get('title', '')
                        detail_str = json.dumps(item_data, ensure_ascii=False)
                    else:
                        detail_str = item_data
                    
                    new_item = XYCatalogItem(
                        owner_id=owner_id,
                        account_pk=account_pk,
                        item_id=item_id,
                        title=title,
                        metadata_json={'detail': detail_str}
                    )
                    session.add(new_item)
                    await session.commit()
                    logger.info(f"新增商品信息: {item_id}")
                
                return True
        
        try:
            return self._run_async(_save) or False
        except Exception as e:
            logger.error(f"保存商品信息失败: {e}")
            return False
    
    def batch_save_item_basic_info(self, items: List[Dict[str, Any]]) -> int:
        """批量保存商品基本信息（新商品）
        
        Args:
            items: 商品信息列表，每个包含 cookie_id, item_id, item_title, item_price, item_category, item_detail 等
            
        Returns:
            int: 成功保存的数量
        """
        async def _batch_save(session_maker):
            saved_count = 0
            async with session_maker() as session:
                for item_data in items:
                    try:
                        cookie_id = item_data.get('cookie_id')
                        item_id = item_data.get('item_id')
                        
                        if not cookie_id or not item_id:
                            continue
                        
                        # 获取账号主键和owner_id
                        account_stmt = select(XYAccount.id, XYAccount.owner_id).where(XYAccount.account_id == cookie_id)
                        account_result = await session.execute(account_stmt)
                        account_row = account_result.first()
                        if not account_row:
                            logger.warning(f"批量保存商品: 未找到账号 {cookie_id}")
                            continue
                        
                        # 检查商品是否已存在
                        existing_stmt = select(XYCatalogItem.id).where(
                            XYCatalogItem.account_pk == account_row.id,
                            XYCatalogItem.item_id == item_id
                        )
                        existing_result = await session.execute(existing_stmt)
                        if existing_result.scalar_one_or_none():
                            continue  # 已存在，跳过
                        
                        # 创建新商品
                        new_item = XYCatalogItem(
                            owner_id=account_row.owner_id,
                            account_pk=account_row.id,
                            item_id=item_id,
                            title=item_data.get('item_title', ''),
                            price=item_data.get('item_price', '0'),
                            metadata_json={
                                'category': item_data.get('item_category', ''),
                                'detail': item_data.get('item_detail', ''),
                                'description': item_data.get('item_description', ''),
                            },
                            created_at=get_beijing_now_naive()
                        )
                        session.add(new_item)
                        saved_count += 1
                    except Exception as e:
                        logger.error(f"保存商品 {item_data.get('item_id')} 失败: {e}")
                        continue
                
                await session.commit()
            return saved_count
        
        try:
            return self._run_async(_batch_save) or 0
        except Exception as e:
            logger.error(f"批量保存商品基本信息失败: {e}")
            return 0
    
    def batch_update_item_title_price(self, items: List[Dict[str, Any]]) -> int:
        """批量更新商品标题和价格
        
        Args:
            items: 商品信息列表，每个包含 cookie_id, item_id, item_title, item_price 等
            
        Returns:
            int: 成功更新的数量
        """
        async def _batch_update(session_maker):
            updated_count = 0
            async with session_maker() as session:
                for item_data in items:
                    try:
                        cookie_id = item_data.get('cookie_id')
                        item_id = item_data.get('item_id')
                        
                        if not cookie_id or not item_id:
                            continue
                        
                        # 获取账号主键
                        account_stmt = select(XYAccount.id).where(XYAccount.account_id == cookie_id)
                        account_result = await session.execute(account_stmt)
                        account_pk = account_result.scalar_one_or_none()
                        if not account_pk:
                            continue
                        
                        # 更新商品标题和价格
                        update_values = {}
                        if 'item_title' in item_data:
                            update_values['title'] = item_data['item_title']
                        if 'item_price' in item_data:
                            update_values['price'] = item_data['item_price']
                        
                        if update_values:
                            stmt = update(XYCatalogItem).where(
                                XYCatalogItem.account_pk == account_pk,
                                XYCatalogItem.item_id == item_id
                            ).values(**update_values)
                            result = await session.execute(stmt)
                            if result.rowcount > 0:
                                updated_count += 1
                    except Exception as e:
                        logger.error(f"更新商品 {item_data.get('item_id')} 失败: {e}")
                        continue
                
                await session.commit()
            return updated_count
        
        try:
            return self._run_async(_batch_update) or 0
        except Exception as e:
            logger.error(f"批量更新商品标题价格失败: {e}")
            return 0

    def update_item_detail(self, cookie_id: str, item_id: str, item_detail: str) -> bool:
        """更新商品详情（不覆盖商品标题等基本信息）
        
        Args:
            cookie_id: Cookie ID
            item_id: 商品ID
            item_detail: 商品详情内容
            
        Returns:
            bool: 操作是否成功
        """
        async def _update(session_maker):
            async with session_maker() as session:
                # 获取账号主键
                account_stmt = select(XYAccount.id).where(XYAccount.account_id == cookie_id)
                account_result = await session.execute(account_stmt)
                account_pk = account_result.scalar_one_or_none()
                if not account_pk:
                    logger.warning(f"更新商品详情失败：账号不存在 - {cookie_id}")
                    return False
                
                # 查找商品
                stmt = select(XYCatalogItem).where(
                    XYCatalogItem.account_pk == account_pk,
                    XYCatalogItem.item_id == item_id
                )
                result = await session.execute(stmt)
                item = result.scalars().first()
                
                if not item:
                    logger.warning(f"更新商品详情失败：商品不存在 - {item_id}")
                    return False
                
                # 更新metadata_json中的detail字段
                metadata = item.metadata_json or {}
                metadata['detail'] = item_detail
                
                update_stmt = update(XYCatalogItem).where(
                    XYCatalogItem.account_pk == account_pk,
                    XYCatalogItem.item_id == item_id
                ).values(metadata_json=metadata)
                
                await session.execute(update_stmt)
                await session.commit()
                logger.info(f"更新商品详情成功: {item_id}")
                return True
        
        try:
            return self._run_async(_update) or False
        except Exception as e:
            logger.error(f"更新商品详情失败: {e}")
            return False

    def get_item_multi_spec_status(self, cookie_id: str, item_id: str) -> bool:
        """获取商品是否为多规格商品
        
        Args:
            cookie_id: Cookie ID
            item_id: 商品ID
            
        Returns:
            bool: 是否为多规格商品
        """
        info = self.get_item_info(cookie_id, item_id)
        if info:
            # 从metadata中获取multi_spec状态
            return info.get('multi_spec', False)
        return False
    
    def get_cookie_by_id(self, cookie_id: str) -> Optional[Dict[str, Any]]:
        """根据cookie_id获取账号信息
        
        Args:
            cookie_id: Cookie ID
            
        Returns:
            账号信息字典或None
        """
        return self.get_cookie_details(cookie_id)
    
    def insert_or_update_order(self, order_id: str, item_id: str = None, buyer_id: str = None, 
                               cookie_id: str = None, chat_id: str = None, **kwargs) -> bool:
        """插入或更新订单
        
        Args:
            order_id: 订单ID
            item_id: 商品ID
            buyer_id: 买家ID
            cookie_id: Cookie ID
            chat_id: 聊天会话ID
            
        Returns:
            bool: 是否成功
        """
        async def _upsert(session_maker):
            async with session_maker() as session:
                # 检查订单是否存在
                stmt = select(XYOrder).where(XYOrder.order_no == order_id)
                result = await session.execute(stmt)
                existing = result.scalars().first()
                
                if existing:
                    # 更新：只有当数据库中的值为空时才更新
                    update_values = {}
                    if item_id and not existing.item_id:
                        update_values['item_id'] = item_id
                    if buyer_id and not existing.buyer_id:
                        update_values['buyer_id'] = buyer_id
                    if chat_id and not existing.chat_id:
                        update_values['chat_id'] = chat_id
                    if update_values:
                        stmt = update(XYOrder).where(XYOrder.order_no == order_id).values(**update_values)
                        await session.execute(stmt)
                        await session.commit()
                    return True
                else:
                    # 获取账号信息
                    owner_id = None
                    if cookie_id:
                        account_stmt = select(XYAccount).where(XYAccount.account_id == cookie_id)
                        account_result = await session.execute(account_stmt)
                        account = account_result.scalars().first()
                        if account:
                            owner_id = account.owner_id
                    
                    if not owner_id:
                        logger.warning(f"无法获取owner_id，跳过订单插入: {order_id}")
                        return False
                    
                    # 插入新订单
                    new_order = XYOrder(
                        order_no=order_id,
                        owner_id=owner_id,
                        item_id=item_id or '',
                        buyer_id=buyer_id or '',
                        chat_id=chat_id or '',
                        account_id=cookie_id,
                        status='processing',
                        created_at=get_beijing_now_naive()
                    )
                    session.add(new_order)
                    await session.commit()
                    logger.info(f"插入新订单成功: {order_id}, item_id={item_id}, buyer_id={buyer_id}")
                    return True
        try:
            return self._run_async(_upsert) or False
        except Exception as e:
            logger.error(f"插入或更新订单失败: {e}")
            return False
    
    def get_cards_by_item_id(self, item_id: str, spec_name: str = None, spec_value: str = None) -> List[Dict[str, Any]]:
        """根据商品ID获取卡券列表（通过关联表查询，含向后兼容回退）
        
        Args:
            item_id: 商品ID
            spec_name: 规格名称（可选，用于多规格匹配）
            spec_value: 规格值（可选，用于多规格匹配）
            
        Returns:
            卡券列表
        """
        async def _query(session_maker):
            async with session_maker() as session:
                from common.services.card_matcher import CardMatcher
                matcher = CardMatcher(session)
                return await matcher.get_cards_by_item_id(item_id, spec_name, spec_value)
        
        try:
            return self._run_async(_query) or []
        except Exception as e:
            logger.error(f"根据商品ID获取卡券失败: {e}")
            return []
    
    def consume_batch_data(self, card_id: int) -> Optional[str]:
        """消费批量数据卡券的一条数据

        从卡券的 data_content 中取出第一行数据并删除。

        并发安全设计（CAS 乐观锁，不依赖行锁与事务隔离级别）：
            采用「读取当前内容 → 用单条 UPDATE 原子替换」的比较并交换方式：
            ``UPDATE xy_cards SET data_content=<去掉首行后的剩余内容>
              WHERE id=:card_id AND data_content=<读取到的旧内容>``。
            MySQL（InnoDB）保证对同一行的单条 UPDATE 是串行执行的，因此并发的
            多个消费请求中只有一个能匹配到旧内容并成功（rowcount=1），其余请求
            rowcount=0（说明内容已被其他请求改写）后自动重读重试，从根本上避免
            同一条卡密/兑换码被重复派发给不同订单。

            相比 ``SELECT ... FOR UPDATE`` 行锁，本方案不依赖连接是否处于显式
            事务、隔离级别或 autocommit 行为，在任意运行环境下都成立。

        Args:
            card_id: 卡券ID

        Returns:
            消费的数据内容或None
        """
        # CAS 失败（被其他并发请求抢先消费）时的最大重试次数，避免极端竞争下死循环
        max_cas_retries = 50

        async def _consume(session_maker):
            async with session_maker() as session:
                for _ in range(max_cas_retries):
                    # 1. 读取当前卡券内容（普通读，无需行锁）
                    stmt = select(Card.data_content).where(Card.id == card_id)
                    result = await session.execute(stmt)
                    current_content = result.scalar_one_or_none()

                    if current_content is None:
                        logger.warning(f"卡券 {card_id} 不存在或没有批量数据")
                        return None

                    # 2. 计算首行与剩余内容
                    lines = [line.strip() for line in current_content.split('\n') if line.strip()]
                    if not lines:
                        logger.warning(f"卡券 {card_id} 批量数据已用完")
                        return None

                    consumed_data = lines[0]
                    remaining_lines = lines[1:]
                    new_content = '\n'.join(remaining_lines) if remaining_lines else ''

                    # 3. CAS 原子替换：仅当 data_content 仍等于刚读取到的旧值时才更新
                    #    并发下只有一个请求能命中（rowcount=1），其余 rowcount=0 重试
                    cas_stmt = (
                        update(Card)
                        .where(Card.id == card_id, Card.data_content == current_content)
                        .values(data_content=new_content)
                    )
                    cas_result = await session.execute(cas_stmt)
                    await session.commit()

                    if cas_result.rowcount == 1:
                        logger.info(f"卡券 {card_id} 消费数据成功，剩余 {len(remaining_lines)} 条")
                        return consumed_data

                    # rowcount=0：内容已被其他并发请求改写，重读重试
                    logger.warning(f"卡券 {card_id} 消费存在并发竞争，重试中...")

                logger.error(f"卡券 {card_id} 消费失败：并发竞争超过最大重试次数 {max_cas_retries}")
                return None

        try:
            return self._run_async(_consume)
        except Exception as e:
            logger.error(f"消费批量数据失败: {e}")
            return None

    def increment_delivery_count(self, card_id: int) -> bool:
        """增加卡券的发货次数
        
        Args:
            card_id: 卡券ID
            
        Returns:
            是否更新成功
        """
        async def _increment(session_maker):
            async with session_maker() as session:
                stmt = (
                    update(Card)
                    .where(Card.id == card_id)
                    .values(delivery_count=Card.delivery_count + 1)
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
        
        try:
            return self._run_async(_increment) or False
        except Exception as e:
            logger.error(f"增加发货次数失败: {e}")
            return False

    # ==================== 消息过滤相关 ====================
    
    def get_message_filter_keywords(self, cookie_id: str, filter_type: str = 'skip_reply') -> List[str]:
        """获取账号的消息过滤关键词列表
        
        Args:
            cookie_id: 账号标识
            filter_type: 过滤类型，默认 'skip_reply'（跳过自动回复）
            
        Returns:
            关键词列表
        """
        async def _query(session_maker):
            async with session_maker() as session:
                result = await session.execute(
                    text("""
                        SELECT keyword FROM xy_message_filters 
                        WHERE account_id = :account_id 
                        AND filter_type = :filter_type 
                        AND enabled = 1
                    """),
                    {"account_id": cookie_id, "filter_type": filter_type}
                )
                rows = result.fetchall()
                return [row.keyword for row in rows]
        
        try:
            return self._run_async(_query) or []
        except Exception as e:
            logger.error(f"获取消息过滤关键词失败: {e}")
            return []


# 全局实例
db_manager = DBManagerCompat()
