"""
自动确认发货服务

功能:
1. 调用闲鱼API确认发货
2. 支持重试机制(最多4次)
3. 自动处理Cookie更新
4. 处理已发货订单

复刻原始secure_confirm_decrypted.py的逻辑
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

import aiohttp
from loguru import logger

from app.services.shipping.base import BaseShippingService
from common.utils.xianyu_utils import generate_sign, trans_cookies


class ConfirmShippingService(BaseShippingService):
    """自动确认发货服务
    
    调用闲鱼API确认订单发货,支持重试和错误处理
    """

    # API配置
    API_URL = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.logistic.consign.dummy/1.0/"
    API_NAME = "mtop.taobao.idle.logistic.consign.dummy"
    MAX_RETRY = 4

    async def auto_confirm(
        self,
        order_id: str,
        item_id: Optional[str] = None,
        retry_count: int = 0,
    ) -> Dict[str, Any]:
        """自动确认发货
        
        Args:
            order_id: 订单ID
            item_id: 商品ID(可选,用于Token刷新)
            retry_count: 当前重试次数
            
        Returns:
            结果字典,包含success或error字段
        """
        if retry_count >= self.MAX_RETRY + 1:
            logger.error("自动确认发货失败,重试次数过多")
            return {"error": "自动确认发货失败,重试次数过多"}

        # 确保账号信息已加载
        if not self._account:
            if not await self._load_account():
                return {"error": "账号信息加载失败"}

        # 保存item_id供Token刷新使用
        if item_id:
            self._current_item_id = item_id
            logger.debug(f"【{self.account_id}】设置当前商品ID: {item_id}")

        # 确保http_session已创建
        if not self.http_session:
            return {"error": "HTTP Session未创建"}

        # 构建请求参数
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
            'api': self.API_NAME,
            'sessionOption': 'AutoLoginOnly',
        }

        # 构建请求数据
        data_val = '{"orderId":"' + order_id + '", "tradeText":"","picList":[],"newUnconsign":true}'
        data = {'data': data_val}

        # 获取Token并生成签名
        token = self._get_token_from_cookies()
        if token:
            logger.info(f"使用cookies中的_m_h5_tk token: {token}")
        else:
            logger.warning("cookies中没有找到_m_h5_tk token")

        sign = generate_sign(params['t'], token, data_val)
        params['sign'] = sign

        try:
            logger.info(f"【{self.account_id}】开始自动确认发货,订单ID: {order_id}")
            
            async with self.http_session.post(
                self.API_URL,
                params=params,
                data=data,
                headers=self._build_headers(),
            ) as response:
                res_json = await response.json()

                # 处理响应中的Cookie更新
                await self._handle_response_cookies(response)

                logger.info(f"【{self.account_id}】自动确认发货响应: {res_json}")

                # 检查响应结果
                ret_msg = res_json.get('ret', ['未知错误'])[0] if res_json.get('ret') else '未知错误'
                
                if ret_msg == 'SUCCESS::调用成功':
                    logger.info(f"【{self.account_id}】✅ 自动确认发货成功,订单ID: {order_id}")
                    return {"success": True, "order_id": order_id, "message": ret_msg}
                elif 'ORDER_ALREADY_DELIVERY' in ret_msg or '已发货成功' in ret_msg:
                    # 已发货的订单也视为成功
                    logger.info(f"【{self.account_id}】✅ 订单已发货,无需重复确认,订单ID: {order_id}")
                    return {"success": True, "order_id": order_id, "already_delivered": True, "message": ret_msg}
                else:
                    logger.warning(f"【{self.account_id}】❌ 自动确认发货失败: {ret_msg}")
                    
                    # 重试
                    return await self.auto_confirm(order_id, item_id, retry_count + 1)

        except Exception as e:
            logger.error(f"【{self.account_id}】自动确认发货API请求异常: {self._safe_str(e)}")
            await asyncio.sleep(0.5)

            # 网络异常也进行重试
            if retry_count < 2:
                logger.info(f"【{self.account_id}】网络异常,准备重试...")
                return await self.auto_confirm(order_id, item_id, retry_count + 1)

            return {"error": f"网络异常: {self._safe_str(e)}", "order_id": order_id}

    def _build_headers(self) -> Dict[str, str]:
        """构建请求头
        
        Returns:
            请求头字典
        """
        return {
            'Cookie': self.cookies_str,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Referer': 'https://www.goofish.com/',
        }


# 便捷函数
async def confirm_shipping(
    db_session,
    http_session: aiohttp.ClientSession,
    account_pk: int,
    order_id: str,
    item_id: Optional[str] = None,
) -> Dict[str, Any]:
    """确认发货的便捷函数
    
    Args:
        db_session: 异步数据库会话
        http_session: aiohttp会话
        account_pk: 账号主键
        order_id: 订单ID
        item_id: 商品ID(可选)
        
    Returns:
        结果字典
    """
    service = ConfirmShippingService(db_session, http_session, account_pk)
    return await service.auto_confirm(order_id, item_id)
