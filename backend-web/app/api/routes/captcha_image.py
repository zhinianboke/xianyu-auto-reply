"""
图形验证码接口与图片生成工具。

功能：
1. 生成图形验证码图片
2. 校验并消费图形验证码，保留原接口路径与响应
"""
from __future__ import annotations

import base64
import io
import os
import random
import time

from fastapi import APIRouter
from loguru import logger
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel

from common.schemas.common import ApiResponse

router = APIRouter()
captcha_store: dict = {}


class CaptchaRequest(BaseModel):
    """图形验证码请求"""
    session_id: str


class VerifyCaptchaRequest(BaseModel):
    """验证图形验证码请求"""
    session_id: str
    captcha_code: str


def generate_captcha_text(length: int = 4) -> str:
    """生成随机验证码文本"""
    # 排除容易混淆的字符: 0, O, 1, I, l
    chars = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    return "".join(random.choices(chars, k=length))


def _load_captcha_font(size: int = 28):
    """
    按候选路径加载验证码字体。

    Why: Linux 容器（python:3.11-slim）默认没有 arial.ttf，原先直接
    truetype("arial.ttf") 抛异常后 fallback 到 load_default() 的位图字体
    极小（~10px），用户看到的验证码图片几乎是空白。
    这里按优先级尝试各平台常见 TTF 路径，全部失败再退回默认字体。
    """

    # 全部使用绝对路径，避免 truetype 解析相对路径时抛异常拖慢生成
    candidates = [
        # Linux 容器（apt 安装 fonts-dejavu-core / fonts-liberation 后存在）
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        # Windows 本地开发
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        # macOS
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    for path in candidates:
        if not os.path.exists(path):
            continue
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue

    # 全部 TTF 都不可用时的兜底：Pillow 10+ 支持 load_default(size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        # 老版本 Pillow 不支持 size 参数，只能回退到默认小字体
        return ImageFont.load_default()


def generate_captcha_image(text: str) -> str:
    """
    生成图形验证码图片

    返回base64编码的图片
    """
    try:

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
        font = _load_captcha_font(28)

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


def cleanup_expired_captcha():
    """清理过期的验证码"""
    current_time = time.time()
    expired_keys = [k for k, v in captcha_store.items() if v["expires_at"] < current_time]
    for k in expired_keys:
        del captcha_store[k]


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
