"""
极验验证码SDK核心类

功能：
1. 验证码初始化（register）
2. 二次验证（validate）
3. 支持正常模式和宕机降级模式
"""
import hashlib
import json
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import httpx
from loguru import logger

from .geetest_config import GeetestConfig


class DigestMod(Enum):
    """摘要算法类型"""
    MD5 = "md5"
    SHA256 = "sha256"
    HMAC_SHA256 = "hmac-sha256"


@dataclass
class GeetestResult:
    """极验返回结果封装"""
    status: int = 0  # 1成功，0失败
    data: str = ""   # JSON字符串
    msg: str = ""    # 错误信息
    
    def to_dict(self) -> dict:
        """转换为字典"""
        try:
            return json.loads(self.data) if self.data else {}
        except json.JSONDecodeError:
            return {}


class GeetestLib:
    """
    极验验证码SDK核心类
    
    使用方法：
    1. 初始化: gt_lib = GeetestLib()
    2. 获取验证码参数: result = await gt_lib.register()
    3. 二次验证: result = await gt_lib.validate(challenge, validate, seccode)
    """
    
    def __init__(
        self,
        captcha_id: Optional[str] = None,
        private_key: Optional[str] = None
    ):
        """
        初始化极验SDK
        
        Args:
            captcha_id: 极验分配的captcha_id，默认从配置读取
            private_key: 极验分配的私钥，默认从配置读取
        """
        self.captcha_id = captcha_id or GeetestConfig.CAPTCHA_ID
        self.private_key = private_key or GeetestConfig.PRIVATE_KEY
        self.result = GeetestResult()
    
    def _md5_encode(self, value: str) -> str:
        """MD5加密"""
        return hashlib.md5(value.encode()).hexdigest()
    
    def _sha256_encode(self, value: str) -> str:
        """SHA256加密"""
        return hashlib.sha256(value.encode()).hexdigest()
    
    def _hmac_sha256_encode(self, value: str, key: str) -> str:
        """HMAC-SHA256加密"""
        import hmac
        return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()
    
    def _check_params(self, challenge: str, validate: str, seccode: str) -> bool:
        """检查参数是否有效"""
        return bool(challenge and validate and seccode)

    async def _request_register(self, params: dict) -> None:
        """请求极验注册接口"""
        params.update({
            "gt": self.captcha_id,
            "json_format": "1",
            "sdk": GeetestConfig.VERSION
        })
        
        url = f"{GeetestConfig.API_URL}{GeetestConfig.REGISTER_URL}"
        
        try:
            async with httpx.AsyncClient(timeout=GeetestConfig.TIMEOUT) as client:
                response = await client.get(url, params=params)
                response.raise_for_status()
                
                res_data = response.json()
                challenge = res_data.get("challenge", "")
                
                if challenge and len(challenge) == 32:
                    # 正常模式
                    challenge = self._md5_encode(challenge + self.private_key)
                    data = {
                        "success": 1,
                        "gt": self.captcha_id,
                        "challenge": challenge,
                        "new_captcha": True
                    }
                    self.result = GeetestResult(
                        status=1,
                        data=json.dumps(data),
                        msg=""
                    )
                else:
                    # 宕机模式
                    self._local_init()
                    
        except Exception as e:
            logger.error(f"极验注册请求失败: {e}")
            self._local_init()
    
    def _local_init(self) -> None:
        """本地初始化（宕机降级模式）"""
        challenge = str(uuid.uuid4()).replace("-", "")
        data = {
            "success": 0,
            "gt": self.captcha_id,
            "challenge": challenge,
            "new_captcha": True
        }
        self.result = GeetestResult(
            status=0,
            data=json.dumps(data),
            msg="宕机模式"
        )
    
    async def register(
        self,
        digest_mod: DigestMod = DigestMod.MD5,
        user_id: Optional[str] = None,
        client_type: Optional[str] = None
    ) -> GeetestResult:
        """
        验证码初始化
        
        Args:
            digest_mod: 摘要算法类型
            user_id: 用户标识
            client_type: 客户端类型
        
        Returns:
            GeetestResult对象
        """
        logger.info(f"极验register开始: digest_mod={digest_mod.value}")
        
        params = {
            "digestmod": digest_mod.value,
            "user_id": user_id or GeetestConfig.USER_ID,
            "client_type": client_type or GeetestConfig.CLIENT_TYPE
        }
        
        await self._request_register(params)
        
        logger.info(f"极验register结果: status={self.result.status}")
        return self.result
    
    def local_init(self) -> GeetestResult:
        """
        本地初始化（宕机降级模式）
        
        Returns:
            GeetestResult对象
        """
        logger.info("极验本地初始化（宕机模式）")
        self._local_init()
        return self.result

    async def _request_validate(
        self,
        challenge: str,
        validate: str,
        seccode: str,
        params: dict
    ) -> Optional[str]:
        """请求极验验证接口"""
        params.update({
            "seccode": seccode,
            "json_format": "1",
            "challenge": challenge,
            "sdk": GeetestConfig.VERSION,
            "captchaid": self.captcha_id
        })
        
        url = f"{GeetestConfig.API_URL}{GeetestConfig.VALIDATE_URL}"
        
        try:
            async with httpx.AsyncClient(timeout=GeetestConfig.TIMEOUT) as client:
                response = await client.post(url, data=params)
                response.raise_for_status()
                
                res_data = response.json()
                return res_data.get("seccode")
                
        except Exception as e:
            logger.error(f"极验验证请求失败: {e}")
            return None
    
    async def success_validate(
        self,
        challenge: str,
        validate: str,
        seccode: str,
        user_id: Optional[str] = None,
        client_type: Optional[str] = None
    ) -> GeetestResult:
        """
        正常模式下的二次验证
        
        Args:
            challenge: 流水号
            validate: 验证结果
            seccode: 验证码
            user_id: 用户标识
            client_type: 客户端类型
        
        Returns:
            GeetestResult对象
        """
        logger.info(f"极验二次验证（正常模式）: challenge={challenge[:16]}...")
        
        if not self._check_params(challenge, validate, seccode):
            self.result = GeetestResult(
                status=0,
                data="",
                msg="正常模式，本地校验，参数challenge、validate、seccode不可为空"
            )
            return self.result
        
        params = {
            "user_id": user_id or GeetestConfig.USER_ID,
            "client_type": client_type or GeetestConfig.CLIENT_TYPE
        }
        
        response_seccode = await self._request_validate(challenge, validate, seccode, params)
        
        if not response_seccode:
            self.result = GeetestResult(
                status=0,
                data="",
                msg="请求极验validate接口失败"
            )
        elif response_seccode == "false":
            self.result = GeetestResult(
                status=0,
                data="",
                msg="极验二次验证不通过"
            )
        else:
            self.result = GeetestResult(
                status=1,
                data="",
                msg=""
            )
        
        logger.info(f"极验二次验证完成: status={self.result.status}")
        return self.result
    
    def fail_validate(
        self,
        challenge: str,
        validate: str,
        seccode: str
    ) -> GeetestResult:
        """
        宕机模式下的二次验证（简单参数校验）
        
        Args:
            challenge: 流水号
            validate: 验证结果
            seccode: 验证码
        
        Returns:
            GeetestResult对象
        """
        logger.info(f"极验二次验证（宕机模式）: challenge={challenge[:16] if challenge else 'None'}...")
        
        if not self._check_params(challenge, validate, seccode):
            self.result = GeetestResult(
                status=0,
                data="",
                msg="宕机模式，本地校验，参数challenge、validate、seccode不可为空"
            )
        else:
            self.result = GeetestResult(
                status=1,
                data="",
                msg=""
            )
        
        return self.result
