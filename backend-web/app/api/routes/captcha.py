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
from app.services.websocket_client import websocket_client
from common.models.user import User
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


class SliderSolveRequest(BaseModel):
    """过滑块请求（模式B，外部使用）"""
    secret_key: str                      # 用户个人设置中的秘钥（用于身份校验，查到用户名）
    account_id: str = ""                 # 外部账号标识（仅用于日志/浏览器实例隔离，本系统不查库）
    url: str                             # punish 验证链接（punish?x5secdata=...）
    browser_timeout: int = 40            # 单次浏览器超时（秒），范围 20~120


class TestRemoteSolveRequest(BaseModel):
    """测试远程过滑块服务连通性请求"""
    url: str                             # 远程过滑块服务URL
    secret_key: str = ""                 # 秘钥（用于校验远程是否接受该秘钥）


class RemoteConfigUpdate(BaseModel):
    """远程过滑块全局配置（仅管理员）"""
    url: str = ""
    secret_key: str = ""


# 远程过滑块全局配置存储 key（system_settings，全局唯一，仅管理员可读写）
REMOTE_CONFIG_URL_KEY = "captcha.remote_service_url"
REMOTE_CONFIG_SECRET_KEY = "captcha.remote_secret_key"


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

# 邮箱验证码存储: {email: {"code": str, "type": str, "expires_at": float, "fail_count": int}}
email_code_store: dict = {}

# 单个邮箱验证码最大允许尝试次数，超过即作废（防暴力枚举）
MAX_EMAIL_CODE_ATTEMPTS = 5


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

    安全说明：单个验证码最多允许尝试 MAX_EMAIL_CODE_ATTEMPTS 次，
    超过后立即作废，防止 6 位数字验证码被暴力枚举。
    """
    cleanup_expired_email_codes()

    stored = email_code_store.get(email)

    if not stored:
        return False, "验证码不存在或已过期"

    if stored["expires_at"] < time.time():
        del email_code_store[email]
        return False, "验证码已过期"

    if stored["type"] != code_type:
        return False, "验证码类型不匹配"

    if stored["code"] != code:
        # 记录失败次数，超过上限直接作废，避免暴力枚举
        stored["fail_count"] = stored.get("fail_count", 0) + 1
        if stored["fail_count"] >= MAX_EMAIL_CODE_ATTEMPTS:
            del email_code_store[email]
            return False, "验证码错误次数过多，请重新获取验证码"
        remaining = MAX_EMAIL_CODE_ATTEMPTS - stored["fail_count"]
        return False, f"验证码错误，还可尝试 {remaining} 次"

    # 验证成功后删除
    del email_code_store[email]

    return True, "验证码验证成功"


# ==================== 过滑块（外部接口，模式B） ====================

@router.post("/slider-solve")
async def slider_solve(
    request: SliderSolveRequest,
    db: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """过滑块（供外部系统调用）。

    模式B：仅凭传入的 punish 链接求解，本系统不查账号库、不回填 cookies。
    - 鉴权：必须传入有效的用户秘钥（个人设置中的秘钥），校验存在即放行，并据此记录调用用户。
    - 成功：data = { engine, cookies: { x5sec, ... } }
    - 失败：success=false
    """
    from sqlalchemy import select
    from common.models.user import User

    secret_key = (request.secret_key or "").strip()
    if not secret_key:
        return ApiResponse(success=False, message="缺少秘钥")

    # 校验秘钥是否存在（个人设置中的用户秘钥），并查出用户名
    result = await db.execute(select(User).where(User.secret_key == secret_key))
    user = result.scalar_one_or_none()
    if not user:
        return ApiResponse(success=False, message="无效的秘钥")

    url = (request.url or "").strip()
    if not url:
        return ApiResponse(success=False, message="punish 链接不能为空")

    timeout = max(20, min(int(request.browser_timeout or 40), 120))
    result_data = await websocket_client.solve_captcha(
        account_id=(request.account_id or "external"),
        url=url,
        browser_timeout=timeout,
        call_type="remote",
        call_user=user.username,
    )

    if isinstance(result_data, dict) and result_data.get("success"):
        return ApiResponse(success=True, message="过滑块成功", data=result_data.get("data"))
    message = (result_data or {}).get("message") if isinstance(result_data, dict) else None
    data = (result_data or {}).get("data") if isinstance(result_data, dict) else None
    return ApiResponse(success=False, message=message or "过滑块失败", data=data)


@router.post("/slider-solve/test")
async def test_remote_slider_solve(
    request: TestRemoteSolveRequest,
    current_user: User = Depends(deps.get_current_admin_user),  # 仅管理员可发起（也避免被滥用做 SSRF）
) -> ApiResponse:
    """测试远程过滑块服务连通性与秘钥有效性（服务端代理请求，规避浏览器跨域）。

    以一个“空 punish 链接”探测：远程会先校验秘钥，再校验链接，据此判断：
    - 秘钥无效 → 连接成功但秘钥无效
    - 提示缺少链接/其它正常业务响应 → 连接成功且秘钥有效
    - 网络异常 → 无法连接
    """
    import aiohttp

    url = (request.url or "").strip()
    if not url:
        return ApiResponse(success=False, message="请先填写远程服务URL")
    if not url.lower().startswith(("http://", "https://")):
        return ApiResponse(success=False, message="远程服务URL 必须以 http:// 或 https:// 开头")

    payload = {
        "secret_key": (request.secret_key or "").strip(),
        "account_id": "connectivity-test",
        "url": "",  # 故意留空：只测连通+秘钥，不真正过滑块
    }
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as session:
            async with session.post(url, json=payload) as resp:
                try:
                    body = await resp.json(content_type=None)
                except Exception:
                    body = {}
                msg = ((body or {}).get("message") or "").strip()
                if "秘钥" in msg and ("无效" in msg or "缺少" in msg):
                    return ApiResponse(success=False, message=f"连接成功，但秘钥无效（远程：{msg}）")
                return ApiResponse(success=True, message=f"连接成功（远程返回：{msg or '正常'}）")
    except Exception as e:
        return ApiResponse(success=False, message=f"无法连接到远程服务：{str(e)}")


@router.get("/remote-config")
async def get_remote_config(
    current_user: User = Depends(deps.get_current_admin_user),  # 仅管理员可读
    db: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """读取远程过滑块全局配置（仅管理员）。"""
    from sqlalchemy import select
    from common.models.system_setting import SystemSetting

    rows = (await db.execute(
        select(SystemSetting).where(
            SystemSetting.key.in_([REMOTE_CONFIG_URL_KEY, REMOTE_CONFIG_SECRET_KEY])
        )
    )).scalars().all()
    m = {r.key: (r.value or "") for r in rows}
    return ApiResponse(success=True, data={
        "url": m.get(REMOTE_CONFIG_URL_KEY, ""),
        "secret_key": m.get(REMOTE_CONFIG_SECRET_KEY, ""),
    })


@router.put("/remote-config")
async def update_remote_config(
    request: RemoteConfigUpdate,
    current_user: User = Depends(deps.get_current_admin_user),  # 仅管理员可写
    db: AsyncSession = Depends(deps.get_db_session),
) -> ApiResponse:
    """保存远程过滑块全局配置（仅管理员，存于 system_settings，全局唯一）。"""
    from app.services.system_setting_service import SystemSettingService

    svc = SystemSettingService(db)
    await svc.set_setting(REMOTE_CONFIG_URL_KEY, (request.url or "").strip(), "远程过滑块服务URL")
    await svc.set_setting(REMOTE_CONFIG_SECRET_KEY, (request.secret_key or "").strip(), "远程过滑块秘钥")
    return ApiResponse(success=True, message="保存成功")
