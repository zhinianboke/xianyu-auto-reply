"""
支付宝当面付服务

功能：
1. 从系统设置读取支付宝配置
2. 创建当面付预下单（生成二维码）
3. RSA2签名生成与验证
4. 异步通知验签
"""
from __future__ import annotations

import base64
import json
import logging
import random
import re
import string
from typing import Any, Dict, Optional

import requests
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from common.models.system_setting import SystemSetting
from common.utils.time_utils import get_beijing_now_naive

logger = logging.getLogger(__name__)


class AlipayService:
    """支付宝当面付服务类"""

    def __init__(self, config: Dict[str, str]):
        """初始化支付宝服务

        Args:
            config: 支付宝配置字典
        """
        self.config = config
        required = ['app_id', 'private_key', 'alipay_public_key']
        missing = [k for k in required if not self.config.get(k)]
        if missing:
            raise ValueError(f"支付宝配置缺少必要字段: {', '.join(missing)}")

    @staticmethod
    async def load_config(session: AsyncSession) -> Dict[str, str]:
        """从系统设置表读取支付宝配置"""
        keys = [
            'alipay.app_id', 'alipay.private_key',
            'alipay.alipay_public_key', 'alipay.gateway_url',
            'alipay.notify_url',
        ]
        stmt = select(SystemSetting).where(SystemSetting.key.in_(keys))
        result = await session.execute(stmt)
        settings = {s.key: s.value for s in result.scalars().all()}
        return {
            'app_id': settings.get('alipay.app_id', ''),
            'private_key': settings.get('alipay.private_key', ''),
            'alipay_public_key': settings.get('alipay.alipay_public_key', ''),
            'gateway_url': settings.get('alipay.gateway_url',
                                        'https://openapi.alipay.com/gateway.do'),
            'notify_url': settings.get('alipay.notify_url', ''),
        }

    def create_f2f_pay(self, order_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """创建支付宝当面付（扫码支付）

        Args:
            order_data: 包含 out_trade_no, total_amount, subject 等

        Returns:
            成功返回含 qr_code 的字典，失败返回 None
        """
        try:
            order_no = order_data['out_trade_no']
            amount = str(order_data['total_amount'])
            subject = order_data['subject']

            params = {
                'app_id': self.config['app_id'],
                'method': 'alipay.trade.precreate',
                'charset': 'utf-8',
                'sign_type': 'RSA2',
                'timestamp': get_beijing_now_naive().strftime('%Y-%m-%d %H:%M:%S'),
                'version': '1.0',
                'biz_content': json.dumps({
                    'out_trade_no': order_no,
                    'total_amount': amount,
                    'subject': subject,
                    'body': order_data.get('body', ''),
                    'timeout_express': order_data.get('timeout_express', '30m'),
                }, ensure_ascii=False),
            }

            notify_url = order_data.get('notify_url') or self.config.get('notify_url', '')
            if notify_url:
                params['notify_url'] = notify_url

            params['sign'] = self._generate_sign(params)

            gateway = self.config.get('gateway_url', 'https://openapi.alipay.com/gateway.do')
            logger.info(f"发送支付宝当面付请求: 订单号={order_no}, 金额={amount}")

            headers = {'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8'}
            resp = requests.post(gateway, data=params, headers=headers, timeout=30)
            return self._parse_precreate_response(resp.text, order_no, amount, subject)

        except Exception as e:
            logger.error(f"创建支付宝当面付失败: {e}")
            return None

    def _parse_precreate_response(
        self, text: str, order_no: str, amount: str, subject: str
    ) -> Optional[Dict[str, Any]]:
        """解析当面付API响应"""
        match = re.search(r'"alipay_trade_precreate_response":\s*(\{[^}]+\})', text)
        if not match:
            logger.error(f"无法解析支付宝API响应: {text}")
            return None

        data = json.loads(match.group(1))
        if data.get('code') == '10000' and data.get('qr_code'):
            logger.info(f"支付宝当面付二维码生成成功: {order_no}")
            return {
                'success': True, 'qr_code': data['qr_code'],
                'order_no': order_no, 'amount': amount, 'subject': subject,
            }

        sub_msg = data.get('sub_msg', data.get('msg', '未知错误'))
        logger.error(f"支付宝当面付失败: {data}")
        return {'success': False, 'error': sub_msg}

    def verify_notify(self, notify_data: Dict[str, Any]) -> bool:
        """验证支付宝异步通知签名"""
        sign = notify_data.get('sign', '')
        if not sign:
            logger.error("通知数据中没有签名")
            return False

        if notify_data.get('app_id') != self.config.get('app_id'):
            logger.error("app_id不匹配")
            return False

        try:
            # 构建待验签字符串
            filtered = {
                k: v for k, v in notify_data.items()
                if k not in ('sign', 'sign_type') and v
            }
            sign_string = '&'.join(f"{k}={v}" for k, v in sorted(filtered.items()))

            pub_key = self._format_public_key(self.config['alipay_public_key'])
            key = RSA.import_key(pub_key)
            h = SHA256.new(sign_string.encode('utf-8'))
            pkcs1_15.new(key).verify(h, base64.b64decode(sign))
            logger.info(f"支付宝通知验签成功: {notify_data.get('out_trade_no')}")
            return True
        except Exception as e:
            logger.error(f"支付宝通知验签失败: {e}")
            return False

    def _generate_sign(self, params: Dict[str, Any]) -> str:
        """生成RSA2签名"""
        filtered = {
            k: v for k, v in params.items()
            if k != 'sign' and v is not None and str(v).strip()
        }
        sign_string = '&'.join(f"{k}={v}" for k, v in sorted(filtered.items()))

        priv_key = self._format_private_key(self.config['private_key'])
        key = RSA.import_key(priv_key)
        h = SHA256.new(sign_string.encode('utf-8'))
        signature = pkcs1_15.new(key).sign(h)
        return base64.b64encode(signature).decode('utf-8')

    @staticmethod
    def _format_private_key(raw: str) -> str:
        """格式化私钥为PEM格式"""
        raw = raw.strip()
        for tag in ('-----BEGIN RSA PRIVATE KEY-----', '-----END RSA PRIVATE KEY-----',
                     '-----BEGIN PRIVATE KEY-----', '-----END PRIVATE KEY-----'):
            raw = raw.replace(tag, '')
        raw = raw.replace('\n', '').replace('\r', '').replace(' ', '')
        lines = [raw[i:i + 64] for i in range(0, len(raw), 64)]
        return f"-----BEGIN RSA PRIVATE KEY-----\n{chr(10).join(lines)}\n-----END RSA PRIVATE KEY-----"

    @staticmethod
    def _format_public_key(raw: str) -> str:
        """格式化公钥为PEM格式"""
        raw = raw.strip()
        for tag in ('-----BEGIN PUBLIC KEY-----', '-----END PUBLIC KEY-----',
                     '-----BEGIN RSA PUBLIC KEY-----', '-----END RSA PUBLIC KEY-----'):
            raw = raw.replace(tag, '')
        raw = raw.replace('\n', '').replace('\r', '').replace(' ', '')
        lines = [raw[i:i + 64] for i in range(0, len(raw), 64)]
        return f"-----BEGIN PUBLIC KEY-----\n{chr(10).join(lines)}\n-----END PUBLIC KEY-----"

    @staticmethod
    def generate_order_no() -> str:
        """生成唯一充值订单号"""
        ts = get_beijing_now_naive().strftime('%Y%m%d%H%M%S')
        rand = ''.join(random.choices(string.digits, k=6))
        return f"RC{ts}{rand}"

    @staticmethod
    def is_trade_success(trade_status: str) -> bool:
        """判断交易是否成功"""
        return trade_status in ('TRADE_SUCCESS', 'TRADE_FINISHED')
