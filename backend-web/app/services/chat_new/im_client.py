"""
闲鱼IM WebSocket客户端

功能：
1. 通过mtop API获取IM登录Token
2. 建立WebSocket连接并注册
3. 获取会话列表 (/r/Conversation/listNewestPagination)
4. 获取聊天记录 (/r/MessageManager/listUserMessages)
5. 心跳保活与自动ACK

参照 goofish-client 和 XianYuApis-master 实现
"""
import asyncio
import base64
import json
import random
import time
from datetime import timedelta
from typing import Any, Dict, List, Optional

import aiohttp
from loguru import logger
from sqlalchemy import text

from common.db.session import async_session_maker
from common.utils.time_utils import get_beijing_now_naive
from common.utils.xianyu_utils import (
    generate_device_id,
    generate_mid,
    generate_sign,
    generate_uuid,
    trans_cookies,
)


# WebSocket连接地址
WS_URL = "wss://wss-goofish.dingtalk.com/"
# IM Token获取地址
TOKEN_API_URL = "https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/"
# 请求超时（秒）
REQUEST_TIMEOUT = 20
# 心跳间隔（秒）
HEARTBEAT_INTERVAL = 15


class GoofishImClient:
    """闲鱼IM WebSocket客户端，用于获取会话列表和聊天记录"""

    def __init__(self, account_id: str, cookies_str: str):
        """
        初始化IM客户端

        Args:
            account_id: 账号ID（数据库account_id）
            cookies_str: Cookie字符串
        """
        self.account_id = account_id
        self.cookies_str = cookies_str
        self.cookies: Dict[str, str] = trans_cookies(cookies_str)
        self.myid: str = self.cookies.get("unb", "")
        self.device_id: str = generate_device_id(self.myid)
        self.token: str = ""

        # WebSocket相关
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._connected: bool = False
        self._registered: bool = False

        # 请求-响应配对
        self._pending: Dict[str, asyncio.Future] = {}
        # 后台任务
        self._recv_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

        # 推送消息回调列表（用于向前端 WebSocket 转发实时消息）
        self._push_callbacks: List = []

    # ==================== 连接管理 ====================

    async def connect(self) -> bool:
        """
        建立连接：获取Token -> 连接WebSocket -> 注册

        Returns:
            是否连接成功
        """
        try:
            # 1. 获取IM Token
            self.token = await self._get_im_token()
            if not self.token:
                logger.error(f"【{self.account_id}】获取IM Token失败")
                return False
            logger.info(f"【{self.account_id}】获取IM Token成功")

            # 2. 建立WebSocket连接
            headers = {
                "Cookie": self.cookies_str,
                "Host": "wss-goofish.dingtalk.com",
                "Connection": "Upgrade",
                "Pragma": "no-cache",
                "Cache-Control": "no-cache",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/146.0.0.0 Safari/537.36"
                ),
                "Origin": "https://www.goofish.com",
                "Accept-Encoding": "gzip, deflate, br, zstd",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
            self._session = aiohttp.ClientSession()
            # 超时策略（应对 wss:// 网络抖动）：
            # - total=None:      WebSocket 是长连接，原 total=30 会强制 30 秒后断开整个会话
            # - connect=30:      TCP + SSL/TLS 握手 + 连接池等待的超时（关键！wss 的 TLS 握手由此覆盖）
            # - sock_connect=30: 仅 TCP 三次握手超时（不含 TLS，作为 connect 的兜底）
            # - sock_read=None:  持久 WebSocket 不应有读超时（消息间隔可能很长）
            # - heartbeat=30:    aiohttp 库自身 PING 帧间隔 30 秒（与应用层心跳互补）
            self._ws = await self._session.ws_connect(
                WS_URL,
                headers=headers,
                heartbeat=30,
                timeout=aiohttp.ClientTimeout(
                    total=None,
                    connect=30,
                    sock_connect=30,
                    sock_read=None,
                ),
            )
            self._connected = True
            logger.info(f"【{self.account_id}】WebSocket连接成功")

            # 3. 启动消息接收循环
            self._recv_task = asyncio.create_task(self._recv_loop())

            # 4. 注册
            await self._register()
            self._registered = True
            logger.info(f"【{self.account_id}】IM注册成功")

            # 5. 注册后冷却（防止立即请求触发IM流控 400600001）
            await asyncio.sleep(3)

            # 6. 启动心跳
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            return True

        except Exception as e:
            logger.error(f"【{self.account_id}】IM连接失败: {e}")
            await self.disconnect()
            return False

    async def disconnect(self):
        """断开连接，释放资源"""
        self._connected = False
        self._registered = False

        # 取消后台任务
        for task in [self._heartbeat_task, self._recv_task]:
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._heartbeat_task = None
        self._recv_task = None

        # 拒绝所有待处理请求
        for mid, future in self._pending.items():
            if not future.done():
                future.set_exception(Exception("连接已断开"))
        self._pending.clear()

        # 关闭WebSocket
        if self._ws and not self._ws.closed:
            try:
                await self._ws.close()
            except Exception:
                pass
        self._ws = None

        # 关闭HTTP会话
        if self._session and not self._session.closed:
            try:
                await self._session.close()
            except Exception:
                pass
        self._session = None

        logger.info(f"【{self.account_id}】IM连接已断开")

    @property
    def is_connected(self) -> bool:
        """是否已连接并注册"""
        return self._connected and self._registered

    # ==================== 业务接口 ====================

    async def get_conversations(
        self, start_timestamp: Optional[int] = None, limit: int = 20
    ) -> Dict[str, Any]:
        """
        获取会话列表（含流控自动重试）

        Args:
            start_timestamp: 开始时间戳，首页传None(使用MAX_SAFE_INTEGER)，翻页传nextCursor
            limit: 每页数量

        Returns:
            包含 hasMore, nextCursor, userConvs 的字典
        """
        if start_timestamp is None:
            start_timestamp = 9007199254740991  # Number.MAX_SAFE_INTEGER

        max_retries = 3
        for attempt in range(max_retries):
            mid = generate_mid()
            msg = {
                "lwp": "/r/Conversation/listNewestPagination",
                "headers": {"mid": mid},
                "body": [start_timestamp, limit],
            }
            response = await self._send_and_wait(mid, msg)
            body = response.get("body", {})

            # 检查是否被流控
            if isinstance(body, dict) and body.get("code") == "400600001":
                wait_sec = (attempt + 1) * 2
                logger.warning(
                    f"【{self.account_id}】会话列表被流控，"
                    f"{wait_sec}秒后重试（{attempt + 1}/{max_retries}）"
                )
                await asyncio.sleep(wait_sec)
                continue

            return body

        # 重试耗尽，返回最后一次结果
        return body

    async def get_messages(
        self,
        cid: str,
        start_timestamp: Optional[int] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """
        获取单个会话的聊天记录

        Args:
            cid: 会话ID（不含@goofish后缀）
            start_timestamp: 开始时间戳，首页传None，翻页传nextCursor
            limit: 每页数量

        Returns:
            包含 hasMore, nextCursor, userMessageModels 的字典
        """
        if start_timestamp is None:
            start_timestamp = 9007199254740991

        # 确保cid带@goofish后缀
        full_cid = cid if "@goofish" in cid else f"{cid}@goofish"

        mid = generate_mid()
        msg = {
            "lwp": "/r/MessageManager/listUserMessages",
            "headers": {"mid": mid},
            "body": [full_cid, False, start_timestamp, limit, False],
        }
        response = await self._send_and_wait(mid, msg)
        return response.get("body", {})

    async def send_text_message(
        self, cid: str, to_user_id: str, text: str
    ) -> Dict[str, Any]:
        """
        发送文本消息

        参照 XianYuApis-master/goofish_live.py 的 send_msg 实现

        Args:
            cid: 会话ID（不含@goofish后缀）
            to_user_id: 对方用户ID
            text: 消息文本

        Returns:
            IM服务器响应
        """
        full_cid = cid if "@goofish" in cid else f"{cid}@goofish"
        full_to = to_user_id if "@goofish" in to_user_id else f"{to_user_id}@goofish"
        full_self = f"{self.myid}@goofish"

        # 构造文本消息 payload
        payload = {"contentType": 1, "text": {"text": text}}
        data_b64 = base64.b64encode(
            json.dumps(payload).encode("utf-8")
        ).decode("utf-8")

        mid = generate_mid()
        message_uuid = generate_uuid()
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {"mid": mid},
            "body": [
                {
                    "uuid": message_uuid,
                    "cid": full_cid,
                    "conversationType": 1,
                    "content": {
                        "contentType": 101,
                        "custom": {"type": 1, "data": data_b64},
                    },
                    "redPointPolicy": 0,
                    "extension": {"extJson": "{}"},
                    "ctx": {"appVersion": "1.0", "platform": "web"},
                    "mtags": {},
                    "msgReadStatusSetting": 1,
                },
                {"actualReceivers": [full_to, full_self]},
            ],
        }
        response = await self._send_and_wait(mid, msg)
        # IM 服务端对违规内容会返回带 reason 的 body（如 CSI_FORBID 安全拦截），
        # 此时虽然响应携带 body 不会在 _send_and_wait 抛错，但消息实际未送达，
        # 需在此识别为发送失败并抛出明文原因，供上层反馈给前端。
        self._raise_if_send_rejected(response)
        # 解析服务端返回的 messageId，供消息撤回功能使用
        body = response.get("body", {})
        message_id = ""
        if isinstance(body, dict):
            raw_message_id = body.get("messageId") or body.get("1")
            if isinstance(raw_message_id, dict):
                raw_message_id = raw_message_id.get("messageId") or raw_message_id.get("1")
            if isinstance(raw_message_id, str):
                message_id = raw_message_id
        return {"response": response, "messageId": message_id, "uuid": message_uuid}

    async def send_image_message(
        self,
        cid: str,
        to_user_id: str,
        image_url: str,
        width: int = 800,
        height: int = 600,
    ) -> Dict[str, Any]:
        """
        发送图片消息

        与 send_text_message 协议一致，仅消息体内容为 contentType=2 的图片结构。
        图片必须是已上传到闲鱼CDN的可访问URL（通过 ImageUploader 上传得到）。

        Args:
            cid: 会话ID（不含@goofish后缀）
            to_user_id: 对方用户ID
            image_url: 闲鱼CDN图片URL
            width: 图片宽度（像素），用于前端按比例渲染
            height: 图片高度（像素）

        Returns:
            包含 response、messageId、uuid 的结果字典
        """
        full_cid = cid if "@goofish" in cid else f"{cid}@goofish"
        full_to = to_user_id if "@goofish" in to_user_id else f"{to_user_id}@goofish"
        full_self = f"{self.myid}@goofish"

        # 构造图片消息 payload（pics 数组格式，与官方协议一致）
        payload = {
            "contentType": 2,
            "image": {
                "pics": [
                    {
                        "height": int(height),
                        "type": 0,
                        "url": image_url,
                        "width": int(width),
                    }
                ]
            },
        }
        data_b64 = base64.b64encode(
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
        ).decode("utf-8")

        mid = generate_mid()
        message_uuid = generate_uuid()
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {"mid": mid},
            "body": [
                {
                    "uuid": message_uuid,
                    "cid": full_cid,
                    "conversationType": 1,
                    "content": {
                        "contentType": 101,
                        "custom": {"type": 1, "data": data_b64},
                    },
                    "redPointPolicy": 0,
                    "extension": {"extJson": "{}"},
                    "ctx": {"appVersion": "1.0", "platform": "web"},
                    "mtags": {},
                    "msgReadStatusSetting": 1,
                },
                {"actualReceivers": [full_to, full_self]},
            ],
        }
        response = await self._send_and_wait(mid, msg)
        # 与文本发送一致，识别安全拦截等业务错误并抛出明文原因
        self._raise_if_send_rejected(response)
        body = response.get("body", {})
        message_id = ""
        if isinstance(body, dict):
            raw_message_id = body.get("messageId") or body.get("1")
            if isinstance(raw_message_id, dict):
                raw_message_id = raw_message_id.get("messageId") or raw_message_id.get("1")
            if isinstance(raw_message_id, str):
                message_id = raw_message_id
        return {"response": response, "messageId": message_id, "uuid": message_uuid}

    async def recall_message(self, message_id: str) -> Dict[str, Any]:
        """通过闲鱼官方 IM 协议撤回一条消息"""
        mid = generate_mid()
        response = await self._send_and_wait(mid, {
            "lwp": "/r/MessageManager/recallMessage",
            "headers": {"mid": mid},
            "body": [message_id],
        })
        if response.get("code") != 200:
            body = response.get("body", {})
            reason = body.get("reason") if isinstance(body, dict) else ""
            raise RuntimeError(reason or "闲鱼未确认撤回成功")
        return response

    @staticmethod
    def _raise_if_send_rejected(response: Dict[str, Any]) -> None:
        """检查发送响应是否被 IM 服务端拒绝（如安全拦截），是则抛出明文原因

        Args:
            response: IM 服务器返回的完整响应

        Raises:
            Exception: 当响应 body 含 reason（业务错误）时抛出，message 为服务端原因文案
        """
        if not isinstance(response, dict):
            return
        body = response.get("body", {})
        if isinstance(body, dict) and body.get("reason"):
            reason = body.get("reason", "")
            more_info = body.get("moreInfo", "")
            # moreInfo 形如 "CSI_FORBID||安全拦截"，附在原因后便于定位拦截类型
            detail = f"{reason}（{more_info}）" if more_info else reason
            raise Exception(detail)

    # ==================== Token缓存（数据库） ====================
    # 缓存键使用 chat_{myid} 前缀，与自动回复WebSocket的缓存隔离，
    # 避免共用同一token/device_id导致IM服务器踢掉自动回复连接

    @property
    def _cache_user_id(self) -> str:
        """Token缓存键，加chat_前缀与自动回复隔离"""
        return f"chat_{self.myid}"

    async def _get_cached_token(self) -> Optional[Dict[str, str]]:
        """从数据库xy_token_cache获取缓存的token和device_id

        Returns:
            包含token和device_id的字典，不存在或已过期则返回None
        """
        try:
            async with async_session_maker() as session:
                result = await session.execute(
                    text("""
                        SELECT token, device_id, expire_at
                        FROM xy_token_cache
                        WHERE user_id = :user_id
                        LIMIT 1
                    """),
                    {"user_id": self._cache_user_id},
                )
                row = result.fetchone()

                if row:
                    token_val, device_id_val, expire_at = row
                    now = get_beijing_now_naive()
                    if expire_at and expire_at > now:
                        remaining = expire_at - now
                        hours = int(remaining.total_seconds() // 3600)
                        minutes = int((remaining.total_seconds() % 3600) // 60)
                        logger.info(
                            f"【{self.account_id}】Token缓存命中: "
                            f"user_id={self.myid}, "
                            f"剩余有效时间={hours}小时{minutes}分钟"
                        )
                        return {"token": token_val, "device_id": device_id_val}
                    else:
                        logger.info(
                            f"【{self.account_id}】Token缓存已过期: "
                            f"user_id={self.myid}, 过期时间={expire_at}"
                        )
                        await self._delete_cached_token()
                else:
                    logger.info(
                        f"【{self.account_id}】Token缓存未命中: "
                        f"cache_key={self._cache_user_id}"
                    )
        except Exception as e:
            logger.warning(f"【{self.account_id}】获取Token缓存失败: {e}")
        return None

    async def _set_cached_token(self, token_val: str, device_id_val: str):
        """将token和device_id缓存到数据库

        使用 INSERT ... ON DUPLICATE KEY UPDATE 实现插入或更新
        过期时间为当前时间 + 8~10小时随机

        Args:
            token_val: IM Token
            device_id_val: 设备ID
        """
        try:
            ttl_hours = random.uniform(8, 10)
            expire_at = get_beijing_now_naive() + timedelta(hours=ttl_hours)

            async with async_session_maker() as session:
                await session.execute(
                    text("""
                        INSERT INTO xy_token_cache
                            (user_id, token, device_id, expire_at, created_at, updated_at)
                        VALUES
                            (:user_id, :token, :device_id, :expire_at, NOW(), NOW())
                        ON DUPLICATE KEY UPDATE
                            token = VALUES(token),
                            device_id = VALUES(device_id),
                            expire_at = VALUES(expire_at),
                            updated_at = NOW()
                    """),
                    {
                        "user_id": self._cache_user_id,
                        "token": token_val,
                        "device_id": device_id_val,
                        "expire_at": expire_at,
                    },
                )
                await session.commit()
                logger.info(
                    f"【{self.account_id}】Token已缓存到数据库 "
                    f"(过期时间={expire_at.strftime('%Y-%m-%d %H:%M:%S')}, "
                    f"TTL={ttl_hours:.1f}小时)"
                )
        except Exception as e:
            logger.warning(f"【{self.account_id}】缓存Token到数据库失败: {e}")

    async def _delete_cached_token(self):
        """删除数据库中缓存的token"""
        try:
            async with async_session_maker() as session:
                await session.execute(
                    text(
                        "DELETE FROM xy_token_cache WHERE user_id = :user_id"
                    ),
                    {"user_id": self._cache_user_id},
                )
                await session.commit()
                logger.info(
                    f"【{self.account_id}】已清除Token缓存: "
                    f"cache_key={self._cache_user_id}"
                )
        except Exception as e:
            logger.warning(f"【{self.account_id}】清除Token缓存失败: {e}")

    # ==================== 内部方法 ====================

    async def _get_im_token(self) -> str:
        """获取IM Token，优先从数据库缓存获取，缓存未命中再调mtop API"""
        # 1. 先从数据库缓存获取
        cached = await self._get_cached_token()
        if cached:
            # 恢复缓存中的device_id，保持一致
            self.device_id = cached["device_id"]
            logger.info(
                f"【{self.account_id}】使用数据库缓存的Token和Device ID"
            )
            return cached["token"]

        # 2. 缓存未命中，调API获取
        token = await self._fetch_im_token_from_api()
        if token:
            # 存入数据库缓存
            await self._set_cached_token(token, self.device_id)
        return token

    async def _fetch_im_token_from_api(self, _retry: int = 0) -> str:
        """
        通过mtop API获取IM登录Token

        令牌过期时会从响应Set-Cookie中提取新Cookie，增量合并后更新到数据库和内存，
        然后使用新Cookie重试一次（最多重试1次，防止无限递归）。

        Args:
            _retry: 内部重试计数，外部不需要传
        """
        from common.utils.cookie_refresh import (
            extract_cookies_from_response,
            merge_cookies,
            update_account_cookies_in_db,
        )

        try:
            timestamp = str(int(time.time() * 1000))
            data_val = json.dumps(
                {
                    "appKey": "444e9908a51d1cb236a27862abc769c9",
                    "deviceId": self.device_id,
                },
                separators=(",", ":"),
            )

            token_part = self.cookies.get("_m_h5_tk", "").split("_")[0]
            sign = generate_sign(timestamp, token_part, data_val)

            params = {
                "jsv": "2.7.2",
                "appKey": "34839810",
                "t": timestamp,
                "sign": sign,
                "v": "1.0",
                "type": "originaljson",
                "accountSite": "xianyu",
                "dataType": "json",
                "timeout": "20000",
                "api": "mtop.taobao.idlemessage.pc.login.token",
                "sessionOption": "AutoLoginOnly",
                "spm_cnt": "a21ybx.im.0.0",
                "spm_pre": "a21ybx.home.sidebar.1.4c053da6vYwnmf",
                "log_id": "4c053da6vYwnmf",
            }

            headers = {
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
                "cookie": self.cookies_str,
                "referer": "https://www.goofish.com/",
                "origin": "https://www.goofish.com",
                "user-agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/146.0.0.0 Safari/537.36"
                ),
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    TOKEN_API_URL,
                    params=params,
                    data={"data": data_val},
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as resp:
                    result = await resp.json(content_type=None)

                    # ---- 先提取响应中的 Set-Cookie 增量更新 ----
                    new_cookies = extract_cookies_from_response(resp)
                    if new_cookies:
                        merged_str = merge_cookies(self.cookies_str, new_cookies)
                        self.cookies_str = merged_str
                        self.cookies = trans_cookies(merged_str)
                        await update_account_cookies_in_db(self.account_id, merged_str)
                        logger.info(
                            f"【{self.account_id}】已从Set-Cookie合并 {len(new_cookies)} 个Cookie字段并更新到数据库"
                        )

            # 检查令牌过期，使用新Cookie重试（最多1次）
            ret = result.get("ret", [])
            ret_str = str(ret)
            if ("令牌过期" in ret_str or "FAIL_SYS_TOKEN_EXOIRED" in ret_str
                    or "FAIL_SYS_TOKEN_EXPIRED" in ret_str):
                if _retry < 1:
                    logger.warning(
                        f"【{self.account_id}】令牌过期，已更新Cookie，准备重试获取Token（第{_retry + 1}次）"
                    )
                    return await self._fetch_im_token_from_api(_retry=_retry + 1)
                else:
                    logger.error(f"【{self.account_id}】令牌过期重试已达上限，放弃获取Token")
                    return ""

            access_token = result.get("data", {}).get("accessToken", "")
            if not access_token:
                logger.error(
                    f"【{self.account_id}】Token响应异常: "
                    f"{json.dumps(result, ensure_ascii=False)[:300]}"
                )
            return access_token

        except Exception as e:
            logger.error(f"【{self.account_id}】获取IM Token异常: {e}")
            return ""

    async def _register(self):
        """发送注册消息 (/reg) 并等待服务器确认，然后发送 ackDiff"""
        # 发送 /reg 并等待响应
        reg_mid = generate_mid()
        reg_msg = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": "444e9908a51d1cb236a27862abc769c9",
                "token": self.token,
                "ua": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/146.0.0.0 Safari/537.36 "
                    "DingTalk(2.1.5) OS(Windows/10) "
                    "Browser(Chrome/146.0.0.0) DingWeb/2.1.5 "
                    "IMPaaS DingWeb/2.1.5"
                ),
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self.device_id,
                "mid": reg_mid,
            },
        }

        try:
            reg_response = await self._send_and_wait(reg_mid, reg_msg, timeout=5)
            reg_code = reg_response.get("code", 0)
            logger.info(
                f"【{self.account_id}】注册响应: code={reg_code}, "
                f"body={json.dumps(reg_response.get('body', {}), ensure_ascii=False)[:200]}"
            )
            if reg_code != 200:
                logger.warning(f"【{self.account_id}】注册返回非200: {reg_code}")
        except Exception as e:
            logger.warning(f"【{self.account_id}】等待注册响应异常: {e}，继续尝试")

        # 发送 ackDiff
        current_time = int(time.time() * 1000)
        ack_mid = generate_mid()
        ack_msg = {
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": ack_mid},
            "body": [
                {
                    "pipeline": "sync",
                    "tooLong2Tag": "PNM,1",
                    "channel": "sync",
                    "topic": "sync",
                    "highPts": 0,
                    "pts": current_time * 1000,
                    "seq": 0,
                    "timestamp": current_time,
                }
            ],
        }
        await self._send_raw(ack_msg)

        # 等待同步完成
        await asyncio.sleep(1)

    async def _send_raw(self, msg: dict):
        """直接发送消息（不等待响应）"""
        if not self._ws or self._ws.closed:
            raise Exception("WebSocket未连接")
        await self._ws.send_json(msg)

    async def _send_and_wait(
        self, mid: str, msg: dict, timeout: float = REQUEST_TIMEOUT
    ) -> dict:
        """
        发送消息并等待匹配mid的响应

        Args:
            mid: 消息ID
            msg: 消息内容
            timeout: 超时秒数

        Returns:
            响应消息字典
        """
        if not self._ws or self._ws.closed:
            raise Exception("WebSocket未连接")

        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[mid] = future

        try:
            await self._ws.send_json(msg)
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise Exception(f"请求超时: {msg.get('lwp', 'unknown')}")
        finally:
            self._pending.pop(mid, None)

    async def _recv_loop(self):
        """后台消息接收循环"""
        try:
            async for ws_msg in self._ws:
                if ws_msg.type == aiohttp.WSMsgType.TEXT:
                    await self._handle_message(ws_msg.data)
                elif ws_msg.type in (
                    aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    logger.warning(
                        f"【{self.account_id}】WebSocket连接异常关闭"
                    )
                    self._connected = False
                    break
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"【{self.account_id}】消息接收异常: {e}")
            self._connected = False

    def add_push_callback(self, callback):
        """注册推送消息回调（用于向前端转发实时消息）

        Args:
            callback: 异步回调函数，接收解析后的推送消息 dict
        """
        if callback not in self._push_callbacks:
            self._push_callbacks.append(callback)

    def remove_push_callback(self, callback):
        """注销推送消息回调"""
        if callback in self._push_callbacks:
            self._push_callbacks.remove(callback)

    async def _handle_message(self, data: str):
        """处理收到的WebSocket消息"""
        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            return

        # 发送ACK
        headers = message.get("headers", {})
        mid = headers.get("mid", generate_mid())
        ack = {
            "code": 200,
            "headers": {
                "mid": mid,
                "sid": headers.get("sid", ""),
            },
        }
        # 复制需要回传的header字段
        for key in ("app-key", "ua", "dt"):
            if key in headers:
                ack["headers"][key] = headers[key]

        try:
            await self._send_raw(ack)
        except Exception:
            pass

        # 匹配等待中的请求
        # 注意：IM数据响应通常没有code字段，匹配到mid就直接resolve
        if mid in self._pending:
            future = self._pending[mid]
            if not future.done():
                code = message.get("code", 200)
                body = message.get("body", {})
                # 记录错误响应的完整内容
                if isinstance(body, dict) and "reason" in body:
                    logger.warning(
                        f"【{self.account_id}】IM请求响应含错误, "
                        f"code={code}, body={json.dumps(body, ensure_ascii=False)[:300]}"
                    )
                if code == 200 or "body" in message:
                    future.set_result(message)
                else:
                    future.set_exception(
                        Exception(
                            f"请求失败: code={code}, "
                            f"msg={json.dumps(message, ensure_ascii=False)[:200]}"
                        )
                    )
            return

        # 非请求响应 —— 服务器主动推送的消息，解密并记录日志
        await self._handle_push_message(message)

    async def _handle_push_message(self, message: dict):
        """
        处理服务器主动推送的消息

        参照自动回复 message_handler.py 的解密和解析逻辑：
        1. 检查是否为 syncPushPackage（同步推送包）
        2. 解密每条消息（base64 -> JSON 或 decrypt）
        3. 解析聊天消息内容并打印完整日志
        4. 触发已注册的回调，将解析后的消息推送给前端
        """
        try:
            body = message.get("body", {})
            sync_pkg = body.get("syncPushPackage") if isinstance(body, dict) else None
            if not sync_pkg:
                return
            data_list = sync_pkg.get("data", [])
            if not data_list:
                return

            # 延迟初始化解析器
            if not hasattr(self, "_push_parser"):
                from .push_message_parser import PushMessageParser
                self._push_parser = PushMessageParser(self.account_id, self.myid)

            for sync_data in data_list:
                if not isinstance(sync_data, dict) or "data" not in sync_data:
                    continue
                decrypted = self._push_parser.decrypt_push_data(sync_data["data"])
                if decrypted is None:
                    continue
                parsed = self._push_parser.parse(decrypted)
                if parsed is None:
                    continue
                for cb in self._push_callbacks:
                    try:
                        await cb(parsed)
                    except Exception as cb_e:
                        logger.warning(f"【{self.account_id}】推送回调异常: {cb_e}")
        except Exception as e:
            logger.warning(f"【{self.account_id}】处理推送消息异常: {e}")

    async def _heartbeat_loop(self):
        """心跳保活循环"""
        try:
            while self._connected:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
                if not self._connected or not self._ws or self._ws.closed:
                    break
                try:
                    heartbeat = {
                        "lwp": "/!",
                        "headers": {"mid": generate_mid()},
                    }
                    await self._send_raw(heartbeat)
                except Exception as e:
                    logger.warning(
                        f"【{self.account_id}】心跳发送失败: {e}"
                    )
                    break
        except asyncio.CancelledError:
            pass
