"""
推广返佣系统 - 极验滑动验证码API路由

功能：
1. 获取验证码初始化参数（/register）
2. 二次验证（/validate）
3. 支持正常模式和宕机降级模式

复用common/services/geetest中的GeetestLib实现
"""
import time
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field
from loguru import logger

from common.services.geetest import GeetestLib


router = APIRouter(tags=["极验验证码"])


# ==================== 请求/响应模型 ====================

class GeetestRegisterResponse(BaseModel):
    """验证码初始化响应"""
    success: bool
    code: int = 200
    message: str = ""
    data: Optional[dict] = None


class GeetestValidateRequest(BaseModel):
    """二次验证请求"""
    challenge: str
    geetest_validate: str = Field(..., alias="validate")
    seccode: str


class GeetestValidateResponse(BaseModel):
    """二次验证响应"""
    success: bool
    code: int = 200
    message: str = ""


# ==================== 内存存储（记录验证状态） ====================

# 存储验证状态: {challenge: {"status": int, "expires_at": float}}
# status: 0=未验证, 1=已验证
geetest_status_store: dict = {}


def cleanup_expired_status():
    """清理过期的验证状态"""
    current_time = time.time()
    expired_keys = [k for k, v in geetest_status_store.items() if v["expires_at"] < current_time]
    for k in expired_keys:
        del geetest_status_store[k]


def set_geetest_status(challenge: str, status: int):
    """设置验证状态"""
    cleanup_expired_status()
    geetest_status_store[challenge] = {
        "status": status,
        "expires_at": time.time() + 300  # 5分钟有效
    }


def get_geetest_status(challenge: str) -> int:
    """获取验证状态，返回0表示未验证或已过期"""
    cleanup_expired_status()
    stored = geetest_status_store.get(challenge)
    if stored and stored["expires_at"] > time.time():
        return stored["status"]
    return 0


def check_geetest_verified(challenge: str) -> tuple[bool, str]:
    """
    检查极验是否已验证通过（供auth路由调用）

    Args:
        challenge: 验证流水号

    Returns:
        (是否通过, 消息)
    """
    if not challenge:
        return False, "请完成滑动验证"

    status = get_geetest_status(challenge)
    if status == 1:
        # 验证通过后删除状态，防止重复使用
        if challenge in geetest_status_store:
            del geetest_status_store[challenge]
        return True, "验证通过"

    return False, "请完成滑动验证"


# ==================== 路由 ====================

@router.get("/register", response_model=GeetestRegisterResponse)
async def geetest_register():
    """
    获取极验验证码初始化参数

    前端调用此接口获取gt、challenge等参数，用于初始化验证码组件
    """
    try:
        gt_lib = GeetestLib()
        result = await gt_lib.register()

        data = result.to_dict()
        logger.info(f"极验初始化结果: status={result.status}, data={data}")

        # 记录初始状态
        challenge = data.get("challenge", "")
        if challenge:
            set_geetest_status(challenge, 0)

        return GeetestRegisterResponse(
            success=True,
            code=200,
            message="获取成功" if result.status == 1 else "宕机模式",
            data=data
        )

    except Exception as e:
        logger.error(f"极验初始化失败: {e}")
        # 返回本地初始化结果
        gt_lib = GeetestLib()
        result = gt_lib.local_init()
        data = result.to_dict()

        # 记录初始状态
        challenge = data.get("challenge", "")
        if challenge:
            set_geetest_status(challenge, 0)

        return GeetestRegisterResponse(
            success=True,
            code=200,
            message="本地初始化",
            data=data
        )


@router.post("/validate", response_model=GeetestValidateResponse)
async def geetest_validate(request: GeetestValidateRequest):
    """
    极验二次验证

    用户完成滑动验证后，前端调用此接口进行二次验证
    """
    try:
        logger.info(f"极验二次验证请求: challenge={request.challenge[:16]}...")

        # 检查是否已经验证过
        if get_geetest_status(request.challenge) == 1:
            return GeetestValidateResponse(
                success=True,
                code=200,
                message="验证通过"
            )

        gt_lib = GeetestLib()

        # 正常模式验证
        result = await gt_lib.success_validate(
            request.challenge,
            request.geetest_validate,
            request.seccode
        )

        logger.info(f"极验二次验证结果: status={result.status}, msg={result.msg}")

        if result.status == 1:
            # 记录验证通过状态
            set_geetest_status(request.challenge, 1)

            return GeetestValidateResponse(
                success=True,
                code=200,
                message="验证通过"
            )
        else:
            return GeetestValidateResponse(
                success=False,
                code=400,
                message=result.msg or "验证失败"
            )

    except Exception as e:
        logger.error(f"极验二次验证失败: {e}")
        return GeetestValidateResponse(
            success=False,
            code=500,
            message="验证服务异常"
        )
