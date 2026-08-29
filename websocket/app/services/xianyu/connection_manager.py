"""
WebSocket连接管理模块

功能:
1. WebSocket连接建立和维护
2. 心跳循环
3. 连接状态管理
4. 重连逻辑
"""
import asyncio
import inspect
import json
import random
import time
import websockets
from enum import Enum
from loguru import logger


class ConnectionState(Enum):
    """WebSocket连接状态枚举"""
    DISCONNECTED = "disconnected"  # 未连接
    CONNECTING = "connecting"  # 连接中
    CONNECTED = "connected"  # 已连接
    RECONNECTING = "reconnecting"  # 重连中
    FAILED = "failed"  # 连接失败
    CLOSED = "closed"  # 已关闭


class ConnectionManager:
    """WebSocket连接管理器"""
    
    def __init__(self, xianyu_instance):
        """
        初始化连接管理器
        
        Args:
            xianyu_instance: XianyuAsync实例的引用
        """
        self.xianyu = xianyu_instance
        self.cookie_id = xianyu_instance.cookie_id
        
        # 连接状态
        self.connection_state = ConnectionState.DISCONNECTED
        self.connection_failures = 0  # 认证/Token相关失败计数
        self.max_connection_failures = 5  # 认证失败阈值
        self.network_failures = 0  # 纯网络错误计数（如ConnectionClosedError）
        self.max_network_failures = 20  # 网络错误阈值（更宽松）
        self.last_successful_connection = 0
        self.last_state_change_time = time.time()
        
        # 短连接频繁断开检测（连接维持少于30秒视为短连接）
        self.short_disconnect_times: list = []  # 记录短连接断开的时间戳
        self.short_connection_threshold = 30  # 短连接阈值（秒）
        self.frequent_disconnect_window = 300  # 频繁断开检测窗口（5分钟）
        self.frequent_disconnect_limit = 5  # 频繁断开次数限制
        
        # 心跳配置
        self.heartbeat_interval = xianyu_instance.heartbeat_interval
        self.heartbeat_timeout = xianyu_instance.heartbeat_timeout
        self.last_heartbeat_time = 0
        self.last_heartbeat_response = 0
        
        # WebSocket连接
        self.ws = None
    
    def set_connection_state(self, new_state: ConnectionState, reason: str = ""):
        """
        设置连接状态并记录日志
        
        Args:
            new_state: 新的连接状态
            reason: 状态变更原因
        """
        if self.connection_state != new_state:
            old_state = self.connection_state
            self.connection_state = new_state
            self.last_state_change_time = time.time()
            
            # 记录状态转换
            state_msg = f"【{self.cookie_id}】连接状态: {old_state.value} → {new_state.value}"
            if reason:
                state_msg += f" ({reason})"
            
            # 根据状态严重程度选择日志级别
            if new_state == ConnectionState.FAILED:
                logger.error(state_msg)
            elif new_state == ConnectionState.RECONNECTING:
                logger.warning(state_msg)
            elif new_state == ConnectionState.CONNECTED:
                logger.success(state_msg)
            else:
                logger.info(state_msg)
    
    def record_short_disconnect(self, connected_duration: float) -> bool:
        """
        记录短连接断开，检测是否频繁断开
        
        Args:
            connected_duration: 本次连接维持的时间（秒）
            
        Returns:
            True 如果检测到频繁断开需要禁用账号，False 否则
        """
        # 只记录短连接（维持时间少于阈值）
        if connected_duration >= self.short_connection_threshold:
            # 长连接，清空短连接记录
            self.short_disconnect_times.clear()
            return False
        
        current_time = time.time()
        self.short_disconnect_times.append(current_time)
        
        # 清理超出时间窗口的记录
        window_start = current_time - self.frequent_disconnect_window
        self.short_disconnect_times = [t for t in self.short_disconnect_times if t >= window_start]
        
        # 记录当前短连接计数
        logger.warning(f"【{self.cookie_id}】短连接断开记录: 本次连接{connected_duration:.1f}秒, 累计{len(self.short_disconnect_times)}次/{self.frequent_disconnect_limit}次阈值")
        
        # 检查是否超过频繁断开限制
        if len(self.short_disconnect_times) >= self.frequent_disconnect_limit:
            logger.warning(f"【{self.cookie_id}】检测到频繁短连接断开: {len(self.short_disconnect_times)}次/{self.frequent_disconnect_window}秒")
            return True
        
        return False
    
    @staticmethod
    def is_ws_closed(ws) -> bool:
        """
        判断 WebSocket 连接是否已关闭（兼容 websockets 旧版与新版实现）

        websockets 14.0 起 connect() 默认返回新版 asyncio 实现的 ClientConnection，
        它没有旧版 WebSocketClientProtocol 的 .closed / .open 属性，改为暴露
        .state（State 枚举：CONNECTING / OPEN / CLOSING / CLOSED）。
        直接访问 ws.closed 会抛 AttributeError，被心跳循环当成发送失败，
        导致心跳连续失败 3 次后停止、连接被误判为断开。

        Args:
            ws: WebSocket 连接对象（旧版 protocol 或新版 ClientConnection）
        Returns:
            True 表示连接已关闭/正在关闭，False 表示仍可用
        """
        # 旧版（websockets <= 13）：直接使用 .closed 属性，保持原有语义
        closed = getattr(ws, 'closed', None)
        if isinstance(closed, bool):
            return closed

        # 新版（websockets >= 14）：通过 .state 判断，CLOSING/CLOSED 均视为不可用
        state = getattr(ws, 'state', None)
        if state is not None:
            return getattr(state, 'name', '') in ('CLOSING', 'CLOSED')

        # 两者都取不到时不阻断发送，交由实际 send 抛错处理
        return False

    def _resolve_header_kwarg_name(self, websockets_version: str) -> str:
        """
        根据 websockets 库版本选择连接时传递请求头的关键字参数名

        websockets 14.0 起 extra_headers 更名为 additional_headers。优先内省
        connect() 的函数签名判断（最可靠，不受版本号格式影响），无法内省时再
        回退到主版本号判断。

        Args:
            websockets_version: 已获取的 websockets 版本号字符串
        Returns:
            'additional_headers'（websockets >= 14）或 'extra_headers'（旧版）
        """
        # 优先内省 connect 签名：新版显式声明 additional_headers 参数，旧版为 extra_headers
        try:
            params = inspect.signature(websockets.connect).parameters
            if 'additional_headers' in params:
                return 'additional_headers'
            if 'extra_headers' in params:
                return 'extra_headers'
        except (ValueError, TypeError):
            pass

        # 无法内省时按主版本号判断（14.0 起使用 additional_headers）
        try:
            major = int(str(websockets_version).split('.')[0])
        except (ValueError, TypeError, IndexError):
            major = 0
        return 'additional_headers' if major >= 14 else 'extra_headers'

    async def create_websocket_connection(self, headers: dict):
        """
        创建WebSocket连接,兼容不同版本的websockets库,支持代理配置
        
        Args:
            headers: WebSocket连接头
            
        Returns:
            WebSocket连接上下文管理器
        
        超时与心跳策略（应对不稳定网络）：
        - open_timeout=30: 握手超时延长到 30 秒（默认 10 秒太短，TLS 握手在网络抖动时
          可能耗时 5-15 秒，10 秒会被错误地判定为 Token 失效，触发不必要的密码登录+
          人脸验证。日志中"连接失败(尝试10.0秒): TimeoutError"即为此问题。）
        - ping_interval=20: WebSocket 库每 20 秒发送底层 PING 帧（与应用层 heartbeat
          互补，更早检测半开连接）
        - ping_timeout=15: PING 帧响应超时 15 秒，避免在抖动时频繁误断
        """
        # 获取websockets版本用于调试
        websockets_version = getattr(websockets, '__version__', '未知')
        logger.info(f"【{self.cookie_id}】websockets库版本: {websockets_version}")

        # 统一的超时和心跳参数（所有 connect 调用路径都需带上）
        # 注意：这些参数 websockets >= 9.0 都支持，向下兼容到旧版本是安全的
        timeout_kwargs = {
            'open_timeout': 30,      # 握手超时（默认 10 秒太短，应对网络抖动）
            'ping_interval': 20,     # 库自身心跳间隔（与应用层 heartbeat 互补）
            'ping_timeout': 15,      # 库自身心跳响应超时
        }

        # 检查是否需要使用代理（与 HTTP 出站共用同一代理配置，确保账号 IP 一致）
        proxy_url = self.xianyu._get_proxy_url()
        proxy_sock = None
        
        if proxy_url:
            proxy_type = self.xianyu.proxy_config.get('proxy_type', 'none')
            logger.info(f"【{self.cookie_id}】WebSocket将通过代理连接: {proxy_type}://{self.xianyu.proxy_config.get('proxy_host')}:{self.xianyu.proxy_config.get('proxy_port')}")
            
            try:
                # 使用非v2 API，proxy.connect()返回标准Python socket（非阻塞模式）
                # 可以直接传给websockets.connect(sock=...)，SSL由websockets自动处理
                from python_socks.async_.asyncio import Proxy
                from python_socks import ProxyType as SocksProxyType
                
                # 确定代理类型
                if proxy_type == 'socks5':
                    socks_type = SocksProxyType.SOCKS5
                elif proxy_type == 'socks4':
                    socks_type = SocksProxyType.SOCKS4
                elif proxy_type in ['http', 'https']:
                    socks_type = SocksProxyType.HTTP
                else:
                    socks_type = None
                
                if socks_type:
                    # 解析WebSocket URL获取目标主机和端口
                    import urllib.parse
                    parsed_url = urllib.parse.urlparse(self.xianyu.base_url)
                    dest_host = parsed_url.hostname
                    dest_port = parsed_url.port or (443 if parsed_url.scheme == 'wss' else 80)
                    
                    # 创建代理连接
                    proxy = Proxy(
                        proxy_type=socks_type,
                        host=self.xianyu.proxy_config.get('proxy_host'),
                        port=self.xianyu.proxy_config.get('proxy_port'),
                        username=self.xianyu.proxy_config.get('proxy_user') or None,
                        password=self.xianyu.proxy_config.get('proxy_pass') or None
                    )
                    
                    # 通过代理连接到目标服务器（返回标准socket，SSL由websockets处理）
                    proxy_sock = await proxy.connect(
                        dest_host=dest_host,
                        dest_port=dest_port
                    )
                    
                    logger.info(f"【{self.cookie_id}】代理连接建立成功")
                    
            except ImportError:
                logger.warning(f"【{self.cookie_id}】代理连接需要安装 python-socks: pip install python-socks[asyncio]")
                logger.warning(f"【{self.cookie_id}】将尝试不使用代理进行WebSocket连接")
                proxy_sock = None
            except Exception as e:
                logger.error(f"【{self.cookie_id}】通过代理建立连接失败: {str(e)}")
                logger.warning(f"【{self.cookie_id}】将尝试不使用代理进行WebSocket连接")
                proxy_sock = None

        # 选择正确的请求头参数名（关键修复）
        # ──────────────────────────────────────────────────────────────
        # websockets 14.0 起，connect() 的 extra_headers 参数更名为 additional_headers。
        # 更关键的是：新版 connect() 是惰性的，非法关键字参数不会在 connect() 调用时报错，
        # 而是被透传给 loop.create_connection()，直到外层 await 连接时才抛出：
        #   "BaseEventLoop.create_connection() got an unexpected keyword argument 'extra_headers'"
        # 因此原先"先试 extra_headers、报错再回退 additional_headers"的 try/except 完全无效
        # （connect() 不抛错，异常在外层 await 处才出现），必须在调用前就选对参数名。
        header_kwarg = self._resolve_header_kwarg_name(websockets_version)
        logger.info(f"【{self.cookie_id}】WebSocket 请求头参数使用: {header_kwarg}")

        connect_kwargs = {
            header_kwarg: headers,
            **timeout_kwargs,
        }
        if proxy_sock:
            connect_kwargs['sock'] = proxy_sock

        return websockets.connect(self.xianyu.base_url, **connect_kwargs)
    
    async def send_heartbeat(self, ws):
        """
        发送心跳包
        
        Args:
            ws: WebSocket连接
        """
        if self.is_ws_closed(ws):
            raise ConnectionError("WebSocket连接已关闭,无法发送心跳")
        
        from common.utils.xianyu_utils import generate_mid
        
        msg = {
            "lwp": "/!",
            "headers": {
                "mid": generate_mid()
            }
        }
        try:
            await asyncio.wait_for(ws.send(json.dumps(msg)), timeout=2.0)
            self.last_heartbeat_time = time.time()
        except asyncio.TimeoutError:
            raise ConnectionError("心跳发送超时,WebSocket可能已断开")
        except asyncio.CancelledError:
            raise
    
    async def heartbeat_loop(self, ws):
        """
        心跳循环
        
        Args:
            ws: WebSocket连接
        """
        consecutive_failures = 0
        max_failures = 3

        try:
            while True:
                try:
                    if self.is_ws_closed(ws):
                        logger.warning(f"【{self.cookie_id}】WebSocket连接已关闭,停止心跳循环")
                        break

                    await self.send_heartbeat(ws)
                    consecutive_failures = 0

                    await self.xianyu._interruptible_sleep(self.heartbeat_interval)

                except asyncio.CancelledError:
                    logger.info(f"【{self.cookie_id}】心跳循环收到取消信号,准备退出")
                    raise
                except Exception as e:
                    consecutive_failures += 1
                    logger.error(f"心跳发送失败 ({consecutive_failures}/{max_failures}): {str(e)}")

                    if consecutive_failures >= max_failures:
                        logger.error(f"【{self.cookie_id}】心跳连续失败{max_failures}次,停止心跳循环")
                        break

                    try:
                        await self.xianyu._interruptible_sleep(5)
                    except asyncio.CancelledError:
                        logger.info(f"【{self.cookie_id}】心跳循环在重试等待时收到取消信号,准备退出")
                        raise
        except asyncio.CancelledError:
            logger.info(f"【{self.cookie_id}】心跳循环已取消,正在退出...")
            raise
        finally:
            logger.info(f"【{self.cookie_id}】心跳循环已退出")
    
    def handle_heartbeat_response(self, message_data: dict) -> bool:
        """
        处理心跳响应
        
        Args:
            message_data: 消息数据
            
        Returns:
            是否为心跳响应
        """
        try:
            if "body" in message_data:
                return False
            if message_data.get("code") == 200:
                self.last_heartbeat_response = time.time()
                logger.info(f"【{self.cookie_id}】心跳响应正常")
                return True
        except Exception as e:
            logger.error(f"处理心跳响应出错: {str(e)}")
        return False
    
    def calculate_retry_delay(self, error_msg: str) -> float:
        """
        根据错误类型和失败次数计算重试延迟（指数退避 + 抖动）

        多账号场景下，纯线性公式会导致所有账号在同一时刻重连，
        触发"重连风暴"并冲击闲鱼后端。这里改为指数退避叠加 0~30%
        随机抖动，让多账号在同一原因故障时也能自然错开重连时间。

        Args:
            error_msg: 错误消息

        Returns:
            重试延迟(秒)
        """
        failures = max(1, self.connection_failures)

        # WebSocket意外断开 - 短退避，封顶 30 秒
        if "no close frame received or sent" in error_msg:
            base = min(2 ** failures, 30)
        # 网络连接问题 - 长退避，封顶 90 秒
        elif "Connection refused" in error_msg or "timeout" in error_msg.lower():
            base = min(2 * (2 ** failures), 90)
        # 其他未知错误 - 中等退避，封顶 45 秒
        else:
            base = min(2 ** failures, 45)

        # 加 0% ~ 30% 随机抖动，避免多账号同时重连
        jitter = random.uniform(0, base * 0.3)
        return round(base + jitter, 1)

    def calculate_network_retry_delay(self) -> float:
        """
        计算纯网络断开重连延迟（指数退避 + 抖动）

        用于连接已正常建立后被断开（如网络抖动、闲鱼 WebSocket 服务波动）
        的重试场景。多账号同时被断开时，抖动可避免群体同步重连。

        Returns:
            重试延迟(秒)
        """
        failures = max(1, self.network_failures)
        # 网络错误使用较温和的指数退避，封顶 60 秒
        base = min(2 + 2 ** failures, 60)
        # 加 0% ~ 30% 随机抖动，避免多账号同时重连
        jitter = random.uniform(0, base * 0.3)
        return round(base + jitter, 1)
