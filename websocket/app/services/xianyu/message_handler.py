"""
消息处理模块

负责解析和处理WebSocket接收到的消息
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from typing import Dict, Any, Optional, Callable

from loguru import logger

from .utils import safe_str
from common.utils.xianyu_utils import decrypt


class MessageHandler:
    """消息处理器
    
    负责：
    - 消息解析
    - 消息去重
    - 消息防抖
    - 消息分发
    """
    
    def __init__(self, cookie_id: str, myid: str = None):
        """初始化消息处理器
        
        Args:
            cookie_id: 账号ID
            myid: 用户ID（从cookies的unb字段获取），用于判断是否是自己发出的消息
        """
        self.cookie_id = cookie_id
        self.myid = myid or cookie_id  # 如果没有传入myid，使用cookie_id作为备选
        
        # 消息去重
        self.processed_message_ids: Dict[str, float] = {}
        self.processed_message_ids_lock = asyncio.Lock()
        self.processed_message_ids_max_size = 10000
        self.message_expire_time = self._load_message_expire_time()  # 从数据库加载
        
        # 消息防抖
        self.message_debounce_tasks: Dict[str, Dict] = {}
        self.message_debounce_delay = 3  # 秒
        self.message_debounce_lock = asyncio.Lock()
        
        # 消息处理回调
        self._on_chat_message: Optional[Callable] = None
        self._on_system_message: Optional[Callable] = None
        self._on_order_message: Optional[Callable] = None
        self._on_card_message: Optional[Callable] = None  # 卡片消息回调（小刀等）
        self._on_card_update_message: Optional[Callable] = None  # 卡片更新消息回调（付款状态变更等）
    
    def _load_message_expire_time(self) -> int:
        """从数据库加载当前账号的相同消息等待时间配置（参照旧框架）"""
        try:
            from common.db.compat import db_manager
            expire_time = db_manager.get_cookie_message_expire_time(self.cookie_id)
            if expire_time is not None and expire_time >= 60:
                logger.info(f"【{self.cookie_id}】加载消息等待时间配置: {expire_time}秒")
                return expire_time
            return 3600  # 默认1小时
        except Exception as e:
            logger.warning(f"【{self.cookie_id}】加载消息等待时间配置失败: {e}，使用默认值3600秒")
            return 3600
    
    def set_chat_message_handler(self, handler: Callable):
        """设置聊天消息处理回调"""
        self._on_chat_message = handler
    
    def set_system_message_handler(self, handler: Callable):
        """设置系统消息处理回调"""
        self._on_system_message = handler
    
    def set_order_message_handler(self, handler: Callable):
        """设置订单消息处理回调"""
        self._on_order_message = handler
    
    def set_card_message_handler(self, handler: Callable):
        """设置卡片消息处理回调（用于小刀等卡片消息）"""
        self._on_card_message = handler
    
    def set_card_update_message_handler(self, handler: Callable):
        """设置卡片更新消息处理回调（用于付款状态变更等）"""
        self._on_card_update_message = handler
    
    def is_card_update_message(self, message: dict) -> bool:
        """判断是否为卡片更新消息
        
        卡片更新消息的特征：message["1"]是字符串，message["4"]包含reminderContent
        这类消息用于通知付款状态变更等，需要提取订单信息并触发自动发货
        """
        try:
            return (
                isinstance(message, dict)
                and "1" in message
                and isinstance(message["1"], str)
                and "4" in message
                and isinstance(message["4"], dict)
                and "reminderContent" in message["4"]
            )
        except Exception:
            return False
    
    def is_system_tip_message(self, message: dict) -> bool:
        """判断是否为平台系统提示 / 营销活动类消息（如"队友喊你来打气"任务提醒）

        这类消息不是买卖双方的真实聊天，不应触发自动回复，也不写入消息日志。

        识别依据（唯一且最可靠的标记）：
            extJson 中 msgArg1 == "MsgTips"
            —— 这是闲鱼平台对"营销/运营提示类消息"的明确分类标记。

        为什么只用这一个条件（确保不误杀正常消息 / 发货消息）：
        - 正常文本、图片、卡片消息不属于该营销分类，不会带 msgArg1=="MsgTips"。
        - 交易类消息（[我已拍下，待付款]、[我已付款，等待你发货]、评价请求、
          确认收货等）是靠 reminderContent 文本识别并触发发货 / 评价流程的，
          它们同样不属于营销提示分类，不会带 msgArg1=="MsgTips"。
        - 不使用 message["1"]["6"]["1"]==101 判断：101 是"自定义消息类型"，
          正常卡片消息（小刀、评价、确认收货）也是 101，会误杀。
        - 不使用 contentType=="14" 判断：缺乏交易类消息的内容类型样本佐证，
          为避免任何潜在误杀，宁可放过个别提示消息，也不拦截真实业务消息。
        """
        try:
            if not isinstance(message, dict):
                return False
            inner = message.get("1")
            if not isinstance(inner, dict):
                return False
            meta = inner.get("10")
            if not isinstance(meta, dict):
                return False
            ext_json = meta.get("extJson", "")
            if not isinstance(ext_json, str) or not ext_json:
                return False
            try:
                ext = json.loads(ext_json)
            except (json.JSONDecodeError, TypeError):
                return False
            if isinstance(ext, dict) and ext.get("msgArg1") == "MsgTips":
                return True
        except Exception:
            return False
        return False

    def is_chat_message(self, message: dict) -> bool:
        """判断是否为用户聊天消息"""
        try:
            return (
                isinstance(message, dict)
                and "1" in message
                and isinstance(message["1"], dict)
                and "10" in message["1"]
                and isinstance(message["1"]["10"], dict)
                and "reminderContent" in message["1"]["10"]
            )
        except Exception:
            return False
    
    def is_sync_package(self, message_data: dict) -> bool:
        """判断是否为同步包消息"""
        try:
            return (
                isinstance(message_data, dict)
                and "body" in message_data
                and "syncPushPackage" in message_data["body"]
                and "data" in message_data["body"]["syncPushPackage"]
                and len(message_data["body"]["syncPushPackage"]["data"]) > 0
            )
        except Exception:
            return False
    
    def extract_message_id(self, message_data: dict) -> Optional[str]:
        """从消息数据中提取消息ID"""
        try:
            if isinstance(message_data, dict) and "1" in message_data:
                message_1 = message_data.get("1")
                if isinstance(message_1, dict) and "10" in message_1:
                    message_10 = message_1.get("10")
                    if isinstance(message_10, dict) and "bizTag" in message_10:
                        biz_tag = message_10.get("bizTag", "")
                        if isinstance(biz_tag, str):
                            try:
                                biz_tag_dict = json.loads(biz_tag)
                                if isinstance(biz_tag_dict, dict) and "messageId" in biz_tag_dict:
                                    return biz_tag_dict.get("messageId")
                            except (json.JSONDecodeError, TypeError):
                                pass
                        
                        if "extJson" in message_10:
                            ext_json = message_10.get("extJson", "")
                            if isinstance(ext_json, str):
                                try:
                                    ext_json_dict = json.loads(ext_json)
                                    if isinstance(ext_json_dict, dict) and "messageId" in ext_json_dict:
                                        return ext_json_dict.get("messageId")
                                except (json.JSONDecodeError, TypeError):
                                    pass
            # 卡片更新消息：消息ID在message["4"]中
            if isinstance(message_data, dict) and "4" in message_data:
                message_4 = message_data.get("4")
                if isinstance(message_4, dict):
                    ext_json = message_4.get("extJson", "")
                    if isinstance(ext_json, str):
                        try:
                            ext_json_dict = json.loads(ext_json)
                            if isinstance(ext_json_dict, dict) and "messageId" in ext_json_dict:
                                return ext_json_dict.get("messageId")
                        except (json.JSONDecodeError, TypeError):
                            pass
        except Exception as e:
            logger.debug(f"【{self.cookie_id}】提取消息ID失败: {safe_str(e)}")
        
        return None
    
    async def is_message_processed(self, message_id: str) -> bool:
        """检查消息是否已处理"""
        async with self.processed_message_ids_lock:
            current_time = time.time()
            
            if message_id in self.processed_message_ids:
                last_process_time = self.processed_message_ids[message_id]
                time_elapsed = current_time - last_process_time
                
                if time_elapsed < self.message_expire_time:
                    return True
            
            return False
    
    async def mark_message_processed(self, message_id: str):
        """标记消息为已处理"""
        async with self.processed_message_ids_lock:
            current_time = time.time()
            self.processed_message_ids[message_id] = current_time
            
            # 清理过期记录
            if len(self.processed_message_ids) > self.processed_message_ids_max_size:
                expired_ids = [
                    msg_id for msg_id, timestamp in self.processed_message_ids.items()
                    if current_time - timestamp > self.message_expire_time
                ]
                
                for msg_id in expired_ids:
                    del self.processed_message_ids[msg_id]
                
                if expired_ids:
                    logger.info(f"【{self.cookie_id}】清理了 {len(expired_ids)} 个过期消息ID")
    
    def parse_chat_message(self, message: dict) -> Optional[Dict[str, Any]]:
        """解析聊天消息（支持普通消息和卡片消息两种格式）"""
        try:
            message_1 = message.get("1", {})
            message_10 = message_1.get("10", {})
            
            # 提取会话ID（参照旧框架：从message_1["2"]提取）
            chat_id_raw = message_1.get("2", "")
            chat_id = chat_id_raw.split('@')[0] if '@' in str(chat_id_raw) else str(chat_id_raw)
            
            # 提取消息时间
            msg_time = message_1.get("5", 0)
            if msg_time:
                msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(msg_time / 1000))
            else:
                msg_time = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 判断消息格式：有"10"字段且有reminderContent是普通聊天消息
            if message_10 and message_10.get("reminderContent"):
                # 普通聊天消息格式
                send_user_id = message_10.get("senderUserId", "unknown")
                reminder_content = message_10.get("reminderContent", "")
                # 提取发送者名称（参照旧框架：优先使用senderNick，再用reminderTitle）
                # 注意：需要检查空字符串
                send_user_name = message_10.get("senderNick") or message_10.get("reminderTitle") or "系统"
            else:
                # 卡片消息格式（如评价请求、确认收货等系统卡片）
                # 结构: {"1": {"1": {"1": "xxx@goofish"}, "2": "xxx@goofish", "6": {"3": {"2": "消息内容"}}}}
                message_1_1 = message_1.get("1", {})
                if isinstance(message_1_1, dict):
                    sender_raw = message_1_1.get("1", "")
                    send_user_id = sender_raw.split('@')[0] if '@' in str(sender_raw) else str(sender_raw)
                else:
                    send_user_id = "unknown"
                
                # 从卡片消息中提取内容
                message_6 = message_1.get("6", {})
                message_6_3 = message_6.get("3", {})
                reminder_content = message_6_3.get("2", "")  # 卡片消息的文本内容
                
                # 卡片消息通常是系统消息，用户名设为"系统"
                send_user_name = "系统"
            
            # 提取商品ID
            item_id = self._extract_item_id(message)
            
            return {
                "send_user_id": send_user_id,
                "send_user_name": send_user_name,
                "send_message": reminder_content,
                "chat_id": chat_id,
                "item_id": item_id,
                "msg_time": msg_time,
                "raw_message": message,
            }
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】解析聊天消息失败: {safe_str(e)}")
            return None
    
    def parse_card_update_message(self, message: dict) -> Optional[Dict[str, Any]]:
        """解析卡片更新消息（message["1"]为字符串的特殊格式）
        
        此类消息结构：
        - message["1"]: 字符串（包含商品相关ID）
        - message["2"]: 会话ID
        - message["4"]: 类似标准消息的message["1"]["10"]，包含reminderContent等
        - message["5"]: 时间戳
        """
        try:
            message_4 = message.get("4", {})
            
            # 提取会话ID（从message["2"]）
            chat_id_raw = message.get("2", "")
            chat_id = chat_id_raw.split('@')[0] if '@' in str(chat_id_raw) else str(chat_id_raw)
            
            # 提取消息时间
            msg_time = message.get("5", 0)
            if msg_time:
                msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(msg_time / 1000))
            else:
                msg_time = time.strftime("%Y-%m-%d %H:%M:%S")
            
            # 从message["4"]中提取消息内容（结构与标准消息的message["1"]["10"]相同）
            reminder_content = message_4.get("reminderContent", "")
            send_user_id = message_4.get("senderUserId", "unknown")
            send_user_name = message_4.get("reminderTitle", "系统")
            
            # 提取商品ID
            item_id = self._extract_item_id_from_card_update(message_4)
            
            return {
                "send_user_id": send_user_id,
                "send_user_name": send_user_name,
                "send_message": reminder_content,
                "chat_id": chat_id,
                "item_id": item_id,
                "msg_time": msg_time,
                "raw_message": message,
            }
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】解析卡片更新消息失败: {safe_str(e)}")
            return None
    
    def _extract_item_id_from_card_update(self, message_4: dict) -> str:
        """从卡片更新消息的message["4"]中提取商品ID"""
        try:
            # 方法1: 从reminderUrl中提取
            url_info = message_4.get("reminderUrl", "")
            if url_info and "itemId=" in str(url_info):
                item_id = url_info.split("itemId=")[1].split("&")[0]
                if item_id:
                    return str(item_id)
            
            # 方法2: 从extJson中提取
            ext_json = message_4.get("extJson", "")
            if ext_json:
                try:
                    ext_json_dict = json.loads(ext_json)
                    item_id = ext_json_dict.get("itemId", "")
                    if item_id:
                        return str(item_id)
                except Exception:
                    pass
            
            return ""
        except Exception:
            return ""
    
    def _extract_item_id(self, message: dict) -> str:
        """从消息中提取商品ID（参照旧框架message_handler_core.py）"""
        try:
            message_1 = message.get("1", {})
            message_10 = message_1.get("10", {})
            
            # 方法1: 从reminderUrl提取（参照旧框架，优先级最高）
            url_info = message_10.get("reminderUrl", "")
            if url_info and "itemId=" in str(url_info):
                item_id = url_info.split("itemId=")[1].split("&")[0]
                if item_id:
                    return str(item_id)
            
            # 方法2: 尝试从bizTag提取
            biz_tag = message_10.get("bizTag", "")
            if biz_tag:
                try:
                    biz_tag_dict = json.loads(biz_tag)
                    item_id = biz_tag_dict.get("itemId", "")
                    if item_id:
                        return str(item_id)
                except Exception:
                    pass
            
            # 方法3: 尝试从extJson提取
            ext_json = message_10.get("extJson", "")
            if ext_json:
                try:
                    ext_json_dict = json.loads(ext_json)
                    item_id = ext_json_dict.get("itemId", "")
                    if item_id:
                        return str(item_id)
                except Exception:
                    pass
            
            # 方法4: 从卡片消息的JSON内容中提取（用于评价请求等卡片消息）
            message_6 = message_1.get("6", {})
            message_6_3 = message_6.get("3", {})
            card_json_str = message_6_3.get("5", "")
            if card_json_str:
                try:
                    card_content = json.loads(card_json_str)
                    # 尝试从jumpUrl中提取itemId
                    jump_url = card_content.get("dxCard", {}).get("item", {}).get("main", {}).get("exContent", {}).get("button", {}).get("intent", {}).get("page", {}).get("jumpUrl", "")
                    if jump_url and "itemId=" in jump_url:
                        item_id = jump_url.split("itemId=")[1].split("&")[0]
                        if item_id:
                            return str(item_id)
                except Exception:
                    pass
            
            return ""
        except Exception:
            return ""
    
    def extract_card_title(self, message: dict) -> Optional[str]:
        """从卡片消息中提取标题（参照旧框架message_handler_core.py）
        
        用于检测"小刀"等卡片消息
        
        Args:
            message: 消息数据
            
        Returns:
            卡片标题，如"我已小刀，待刀成"
        """
        try:
            message_1 = message.get("1", {})
            message_6 = message_1.get("6", {})
            message_6_3 = message_6.get("3", {})
            if "5" in message_6_3:
                card_content = json.loads(message_6_3["5"])
                return card_content.get("dxCard", {}).get("item", {}).get("main", {}).get("exContent", {}).get("title", "")
        except Exception:
            pass
        return None
    
    def is_card_message(self, message: dict) -> bool:
        """判断是否为卡片消息（参照旧框架）"""
        try:
            message_1 = message.get("1", {})
            message_6 = message_1.get("6", {})
            return isinstance(message_6, dict) and "3" in message_6
        except Exception:
            return False
    
    async def handle_message(self, message_data: dict, websocket) -> bool:
        """处理消息"""
        try:
            # 发送ACK确认消息（参照旧框架，必须发送否则服务器会断开连接）
            await self._send_ack(message_data, websocket)
            
            # 检查是否为同步包
            if self.is_sync_package(message_data):
                sync_data_list = message_data["body"]["syncPushPackage"]["data"]
                for sync_data in sync_data_list:
                    if isinstance(sync_data, dict):
                        # 解密消息（参照旧框架）
                        message = self._decrypt_message(sync_data)
                        if message is not None and isinstance(message, dict):
                            await self._process_single_message(message, websocket)
                return True
            
            # 处理单条消息（非同步包）
            return await self._process_single_message(message_data, websocket)
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】处理消息异常: {safe_str(e)}")
            return False
    
    async def _send_ack(self, message_data: dict, websocket) -> None:
        """发送ACK确认消息（参照旧框架实现）
        
        服务器需要收到ACK确认，否则可能会断开连接
        
        Args:
            message_data: 原始消息数据
            websocket: WebSocket连接
        """
        try:
            from common.utils.xianyu_utils import generate_mid
            
            headers = message_data.get("headers", {})
            ack = {
                "code": 200,
                "headers": {
                    "mid": headers.get("mid", generate_mid()),
                    "sid": headers.get("sid", ""),
                }
            }
            # 复制部分原始headers
            for key in ['app-key', 'ua', 'dt']:
                if key in headers:
                    ack["headers"][key] = headers[key]
            
            await websocket.send(json.dumps(ack))
        except Exception:
            pass  # ACK发送失败不影响主流程
    
    def _decrypt_message(self, sync_data: dict) -> Optional[dict]:
        """解密消息数据（参照旧框架实现）
        
        Args:
            sync_data: 同步包中的单条数据
            
        Returns:
            解密后的消息字典，解密失败返回None
        """
        if "data" not in sync_data:
            return None
        try:
            data = sync_data["data"]
            try:
                # 先尝试base64解码
                data = base64.b64decode(data).decode("utf-8")
                parsed_data = json.loads(data)
                # 处理未加密的消息（如系统提示等）
                if isinstance(parsed_data, dict) and 'chatType' in parsed_data:
                    # 系统消息不需要处理，直接返回None
                    return None
                # 过滤不需要打印的消息类型（如商品定价失败通知）
                biz_type = parsed_data.get('bizType', '') if isinstance(parsed_data, dict) else ''
                if biz_type not in ('IDLE_SPACE_PRICING',) and not self.is_system_tip_message(parsed_data):
                    logger.warning(f"【{self.cookie_id}】解密消息: {json.dumps(parsed_data, ensure_ascii=False)[:1000]}")
                return parsed_data
            except Exception:
                # base64解码失败，尝试使用decrypt解密
                decrypted = json.loads(decrypt(data))
                # 过滤不需要打印的消息类型
                biz_type = decrypted.get('bizType', '') if isinstance(decrypted, dict) else ''
                if biz_type not in ('IDLE_SPACE_PRICING',) and not self.is_system_tip_message(decrypted):
                    logger.warning(f"【{self.cookie_id}】解密消息: {json.dumps(decrypted, ensure_ascii=False)[:1000]}")
                return decrypted
        except Exception as e:
            logger.debug(f"【{self.cookie_id}】消息解密失败: {safe_str(e)}")
            return None
    
    async def _process_single_message(self, message: dict, websocket) -> bool:
        """处理单条消息（参照旧框架message_handler_core.py）"""
        try:
            # 提取消息ID进行去重
            message_id = self.extract_message_id(message)
            if message_id:
                if await self.is_message_processed(message_id):
                    logger.debug(f"【{self.cookie_id}】消息已处理，跳过: {message_id[:20]}...")
                    return True
                await self.mark_message_processed(message_id)
            
            # 过滤平台系统提示 / 营销活动类消息（如"打气"任务提醒）：
            # 这类消息会命中 is_chat_message（含 reminderContent），但并非真实聊天，
            # 不触发自动回复，也不记录消息日志，直接跳过。
            if self.is_system_tip_message(message):
                logger.debug(f"【{self.cookie_id}】跳过系统提示/营销活动消息")
                return True
            
            # 判断消息类型并分发
            if self.is_chat_message(message):
                parsed = self.parse_chat_message(message)
                if parsed:
                    # 打印解密后的消息（参照旧框架）
                    self._log_chat_message(parsed)
                    
                    send_message = parsed.get("send_message", "")
                    
                    # 参照旧框架：检查是否为卡片消息（reminderContent为[卡片消息]）
                    # 小刀等卡片消息的reminderContent是[卡片消息]，需要提取card_title来判断具体类型
                    if send_message == '[卡片消息]' and self._on_card_message:
                        card_title = self.extract_card_title(message)
                        if card_title:
                            parsed["card_title"] = card_title
                            logger.info(f"【{self.cookie_id}】检测到卡片消息: {card_title}")
                            await self._on_card_message(parsed, websocket)
                            return True
                    
                    if self._on_chat_message:
                        await self._on_chat_message(parsed, websocket)
                return True
            
            # 检查是否为卡片更新消息（message["1"]为字符串的特殊格式，如付款状态变更）
            if self.is_card_update_message(message):
                parsed = self.parse_card_update_message(message)
                if parsed:
                    logger.info(f"【{self.cookie_id}】检测到卡片更新消息: {parsed.get('send_message', '')}")
                    if self._on_card_update_message:
                        await self._on_card_update_message(parsed, websocket)
                    else:
                        logger.debug(f"【{self.cookie_id}】卡片更新消息回调未设置，跳过")
                return True
            
            # 检查是否为卡片消息（无reminderContent的卡片消息，如系统卡片）
            if self.is_card_message(message):
                card_title = self.extract_card_title(message)
                if card_title and self._on_card_message:
                    # 解析基本信息用于卡片消息处理
                    parsed = self.parse_chat_message(message)
                    if parsed:
                        parsed["card_title"] = card_title
                        logger.info(f"【{self.cookie_id}】检测到系统卡片消息: {card_title}")
                        await self._on_card_message(parsed, websocket)
                return True
            
            # 其他类型消息
            if self._on_system_message:
                await self._on_system_message(message, websocket)
            
            return True
            
        except Exception as e:
            logger.error(f"【{self.cookie_id}】处理单条消息异常: {safe_str(e)}")
            return False
    
    def _log_chat_message(self, parsed: Dict[str, Any]) -> None:
        """打印聊天消息日志（参照旧框架格式）
        
        Args:
            parsed: 解析后的消息数据
        """
        try:
            send_user_id = parsed.get("send_user_id", "")
            send_user_name = parsed.get("send_user_name", "")
            send_message = parsed.get("send_message", "")
            chat_id = parsed.get("chat_id", "")
            item_id = parsed.get("item_id", "")
            msg_time = parsed.get("msg_time", "")
            
            # 打印chat_id用于调试
            logger.info(f"【{self.cookie_id}】解析消息: chat_id={chat_id}, send_user_id={send_user_id}")
            
            # 判断是否是自己发出的消息（参照旧框架，使用myid判断）
            if send_user_id == self.myid:
                logger.info(f"[{msg_time}] 【手动发出】 商品({item_id}): {send_message}")
            else:
                logger.warning(f"[{msg_time}] 【收到】用户: {send_user_name}, 商品({item_id}): {send_message}")
        except Exception as e:
            logger.debug(f"【{self.cookie_id}】打印消息日志失败: {safe_str(e)}")
    
    async def schedule_debounced_reply(
        self,
        chat_id: str,
        message_info: Dict[str, Any],
        reply_callback: Callable,
    ):
        """调度防抖回复"""
        async with self.message_debounce_lock:
            # 取消之前的防抖任务
            if chat_id in self.message_debounce_tasks:
                old_task = self.message_debounce_tasks[chat_id].get("task")
                if old_task and not old_task.done():
                    old_task.cancel()
            
            # 创建新的防抖任务
            async def debounced_reply():
                try:
                    await asyncio.sleep(self.message_debounce_delay)
                    await reply_callback(message_info)
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"【{self.cookie_id}】防抖回复异常: {safe_str(e)}")
                finally:
                    async with self.message_debounce_lock:
                        if chat_id in self.message_debounce_tasks:
                            del self.message_debounce_tasks[chat_id]
            
            task = asyncio.create_task(debounced_reply())
            self.message_debounce_tasks[chat_id] = {
                "task": task,
                "last_message": message_info,
                "timer": time.time(),
            }
