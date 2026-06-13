"""
验证码相关路由

包含图形验证码和邮箱验证码功能
"""
from __future__ import annotations

import random
import string
import time
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.api import deps
from common.schemas.common import ApiResponse

router = APIRouter(prefix="/captcha", tags=["验证码"])


# ==================== 请求/响应模型 ====================

class CaptchaRequest(BaseModel):
    """图形验证码请求"""
    session_id: str


class VerifyCaptchaRequest(BaseModel):
    """验证图形验证码请求"""
    session_id: str
    captcha_code: str


class SendCodeRequest(BaseModel):
    """发送邮箱验证码请求"""
    email: EmailStr
    session_id: Optional[str] = None
    type: str = "register"  # register, login 或 reset_password


# ==================== 工具函数 ====================

def generate_captcha_text(length: int = 4) -> str:
    """生成随机验证码文本"""
    # 排除容易混淆的字符: 0, O, 1, I, l
    chars = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(random.choices(chars, k=length))


def generate_captcha_image(text: str) -> str:
    """
    生成图形验证码图片
    
    返回base64编码的图片
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        import io
        import base64
        
        # 图片尺寸
        width, height = 120, 40
        
        # 创建图片
        image = Image.new("RGB", (width, height), color=(255, 255, 255))
        draw = ImageDraw.Draw(image)
        
        # 添加干扰线
        for _ in range(5):
            x1 = random.randint(0, width)
            y1 = random.randint(0, height)
            x2 = random.randint(0, width)
            y2 = random.randint(0, height)
            draw.line(
                [(x1, y1), (x2, y2)], 
                fill=(random.randint(0, 200), random.randint(0, 200), random.randint(0, 200))
            )
        
        # 添加干扰点
        for _ in range(50):
            x = random.randint(0, width)
            y = random.randint(0, height)
            draw.point(
                (x, y), 
                fill=(random.randint(0, 200), random.randint(0, 200), random.randint(0, 200))
            )
        
        # 绘制文字
        try:
            font = ImageFont.truetype("arial.ttf", 28)
        except Exception:
            font = ImageFont.load_default()
        
        # 计算文字位置
        for i, char in enumerate(text):
            x = 10 + i * 25 + random.randint(-3, 3)
            y = random.randint(2, 10)
            color = (random.randint(0, 150), random.randint(0, 150), random.randint(0, 150))
            draw.text((x, y), char, font=font, fill=color)
        
        # 转换为base64
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        img_str = base64.b64encode(buffer.getvalue()).decode()
        
        return f"data:image/png;base64,{img_str}"
        
    except Exception as e:
        logger.error(f"生成验证码图片失败: {e}")
        return ""


def generate_verification_code(length: int = 6) -> str:
    """生成数字验证码"""
    return "".join(random.choices(string.digits, k=length))


# ==================== 内存存储（简化实现，生产环境建议用Redis） ====================

# 图形验证码存储: {session_id: {"code": str, "expires_at": float}}
captcha_store: dict = {}

# 邮箱验证码存储: {email: {"code": str, "type": str, "expires_at": float}}
email_code_store: dict = {}


def cleanup_expired_captcha():
    """清理过期的验证码"""
    current_time = time.time()
    expired_keys = [k for k, v in captcha_store.items() if v["expires_at"] < current_time]
    for k in expired_keys:
        del captcha_store[k]


def cleanup_expired_email_codes():
    """清理过期的邮箱验证码"""
    current_time = time.time()
    expired_keys = [k for k, v in email_code_store.items() if v["expires_at"] < current_time]
    for k in expired_keys:
        del email_code_store[k]


# ==================== 路由 ====================

@router.post("/generate")
async def generate_captcha(request: CaptchaRequest) -> ApiResponse:
    """生成图形验证码"""
    try:
        cleanup_expired_captcha()
        
        # 生成验证码
        captcha_text = generate_captcha_text()
        captcha_image = generate_captcha_image(captcha_text)
        
        if not captcha_image:
            return ApiResponse(
                success=False,
                message="图形验证码生成失败"
            )
        
        # 保存验证码（5分钟有效）
        captcha_store[request.session_id] = {
            "code": captcha_text.upper(),
            "expires_at": time.time() + 300
        }
        
        logger.info(f"生成图形验证码: session_id={request.session_id}")
        
        return ApiResponse(
            success=True,
            message="图形验证码生成成功",
            data={
                "captcha_image": captcha_image,
                "session_id": request.session_id
            }
        )
        
    except Exception as e:
        logger.error(f"生成图形验证码失败: {e}")
        return ApiResponse(
            success=False,
            message="图形验证码生成失败"
        )


@router.post("/verify")
async def verify_captcha(request: VerifyCaptchaRequest) -> ApiResponse:
    """验证图形验证码"""
    try:
        cleanup_expired_captcha()
        
        stored = captcha_store.get(request.session_id)
        
        if not stored:
            return ApiResponse(
                success=False,
                message="验证码不存在或已过期"
            )
        
        if stored["expires_at"] < time.time():
            del captcha_store[request.session_id]
            return ApiResponse(
                success=False,
                message="验证码已过期"
            )
        
        if stored["code"] != request.captcha_code.upper():
            return ApiResponse(
                success=False,
                message="验证码错误"
            )
        
        # 验证成功后删除
        del captcha_store[request.session_id]
        
        logger.info(f"图形验证码验证成功: session_id={request.session_id}")
        
        return ApiResponse(
            success=True,
            message="验证码验证成功"
        )
        
    except Exception as e:
        logger.error(f"验证图形验证码失败: {e}")
        return ApiResponse(
            success=False,
            message="验证码验证失败"
        )


@router.post("/send-email-code")
async def send_email_verification_code(
    request: SendCodeRequest,
    db: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """发送邮箱验证码"""
    try:
        cleanup_expired_email_codes()
        
        from app.services.user_service import UserService
        user_service = UserService(db)
        
        # 根据类型检查邮箱
        if request.type == "register":
            existing_user = await user_service.get_by_email(request.email)
            if existing_user:
                return ApiResponse(
                    success=False,
                    message="该邮箱已被注册"
                )
        elif request.type == "login":
            existing_user = await user_service.get_by_email(request.email)
            if not existing_user:
                return ApiResponse(
                    success=False,
                    message="该邮箱未注册"
                )
        elif request.type == "reset_password":
            existing_user = await user_service.get_by_email(request.email)
            if not existing_user:
                return ApiResponse(
                    success=False,
                    message="该邮箱未注册"
                )
        
        # 检查发送频率（1分钟内只能发送一次）
        stored = email_code_store.get(request.email)
        if stored and stored["expires_at"] - 240 > time.time():
            return ApiResponse(
                success=False,
                message="验证码发送过于频繁，请稍后再试"
            )
        
        # 生成验证码
        code = generate_verification_code()
        
        # 保存验证码（5分钟有效）
        email_code_store[request.email] = {
            "code": code,
            "type": request.type,
            "expires_at": time.time() + 300
        }
        
        # 发送邮件
        from app.services.email_service import send_verification_code_email
        success, message = await send_verification_code_email(request.email, code, request.type)
        
        if not success:
            # 发送失败，删除验证码
            del email_code_store[request.email]
            return ApiResponse(
                success=False,
                message=message
            )
        
        logger.info(f"发送邮箱验证码成功: email={request.email}, type={request.type}")
        
        return ApiResponse(
            success=True,
            message="验证码已发送到您的邮箱，请查收"
        )
        
    except Exception as e:
        logger.error(f"发送邮箱验证码失败: {e}")
        return ApiResponse(
            success=False,
            message="验证码发送失败，请稍后重试"
        )


@router.post("/verify-email-code")
async def verify_email_code(
    email: str,
    code: str,
    code_type: str = "register",
) -> ApiResponse:
    """验证邮箱验证码"""
    cleanup_expired_email_codes()
    
    stored = email_code_store.get(email)
    
    if not stored:
        return ApiResponse(success=False, message="验证码不存在或已过期")
    
    if stored["expires_at"] < time.time():
        del email_code_store[email]
        return ApiResponse(success=False, message="验证码已过期")
    
    if stored["code"] != code:
        return ApiResponse(success=False, message="验证码错误")
    
    if stored["type"] != code_type:
        return ApiResponse(success=False, message="验证码类型不匹配")
    
    # 验证成功后删除
    del email_code_store[email]
    
    return ApiResponse(success=True, message="验证码验证成功")


def check_email_code(email: str, code: str, code_type: str = "login") -> tuple[bool, str]:
    """
    验证邮箱验证码（供其他模块调用）
    
    返回: (是否成功, 消息)
    """
    cleanup_expired_email_codes()
    
    stored = email_code_store.get(email)
    
    if not stored:
        return False, "验证码不存在或已过期"
    
    if stored["expires_at"] < time.time():
        del email_code_store[email]
        return False, "验证码已过期"
    
    if stored["code"] != code:
        return False, "验证码错误"
    
    if stored["type"] != code_type:
        return False, "验证码类型不匹配"
    
    # 验证成功后删除
    del email_code_store[email]
    
    return True, "验证码验证成功"
