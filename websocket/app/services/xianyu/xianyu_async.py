"""
XianyuAsync核心类

功能:
1. 整合ConnectionManager、TokenManager、MessageSender等模块
2. 实现主程序入口main()
3. 实现初始化逻辑init()
4. 实现消息处理调度
5. 管理WebSocket连接生命周期
"""
import asyncio
import json
import time
import os
import sys
import aiohttp
from collections import defaultdict
from typing import Dict, Optional
import weakref
from loguru import logger

from common.utils.xianyu_utils import (
    trans_cookies, generate_device_id, generate_mid
)
from common.utils.time_utils import get_beijing_now_naive
from common.utils.text_utils import safe_str
from app.services.xianyu.connection_manager import ConnectionManager, ConnectionState
from app.services.xianyu.token_manager import TokenManager
from app.services.xianyu.handlers.message_router import MessageRouter

# 配置常量
WEBSOCKET_URL = os.getenv('WEBSOCKET_URL', 'wss://wss-goofish.dingtalk.com/')
HEARTBEAT_INTERVAL = int(os.getenv('HEARTBEAT_INTERVAL', '15'))
HEARTBEAT_TIMEOUT = int(os.getenv('HEARTBEAT_TIMEOUT', '30'))
TOKEN_REFRESH_INTERVAL = int(os.getenv('TOKEN_REFRESH_INTERVAL', '72000'))
TOKEN_RETRY_INTERVAL = int(os.getenv('TOKEN_RETRY_INTERVAL', '7200'))

DEFAULT_HEADERS = {
    'accept': 'application/json',
    'accept-language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'cache-control': 'no-cache',
    'content-type': 'application/x-www-form-urlencoded',
    'origin': 'https://www.goofish.com',
    'pragma': 'no-cache',
    'referer': 'https://www.goofish.com/',
    'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}

WEBSOCKET_HEADERS = {}


class XianyuAsync:
    """闲鱼WebSocket客户端核心类"""
    
    # 类级别的实例管理字典（WeakValueDictionary 防止内存泄漏）
    _instances: weakref.WeakValueDictionary = weakref.WeakValueDictionary()
    _instances_lock = asyncio.Lock()
    
    # 类级别的密码登录时间记录
    _last_password_login_time = {}
    _password_login_cooldown = 60
    
    # 账密错误冷却记录
    _password_error_cooldown_time = {}
    _password_error_cooldown = 5 * 60 * 60
    
    def __init__(self, cookies_str: str = None, cookie_id: str = "default", user_id: int = None):
        """
        初始化XianyuAsync实例
        
        Args:
            cookies_str: Cookie字符串
            cookie_id: 账号唯一标识
            user_id: 用户ID
        """
        logger.info(f"【{cookie_id}】开始初始化XianyuAsync...")
        
        if not cookies_str:
            raise ValueError("未提供cookies")
        
        # 解析cookies
        logger.info(f"【{cookie_id}】解析cookies...")
        self.cookies = trans_cookies(cookies_str)
        logger.info(f"【{cookie_id}】cookies解析完成,包含字段: {list(self.cookies.keys())}")
        
        self.cookie_id = cookie_id
        self.cookies_str = cookies_str
        self.user_id = user_id
        self.base_url = WEBSOCKET_URL
        
        # 验证必需字段
        if 'unb' not in self.cookies:
            # 禁用账号
            try:
                from common.db.compat import db_manager
                db_manager.disable_account(cookie_id, reason="Cookie缺少必需的unb字段")
                logger.warning(f"【{cookie_id}】Cookie缺少unb字段，账号已自动禁用")
            except Exception as e:
                logger.error(f"【{cookie_id}】禁用账号失败: {e}")
            raise ValueError(f"【{cookie_id}】Cookie中缺少必需的'unb'字段")
        
        self.myid = self.cookies['unb']
        logger.info(f"【{cookie_id}】用户ID: {self.myid}")
        self.device_id = generate_device_id(self.myid)
        
        # 心跳配置
        self.heartbeat_interval = HEARTBEAT_INTERVAL
        self.heartbeat_timeout = HEARTBEAT_TIMEOUT
        
        # Token配置
        self.token_refresh_interval = TOKEN_REFRESH_INTERVAL
        self.token_retry_interval = TOKEN_RETRY_INTERVAL
        self.current_token = None
        self.last_token_refresh_time = 0  # 最后Token刷新时间
        
        # 代理配置
        self.proxy_config = self._default_proxy_config()
        
        # 后台任务
        self.heartbeat_task = None
        self.token_refresh_task = None
        self.cleanup_task = None
        self.cookie_refresh_task = None
        self.background_tasks = set()
        
        # 消息处理并发控制
        self.message_semaphore = asyncio.Semaphore(100)
        self.active_message_tasks = 0

        # LWP 请求-响应关联：按 mid 等待服务端响应
        # key: mid（客户端发送时生成），value: asyncio.Future（消息循环收到响应时 set_result）
        # 用于 /r/SingleChatConversation/create 等需要拿响应结果的请求
        from app.services.xianyu.future_manager import FutureManager
        self._mid_future_manager = FutureManager(name=cookie_id, cleanup_interval=30.0)
        
        # Session
        self.session = None
        
        # 初始化连接管理器
        self.connection_manager = ConnectionManager(self)
        
        # 初始化Token管理器
        self.token_manager = TokenManager(self)
        
        # 初始化Cookie/Token管理器（处理滑块验证等复杂逻辑）
        from app.services.xianyu.cookie_token_manager import CookieTokenManager
        self._cookie_token_manager = CookieTokenManager(self)
        
        # 初始化通知管理器
        from app.services.xianyu.notification_manager import NotificationManager
        self._notification_manager = NotificationManager(self.cookie_id)
        
        # 添加缺失的属性（CookieTokenManager需要）
        self.last_token_refresh_status = "not_started"
        self.max_captcha_verification_count = 3
        self.last_message_received_time = 0
        self.message_cookie_refresh_cooldown = 300
        self.restarted_in_browser_refresh = False
        
        # 自动发货相关属性（AutoDeliveryHandler需要）
        self.delivery_sent_orders = {}  # 已发货订单字典 {order_id: timestamp}（防重复发货，支持清理）
        self.last_delivery_time = {}  # 最后发货时间字典 {order_id: timestamp}
        self.delivery_cooldown = 60  # 发货冷却时间（秒）
        self._order_locks = defaultdict(asyncio.Lock)  # 订单锁字典（并发控制）
        self._lock_usage_times = {}  # 锁使用时间 {lock_key: timestamp}
        self._lock_hold_info = {}  # 锁持有信息 {lock_key: {locked, lock_time, release_time, task}}
        self.confirmed_orders = {}  # 已确认订单字典 {order_id: confirm_time}
        self.order_confirm_cooldown = 300  # 确认发货冷却时间（秒）
        self.yifan_account_lock = asyncio.Lock()  # 亦凡账号锁
        self.yifan_account_waiting = False  # 亦凡账号等待状态
        
        # 初始化自动发货处理器
        from app.services.xianyu.auto_delivery_handler import AutoDeliveryHandler
        self.auto_delivery_handler = AutoDeliveryHandler(self)

        # 初始化消息路由器（延迟加载，首次消息时初始化回调）
        self.message_router = MessageRouter(self)
        
        # 注册实例
        self._register_instance()
        
        logger.info(f"【{cookie_id}】XianyuAsync初始化完成")

    def _default_proxy_config(self) -> dict:
        return {
            'proxy_type': 'none',
            'proxy_host': '',
            'proxy_port': 0,
            'proxy_user': '',
            'proxy_pass': ''
        }

    async def _load_runtime_account_state(self) -> Optional[dict]:
        try:
            from sqlalchemy import select
            from common.db.session import async_session_maker
            from common.models import XYAccount

            async with async_session_maker() as session:
                stmt = (
                    select(
                        XYAccount.status,
                        XYAccount.proxy_type,
                        XYAccount.proxy_host,
                        XYAccount.proxy_port,
                        XYAccount.proxy_user,
                        XYAccount.proxy_pass,
                    )
                    .where(XYAccount.account_id == self.cookie_id)
                    .order_by(XYAccount.id.desc())
                    .limit(2)
                )
                result = await session.execute(stmt)
                rows = result.all()
                if not rows:
                    logger.warning(f"【{self.cookie_id}】未找到账号运行配置")
                    return None
                if len(rows) > 1:
                    logger.warning(f"【{self.cookie_id}】检测到重复账号ID，已按最新记录加载运行配置")
                row = rows[0]
                return {
                    'status': row.status or 'disabled',
                    'proxy_type': row.proxy_type or 'none',
                    'proxy_host': row.proxy_host or '',
                    'proxy_port': row.proxy_port or 0,
                    'proxy_user': row.proxy_user or '',
                    'proxy_pass': row.proxy_pass or '',
                }
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】加载账号运行配置失败: {e}")
            return None
    
    def _load_proxy_config(self) -> dict:
        """从数据库加载代理配置"""
        try:
            from common.db.compat import db_manager
            proxy_config = db_manager.get_cookie_proxy_config(self.cookie_id) or self._default_proxy_config()
            if not isinstance(proxy_config, dict):
                proxy_config = self._default_proxy_config()
            proxy_type = proxy_config.get('proxy_type', 'none')
            if proxy_type and proxy_type != 'none':
                logger.info(f"【{self.cookie_id}】加载代理配置: {proxy_type}://{proxy_config.get('proxy_host')}:{proxy_config.get('proxy_port')}")
            else:
                logger.info(f"【{self.cookie_id}】未配置代理")
            return proxy_config
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】加载代理配置失败: {e}")
            return self._default_proxy_config()
    
    def _get_proxy_url(self) -> Optional[str]:
        """根据 self.proxy_config 拼代理 URL（HTTP 出站 + WebSocket 共用）

        统一让所有出站走同一代理 IP，避免账号在闲鱼侧出现"HTTP 来源 IP"
        与"WebSocket 来源 IP"不一致触发风控（典型表现：Token 刷新被拒、
        连续失败 10 次后账号被自动禁用）。

        Returns:
            形如 'http://host:port'、'socks5://user:pass@host:port' 的代理 URL；
            未配置代理时返回 None（调用方应走直连）。
        """
        proxy_type = self.proxy_config.get('proxy_type', 'none')
        if proxy_type == 'none':
            return None

        host = self.proxy_config.get('proxy_host')
        port = self.proxy_config.get('proxy_port')
        user = self.proxy_config.get('proxy_user')
        password = self.proxy_config.get('proxy_pass')

        if not host or not port:
            return None

        if user and password:
            return f"{proxy_type}://{user}:{password}@{host}:{port}"
        return f"{proxy_type}://{host}:{port}"

    async def _load_system_proxy_settings(self) -> Optional[dict]:
        """读取系统级代理设置（xy_system_settings 表）

        Returns:
            {'api_url': str, 'enabled': bool}；读取失败返回 None。
        """
        try:
            from sqlalchemy import select
            from common.db.session import async_session_maker
            from common.models.system_setting import SystemSetting

            async with async_session_maker() as session:
                stmt = select(SystemSetting.key, SystemSetting.value).where(
                    SystemSetting.key.in_(['proxy.api_url', 'proxy.enabled'])
                )
                result = await session.execute(stmt)
                rows = {key: value for key, value in result.all()}

            return {
                'api_url': str(rows.get('proxy.api_url') or '').strip(),
                'enabled': str(rows.get('proxy.enabled') or 'false').strip().lower()
                in ('true', '1', 'yes', 'on'),
            }
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】读取系统代理设置失败: {e}")
            return None

    async def _fetch_system_proxy_endpoint(self) -> Optional[tuple]:
        """调用系统代理 API 获取 HTTP 代理的 (host, port)

        响应格式约定：纯文本 IP:PORT（按行返回，取第一非空行）。
        典型供应商示例响应：
            42.123.45.67:8080
            或多行：
            42.123.45.67:8080
            58.220.95.30:10086
            ...

        失败处理：未启用 / 未配置 / API 返回非 200 / 文本为空 / 格式异常 / 超时
                  统一返回 None，由调用方走直连，不阻塞 WebSocket 连接重试。

        Returns:
            (host, port) 或 None
        """
        config = await self._load_system_proxy_settings()
        if not config or not config['enabled'] or not config['api_url']:
            return None

        api_url = config['api_url']
        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url) as resp:
                    if resp.status != 200:
                        logger.warning(
                            f"【{self.cookie_id}】代理 API 返回状态码 {resp.status}，本次直连"
                        )
                        return None
                    text = (await resp.text() or '').strip()

            if not text:
                logger.warning(f"【{self.cookie_id}】代理 API 返回内容为空，本次直连")
                return None

            # 取第一非空行（兼容多行返回的代理供应商）
            first_line = next((line.strip() for line in text.splitlines() if line.strip()), '')
            if not first_line:
                return None

            # 严格解析 host:port，避免代理供应商误返回 HTML/JSON 等被错误使用
            import re
            m = re.match(r'^([^\s:]+):(\d{1,5})$', first_line)
            if not m:
                logger.warning(
                    f"【{self.cookie_id}】代理 API 返回格式无法解析: {first_line!r}，本次直连"
                )
                return None
            host = m.group(1)
            port = int(m.group(2))
            if not (1 <= port <= 65535):
                logger.warning(f"【{self.cookie_id}】代理端口非法: {port}，本次直连")
                return None

            logger.info(f"【{self.cookie_id}】系统代理 API 获取成功: http://{host}:{port}")
            return (host, port)
        except asyncio.TimeoutError:
            logger.warning(f"【{self.cookie_id}】代理 API 调用超时（10s），本次直连")
            return None
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】代理 API 调用异常: {e}，本次直连")
            return None
    
    async def _interruptible_sleep(self, duration: float):
        """可中断的sleep"""
        chunk_size = 1.0
        remaining = duration
        
        while remaining > 0:
            sleep_time = min(chunk_size, remaining)
            try:
                await asyncio.sleep(sleep_time)
                remaining -= sleep_time
            except asyncio.CancelledError:
                raise
    
    def _register_instance(self):
        """注册实例到全局字典"""
        try:
            XianyuAsync._instances[self.cookie_id] = self
            logger.info(f"【{self.cookie_id}】实例已注册到全局字典")
        except Exception as e:
            logger.error(f"【{self.cookie_id}】注册实例失败: {e}")
    
    def _unregister_instance(self):
        """从全局字典注销实例"""
        try:
            if self.cookie_id in XianyuAsync._instances:
                del XianyuAsync._instances[self.cookie_id]
                logger.info(f"【{self.cookie_id}】实例已从全局字典注销")
        except Exception as e:
            logger.error(f"【{self.cookie_id}】注销实例失败: {e}")

    async def _start_pending_futures_cleanup(self):
        """启动 mid future 超时清理任务（委托给 FutureManager）"""
        await self._mid_future_manager.start()

    async def _cleanup_pending_futures_loop(self):
        """清理超时的 mid futures（已委托给 FutureManager，保留方法兼容性）"""
        # FutureManager 内置清理循环，此方法保留以兼容外部调用
        pass
    
    @classmethod
    def get_instance(cls, cookie_id: str):
        """获取指定cookie_id的实例"""
        return cls._instances.get(cookie_id)
    
    @classmethod
    def get_all_instances(cls):
        """获取所有活跃实例"""
        return dict(cls._instances)
    
    @classmethod
    def get_instance_count(cls):
        """获取当前活跃实例数量"""
        return len(cls._instances)
    
    def _build_session_connector(self):
        """根据当前 self.proxy_config 构造 aiohttp 的 connector

        - SOCKS5 / HTTP / HTTPS：用 aiohttp_socks.ProxyConnector，所有请求自动走代理
        - 无代理或依赖缺失：用普通 TCPConnector 直连

        统一所有 aiohttp 出站（含 Token 刷新、订单查询等）走同一代理，
        避免与 WebSocket 出站 IP 不一致触发闲鱼风控。
        """
        proxy_type = self.proxy_config.get('proxy_type', 'none')
        if proxy_type == 'none':
            return aiohttp.TCPConnector(limit=100, limit_per_host=30)

        host = self.proxy_config.get('proxy_host')
        port = self.proxy_config.get('proxy_port')
        if not host or not port:
            return aiohttp.TCPConnector(limit=100, limit_per_host=30)

        try:
            from aiohttp_socks import ProxyConnector, ProxyType
            if proxy_type == 'socks5':
                socks_type = ProxyType.SOCKS5
            elif proxy_type == 'socks4':
                socks_type = ProxyType.SOCKS4
            elif proxy_type in ('http', 'https'):
                socks_type = ProxyType.HTTP
            else:
                logger.warning(f"【{self.cookie_id}】未知代理类型: {proxy_type}，回退直连")
                return aiohttp.TCPConnector(limit=100, limit_per_host=30)

            connector = ProxyConnector(
                proxy_type=socks_type,
                host=host,
                port=port,
                username=self.proxy_config.get('proxy_user') or None,
                password=self.proxy_config.get('proxy_pass') or None,
                rdns=True,
            )
            logger.info(f"【{self.cookie_id}】HTTP Session 走代理: {proxy_type}://{host}:{port}")
            return connector
        except ImportError:
            logger.error(f"【{self.cookie_id}】aiohttp-socks 未安装，HTTP 代理无法生效，回退直连")
            return aiohttp.TCPConnector(limit=100, limit_per_host=30)
        except Exception as e:
            logger.error(f"【{self.cookie_id}】构造代理 connector 失败: {e}，回退直连")
            return aiohttp.TCPConnector(limit=100, limit_per_host=30)

    async def create_session(self):
        """创建aiohttp session（按当前 proxy_config 接入代理）"""
        if not self.session:
            headers = DEFAULT_HEADERS.copy()
            headers['cookie'] = self.cookies_str.replace('\n', '').replace('\r', '') if self.cookies_str else ''

            connector = self._build_session_connector()
            self.session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
                connector=connector,
            )
            # 记录当前 session 绑定的代理 URL，用于检测代理变化时重建 session
            self._current_session_proxy_url = self._get_proxy_url()
    
    async def close_session(self):
        """关闭aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def refresh_token(self, captcha_retry_count: int = 0):
        """
        刷新token（委托给CookieTokenManager处理，包含滑块验证逻辑）
        
        Args:
            captcha_retry_count: 滑块验证重试次数
            
        Returns:
            新的token或None
        """
        return await self._cookie_token_manager.refresh_token(captcha_retry_count)
    
    async def send_token_refresh_notification(self, error_message: str, notification_type: str = "token_refresh",
                                             chat_id: str = None, attachment_path: str = None, 
                                             verification_url: str = None):
        """发送Token刷新异常通知"""
        try:
            if hasattr(self, '_notification_manager') and self._notification_manager:
                return await self._notification_manager.send_token_refresh_notification(
                    error_message, notification_type, chat_id, attachment_path, verification_url
                )
            else:
                # 创建临时通知管理器
                from app.services.xianyu.notification_manager import NotificationManager
                notification_manager = NotificationManager(self.cookie_id)
                return await notification_manager.send_token_refresh_notification(
                    error_message, notification_type, chat_id, attachment_path, verification_url
                )
        except Exception as e:
            logger.error(f"【{self.cookie_id}】发送Token刷新通知失败: {self._safe_str(e)}")
    
    async def restart_instance(self, reason: str = None):
        """重启实例的公开方法（供 CookieTokenManager 调用）
        
        Args:
            reason: 重启原因，用于日志记录
        """
        if reason:
            logger.info(f"【{self.cookie_id}】重启原因: {reason}")
        await self._restart_instance()
    
    async def _restart_instance(self):
        """重启XianyuLive实例
        
        ⚠️ 注意：此方法会触发当前任务被取消！
        调用此方法后，当前任务会立即被 CookieManager 取消，
        因此不要在此方法后执行任何重要操作。
        """
        try:
            logger.info(f"【{self.cookie_id}】准备重启实例...")

            from app.services.xianyu.cookie_manager import get_manager
            cookie_manager = get_manager()

            if cookie_manager:
                logger.info(f"【{self.cookie_id}】通过CookieManager重启实例...")
                
                # 使用 asyncio 调度重启，避免线程问题
                async def delayed_restart():
                    """延迟重启，给当前任务时间清理"""
                    try:
                        await asyncio.sleep(2.0)
                        # 直接调用异步方法
                        await cookie_manager._stop_task_async(self.cookie_id)
                        await cookie_manager._add_cookie_async(self.cookie_id, self.cookies_str, self.user_id)
                        logger.info(f"【{self.cookie_id}】实例重启请求已触发")
                    except Exception as e:
                        logger.error(f"【{self.cookie_id}】触发实例重启失败: {e}")
                
                # 创建后台任务，不等待它完成
                asyncio.create_task(delayed_restart())
                
                logger.info(f"【{self.cookie_id}】实例重启已调度，当前任务即将退出...")
                logger.warning(f"【{self.cookie_id}】注意：重启请求已调度，CookieManager将在2秒后取消当前任务并启动新实例")
                    
            else:
                logger.warning(f"【{self.cookie_id}】CookieManager不可用，无法重启实例")

        except Exception as e:
            logger.error(f"【{self.cookie_id}】重启实例失败: {self._safe_str(e)}")
    
    def _safe_str(self, obj):
        """安全地将对象转换为字符串（委托公共实现）"""
        return safe_str(obj)
    
    async def init(self, ws):
        """
        初始化WebSocket连接
        
        Args:
            ws: WebSocket连接对象
        """
        # 获取token
        if not self.current_token:
            logger.info(f"【{self.cookie_id}】获取初始token...")
            await self.refresh_token()
        
        if not self.current_token:
            logger.warning(f"【{self.cookie_id}】无法获取有效token")
            raise Exception("Token获取失败")
        
        # 发送注册消息
        msg = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": "444e9908a51d1cb236a27862abc769c9",
                "token": self.current_token,
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self.device_id,
                "mid": generate_mid()
            }
        }
        await ws.send(json.dumps(msg))
        await asyncio.sleep(1)
        
        # 发送同步状态消息
        current_time = int(time.time() * 1000)
        msg = {
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": generate_mid()},
            "body": [
                {
                    "pipeline": "sync",
                    "tooLong2Tag": "PNM,1",
                    "channel": "sync",
                    "topic": "sync",
                    "highPts": 0,
                    "pts": current_time * 1000,
                    "seq": 0,
                    "timestamp": current_time
                }
            ]
        }
        await ws.send(json.dumps(msg))
        logger.info(f'【{self.cookie_id}】连接注册完成')
    
    def _create_tracked_task(self, coro):
        """创建并追踪后台任务，确保异常不会被静默忽略"""
        task = asyncio.create_task(coro)
        self.background_tasks.add(task)
        task.add_done_callback(self.background_tasks.discard)
        return task
    
    def _reset_background_tasks(self):
        """直接重置后台任务引用，不等待取消（用于快速重连）
        
        注意：只重置心跳任务，因为只有心跳任务依赖WebSocket连接。
        其他任务（Token刷新、清理、Cookie刷新）不依赖WebSocket，可以继续运行。
        """
        logger.info(f"【{self.cookie_id}】准备重置后台任务引用（仅重置依赖WebSocket的任务）...")
        
        # 只处理心跳任务（依赖WebSocket，需要重启）
        if self.heartbeat_task:
            status = "已完成" if self.heartbeat_task.done() else "运行中"
            logger.info(f"【{self.cookie_id}】发现心跳任务（状态: {status}），需要重置（因为依赖WebSocket连接）")
            # 尝试取消心跳任务（但不等待）
            if not self.heartbeat_task.done():
                try:
                    self.heartbeat_task.cancel()
                    logger.debug(f"【{self.cookie_id}】已发送取消信号给心跳任务（不等待响应）")
                except Exception as e:
                    logger.warning(f"【{self.cookie_id}】取消心跳任务失败: {e}")
            # 重置心跳任务引用
            self.heartbeat_task = None
            logger.info(f"【{self.cookie_id}】心跳任务引用已重置")
        else:
            logger.info(f"【{self.cookie_id}】没有心跳任务需要重置")
        
        # 检查其他任务的状态（这些任务不依赖WebSocket，不需要重启）
        other_tasks_status = []
        if self.token_refresh_task:
            status = "已完成" if self.token_refresh_task.done() else "运行中"
            other_tasks_status.append(f"Token刷新任务({status})")
        if self.cleanup_task:
            status = "已完成" if self.cleanup_task.done() else "运行中"
            other_tasks_status.append(f"清理任务({status})")
        if self.cookie_refresh_task:
            status = "已完成" if self.cookie_refresh_task.done() else "运行中"
            other_tasks_status.append(f"Cookie刷新任务({status})")
        
        if other_tasks_status:
            logger.info(f"【{self.cookie_id}】其他任务继续运行（不依赖WebSocket）: {', '.join(other_tasks_status)}")
        else:
            logger.info(f"【{self.cookie_id}】没有其他任务在运行")
        
        logger.info(f"【{self.cookie_id}】任务重置完成，可以立即创建新的心跳任务")
    
    async def _handle_message_with_semaphore(self, message_data: dict, websocket):
        """带信号量的消息处理包装器，防止并发任务过多"""
        async with self.message_semaphore:
            self.active_message_tasks += 1
            try:
                await self.handle_message(message_data, websocket)
            finally:
                self.active_message_tasks -= 1
                # 定期记录活跃任务数（每100个任务记录一次）
                if self.active_message_tasks % 100 == 0 and self.active_message_tasks > 0:
                    logger.info(f"【{self.cookie_id}】当前活跃消息处理任务数: {self.active_message_tasks}")
    
    async def handle_message(self, message_data: dict, websocket):
        """
        处理接收到的消息（委托给 MessageRouter）
        
        Args:
            message_data: 消息数据
            websocket: WebSocket连接
        """
        await self.message_router.route(message_data, websocket)
    
    # ==================== 向后兼容的订单方法委托 ==========================
    # 以下方法保留供外部模块直接调用，内部委托给 OrderStatusHandler

    def _extract_order_id(self, message: dict) -> str:
        """从消息中提取订单ID（委托给 OrderStatusHandler）"""
        return self.message_router.order_status_handler.extract_order_id(message)
    
    async def _process_order_status(self, message: dict, send_message: str, item_id: str, buyer_id: str, msg_time: str) -> None:
        """处理订单状态（委托给 OrderStatusHandler）"""
        await self.message_router.order_status_handler.process_order_status(
            message, send_message, item_id, buyer_id, msg_time
        )
    
    async def _fetch_order_detail_async(self, order_id: str, item_id: str = None, buyer_id: str = None) -> None:
        """异步获取订单详情（委托给 OrderStatusHandler）"""
        await self.message_router.order_status_handler._fetch_order_detail_async(
            order_id, item_id, buyer_id
        )
    
    async def pause_cleanup_loop(self):
        """定期清理过期的暂停记录、锁和缓存（防止内存泄漏）"""
        try:
            while True:
                try:
                    current_time = time.time()
                    
                    # 清理过期的暂停记录
                    from app.services.xianyu.resource_manager import pause_manager
                    pause_manager.cleanup_expired_pauses()
                    await asyncio.sleep(0)
                    
                    # 清理过期的消息锁（超过1小时的锁）
                    if hasattr(self, '_message_locks'):
                        expired_locks = [
                            key for key, lock_time in self._message_locks.items()
                            if current_time - lock_time > 3600  # 1小时
                        ]
                        for key in expired_locks:
                            self._message_locks.pop(key, None)
                        if expired_locks:
                            logger.debug(f"【{self.cookie_id}】清理了 {len(expired_locks)} 个过期消息锁")
                    
                    # 清理 delivery_sent_orders（超过24小时的订单记录）
                    expired_delivery_sent = [
                        order_id for order_id, sent_time in self.delivery_sent_orders.items()
                        if current_time - sent_time > 86400  # 24小时
                    ]
                    for order_id in expired_delivery_sent:
                        self.delivery_sent_orders.pop(order_id, None)
                    if expired_delivery_sent:
                        logger.debug(f"【{self.cookie_id}】清理了 {len(expired_delivery_sent)} 个过期发货记录")
                    
                    # 清理 last_delivery_time（超过24小时的记录）
                    expired_delivery_time = [
                        order_id for order_id, delivery_time in self.last_delivery_time.items()
                        if current_time - delivery_time > 86400  # 24小时
                    ]
                    for order_id in expired_delivery_time:
                        self.last_delivery_time.pop(order_id, None)
                    if expired_delivery_time:
                        logger.debug(f"【{self.cookie_id}】清理了 {len(expired_delivery_time)} 个过期发货时间记录")
                    
                    # 清理 confirmed_orders（超过24小时的确认记录）
                    expired_confirmed = [
                        order_id for order_id, confirm_time in self.confirmed_orders.items()
                        if current_time - confirm_time > 86400  # 24小时
                    ]
                    for order_id in expired_confirmed:
                        self.confirmed_orders.pop(order_id, None)
                    if expired_confirmed:
                        logger.debug(f"【{self.cookie_id}】清理了 {len(expired_confirmed)} 个过期订单确认记录")
                    
                    # 清理 _order_locks 相关（超过2小时未使用的锁）
                    expired_order_locks = [
                        key for key, lock_time in self._lock_usage_times.items()
                        if current_time - lock_time > 7200  # 2小时
                    ]
                    for key in expired_order_locks:
                        self._order_locks.pop(key, None)
                        self._lock_usage_times.pop(key, None)
                        self._lock_hold_info.pop(key, None)
                    if expired_order_locks:
                        logger.debug(f"【{self.cookie_id}】清理了 {len(expired_order_locks)} 个过期订单锁")
                    
                    # 每次清理后记录当前内存占用情况（仅当数据量较大时）
                    total_items = (
                        len(self.delivery_sent_orders) +
                        len(self.last_delivery_time) +
                        len(self.confirmed_orders) +
                        len(self._order_locks)
                    )
                    if total_items > 100:
                        logger.info(f"【{self.cookie_id}】内存占用统计: delivery_sent={len(self.delivery_sent_orders)}, "
                                   f"last_delivery_time={len(self.last_delivery_time)}, "
                                   f"confirmed_orders={len(self.confirmed_orders)}, "
                                   f"order_locks={len(self._order_locks)}")
                    
                    await self._interruptible_sleep(300)
                    
                except asyncio.CancelledError:
                    logger.info(f"【{self.cookie_id}】清理循环收到取消信号")
                    raise
                except Exception as e:
                    logger.error(f"【{self.cookie_id}】清理循环异常: {e}")
                    await self._interruptible_sleep(60)
                    
        except asyncio.CancelledError:
            logger.info(f"【{self.cookie_id}】清理循环已取消")
            raise
        finally:
            logger.info(f"【{self.cookie_id}】清理循环已退出")
    
    # ==================== 自动发货相关方法 ====================
    
    @property
    def ws(self):
        """获取当前WebSocket连接"""
        return self.connection_manager.ws if self.connection_manager else None
    
    def is_lock_held(self, lock_key: str) -> bool:
        """检查锁是否被持有"""
        if lock_key not in self._lock_hold_info:
            return False
        return self._lock_hold_info[lock_key].get('locked', False)
    
    async def _delayed_lock_release(self, lock_key: str, delay_minutes: int = 10):
        """延迟释放锁"""
        try:
            await asyncio.sleep(delay_minutes * 60)
            if lock_key in self._lock_hold_info:
                self._lock_hold_info[lock_key]['locked'] = False
                self._lock_hold_info[lock_key]['release_time'] = time.time()
                logger.info(f"【{self.cookie_id}】订单锁 {lock_key} 已延迟释放")
        except asyncio.CancelledError:
            logger.info(f"【{self.cookie_id}】订单锁 {lock_key} 延迟释放任务被取消")
        except Exception as e:
            logger.error(f"【{self.cookie_id}】延迟释放锁失败: {e}")
    
    def is_auto_confirm_enabled(self) -> bool:
        """检查是否启用自动确认发货"""
        try:
            from common.db.compat import db_manager
            return db_manager.get_auto_confirm(self.cookie_id)
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取自动确认设置失败: {e}")
            return False
    
    def is_confirm_before_send_enabled(self) -> bool:
        """检查是否开启发货成功再发卡券开关"""
        try:
            from common.db.compat import db_manager
            return db_manager.get_confirm_before_send(self.cookie_id)
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取发货成功再发卡券设置失败: {e}")
            return False

    def is_send_before_confirm_enabled(self) -> bool:
        """检查是否开启卡券发送成功再确认发货开关"""
        try:
            from common.db.compat import db_manager
            return db_manager.get_send_before_confirm(self.cookie_id)
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取卡券发送成功再确认发货设置失败: {e}")
            return False
            return False
    
    # _extract_order_id, _process_order_status, _fetch_order_detail_async
    # 已委托给 MessageRouter -> OrderStatusHandler（见上方 thin wrappers）
    
    async def _handle_auto_delivery_from_message(self, parsed_message: dict, websocket) -> None:
        """从解析后的消息触发自动发货（参照旧框架message_handler_core.py）
        
        Args:
            parsed_message: 解析后的消息数据
            websocket: WebSocket连接
        """
        try:
            send_user_id = parsed_message.get("send_user_id", "")
            send_user_name = parsed_message.get("send_user_name", "")
            send_message = parsed_message.get("send_message", "")
            chat_id = parsed_message.get("chat_id", "")
            item_id = parsed_message.get("item_id", "")
            msg_time = parsed_message.get("msg_time", "")
            raw_message = parsed_message.get("raw_message", {})
            
            logger.info(f"【{self.cookie_id}】开始处理自动发货: item_id={item_id}, chat_id={chat_id}")
            
            # 调用auto_delivery_handler的_handle_auto_delivery方法
            if hasattr(self, 'auto_delivery_handler') and self.auto_delivery_handler:
                await self.auto_delivery_handler._handle_auto_delivery(
                    websocket=websocket,
                    message=raw_message,
                    send_user_name=send_user_name,
                    send_user_id=send_user_id,
                    item_id=item_id,
                    chat_id=chat_id,
                    msg_time=msg_time
                )
            else:
                logger.warning(f"【{self.cookie_id}】auto_delivery_handler未初始化，跳过自动发货")
                
        except Exception as e:
            logger.error(f"【{self.cookie_id}】处理自动发货失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _handle_card_message(self, parsed_message: dict, websocket) -> None:
        """处理卡片消息（参照旧框架message_handler_core.py的_handle_card_message）
        
        用于检测"小刀"等卡片消息并触发相应处理
        
        Args:
            parsed_message: 解析后的消息数据，包含card_title
            websocket: WebSocket连接
        """
        try:
            card_title = parsed_message.get("card_title", "")
            item_id = parsed_message.get("item_id", "")
            send_user_id = parsed_message.get("send_user_id", "")
            send_user_name = parsed_message.get("send_user_name", "")
            chat_id = parsed_message.get("chat_id", "")
            msg_time = parsed_message.get("msg_time", "")
            raw_message = parsed_message.get("raw_message", {})
            
            # 检测"小刀"卡片消息（参照旧框架）
            if card_title == "我已小刀，待刀成":
                order_id = self._extract_order_id(raw_message)
                logger.info(f"【{self.cookie_id}】检测到小刀卡片消息: order_id={order_id}, item_id={item_id}")
                
                # 更新订单小刀状态
                if order_id:
                    try:
                        from common.db.compat import db_manager
                        db_manager.update_order_bargain_status(order_id, True)
                        logger.info(f"【{self.cookie_id}】订单 {order_id} 检测到小刀，已更新小刀状态")
                    except Exception as e:
                        logger.error(f"【{self.cookie_id}】更新订单小刀状态失败: {e}")
                
                # 检查是否启用自动确认发货
                if self.is_auto_confirm_enabled():
                    if order_id:
                        await asyncio.sleep(2)
                        # 调用auto_delivery_handler的免拼发货方法
                        if hasattr(self, 'auto_delivery_handler') and self.auto_delivery_handler:
                            # 关键防护：在调 pre_check 之前先做 item 归属检查
                            # 因为 pre_check 命中禁止发货时会主动关闭订单，必须确保订单确实属于
                            # 当前账号，避免因数据异常关掉别人的订单。原本 _handle_auto_delivery
                            # 内部第一件事就是 item 归属检查，这里我们提前执行同样的检查。
                            if item_id and item_id != "未知商品":
                                try:
                                    from common.db.compat import db_manager
                                    item_info = db_manager.get_item_info(self.cookie_id, item_id)
                                    if not item_info:
                                        logger.warning(
                                            f"【{self.cookie_id}】小刀卡片：商品 {item_id} 不属于当前账号，"
                                            f"跳过 pre_check / freeshipping / 自动发货"
                                        )
                                        return
                                except Exception as e:
                                    logger.error(
                                        f"【{self.cookie_id}】小刀卡片：检查商品归属失败，跳过自动发货: {e}"
                                    )
                                    return

                            # 在调免拼接口前，先做禁止发货预检查：
                            #   - block：订单被关闭/拦截，不调免拼也不进自动发货
                            #   - card_only：订单已被卖家主动关闭，跳过免拼直接走 _handle_auto_delivery 仅发卡券
                            #   - allow：正常调免拼后再走 _handle_auto_delivery
                            # 预检查结果通过 pre_check_result 传给 _handle_auto_delivery，避免内部重复执行
                            pre_check = await self.auto_delivery_handler.pre_delivery_check_and_close(
                                websocket=websocket,
                                order_no=order_id,
                                buyer_id=send_user_id,
                                chat_id=chat_id,
                                log_prefix=f"【{self.cookie_id}】小刀卡片：",
                                item_id=item_id,
                            )
                            pre_action = pre_check.get('action', 'allow')
                            if pre_action == 'block':
                                logger.info(f"【{self.cookie_id}】小刀卡片：禁止发货命中，订单 {order_id} 拦截结束")
                                return

                            # 仅 allow 时才调用免拼接口；card_only 时订单已被关闭，调免拼无意义
                            if pre_action == 'allow':
                                freeshipping_result = await self.auto_delivery_handler.auto_freeshipping(
                                    order_id, item_id, send_user_id
                                )

                                # 检查是否是"已发货成功"的响应
                                if freeshipping_result and freeshipping_result.get('success'):
                                    success_msg = freeshipping_result.get('message', '')
                                    if 'ORDER_ALREADY_DELIVERY' in success_msg or '已发货成功' in success_msg:
                                        logger.info(f"【{self.cookie_id}】订单 {order_id} 已发货过，只更新数据库状态")

                                        # 更新订单状态为已发货
                                        try:
                                            from common.services.order_service import OrderService
                                            from common.db.session import async_session_maker
                                            async with async_session_maker() as db_session:
                                                order_service = OrderService(db_session)
                                                await order_service.update_order_status(order_id, "shipped")
                                            logger.info(f"【{self.cookie_id}】订单 {order_id} 状态已更新为已发货")
                                        except Exception as e:
                                            logger.error(f"【{self.cookie_id}】更新订单状态失败: {e}")

                                        # 标记已发货，防止重复处理
                                        await self.auto_delivery_handler.mark_delivery_sent(order_id)
                                        return
                            else:
                                logger.info(
                                    f"【{self.cookie_id}】小刀卡片：card_only 模式，订单 {order_id} 已被关闭，"
                                    f"跳过免拼接口，直接进入卡券补发流程"
                                )

                            # 继续正常的自动发货流程，复用 pre_check 结果
                            await self.auto_delivery_handler._handle_auto_delivery(
                                websocket, raw_message, send_user_name,
                                send_user_id, item_id, chat_id, msg_time,
                                pre_check_result=pre_check,
                            )
                        else:
                            logger.warning(f"【{self.cookie_id}】auto_delivery_handler未初始化，跳过小刀处理")
            else:
                logger.debug(f"【{self.cookie_id}】收到卡片消息: {card_title}")
                
        except Exception as e:
            logger.error(f"【{self.cookie_id}】处理卡片消息失败: {e}")
    
    async def _handle_rate_request_message(self, parsed_message: dict, websocket) -> None:
        """处理评价请求消息，自动评价买家（参照旧框架message_handler_core.py）
        
        同时触发确认收货消息（因为系统有时候不发送"买家确认收货，交易成功"消息）
        
        Args:
            parsed_message: 解析后的消息数据
            websocket: WebSocket连接
        """
        try:
            chat_id = parsed_message.get("chat_id", "")
            msg_time = parsed_message.get("msg_time", "")
            item_id = parsed_message.get("item_id", "")
            raw_message = parsed_message.get("raw_message", {})
            
            # 检查商品是否属于当前账号（只有商品ID存在时才检查）
            from app.services.xianyu.rate_service import check_item_belongs_to_account
            if item_id:
                belongs_to_account = await check_item_belongs_to_account(self.cookie_id, item_id)
                if not belongs_to_account:
                    logger.info(f"[{msg_time}] 【{self.cookie_id}】商品 {item_id} 不属于当前账号，跳过自动评价和确认收货消息")
                    return
            # 商品ID不存在时继续执行原有逻辑
            
            # 先触发确认收货消息（因为系统有时候不发送"买家确认收货，交易成功"消息）
            logger.info(f"[{msg_time}] 【{self.cookie_id}】评价请求消息同时触发确认收货消息")
            await self._handle_confirm_receipt_message(parsed_message, websocket)
            
            # 提取订单ID
            order_id = self._extract_order_id(raw_message)
            if not order_id:
                logger.warning(f"[{msg_time}] 【{self.cookie_id}】评价消息无法提取订单ID，跳过自动评价")
                return
            
            # 获取评价内容配置
            from app.services.xianyu.rate_service import RateService, update_order_rated_status, get_rate_feedback_content
            
            feedback = await get_rate_feedback_content(self.cookie_id)
            if feedback is None:
                logger.info(f"[{msg_time}] 【{self.cookie_id}】自动评价未启用或获取评价内容失败，跳过")
                return
            
            logger.info(f"[{msg_time}] 【{self.cookie_id}】收到评价请求，订单ID: {order_id}，商品ID: {item_id}，开始自动评价，内容: {feedback[:30]}...")
            
            # 调用评价服务（传入account_id支持令牌过期自动刷新Cookie）
            rate_service = RateService(self.cookies_str, account_id=self.cookie_id)
            result = await rate_service.rate_buyer(order_id, feedback=feedback)
            
            if result.get('success'):
                logger.info(f"[{msg_time}] 【{self.cookie_id}】订单 {order_id} 自动评价成功")
                # 更新订单评价状态
                await update_order_rated_status(order_id, True)
            else:
                logger.warning(f"[{msg_time}] 【{self.cookie_id}】订单 {order_id} 自动评价失败: {result.get('message')}")
                
        except Exception as e:
            logger.error(f"【{self.cookie_id}】处理评价请求消息异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _handle_confirm_receipt_message(self, parsed_message: dict, websocket):
        """处理买家确认收货消息，发送配置的确认收货回复
        
        参照旧框架 message_handler_core.py 的 _handle_confirm_receipt_message 方法
        
        Args:
            parsed_message: 解析后的消息
            websocket: WebSocket连接
        """
        try:
            msg_time = get_beijing_now_naive().strftime("%Y-%m-%d %H:%M:%S")
            
            chat_id = parsed_message.get("chat_id", "")
            send_user_id = parsed_message.get("send_user_id", "")
            send_user_name = parsed_message.get("send_user_name", "")
            item_id = parsed_message.get("item_id", "")
            
            # 检查商品是否属于当前账号（只有商品ID存在时才检查）
            if item_id:
                from app.services.xianyu.rate_service import check_item_belongs_to_account
                belongs_to_account = await check_item_belongs_to_account(self.cookie_id, item_id)
                if not belongs_to_account:
                    logger.info(f"[{msg_time}] 【{self.cookie_id}】商品 {item_id} 不属于当前账号，跳过确认收货消息")
                    return
            # 商品ID不存在时继续执行原有逻辑
            
            from common.db.session import async_session_maker
            from sqlalchemy import select
            from common.models.confirm_receipt_message import ConfirmReceiptMessage
            
            # 查询确认收货消息配置
            async with async_session_maker() as db_session:
                result = await db_session.execute(
                    select(ConfirmReceiptMessage).where(ConfirmReceiptMessage.account_id == self.cookie_id)
                )
                config = result.scalar_one_or_none()
                
                if not config or not config.enabled:
                    logger.info(f"[{msg_time}] 【{self.cookie_id}】确认收货消息未启用，跳过")
                    return
                
                # 检查是否有内容需要发送
                has_image = config.message_image and config.message_image.strip()
                has_content = config.message_content and config.message_content.strip()
                
                if not has_image and not has_content:
                    logger.info(f"[{msg_time}] 【{self.cookie_id}】确认收货消息内容为空，跳过")
                    return
                
                logger.info(f"[{msg_time}] 【{self.cookie_id}】检测到买家确认收货，准备发送确认收货消息")
                
                # 先发送图片（如果有）
                if has_image:
                    try:
                        image_url = config.message_image.strip()
                        cdn_url = await self._process_confirm_receipt_image(image_url, msg_time)
                        if cdn_url:
                            await self.send_image_msg(websocket, chat_id, send_user_id, cdn_url)
                            logger.info(f"[{msg_time}] 【确认收货图片发出】用户: {send_user_name}, 商品({item_id}): 图片已发送")
                    except Exception as img_error:
                        logger.error(f"[{msg_time}] 【{self.cookie_id}】发送确认收货图片失败: {img_error}")
                
                # 再发送文字（如果有）
                if has_content:
                    try:
                        await self.send_msg(websocket, chat_id, send_user_id, config.message_content.strip())
                        logger.info(f"[{msg_time}] 【确认收货消息发出】用户: {send_user_name}, 商品({item_id}): {config.message_content.strip()[:50]}...")
                    except Exception as msg_error:
                        logger.error(f"[{msg_time}] 【{self.cookie_id}】发送确认收货消息失败: {msg_error}")
                        
        except Exception as e:
            logger.error(f"【{self.cookie_id}】处理确认收货消息异常: {e}")
            import traceback
            logger.error(traceback.format_exc())
    
    async def _process_confirm_receipt_image(self, image_url: str, msg_time: str) -> str:
        """处理确认收货消息的图片，上传到CDN并返回CDN链接
        
        Args:
            image_url: 图片URL（可能是本地路径或CDN链接）
            msg_time: 消息时间
            
        Returns:
            CDN图片URL，失败返回None
        """
        try:
            import os
            import tempfile
            import aiohttp
            from pathlib import Path
            
            if not image_url or not image_url.strip():
                return None
            
            # 判断是否是CDN链接
            cdn_domains = ['gw.alicdn.com', 'img.alicdn.com', 'cdn.', 'oss-cn-', 'cloud.goofish.com']
            is_cdn = any(domain in image_url for domain in cdn_domains)
            
            if is_cdn:
                logger.info(f"[{msg_time}] 【{self.cookie_id}】确认收货消息使用已有的CDN图片链接: {image_url}")
                return image_url
            
            # 处理本地图片路径（图片存储在backend-web服务）
            if image_url.startswith('/static/uploads/') or image_url.startswith('static/uploads/'):
                from app.utils.image_uploader import ImageUploader
                from app.core.config import get_settings
                
                settings = get_settings()
                
                # 使用STATIC_DIR环境变量（Docker共享卷），本地回退到backend-web/static
                _static_env = os.environ.get("STATIC_DIR", "")
                if _static_env:
                    static_root = Path(_static_env)
                    if not static_root.is_absolute():
                        static_root = Path.cwd() / static_root
                else:
                    # 本地源码部署：websocket -> 项目根目录 -> backend-web/static
                    static_root = Path(__file__).resolve().parent.parent.parent.parent.parent / "backend-web" / "static"
                
                # 转换URL路径为本地文件路径
                relative_path = image_url.lstrip('/').replace('static/', '', 1)
                local_image_path = str(static_root / relative_path)
                
                logger.info(f"[{msg_time}] 【{self.cookie_id}】静态文件根目录: {static_root}")
                logger.info(f"[{msg_time}] 【{self.cookie_id}】本地图片路径: {local_image_path}")
                
                if os.path.exists(local_image_path):
                    logger.info(f"[{msg_time}] 【{self.cookie_id}】准备上传确认收货图片到闲鱼CDN: {local_image_path}")
                    
                    uploader = ImageUploader(self.cookies_str)
                    
                    async with uploader:
                        cdn_url = await uploader.upload_image(local_image_path)
                        if cdn_url:
                            logger.info(f"[{msg_time}] 【{self.cookie_id}】确认收货图片上传成功，CDN URL: {cdn_url}")
                            # 上传成功后更新数据库中的图片URL
                            try:
                                from common.db.compat import db_manager
                                db_manager.update_confirm_receipt_image_url(self.cookie_id, cdn_url)
                                logger.info(f"[{msg_time}] 【{self.cookie_id}】已更新确认收货图片URL到数据库")
                            except Exception as e:
                                logger.warning(f"[{msg_time}] 【{self.cookie_id}】更新确认收货图片URL到数据库失败: {e}")
                            return cdn_url
                        else:
                            logger.error(f"[{msg_time}] 【{self.cookie_id}】确认收货图片上传失败: {local_image_path}")
                            return None
                else:
                    # 本地文件不存在，尝试从backend-web服务下载
                    logger.info(f"[{msg_time}] 【{self.cookie_id}】本地图片不存在，尝试从backend-web服务获取...")
                    
                    # 构建backend-web服务的图片URL
                    backend_web_url = settings.backend_web_service_url.rstrip('/')
                    full_image_url = f"{backend_web_url}/{image_url.lstrip('/')}"
                    
                    try:
                        async with aiohttp.ClientSession() as http_session:
                            async with http_session.get(full_image_url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                                if response.status == 200:
                                    # 下载图片到临时文件
                                    image_data = await response.read()
                                    
                                    # 获取文件扩展名
                                    ext = os.path.splitext(image_url)[1] or '.png'
                                    
                                    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp_file:
                                        tmp_file.write(image_data)
                                        tmp_path = tmp_file.name
                                    
                                    try:
                                        logger.info(f"[{msg_time}] 【{self.cookie_id}】从backend-web下载图片成功，准备上传到CDN: {tmp_path}")
                                        
                                        uploader = ImageUploader(self.cookies_str)
                                        
                                        async with uploader:
                                            cdn_url = await uploader.upload_image(tmp_path)
                                            if cdn_url:
                                                logger.info(f"[{msg_time}] 【{self.cookie_id}】确认收货图片上传成功，CDN URL: {cdn_url}")
                                                # 上传成功后更新数据库中的图片URL
                                                try:
                                                    from common.db.compat import db_manager
                                                    db_manager.update_confirm_receipt_image_url(self.cookie_id, cdn_url)
                                                    logger.info(f"[{msg_time}] 【{self.cookie_id}】已更新确认收货图片URL到数据库")
                                                except Exception as e:
                                                    logger.warning(f"[{msg_time}] 【{self.cookie_id}】更新确认收货图片URL到数据库失败: {e}")
                                                return cdn_url
                                            else:
                                                logger.error(f"[{msg_time}] 【{self.cookie_id}】确认收货图片上传失败")
                                                return None
                                    finally:
                                        # 清理临时文件
                                        try:
                                            os.unlink(tmp_path)
                                        except Exception:
                                            pass
                                else:
                                    logger.error(f"[{msg_time}] 【{self.cookie_id}】从backend-web获取图片失败，状态码: {response.status}")
                                    return None
                    except Exception as e:
                        logger.error(f"[{msg_time}] 【{self.cookie_id}】从backend-web获取图片异常: {e}")
                        return None
            else:
                # 其他外部链接，直接使用
                logger.info(f"[{msg_time}] 【{self.cookie_id}】确认收货消息使用外部图片链接: {image_url}")
                return image_url
                
        except Exception as e:
            logger.error(f"[{msg_time}] 【{self.cookie_id}】处理确认收货图片失败: {e}")
            return None
    
    async def send_msg(self, websocket, chat_id: str, send_user_id: str, content: str):
        """发送文本消息（参照旧框架实现）

        消息通过 WebSocket 发出后立即返回成功（不阻塞自动回复）。
        同时注册 mid 等待队列，返回结果中携带 mid，供上层在写入日志后
        异步等待服务端响应、回写发送状态（识别 CSI_FORBID 安全拦截等失败）。
        """
        try:
            import base64
            from common.utils.xianyu_utils import generate_mid, generate_uuid

            # 构建消息内容（参照旧框架）
            msg_content = {
                "contentType": 1,
                "text": {"text": content}
            }
            content_json = json.dumps(msg_content, ensure_ascii=False)
            content_base64 = base64.b64encode(content_json.encode("utf-8")).decode("utf-8")

            mid = generate_mid()
            msg = {
                "lwp": "/r/MessageSend/sendByReceiverScope",
                "headers": {"mid": mid},
                "body": [
                    {
                        "uuid": generate_uuid(),
                        "cid": f"{chat_id}@goofish",
                        "conversationType": 1,
                        "content": {
                            "contentType": 101,
                            "custom": {"type": 1, "data": content_base64}
                        },
                        "redPointPolicy": 0,
                        "extension": {"extJson": "{}"},
                        "ctx": {"appVersion": "1.0", "platform": "web"},
                        "mtags": {},
                        "msgReadStatusSetting": 1
                    },
                    {
                        "actualReceivers": [
                            f"{send_user_id}@goofish",
                            f"{self.myid}@goofish"
                        ]
                    }
                ]
            }
            
            # 打印发送参数用于调试
            logger.info(f"【{self.cookie_id}】发送文本消息: chat_id={chat_id}, to={send_user_id}, myid={self.myid}")
            
            # 打印完整的WebSocket消息用于调试
            msg_str = json.dumps(msg)
            logger.info(f"【{self.cookie_id}】WebSocket发送数据长度: {len(msg_str)} 字节")

            # 注册 mid 等待队列（供上层写日志后异步检测发送结果），注册失败不影响发送
            registered_mid = None
            send_future = None
            try:
                send_future = self._mid_future_manager.create_future(mid, timeout=60)
                registered_mid = mid
            except Exception as reg_e:
                logger.warning(f"【{self.cookie_id}】注册发送结果检测失败（不影响发送）: {self._safe_str(reg_e)}")

            await websocket.send(msg_str)
            logger.info(f"【{self.cookie_id}】发送消息成功: {content[:50]}...")
            return {
                "success": True,
                "mode": "text",
                "content": content,
                "mid": registered_mid,
                # 直接携带 Future 引用：即使服务端响应在上层 await 之前到达
                # （_dispatch_mid_response 已 set_result 并从字典移除），
                # 持有引用仍能拿到结果，避免漏判拦截
                "send_future": send_future,
            }
        except Exception as e:
            logger.error(f"【{self.cookie_id}】发送消息失败: {e}")
            import traceback
            logger.error(f"【{self.cookie_id}】发送消息异常堆栈: {traceback.format_exc()}")
            return {
                "success": False,
                "mode": "text",
                "content": content,
                "error_message": str(e),
            }

    async def wait_send_reject_reason(
        self,
        send_future: "asyncio.Future",
        mid: Optional[str] = None,
        timeout: float = 10.0,
    ) -> Optional[str]:
        """等待发送响应 Future，返回拦截原因（未被拦截或超时返回 None）

        闲鱼对违规内容会异步返回带 reason 的响应（如 CSI_FORBID 安全拦截）。
        正常消息服务端不一定回带相同 mid 的响应，因此超时按"未拦截"处理，
        不视为失败，避免误判。

        直接接收 send_msg 返回的 Future 引用（而非从字典查 mid），
        避免响应早于本方法 await 到达、Future 已被分派移除导致漏判。
        传入 mid 用于超时（服务端无响应）时清理等待队列，防止内存堆积。

        Args:
            send_future: send_msg 返回结果中的 send_future
            mid: send_msg 返回结果中的 mid（用于超时清理）
            timeout: 等待响应超时时间（秒）

        Returns:
            拦截原因明文（含 moreInfo 类型），未被拦截/超时/异常返回 None
        """
        if send_future is None:
            return None
        try:
            response = await asyncio.wait_for(send_future, timeout=timeout)
            return self._extract_send_reject_reason(response)
        except asyncio.TimeoutError:
            return None
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】检测发送结果异常: {self._safe_str(e)}")
            return None
        finally:
            # 已被 _dispatch_mid_response 分派的 mid 已从字典移除（pop 安全幂等）；
            # 超时未响应的 mid 在此清理，防止堆积
            if mid:
                self._mid_future_manager.cancel_future(mid)

    @staticmethod
    def _extract_send_reject_reason(response: dict) -> Optional[str]:
        """从发送响应中提取拦截原因，未被拦截返回 None

        Args:
            response: 服务端返回的完整响应（含 headers/code/body）

        Returns:
            拦截原因明文（含 moreInfo 类型），未拦截返回 None
        """
        if not isinstance(response, dict):
            return None
        body = response.get("body", {})
        if isinstance(body, dict) and body.get("reason"):
            reason = body.get("reason", "")
            more_info = body.get("moreInfo", "")
            return f"{reason}（{more_info}）" if more_info else reason
        return None

    # ==================== LWP 请求-响应关联 ====================

    def _dispatch_mid_response(self, message_data: dict) -> None:
        """将带 mid 的服务端响应分派给等待中的 Future
        
        LWP 协议规则：客户端发请求时在 headers.mid 生成唯一ID，
        服务端响应时会在 headers.mid 带回同样的ID。
        用于 create_chat_conversation 等需要拿响应结果的请求。
        
        Args:
            message_data: 解析后的 WebSocket 消息字典
        """
        try:
            if not isinstance(message_data, dict):
                return
            headers = message_data.get("headers") or {}
            mid = headers.get("mid") if isinstance(headers, dict) else None
            if not mid:
                return
            self._mid_future_manager.resolve_future(mid, message_data)
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】分派 mid 响应失败: {e}")

    async def create_chat_conversation(
        self,
        to_user_id: str,
        item_id: str,
        timeout: float = 15.0,
    ) -> str:
        """创建（或获取）单聊会话，返回会话ID（chat_id）
        
        通过 LWP 协议 /r/SingleChatConversation/create 请求服务端：
        - 服务端基于 (pairFirst, pairSecond, bizType) 幂等生成 cid
        - 已存在则直接返回现有 cid，不会重复创建
        
        Args:
            to_user_id: 对方用户ID（买家ID，不带 @goofish 后缀）
            item_id: 关联商品ID（用作会话卡片显示）
            timeout: 等待响应超时时间（秒），默认15秒
            
        Returns:
            chat_id（不带 @goofish 后缀）
            
        Raises:
            ConnectionError: WebSocket 未连接
            TimeoutError: 等待响应超时
            ValueError: 响应中未找到 cid
        """
        ws = self.connection_manager.ws
        if ws is None:
            raise ConnectionError(f"【{self.cookie_id}】WebSocket 未连接，无法创建会话")

        if not to_user_id:
            raise ValueError("to_user_id 不能为空")
        if not item_id:
            raise ValueError("item_id 不能为空")

        mid = generate_mid()
        msg = {
            "lwp": "/r/SingleChatConversation/create",
            "headers": {"mid": mid},
            "body": [
                {
                    "pairFirst": f"{to_user_id}@goofish",
                    "pairSecond": f"{self.myid}@goofish",
                    "bizType": "1",
                    "extension": {"itemId": str(item_id)},
                    "ctx": {"appVersion": "1.0", "platform": "web"},
                }
            ],
        }

        # 注册等待 Future 并发送请求
        future = self._mid_future_manager.create_future(mid, timeout=60)

        try:
            logger.info(
                f"【{self.cookie_id}】发起创建会话请求: to_user_id={to_user_id}, "
                f"item_id={item_id}, mid={mid}"
            )
            await ws.send(json.dumps(msg))

            # 等待服务端响应
            response = await asyncio.wait_for(future, timeout=timeout)

            # 解析响应提取 cid
            chat_id = self._extract_cid_from_create_chat_response(response)
            if not chat_id:
                logger.error(f"【{self.cookie_id}】创建会话响应中未找到 cid: {response}")
                raise ValueError("响应中未找到 cid")

            logger.info(
                f"【{self.cookie_id}】创建会话成功: to_user_id={to_user_id}, "
                f"item_id={item_id}, chat_id={chat_id}"
            )
            return chat_id
        except asyncio.TimeoutError:
            # 超时清理 pending
            self._mid_future_manager.cancel_future(mid)
            logger.error(
                f"【{self.cookie_id}】创建会话超时: to_user_id={to_user_id}, "
                f"item_id={item_id}, timeout={timeout}s"
            )
            raise TimeoutError(f"创建会话超时（{timeout}秒）")
        except Exception:
            # 其他异常也要清理
            self._mid_future_manager.cancel_future(mid)
            raise

    @staticmethod
    def _extract_cid_from_create_chat_response(response: dict) -> Optional[str]:
        """从创建会话响应中提取会话ID（去掉 @goofish 后缀）
        
        闲鱼 LWP 响应格式不固定，已知可能的结构：
        1) body: [{"singleChatConversation": {"cid": "xxx@goofish"}}]
        2) body: [{"singleChatUserConversation": {"singleChatConversation": {"cid": "xxx@goofish"}}}]
        3) body: [{"data": {"singleChatConversation": {"cid": "xxx@goofish"}}}]
        4) body: [{"cid": "xxx@goofish"}]  (兜底)
        5) body: {"singleChatConversation": {...}}  (body 不是数组)
        
        Args:
            response: 服务端响应字典
            
        Returns:
            chat_id（不带 @goofish 后缀），未找到返回 None
        """
        try:
            if not isinstance(response, dict):
                return None
            body = response.get("body")
            # body 可能是数组或对象，统一转成字典进行提取
            first: Optional[dict] = None
            if isinstance(body, list) and body:
                if isinstance(body[0], dict):
                    first = body[0]
            elif isinstance(body, dict):
                first = body
            if not isinstance(first, dict):
                return None
            
            # 按优先级尝试多种嵌套结构
            conv: Optional[dict] = None
            
            # 结构1: 直接 singleChatConversation
            candidate = first.get("singleChatConversation")
            if isinstance(candidate, dict):
                conv = candidate
            
            # 结构2: singleChatUserConversation.singleChatConversation（会话列表同款格式）
            if conv is None:
                user_conv = first.get("singleChatUserConversation")
                if isinstance(user_conv, dict):
                    candidate = user_conv.get("singleChatConversation")
                    if isinstance(candidate, dict):
                        conv = candidate
            
            # 结构3: data.singleChatConversation
            if conv is None:
                data = first.get("data")
                if isinstance(data, dict):
                    candidate = data.get("singleChatConversation")
                    if isinstance(candidate, dict):
                        conv = candidate
            
            # 结构4: 兜底，直接从 first 找 cid 字段
            if conv is None:
                conv = first
            
            cid = conv.get("cid") or conv.get("id") or ""
            if not cid or not isinstance(cid, str):
                return None
            # 去掉 @goofish 后缀
            if "@" in cid:
                cid = cid.split("@", 1)[0]
            return cid or None
        except Exception:
            return None

    async def _get_image_size_from_url(self, image_url: str) -> tuple:
        """从URL获取图片尺寸（参照旧框架实现）
        
        Args:
            image_url: 图片URL
            
        Returns:
            (width, height) 元组，失败返回 (None, None)
        """
        import aiohttp
        from io import BytesIO
        
        try:
            logger.info(f"【{self.cookie_id}】开始从URL获取图片尺寸: {image_url[:80]}...")
            
            # 不接受AVIF格式（PIL默认不支持），让CDN返回WEBP/JPEG等格式
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'image/jpeg,image/png,image/gif,image/webp,*/*;q=0.8',
                'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
                'Referer': 'https://www.goofish.com/',
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(image_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        from PIL import Image
                        with Image.open(BytesIO(image_data)) as img:
                            width, height = img.size
                            logger.info(f"【{self.cookie_id}】解析图片尺寸成功: {width}x{height}")
                            return (width, height)
                    else:
                        logger.warning(f"【{self.cookie_id}】下载图片失败，HTTP状态码: {response.status}")
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】从URL获取图片尺寸失败: {e}")
        
        return (None, None)
    
    async def send_image_msg(self, websocket, chat_id: str, send_user_id: str, image_url: str, card_id: int = None, keyword: str = None, default_reply_item_id = None, image_index: int = None):
        """发送图片消息（参照旧框架实现）
        
        支持:
        - 闲鱼CDN链接直接发送
        - 本地图片先上传到CDN再发送
        
        Args:
            websocket: WebSocket连接
            chat_id: 聊天会话ID
            send_user_id: 接收者用户ID
            image_url: 图片URL
            card_id: 卡券ID（可选，用于更新卡券图片URL）
            keyword: 关键词（可选，用于更新关键词图片URL）
            default_reply_item_id: 默认回复的商品ID（可选，用于更新默认回复图片URL）
                - None: 不更新默认回复图片
                - "": 更新账号级别的默认回复图片
                - 具体值: 更新指定商品的默认回复图片
            image_index: 多图片索引（可选，用于更新卡券多图片列表中指定索引的URL）
        """
        try:
            import base64
            import os
            from pathlib import Path
            from common.utils.xianyu_utils import generate_mid, generate_uuid
            
            cdn_url = image_url
            width, height = 800, 600  # 默认尺寸
            need_get_size_from_url = False  # 标记是否需要从URL获取尺寸
            
            # 检查是否是CDN链接
            cdn_domains = ["gw.alicdn.com", "img.alicdn.com", "cloud.goofish.com", 
                          "goofish.com", "taobaocdn.com", "tbcdn.cn", "aliimg.com"]
            is_cdn = any(domain in image_url.lower() for domain in cdn_domains)
            
            if is_cdn:
                # CDN链接需要从URL获取尺寸
                logger.info(f"【{self.cookie_id}】使用已有的CDN图片链接: {image_url}")
                need_get_size_from_url = True
            elif image_url.startswith('/static/uploads/') or image_url.startswith('static/uploads/'):
                # 本地图片需要先上传到CDN
                # 使用STATIC_DIR环境变量（Docker共享卷），本地回退到backend-web/static
                _static_env = os.environ.get("STATIC_DIR", "")
                if _static_env:
                    static_root = Path(_static_env)
                    if not static_root.is_absolute():
                        static_root = Path.cwd() / static_root
                else:
                    static_root = Path(__file__).resolve().parent.parent.parent.parent.parent / "backend-web" / "static"
                
                relative_path = image_url.lstrip('/').replace('static/', '', 1)
                local_image_path = str(static_root / relative_path)
                
                logger.info(f"【{self.cookie_id}】静态文件根目录: {static_root}")
                logger.info(f"【{self.cookie_id}】本地图片路径: {local_image_path}")
                
                if os.path.exists(local_image_path):
                    logger.info(f"【{self.cookie_id}】准备上传本地图片到闲鱼CDN: {local_image_path}")
                    
                    # 获取本地图片尺寸
                    try:
                        from PIL import Image
                        with Image.open(local_image_path) as img:
                            width, height = img.size
                            logger.info(f"【{self.cookie_id}】获取到本地图片尺寸: {width}x{height}")
                    except Exception as e:
                        logger.warning(f"【{self.cookie_id}】获取图片尺寸失败，使用默认尺寸: {e}")
                    
                    from app.utils.image_uploader import ImageUploader
                    uploader = ImageUploader(self.cookies_str)
                    
                    async with uploader:
                        cdn_url = await uploader.upload_image(local_image_path)
                        
                    if not cdn_url:
                        logger.error(f"【{self.cookie_id}】图片上传到CDN失败")
                        return {
                            "success": False,
                            "mode": "image",
                            "image_url": image_url,
                            "error_message": "图片上传到CDN失败",
                        }
                    
                    logger.info(f"【{self.cookie_id}】图片上传成功，CDN URL: {cdn_url}")
                    
                    # 上传成功后更新卡券图片URL到数据库
                    if card_id:
                        try:
                            from common.db.compat import db_manager
                            if image_index is not None:
                                # 多图片模式：更新指定索引的图片URL
                                db_manager.update_card_image_urls(card_id, image_index, cdn_url)
                                logger.info(f"【{self.cookie_id}】已更新卡券 {card_id} 的第 {image_index+1} 张图片URL为CDN地址")
                            else:
                                # 单图片模式：更新image_url字段
                                db_manager.update_card_image_url(card_id, cdn_url)
                                logger.info(f"【{self.cookie_id}】已更新卡券 {card_id} 的图片URL为CDN地址")
                        except Exception as e:
                            logger.warning(f"【{self.cookie_id}】更新卡券图片URL失败: {e}")
                    
                    # 上传成功后更新关键词图片URL到数据库
                    if keyword:
                        try:
                            from common.db.compat import db_manager
                            db_manager.update_keyword_image_url(self.cookie_id, keyword, cdn_url)
                            logger.info(f"【{self.cookie_id}】已更新关键词 '{keyword}' 的图片URL为CDN地址")
                        except Exception as e:
                            logger.warning(f"【{self.cookie_id}】更新关键词图片URL失败: {e}")
                    
                    # 上传成功后更新默认回复图片URL到数据库
                    # default_reply_item_id 不为 None 时才更新（空字符串表示账号级别）
                    if default_reply_item_id is not None:
                        try:
                            from common.db.compat import db_manager
                            # 空字符串转为None表示账号级别
                            item_id_for_update = default_reply_item_id if default_reply_item_id else None
                            db_manager.update_default_reply_image_url(self.cookie_id, cdn_url, item_id_for_update)
                            if item_id_for_update:
                                logger.info(f"【{self.cookie_id}】已更新商品 '{item_id_for_update}' 的默认回复图片URL为CDN地址")
                            else:
                                logger.info(f"【{self.cookie_id}】已更新账号级别的默认回复图片URL为CDN地址")
                        except Exception as e:
                            logger.warning(f"【{self.cookie_id}】更新默认回复图片URL失败: {e}")
                else:
                    logger.error(f"【{self.cookie_id}】本地图片文件不存在: {local_image_path}")
                    return {
                        "success": False,
                        "mode": "image",
                        "image_url": image_url,
                        "error_message": "本地图片文件不存在",
                    }
            else:
                # 其他外部链接，尝试直接使用，需要从URL获取尺寸
                logger.warning(f"【{self.cookie_id}】使用非CDN图片链接: {image_url}")
                need_get_size_from_url = True
            
            # 如果需要从URL获取图片尺寸（CDN链接或外部链接）
            if need_get_size_from_url:
                try:
                    actual_width, actual_height = await self._get_image_size_from_url(cdn_url)
                    if actual_width and actual_height:
                        width, height = actual_width, actual_height
                        logger.info(f"【{self.cookie_id}】从URL获取到实际图片尺寸: {width}x{height}")
                except Exception as e:
                    logger.warning(f"【{self.cookie_id}】从URL获取图片尺寸失败，使用默认尺寸: {e}")
            
            # 构建图片消息内容（参照旧框架，使用pics数组格式）
            msg_content = {
                "contentType": 2,
                "image": {
                    "pics": [
                        {
                            "height": int(height),
                            "type": 0,
                            "url": cdn_url,
                            "width": int(width)
                        }
                    ]
                }
            }
            content_json = json.dumps(msg_content, ensure_ascii=False)
            content_base64 = base64.b64encode(content_json.encode("utf-8")).decode("utf-8")
            
            logger.info(f"【{self.cookie_id}】图片消息内容: {content_json}")
            
            msg = {
                "lwp": "/r/MessageSend/sendByReceiverScope",
                "headers": {"mid": generate_mid()},
                "body": [
                    {
                        "uuid": generate_uuid(),
                        "cid": f"{chat_id}@goofish",
                        "conversationType": 1,
                        "content": {
                            "contentType": 101,
                            "custom": {"type": 1, "data": content_base64}
                        },
                        "redPointPolicy": 0,
                        "extension": {"extJson": "{}"},
                        "ctx": {"appVersion": "1.0", "platform": "web"},
                        "mtags": {},
                        "msgReadStatusSetting": 1
                    },
                    {
                        "actualReceivers": [
                            f"{send_user_id}@goofish",
                            f"{self.myid}@goofish"
                        ]
                    }
                ]
            }
            
            # 打印完整的发送消息用于调试
            logger.debug(f"【{self.cookie_id}】发送图片WebSocket消息: {json.dumps(msg, ensure_ascii=False)[:500]}...")
            
            await websocket.send(json.dumps(msg))
            logger.info(f"【{self.cookie_id}】发送图片消息成功: {cdn_url}")
            return {
                "success": True,
                "mode": "image",
                "image_url": cdn_url,
                "original_image_url": image_url,
            }
        except Exception as e:
            logger.error(f"【{self.cookie_id}】发送图片消息失败: {e}")
            return {
                "success": False,
                "mode": "image",
                "image_url": image_url,
                "error_message": str(e),
            }
    
    async def _cancel_background_tasks(self):
        """取消并清理所有后台任务"""
        tasks_to_cancel = []
        
        if self.heartbeat_task and not self.heartbeat_task.done():
            tasks_to_cancel.append(('心跳', self.heartbeat_task))
        
        if self.token_refresh_task and not self.token_refresh_task.done():
            tasks_to_cancel.append(('Token刷新', self.token_refresh_task))
        
        if self.cleanup_task and not self.cleanup_task.done():
            tasks_to_cancel.append(('清理', self.cleanup_task))
        
        if self.cookie_refresh_task and not self.cookie_refresh_task.done():
            tasks_to_cancel.append(('Cookie刷新', self.cookie_refresh_task))
        
        if tasks_to_cancel:
            logger.info(f"【{self.cookie_id}】准备取消 {len(tasks_to_cancel)} 个后台任务...")
            
            for task_name, task in tasks_to_cancel:
                try:
                    task.cancel()
                    logger.info(f"【{self.cookie_id}】已发送取消信号给{task_name}任务")
                except Exception as e:
                    logger.error(f"【{self.cookie_id}】取消{task_name}任务失败: {e}")
            
            # 等待所有任务完成取消
            for task_name, task in tasks_to_cancel:
                try:
                    await asyncio.wait_for(task, timeout=3.0)
                except asyncio.TimeoutError:
                    logger.warning(f"【{self.cookie_id}】{task_name}任务取消超时")
                except asyncio.CancelledError:
                    logger.info(f"【{self.cookie_id}】{task_name}任务已取消")
                except Exception as e:
                    logger.error(f"【{self.cookie_id}】{task_name}任务取消异常: {e}")
            
            logger.info(f"【{self.cookie_id}】所有后台任务已处理完成")
    
    async def main(self):
        """主程序入口"""
        try:
            logger.info(f"【{self.cookie_id}】开始启动XianyuAsync主程序...")
            await self.create_session()
            logger.info(f"【{self.cookie_id}】Session创建完成,开始WebSocket连接循环...")
            
            while True:
                try:
                    runtime_state = await self._load_runtime_account_state()
                    if runtime_state is not None:
                        if runtime_state.get('status') != 'active':
                            logger.warning(f"【{self.cookie_id}】账号已禁用，停止连接")
                            break

                        self.proxy_config = {
                            'proxy_type': runtime_state.get('proxy_type', 'none'),
                            'proxy_host': runtime_state.get('proxy_host', ''),
                            'proxy_port': runtime_state.get('proxy_port', 0),
                            'proxy_user': runtime_state.get('proxy_user', ''),
                            'proxy_pass': runtime_state.get('proxy_pass', ''),
                        }
                    else:
                        logger.warning(f"【{self.cookie_id}】无法刷新账号运行配置，保留当前代理配置继续运行")

                    # 系统级代理总开关：xy_system_settings.proxy.enabled
                    # - 关闭时：账号级代理也不生效（强制直连），让用户可通过系统设置一键关闭所有代理
                    #   （场景：账号级 SOCKS5 代理批量失效时，无需逐个修改账号配置即可切回直连）
                    # - 开启时：账号级代理正常生效；账号未配置代理时使用系统代理 API
                    # - DB 读取失败 (None)：保留账号级代理，避免偶发故障导致全量代理被错误关闭
                    system_proxy_settings = await self._load_system_proxy_settings()
                    if (
                        system_proxy_settings is not None
                        and not system_proxy_settings.get('enabled', False)
                        and self.proxy_config.get('proxy_type', 'none') != 'none'
                    ):
                        original_type = self.proxy_config.get('proxy_type')
                        original_host = self.proxy_config.get('proxy_host')
                        original_port = self.proxy_config.get('proxy_port')
                        logger.info(
                            f"【{self.cookie_id}】系统代理总开关已关闭，账号级代理"
                            f"（{original_type}://{original_host}:{original_port}）"
                            f"暂不启用，本次走直连"
                        )
                        self.proxy_config = self._default_proxy_config()

                    # 账号级代理未配置时，尝试使用系统级代理（来自 xy_system_settings.proxy.*）
                    # 优先级：账号代理（xy_account.proxy_type 非 none）> 系统代理 API > 直连
                    # 失败兜底：API 调用失败时保持 'none'，走直连让重连机制自愈
                    # 注意：_fetch_system_proxy_endpoint 内部会再次校验 proxy.enabled，
                    # 总开关关闭时直接返回 None，无需在此重复判断
                    if self.proxy_config.get('proxy_type', 'none') == 'none':
                        system_proxy = await self._fetch_system_proxy_endpoint()
                        if system_proxy:
                            host, port = system_proxy
                            self.proxy_config = {
                                'proxy_type': 'http',
                                'proxy_host': host,
                                'proxy_port': port,
                                'proxy_user': '',
                                'proxy_pass': '',
                            }

                    # HTTP session 代理状态检测：仅在"代理状态变化"时重建 session
                    # - 首次拿到代理（直连 → 代理）：重建让 HTTP 接入代理
                    # - 代理被取消（代理 → 直连）：重建切回直连
                    # - 代理 URL 在不同 IP 间切换：不重建，HTTP session 保持已有代理 IP
                    #   （不强求与 WebSocket 同 IP，避免每次重连都重建 session）
                    new_proxy_url = self._get_proxy_url()
                    current_proxy_url = getattr(self, '_current_session_proxy_url', None)
                    proxy_state_changed = bool(new_proxy_url) != bool(current_proxy_url)
                    if self.session and proxy_state_changed:
                        logger.info(
                            f"【{self.cookie_id}】HTTP session 代理状态变更"
                            f"（{current_proxy_url or '直连'} → {new_proxy_url or '直连'}），重建 session"
                        )
                        await self.close_session()
                        await self.create_session()
                    
                    headers = WEBSOCKET_HEADERS.copy()
                    headers['Cookie'] = self.cookies_str.replace('\n', '').replace('\r', '') if self.cookies_str else ''
                    
                    # 在WebSocket连接之前获取Token（确保Token有效）
                    if not self.current_token:
                        logger.info(f"【{self.cookie_id}】WebSocket连接前获取Token...")
                        await self.refresh_token()
                        if not self.current_token:
                            # 根据 Token 刷新状态区分失败原因：
                            # - 滑块/风控类失败：不计入禁用计数（属于可恢复的风控场景，账号本身不一定有问题）
                            # - 真实故障（网络/超时/API 业务失败/Cookie 失效）：累加计数，达到 10 次禁用
                            refresh_status = getattr(self, 'last_token_refresh_status', '') or ''
                            # 不计入禁用计数的状态（滑块/风控/冷却）
                            non_counted_statuses = (
                                'failed_captcha',
                                'failed_captcha_exception',
                                'failed_captcha_max_retries',
                                'skipped_cooldown',
                            )

                            if not hasattr(self, '_token_fetch_failures'):
                                self._token_fetch_failures = 0
                            if not hasattr(self, '_token_fetch_failure_times'):
                                self._token_fetch_failure_times = []  # 记录每次失败的时间戳

                            if refresh_status in non_counted_statuses:
                                # 滑块/风控类失败：不累加计数，避免账号在风控期间被误禁用
                                logger.warning(
                                    f"【{self.cookie_id}】Token 获取失败（原因: {refresh_status}），"
                                    f"属于滑块/风控类场景，不计入禁用计数，等待重试..."
                                )
                            else:
                                # 真实故障：记录时间戳，使用时间窗口计数
                                now = time.time()
                                self._token_fetch_failure_times.append(now)
                                # 清理超出1小时窗口的记录
                                window_start = now - 3600
                                self._token_fetch_failure_times = [
                                    t for t in self._token_fetch_failure_times if t > window_start
                                ]
                                self._token_fetch_failures = len(self._token_fetch_failure_times)
                                logger.warning(
                                    f"【{self.cookie_id}】无法获取有效Token"
                                    f"（原因: {refresh_status or '未知'}，近1小时内第{self._token_fetch_failures}次失败），等待重试..."
                                )

                                # 1小时内失败达到20次后禁用账号（更合理的时间窗口阈值）
                                if self._token_fetch_failures >= 20:
                                    logger.error(f"【{self.cookie_id}】Token获取连续失败{self._token_fetch_failures}次，禁用账号")
                                    try:
                                        from common.db.compat import db_manager
                                        db_manager.disable_account(self.cookie_id, reason=f"Token获取连续失败{self._token_fetch_failures}次")
                                        logger.warning(f"【{self.cookie_id}】账号已自动禁用")
                                    except Exception as disable_e:
                                        logger.error(f"【{self.cookie_id}】自动禁用账号失败: {disable_e}")
                                    break

                            # 根据失败原因决定重试间隔：
                            # - 账密登录冷却中（skipped_cooldown）：拉长到 5 分钟。
                            #   该状态属于"确定性可恢复但短期内无法自愈"（账密错误冷却 5 小时 /
                            #   上次登录间隔 300 秒未到），每 5 秒重试无意义且会刷屏日志、
                            #   占用 token API 配额。
                            # - 其他场景（滑块、网络故障、API 业务失败）：保持 5 秒快速重试，
                            #   避免延误账号恢复。
                            sleep_duration = 300 if refresh_status == 'skipped_cooldown' else 5
                            await self._interruptible_sleep(sleep_duration)
                            continue
                    else:
                        # Token获取成功，重置失败计数
                        if hasattr(self, '_token_fetch_failures'):
                            self._token_fetch_failures = 0
                        if hasattr(self, '_token_fetch_failure_times'):
                            self._token_fetch_failure_times = []
                    
                    # 更新连接状态
                    self.connection_manager.set_connection_state(
                        ConnectionState.CONNECTING, 
                        "准备建立WebSocket连接"
                    )
                    # 记录本次连接尝试的开始时间（用于判断是连接建立阶段超时还是连接成功后断开）
                    self._connection_attempt_start_time = time.time()
                    logger.info(f"【{self.cookie_id}】WebSocket目标地址: {self.base_url}")
                    
                    # 创建WebSocket连接
                    async with await self.connection_manager.create_websocket_connection(headers) as websocket:
                        self.connection_manager.ws = websocket
                        logger.info(f"【{self.cookie_id}】WebSocket连接建立成功,开始初始化...")
                        
                        try:
                            # 初始化连接
                            await self.init(websocket)
                            logger.info(f"【{self.cookie_id}】WebSocket初始化完成!")
                            
                            # 更新连接状态
                            self.connection_manager.set_connection_state(
                                ConnectionState.CONNECTED,
                                "初始化完成,连接就绪"
                            )
                            self.connection_manager.connection_failures = 0
                            self.connection_manager.network_failures = 0  # 成功连接后重置网络错误计数
                            self.connection_manager.last_successful_connection = time.time()
                            self._connection_start_time = time.time()  # 记录连接开始时间
                            
                            # 启动后台任务
                            logger.info(f"【{self.cookie_id}】启动后台任务...")
                            
                            # 如果存在旧的心跳任务，先清理（心跳任务依赖WebSocket，必须重启）
                            if self.heartbeat_task:
                                logger.warning(f"【{self.cookie_id}】检测到旧心跳任务引用，先清理...")
                                if not self.heartbeat_task.done():
                                    try:
                                        self.heartbeat_task.cancel()
                                        logger.debug(f"【{self.cookie_id}】已发送取消信号给旧心跳任务")
                                    except Exception as e:
                                        logger.warning(f"【{self.cookie_id}】取消旧心跳任务失败: {e}")
                                self.heartbeat_task = None
                            
                            # 启动心跳任务
                            logger.info(f"【{self.cookie_id}】启动心跳任务...")
                            self.heartbeat_task = asyncio.create_task(
                                self.connection_manager.heartbeat_loop(websocket)
                            )
                            
                            # 启动Token刷新任务
                            if not self.token_refresh_task or self.token_refresh_task.done():
                                self.token_refresh_task = asyncio.create_task(
                                    self.token_manager.token_refresh_loop()
                                )
                            
                            # 启动清理任务
                            if not self.cleanup_task or self.cleanup_task.done():
                                self.cleanup_task = asyncio.create_task(
                                    self.pause_cleanup_loop()
                                )
                            
                            # 启动Cookie刷新任务
                            if not self.cookie_refresh_task or self.cookie_refresh_task.done():
                                logger.info(f"【{self.cookie_id}】启动Cookie刷新任务...")
                                self.cookie_refresh_task = asyncio.create_task(
                                    self.token_manager.cookie_refresh_loop()
                                )
                            else:
                                logger.info(f"【{self.cookie_id}】Cookie刷新任务已在运行，跳过启动")
                            
                            logger.info(f"【{self.cookie_id}】所有后台任务已启动")
                            logger.info(f"【{self.cookie_id}】开始监听WebSocket消息...")
                            
                            # 消息循环
                            async for message in websocket:
                                logger.debug(f"【{self.cookie_id}】收到消息: {len(message) if message else 0} 字节")
                                try:
                                    message_data = json.loads(message)
                                    
                                    # 处理心跳响应
                                    if self.connection_manager.handle_heartbeat_response(message_data):
                                        continue
                                    
                                    # 处理LWP请求-响应关联：如果响应的mid命中等待队列，
                                    # resolve对应Future（用于 create_chat 等需要等待结果的请求）
                                    self._dispatch_mid_response(message_data)
                                    
                                    # 处理其他消息
                                    # 使用追踪的异步任务处理消息，防止阻塞后续消息接收
                                    # 并通过信号量控制并发数量，防止内存泄漏
                                    self._create_tracked_task(self._handle_message_with_semaphore(message_data, websocket))
                                    
                                except Exception as e:
                                    logger.error(f"【{self.cookie_id}】处理消息出错: {e}")
                                    continue
                        
                        finally:
                            # 清理WebSocket引用
                            if self.connection_manager.ws == websocket:
                                self.connection_manager.ws = None
                                logger.info(f"【{self.cookie_id}】WebSocket连接已退出")
                
                except Exception as e:
                    error_msg = str(e)
                    error_type = type(e).__name__
                    
                    # 检查是否是网络类型错误
                    is_network_type_error = (
                        'ConnectionClosedError' in error_type or
                        'ConnectionClosed' in error_type or
                        'no close frame received or sent' in error_msg or
                        'ConnectionResetError' in error_type or
                        'TimeoutError' in error_type or
                        'connection reset' in error_msg.lower()
                    )
                    
                    # 计算本次连接尝试的持续时间（从开始尝试连接到出错）
                    attempt_duration = time.time() - getattr(self, '_connection_attempt_start_time', time.time())
                    
                    # 判断是否曾经成功连接过：检查连接成功后的持续时间
                    # _connection_start_time 是在连接成功并初始化完成后才设置的
                    connection_success_time = getattr(self, '_connection_start_time', 0)
                    # 如果连接成功时间在本次尝试开始之后，说明本次连接曾经成功过
                    was_connected = connection_success_time > getattr(self, '_connection_attempt_start_time', 0)
                    # 连接成功后的持续时间
                    connected_duration = time.time() - connection_success_time if was_connected else 0
                    
                    # 清理WebSocket引用
                    if self.connection_manager.ws:
                        self.connection_manager.ws = None
                    
                    if is_network_type_error and was_connected:
                        # 纯网络错误：连接已经正常工作过，只是网络断开
                        self.connection_manager.network_failures += 1
                        logger.warning(f"【{self.cookie_id}】网络连接断开(第{self.connection_manager.network_failures}次，已连接{connected_duration:.1f}秒): {error_type}")
                        
                        # 检测是否频繁短连接断开
                        if self.connection_manager.record_short_disconnect(connected_duration):
                            # 频繁短连接断开，禁用账号
                            logger.error(f"【{self.cookie_id}】频繁短连接断开，禁用账号")
                            try:
                                from common.db.compat import db_manager
                                db_manager.disable_account(self.cookie_id, reason="未知原因频繁断开连接")
                                logger.warning(f"【{self.cookie_id}】账号已禁用，原因: 未知原因频繁断开连接")
                            except Exception as e:
                                logger.error(f"【{self.cookie_id}】禁用账号失败: {e}")
                            break
                        
                        self.connection_manager.set_connection_state(
                            ConnectionState.RECONNECTING,
                            f"网络断开第{self.connection_manager.network_failures}次"
                        )
                        
                        # 网络错误阈值更宽松，不会导致禁用账号
                        if self.connection_manager.network_failures >= self.connection_manager.max_network_failures:
                            logger.warning(f"【{self.cookie_id}】网络连续断开{self.connection_manager.max_network_failures}次，等待较长时间后重试")
                            # 重置网络失败计数，等待更长时间后继续重试
                            self.connection_manager.network_failures = 0
                            await self._interruptible_sleep(120)  # 等待2分钟
                        else:
                            # 正常重试延迟（指数退避 + 抖动，避免多账号同时重连冲击闲鱼后端）
                            retry_delay = self.connection_manager.calculate_network_retry_delay()
                            logger.info(f"【{self.cookie_id}】将在 {retry_delay} 秒后重试...")
                            await self._interruptible_sleep(retry_delay)
                        
                        continue
                    
                    # 认证/Token相关失败：连接很快就断开或无法建立
                    self.connection_manager.connection_failures += 1
                    self.connection_manager.set_connection_state(
                        ConnectionState.RECONNECTING,
                        f"第{self.connection_manager.connection_failures}次失败"
                    )
                    
                    logger.warning(f"【{self.cookie_id}】连接失败(尝试{attempt_duration:.1f}秒): {error_type} - {error_msg}")
                    
                    # 如果连接尝试时间较短（15秒内失败），说明可能是Token无效，清除缓存
                    if attempt_duration < 15 and self._cookie_token_manager:
                        logger.warning(f"【{self.cookie_id}】连接尝试{attempt_duration:.1f}秒后失败，Token可能无效，清除缓存...")
                        try:
                            await self._cookie_token_manager._delete_cached_token()
                            logger.info(f"【{self.cookie_id}】Token缓存已清除")
                        except Exception as e:
                            logger.error(f"【{self.cookie_id}】清除Token缓存失败: {e}")
                    
                    # 检查是否超过最大失败次数
                    if self.connection_manager.connection_failures >= self.connection_manager.max_connection_failures:
                        logger.error(f"【{self.cookie_id}】认证相关连续失败{self.connection_manager.max_connection_failures}次")
                        
                        # 尝试密码登录刷新
                        # try_password_login_refresh 的返回值契约（与 cookie_token_manager.py 内部
                        # 递归调用、internal.py 中 API 调用保持一致）：
                        #   True              → 密码登录成功 + Cookie 已更新 + 实例已重启
                        #   "no_credentials"  → 未配置用户名/密码，无法自动刷新
                        #   "skipped_cooldown"→ 命中密码登录冷却期 / 账密错误冷却期，跳过本次
                        #   False / 其他      → 真实失败（账号信息缺失、密码错误、Cookie 更新失败等）
                        # 注意：以前误用 `result == "success"` 判定成功，导致 True 永远不命中，
                        # 即使登录成功也会错误打印"密码登录失败"并漏掉连接失败计数归零。
                        try:
                            logger.info(f"【{self.cookie_id}】尝试通过密码登录刷新Cookie")
                            if self._cookie_token_manager:
                                result = await self._cookie_token_manager.try_password_login_refresh("认证失败5次")
                                if result is True:
                                    logger.info(f"【{self.cookie_id}】密码登录成功，重置失败计数")
                                    self.connection_manager.connection_failures = 0
                                    self.connection_manager.network_failures = 0
                                    continue
                                elif result == "no_credentials":
                                    logger.warning(f"【{self.cookie_id}】未配置密码，无法自动登录")
                                elif result == "skipped_cooldown":
                                    logger.warning(f"【{self.cookie_id}】密码登录冷却期内，跳过本次刷新")
                                else:
                                    logger.error(f"【{self.cookie_id}】密码登录失败")
                            else:
                                logger.warning(f"【{self.cookie_id}】CookieTokenManager未初始化")
                        except Exception as e:
                            logger.error(f"【{self.cookie_id}】密码登录异常: {e}")
                        
                        break
                    
                    # 计算重试延迟
                    retry_delay = self.connection_manager.calculate_retry_delay(error_msg)
                    logger.warning(f"【{self.cookie_id}】将在 {retry_delay} 秒后重试...")
                    
                    # 清空token（内存）
                    if self.current_token:
                        self.current_token = None
                    
                    # 等待后重试
                    await self._interruptible_sleep(retry_delay)
                    logger.info(f"【{self.cookie_id}】开始新一轮连接尝试...")
                    continue
        
        finally:
            # 更新连接状态
            self.connection_manager.set_connection_state(ConnectionState.CLOSED, "程序退出")
            
            # 清理后台任务
            logger.info(f"【{self.cookie_id}】清理后台任务...")
            await self._cancel_background_tasks()
            
            # 关闭session
            await self.close_session()
            
            # 注销实例
            self._unregister_instance()
            logger.info(f"【{self.cookie_id}】XianyuAsync主程序已完全退出")


if __name__ == '__main__':
    cookies_str = os.getenv('COOKIES_STR')
    xianyu = XianyuAsync(cookies_str)
    asyncio.run(xianyu.main())
