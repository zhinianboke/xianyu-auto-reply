import asyncio
import json
import re
import time
import base64
import os
from loguru import logger
import websockets
from utils.xianyu_utils import (
    decrypt, generate_mid, generate_uuid, trans_cookies,
    generate_device_id, generate_sign
)
from config import (
    WEBSOCKET_URL, HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT,
    TOKEN_REFRESH_INTERVAL, TOKEN_RETRY_INTERVAL, config, COOKIES_STR,
    LOG_CONFIG, AUTO_REPLY, DEFAULT_HEADERS, WEBSOCKET_HEADERS,
    APP_CONFIG, API_ENDPOINTS
)
from utils.message_utils import format_message, format_system_message
from utils.ws_utils import WebSocketClient
import sys
import aiohttp

# 日志配置
log_dir = 'logs'
os.makedirs(log_dir, exist_ok=True)
log_path = os.path.join(log_dir, f"xianyu_{time.strftime('%Y-%m-%d')}.log")
logger.remove()
logger.add(
    log_path,
    rotation=LOG_CONFIG.get('rotation', '1 day'),
    retention=LOG_CONFIG.get('retention', '7 days'),
    compression=LOG_CONFIG.get('compression', 'zip'),
    level=LOG_CONFIG.get('level', 'INFO'),
    format=LOG_CONFIG.get('format', '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>'),
    encoding='utf-8',
    enqueue=True
)
logger.add(
    sys.stdout,
    level=LOG_CONFIG.get('level', 'INFO'),
    format=LOG_CONFIG.get('format', '<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>'),
    enqueue=True
)

class XianyuLive:
    def _safe_str(self, e):
        """安全地将异常转换为字符串"""
        try:
            return str(e)
        except:
            try:
                return repr(e)
            except:
                return "未知错误"

    def __init__(self, cookies_str=None, cookie_id: str = "default", user_id: int = None):
        """初始化闲鱼直播类"""
        logger.info(f"【{cookie_id}】开始初始化XianyuLive...")

        if not cookies_str:
            cookies_str = COOKIES_STR
        if not cookies_str:
            raise ValueError("未提供cookies，请在global_config.yml中配置COOKIES_STR或通过参数传入")

        logger.info(f"【{cookie_id}】解析cookies...")
        self.cookies = trans_cookies(cookies_str)
        logger.info(f"【{cookie_id}】cookies解析完成，包含字段: {list(self.cookies.keys())}")

        self.cookie_id = cookie_id  # 唯一账号标识
        self.cookies_str = cookies_str  # 保存原始cookie字符串
        self.user_id = user_id  # 保存用户ID，用于token刷新时保持正确的所有者关系
        self.base_url = WEBSOCKET_URL

        if 'unb' not in self.cookies:
            raise ValueError(f"【{cookie_id}】Cookie中缺少必需的'unb'字段，当前字段: {list(self.cookies.keys())}")

        self.myid = self.cookies['unb']
        logger.info(f"【{cookie_id}】用户ID: {self.myid}")
        self.device_id = generate_device_id(self.myid)
        
        # 心跳相关配置
        self.heartbeat_interval = HEARTBEAT_INTERVAL
        self.heartbeat_timeout = HEARTBEAT_TIMEOUT
        self.last_heartbeat_time = 0
        self.last_heartbeat_response = 0
        self.heartbeat_task = None
        self.ws = None
        
        # Token刷新相关配置
        self.token_refresh_interval = TOKEN_REFRESH_INTERVAL
        self.token_retry_interval = TOKEN_RETRY_INTERVAL
        self.last_token_refresh_time = 0
        self.current_token = None
        self.token_refresh_task = None
        self.connection_restart_flag = False  # 连接重启标志

        # 通知防重复机制
        self.last_notification_time = {}  # 记录每种通知类型的最后发送时间
        self.notification_cooldown = 300  # 5分钟内不重复发送相同类型的通知

        # 自动发货防重复机制
        self.last_delivery_time = {}  # 记录每个商品的最后发货时间
        self.delivery_cooldown = 600  # 10分钟内不重复发货

        # 自动确认发货防重复机制
        self.confirmed_orders = {}  # 记录已确认发货的订单，防止重复确认
        self.order_confirm_cooldown = 600  # 10分钟内不重复确认同一订单
        

        self.session = None  # 用于API调用的aiohttp session

    def is_auto_confirm_enabled(self) -> bool:
        """检查当前账号是否启用自动确认发货"""
        try:
            from db_manager import db_manager
            return db_manager.get_auto_confirm(self.cookie_id)
        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取自动确认发货设置失败: {self._safe_str(e)}")
            return True  # 出错时默认启用



    def can_auto_delivery(self, order_id: str) -> bool:
        """检查是否可以进行自动发货（防重复发货）- 基于订单ID"""
        if not order_id:
            # 如果没有订单ID，则不进行冷却检查，允许发货
            return True

        current_time = time.time()
        last_delivery = self.last_delivery_time.get(order_id, 0)

        if current_time - last_delivery < self.delivery_cooldown:
            logger.info(f"【{self.cookie_id}】订单 {order_id} 在冷却期内，跳过自动发货")
            return False

        return True

    def mark_delivery_sent(self, order_id: str):
        """标记订单已发货 - 基于订单ID"""
        if order_id:
            self.last_delivery_time[order_id] = time.time()
            logger.debug(f"【{self.cookie_id}】标记订单 {order_id} 已发货")
        else:
            logger.debug(f"【{self.cookie_id}】无订单ID，跳过发货标记")

    def _is_auto_delivery_trigger(self, message: str) -> bool:
        """检查消息是否为自动发货触发关键字"""
        # 定义所有自动发货触发关键字
        auto_delivery_keywords = [
            # 系统消息
            '[我已付款，等待你发货]',
            '[已付款，待发货]',
            '我已付款，等待你发货',
            '[记得及时发货]',
        ]

        # 检查消息是否包含任何触发关键字
        for keyword in auto_delivery_keywords:
            if keyword in message:
                return True

        return False

    def _extract_order_id(self, message: dict) -> str:
        """从消息中提取订单ID"""
        try:
            order_id = None

            # 先查看消息的完整结构
            logger.debug(f"【{self.cookie_id}】🔍 完整消息结构: {message}")

            # 检查message['1']的结构
            message_1 = message.get('1', {})
            logger.debug(f"【{self.cookie_id}】🔍 message['1'] keys: {list(message_1.keys()) if message_1 else 'None'}")

            # 检查message['1']['6']的结构
            message_1_6 = message_1.get('6', {}) if message_1 else {}
            logger.debug(f"【{self.cookie_id}】🔍 message['1']['6'] keys: {list(message_1_6.keys()) if message_1_6 else 'None'}")

            # 方法1: 从button的targetUrl中提取orderId
            content_json_str = message.get('1', {}).get('6', {}).get('3', {}).get('5', '')
            if content_json_str:
                try:
                    content_data = json.loads(content_json_str)

                    # 方法1a: 从button的targetUrl中提取orderId
                    target_url = content_data.get('dxCard', {}).get('item', {}).get('main', {}).get('exContent', {}).get('button', {}).get('targetUrl', '')
                    if target_url:
                        # 从URL中提取orderId参数
                        order_match = re.search(r'orderId=(\d+)', target_url)
                        if order_match:
                            order_id = order_match.group(1)
                            logger.info(f'【{self.cookie_id}】✅ 从button提取到订单ID: {order_id}')

                    # 方法1b: 从main的targetUrl中提取order_detail的id
                    if not order_id:
                        main_target_url = content_data.get('dxCard', {}).get('item', {}).get('main', {}).get('targetUrl', '')
                        if main_target_url:
                            order_match = re.search(r'order_detail\?id=(\d+)', main_target_url)
                            if order_match:
                                order_id = order_match.group(1)
                                logger.info(f'【{self.cookie_id}】✅ 从main targetUrl提取到订单ID: {order_id}')

                except Exception as parse_e:
                    logger.debug(f"解析内容JSON失败: {parse_e}")

            # 方法2: 从dynamicOperation中的order_detail URL提取orderId
            if not order_id and content_json_str:
                try:
                    content_data = json.loads(content_json_str)
                    dynamic_target_url = content_data.get('dynamicOperation', {}).get('changeContent', {}).get('dxCard', {}).get('item', {}).get('main', {}).get('exContent', {}).get('button', {}).get('targetUrl', '')
                    if dynamic_target_url:
                        # 从order_detail URL中提取id参数
                        order_match = re.search(r'order_detail\?id=(\d+)', dynamic_target_url)
                        if order_match:
                            order_id = order_match.group(1)
                            logger.info(f'【{self.cookie_id}】✅ 从order_detail提取到订单ID: {order_id}')
                except Exception as parse_e:
                    logger.debug(f"解析dynamicOperation JSON失败: {parse_e}")

            return order_id

        except Exception as e:
            logger.error(f"提取订单ID失败: {self._safe_str(e)}")
            return None

    async def _handle_auto_delivery(self, websocket, message: dict, send_user_name: str, send_user_id: str,
                                   item_id: str, chat_id: str, msg_time: str):
        """统一处理自动发货逻辑"""
        try:
            # 提取订单ID
            order_id = self._extract_order_id(message)

            # 订单ID已提取，将在自动发货时进行确认发货处理
            if order_id:
                logger.info(f'[{msg_time}] 【{self.cookie_id}】提取到订单ID: {order_id}，将在自动发货时处理确认发货')
            else:
                logger.warning(f'[{msg_time}] 【{self.cookie_id}】❌ 未能提取到订单ID')

            # 检查是否可以进行自动发货（防重复）- 基于订单ID
            if not self.can_auto_delivery(order_id):
                return

            # 构造用户URL
            user_url = f'https://www.goofish.com/personal?userId={send_user_id}'

            # 自动发货逻辑
            try:
                # 设置默认标题（将通过API获取真实商品信息）
                item_title = "待获取商品信息"

                logger.info(f"【{self.cookie_id}】准备自动发货: item_id={item_id}, item_title={item_title}")

                # 调用自动发货方法（包含自动确认发货）
                delivery_content = await self._auto_delivery(item_id, item_title, order_id)

                if delivery_content:
                    # 标记已发货（防重复）- 基于订单ID
                    self.mark_delivery_sent(order_id)

                    # 发送发货内容给买家
                    await self.send_msg(websocket, chat_id, send_user_id, delivery_content)
                    logger.info(f'[{msg_time}] 【自动发货】已向 {user_url} 发送发货内容')
                    await self.send_delivery_failure_notification(send_user_name, send_user_id, item_id, "发货成功")
                else:
                    logger.warning(f'[{msg_time}] 【自动发货】未找到匹配的发货规则或获取发货内容失败')
                    # 发送自动发货失败通知
                    await self.send_delivery_failure_notification(send_user_name, send_user_id, item_id, "未找到匹配的发货规则或获取发货内容失败")

            except Exception as e:
                logger.error(f"自动发货处理异常: {self._safe_str(e)}")
                # 发送自动发货异常通知
                await self.send_delivery_failure_notification(send_user_name, send_user_id, item_id, f"自动发货处理异常: {str(e)}")

        except Exception as e:
            logger.error(f"统一自动发货处理异常: {self._safe_str(e)}")



    async def refresh_token(self):
        """刷新token"""
        try:
            logger.info(f"【{self.cookie_id}】开始刷新token...")
            params = {
                'jsv': '2.7.2',
                'appKey': '34839810',
                't': str(int(time.time()) * 1000),
                'sign': '',
                'v': '1.0',
                'type': 'originaljson',
                'accountSite': 'xianyu',
                'dataType': 'json',
                'timeout': '20000',
                'api': 'mtop.taobao.idlemessage.pc.login.token',
                'sessionOption': 'AutoLoginOnly',
                'spm_cnt': 'a21ybx.im.0.0',
            }
            data_val = '{"appKey":"444e9908a51d1cb236a27862abc769c9","deviceId":"' + self.device_id + '"}'
            data = {
                'data': data_val,
            }
            
            # 获取token
            token = None
            token = trans_cookies(self.cookies_str).get('_m_h5_tk', '').split('_')[0] if trans_cookies(self.cookies_str).get('_m_h5_tk') else ''
            
            sign = generate_sign(params['t'], token, data_val)
            params['sign'] = sign
            
            # 发送请求
            headers = DEFAULT_HEADERS.copy()
            headers['cookie'] = self.cookies_str
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    API_ENDPOINTS.get('token'),
                    params=params,
                    data=data,
                    headers=headers
                ) as response:
                    res_json = await response.json()
                    
                    # 检查并更新Cookie
                    if 'set-cookie' in response.headers:
                        new_cookies = {}
                        for cookie in response.headers.getall('set-cookie', []):
                            if '=' in cookie:
                                name, value = cookie.split(';')[0].split('=', 1)
                                new_cookies[name.strip()] = value.strip()
                        
                        # 更新cookies
                        if new_cookies:
                            self.cookies.update(new_cookies)
                            # 生成新的cookie字符串
                            self.cookies_str = '; '.join([f"{k}={v}" for k, v in self.cookies.items()])
                            # 更新数据库中的Cookie
                            await self.update_config_cookies()
                            logger.debug("已更新Cookie到数据库")
                    
                    if isinstance(res_json, dict):
                        ret_value = res_json.get('ret', [])
                        # 检查ret是否包含成功信息
                        if any('SUCCESS::调用成功' in ret for ret in ret_value):
                            if 'data' in res_json and 'accessToken' in res_json['data']:
                                new_token = res_json['data']['accessToken']
                                self.current_token = new_token
                                self.last_token_refresh_time = time.time()
                                logger.info(f"【{self.cookie_id}】Token刷新成功")
                                return new_token
                            
                    logger.error(f"【{self.cookie_id}】Token刷新失败: {res_json}")
                    # 发送Token刷新失败通知
                    await self.send_token_refresh_notification(f"Token刷新失败: {res_json}", "token_refresh_failed")
                    return None

        except Exception as e:
            logger.error(f"Token刷新异常: {self._safe_str(e)}")
            # 发送Token刷新异常通知
            await self.send_token_refresh_notification(f"Token刷新异常: {str(e)}", "token_refresh_exception")
            return None

    async def update_config_cookies(self):
        """更新数据库中的cookies"""
        try:
            from db_manager import db_manager

            # 更新数据库中的Cookie
            if hasattr(self, 'cookie_id') and self.cookie_id:
                try:
                    # 获取当前Cookie的用户ID，避免在刷新时改变所有者
                    current_user_id = None
                    if hasattr(self, 'user_id') and self.user_id:
                        current_user_id = self.user_id

                    db_manager.save_cookie(self.cookie_id, self.cookies_str, current_user_id)
                    logger.debug(f"已更新Cookie到数据库: {self.cookie_id}")
                except Exception as e:
                    logger.error(f"更新数据库Cookie失败: {self._safe_str(e)}")
                    # 发送数据库更新失败通知
                    await self.send_token_refresh_notification(f"数据库Cookie更新失败: {str(e)}", "db_update_failed")
            else:
                logger.warning("Cookie ID不存在，无法更新数据库")
                # 发送Cookie ID缺失通知
                await self.send_token_refresh_notification("Cookie ID不存在，无法更新数据库", "cookie_id_missing")

        except Exception as e:
            logger.error(f"更新Cookie失败: {self._safe_str(e)}")
            # 发送Cookie更新失败通知
            await self.send_token_refresh_notification(f"Cookie更新失败: {str(e)}", "cookie_update_failed")

    async def save_item_info_to_db(self, item_id: str, item_detail: str = None, item_title: str = None):
        """保存商品信息到数据库

        Args:
            item_id: 商品ID
            item_detail: 商品详情内容（可以是任意格式的文本）
            item_title: 商品标题
        """
        try:
            # 跳过以 auto_ 开头的商品ID
            if item_id and item_id.startswith('auto_'):
                logger.debug(f"跳过保存自动生成的商品ID: {item_id}")
                return

            # 验证：如果只有商品ID，没有商品标题和商品详情，则不插入数据库
            if not item_title and not item_detail:
                logger.debug(f"跳过保存商品信息：缺少商品标题和详情 - {item_id}")
                return

            # 如果有商品标题但没有详情，也跳过（根据需求，需要同时有标题和详情）
            if not item_title or not item_detail:
                logger.debug(f"跳过保存商品信息：商品标题或详情不完整 - {item_id}")
                return

            from db_manager import db_manager

            # 直接使用传入的详情内容
            item_data = item_detail

            # 保存到数据库
            success = db_manager.save_item_info(self.cookie_id, item_id, item_data)
            if success:
                logger.info(f"商品信息已保存到数据库: {item_id}")
            else:
                logger.warning(f"保存商品信息到数据库失败: {item_id}")

        except Exception as e:
            logger.error(f"保存商品信息到数据库异常: {self._safe_str(e)}")

    async def save_item_detail_only(self, item_id, item_detail):
        """仅保存商品详情（不影响标题等基本信息）"""
        try:
            from db_manager import db_manager

            # 使用专门的详情更新方法
            success = db_manager.update_item_detail(self.cookie_id, item_id, item_detail)

            if success:
                logger.info(f"商品详情已更新: {item_id}")
            else:
                logger.warning(f"更新商品详情失败: {item_id}")

            return success

        except Exception as e:
            logger.error(f"更新商品详情异常: {self._safe_str(e)}")
            return False

    async def fetch_item_detail_from_api(self, item_id: str) -> str:
        """从外部API获取商品详情

        Args:
            item_id: 商品ID

        Returns:
            str: 商品详情文本，获取失败返回空字符串
        """
        try:
            # 检查是否启用自动获取功能
            from config import config
            auto_fetch_config = config.get('ITEM_DETAIL', {}).get('auto_fetch', {})

            if not auto_fetch_config.get('enabled', True):
                logger.debug(f"自动获取商品详情功能已禁用: {item_id}")
                return ""

            # 从配置获取API地址和超时时间
            api_base_url = auto_fetch_config.get('api_url', 'https://selfapi.zhinianboke.com/api/getItemDetail')
            timeout_seconds = auto_fetch_config.get('timeout', 10)

            api_url = f"{api_base_url}/{item_id}"

            logger.info(f"正在从外部API获取商品详情: {item_id}")

            # 使用aiohttp发送异步请求
            import aiohttp
            import asyncio

            timeout = aiohttp.ClientTimeout(total=timeout_seconds)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(api_url) as response:
                    if response.status == 200:
                        result = await response.json()

                        # 检查返回状态
                        if result.get('status') == '200' and result.get('data'):
                            item_detail = result['data']
                            logger.info(f"成功获取商品详情: {item_id}, 长度: {len(item_detail)}")
                            logger.debug(f"商品详情内容: {item_detail[:200]}...")
                            return item_detail
                        else:
                            logger.warning(f"API返回状态异常: {result.get('status')}, message: {result.get('message')}")
                            return ""
                    else:
                        logger.warning(f"API请求失败: HTTP {response.status}")
                        return ""

        except asyncio.TimeoutError:
            logger.warning(f"获取商品详情超时: {item_id}")
            return ""
        except Exception as e:
            logger.error(f"获取商品详情异常: {item_id}, 错误: {self._safe_str(e)}")
            return ""

    async def save_items_list_to_db(self, items_list):
        """批量保存商品列表信息到数据库（并发安全）

        Args:
            items_list: 从get_item_list_info获取的商品列表
        """
        try:
            from db_manager import db_manager

            # 准备批量数据
            batch_data = []
            items_need_detail = []  # 需要获取详情的商品列表

            for item in items_list:
                item_id = item.get('id')
                if not item_id or item_id.startswith('auto_'):
                    continue

                # 构造商品详情数据
                item_detail = {
                    'title': item.get('title', ''),
                    'price': item.get('price', ''),
                    'price_text': item.get('price_text', ''),
                    'category_id': item.get('category_id', ''),
                    'auction_type': item.get('auction_type', ''),
                    'item_status': item.get('item_status', 0),
                    'detail_url': item.get('detail_url', ''),
                    'pic_info': item.get('pic_info', {}),
                    'detail_params': item.get('detail_params', {}),
                    'track_params': item.get('track_params', {}),
                    'item_label_data': item.get('item_label_data', {}),
                    'card_type': item.get('card_type', 0)
                }

                # 检查数据库中是否已有详情
                existing_item = db_manager.get_item_info(self.cookie_id, item_id)
                has_detail = existing_item and existing_item.get('item_detail') and existing_item['item_detail'].strip()

                batch_data.append({
                    'cookie_id': self.cookie_id,
                    'item_id': item_id,
                    'item_title': item.get('title', ''),
                    'item_description': '',  # 暂时为空
                    'item_category': str(item.get('category_id', '')),
                    'item_price': item.get('price_text', ''),
                    'item_detail': json.dumps(item_detail, ensure_ascii=False)
                })

                # 如果没有详情，添加到需要获取详情的列表
                if not has_detail:
                    items_need_detail.append({
                        'item_id': item_id,
                        'item_title': item.get('title', '')
                    })

            if not batch_data:
                logger.info("没有有效的商品数据需要保存")
                return 0

            # 使用批量保存方法（并发安全）
            saved_count = db_manager.batch_save_item_basic_info(batch_data)
            logger.info(f"批量保存商品信息完成: {saved_count}/{len(batch_data)} 个商品")

            # 异步获取缺失的商品详情
            if items_need_detail:
                from config import config
                auto_fetch_config = config.get('ITEM_DETAIL', {}).get('auto_fetch', {})

                if auto_fetch_config.get('enabled', True):
                    logger.info(f"发现 {len(items_need_detail)} 个商品缺少详情，开始获取...")
                    detail_success_count = await self._fetch_missing_item_details(items_need_detail)
                    logger.info(f"成功获取 {detail_success_count}/{len(items_need_detail)} 个商品的详情")
                else:
                    logger.info(f"发现 {len(items_need_detail)} 个商品缺少详情，但自动获取功能已禁用")

            return saved_count

        except Exception as e:
            logger.error(f"批量保存商品信息异常: {self._safe_str(e)}")
            return 0

    async def _fetch_missing_item_details(self, items_need_detail):
        """批量获取缺失的商品详情

        Args:
            items_need_detail: 需要获取详情的商品列表

        Returns:
            int: 成功获取详情的商品数量
        """
        success_count = 0

        try:
            from db_manager import db_manager
            from config import config

            # 从配置获取并发数量和延迟时间
            auto_fetch_config = config.get('ITEM_DETAIL', {}).get('auto_fetch', {})
            max_concurrent = auto_fetch_config.get('max_concurrent', 3)
            retry_delay = auto_fetch_config.get('retry_delay', 0.5)

            # 限制并发数量，避免对API服务器造成压力
            semaphore = asyncio.Semaphore(max_concurrent)

            async def fetch_single_item_detail(item_info):
                async with semaphore:
                    try:
                        item_id = item_info['item_id']
                        item_title = item_info['item_title']

                        # 获取商品详情
                        item_detail_text = await self.fetch_item_detail_from_api(item_id)

                        if item_detail_text:
                            # 保存详情到数据库
                            success = await self.save_item_detail_only(item_id, item_detail_text)
                            if success:
                                logger.info(f"✅ 成功获取并保存商品详情: {item_id} - {item_title}")
                                return 1
                            else:
                                logger.warning(f"❌ 获取详情成功但保存失败: {item_id}")
                        else:
                            logger.warning(f"❌ 未能获取商品详情: {item_id} - {item_title}")

                        # 添加延迟，避免请求过于频繁
                        await asyncio.sleep(retry_delay)
                        return 0

                    except Exception as e:
                        logger.error(f"获取单个商品详情异常: {item_info.get('item_id', 'unknown')}, 错误: {self._safe_str(e)}")
                        return 0

            # 并发获取所有商品详情
            tasks = [fetch_single_item_detail(item_info) for item_info in items_need_detail]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            # 统计成功数量
            for result in results:
                if isinstance(result, int):
                    success_count += result
                elif isinstance(result, Exception):
                    logger.error(f"获取商品详情任务异常: {result}")

            return success_count

        except Exception as e:
            logger.error(f"批量获取商品详情异常: {self._safe_str(e)}")
            return success_count

    async def get_item_info(self, item_id, retry_count=0):
        """获取商品信息，自动处理token失效的情况"""
        if retry_count >= 4:  # 最多重试3次
            logger.error("获取商品信息失败，重试次数过多")
            return {"error": "获取商品信息失败，重试次数过多"}

        # 如果是重试（retry_count > 0），强制刷新token
        if retry_count > 0:
            old_token = self.cookies.get('_m_h5_tk', '').split('_')[0] if self.cookies.get('_m_h5_tk') else ''
            logger.info(f"重试第{retry_count}次，强制刷新token... 当前_m_h5_tk: {old_token}")
            await self.refresh_token()
            new_token = self.cookies.get('_m_h5_tk', '').split('_')[0] if self.cookies.get('_m_h5_tk') else ''
            logger.info(f"重试刷新token完成，新的_m_h5_tk: {new_token}")
        else:
            # 确保使用最新的token（首次调用时的正常逻辑）
            if not self.current_token or (time.time() - self.last_token_refresh_time) >= self.token_refresh_interval:
                old_token = self.cookies.get('_m_h5_tk', '').split('_')[0] if self.cookies.get('_m_h5_tk') else ''
                logger.info(f"Token过期或不存在，刷新token... 当前_m_h5_tk: {old_token}")
                await self.refresh_token()
                new_token = self.cookies.get('_m_h5_tk', '').split('_')[0] if self.cookies.get('_m_h5_tk') else ''
                logger.info(f"Token刷新完成，新的_m_h5_tk: {new_token}")

        # 确保session已创建
        if not self.session:
            await self.create_session()

        params = {
            'jsv': '2.7.2',
            'appKey': '34839810',
            't': str(int(time.time()) * 1000),
            'sign': '',
            'v': '1.0',
            'type': 'originaljson',
            'accountSite': 'xianyu',
            'dataType': 'json',
            'timeout': '20000',
            'api': 'mtop.taobao.idle.pc.detail',
            'sessionOption': 'AutoLoginOnly',
            'spm_cnt': 'a21ybx.im.0.0',
        }

        data_val = '{"itemId":"' + item_id + '"}'
        data = {
            'data': data_val,
        }

        # 始终从最新的cookies中获取_m_h5_tk token（刷新后cookies会被更新）
        token = trans_cookies(self.cookies_str).get('_m_h5_tk', '').split('_')[0] if trans_cookies(self.cookies_str).get('_m_h5_tk') else ''

        logger.warning(111)
        logger.warning(token)
        if token:
            logger.debug(f"使用cookies中的_m_h5_tk token: {token}")
        else:
            logger.warning("cookies中没有找到_m_h5_tk token")

        from utils.xianyu_utils import generate_sign
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign

        try:
            async with self.session.post(
                'https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/',
                params=params,
                data=data
            ) as response:
                res_json = await response.json()

                # 检查并更新Cookie
                if 'set-cookie' in response.headers:
                    new_cookies = {}
                    for cookie in response.headers.getall('set-cookie', []):
                        if '=' in cookie:
                            name, value = cookie.split(';')[0].split('=', 1)
                            new_cookies[name.strip()] = value.strip()
                    
                    # 更新cookies
                    if new_cookies:
                        self.cookies.update(new_cookies)
                        # 生成新的cookie字符串
                        self.cookies_str = '; '.join([f"{k}={v}" for k, v in self.cookies.items()])
                        # 更新数据库中的Cookie
                        await self.update_config_cookies()
                        logger.debug("已更新Cookie到数据库")

                logger.debug(f"商品信息获取成功: {res_json}")
                # 检查返回状态
                if isinstance(res_json, dict):
                    ret_value = res_json.get('ret', [])
                    # 检查ret是否包含成功信息
                    if not any('SUCCESS::调用成功' in ret for ret in ret_value):
                        logger.warning(f"商品信息API调用失败，错误信息: {ret_value}")
                        
                        await asyncio.sleep(0.5)
                        return await self.get_item_info(item_id, retry_count + 1)
                    else:
                        logger.debug(f"商品信息获取成功: {item_id}")
                        return res_json
                else:
                    logger.error(f"商品信息API返回格式异常: {res_json}")
                    return await self.get_item_info(item_id, retry_count + 1)

        except Exception as e:
            logger.error(f"商品信息API请求异常: {self._safe_str(e)}")
            await asyncio.sleep(0.5)
            return await self.get_item_info(item_id, retry_count + 1)

    def extract_item_id_from_message(self, message):
        """从消息中提取商品ID的辅助方法"""
        try:
            # 方法1: 从message["1"]中提取（如果是字符串格式）
            message_1 = message.get('1')
            if isinstance(message_1, str):
                # 尝试从字符串中提取数字ID
                id_match = re.search(r'(\d{10,})', message_1)
                if id_match:
                    logger.info(f"从message[1]字符串中提取商品ID: {id_match.group(1)}")
                    return id_match.group(1)

            # 方法2: 从message["3"]中提取
            message_3 = message.get('3', {})
            if isinstance(message_3, dict):

                # 从extension中提取
                if 'extension' in message_3:
                    extension = message_3['extension']
                    if isinstance(extension, dict):
                        item_id = extension.get('itemId') or extension.get('item_id')
                        if item_id:
                            logger.info(f"从extension中提取商品ID: {item_id}")
                            return item_id

                # 从bizData中提取
                if 'bizData' in message_3:
                    biz_data = message_3['bizData']
                    if isinstance(biz_data, dict):
                        item_id = biz_data.get('itemId') or biz_data.get('item_id')
                        if item_id:
                            logger.info(f"从bizData中提取商品ID: {item_id}")
                            return item_id

                # 从其他可能的字段中提取
                for key, value in message_3.items():
                    if isinstance(value, dict):
                        item_id = value.get('itemId') or value.get('item_id')
                        if item_id:
                            logger.info(f"从{key}字段中提取商品ID: {item_id}")
                            return item_id

                # 从消息内容中提取数字ID
                content = message_3.get('content', '')
                if isinstance(content, str) and content:
                    id_match = re.search(r'(\d{10,})', content)
                    if id_match:
                        logger.info(f"【{self.cookie_id}】从消息内容中提取商品ID: {id_match.group(1)}")
                        return id_match.group(1)

            # 方法3: 遍历整个消息结构查找可能的商品ID
            def find_item_id_recursive(obj, path=""):
                if isinstance(obj, dict):
                    # 直接查找itemId字段
                    for key in ['itemId', 'item_id', 'id']:
                        if key in obj and isinstance(obj[key], (str, int)):
                            value = str(obj[key])
                            if len(value) >= 10 and value.isdigit():
                                logger.info(f"从{path}.{key}中提取商品ID: {value}")
                                return value

                    # 递归查找
                    for key, value in obj.items():
                        result = find_item_id_recursive(value, f"{path}.{key}" if path else key)
                        if result:
                            return result

                elif isinstance(obj, str):
                    # 从字符串中提取可能的商品ID
                    id_match = re.search(r'(\d{10,})', obj)
                    if id_match:
                        logger.info(f"从{path}字符串中提取商品ID: {id_match.group(1)}")
                        return id_match.group(1)

                return None

            result = find_item_id_recursive(message)
            if result:
                return result

            logger.debug("所有方法都未能提取到商品ID")
            return None

        except Exception as e:
            logger.error(f"提取商品ID失败: {self._safe_str(e)}")
            return None

    def debug_message_structure(self, message, context=""):
        """调试消息结构的辅助方法"""
        try:
            logger.debug(f"[{context}] 消息结构调试:")
            logger.debug(f"  消息类型: {type(message)}")

            if isinstance(message, dict):
                for key, value in message.items():
                    logger.debug(f"  键 '{key}': {type(value)} - {str(value)[:100]}...")

                    # 特别关注可能包含商品ID的字段
                    if key in ["1", "3"] and isinstance(value, dict):
                        logger.debug(f"    详细结构 '{key}':")
                        for sub_key, sub_value in value.items():
                            logger.debug(f"      '{sub_key}': {type(sub_value)} - {str(sub_value)[:50]}...")
            else:
                logger.debug(f"  消息内容: {str(message)[:200]}...")

        except Exception as e:
            logger.error(f"调试消息结构时发生错误: {self._safe_str(e)}")

    async def get_default_reply(self, send_user_name: str, send_user_id: str, send_message: str) -> str:
        """获取默认回复内容，支持变量替换"""
        try:
            from db_manager import db_manager

            # 获取当前账号的默认回复设置
            default_reply_settings = db_manager.get_default_reply(self.cookie_id)

            if not default_reply_settings or not default_reply_settings.get('enabled', False):
                logger.debug(f"账号 {self.cookie_id} 未启用默认回复")
                return None

            reply_content = default_reply_settings.get('reply_content', '')
            if not reply_content:
                logger.warning(f"账号 {self.cookie_id} 默认回复内容为空")
                return None

            # 进行变量替换
            try:
                formatted_reply = reply_content.format(
                    send_user_name=send_user_name,
                    send_user_id=send_user_id,
                    send_message=send_message
                )
                logger.info(f"【{self.cookie_id}】使用默认回复: {formatted_reply}")
                return formatted_reply
            except Exception as format_error:
                logger.error(f"默认回复变量替换失败: {self._safe_str(format_error)}")
                # 如果变量替换失败，返回原始内容
                return reply_content

        except Exception as e:
            logger.error(f"获取默认回复失败: {self._safe_str(e)}")
            return None

    async def get_keyword_reply(self, send_user_name: str, send_user_id: str, send_message: str, item_id: str = None) -> str:
        """获取关键词匹配回复（支持商品ID优先匹配）"""
        try:
            from db_manager import db_manager

            # 获取当前账号的关键词列表（包含商品ID）
            keywords = db_manager.get_keywords_with_item_id(self.cookie_id)

            if not keywords:
                logger.debug(f"账号 {self.cookie_id} 没有配置关键词")
                return None

            # 1. 如果有商品ID，优先匹配该商品ID对应的关键词
            if item_id:
                for keyword, reply, keyword_item_id in keywords:
                    if keyword_item_id == item_id and keyword.lower() in send_message.lower():
                        # 进行变量替换
                        try:
                            formatted_reply = reply.format(
                                send_user_name=send_user_name,
                                send_user_id=send_user_id,
                                send_message=send_message
                            )
                            logger.info(f"商品ID关键词匹配成功: 商品{item_id} '{keyword}' -> {formatted_reply}")
                            return formatted_reply
                        except Exception as format_error:
                            logger.error(f"关键词回复变量替换失败: {self._safe_str(format_error)}")
                            # 如果变量替换失败，返回原始内容
                            return reply

            # 2. 如果商品ID匹配失败或没有商品ID，匹配没有商品ID的通用关键词
            for keyword, reply, keyword_item_id in keywords:
                if not keyword_item_id and keyword.lower() in send_message.lower():
                    # 进行变量替换
                    try:
                        formatted_reply = reply.format(
                            send_user_name=send_user_name,
                            send_user_id=send_user_id,
                            send_message=send_message
                        )
                        logger.info(f"通用关键词匹配成功: '{keyword}' -> {formatted_reply}")
                        return formatted_reply
                    except Exception as format_error:
                        logger.error(f"关键词回复变量替换失败: {self._safe_str(format_error)}")
                        # 如果变量替换失败，返回原始内容
                        return reply

            logger.debug(f"未找到匹配的关键词: {send_message}")
            return None

        except Exception as e:
            logger.error(f"获取关键词回复失败: {self._safe_str(e)}")
            return None

    async def get_ai_reply(self, send_user_name: str, send_user_id: str, send_message: str, item_id: str, chat_id: str):
        """获取AI回复"""
        try:
            from ai_reply_engine import ai_reply_engine

            # 检查是否启用AI回复
            if not ai_reply_engine.is_ai_enabled(self.cookie_id):
                logger.debug(f"账号 {self.cookie_id} 未启用AI回复")
                return None

            # 从数据库获取商品信息
            from db_manager import db_manager
            item_info_raw = db_manager.get_item_info(self.cookie_id, item_id)

            if not item_info_raw:
                logger.debug(f"数据库中无商品信息: {item_id}")
                # 使用默认商品信息
                item_info = {
                    'title': '商品信息获取失败',
                    'price': 0,
                    'desc': '暂无商品描述'
                }
            else:
                # 解析数据库中的商品信息
                item_info = {
                    'title': item_info_raw.get('item_title', '未知商品'),
                    'price': self._parse_price(item_info_raw.get('item_price', '0')),
                    'desc': item_info_raw.get('item_description', '暂无商品描述')
                }

            # 生成AI回复
            reply = ai_reply_engine.generate_reply(
                message=send_message,
                item_info=item_info,
                chat_id=chat_id,
                cookie_id=self.cookie_id,
                user_id=send_user_id,
                item_id=item_id
            )

            if reply:
                logger.info(f"【{self.cookie_id}】AI回复生成成功: {reply}")
                return reply
            else:
                logger.debug(f"AI回复生成失败")
                return None

        except Exception as e:
            logger.error(f"获取AI回复失败: {self._safe_str(e)}")
            return None

    def _parse_price(self, price_str: str) -> float:
        """解析价格字符串为数字"""
        try:
            if not price_str:
                return 0.0
            # 移除非数字字符，保留小数点
            price_clean = re.sub(r'[^\d.]', '', str(price_str))
            return float(price_clean) if price_clean else 0.0
        except:
            return 0.0

    async def send_notification(self, send_user_name: str, send_user_id: str, send_message: str, item_id: str = None):
        """发送消息通知"""
        try:
            from db_manager import db_manager
            import aiohttp


            # 获取当前账号的通知配置
            notifications = db_manager.get_account_notifications(self.cookie_id)

            if not notifications:
                logger.debug(f"账号 {self.cookie_id} 未配置消息通知")
                return

            # 构建通知消息
            notification_msg = f"🚨 接收消息通知\n\n" \
                             f"账号: {self.cookie_id}\n" \
                             f"买家: {send_user_name} (ID: {send_user_id})\n" \
                             f"商品ID: {item_id or '未知'}\n" \
                             f"消息内容: {send_message}\n" \
                             f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"

            # 发送通知到各个渠道
            for notification in notifications:
                if not notification.get('enabled', True):
                    continue

                channel_type = notification.get('channel_type')
                channel_config = notification.get('channel_config')

                try:
                    # 解析配置数据
                    config_data = self._parse_notification_config(channel_config)

                    match channel_type:
                        case 'qq':
                            await self._send_qq_notification(config_data, notification_msg)
                        case 'ding_talk' | 'dingtalk':
                            await self._send_dingtalk_notification(config_data, notification_msg)
                        case 'email':
                            await self._send_email_notification(config_data, notification_msg)
                        case 'webhook':
                            await self._send_webhook_notification(config_data, notification_msg)
                        case 'wechat':
                            await self._send_wechat_notification(config_data, notification_msg)
                        case 'telegram':
                            await self._send_telegram_notification(config_data, notification_msg)
                        case _:
                            logger.warning(f"不支持的通知渠道类型: {channel_type}")

                except Exception as notify_error:
                    logger.error(f"发送通知失败 ({notification.get('channel_name', 'Unknown')}): {self._safe_str(notify_error)}")

        except Exception as e:
            logger.error(f"处理消息通知失败: {self._safe_str(e)}")

    def _parse_notification_config(self, config: str) -> dict:
        """解析通知配置数据"""
        try:
            import json
            # 尝试解析JSON格式的配置
            return json.loads(config)
        except (json.JSONDecodeError, TypeError):
            # 兼容旧格式（直接字符串）
            return {"config": config}

    async def _send_qq_notification(self, config_data: dict, message: str):
        """发送QQ通知"""
        try:
            import aiohttp

            # 解析配置（QQ号码）
            qq_number = config_data.get('qq_number') or config_data.get('config', '')
            qq_number = qq_number.strip() if qq_number else ''

            if not qq_number:
                logger.warning("QQ通知配置为空")
                return

            # 构建请求URL
            api_url = "http://notice.zhinianblog.cn/sendPrivateMsg"
            params = {
                'qq': qq_number,
                'msg': message
            }

            # 发送GET请求
            async with aiohttp.ClientSession() as session:
                async with session.get(api_url, params=params, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"QQ通知发送成功: {qq_number}")
                    else:
                        logger.warning(f"QQ通知发送失败: {response.status}")

        except Exception as e:
            logger.error(f"发送QQ通知异常: {self._safe_str(e)}")

    async def _send_dingtalk_notification(self, config_data: dict, message: str):
        """发送钉钉通知"""
        try:
            import aiohttp
            import json
            import hmac
            import hashlib
            import base64
            import time

            # 解析配置
            webhook_url = config_data.get('webhook_url') or config_data.get('config', '')
            secret = config_data.get('secret', '')

            webhook_url = webhook_url.strip() if webhook_url else ''
            if not webhook_url:
                logger.warning("钉钉通知配置为空")
                return

            # 如果有加签密钥，生成签名
            if secret:
                timestamp = str(round(time.time() * 1000))
                secret_enc = secret.encode('utf-8')
                string_to_sign = f'{timestamp}\n{secret}'
                string_to_sign_enc = string_to_sign.encode('utf-8')
                hmac_code = hmac.new(secret_enc, string_to_sign_enc, digestmod=hashlib.sha256).digest()
                sign = base64.b64encode(hmac_code).decode('utf-8')
                webhook_url += f'&timestamp={timestamp}&sign={sign}'

            data = {
                "msgtype": "markdown",
                "markdown": {
                    "title": "闲鱼自动回复通知",
                    "text": message
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=data, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"钉钉通知发送成功")
                    else:
                        logger.warning(f"钉钉通知发送失败: {response.status}")

        except Exception as e:
            logger.error(f"发送钉钉通知异常: {self._safe_str(e)}")

    async def _send_email_notification(self, config_data: dict, message: str):
        """发送邮件通知"""
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            # 解析配置
            smtp_server = config_data.get('smtp_server', '')
            smtp_port = int(config_data.get('smtp_port', 587))
            email_user = config_data.get('email_user', '')
            email_password = config_data.get('email_password', '')
            recipient_email = config_data.get('recipient_email', '')

            if not all([smtp_server, email_user, email_password, recipient_email]):
                logger.warning("邮件通知配置不完整")
                return

            # 创建邮件
            msg = MIMEMultipart()
            msg['From'] = email_user
            msg['To'] = recipient_email
            msg['Subject'] = "闲鱼自动回复通知"

            # 添加邮件正文
            msg.attach(MIMEText(message, 'plain', 'utf-8'))

            # 发送邮件
            server = smtplib.SMTP(smtp_server, smtp_port)
            server.starttls()
            server.login(email_user, email_password)
            server.send_message(msg)
            server.quit()

            logger.info(f"邮件通知发送成功: {recipient_email}")

        except Exception as e:
            logger.error(f"发送邮件通知异常: {self._safe_str(e)}")

    async def _send_webhook_notification(self, config_data: dict, message: str):
        """发送Webhook通知"""
        try:
            import aiohttp
            import json

            # 解析配置
            webhook_url = config_data.get('webhook_url', '')
            http_method = config_data.get('http_method', 'POST').upper()
            headers_str = config_data.get('headers', '{}')
            message_template = config_data.get('message_template', '')

            if not webhook_url:
                logger.warning("Webhook通知配置为空")
                return

            # 解析自定义请求头
            try:
                custom_headers = json.loads(headers_str) if headers_str else {}
            except json.JSONDecodeError:
                custom_headers = {}

            # 设置默认请求头
            headers = {'Content-Type': 'application/json'}
            headers.update(custom_headers)

            # 构建消息数据
            data = self._build_webhook_message(message_template, message)

            async with aiohttp.ClientSession() as session:
                if http_method == 'POST':
                    async with session.post(webhook_url, json=data, headers=headers, timeout=10) as response:
                        response_text = await response.text()
                        if response.status == 200:
                            logger.info(f"Webhook通知发送成功")
                            logger.debug(f"响应内容: {response_text}")
                        else:
                            logger.warning(f"Webhook通知发送失败: {response.status}, 响应: {response_text}")
                elif http_method == 'PUT':
                    async with session.put(webhook_url, json=data, headers=headers, timeout=10) as response:
                        response_text = await response.text()
                        if response.status == 200:
                            logger.info(f"Webhook通知发送成功")
                            logger.debug(f"响应内容: {response_text}")
                        else:
                            logger.warning(f"Webhook通知发送失败: {response.status}, 响应: {response_text}")
                else:
                    logger.warning(f"不支持的HTTP方法: {http_method}")

        except Exception as e:
            logger.error(f"发送Webhook通知异常: {self._safe_str(e)}")

    def _build_webhook_message(self, message_template: str, message: str) -> dict:
        """构建Webhook消息数据"""
        import json
        import time

        # 变量替换数据
        variables = {
            'message': message,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
            'source': 'xianyu-auto-reply'
        }

        # 如果没有自定义模板，使用默认格式
        if not message_template or not message_template.strip():
            return {
                'message': message,
                'timestamp': variables['timestamp'],
                'source': variables['source']
            }

        try:
            # 解析自定义模板
            template = json.loads(message_template)

            # 变量替换
            template_str = json.dumps(template)
            for key, value in variables.items():
                # 对值进行JSON转义，确保特殊字符被正确处理
                escaped_value = json.dumps(str(value))[1:-1]  # 去掉外层引号
                template_str = template_str.replace(f'{{{{{key}}}}}', escaped_value)

            return json.loads(template_str)

        except json.JSONDecodeError as e:
            logger.warning(f"消息模板JSON格式错误: {e}，使用默认格式")
            return {
                'message': message,
                'timestamp': variables['timestamp'],
                'source': variables['source']
            }

    async def _send_wechat_notification(self, config_data: dict, message: str):
        """发送微信通知"""
        try:
            import aiohttp
            import json

            # 解析配置
            webhook_url = config_data.get('webhook_url', '')

            if not webhook_url:
                logger.warning("微信通知配置为空")
                return

            data = {
                "msgtype": "text",
                "text": {
                    "content": message
                }
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(webhook_url, json=data, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"微信通知发送成功")
                    else:
                        logger.warning(f"微信通知发送失败: {response.status}")

        except Exception as e:
            logger.error(f"发送微信通知异常: {self._safe_str(e)}")

    async def _send_telegram_notification(self, config_data: dict, message: str):
        """发送Telegram通知"""
        try:
            import aiohttp

            # 解析配置
            bot_token = config_data.get('bot_token', '')
            chat_id = config_data.get('chat_id', '')

            if not all([bot_token, chat_id]):
                logger.warning("Telegram通知配置不完整")
                return

            # 构建API URL
            api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

            data = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'HTML'
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, json=data, timeout=10) as response:
                    if response.status == 200:
                        logger.info(f"Telegram通知发送成功")
                    else:
                        logger.warning(f"Telegram通知发送失败: {response.status}")

        except Exception as e:
            logger.error(f"发送Telegram通知异常: {self._safe_str(e)}")

    async def send_token_refresh_notification(self, error_message: str, notification_type: str = "token_refresh"):
        """发送Token刷新异常通知（带防重复机制）"""
        try:
            # 检查是否是正常的令牌过期，这种情况不需要发送通知
            if self._is_normal_token_expiry(error_message):
                logger.debug(f"检测到正常的令牌过期，跳过通知: {error_message}")
                return

            # 检查是否在冷却期内
            current_time = time.time()
            last_time = self.last_notification_time.get(notification_type, 0)

            if current_time - last_time < self.notification_cooldown:
                logger.debug(f"通知在冷却期内，跳过发送: {notification_type} (距离上次 {int(current_time - last_time)} 秒)")
                return

            from db_manager import db_manager

            # 获取当前账号的通知配置
            notifications = db_manager.get_account_notifications(self.cookie_id)

            if not notifications:
                logger.debug("未配置消息通知，跳过Token刷新通知")
                return

            # 构造通知消息
            notification_msg = f"""🔴 闲鱼账号Token刷新异常

账号ID: {self.cookie_id}
异常时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}
异常信息: {error_message}

请检查账号Cookie是否过期，如有需要请及时更新Cookie配置。"""

            logger.info(f"准备发送Token刷新异常通知: {self.cookie_id}")

            # 发送通知到各个渠道
            notification_sent = False
            for notification in notifications:
                if not notification.get('enabled', True):
                    continue

                channel_type = notification.get('channel_type')
                channel_config = notification.get('channel_config')

                try:
                    # 解析配置数据
                    config_data = self._parse_notification_config(channel_config)

                    match channel_type:
                        case 'qq':
                            await self._send_qq_notification(config_data, notification_msg)
                            notification_sent = True
                        case 'ding_talk' | 'dingtalk':
                            await self._send_dingtalk_notification(config_data, notification_msg)
                            notification_sent = True
                        case 'email':
                            await self._send_email_notification(config_data, notification_msg)
                            notification_sent = True
                        case 'webhook':
                            await self._send_webhook_notification(config_data, notification_msg)
                            notification_sent = True
                        case 'wechat':
                            await self._send_wechat_notification(config_data, notification_msg)
                            notification_sent = True
                        case 'telegram':
                            await self._send_telegram_notification(config_data, notification_msg)
                            notification_sent = True
                        case _:
                            logger.warning(f"不支持的通知渠道类型: {channel_type}")

                except Exception as notify_error:
                    logger.error(f"发送Token刷新通知失败 ({notification.get('channel_name', 'Unknown')}): {self._safe_str(notify_error)}")

            # 如果成功发送了通知，更新最后发送时间
            if notification_sent:
                self.last_notification_time[notification_type] = current_time
                logger.info(f"Token刷新通知已发送，下次可发送时间: {time.strftime('%H:%M:%S', time.localtime(current_time + self.notification_cooldown))}")

        except Exception as e:
            logger.error(f"处理Token刷新通知失败: {self._safe_str(e)}")

    def _is_normal_token_expiry(self, error_message: str) -> bool:
        """检查是否是正常的令牌过期或其他不需要通知的情况"""
        # 不需要发送通知的关键词
        no_notification_keywords = [
            # 正常的令牌过期
            'FAIL_SYS_TOKEN_EXOIRED::令牌过期',
            'FAIL_SYS_TOKEN_EXPIRED::令牌过期',
            'FAIL_SYS_TOKEN_EXOIRED',
            'FAIL_SYS_TOKEN_EXPIRED',
            '令牌过期',
            # Session过期（正常情况）
            'FAIL_SYS_SESSION_EXPIRED::Session过期',
            'FAIL_SYS_SESSION_EXPIRED',
            'Session过期',
            # Token定时刷新失败（会自动重试）
            'Token定时刷新失败，将自动重试',
            'Token定时刷新失败'
        ]

        # 检查错误消息是否包含不需要通知的关键词
        for keyword in no_notification_keywords:
            if keyword in error_message:
                return True

        return False

    async def send_delivery_failure_notification(self, send_user_name: str, send_user_id: str, item_id: str, error_message: str):
        """发送自动发货失败通知"""
        try:
            from db_manager import db_manager

            # 获取当前账号的通知配置
            notifications = db_manager.get_account_notifications(self.cookie_id)

            if not notifications:
                logger.debug("未配置消息通知，跳过自动发货通知")
                return

            # 构造通知消息
            notification_message = f"🚨 自动发货通知\n\n" \
                                 f"账号: {self.cookie_id}\n" \
                                 f"买家: {send_user_name} (ID: {send_user_id})\n" \
                                 f"商品ID: {item_id}\n" \
                                 f"结果: {error_message}\n" \
                                 f"时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n" \
                                 f"请及时处理！"

            # 发送通知到所有已启用的通知渠道
            for notification in notifications:
                if notification.get('enabled', False):
                    channel_type = notification.get('channel_type', 'qq')
                    channel_config = notification.get('channel_config', '')

                    try:
                        # 解析配置数据
                        config_data = self._parse_notification_config(channel_config)

                        match channel_type:
                            case 'qq':
                                await self._send_qq_notification(config_data, notification_message)
                                logger.info(f"已发送自动发货通知到QQ")
                            case 'ding_talk' | 'dingtalk':
                                await self._send_dingtalk_notification(config_data, notification_message)
                                logger.info(f"已发送自动发货通知到钉钉")
                            case 'email':
                                await self._send_email_notification(config_data, notification_message)
                                logger.info(f"已发送自动发货通知到邮箱")
                            case 'webhook':
                                await self._send_webhook_notification(config_data, notification_message)
                                logger.info(f"已发送自动发货通知到Webhook")
                            case 'wechat':
                                await self._send_wechat_notification(config_data, notification_message)
                                logger.info(f"已发送自动发货通知到微信")
                            case 'telegram':
                                await self._send_telegram_notification(config_data, notification_message)
                                logger.info(f"已发送自动发货通知到Telegram")
                            case _:
                                logger.warning(f"不支持的通知渠道类型: {channel_type}")

                    except Exception as notify_error:
                        logger.error(f"发送自动发货通知失败: {self._safe_str(notify_error)}")

        except Exception as e:
            logger.error(f"发送自动发货通知异常: {self._safe_str(e)}")

    async def auto_confirm(self, order_id, retry_count=0):
        """自动确认发货 - 使用加密模块，不包含延时处理（延时已在_auto_delivery中处理）"""
        try:
            logger.debug(f"【{self.cookie_id}】开始确认发货，订单ID: {order_id}")

            # 导入超级混淆加密模块
            from secure_confirm_ultra import SecureConfirm

            # 创建加密确认实例
            secure_confirm = SecureConfirm(self.session, self.cookies_str, self.cookie_id)

            # 传递必要的属性
            secure_confirm.current_token = self.current_token
            secure_confirm.last_token_refresh_time = self.last_token_refresh_time
            secure_confirm.token_refresh_interval = self.token_refresh_interval
            secure_confirm.refresh_token = self.refresh_token  # 传递refresh_token方法

            # 调用加密的确认方法
            return await secure_confirm.auto_confirm(order_id, retry_count)

        except Exception as e:
            logger.error(f"【{self.cookie_id}】加密确认模块调用失败: {self._safe_str(e)}")
            return {"error": f"加密确认模块调用失败: {self._safe_str(e)}", "order_id": order_id}

    async def auto_freeshipping(self, order_id, item_id, buyer_id, retry_count=0):
        """自动免拼发货 - 使用加密模块"""
        try:
            logger.debug(f"【{self.cookie_id}】开始免拼发货，订单ID: {order_id}")

            # 导入超级混淆加密模块
            from secure_freeshipping_ultra import SecureFreeshipping

            # 创建加密免拼发货实例
            secure_freeshipping = SecureFreeshipping(self.session, self.cookies_str, self.cookie_id)

            # 传递必要的属性
            secure_freeshipping.current_token = self.current_token
            secure_freeshipping.last_token_refresh_time = self.last_token_refresh_time
            secure_freeshipping.token_refresh_interval = self.token_refresh_interval
            secure_freeshipping.refresh_token = self.refresh_token  # 传递refresh_token方法

            # 调用加密的免拼发货方法
            return await secure_freeshipping.auto_freeshipping(order_id, item_id, buyer_id, retry_count)

        except Exception as e:
            logger.error(f"【{self.cookie_id}】加密免拼发货模块调用失败: {self._safe_str(e)}")
            return {"error": f"加密免拼发货模块调用失败: {self._safe_str(e)}", "order_id": order_id}

    async def fetch_order_detail_info(self, order_id: str):
        """获取订单详情信息"""
        try:
            logger.info(f"【{self.cookie_id}】开始获取订单详情: {order_id}")

            # 导入订单详情获取器
            from utils.order_detail_fetcher import fetch_order_detail_simple

            # 获取当前账号的cookie字符串
            cookie_string = self.cookies_str
            logger.debug(f"【{self.cookie_id}】使用Cookie长度: {len(cookie_string) if cookie_string else 0}")

            # 异步获取订单详情（使用当前账号的cookie和无头模式）
            result = await fetch_order_detail_simple(order_id, cookie_string, headless=True)

            if result:
                logger.info(f"【{self.cookie_id}】订单详情获取成功: {order_id}")
                logger.info(f"【{self.cookie_id}】页面标题: {result.get('title', '未知')}")

                # 获取解析后的规格信息
                spec_name = result.get('spec_name', '')
                spec_value = result.get('spec_value', '')

                if spec_name and spec_value:
                    logger.info(f"【{self.cookie_id}】📋 规格名称: {spec_name}")
                    logger.info(f"【{self.cookie_id}】📝 规格值: {spec_value}")
                    print(f"🛍️ 【{self.cookie_id}】订单 {order_id} 规格信息: {spec_name} -> {spec_value}")
                else:
                    logger.warning(f"【{self.cookie_id}】未获取到有效的规格信息")
                    print(f"⚠️ 【{self.cookie_id}】订单 {order_id} 规格信息获取失败")

                return result
            else:
                logger.warning(f"【{self.cookie_id}】订单详情获取失败: {order_id}")
                return None

        except Exception as e:
            logger.error(f"【{self.cookie_id}】获取订单详情异常: {self._safe_str(e)}")
            return None

    async def _auto_delivery(self, item_id: str, item_title: str = None, order_id: str = None):
        """自动发货功能 - 获取卡券规则，执行延时，确认发货，发送内容"""
        try:
            from db_manager import db_manager

            logger.info(f"开始自动发货检查: 商品ID={item_id}")

            # 获取商品详细信息
            item_info = None
            search_text = item_title  # 默认使用传入的标题

            if item_id and item_id != "未知商品":
                # 优先尝试通过API获取商品信息
                try:
                    logger.info(f"通过API获取商品详细信息: {item_id}")
                    item_info = await self.get_item_info(item_id)
                    if item_info and 'data' in item_info:
                        data = item_info['data']
                        item_data = data['itemDO']
                        shareData = item_data['shareData']
                        shareInfoJsonString = shareData['shareInfoJsonString']

                        # 解析 shareInfoJsonString 并提取 content 内容
                        try:
                            share_info = json.loads(shareInfoJsonString)
                            content = share_info.get('contentParams', {}).get('mainParams', {}).get('content', '')
                            if content:
                                search_text = content
                                logger.info(f"API成功提取商品内容作为搜索文本: {content[:100]}...")
                            else:
                                search_text = shareInfoJsonString
                                logger.warning("未能从API商品信息中提取到content字段，使用完整JSON字符串")
                        except json.JSONDecodeError as json_e:
                            logger.warning(f"解析API商品信息JSON失败: {self._safe_str(json_e)}，使用原始字符串")
                            search_text = shareInfoJsonString
                        except Exception as parse_e:
                            logger.warning(f"提取API商品内容失败: {self._safe_str(parse_e)}，使用原始字符串")
                            search_text = shareInfoJsonString

                        logger.info(f"API获取到的商品信息为: {search_text[:200]}...")
                    else:
                        raise Exception("API返回数据格式异常")

                except Exception as e:
                    logger.warning(f"API获取商品信息失败: {self._safe_str(e)}，尝试从数据库获取")

                    # API失败时，从数据库获取商品信息
                    try:
                        db_item_info = db_manager.get_item_info(self.cookie_id, item_id)
                        if db_item_info:
                            # 拼接商品标题和详情作为搜索文本
                            item_title_db = db_item_info.get('item_title', '') or ''
                            item_detail_db = db_item_info.get('item_detail', '') or ''

                            # 如果数据库中没有详情，尝试从外部API获取
                            if not item_detail_db.strip():
                                from config import config
                                auto_fetch_config = config.get('ITEM_DETAIL', {}).get('auto_fetch', {})

                                if auto_fetch_config.get('enabled', True):
                                    logger.info(f"数据库中商品详情为空，尝试从外部API获取: {item_id}")
                                    try:
                                        fetched_detail = await self.fetch_item_detail_from_api(item_id)
                                        if fetched_detail:
                                            # 保存获取到的详情
                                            await self.save_item_detail_only(item_id, fetched_detail)
                                            item_detail_db = fetched_detail
                                            logger.info(f"成功从外部API获取并保存商品详情: {item_id}")
                                        else:
                                            logger.warning(f"外部API未能获取到商品详情: {item_id}")
                                    except Exception as api_e:
                                        logger.warning(f"从外部API获取商品详情失败: {item_id}, 错误: {self._safe_str(api_e)}")
                                else:
                                    logger.debug(f"自动获取商品详情功能已禁用，跳过: {item_id}")

                            # 组合搜索文本：商品标题 + 商品详情
                            search_parts = []
                            if item_title_db.strip():
                                search_parts.append(item_title_db.strip())
                            if item_detail_db.strip():
                                search_parts.append(item_detail_db.strip())

                            if search_parts:
                                search_text = ' '.join(search_parts)
                                logger.info(f"使用数据库商品标题+详情作为搜索文本: 标题='{item_title_db}', 详情长度={len(item_detail_db)}")
                                logger.debug(f"完整搜索文本: {search_text[:200]}...")
                            else:
                                logger.warning(f"数据库中商品标题和详情都为空，且无法从API获取: {item_id}")
                                search_text = item_title or item_id
                        else:
                            logger.debug(f"数据库中未找到商品信息: {item_id}")
                            search_text = item_title or item_id

                    except Exception as db_e:
                        logger.debug(f"从数据库获取商品信息失败: {self._safe_str(db_e)}")
                        search_text = item_title or item_id

            if not search_text:
                search_text = item_id or "未知商品"

            logger.info(f"使用搜索文本匹配发货规则: {search_text[:100]}...")

            # 检查商品是否为多规格商品
            is_multi_spec = db_manager.get_item_multi_spec_status(self.cookie_id, item_id)
            spec_name = None
            spec_value = None

            # 如果是多规格商品且有订单ID，获取规格信息
            if is_multi_spec and order_id:
                logger.info(f"检测到多规格商品，获取订单规格信息: {order_id}")
                try:
                    order_detail = await self.fetch_order_detail_info(order_id)
                    if order_detail:
                        spec_name = order_detail.get('spec_name', '')
                        spec_value = order_detail.get('spec_value', '')
                        if spec_name and spec_value:
                            logger.info(f"获取到规格信息: {spec_name} = {spec_value}")
                        else:
                            logger.warning(f"未能获取到规格信息，将使用兜底匹配")
                    else:
                        logger.warning(f"获取订单详情失败，将使用兜底匹配")
                except Exception as e:
                    logger.error(f"获取订单规格信息失败: {self._safe_str(e)}，将使用兜底匹配")

            # 智能匹配发货规则：优先精确匹配，然后兜底匹配
            delivery_rules = []

            # 第一步：如果有规格信息，尝试精确匹配多规格发货规则
            if spec_name and spec_value:
                logger.info(f"尝试精确匹配多规格发货规则: {search_text[:50]}... [{spec_name}:{spec_value}]")
                delivery_rules = db_manager.get_delivery_rules_by_keyword_and_spec(search_text, spec_name, spec_value)

                if delivery_rules:
                    logger.info(f"✅ 找到精确匹配的多规格发货规则: {len(delivery_rules)}个")
                else:
                    logger.info(f"❌ 未找到精确匹配的多规格发货规则")

            # 第二步：如果精确匹配失败，尝试兜底匹配（普通发货规则）
            if not delivery_rules:
                logger.info(f"尝试兜底匹配普通发货规则: {search_text[:50]}...")
                delivery_rules = db_manager.get_delivery_rules_by_keyword(search_text)

                if delivery_rules:
                    logger.info(f"✅ 找到兜底匹配的普通发货规则: {len(delivery_rules)}个")
                else:
                    logger.info(f"❌ 未找到任何匹配的发货规则")

            if not delivery_rules:
                logger.warning(f"未找到匹配的发货规则: {search_text[:50]}...")
                return None

            # 使用第一个匹配的规则（按关键字长度降序排列，优先匹配更精确的规则）
            rule = delivery_rules[0]

            # 保存商品信息到数据库（需要有商品标题才保存）
            # 尝试获取商品标题
            item_title_for_save = None
            try:
                from db_manager import db_manager
                db_item_info = db_manager.get_item_info(self.cookie_id, item_id)
                if db_item_info:
                    item_title_for_save = db_item_info.get('item_title', '').strip()
            except:
                pass

            # 如果有商品标题，则保存商品信息
            if item_title_for_save:
                await self.save_item_info_to_db(item_id, search_text, item_title_for_save)
            else:
                logger.debug(f"跳过保存商品信息：缺少商品标题 - {item_id}")

            # 详细的匹配结果日志
            if rule.get('is_multi_spec'):
                if spec_name and spec_value:
                    logger.info(f"🎯 精确匹配多规格发货规则: {rule['keyword']} -> {rule['card_name']} [{rule['spec_name']}:{rule['spec_value']}]")
                    logger.info(f"📋 订单规格: {spec_name}:{spec_value} ✅ 匹配卡券规格: {rule['spec_name']}:{rule['spec_value']}")
                else:
                    logger.info(f"⚠️ 使用多规格发货规则但无订单规格信息: {rule['keyword']} -> {rule['card_name']} [{rule['spec_name']}:{rule['spec_value']}]")
            else:
                if spec_name and spec_value:
                    logger.info(f"🔄 兜底匹配普通发货规则: {rule['keyword']} -> {rule['card_name']} ({rule['card_type']})")
                    logger.info(f"📋 订单规格: {spec_name}:{spec_value} ➡️ 使用普通卡券兜底")
                else:
                    logger.info(f"✅ 匹配普通发货规则: {rule['keyword']} -> {rule['card_name']} ({rule['card_type']})")

            # 获取延时设置
            delay_seconds = rule.get('card_delay_seconds', 0)

            # 执行延时（不管是否确认发货，只要有延时设置就执行）
            if delay_seconds and delay_seconds > 0:
                logger.info(f"检测到发货延时设置: {delay_seconds}秒，开始延时...")
                await asyncio.sleep(delay_seconds)
                logger.info(f"延时完成")

            # 如果有订单ID，执行确认发货
            if order_id:
                # 检查是否启用自动确认发货
                if not self.is_auto_confirm_enabled():
                    logger.info(f"自动确认发货已关闭，跳过订单 {order_id}")
                else:
                    # 检查确认发货冷却时间
                    current_time = time.time()
                    should_confirm = True

                    if order_id in self.confirmed_orders:
                        last_confirm_time = self.confirmed_orders[order_id]
                        if current_time - last_confirm_time < self.order_confirm_cooldown:
                            logger.info(f"订单 {order_id} 已在 {self.order_confirm_cooldown} 秒内确认过，跳过重复确认")
                            should_confirm = False

                    if should_confirm:
                        logger.info(f"开始自动确认发货: 订单ID={order_id}")
                        confirm_result = await self.auto_confirm(order_id)
                        if confirm_result.get('success'):
                            self.confirmed_orders[order_id] = current_time
                            logger.info(f"🎉 自动确认发货成功！订单ID: {order_id}")
                        else:
                            logger.warning(f"⚠️ 自动确认发货失败: {confirm_result.get('error', '未知错误')}")
                            # 即使确认发货失败，也继续发送发货内容

            # 检查是否存在订单ID，只有存在订单ID才处理发货内容
            if order_id:
                # 开始处理发货内容
                logger.info(f"开始处理发货内容，规则: {rule['keyword']} -> {rule['card_name']} ({rule['card_type']})")

                delivery_content = None

                # 根据卡券类型处理发货内容
                if rule['card_type'] == 'api':
                    # API类型：调用API获取内容
                    delivery_content = await self._get_api_card_content(rule)

                elif rule['card_type'] == 'text':
                    # 固定文字类型：直接使用文字内容
                    delivery_content = rule['text_content']

                elif rule['card_type'] == 'data':
                    # 批量数据类型：获取并消费第一条数据
                    delivery_content = db_manager.consume_batch_data(rule['card_id'])

                if delivery_content:
                    # 处理备注信息和变量替换
                    final_content = self._process_delivery_content_with_description(delivery_content, rule.get('card_description', ''))

                    # 增加发货次数统计
                    db_manager.increment_delivery_times(rule['id'])
                    logger.info(f"自动发货成功: 规则ID={rule['id']}, 内容长度={len(final_content)}")
                    return final_content
                else:
                    logger.warning(f"获取发货内容失败: 规则ID={rule['id']}")
                    return None
            else:
                # 没有订单ID，记录日志但不处理发货内容
                logger.info(f"⚠️ 未检测到订单ID，跳过发货内容处理。规则: {rule['keyword']} -> {rule['card_name']} ({rule['card_type']})")
                return None

        except Exception as e:
            logger.error(f"自动发货失败: {self._safe_str(e)}")
            return None

    def _process_delivery_content_with_description(self, delivery_content: str, card_description: str) -> str:
        """处理发货内容和备注信息，实现变量替换"""
        try:
            # 如果没有备注信息，直接返回发货内容
            if not card_description or not card_description.strip():
                return delivery_content

            # 替换备注中的变量
            processed_description = card_description.replace('{DELIVERY_CONTENT}', delivery_content)

            # 如果备注中包含变量替换，返回处理后的备注
            if '{DELIVERY_CONTENT}' in card_description:
                return processed_description
            else:
                # 如果备注中没有变量，将备注和发货内容组合
                return f"{processed_description}\n\n{delivery_content}"

        except Exception as e:
            logger.error(f"处理备注信息失败: {e}")
            # 出错时返回原始发货内容
            return delivery_content

    async def _get_api_card_content(self, rule, retry_count=0):
        """调用API获取卡券内容，支持重试机制"""
        max_retries = 4

        if retry_count >= max_retries:
            logger.error(f"API调用失败，已达到最大重试次数({max_retries})")
            return None

        try:
            import aiohttp
            import json

            api_config = rule.get('api_config')
            if not api_config:
                logger.error(f"API配置为空，规则ID: {rule.get('id')}, 卡券名称: {rule.get('card_name')}")
                logger.debug(f"规则详情: {rule}")
                return None

            # 解析API配置
            if isinstance(api_config, str):
                api_config = json.loads(api_config)

            url = api_config.get('url')
            method = api_config.get('method', 'GET').upper()
            timeout = api_config.get('timeout', 10)
            headers = api_config.get('headers', '{}')
            params = api_config.get('params', '{}')

            # 解析headers和params
            if isinstance(headers, str):
                headers = json.loads(headers)
            if isinstance(params, str):
                params = json.loads(params)

            retry_info = f" (重试 {retry_count + 1}/{max_retries})" if retry_count > 0 else ""
            logger.info(f"调用API获取卡券: {method} {url}{retry_info}")

            # 确保session存在
            if not self.session:
                await self.create_session()

            # 发起HTTP请求
            timeout_obj = aiohttp.ClientTimeout(total=timeout)

            if method == 'GET':
                async with self.session.get(url, headers=headers, params=params, timeout=timeout_obj) as response:
                    status_code = response.status
                    response_text = await response.text()
            elif method == 'POST':
                async with self.session.post(url, headers=headers, json=params, timeout=timeout_obj) as response:
                    status_code = response.status
                    response_text = await response.text()
            else:
                logger.error(f"不支持的HTTP方法: {method}")
                return None

            if status_code == 200:
                # 尝试解析JSON响应，如果失败则使用原始文本
                try:
                    result = json.loads(response_text)
                    # 如果返回的是对象，尝试提取常见的内容字段
                    if isinstance(result, dict):
                        content = result.get('data') or result.get('content') or result.get('card') or str(result)
                    else:
                        content = str(result)
                except:
                    content = response_text

                logger.info(f"API调用成功，返回内容长度: {len(content)}")
                return content
            else:
                logger.warning(f"API调用失败: {status_code} - {response_text[:200]}...")

                # 如果是服务器错误(5xx)或请求超时，进行重试
                if status_code >= 500 or status_code == 408:
                    if retry_count < max_retries - 1:
                        wait_time = (retry_count + 1) * 2  # 递增等待时间: 2s, 4s, 6s
                        logger.info(f"等待 {wait_time} 秒后重试...")
                        await asyncio.sleep(wait_time)
                        return await self._get_api_card_content(rule, retry_count + 1)

                return None

        except (aiohttp.ClientTimeout, aiohttp.ClientError) as e:
            logger.warning(f"API调用网络异常: {self._safe_str(e)}")

            # 网络异常也进行重试
            if retry_count < max_retries - 1:
                wait_time = (retry_count + 1) * 2  # 递增等待时间
                logger.info(f"等待 {wait_time} 秒后重试...")
                await asyncio.sleep(wait_time)
                return await self._get_api_card_content(rule, retry_count + 1)
            else:
                logger.error(f"API调用网络异常，已达到最大重试次数: {self._safe_str(e)}")
                return None

        except Exception as e:
            logger.error(f"API调用异常: {self._safe_str(e)}")
            return None

    async def token_refresh_loop(self):
        """Token刷新循环"""
        while True:
            try:
                # 检查账号是否启用
                from cookie_manager import manager as cookie_manager
                if cookie_manager and not cookie_manager.get_cookie_status(self.cookie_id):
                    logger.info(f"【{self.cookie_id}】账号已禁用，停止Token刷新循环")
                    break

                current_time = time.time()
                if current_time - self.last_token_refresh_time >= self.token_refresh_interval:
                    logger.info("Token即将过期，准备刷新...")
                    new_token = await self.refresh_token()
                    if new_token:
                        logger.info(f"【{self.cookie_id}】Token刷新成功，准备重新建立连接...")
                        self.connection_restart_flag = True
                        if self.ws:
                            await self.ws.close()
                        break
                    else:
                        logger.error(f"【{self.cookie_id}】Token刷新失败，将在{self.token_retry_interval // 60}分钟后重试")
                        # 发送Token刷新失败通知
                        await self.send_token_refresh_notification("Token定时刷新失败，将自动重试", "token_scheduled_refresh_failed")
                        await asyncio.sleep(self.token_retry_interval)
                        continue
                await asyncio.sleep(60)
            except Exception as e:
                logger.error(f"Token刷新循环出错: {self._safe_str(e)}")
                await asyncio.sleep(60)

    async def create_chat(self, ws, toid, item_id='891198795482'):
        msg = {
            "lwp": "/r/SingleChatConversation/create",
            "headers": {
                "mid": generate_mid()
            },
            "body": [
                {
                    "pairFirst": f"{toid}@goofish",
                    "pairSecond": f"{self.myid}@goofish",
                    "bizType": "1",
                    "extension": {
                        "itemId": item_id
                    },
                    "ctx": {
                        "appVersion": "1.0",
                        "platform": "web"
                    }
                }
            ]
        }
        await ws.send(json.dumps(msg))

    async def send_msg(self, ws, cid, toid, text):
        text = {
            "contentType": 1,
            "text": {
                "text": text
            }
        }
        text_base64 = str(base64.b64encode(json.dumps(text).encode('utf-8')), 'utf-8')
        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {
                "mid": generate_mid()
            },
            "body": [
                {
                    "uuid": generate_uuid(),
                    "cid": f"{cid}@goofish",
                    "conversationType": 1,
                    "content": {
                        "contentType": 101,
                        "custom": {
                            "type": 1,
                            "data": text_base64
                        }
                    },
                    "redPointPolicy": 0,
                    "extension": {
                        "extJson": "{}"
                    },
                    "ctx": {
                        "appVersion": "1.0",
                        "platform": "web"
                    },
                    "mtags": {},
                    "msgReadStatusSetting": 1
                },
                {
                    "actualReceivers": [
                        f"{toid}@goofish",
                        f"{self.myid}@goofish"
                    ]
                }
            ]
        }
        await ws.send(json.dumps(msg))

    async def init(self, ws):
        # 如果没有token或者token过期，获取新token
        token_refresh_attempted = False
        if not self.current_token or (time.time() - self.last_token_refresh_time) >= self.token_refresh_interval:
            logger.info(f"【{self.cookie_id}】获取初始token...")
            token_refresh_attempted = True
            await self.refresh_token()

        if not self.current_token:
            logger.error("无法获取有效token，初始化失败")
            # 只有在没有尝试刷新token的情况下才发送通知，避免与refresh_token中的通知重复
            if not token_refresh_attempted:
                await self.send_token_refresh_notification("初始化时无法获取有效Token", "token_init_failed")
            else:
                logger.info("由于刚刚尝试过token刷新，跳过重复的初始化失败通知")
            raise Exception("Token获取失败")
            
        msg = {
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": APP_CONFIG.get('app_key'),
                "token": self.current_token,
                "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 DingTalk(2.1.5) OS(Windows/10) Browser(Chrome/133.0.0.0) DingWeb/2.1.5 IMPaaS DingWeb/2.1.5",
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self.device_id,
                "mid": generate_mid()
            }
        }
        await ws.send(json.dumps(msg))
        await asyncio.sleep(1)
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

    async def send_heartbeat(self, ws):
        """发送心跳包"""
        msg = {
            "lwp": "/!",
            "headers": {
                "mid": generate_mid()
            }
        }
        await ws.send(json.dumps(msg))
        self.last_heartbeat_time = time.time()

    async def heartbeat_loop(self, ws):
        """心跳循环"""
        while True:
            try:
                # 检查账号是否启用
                from cookie_manager import manager as cookie_manager
                if cookie_manager and not cookie_manager.get_cookie_status(self.cookie_id):
                    logger.info(f"【{self.cookie_id}】账号已禁用，停止心跳循环")
                    break

                await self.send_heartbeat(ws)
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                logger.error(f"心跳发送失败: {self._safe_str(e)}")
                break

    async def handle_heartbeat_response(self, message_data):
        """处理心跳响应"""
        try:
            if message_data.get("code") == 200:
                self.last_heartbeat_response = time.time()
                logger.debug("心跳响应正常")
                return True
        except Exception as e:
            logger.error(f"处理心跳响应出错: {self._safe_str(e)}")
        return False

    async def send_msg_once(self, toid, item_id, text):
        headers = {
            "Cookie": self.cookies_str,
            "Host": "wss-goofish.dingtalk.com",
            "Connection": "Upgrade",
            "Pragma": "no-cache",
            "Cache-Control": "no-cache",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "Origin": "https://www.goofish.com",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        # 兼容不同版本的websockets库
        try:
            async with websockets.connect(
                self.base_url,
                extra_headers=headers
            ) as websocket:
                await self._handle_websocket_connection(websocket, toid, item_id, text)
        except TypeError as e:
            # 安全地检查异常信息
            error_msg = self._safe_str(e)

            if "extra_headers" in error_msg:
                logger.warning("websockets库不支持extra_headers参数，使用兼容模式")
                # 使用兼容模式，通过subprotocols传递部分头信息
                async with websockets.connect(
                    self.base_url,
                    additional_headers=headers
                ) as websocket:
                    await self._handle_websocket_connection(websocket, toid, item_id, text)
            else:
                raise

    async def _create_websocket_connection(self, headers):
        """创建WebSocket连接，兼容不同版本的websockets库"""
        import websockets

        # 获取websockets版本用于调试
        websockets_version = getattr(websockets, '__version__', '未知')
        logger.debug(f"websockets库版本: {websockets_version}")

        try:
            # 尝试使用extra_headers参数
            return websockets.connect(
                self.base_url,
                extra_headers=headers
            )
        except Exception as e:
            # 捕获所有异常类型，不仅仅是TypeError
            error_msg = self._safe_str(e)
            logger.debug(f"extra_headers参数失败: {error_msg}")

            if "extra_headers" in error_msg or "unexpected keyword argument" in error_msg:
                logger.warning("websockets库不支持extra_headers参数，尝试additional_headers")
                # 使用additional_headers参数（较新版本）
                try:
                    return websockets.connect(
                        self.base_url,
                        additional_headers=headers
                    )
                except Exception as e2:
                    error_msg2 = self._safe_str(e2)
                    logger.debug(f"additional_headers参数失败: {error_msg2}")

                    if "additional_headers" in error_msg2 or "unexpected keyword argument" in error_msg2:
                        # 如果都不支持，则不传递headers
                        logger.warning("websockets库不支持headers参数，使用基础连接模式")
                        return websockets.connect(self.base_url)
                    else:
                        raise e2
            else:
                raise e

    async def _handle_websocket_connection(self, websocket, toid, item_id, text):
        """处理WebSocket连接的具体逻辑"""
        await self.init(websocket)
        await self.create_chat(websocket, toid, item_id)
        async for message in websocket:
            try:
                logger.info(f"【{self.cookie_id}】message: {message}")
                message = json.loads(message)
                cid = message["body"]["singleChatConversation"]["cid"]
                cid = cid.split('@')[0]
                await self.send_msg(websocket, cid, toid, text)
                logger.info(f'【{self.cookie_id}】send message')
                return
            except Exception as e:
                pass

    def is_chat_message(self, message):
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

    def is_sync_package(self, message_data):
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

    async def create_session(self):
        """创建aiohttp session"""
        if not self.session:
            # 创建带有cookies和headers的session
            headers = DEFAULT_HEADERS.copy()
            headers['cookie'] = self.cookies_str

            self.session = aiohttp.ClientSession(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30)
            )

    async def close_session(self):
        """关闭aiohttp session"""
        if self.session:
            await self.session.close()
            self.session = None

    async def get_api_reply(self, msg_time, user_url, send_user_id, send_user_name, item_id, send_message, chat_id):
        """调用API获取回复消息"""
        try:
            if not self.session:
                await self.create_session()

            api_config = AUTO_REPLY.get('api', {})
            timeout = aiohttp.ClientTimeout(total=api_config.get('timeout', 10))
            
            payload = {
                "cookie_id": self.cookie_id,
                "msg_time": msg_time,
                "user_url": user_url,
                "send_user_id": send_user_id,
                "send_user_name": send_user_name,
                "item_id": item_id,
                "send_message": send_message,
                "chat_id": chat_id
            }
            
            async with self.session.post(
                api_config.get('url', 'http://localhost:8080/xianyu/reply'),
                json=payload,
                timeout=timeout
            ) as response:
                result = await response.json()
                
                # 将code转换为字符串进行比较，或者直接用数字比较
                if str(result.get('code')) == '200' or result.get('code') == 200:
                    send_msg = result.get('data', {}).get('send_msg')
                    if send_msg:
                        # 格式化消息中的占位符
                        return send_msg.format(
                            send_user_id=payload['send_user_id'],
                            send_user_name=payload['send_user_name'],
                            send_message=payload['send_message']
                        )
                    else:
                        logger.warning("API返回成功但无回复消息")
                        return None
                else:
                    logger.warning(f"API返回错误: {result.get('msg', '未知错误')}")
                    return None
                    
        except asyncio.TimeoutError:
            logger.error("API调用超时")
            return None
        except Exception as e:
            logger.error(f"调用API出错: {self._safe_str(e)}")
            return None

    async def handle_message(self, message_data, websocket):
        """处理所有类型的消息"""
        try:
            # 检查账号是否启用
            from cookie_manager import manager as cookie_manager
            if cookie_manager and not cookie_manager.get_cookie_status(self.cookie_id):
                logger.debug(f"【{self.cookie_id}】账号已禁用，跳过消息处理")
                return

            # 发送确认消息
            try:
                message = message_data
                ack = {
                    "code": 200,
                    "headers": {
                        "mid": message["headers"]["mid"] if "mid" in message["headers"] else generate_mid(),
                        "sid": message["headers"]["sid"] if "sid" in message["headers"] else '',
                    }
                }
                if 'app-key' in message["headers"]:
                    ack["headers"]["app-key"] = message["headers"]["app-key"]
                if 'ua' in message["headers"]:
                    ack["headers"]["ua"] = message["headers"]["ua"]
                if 'dt' in message["headers"]:
                    ack["headers"]["dt"] = message["headers"]["dt"]
                await websocket.send(json.dumps(ack))
            except Exception as e:
                pass

            # 如果不是同步包消息，直接返回
            if not self.is_sync_package(message_data):
                return

            # 获取并解密数据
            sync_data = message_data["body"]["syncPushPackage"]["data"][0]
            
            # 检查是否有必要的字段
            if "data" not in sync_data:
                logger.debug("同步包中无data字段")
                return

            # 解密数据
            message = None
            try:
                data = sync_data["data"]
                try:
                    data = base64.b64decode(data).decode("utf-8")
                    parsed_data = json.loads(data)
                    # 处理未加密的消息（如系统提示等）
                    msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                    if isinstance(parsed_data, dict) and 'chatType' in parsed_data:
                        if 'operation' in parsed_data and 'content' in parsed_data['operation']:
                            content = parsed_data['operation']['content']
                            if 'sessionArouse' in content:
                                # 处理系统引导消息
                                logger.info(f"[{msg_time}] 【{self.cookie_id}】【系统】小闲鱼智能提示:")
                                if 'arouseChatScriptInfo' in content['sessionArouse']:
                                    for qa in content['sessionArouse']['arouseChatScriptInfo']:
                                        logger.info(f"  - {qa['chatScrip']}")
                            elif 'contentType' in content:
                                # 其他类型的未加密消息
                                logger.debug(f"[{msg_time}] 【{self.cookie_id}】【系统】其他类型消息: {content}")
                        return
                    else:
                        # 如果不是系统消息，将解析的数据作为message
                        message = parsed_data
                except Exception as e:
                    # 如果JSON解析失败，尝试解密
                    decrypted_data = decrypt(data)
                    message = json.loads(decrypted_data)
            except Exception as e:
                logger.error(f"消息解密失败: {self._safe_str(e)}")
                return

            # 确保message不为空
            if message is None:
                logger.error("消息解析后为空")
                return

            # 确保message是字典类型
            if not isinstance(message, dict):
                logger.error(f"消息格式错误，期望字典但得到: {type(message)}")
                logger.debug(f"消息内容: {message}")
                return

            # 安全地获取用户ID
            user_id = None
            try:
                message_1 = message.get("1")
                if isinstance(message_1, str) and '@' in message_1:
                    user_id = message_1.split('@')[0]
                elif isinstance(message_1, dict):
                    # 如果message['1']是字典，尝试其他方式提取user_id
                    user_id = "unknown_user"
                else:
                    user_id = "unknown_user"
            except Exception as e:
                logger.debug(f"提取用户ID失败: {self._safe_str(e)}")
                user_id = "unknown_user"



            # 安全地提取商品ID
            item_id = None
            try:
                if "1" in message and isinstance(message["1"], dict) and "10" in message["1"] and isinstance(message["1"]["10"], dict):
                    url_info = message["1"]["10"].get("reminderUrl", "")
                    if isinstance(url_info, str) and "itemId=" in url_info:
                        item_id = url_info.split("itemId=")[1].split("&")[0]

                # 如果没有提取到，使用辅助方法
                if not item_id:
                    item_id = self.extract_item_id_from_message(message)

                if not item_id:
                    item_id = f"auto_{user_id}_{int(time.time())}"
                    logger.debug(f"无法提取商品ID，使用默认值: {item_id}")

            except Exception as e:
                logger.error(f"提取商品ID时发生错误: {self._safe_str(e)}")
                item_id = f"auto_{user_id}_{int(time.time())}"
            # 处理订单状态消息
            try:
                logger.info(message)
                msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

                # 安全地检查订单状态
                red_reminder = None
                if isinstance(message, dict) and "3" in message and isinstance(message["3"], dict):
                    red_reminder = message["3"].get("redReminder")

                if red_reminder == '等待买家付款':
                    user_url = f'https://www.goofish.com/personal?userId={user_id}'
                    logger.info(f'[{msg_time}] 【系统】等待买家 {user_url} 付款')
                    return
                elif red_reminder == '交易关闭':
                    user_url = f'https://www.goofish.com/personal?userId={user_id}'
                    logger.info(f'[{msg_time}] 【系统】买家 {user_url} 交易关闭')
                    return
                elif red_reminder == '等待卖家发货':
                    user_url = f'https://www.goofish.com/personal?userId={user_id}'
                    logger.info(f'[{msg_time}] 【系统】交易成功 {user_url} 等待卖家发货')
                    # return
            except:
                pass

            # 判断是否为聊天消息
            if not self.is_chat_message(message):
                logger.debug("非聊天消息")
                return

            # 处理聊天消息
            try:
                # 安全地提取聊天消息信息
                if not (isinstance(message, dict) and "1" in message and isinstance(message["1"], dict)):
                    logger.error("消息格式错误：缺少必要的字段结构")
                    return

                message_1 = message["1"]
                if not isinstance(message_1.get("10"), dict):
                    logger.error("消息格式错误：缺少消息详情字段")
                    return

                create_time = int(message_1.get("5", 0))
                message_10 = message_1["10"]
                send_user_name = message_10.get("senderNick", message_10.get("reminderTitle", "未知用户"))
                send_user_id = message_10.get("senderUserId", "unknown")
                send_message = message_10.get("reminderContent", "")

                chat_id_raw = message_1.get("2", "")
                chat_id = chat_id_raw.split('@')[0] if '@' in str(chat_id_raw) else str(chat_id_raw)

            except Exception as e:
                logger.error(f"提取聊天消息信息失败: {self._safe_str(e)}")
                return

            # 格式化消息时间
            msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(create_time/1000))



            # 判断消息方向
            if send_user_id == self.myid:
                logger.info(f"[{msg_time}] 【手动发出】 商品({item_id}): {send_message}")


                return
            else:
                logger.info(f"[{msg_time}] 【收到】用户: {send_user_name} (ID: {send_user_id}), 商品({item_id}): {send_message}")





            # 自动回复消息
            if not AUTO_REPLY.get('enabled', True):
                logger.info(f"[{msg_time}] 【{self.cookie_id}】【系统】自动回复已禁用")
                return

            # 构造用户URL
            user_url = f'https://www.goofish.com/personal?userId={send_user_id}'
                
            reply = None
            # 判断是否启用API回复
            if AUTO_REPLY.get('api', {}).get('enabled', False):
                reply = await self.get_api_reply(
                    msg_time, user_url, send_user_id, send_user_name,
                    item_id, send_message, chat_id
                )
                if not reply:
                    logger.error(f"[{msg_time}] 【API调用失败】用户: {send_user_name} (ID: {send_user_id}), 商品({item_id}): {send_message}")
            
            if send_message == '[我已拍下，待付款]':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】系统消息不处理')
                return
            elif send_message == '[你关闭了订单，钱款已原路退返]':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】系统消息不处理')
                return
            elif send_message == '发来一条消息':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】系统通知消息不处理')
                return
            elif send_message == '发来一条新消息':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】系统通知消息不处理')
                return
            elif send_message == '[买家确认收货，交易成功]':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】交易完成消息不处理')
                return
            elif send_message == '快给ta一个评价吧~' or send_message == '快给ta一个评价吧～':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】评价提醒消息不处理')
                return
            elif send_message == '卖家人不错？送Ta闲鱼小红花':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】小红花提醒消息不处理')
                return
            elif send_message == '[你已确认收货，交易成功]':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】买家确认收货消息不处理')
                return
            elif send_message == '[你已发货]':
                logger.info(f'[{msg_time}] 【{self.cookie_id}】发货确认消息不处理')
                return
            # 检查是否为自动发货触发消息
            elif self._is_auto_delivery_trigger(send_message):
                # 使用统一的自动发货处理方法
                await self._handle_auto_delivery(websocket, message, send_user_name, send_user_id,
                                               item_id, chat_id, msg_time)
                return

            elif send_message == '[卡片消息]':
                # 检查是否为"我已小刀，待刀成"的卡片消息
                try:
                    # 从消息中提取卡片内容
                    card_title = None
                    if isinstance(message, dict) and "1" in message and isinstance(message["1"], dict):
                        message_1 = message["1"]
                        if "6" in message_1 and isinstance(message_1["6"], dict):
                            message_6 = message_1["6"]
                            if "3" in message_6 and isinstance(message_6["3"], dict):
                                message_6_3 = message_6["3"]
                                if "5" in message_6_3:
                                    # 解析JSON内容
                                    try:
                                        card_content = json.loads(message_6_3["5"])
                                        if "dxCard" in card_content and "item" in card_content["dxCard"]:
                                            card_item = card_content["dxCard"]["item"]
                                            if "main" in card_item and "exContent" in card_item["main"]:
                                                ex_content = card_item["main"]["exContent"]
                                                card_title = ex_content.get("title", "")
                                    except (json.JSONDecodeError, KeyError) as e:
                                        logger.debug(f"解析卡片消息失败: {e}")

                    # 检查是否为"我已小刀，待刀成"
                    if card_title == "我已小刀，待刀成":
                        logger.info(f'[{msg_time}] 【{self.cookie_id}】【系统】检测到"我已小刀，待刀成"，准备自动免拼发货')
                        # 提取订单ID
                        order_id = self._extract_order_id(message)
                        if order_id:
                            # 延迟2秒后执行免拼发货
                            logger.info(f'[{msg_time}] 【{self.cookie_id}】延迟2秒后执行免拼发货...')
                            await asyncio.sleep(2)
                            # 调用自动免拼发货方法
                            result = await self.auto_freeshipping(order_id, item_id, send_user_id)
                            if result.get('success'):
                                logger.info(f'[{msg_time}] 【{self.cookie_id}】✅ 自动免拼发货成功')
                            else:
                                logger.warning(f'[{msg_time}] 【{self.cookie_id}】❌ 自动免拼发货失败: {result.get("error", "未知错误")}')
                            await self._handle_auto_delivery(websocket, message, send_user_name, send_user_id,
                                               item_id, chat_id, msg_time)
                            return
                        else:
                            logger.warning(f'[{msg_time}] 【{self.cookie_id}】❌ 未能提取到订单ID，无法执行免拼发货')
                        return
                    else:
                        logger.info(f'[{msg_time}] 【{self.cookie_id}】收到卡片消息，标题: {card_title or "未知"}')

                except Exception as e:
                    logger.error(f"处理卡片消息异常: {self._safe_str(e)}")

                # 如果不是目标卡片消息，继续正常处理流程
            # 记录回复来源
            reply_source = 'API'  # 默认假设是API回复

            # 如果API回复失败或未启用API，按新的优先级顺序处理
            if not reply:
                # 1. 首先尝试关键词匹配（传入商品ID）
                reply = await self.get_keyword_reply(send_user_name, send_user_id, send_message, item_id)
                if reply:
                    reply_source = '关键词'  # 标记为关键词回复
                else:
                    # 2. 关键词匹配失败，如果AI开关打开，尝试AI回复
                    reply = await self.get_ai_reply(send_user_name, send_user_id, send_message, item_id, chat_id)
                    if reply:
                        reply_source = 'AI'  # 标记为AI回复
                    else:
                        # 3. 最后使用默认回复
                        reply = await self.get_default_reply(send_user_name, send_user_id, send_message)
                        reply_source = '默认'  # 标记为默认回复

            # 注意：这里只有商品ID，没有标题和详情，根据新的规则不保存到数据库
            # 商品信息会在其他有完整信息的地方保存（如发货规则匹配时）
            # 发送通知
            await self.send_notification(send_user_name, send_user_id, send_message, item_id)

            # 如果有回复内容，发送消息
            if reply:
                await self.send_msg(websocket, chat_id, send_user_id, reply)
                # 记录发出的消息
                msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                logger.info(f"[{msg_time}] 【{reply_source}发出】用户: {send_user_name} (ID: {send_user_id}), 商品({item_id}): {reply}")
            else:
                msg_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                logger.info(f"[{msg_time}] 【{self.cookie_id}】【系统】未找到匹配的回复规则，不回复")
            
        except Exception as e:
            logger.error(f"处理消息时发生错误: {self._safe_str(e)}")
            logger.debug(f"原始消息: {message_data}")

    async def main(self):
        """主程序入口"""
        try:
            logger.info(f"【{self.cookie_id}】开始启动XianyuLive主程序...")
            await self.create_session()  # 创建session
            logger.info(f"【{self.cookie_id}】Session创建完成，开始WebSocket连接循环...")

            while True:
                try:
                    # 检查账号是否启用
                    from cookie_manager import manager as cookie_manager
                    if cookie_manager and not cookie_manager.get_cookie_status(self.cookie_id):
                        logger.info(f"【{self.cookie_id}】账号已禁用，停止主循环")
                        break

                    headers = WEBSOCKET_HEADERS.copy()
                    headers['Cookie'] = self.cookies_str

                    logger.info(f"【{self.cookie_id}】准备建立WebSocket连接到: {self.base_url}")
                    logger.debug(f"【{self.cookie_id}】WebSocket headers: {headers}")

                    # 兼容不同版本的websockets库
                    async with await self._create_websocket_connection(headers) as websocket:
                        logger.info(f"【{self.cookie_id}】WebSocket连接建立成功！")
                        self.ws = websocket

                        logger.info(f"【{self.cookie_id}】开始初始化WebSocket连接...")
                        await self.init(websocket)
                        logger.info(f"【{self.cookie_id}】WebSocket初始化完成！")

                        # 启动心跳任务
                        logger.info(f"【{self.cookie_id}】启动心跳任务...")
                        self.heartbeat_task = asyncio.create_task(self.heartbeat_loop(websocket))

                        # 启动token刷新任务
                        logger.info(f"【{self.cookie_id}】启动token刷新任务...")
                        self.token_refresh_task = asyncio.create_task(self.token_refresh_loop())

                        logger.info(f"【{self.cookie_id}】开始监听WebSocket消息...")

                        async for message in websocket:
                            try:
                                message_data = json.loads(message)

                                # 处理心跳响应
                                if await self.handle_heartbeat_response(message_data):
                                    continue

                                # 处理其他消息
                                await self.handle_message(message_data, websocket)

                            except Exception as e:
                                logger.error(f"处理消息出错: {self._safe_str(e)}")
                                continue

                except Exception as e:
                    logger.error(f"WebSocket连接异常: {self._safe_str(e)}")
                    if self.heartbeat_task:
                        self.heartbeat_task.cancel()
                    if self.token_refresh_task:
                        self.token_refresh_task.cancel()
                    await asyncio.sleep(5)  # 等待5秒后重试
                    continue
        finally:
            await self.close_session()  # 确保关闭session

    async def get_item_list_info(self, page_number=1, page_size=20, retry_count=0):
        """获取商品信息，自动处理token失效的情况

        Args:
            page_number (int): 页码，从1开始
            page_size (int): 每页数量，默认20
            retry_count (int): 重试次数，内部使用
        """
        if retry_count >= 4:  # 最多重试3次
            logger.error("获取商品信息失败，重试次数过多")
            return {"error": "获取商品信息失败，重试次数过多"}

        # 如果是重试（retry_count > 0），强制刷新token
        if retry_count > 0:
            old_token = trans_cookies(self.cookies_str).get('_m_h5_tk', '').split('_')[0] if trans_cookies(self.cookies_str).get('_m_h5_tk') else ''
            logger.info(f"重试第{retry_count}次，强制刷新token... 当前_m_h5_tk: {old_token}")
            await self.refresh_token()
            new_token = trans_cookies(self.cookies_str).get('_m_h5_tk', '').split('_')[0] if trans_cookies(self.cookies_str).get('_m_h5_tk') else ''
            logger.info(f"重试刷新token完成，新的_m_h5_tk: {new_token}")
        else:
            # 确保使用最新的token（首次调用时的正常逻辑）
            if not self.current_token or (time.time() - self.last_token_refresh_time) >= self.token_refresh_interval:
                old_token = trans_cookies(self.cookies_str).get('_m_h5_tk', '').split('_')[0] if trans_cookies(self.cookies_str).get('_m_h5_tk') else ''
                logger.info(f"Token过期或不存在，刷新token... 当前_m_h5_tk: {old_token}")
                await self.refresh_token()
                new_token = trans_cookies(self.cookies_str).get('_m_h5_tk', '').split('_')[0] if trans_cookies(self.cookies_str).get('_m_h5_tk') else ''
                logger.info(f"Token刷新完成，新的_m_h5_tk: {new_token}")

        # 确保session已创建
        if not self.session:
            await self.create_session()

        params = {
            'jsv': '2.7.2',
            'appKey': '34839810',
            't': str(int(time.time()) * 1000),
            'sign': '',
            'v': '1.0',
            'type': 'originaljson',
            'accountSite': 'xianyu',
            'dataType': 'json',
            'timeout': '20000',
            'api': 'mtop.idle.web.xyh.item.list',
            'sessionOption': 'AutoLoginOnly',
            'spm_cnt': 'a21ybx.im.0.0',
            'spm_pre': 'a21ybx.collection.menu.1.272b5141NafCNK'
        }

        data = {
            'needGroupInfo': False,
            'pageNumber': page_number,
            'pageSize': page_size,
            'groupName': '在售',
            'groupId': '58877261',
            'defaultGroup': True,
            "userId": self.myid
        }

        # 始终从最新的cookies中获取_m_h5_tk token（刷新后cookies会被更新）
        token = trans_cookies(self.cookies_str).get('_m_h5_tk', '').split('_')[0] if trans_cookies(self.cookies_str).get('_m_h5_tk') else ''

        logger.warning(f"准备获取商品列表，token: {token}")
        if token:
            logger.debug(f"使用cookies中的_m_h5_tk token: {token}")
        else:
            logger.warning("cookies中没有找到_m_h5_tk token")

        # 生成签名
        data_val = json.dumps(data, separators=(',', ':'))
        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign

        try:
            async with self.session.post(
                'https://h5api.m.goofish.com/h5/mtop.idle.web.xyh.item.list/1.0/',
                params=params,
                data={'data': data_val}
            ) as response:
                res_json = await response.json()

                # 检查并更新Cookie
                if 'set-cookie' in response.headers:
                    new_cookies = {}
                    for cookie in response.headers.getall('set-cookie', []):
                        if '=' in cookie:
                            name, value = cookie.split(';')[0].split('=', 1)
                            new_cookies[name.strip()] = value.strip()
                    
                    # 更新cookies
                    if new_cookies:
                        self.cookies.update(new_cookies)
                        # 生成新的cookie字符串
                        self.cookies_str = '; '.join([f"{k}={v}" for k, v in self.cookies.items()])
                        # 更新数据库中的Cookie
                        await self.update_config_cookies()
                        logger.debug("已更新Cookie到数据库")

                logger.info(f"商品信息获取响应: {res_json}")

                # 检查响应是否成功
                if res_json.get('ret') and res_json['ret'][0] == 'SUCCESS::调用成功':
                    items_data = res_json.get('data', {})
                    # 从cardList中提取商品信息
                    card_list = items_data.get('cardList', [])

                    # 解析cardList中的商品信息
                    items_list = []
                    for card in card_list:
                        card_data = card.get('cardData', {})
                        if card_data:
                            # 提取商品基本信息
                            item_info = {
                                'id': card_data.get('id', ''),
                                'title': card_data.get('title', ''),
                                'price': card_data.get('priceInfo', {}).get('price', ''),
                                'price_text': card_data.get('priceInfo', {}).get('preText', '') + card_data.get('priceInfo', {}).get('price', ''),
                                'category_id': card_data.get('categoryId', ''),
                                'auction_type': card_data.get('auctionType', ''),
                                'item_status': card_data.get('itemStatus', 0),
                                'detail_url': card_data.get('detailUrl', ''),
                                'pic_info': card_data.get('picInfo', {}),
                                'detail_params': card_data.get('detailParams', {}),
                                'track_params': card_data.get('trackParams', {}),
                                'item_label_data': card_data.get('itemLabelDataVO', {}),
                                'card_type': card.get('cardType', 0)
                            }
                            items_list.append(item_info)

                    logger.info(f"成功获取到 {len(items_list)} 个商品")

                    # 打印商品详细信息到控制台
                    print("\n" + "="*80)
                    print(f"📦 账号 {self.myid} 的商品列表 (第{page_number}页，{len(items_list)} 个商品)")
                    print("="*80)

                    for i, item in enumerate(items_list, 1):
                        print(f"\n🔸 商品 {i}:")
                        print(f"   商品ID: {item.get('id', 'N/A')}")
                        print(f"   商品标题: {item.get('title', 'N/A')}")
                        print(f"   价格: {item.get('price_text', 'N/A')}")
                        print(f"   分类ID: {item.get('category_id', 'N/A')}")
                        print(f"   商品状态: {item.get('item_status', 'N/A')}")
                        print(f"   拍卖类型: {item.get('auction_type', 'N/A')}")
                        print(f"   详情链接: {item.get('detail_url', 'N/A')}")
                        if item.get('pic_info'):
                            pic_info = item['pic_info']
                            print(f"   图片信息: {pic_info.get('width', 'N/A')}x{pic_info.get('height', 'N/A')}")
                            print(f"   图片链接: {pic_info.get('picUrl', 'N/A')}")
                        print(f"   完整信息: {json.dumps(item, ensure_ascii=False, indent=2)}")

                    print("\n" + "="*80)
                    print("✅ 商品列表获取完成")
                    print("="*80)

                    # 自动保存商品信息到数据库
                    if items_list:
                        saved_count = await self.save_items_list_to_db(items_list)
                        logger.info(f"已将 {saved_count} 个商品信息保存到数据库")

                    return {
                        "success": True,
                        "page_number": page_number,
                        "page_size": page_size,
                        "current_count": len(items_list),
                        "items": items_list,
                        "saved_count": saved_count if items_list else 0,
                        "raw_data": items_data  # 保留原始数据以备调试
                    }
                else:
                    # 检查是否是token失效
                    error_msg = res_json.get('ret', [''])[0] if res_json.get('ret') else ''
                    if 'FAIL_SYS_TOKEN_EXOIRED' in error_msg or 'token' in error_msg.lower():
                        logger.warning(f"Token失效，准备重试: {error_msg}")
                        await asyncio.sleep(0.5)
                        return await self.get_item_list_info(page_number, page_size, retry_count + 1)
                    else:
                        logger.error(f"获取商品信息失败: {res_json}")
                        return {"error": f"获取商品信息失败: {error_msg}"}

        except Exception as e:
            logger.error(f"商品信息API请求异常: {self._safe_str(e)}")
            await asyncio.sleep(0.5)
            return await self.get_item_list_info(page_number, page_size, retry_count + 1)

    async def get_all_items(self, page_size=20, max_pages=None):
        """获取所有商品信息（自动分页）

        Args:
            page_size (int): 每页数量，默认20
            max_pages (int): 最大页数限制，None表示无限制

        Returns:
            dict: 包含所有商品信息的字典
        """
        all_items = []
        page_number = 1
        total_saved = 0

        logger.info(f"开始获取所有商品信息，每页{page_size}条")

        while True:
            if max_pages and page_number > max_pages:
                logger.info(f"达到最大页数限制 {max_pages}，停止获取")
                break

            logger.info(f"正在获取第 {page_number} 页...")
            result = await self.get_item_list_info(page_number, page_size)

            if not result.get("success"):
                logger.error(f"获取第 {page_number} 页失败: {result}")
                break

            current_items = result.get("items", [])
            if not current_items:
                logger.info(f"第 {page_number} 页没有数据，获取完成")
                break

            all_items.extend(current_items)
            total_saved += result.get("saved_count", 0)

            logger.info(f"第 {page_number} 页获取到 {len(current_items)} 个商品")

            # 如果当前页商品数量少于页面大小，说明已经是最后一页
            if len(current_items) < page_size:
                logger.info(f"第 {page_number} 页商品数量({len(current_items)})少于页面大小({page_size})，获取完成")
                break

            page_number += 1

            # 添加延迟避免请求过快
            await asyncio.sleep(1)

        logger.info(f"所有商品获取完成，共 {len(all_items)} 个商品，保存了 {total_saved} 个")

        return {
            "success": True,
            "total_pages": page_number,
            "total_count": len(all_items),
            "total_saved": total_saved,
            "items": all_items
        }

if __name__ == '__main__':
    cookies_str = os.getenv('COOKIES_STR')
    xianyuLive = XianyuLive(cookies_str)
    asyncio.run(xianyuLive.main())
