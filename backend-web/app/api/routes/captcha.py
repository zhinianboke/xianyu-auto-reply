"""
验证码路由聚合入口及旧模块兼容导出。

功能：
1. 挂载图形验证码、邮箱验证码与远程滑块子路由
2. 保留 /captcha 前缀、路由名称和已有公共导入
"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.routes.captcha_email import (
    SendCodeRequest,
    send_email_verification_code,
    verify_email_code,
    router as email_router,
)
from app.api.routes.captcha_image import (
    CaptchaRequest,
    VerifyCaptchaRequest,
    captcha_store,
    cleanup_expired_captcha,
    generate_captcha,
    generate_captcha_image,
    generate_captcha_text,
    verify_captcha,
    router as image_router,
)
from app.api.routes.captcha_remote import (
    RemoteConfigUpdate,
    SliderSolveRequest,
    TestRemoteSolveRequest,
    get_remote_config,
    slider_solve,
    test_remote_slider_solve,
    update_remote_config,
    router as remote_router,
)
from common.services.email_verification_code_service import (
    MAX_EMAIL_CODE_ATTEMPTS,
    check_email_code,
    cleanup_expired_email_codes,
    email_code_store,
    generate_verification_code,
)

router = APIRouter(prefix="/captcha", tags=["验证码"])
router.include_router(image_router)
router.include_router(email_router)
router.include_router(remote_router)
