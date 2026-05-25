"""
亦凡API处理模块
负责处理亦凡卡券API相关的所有逻辑，包括：
- 亦凡API卡券获取
- 使用账号调用亦凡API
- 充值账号询问流程
"""

import asyncio
import json
import time
import hashlib
import aiohttp
from loguru import logger


class YifanApiHandler:
    """亦凡API处理器"""
    
    def __init__(self, parent):
        """
        初始化亦凡API处理器
        
        Args:
            parent: AutoDeliveryHandler或XianyuLive实例，用于访问共享资源
        """
        self.parent = parent
    
    # ==================== 属性代理 ====================
    
    @property
    def cookie_id(self):
        return self.parent.cookie_id
    
    @property
    def session(self):
        return self.parent.session
    
    @property
    def ws(self):
        return self.parent.ws
    
    @property
    def yifan_account_lock(self):
        return self.parent.yifan_account_lock
    
    @property
    def yifan_account_waiting(self):
        return self.parent.yifan_account_waiting
    
    # ==================== 辅助方法代理 ====================
    
    def _safe_str(self, obj):
        return self.parent._safe_str(obj)
    
    async def create_session(self):
        return await self.parent.create_session()
    
    async def send_msg(self, websocket, chat_id, send_user_id, content):
        return await self.parent.send_msg(websocket, chat_id, send_user_id, content)
    
    async def send_notification(self, send_user_name, send_user_id, content, item_id, chat_id):
        return await self.parent.send_notification(send_user_name, send_user_id, content, item_id, chat_id)


    # ==================== 亦凡API卡券获取 ====================

    async def get_yifan_api_card_content(self, rule, order_id=None, item_id=None, buyer_id=None, chat_id=None):
        """调用亦凡卡劵API获取内容"""
        try:
            # 获取全局配置
            from app.services.xianyu.xianyu_async import YIFAN_API

            # 获取API配置（存储在api_config字段中）
            api_config = rule.get('api_config')
            if not api_config:
                logger.error(f"亦凡API配置为空，规则ID: {rule.get('id')}, 卡券名称: {rule.get('card_name')}")
                return None

            # 解析API配置
            if isinstance(api_config, str):
                api_config = json.loads(api_config)

            # 亦凡API配置直接存储在api_config字段中
            user_id = api_config.get('user_id')
            user_key = api_config.get('user_key')
            goods_id = api_config.get('goods_id')
            # 回调地址：优先使用卡券配置中的，如果没有则从全局配置读取，最后使用默认地址
            callback_url = (api_config.get('callback_url') or '').strip() or (YIFAN_API.get('callback_url') or '').strip() or 'http://116.196.116.76/yifan.php'
            require_account = api_config.get('require_account', False)

            if not user_id or not user_key or not goods_id:
                logger.error(f"亦凡API配置不完整，规则ID: {rule.get('id')}")
                return None

            # 如果需要充值账号，先进行账号询问和确认流程
            recharge_account = None
            if require_account:
                logger.info(f"亦凡API需要充值账号，开始询问流程")
                recharge_account = await self.ask_for_recharge_account(chat_id, buyer_id, rule, order_id, item_id)
                if recharge_account == "__WAITING_ACCOUNT__":
                    # 已设置等待状态，暂时中断发货流程
                    logger.info(f"已设置等待账号输入状态，暂停发货流程")
                    return None
                elif not recharge_account:
                    logger.error(f"获取充值账号失败，取消发货")
                    return None
                logger.info(f"获取到充值账号: {recharge_account}")

            # 构建API请求参数（所有值都转换为字符串，避免空格问题）
            timestamp = str(int(time.time()))
            params = {
                'userid': str(user_id),
                'timestamp': timestamp,
                'goodsid': str(goods_id),
                'buynum': '1',
            }

            # 如果有回调地址，添加到参数中（签名之前添加）
            if callback_url and callback_url.strip():
                params['callbackurl'] = str(callback_url).strip()

            # 如果有充值账号，添加到参数中
            if recharge_account:
                params['attach'] = str(recharge_account).strip()

            # 生成签名
            sign_params = {k: str(v).strip() for k, v in params.items() if v is not None and str(v).strip() != ''}
            sorted_keys = sorted(sign_params.keys())
            sign_string = '&'.join([f"{key}={sign_params[key]}" for key in sorted_keys])
            sign_string += user_key
            
            logger.info(f"亦凡API签名字符串: {sign_string}")
            
            sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest().lower()
            params['sign'] = sign

            logger.info(f"调用亦凡API: 商户ID={user_id}, 商品ID={goods_id}, 充值账号={recharge_account}, 回调URL={callback_url if callback_url else '无'}")

            # 确保session存在
            if not self.session:
                await self.create_session()

            # 发起API请求（使用data而不是json，发送form格式）
            api_url = "http://price.78shuk.top/dockapiv3/order/create"
            
            timeout_obj = aiohttp.ClientTimeout(total=30)
            async with self.session.post(api_url, data=params, timeout=timeout_obj) as response:
                status_code = response.status
                response_text = await response.text()

                logger.info(f"亦凡API返回状态码: {status_code}, 响应: {response_text}")

                if status_code == 200:
                    try:
                        result = json.loads(response_text)
                        # 根据亦凡API的返回格式处理：code为1表示成功
                        if result.get('code') == 1:
                            # 提取订单信息
                            data = result.get('data', {})
                            order_no = data.get('orderno', '')
                            us_order_no = data.get('usorderno', '')
                            
                            # 构建成功消息
                            success_msg = f"✅ 自动发货订单已提交成功\n\n"
                            success_msg += f"📋 订单信息：\n"
                            success_msg += f"平台订单号: {order_no}\n"
                            if us_order_no:
                                success_msg += f"商家订单号: {us_order_no}\n"
                            
                            # 添加查询地址（从全局配置读取）
                            query_url = YIFAN_API.get('query_url', 'http://116.196.116.76/yifan.php')
                            success_msg += f"\n🔍 查询卡密：\n"
                            success_msg += f"{query_url}\n"
                            success_msg += f"(输入订单号查询)\n"
                            
                            # 添加提示信息
                            success_msg += f"\n⏰ 温馨提示：\n"
                            success_msg += f"订单处理需要一定时间，请耐心等待。\n"
                            success_msg += f"如果1小时后仍未看到卡密信息，\n"
                            success_msg += f"请联系客服处理。"
                            
                            logger.info(f"亦凡API调用成功: order_no={order_no}")
                            
                            # 将亦凡订单号记录到数据库（用于后续回调匹配）
                            if order_id and order_no:
                                try:
                                    from common.db.compat import db_manager
                                    # 更新订单的亦凡订单号和chat_id
                                    db_manager.update_order_yifan_status(
                                        order_id=order_id,
                                        yifan_orderno=order_no,
                                        delivery_status='processing'
                                    )
                                    if chat_id:
                                        db_manager.update_order_chat_id(order_id, chat_id)
                                    logger.info(f"已记录亦凡订单信息: order_id={order_id}, yifan_orderno={order_no}")
                                except Exception as e:
                                    logger.error(f"记录亦凡订单信息失败: {e}")
                            
                            return success_msg
                        else:
                            # code不为1，下单失败，需要通知用户
                            error_msg = result.get('msg', '未知错误')
                            logger.error(f"亦凡API调用失败: code={result.get('code')}, msg={error_msg}")
                            
                            # 发送通知给用户
                            if chat_id and buyer_id:
                                notification_msg = f"❌ 自动发货失败\n错误信息: {error_msg}\n请联系客服处理"
                                await self.send_notification("系统", buyer_id, notification_msg, item_id or "unknown", chat_id)
                            
                            return None
                    except Exception as e:
                        logger.error(f"解析亦凡API返回失败: {self._safe_str(e)}")
                        return None
                else:
                    logger.error(f"亦凡API调用失败: HTTP {status_code} - {response_text[:200]}")
                    return None

        except Exception as e:
            logger.error(f"亦凡API调用异常: {self._safe_str(e)}")
            return None


    async def call_yifan_api_with_account(self, rule, account, order_id=None, item_id=None, buyer_id=None, chat_id=None):
        """使用确认的账号调用亦凡API"""
        try:
            # 获取API配置
            api_config = rule.get('api_config')
            if not api_config:
                logger.error(f"亦凡API配置为空")
                return None

            # 解析API配置
            if isinstance(api_config, str):
                api_config = json.loads(api_config)

            # 亦凡API配置直接存储在api_config字段中
            user_id = api_config.get('user_id')
            user_key = api_config.get('user_key')
            goods_id = api_config.get('goods_id')
            callback_url = api_config.get('callback_url', '')

            if not user_id or not user_key or not goods_id:
                logger.error(f"亦凡API配置不完整")
                return None

            # 构建API请求参数（所有值都转换为字符串，避免空格问题）
            timestamp = str(int(time.time()))
            params = {
                'userid': str(user_id),
                'timestamp': timestamp,
                'goodsid': str(goods_id),
                'buynum': '1',
                'attach': str(account).strip()  # 充值账号，去除首尾空格
            }

            # 如果有回调地址，添加到参数中（签名之前添加）
            if callback_url and callback_url.strip():
                params['callbackurl'] = str(callback_url).strip()

            # 生成签名（确保参数值没有空格）
            sign_params = {k: str(v).strip() for k, v in params.items() if v is not None and str(v).strip() != ''}
            sorted_keys = sorted(sign_params.keys())
            sign_string = '&'.join([f"{key}={sign_params[key]}" for key in sorted_keys])
            sign_string += user_key
            
            logger.info(f"亦凡API签名字符串: {sign_string}")
            
            sign = hashlib.md5(sign_string.encode('utf-8')).hexdigest().lower()
            params['sign'] = sign

            logger.info(f"调用亦凡API: 商户ID={user_id}, 商品ID={goods_id}, 充值账号={account}, 回调URL={callback_url if callback_url else '无'}")

            # 确保session存在
            if not self.session:
                await self.create_session()

            # 发起API请求（使用data而不是json，发送form格式）
            api_url = "http://price.78shuk.top/dockapiv3/order/create"
            
            timeout_obj = aiohttp.ClientTimeout(total=30)
            async with self.session.post(api_url, data=params, timeout=timeout_obj) as response:
                status_code = response.status
                response_text = await response.text()

                logger.info(f"亦凡API返回状态码: {status_code}, 响应: {response_text}")

                if status_code == 200:
                    try:
                        result = json.loads(response_text)
                        if result.get('code') == 1:
                            # 下单成功
                            data = result.get('data', {})
                            order_no = data.get('orderno', '')
                            us_order_no = data.get('usorderno', '')
                            
                            success_msg = f"✅ 下单成功\n"
                            success_msg += f"订单号: {order_no}\n"
                            if us_order_no:
                                success_msg += f"用户订单号: {us_order_no}\n"
                            success_msg += f"充值账号: {account}\n"
                            success_msg += f"返回信息: {result.get('msg', '提交成功')}\n"
                            success_msg += f"有任何问题，请及时联系客服处理。"
                            
                            logger.info(f"亦凡API调用成功: {success_msg}")
                            return success_msg
                        else:
                            # 下单失败
                            error_msg = result.get('msg', '未知错误')
                            logger.error(f"亦凡API调用失败: code={result.get('code')}, msg={error_msg}")
                            
                            # 发送通知给用户
                            if chat_id and buyer_id:
                                notification_msg = f"❌ 自动发货失败\n错误信息: {error_msg}\n请联系客服处理"
                                await self.send_notification("系统", buyer_id, notification_msg, item_id or "unknown", chat_id)
                            
                            return None
                    except Exception as e:
                        logger.error(f"解析亦凡API返回失败: {self._safe_str(e)}")
                        return None
                else:
                    logger.error(f"亦凡API调用失败: HTTP {status_code} - {response_text[:200]}")
                    return None

        except Exception as e:
            logger.error(f"亦凡API调用异常: {self._safe_str(e)}")
            return None

    # ==================== 充值账号询问 ====================

    async def ask_for_recharge_account(self, chat_id, buyer_id, rule, order_id=None, item_id=None):
        """询问客户充值账号并设置等待状态（不阻塞）"""
        try:
            async with self.yifan_account_lock:
                # 设置等待状态
                self.yifan_account_waiting[chat_id] = {
                    'buyer_id': buyer_id,
                    'rule': rule,
                    'order_id': order_id,
                    'item_id': item_id,
                    'state': 'waiting_account',  # waiting_account 或 waiting_confirm
                    'account': None,
                    'create_time': time.time(),
                    'retry_count': 0
                }
            
            # 发送询问消息
            ask_message = "请单独发送您的充值账号，不要有任何其他的文字。如果因为您输错的原因导致错误下单，概不退款。"
            await self.send_msg(self.ws, chat_id, buyer_id, ask_message)
            logger.info(f"已发送充值账号询问消息，等待用户回复")
            
            # 返回特殊标记，表示需要等待用户输入
            return "__WAITING_ACCOUNT__"

        except Exception as e:
            logger.error(f"询问充值账号异常: {self._safe_str(e)}")
            return None
